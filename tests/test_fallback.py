"""Regression tests for the cue-based fallback tier (`src/query/fallback.py`).

Every test here pins a behaviour that ADR-019's measurement paid for. The
numbers quoted in the docstrings come from `comparison/REPORT.md` and are
reproducible with `python -m comparison.harness` and
`python -m comparison.ablations`.

The tests that matter most are the ones asserting the fallback *declines*.
Its measured precision is 40% against template routing's 91%, and its dominant
failure is a confident wrong answer rather than a miss - so the guarantee worth
protecting is not "it answers more" but "it does not answer when it has no
basis to".
"""

from __future__ import annotations

import pytest

from src.graph.build import build_graph, load_relation_map
from src.graph.schema import Edge, Graph, Node
from src.graph.traverse import Path
from src.query.engine import answer_question
from src.query.evidence import EvidenceStatus
from src.query.fallback import (
    cued_relations,
    find_mentions,
    normalise_cue_word,
    relation_cues,
    route_by_cues,
    select_candidates,
)
from src.settings import get_settings


@pytest.fixture(scope="module")
def corpus_root():
    settings = get_settings()
    if not settings.corpus_path.is_dir():
        pytest.skip(f"Corpus not present at {settings.corpus_path}; see README.md")
    return settings.corpus_path


@pytest.fixture(scope="module")
def graph(corpus_root):
    return build_graph()


@pytest.fixture(scope="module")
def relations():
    return load_relation_map()


@pytest.fixture(scope="module")
def cues(relations):
    return relation_cues(relations)


# --------------------------------------------------------------------------
# The tier boundary: templates first, fallback never pre-empts them.
# --------------------------------------------------------------------------


def test_dev_questions_still_route_through_a_template(graph):
    """No regression. ADR-017's 7/7 must not become 7 fallback answers.

    The fallback runs only on a RouteMiss, so a question a template covers
    must still come back as SUFFICIENT, never FALLBACK_SUFFICIENT.
    """
    answer = answer_question(
        "Which accord was ultimately won by the faction of which "
        "Ederon Fellgard is a member?",
        graph,
    )
    assert answer.status == EvidenceStatus.SUFFICIENT
    assert not answer.status.is_fallback
    assert "The Leaden Accord" in answer.values


def test_fallback_answers_a_novel_question_no_template_covers(graph):
    """The measured win. Templates match 1 of 21 novel questions; this is one
    of the 20 they miss and the fallback reaches."""
    answer = answer_question(
        "Which power rules the settlement where The Cinder-Wrought Aegis is housed?",
        graph,
    )
    assert answer.status == EvidenceStatus.FALLBACK_SUFFICIENT
    assert "House Morvain" in answer.values
    assert answer.template == "cue_fallback"
    assert len(answer.documents) >= 2, "a join must cite more than one document"


# --------------------------------------------------------------------------
# Declining. The guarantee worth more than the coverage.
# --------------------------------------------------------------------------


def test_fallback_declines_when_no_entity_resolves(graph):
    """A question naming nothing the graph knows must stay a template miss,
    not become a fallback answer about whatever happened to be nearby."""
    answer = answer_question("What color is the sky in the Ashen Era?", graph)
    assert answer.status == EvidenceStatus.NO_TEMPLATE_MATCH
    assert answer.values == ()


def test_fallback_declines_when_no_relation_is_cued(graph):
    """The entity resolves but the question names no relation the corpus
    records. Returning a profile of everything known about the wyrm would be
    answering a question nobody asked."""
    answer = answer_question("What did the Gravemaw Wyrm eat for breakfast?", graph)
    assert answer.status == EvidenceStatus.NO_TEMPLATE_MATCH
    assert answer.values == ()


def test_declining_preserves_the_template_stages_own_reason(graph):
    """The fallback must not overwrite a more specific diagnosis with a
    vaguer one - `evidence.py`'s named-status taxonomy exists precisely so a
    non-answer says which thing went wrong."""
    answer = answer_question("Which relic has Cerys Sablewode the Ashen wielded?", graph)
    assert not answer.status.is_fallback
    assert answer.note


# --------------------------------------------------------------------------
# Guard 2 - coverage over length. The load-bearing rule.
# --------------------------------------------------------------------------


def _edge(source: str, relation: str, target: str) -> Edge:
    return Edge(
        source=source,
        relation=relation,
        target=target,
        document=f"wiki/{source}.md",
        field_name="Test",
        row=0,
        raw=f"{source} {relation} {target}",
        template="link",
        tier=2,
    )


