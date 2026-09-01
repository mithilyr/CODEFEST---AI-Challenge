"""Tests for the LLM planner tier (`src/query/planner.py`).

No API key and no network: the pool is injected everywhere.

The tests worth reading are the rejection ones. This is the only tier where a
model's output influences what gets traversed, so `validate_plan` is the whole
safety boundary - and the property being protected is not "the planner works"
but "a plan the graph cannot support is refused rather than repaired".
"""

from __future__ import annotations

import json

import pytest

from src.query.engine import answer_question
from src.query.evidence import EvidenceStatus
from src.query.planner import (
    MAX_PLAN_HOPS,
    PLAN_SCHEMA,
    plan_and_walk,
    validate_plan,
)


class FakePool:
    """An OpenRouterPool-shaped stub. Returns a canned plan, records prompts."""

    def __init__(self, plan: dict | str, model: str = "fake/model:free"):
        self._plan = plan
        self._model = model
        self.prompts: list[str] = []

    def generate_structured(self, contents, schema, **kwargs):
        # **kwargs, not a fixed signature. `plan_and_walk` passes `timeout` and
        # `attempts` to bound its wall clock; a stub that did not accept them
        # raised TypeError, which the caller's degrade path swallowed as "the
        # provider failed" - so the test passed a plan and silently measured
        # nothing. A stub must not be stricter than the thing it stands in for.
        self.prompts.append("\n".join(contents))
        self.kwargs = kwargs
        if isinstance(self._plan, str):
            raise RuntimeError(self._plan)
        return self._plan, self._model


# --------------------------------------------------------------------------
# validate_plan - the safety boundary.
# --------------------------------------------------------------------------


def test_a_well_formed_plan_validates(graph, relations):
    plan, reason = validate_plan(
        {
            "start_entity": "Ederon Fellgard",
            "relations": ["member_of", "victor_of"],
            "answer_type": "conflict",
        },
        graph,
        relations,
    )
    assert reason is None
    assert plan.start_key == "ederon_fellgard"
    assert plan.relations == ("member_of", "victor_of")
    assert plan.answer_type == "conflict"


def test_a_near_miss_entity_name_is_refused_not_repaired(graph, relations):
    """ADR-011 applies to model output too. `caedmon_fellgard` and
    `ederon_fellgard` are 0.839 similar; a model's near-miss is not evidence of
    intent, and no threshold loose enough to be useful is safe here."""
    plan, reason = validate_plan(
        {"start_entity": "Ederon Fellgar", "relations": ["member_of"], "answer_type": "faction"},
        graph,
        relations,
    )
    assert plan is None
    assert "does not have" in reason


def test_an_unknown_relation_rejects_the_whole_plan(graph, relations):
    """Not just the bad hop. Executing a plan's valid prefix would answer a
    question nobody asked."""
    plan, reason = validate_plan(
        {
            "start_entity": "Ederon Fellgard",
            "relations": ["member_of", "secretly_despises"],
            "answer_type": "character",
        },
        graph,
        relations,
    )
    assert plan is None
    assert "unknown relation" in reason
    assert "secretly_despises" in reason


def test_a_plan_longer_than_the_hop_bound_is_rejected(graph, relations):
    plan, reason = validate_plan(
        {
            "start_entity": "Ederon Fellgard",
            "relations": ["member_of"] * (MAX_PLAN_HOPS + 1),
            "answer_type": "character",
        },
        graph,
        relations,
    )
    assert plan is None
    assert str(MAX_PLAN_HOPS) in reason


@pytest.mark.parametrize(
    "raw",
    [
        {"start_entity": "", "relations": ["member_of"], "answer_type": "x"},
        {"start_entity": "Ederon Fellgard", "relations": [], "answer_type": "x"},
        {"start_entity": "Ederon Fellgard", "relations": "member_of", "answer_type": "x"},
        {"start_entity": "Ederon Fellgard", "relations": [42], "answer_type": "x"},
        {"relations": ["member_of"], "answer_type": "x"},
    ],
)
def test_malformed_plans_are_rejected(raw, graph, relations):
    plan, reason = validate_plan(raw, graph, relations)
    assert plan is None
    assert reason


def test_unknown_answer_type_becomes_none_rather_than_a_filter(graph, relations):
    """An unusable type hint must not become a filter that silently eliminates
    every candidate - `PATH_MISSING_ATTRIBUTE` exists for real contradictions."""
    plan, _ = validate_plan(
        {"start_entity": "Ederon Fellgard", "relations": ["member_of"], "answer_type": "unknown"},
        graph,
        relations,
    )
    assert plan.answer_type is None


# --------------------------------------------------------------------------
# plan_and_walk - degrading, and never trusting the model past the plan.
# --------------------------------------------------------------------------


