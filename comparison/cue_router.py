"""Arm B of the router comparison: the sister prototype's cue-based routing.

WHAT THIS IS, AND WHAT IT IS NOT
---------------------------------
This is a faithful reimplementation of `graph/src/query/router.py` from the
sister prototype (github.com/YasiruRF/delphi, their ADR-019), transplanted
onto *our* stack. It exists to be measured against `src/query/route.py`, not
to replace it. Nothing in `src/` imports this module and nothing should.

THE CONTROLLED VARIABLE
------------------------
Exactly one thing differs between arm A and arm B: **how a question becomes a
set of candidate paths.** Everything downstream is ours and is held constant -
the same graph, the same `find_paths`, the same `EntityResolver` where
resolution is needed, the same `src/query/conflict.py`. A difference in the
measured numbers is therefore attributable to routing, which is the point of
running this at all.

Three deliberate departures from the sister implementation, each of which
would otherwise confound the measurement:

1. **No LLM escalation.** Their router calls OpenRouter when no entity
   resolves or no relation is cued. Ours has no LLM at all, so comparing with
   escalation live would measure "has an LLM" rather than "routes better".
   Both escalation points are instead *recorded* as `would_escalate`, which
   is precisely the deterministic failure rate Phase 4 needs before deciding
   whether a planner is warranted at all.

2. **Their conflict rule, ported.** Arm B uses
   `comparison/sister_conflicts.py`, a port of their `trust/conflicts.py`,
   NOT our `src/query/conflict.py`. Using ours confounded the measurement:
   it is paragraph-scoped, over-fired as a general per-edge filter, and
   turned 1b_007 and 1b_022 into false `not_found`s. See that module's
   docstring for the measurement. Comparing the two conflict detectors on
   the merits is Phase 2 work, not this.

3. **Their `profile` status is retained but never model-phrased.** With no
   model available it degenerates to "an entity resolved but no relation was
   identified", which is what it amounts to for routing purposes.

Every guard below carries the sister repo's own measured justification,
because Phase 2 tests these four individually and needs to know what each one
was for. Each is switchable so they can be ablated one at a time.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from src.graph.build import RelationMap
from src.graph.schema import Graph
from src.graph.traverse import Path, find_paths

MAX_HOPS = 3

#: Prepositions/articles/auxiliaries that would otherwise pollute every
#: relation's cue set - nearly every field name in relations.yaml contains
#: "of" or "by".
CUE_STOPWORDS = frozenset(
    {
        "of", "by", "in", "at", "the", "a", "an", "to", "is", "was", "are",
        "were", "for", "has", "have", "on", "and", "or",
    }
)

_NON_ALNUM = re.compile(r"[^a-z0-9\s]+")

#: GUARD 4 (irregular verbs). relations.yaml's only victor_of vocabulary is
#: "victor" (field names) and "won" (from the inverse won_by); neither shares
#: a strippable suffix with "win", and dev question 1b_022 asks
#: "...ultimately win?".
IRREGULAR_VERBS = {"win": "won", "wins": "won", "winning": "won"}

#: Suffix stripping down to a 3-character floor, so short cues are not
#: hollowed out. Connects "wields"/"wielded", "rules"/"ruling".
STRIPPABLE_SUFFIXES = ("ing", "ed", "es", "s")


def normalize_cue_word(
    word: str, *, irregulars: bool = True, strip_final_e: bool = False
) -> str:
    """Fold a word toward the stem its cue set is keyed under.

    MEASURED DEFECT, and what `strip_final_e` is for. The sister
    implementation strips suffixes only. That is asymmetric: `ruled`, `rules`
    and `ruling` all fold to `rul`, but the *base* form `rule` has no
    strippable suffix and stays `rule`, so it never matches the `rul` cue
    built from the field name `Ruled by`. Measured on the frozen robustness
    set, a question asking "falls under whose rule?" fails to cue `ruled_by`
    while "which power rules..." succeeds. Same for `house` vs the `hous`
    cue from `Housed in`.

    `strip_final_e=True` also drops a trailing "e", aligning base forms with
    the suffix-stripped stems. Off by default so the sister router is
    measured as written; the harness runs it on as an ablation to separate
    "fixable defect" from "limit of cue-based routing".
    """
    if irregulars and word in IRREGULAR_VERBS:
        return IRREGULAR_VERBS[word]
    for suffix in STRIPPABLE_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    if strip_final_e and word.endswith("e") and len(word) > 3:
        return word[:-1]
    return word


def question_tokens(text: str) -> list[str]:
    """Lowercase, punctuation-folded tokens. Nothing dropped.

    The sister repo measured a live bug here: dropping every "the" broke
    `Cerys Sablewood the Ashen` and `Corvus Hollowmere the Pale`, whose keys
    carry "the" as a title rather than an article. Nothing is dropped, because
    `find_entity_mentions` matches a key-token run at *any* offset, so a
    leading article never needed special handling in the first place.
    """
    return _NON_ALNUM.sub(" ", text.lower()).split()


def _cue_tokens(
    *names: str, irregulars: bool = True, strip_final_e: bool = False
) -> set[str]:
    out: set[str] = set()
    for name in names:
        for word in _NON_ALNUM.sub(" ", name.lower()).split():
            if word not in CUE_STOPWORDS:
                out.add(
                    normalize_cue_word(
                        word, irregulars=irregulars, strip_final_e=strip_final_e
                    )
                )
    return out


def relation_cues(
    relations: RelationMap, *, irregulars: bool = True, strip_final_e: bool = False
) -> dict[str, set[str]]:
    """relation -> cue words, built entirely from config/relations.yaml.

    Sources per relation: its own name, its inverse's name, and every field
    name mapped to it in either direction. This is the same config the graph
    builder reads, so the recognised vocabulary cannot drift from the edges
    that actually exist.
    """
    fields_by_relation: dict[str, list[str]] = defaultdict(list)
    for field_name, relation in relations.forward.items():
        fields_by_relation[relation].append(field_name)
    for field_name, relation in relations.reverse.items():
        fields_by_relation[relation].append(field_name)

    cues: dict[str, set[str]] = {}
    for relation, fields in fields_by_relation.items():
        inverse = relations.inverses.get(relation, relation)
        cues[relation] = _cue_tokens(
            relation, inverse, *fields, irregulars=irregulars,
            strip_final_e=strip_final_e,
        )
    return cues


def cued_relations(
    cues: dict[str, set[str]],
    question: str,
    *,
    irregulars: bool = True,
    strip_final_e: bool = False,
) -> set[str]:
    """Every relation with at least one cue word present in the question."""
    tokens = {
        normalize_cue_word(t, irregulars=irregulars, strip_final_e=strip_final_e)
        for t in question_tokens(question)
    }
    return {relation for relation, words in cues.items() if tokens & words}


@dataclass(frozen=True)
class EntityMention:
    key: str
    name: str
    token_count: int


def find_entity_mentions(graph: Graph, question: str) -> list[EntityMention]:
    """Every known node whose key appears as a contiguous token run.

    On overlapping spans the longer match wins, which is what stops a node
    whose name is a substring of another's from being reported twice for the
    same words. Returns matches longest-first.
    """
    tokens = question_tokens(question)
    candidates: list[tuple[EntityMention, int, int]] = []

    for node in graph.nodes.values():
        key_tokens = node.key.split("_")
        n = len(key_tokens)
        if n == 0:
            continue
        for start in range(len(tokens) - n + 1):
            if tokens[start : start + n] == key_tokens:
                candidates.append(
                    (EntityMention(node.key, node.name, n), start, start + n)
                )

    candidates.sort(key=lambda c: (-c[0].token_count, c[1]))
    kept: list[tuple[EntityMention, int, int]] = []
    covered: set[int] = set()
    for mention, start, end in candidates:
        span = set(range(start, end))
        if span & covered:
            continue
        covered |= span
        kept.append((mention, start, end))

    seen: dict[str, EntityMention] = {}
    for mention, _, _ in kept:
        seen.setdefault(mention.key, mention)
    return sorted(seen.values(), key=lambda m: -m.token_count)


def no_consecutive_repeat(path: Path) -> bool:
    """GUARD 1. False if the same relation is used on two hops in a row.

    Sister repo's measurement: bidirectional traversal lets a walk arrive at
    a high-fan-in hub via one member_of edge and leave via a different
    member_of edge down to a sibling. Ederon Fellgard -> member_of ->
    Iron-Ring Cartel -> member_of -> Caedmon Fellgard is a real two-hop path,
    ties in length with the genuine member_of -> victor_of chain, and won the
    tie-break outright because Ederon and Caedmon share the surname
    "Fellgard". No `acceptable_paths` entry in our own answer_key.json
    repeats a relation on consecutive hops.
    """
    return all(a.relation != b.relation for a, b in zip(path.edges, path.edges[1:]))


def select_candidates(cued_paths: list[Path]) -> list[Path]:
    """GUARD 2. Maximise distinct cued relations covered, then take shortest.

    Sister repo's measurement: "keep the longest cued chain" is wrong.
    relations.yaml maps `Known participant`/`Notable fighter` onto member_of's
    reverse direction, so a cued chain can validly run *past* the correct
    two-hop answer into a third hop landing on a combatant the corpus never
    meant as the answer here. Preferring length silently swaps that combatant
    in. Coverage must be scored before length, because a longer path can tie
    a shorter one's coverage without a plain length comparison noticing.
    """
    if not cued_paths:
        return []

    def coverage(path: Path) -> int:
        return len({edge.relation for edge in path.edges})

    max_coverage = max(coverage(p) for p in cued_paths)
    at_max = [p for p in cued_paths if coverage(p) == max_coverage]
    min_hops = min(len(p.edges) for p in at_max)
    return [p for p in at_max if len(p.edges) == min_hops]


def _shortest_only(cued_paths: list[Path]) -> list[Path]:
    """Guard-2 ablation: plain shortest-path selection, no coverage scoring."""
    if not cued_paths:
        return []
    min_hops = min(len(p.edges) for p in cued_paths)
    return [p for p in cued_paths if len(p.edges) == min_hops]


@dataclass(frozen=True)
class CueRouteResult:
    """Arm B's output.

    `status` mirrors the sister router's vocabulary:
        answered           - exactly one end node survived
        any_of             - more than one end node survived the tie-break
        not_found          - start and relations identified, no path reaches
                             an answer
        unresolved_entity  - no known entity matched
        profile            - an entity resolved but no relation was cued
                             ("Who is X?"). Their router hands this to a model;
                             with no model it is a routing non-answer.
    """

    status: str
    start: EntityMention | None
    paths: tuple[Path, ...]
    cued: tuple[str, ...]
    #: "entity" | "relation" | None - where the sister router would have
    #: called a model. This is the deterministic failure rate Phase 4 needs.
    would_escalate: str | None = None


def route_question(
    graph: Graph,
    question: str,
    relations: RelationMap,
    *,
    cues: dict[str, set[str]] | None = None,
    use_no_consecutive_repeat: bool = True,
    use_coverage_selection: bool = True,
    use_tiebreak_stopwords: bool = True,
    use_irregular_verbs: bool = True,
    use_symmetric_stemming: bool = False,
) -> CueRouteResult:
    """Route a question by relation cues rather than trigger templates.

    Each of the four guards is switchable so Phase 2 can ablate them one at a
    time against the same frozen question set.
    """
    cues = (
        cues
        if cues is not None
        else relation_cues(
            relations,
            irregulars=use_irregular_verbs,
            strip_final_e=use_symmetric_stemming,
        )
    )

    mentions = find_entity_mentions(graph, question)
    if not mentions:
        return CueRouteResult("unresolved_entity", None, (), (), "entity")

    if len(mentions) >= 2:
        start, goal = mentions[0], mentions[1]
        paths = find_paths(graph, start.key, goal.key, max_hops=MAX_HOPS)
        return CueRouteResult(
            "answered" if paths else "not_found", start, tuple(paths), ()
        )

    start = mentions[0]
    cued = cued_relations(
        cues,
        question,
        irregulars=use_irregular_verbs,
        strip_final_e=use_symmetric_stemming,
    )

    if not cued:
        return CueRouteResult("profile", start, (), (), "relation")

    all_paths = find_paths(graph, start.key, max_hops=MAX_HOPS)
    cued_paths = [
        p
        for p in all_paths
        if p.edges
        and all(e.relation in cued for e in p.edges)
        and (no_consecutive_repeat(p) if use_no_consecutive_repeat else True)
    ]
    candidates = (
        select_candidates(cued_paths)
        if use_coverage_selection
        else _shortest_only(cued_paths)
    )

    if not candidates:
        return CueRouteResult("not_found", start, (), tuple(sorted(cued)))

    ends: dict[str, list[Path]] = defaultdict(list)
    for p in candidates:
        ends[p.end].append(p)

    if len(ends) == 1:
        return CueRouteResult(
            "answered", start, tuple(next(iter(ends.values()))), tuple(sorted(cued))
        )

    # GUARD 3 (tie-break stopwords). question_tokens keeps "the" verbatim on
    # purpose - several corpus names carry it as a title. But that same "the"
    # is grammatical scaffolding in most questions ("the faction that..."),
    # and several *different* people carry a "the X" epithet of their own
    # ("Corvus Hollowmere the Pale", "Maelis Harrowick the Pale"). Sister repo
    # measured "the" alone tipping the 1b_006 tie-break toward those two,
    # collapsing a genuine 14-way any_of to 2. Stopwords are filtered here, at
    # the tie-break only, never in entity matching.
    stop = CUE_STOPWORDS if use_tiebreak_stopwords else frozenset()
    q_tokens = {t for t in question_tokens(question) if t not in stop}
    scored = []
    for end_key, ps in ends.items():
        name = graph.nodes[end_key].name if end_key in graph.nodes else end_key
        name_tokens = {t for t in question_tokens(name) if t not in stop}
        scored.append((len(name_tokens & q_tokens), ps))

    max_overlap = max(score for score, _ in scored)
    winners = [ps for score, ps in scored if score == max_overlap]

    if len(winners) == 1:
        return CueRouteResult(
            "answered", start, tuple(winners[0]), tuple(sorted(cued))
        )
    return CueRouteResult(
        "any_of", start, tuple(p for ps in winners for p in ps), tuple(sorted(cued))
    )
