"""Third routing tier: an LLM emits a *plan*, never an answer.

WHEN THIS IS ALLOWED TO EXIST
-------------------------------
ADR-017 forbade a planner until the deterministic failure rate was a measured
number, and ADR-019 measured it. After both deterministic tiers run, on the 49
answerable questions of `eval/robustness/routing_robustness_v1.json`:

    routed by a template            11
    routed by cue fallback          19
    reaching no route at all        19   <- 39%, and this is what a planner is for

Two deterministic tiers leave 39% of realistic questions unrouted. That is the
condition under which a planner was permitted, and it is why this module
exists. It is a third tier, not a replacement: it runs only after both
deterministic tiers have declined.

WHAT THE MODEL IS AND IS NOT ALLOWED TO DO
--------------------------------------------
The model produces a `QueryPlan` - a start entity and an ordered list of
relations - and nothing else. It never sees the graph's contents, never
receives evidence, and never writes an answer. Everything after the plan is
the same deterministic machinery every other tier uses:

    question -> [template] -> [cue fallback] -> LLM plan -> VALIDATE -> walk_relations

`validate_plan` is the load-bearing step and is deliberately unforgiving. A
plan naming an entity the graph does not have, or a relation
`config/relations.yaml` does not define, is rejected outright rather than
repaired - a repaired plan is a guess wearing a plan's clothes. Rejection
returns the previous tier's honest non-answer.

This is the same rule ADR-011 applies to entity resolution and ADR-016 to the
graph: the system may abstain, and may never invent. A model that returns
`ederon_fellgar` gets nothing; it does not get `ederon_fellgard`.

COST AND COUNTING
-------------------
CLAUDE.md requires every LLM fallback to be counted. `PlannerOutcome.escalated`
and `.model` record each call, `OpenRouterPool.usage` records the spend, and
responses are cached by prompt so a re-run of the same question is free. With
no `OPENROUTER_API_KEY` configured this tier is skipped silently and the engine
reports the deterministic tiers' own result - the system remains fully usable
without a key, which is how it runs in CI and how it must run if a demo
machine has no network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.graph.build import RelationMap
from src.graph.schema import Graph
from src.graph.traverse import Path, walk_relations

MAX_PLAN_HOPS = 3

#: Per-model wall-clock bound for a planning call. See `plan_and_walk`.
PLANNER_TIMEOUT_S = 15

#: The only shape the model may return. `strict: True` is set by the client, so
#: a compliant model cannot add fields; `validate_plan` re-checks anyway,
#: because "the schema was declared" and "the response honoured it" are
#: different claims and only the second one matters.
PLAN_SCHEMA: dict = {
    "name": "query_plan",
    "schema": {
        "type": "object",
        "properties": {
            "start_entity": {
                "type": "string",
                "description": "Exact name of the entity the question starts from.",
            },
            "relations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Relations to follow in order, 1 to 3 of them.",
            },
            "answer_type": {
                "type": "string",
                "description": (
                    "Kind of thing the question asks for: character, faction, "
                    "location, conflict, artifact, creature, or unknown."
                ),
            },
        },
        "required": ["start_entity", "relations", "answer_type"],
        "additionalProperties": False,
    },
}

#: The coarse taxonomy `src/graph/metadata.py` assigns. A model returning
#: anything else is returning a word, not a type - MEASURED, live: a planner
#: asked about the sky returned `answer_type: "plan"`.
KNOWN_ANSWER_TYPES = frozenset(
    {"character", "faction", "location", "conflict", "artifact", "creature"}
)

_PROMPT = """You are planning a graph traversal. You are NOT answering the question.

Return a plan naming which entity to start from and which relations to follow, in order.

Rules:
- start_entity MUST be copied character for character from the entity list below,
  and MUST be an entity the question actually names. Do not pick an entity merely
  because it shares a word with the question.