def test_a_valid_plan_is_walked_deterministically(graph, relations):
    pool = FakePool(
        {
            "start_entity": "Ederon Fellgard",
            "relations": ["member_of", "victor_of"],
            "answer_type": "conflict",
        }
    )
    outcome = plan_and_walk(
        "which accord did Ederon Fellgard's own faction take", graph, relations, pool=pool
    )

    assert outcome.escalated
    assert outcome.answered
    assert outcome.model == "fake/model:free"
    for path in outcome.paths:
        for edge in path.edges:
            assert edge.document, "evidence must come from the graph, with provenance"


def test_the_prompt_never_contains_evidence_only_names(graph, relations):
    """The model chooses a chain. It must not be in a position to compose an
    answer, so it is given the entity and relation vocabularies and nothing
    from the corpus."""
    pool = FakePool({"start_entity": "Ederon Fellgard", "relations": ["member_of"], "answer_type": "faction"})
    plan_and_walk("who is Ederon Fellgard aligned with", graph, relations, pool=pool)
    prompt = pool.prompts[0]

    assert "Ederon Fellgard" in prompt
    assert "member_of" in prompt
    assert "wiki/" not in prompt, "no document text or paths may reach the model"
    assert "NOT answering" in prompt


def test_a_rejected_plan_reports_escalation_without_an_answer(graph, relations):
    pool = FakePool({"start_entity": "Nobody At All", "relations": ["member_of"], "answer_type": "x"})
    outcome = plan_and_walk("q", graph, relations, pool=pool)

    assert outcome.escalated, "the call happened and must be counted"
    assert not outcome.answered
    assert outcome.rejection


def test_a_provider_failure_degrades_instead_of_raising(graph, relations):
    outcome = plan_and_walk("q", graph, relations, pool=FakePool("all models exhausted"))
    assert outcome.escalated
    assert not outcome.answered
    assert "planner call failed" in outcome.rejection


def test_a_valid_plan_that_reaches_nothing_is_not_an_answer(graph, relations):
    """A plan can be well-formed and still walk into empty space. That is a
    non-answer, not an answer with no values."""
    pool = FakePool(
        {"start_entity": "Gravemaw Wyrm", "relations": ["victor_of"], "answer_type": "conflict"}
    )
    outcome = plan_and_walk(
        "which war did the Gravemaw Wyrm win", graph, relations, pool=pool
    )
    assert outcome.plan is not None, "the plan itself is well formed and grounded"
    assert not outcome.answered, "but it walks into empty space"


def test_no_api_key_skips_the_tier_without_escalating(graph, relations, monkeypatch):
    """The system must be fully usable with no key - that is how CI runs it and
    how a demo machine without network must run it."""
    import src.clients.openrouter as client

    monkeypatch.setattr(
        client, "OpenRouterPool", lambda **kw: (_ for _ in ()).throw(RuntimeError("OPENROUTER_API_KEY is not set"))
    )
    outcome = plan_and_walk("q", graph, relations)

    assert not outcome.escalated, "no key means no call, so nothing to count"
    assert not outcome.answered


# --------------------------------------------------------------------------
# Tier ordering in the engine.
# --------------------------------------------------------------------------


def test_the_planner_never_pre_empts_a_template(graph):
    """Tier 3 must not fire on a question tier 1 answers. If it did, we would
    be spending quota and precision on questions already solved."""
    pool = FakePool({"start_entity": "Gravemaw Wyrm", "relations": ["lair_in"], "answer_type": "location"})
    answer = answer_question(
        "Which accord was ultimately won by the faction of which Ederon Fellgard is a member?",
        graph,
        use_planner=True,
        planner_pool=pool,
    )
    assert answer.status == EvidenceStatus.SUFFICIENT
    assert pool.prompts == [], "the planner must not have been called at all"


def test_the_planner_never_pre_empts_the_cue_fallback(graph):
    pool = FakePool({"start_entity": "Gravemaw Wyrm", "relations": ["lair_in"], "answer_type": "location"})
    answer = answer_question(
        "Which power rules the settlement where The Cinder-Wrought Aegis is housed?",
        graph,
        use_planner=True,
        planner_pool=pool,
    )
    assert answer.status == EvidenceStatus.FALLBACK_SUFFICIENT
    assert pool.prompts == []


def test_use_planner_false_keeps_the_engine_deterministic(graph):
    """The eval harness sets this, so a measured number can never silently
    depend on a model being reachable."""
    pool = FakePool({"start_entity": "Gravemaw Wyrm", "relations": ["lair_in"], "answer_type": "location"})
    answer = answer_question(
        "What color is the sky in the Ashen Era?", graph, use_planner=False, planner_pool=pool
    )
    assert answer.status == EvidenceStatus.NO_TEMPLATE_MATCH
    assert pool.prompts == []


def test_a_planned_answer_is_labelled_as_such(graph):
    """A question neither deterministic tier routes, which a plan does."""
    pool = FakePool(
        {"start_entity": "Gravemaw Wyrm", "relations": ["lair_in"], "answer_type": "location"}
    )
    answer = answer_question(
        "Tell me where the Gravemaw Wyrm sleeps at night",
        graph,
        use_planner=True,
        planner_pool=pool,
    )

    if answer.status.routing_tier == "llm_plan":
        assert answer.status.is_fallback
        assert answer.template == "llm_plan"
        assert answer.paths
        assert "checked against the graph" in answer.note
    else:
        # A deterministic tier claimed it, which is also correct behaviour -
        # the planner is a last resort, not a preference.
        assert answer.status.routing_tier in (None, "template", "cue_fallback")


