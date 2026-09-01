"""Tests for answer phrasing (`src/query/synthesis.py`).

The property under test is the boundary, not the prose: the model receives a
verified chain and nothing else, and a phrasing failure never costs us an
answer that was already found.
"""

from __future__ import annotations

import pytest

from src.query.engine import answer_question
from src.query.evidence import EvidenceStatus
from src.query.synthesis import synthesise, template_sentence

DEV_QUESTION = (
    "Which accord was ultimately won by the faction of which "
    "Ederon Fellgard is a member?"
)


@pytest.fixture(scope="module")
def answer(graph):
    return answer_question(DEV_QUESTION, graph, use_planner=False)


class FakePool:
    def __init__(self, text="The Leaden Accord, per wiki/ederon_fellgard.md.", fail=False):
        self._text = text
        self._fail = fail
        self.prompts: list[str] = []

    def generate(self, contents, **kw):
        self.prompts.append("\n".join(contents))
        if self._fail:
            raise RuntimeError("all models exhausted")
        return self._text, "fake/model:free"


# --------------------------------------------------------------------------
# Provenance.
# --------------------------------------------------------------------------


def test_model_phrasing_is_recorded_as_model(answer, graph):
    result = synthesise(answer, graph, pool=FakePool())
    assert result.phrasing == "model"
    assert result.model == "fake/model:free"
    assert result.used_a_model


def test_template_phrasing_is_recorded_as_template(answer, graph):
    result = synthesise(answer, graph, use_model=False)
    assert result.phrasing == "template"
    assert result.model is None
    assert not result.used_a_model


def test_nothing_to_phrase_is_recorded_as_none(graph):
    unrouted = answer_question("What color is the sky in the Ashen Era?", graph, use_planner=False)
    result = synthesise(unrouted, graph, use_model=False)
    assert result.phrasing == "none"
    assert result.text


# --------------------------------------------------------------------------
# Degrading. A phrasing failure must not lose a verified answer.
# --------------------------------------------------------------------------


def test_a_provider_failure_degrades_to_the_template(answer, graph):
    result = synthesise(answer, graph, pool=FakePool(fail=True))
    assert result.phrasing == "template"
    assert "The Leaden Accord" in result.text


def test_an_empty_model_response_degrades_to_the_template(answer, graph):
    result = synthesise(answer, graph, pool=FakePool(text="   "))
    assert result.phrasing == "template"
    assert "The Leaden Accord" in result.text


def test_the_template_names_the_answer_the_route_and_the_sources(answer, graph):
    text = template_sentence(answer, graph)
    assert "The Leaden Accord" in text
    assert "Ederon Fellgard" in text
    assert "wiki/" in text, "a sentence without its sources is not checkable"


# --------------------------------------------------------------------------
# The boundary: what the model is given, and what it is told.
# --------------------------------------------------------------------------


def test_the_model_receives_the_chain_and_is_forbidden_from_adding_to_it(answer, graph):
    pool = FakePool()
    synthesise(answer, graph, pool=pool)
    prompt = pool.prompts[0]

    assert "ALREADY been verified" in prompt
    assert "Do not add any fact that is not in the chain below" in prompt
    assert "member_of" in prompt and "victor_of" in prompt
    assert "wiki/ederon_fellgard.md" in prompt


def test_a_conflict_answer_tells_the_model_not_to_pick_a_side(graph):
    """`1b_009` exists to stop us silently resolving a disagreement the corpus
    does not resolve. A model asked for a clean sentence will pick a side
    unless told not to."""
    conflicted = answer_question(
        "In what way is Halvard Crowhurst connected to the victors of the Purge of Blackport?",
        graph,
        use_planner=False,
    )
    if conflicted.status != EvidenceStatus.CONFLICTING_EVIDENCE:
        pytest.skip("this question no longer routes to a conflict; covered by test_query")

    pool = FakePool()
    synthesise(conflicted, graph, pool=pool)
    assert "do not pick a side" in pool.prompts[0].lower()


def test_the_template_states_a_conflict_rather_than_resolving_it(graph):
    conflicted = answer_question(
        "In what way is Halvard Crowhurst connected to the victors of the Purge of Blackport?",
        graph,
        use_planner=False,
    )
    if conflicted.status != EvidenceStatus.CONFLICTING_EVIDENCE:
        pytest.skip("this question no longer routes to a conflict; covered by test_query")
    assert "disagree" in template_sentence(conflicted, graph)


def test_a_lower_tier_route_warns_the_model_not_to_overstate_confidence(graph):
    fallback = answer_question(
        "Which power rules the settlement where The Cinder-Wrought Aegis is housed?",
        graph,
        use_planner=False,
    )
    assert fallback.status.routing_tier == "cue_fallback"

    pool = FakePool()
    synthesise(fallback, graph, pool=pool)
    assert "lower-precision tier" in pool.prompts[0]