def test_coverage_beats_length_when_a_longer_path_ties_on_relations():
    """ADR-019's measurement: removing this rule collapses correctness 12 -> 2.

    A three-hop path that re-uses `member_of` covers the same two relations as
    the correct two-hop chain. Preferring the longest cued chain swaps in a
    person the corpus never meant as the answer; preferring coverage then
    brevity keeps the right one.
    """
    short = Path("a", (_edge("a", "member_of", "f"), _edge("f", "victor_of", "w")))
    long = Path(
        "a",
        (
            _edge("a", "member_of", "f"),
            _edge("f", "victor_of", "w"),
            _edge("w", "member_of", "bystander"),
        ),
    )
    chosen = select_candidates([short, long])
    assert chosen == [short]
    assert long not in chosen


def test_a_path_covering_more_relations_beats_a_shorter_one():
    """The other half of the same rule: coverage is scored BEFORE length, so a
    one-hop path does not win merely by being shortest when the question named
    two relations."""
    one_hop = Path("a", (_edge("a", "wields", "relic"),))
    two_hop = Path(
        "a", (_edge("a", "wields", "relic"), _edge("relic", "housed_in", "place"))
    )
    assert select_candidates([one_hop, two_hop]) == [two_hop]


# --------------------------------------------------------------------------
# The stemming fix - a defect in the sister implementation, not copied.
# --------------------------------------------------------------------------


def test_base_verb_forms_cue_the_same_relation_as_inflected_ones(cues):
    """Measured defect in the sister router: it folds `ruled`/`rules`/`ruling`
    to `rul` but leaves the base form `rule` alone, so "whose rule?" silently
    fails to cue `ruled_by` while "who rules?" succeeds."""
    assert normalise_cue_word("rule") == normalise_cue_word("ruled")
    assert normalise_cue_word("house") == normalise_cue_word("housed")

    asked_as_noun = cued_relations(cues, "The lair falls under whose rule?")
    asked_as_verb = cued_relations(cues, "Which power rules the lair?")
    assert "ruled_by" in asked_as_noun
    assert "ruled_by" in asked_as_verb


def test_irregular_verb_win_cues_victor_of(cues):
    """relations.yaml's victor_of vocabulary is "victor" and "won"; neither
    shares a strippable suffix with "win", and 1b_022 asks "...ultimately
    win?". Worth 3 questions when ablated."""
    assert "victor_of" in cued_relations(cues, "Which war did they ultimately win?")


# --------------------------------------------------------------------------
# Ambiguity is reported, never resolved by picking.
# --------------------------------------------------------------------------


def test_multiple_surviving_endpoints_report_ambiguity(graph, relations):
    """`1b_006` genuinely has fourteen valid answers (F-015). A router that
    silently returned one of them would be wrong about the corpus, so the
    ambiguous status has to be reachable and has to carry every candidate."""
    result = route_by_cues(
        graph,
        "Which individual was a member of the faction that won the War of Drowned Light?",
        relations,
    )
    if result.ambiguous:
        assert len({p.end for p in result.paths}) > 1
    assert EvidenceStatus.FALLBACK_AMBIGUOUS.is_answerable


# --------------------------------------------------------------------------
# Provenance: a reader must be able to tell the tiers apart.
# --------------------------------------------------------------------------


def test_fallback_statuses_are_answerable_but_flagged_as_fallback():
    """The two tiers measure 40% and 91% precision. Collapsing them into one
    status would let the weaker one borrow the stronger one's credibility."""
    for status in (
        EvidenceStatus.FALLBACK_SUFFICIENT,
        EvidenceStatus.FALLBACK_AMBIGUOUS,
    ):
        assert status.is_answerable
        assert status.is_fallback
    assert not EvidenceStatus.SUFFICIENT.is_fallback


def test_fallback_answer_carries_its_evidence_and_says_it_is_lower_precision(graph):
    answer = answer_question(
        "Which power rules the settlement where The Cinder-Wrought Aegis is housed?",
        graph,
    )
    assert answer.paths, "an answer without its evidence cannot be shown to a judge"
    assert "lower precision" in (answer.note or "")
    for path in answer.paths:
        for edge in path.edges:
            assert edge.document, "every hop must name the document it came from"


def test_exact_match_only_no_fuzzy_resolution_in_the_fallback(graph):
    """ADR-011 applies to this tier too: a near-miss spelling must resolve to
    nothing rather than be guessed at, even though `caedmon_fellgard` and
    `ederon_fellgard` are 0.839 similar."""
    assert find_mentions(graph, "Who is Ederon Fellgar?") == []
    assert find_mentions(graph, "Who is Ederon Fellgard?")[0].key == "ederon_fellgard"