- Every relation MUST be copied character for character from the relation list below.
- Use at most {max_hops} relations. Order matters: relations[0] is the first hop.
- DECLINE when you should. Return start_entity as "" and relations as [] if either:
    * the question names no entity on the list, or
    * the question asks about something no relation on the list can express
      (for example colour, diet, appearance, feelings, weather, or motive).
  Declining is correct and expected. A plan that fits the lists but does not fit
  the question is worse than no plan.
- Do not answer the question. Do not explain. Return only the plan.

Known entities:
{entities}

Known relations:
{relations}

Question: {question}"""


@dataclass(frozen=True)
class QueryPlan:
    """A validated traversal instruction. Only `validate_plan` may build one."""

    start_key: str
    relations: tuple[str, ...]
    answer_type: str | None


@dataclass(frozen=True)
class PlannerOutcome:
    """What the planner tier did, including when it did nothing.

    `escalated` is True whenever a model was actually called, so the harness
    can report what fraction of questions needed one - the number CLAUDE.md
    requires of every LLM fallback.
    """

    plan: QueryPlan | None
    paths: tuple[Path, ...]
    escalated: bool
    model: str | None = None
    rejection: str | None = None

    @property
    def answered(self) -> bool:
        return bool(self.paths)


_WORD_RE = re.compile(r"[a-z0-9]+")

#: Tokens too common to ground an entity on. "The Ashen Vanguard" must not be
#: grounded by the word "the".
_GROUNDING_STOPWORDS = frozenset({"the", "of", "a", "an", "and", "or"})


def is_grounded(entity_name: str, question: str) -> bool:
    """True when the question actually names this entity, not just a word of it.

    MEASURED BUG THIS EXISTS TO STOP. Asked "What color is the sky in the Ashen
    Era?" - a question the corpus cannot answer - a live planner returned a
    well-formed plan starting from **The Ashen Vanguard**, because the question
    contains the word "Ashen". `validate_plan` accepted it: the entity is real
    and the relation is real. The result was a confident, evidence-trailed
    answer to a question nobody asked, which is the exact failure this project
    exists to prevent.

    Well-formedness is not relevance. So every significant token of the
    entity's name must appear somewhere in the question. "Ashen Vanguard"
    needs both "ashen" and "vanguard"; sharing one word is not naming it.

    This is looser than `fallback.find_mentions`, which requires a *contiguous*
    run - deliberately, because rephrasing is the planner's whole purpose
    ("where the Gravemaw Wyrm sleeps" should still ground on Gravemaw Wyrm).
    It is far stricter than nothing, which is what it replaces.
    """
    asked = set(_WORD_RE.findall(question.lower()))
    tokens = {
        t for t in _WORD_RE.findall(entity_name.lower()) if t not in _GROUNDING_STOPWORDS
    }
    if not tokens:
        return False
    return tokens <= asked


def validate_plan(
    raw: dict, graph: Graph, relations: RelationMap, question: str = ""
) -> tuple[QueryPlan | None, str | None]:
    """Turn a model's JSON into a `QueryPlan`, or say why it cannot be one.

    Returns (plan, None) or (None, reason). Never repairs, never guesses,
    never partially accepts: a plan whose second hop names an unknown relation
    is rejected whole, because executing its valid prefix would answer a
    question nobody asked.

    `question` is required for the grounding check and defaults to empty only
    so older callers keep working; pass it.
    """
    start_name = raw.get("start_entity")
    if not isinstance(start_name, str) or not start_name.strip():
        return None, "planner declined: no start entity"

    by_name = {node.name: key for key, node in graph.nodes.items()}
    start_key = by_name.get(start_name.strip())
    if start_key is None:
        # Exact match only, ADR-011. `caedmon_fellgard` and `ederon_fellgard`
        # are 0.839 similar; no threshold loose enough to be useful is safe
        # here, and a model's near-miss is not evidence of intent.
        return None, f"planner named an entity the graph does not have: {start_name!r}"

    if question and not is_grounded(start_name.strip(), question):
        return None, (
            f"planner named {start_name!r}, which the question does not name - "
            "sharing a word is not naming an entity"
        )

    raw_relations = raw.get("relations")
    if not isinstance(raw_relations, list):
        return None, "planner returned a malformed relations field"
    if not raw_relations:
        # An explicit decline. The prompt asks for this when no relation can
        # express the question, and it is the correct outcome for "what did it
        # eat for breakfast" - so it is reported as a decline, not an error.
        return None, "planner declined: no relation expresses this question"
    if len(raw_relations) > MAX_PLAN_HOPS:
        return None, (
            f"planner asked for {len(raw_relations)} hops; the bound is {MAX_PLAN_HOPS}"
        )

    known = set(relations.inverses)
    chain: list[str] = []
    for relation in raw_relations:
        if not isinstance(relation, str):
            return None, "planner returned a non-string relation"
        if relation not in known:
            return None, f"planner named an unknown relation: {relation!r}"
        chain.append(relation)

    answer_type = raw.get("answer_type")
    if not isinstance(answer_type, str) or answer_type.strip().lower() not in KNOWN_ANSWER_TYPES:
        # MEASURED, live: a planner asked about the sky returned
        # `answer_type: "plan"`. An unrecognised word must become "no type
        # hint", never a filter that silently eliminates every candidate.
        answer_type = None
    else:
        answer_type = answer_type.strip().lower()

    return QueryPlan(start_key, tuple(chain), answer_type), None


def plan_and_walk(
    question: str,
    graph: Graph,
    relations: RelationMap,
    *,
    pool: object | None = None,
) -> PlannerOutcome:
    """Ask a model for a plan, validate it, then walk it deterministically.

    Args:
        pool: An `OpenRouterPool`-shaped client, injected by tests. Built fresh
            when omitted, which needs `OPENROUTER_API_KEY`.

    Never raises for an absent key, an exhausted rotation or a malformed plan -
    all four are reported as an un-answered `PlannerOutcome` so the caller can
    fall back to the deterministic tiers' own honest non-answer.
    """
    if pool is None:
        try:
            from src.clients.openrouter import PLANNER_MODELS, OpenRouterPool

            pool = OpenRouterPool(models=PLANNER_MODELS)
        except RuntimeError as error:
            # No API key configured. Not an error condition: the system is
            # designed to run fully without one.
            return PlannerOutcome(None, (), False, rejection=str(error))

    prompt = _PROMPT.format(
        max_hops=MAX_PLAN_HOPS,
        entities="\n".join(sorted(node.name for node in graph.nodes.values())),
        relations="\n".join(sorted(relations.inverses)),
        question=question,
    )

    try:
        raw, model = pool.generate_structured(
            [prompt],
            PLAN_SCHEMA,
            description="query planning",
            # Bounded on purpose. This tier sits in front of a person waiting
            # for an answer, and free models are slow. One attempt per model
            # across the rotation caps the worst case at roughly
            # len(PLANNER_MODELS) * PLANNER_TIMEOUT_S instead of letting
            # exponential backoff stack on top of it. A planner that hangs a
            # demo is worse than a planner that declines.
            timeout=PLANNER_TIMEOUT_S,
            attempts=1,
        )
    except Exception as error:  # noqa: BLE001 - every failure degrades the same way
        return PlannerOutcome(None, (), True, rejection=f"planner call failed: {error}")

    plan, reason = validate_plan(raw, graph, relations, question)
    if plan is None:
        return PlannerOutcome(None, (), True, model=model, rejection=reason)

    # From here on nothing the model said is trusted. `walk_relations` is the
    # same deterministic traversal every other tier uses, and the evidence it
    # returns is the graph's, not the model's.
    paths = walk_relations(graph, plan.start_key, list(plan.relations))
    return PlannerOutcome(plan, tuple(paths), True, model=model)