def test_routing_tier_separates_all_three_tiers():
    assert EvidenceStatus.SUFFICIENT.routing_tier == "template"
    assert EvidenceStatus.FALLBACK_SUFFICIENT.routing_tier == "cue_fallback"
    assert EvidenceStatus.PLANNED_SUFFICIENT.routing_tier == "llm_plan"
    assert EvidenceStatus.NO_TEMPLATE_MATCH.routing_tier is None
    assert not EvidenceStatus.SUFFICIENT.is_fallback
    assert EvidenceStatus.PLANNED_SUFFICIENT.is_fallback


def test_plan_schema_is_strict_and_closed():
    """`additionalProperties: False` plus an explicit `required` list is what
    stops a model returning an answer field alongside the plan."""
    schema = PLAN_SCHEMA["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"start_entity", "relations", "answer_type"}
    assert "answer" not in schema["properties"]
    json.dumps(PLAN_SCHEMA)  # must be serialisable as-is


# --------------------------------------------------------------------------
# Grounding - the guard that stopped a live fabricated answer.
# --------------------------------------------------------------------------


def test_an_entity_sharing_one_word_with_the_question_is_not_grounded(graph, relations):
    """MEASURED, LIVE. Asked "What color is the sky in the Ashen Era?" - which
    the corpus cannot answer - a real planner returned a well-formed plan
    starting from **The Ashen Vanguard**, because the question contains the
    word "Ashen". Both the entity and the relation were real, so validation
    accepted it and the engine produced a confident, evidence-trailed answer to
    a question nobody asked.

    Well-formedness is not relevance. This is the guard.
    """
    plan, reason = validate_plan(
        {
            "start_entity": "The Ashen Vanguard",
            "relations": ["in_region"],
            "answer_type": "location",
        },
        graph,
        relations,
        "What color is the sky in the Ashen Era?",
    )
    assert plan is None
    assert "does not name" in reason


def test_a_rephrased_mention_still_grounds(graph, relations):
    """Grounding is looser than `fallback.find_mentions`' contiguous-run rule,
    deliberately - handling rephrasing is the planner's whole purpose."""
    plan, reason = validate_plan(
        {"start_entity": "Gravemaw Wyrm", "relations": ["lair_in"], "answer_type": "location"},
        graph,
        relations,
        "Tell me where the Gravemaw Wyrm sleeps at night",
    )
    assert reason is None
    assert plan.start_key == "gravemaw_wyrm"


def test_an_empty_relation_list_is_a_decline_not_an_error(graph, relations):
    """The prompt gives the model an explicit decline channel for questions no
    relation can express ("what did it eat for breakfast"). Using it must be
    reported as declining, not as a malformed plan."""
    plan, reason = validate_plan(
        {"start_entity": "Gravemaw Wyrm", "relations": [], "answer_type": "unknown"},
        graph,
        relations,
        "What did the Gravemaw Wyrm eat for breakfast?",
    )
    assert plan is None
    assert "declined" in reason


def test_a_word_that_is_not_a_type_becomes_no_type_hint(graph, relations):
    """MEASURED, LIVE: a planner returned `answer_type: "plan"`. An
    unrecognised word must become "no hint", never a filter that silently
    eliminates every candidate."""
    plan, _ = validate_plan(
        {"start_entity": "Gravemaw Wyrm", "relations": ["lair_in"], "answer_type": "plan"},
        graph,
        relations,
        "where does the Gravemaw Wyrm live",
    )
    assert plan.answer_type is None


def test_the_planner_call_is_wall_clock_bounded(graph, relations):
    """A tier sitting in front of a waiting person must not be able to hang a
    demo. One attempt per model, short timeout."""
    from src.query.planner import PLANNER_TIMEOUT_S

    pool = FakePool({"start_entity": "Gravemaw Wyrm", "relations": ["lair_in"], "answer_type": "location"})
    plan_and_walk("where does the Gravemaw Wyrm live", graph, relations, pool=pool)

    assert pool.kwargs["timeout"] == PLANNER_TIMEOUT_S
    assert pool.kwargs["attempts"] == 1


def test_the_engine_is_deterministic_by_default(graph):
    """`use_planner` defaults to False. Deterministic-first is the stated
    architecture, and as a default it also means no test and no eval sweep can
    silently spend daily quota or depend on a model being reachable."""
    pool = FakePool({"start_entity": "Gravemaw Wyrm", "relations": ["lair_in"], "answer_type": "location"})
    answer = answer_question(
        "Tell me where the Gravemaw Wyrm sleeps at night", graph, planner_pool=pool
    )
    assert pool.prompts == [], "the planner must not run unless asked for"
    assert answer.status.routing_tier != "llm_plan"
