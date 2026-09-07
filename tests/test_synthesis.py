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


def test_the_template_names_the_answer_and_the_route_but_not_its_sources(answer, graph):
    """The citation tail is gone (ADR-042).

    It read `Sources: wiki/a.md, wiki/b.md.` and was defended as "a sentence
    without its sources is not checkable" - true of a sentence read alone, and
    not true of this one: the hop blocks beneath it carry every document, field
    and row, and the source-documents table lists them again with tiers.
    """
    text = template_sentence(answer, graph)
    assert "The Leaden Accord" in text
    assert "Ederon Fellgard" in text
    assert "Sources:" not in text
    assert "wiki/" not in text


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


# --------------------------------------------------------------------------
# Readability. The sentence has to be a statement, not a data dump (ADR-037).
# --------------------------------------------------------------------------


def test_every_relation_in_the_graph_has_a_phrase(graph):
    """A relation with no phrase falls back to naming itself, which reads badly.

    Pinned against the live graph rather than against the config, so adding a
    relation that actually produces edges fails here until someone words it.
    """
    from src.query.synthesis import _PHRASES

    built = {edge.relation for edge in graph.edges}
    missing = sorted(built - set(_PHRASES))
    assert not missing, f"relations with no phrasing: {missing}"


def test_the_sentence_words_each_hop_instead_of_drawing_arrows(answer, graph):
    """The old template emitted "Route: A -> B -> C" and left the reader to
    work out what each arrow meant. Each hop is now worded in the direction the
    chain walked it."""
    text = template_sentence(answer, graph)
    assert "->" not in text
    assert "Route:" not in text
    assert "is a member of The Iron-Ring Cartel" in text
    assert "which is named victor of The Leaden Accord" in text


def test_a_reverse_hop_is_worded_in_the_direction_it_was_walked(graph):
    """`1b_006` walks `victor_of` backwards, from the war to the faction that
    won it. Phrasing it forward would assert the war won the faction."""
    answer = answer_question(
        "Which individual was a member of the faction that ultimately won "
        "the War of Drowned Light?",
        graph,
        use_planner=False,
    )
    text = template_sentence(answer, graph)
    assert "The War of Drowned Light was won by The Silent Choir" in text
    assert "The War of Drowned Light is named victor of" not in text


def test_routes_sharing_a_prefix_are_stated_once(graph):
    """`1b_006` has fourteen answers reached the identical way. The old
    template printed fourteen near-identical arrow chains in one sentence."""
    answer = answer_question(
        "Which individual was a member of the faction that ultimately won "
        "the War of Drowned Light?",
        graph,
        use_planner=False,
    )
    text = template_sentence(answer, graph)

    assert len(answer.values) == 14
    assert text.count("The Silent Choir") == 1, "the shared hop is stated once"
    # The names are listed once, as the answer - and referred back to, not
    # relisted, in the explanation.
    assert text.count("Ravena Stormwell") == 1
    assert "those 14" in text


def test_a_conflict_sentence_names_the_disputed_hop_and_picks_no_side(graph):
    """`1b_009`. The caveat is useless if a reader cannot tell which of the two
    hops is disputed - and stating the contested hop as flatly as the
    uncontested one is the failure ADR-018 exists to prevent."""
    answer = answer_question(
        "In what way is Halvard Crowhurst connected to the victors of the "
        "Purge of Blackport?",
        graph,
        use_planner=False,
    )
    assert answer.status == EvidenceStatus.CONFLICTING_EVIDENCE
    text = template_sentence(answer, graph)

    assert "the sources disagree" in text
    assert "The disagreement is over whether" in text
    # Both sides named, neither preferred.
    assert "wiki/the_purge_of_blackport.md asserts it" in text
    assert "wiki/the_iron_ring_cartel.md declines to" in text
    for verdict in ("therefore", "so the victor is", "in fact won"):
        assert verdict not in text.lower()


def test_the_sentence_ends_cleanly_and_carries_no_citation_tail(answer, graph):
    """ADR-042 reversed the earlier judgement here, deliberately.

    The old rule was that the evidence panel is not a substitute inside a
    quotable sentence. It is a substitute on a page where the sentence and the
    panel are three centimetres apart, and the tail was the single ugliest
    thing in the answer box."""
    text = template_sentence(answer, graph)
    assert text.rstrip().endswith(".")
    assert "Sources:" not in text


def test_a_profile_is_worded_as_a_record_not_as_candidate_answers(graph):
    """"Who is X?" names no relation, so the endpoints are X's record - not a
    set of answers to choose between. The generic lead called them
    "2 answers: The Silent Choir and Vharenford", which invites a reader to
    pick one; neither is an answer to anything."""
    answer = answer_question("Who is Ravena Stormwell?", graph, use_planner=False)
    assert answer.status == EvidenceStatus.PROFILE

    text = template_sentence(answer, graph)
    assert text.startswith("Ravena Stormwell is a member of The Silent Choir")
    assert "serves at Vharenford" in text
    assert "answers:" not in text
    # Facts about one subject are one statement, not the subject repeated.
    assert text.count("Ravena Stormwell") == 1
    assert "whole recorded profile" in text
    assert "Sources:" not in text
