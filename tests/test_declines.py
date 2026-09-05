"""Every decline must render what the system established, with citations.

WHY THIS FILE EXISTS
--------------------
`src/query/evidence.py` already guarantees a decline is a *named* result. This
file guarantees it is an *inspectable* one, because on screen those are not the
same thing: `no_template_match` in a red pill and a caught exception in a red
pill look identical to a judge, and "technical execution & robustness" is 25%
of the rubric assessed on inputs the team did not script.

Measured on the frozen robustness set before this work: 23 of 55 questions
decline, 18 of those carry `no_template_match` with a one-line reason and
nothing else. Each test below pins one declining status to the partial evidence
it must now show.

The three ADR-018 thinness tests in `tests/test_ui.py` still own the constraint
that none of this is computed in the UI. These tests own the content.
"""

from __future__ import annotations

import json

import pytest

from src.graph.build import build_graph, load_relation_map
from src.ingest.pipeline import ingest
from src.query.catalogue import build_catalogue
from src.query.engine import answer_question
from src.query.evidence import EvidenceStatus
from src.query.resolve import EntityResolver
from src.query.route import build_gazetteer
from src.settings import get_settings
from src.ui.render import page_answer, page_index
from src.ui.view import build_view

# Questions chosen because each reaches one declining status through the
# ordinary engine, with no monkeypatching. Verified by
# `test_each_question_reaches_the_status_it_is_here_to_exercise`, so a routing
# change that silently reclassifies one of them fails loudly rather than
# quietly testing the wrong branch.
Q_TEMPLATE_MISS = (
    "In which gloom-shrouded stronghold is the artifact that Cerys Sablewood "
    "the Ashen has carried since 356 AS kept?"
)
Q_TYPO = "Which relic has Cerys Sablewode the Ashen wielded since 356 AS?"
Q_UNKNOWN = "Which faction ultimately won the war of which Xanthor Nevermore is a member?"
Q_OUTSIDE = "Which faction won the war that Halvard Cindervale was a member of?"
Q_NO_PATH = (
    "In what way is Ederon Fellgard connected to the victors of the "
    "War of Drowned Light?"
)
Q_MISSING_ATTR = (
    "Which faction is recorded as the victor of the conflict "
    "Morwenna Ashgrove fought in?"
)

EXPECTED = {
    Q_TEMPLATE_MISS: EvidenceStatus.NO_TEMPLATE_MATCH,
    Q_TYPO: EvidenceStatus.AMBIGUOUS_ENTITY,
    Q_UNKNOWN: EvidenceStatus.UNRESOLVED_ENTITY,
    Q_OUTSIDE: EvidenceStatus.OUTSIDE_STRUCTURED_COVERAGE,
    Q_NO_PATH: EvidenceStatus.NO_PATH,
    Q_MISSING_ATTR: EvidenceStatus.PATH_MISSING_ATTRIBUTE,
}


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
def evidence_units(corpus_root):
    """Needed for OUTSIDE_STRUCTURED_COVERAGE, which cannot fire without it."""
    return ingest().evidence


@pytest.fixture(scope="module")
def views(graph, evidence_units):
    resolver = EntityResolver(graph)
    gazetteer = build_gazetteer(graph, resolver)
    out = {}
    for question in EXPECTED:
        answer = answer_question(
            question,
            graph,
            resolver=resolver,
            gazetteer=gazetteer,
            evidence_units=evidence_units,
            # Templates only. The cue tier answers some of these, and this file
            # is about what a *decline* renders - so the decline is produced
            # deliberately rather than hunted for.
            use_fallback=False,
        )
        out[question] = build_view(answer, graph)
    return out


def test_each_question_reaches_the_status_it_is_here_to_exercise(views):
    for question, expected in EXPECTED.items():
        assert views[question]["status"] == expected.value, (
            f"{question!r} no longer reaches {expected.value}; the tests below "
            "would be exercising a different branch than they claim"
        )


def test_every_decline_carries_diagnostics(views):
    for question, view in views.items():
        assert view["answerable"] is False
        assert view["diagnostics"] is not None, f"no diagnostics for {question!r}"


def test_an_answered_result_carries_no_diagnostics(graph, evidence_units):
    """Partial evidence is for declines. An answer shows its evidence path instead."""
    answer = answer_question(
        "Whose dominion encompasses the lair of the Gravemaw Wyrm?",
        graph,
        evidence_units=evidence_units,
    )
    assert answer.status == EvidenceStatus.SUFFICIENT
    assert answer.diagnostics is None
    assert build_view(answer, graph)["diagnostics"] is None


# -- NO_TEMPLATE_MATCH: the 18-of-23 case -----------------------------------


def test_template_miss_shows_the_entities_it_did_resolve_with_citations(views):
    view = views[Q_TEMPLATE_MISS]
    diag = view["diagnostics"]

    established = diag["established"]
    assert established, "the question names Cerys Sablewood the Ashen; she is known"
    entity = established[0]
    assert entity["entity"]["name"] == "Cerys Sablewood the Ashen"
    assert entity["entity"]["page"] == "wiki/cerys_sablewood_the_ashen.md"
    assert entity["relations_present"]

    # Every displayed fact is a citation, exactly as a SUFFICIENT hop is.
    assert entity["facts"]
    for fact in entity["facts"]:
        assert fact["document"]
        assert fact["field_name"]
        assert fact["row"] is not None
        assert fact["raw"]
        assert fact["tier"]

    html = page_answer(view)
    assert "What the system did establish" in html
    assert "Cerys Sablewood the Ashen" in html
    assert "wiki/cerys_sablewood_the_ashen.md" in html
    # The fact this very question was reaching for is on the page, which is what
    # makes the decline legible: the system HAS the first hop, it could not
    # route the wording.
    assert "The Cinder-Wrought Aegis" in html


def test_template_miss_shows_the_declared_relation_vocabulary(views):
    view = views[Q_TEMPLATE_MISS]
    vocabulary = view["diagnostics"]["relation_vocabulary"]
    assert len(vocabulary) == 15
    assert "member_of" in vocabulary and "victor_of" in vocabulary

    html = page_answer(view)
    assert "The relations this system knows" in html
    assert "config/relations.yaml" in html
    # The point of the block: a declared boundary, not an accidental one.
    assert "declared, not" in html


def test_a_question_naming_nothing_known_says_so_plainly(graph, evidence_units):
    view = build_view(
        answer_question(
            "What colour is the sky in the Ashen Era?",
            graph,
            evidence_units=evidence_units,
            use_fallback=False,
        ),
        graph,
    )
    assert view["diagnostics"]["established"] == []
    html = page_answer(view)
    assert "Nothing in this question matched a known entity" in html
    assert 'href="/#entities"' in html


# -- UNRESOLVED / AMBIGUOUS: a name that did not become a node ---------------


def test_typo_offers_a_suggestion_that_is_never_auto_applied(views):
    view = views[Q_TYPO]
    diag = view["diagnostics"]

    assert diag["span"] == "Cerys Sablewode the Ashen"
    assert diag["suggestions"], "a 0.960 near-miss must be reported (ADR-021)"
    suggestion = diag["suggestions"][0]
    assert suggestion["name"] == "Cerys Sablewood the Ashen"
    assert suggestion["similarity"] >= 0.90

    # Reported, not resolved: the answer itself is still a decline with no value.
    assert view["values"] == []
    assert view["answerable"] is False

    html = page_answer(view)
    assert "Did you mean?" in html
    assert "not a correction" in html
    assert "nothing has been applied" in html
    # Offered as a link the user chooses, carrying the corrected question.
    assert "Cerys%20Sablewood%20the%20Ashen" in html


def test_a_suggestion_below_the_reporting_floor_is_not_offered(views):
    """ADR-021's floor is 0.90. Nothing under it may be presented as a suggestion."""
    for view in views.values():
        for suggestion in view["diagnostics"]["suggestions"]:
            assert suggestion["similarity"] >= 0.90


def test_ambiguous_candidates_carry_type_and_source_document(views):
    view = views[Q_TYPO]
    for candidate in view["diagnostics"]["candidates"]:
        assert candidate["key"]
        assert candidate["name"]
        assert candidate["similarity"] is not None
        # `page` is the source document. It may legitimately be None for a node
        # that exists only as a link target - but then the key identifies it.
        assert candidate["page"] is not None or candidate["key"]


def test_an_unknown_name_points_at_the_entity_list(views):
    view = views[Q_UNKNOWN]
    assert view["diagnostics"]["span"] == "Xanthor Nevermore"
    html = page_answer(view)
    assert "The name we could not place" in html
    assert 'href="/#entities"' in html


# -- OUTSIDE_STRUCTURED_COVERAGE: the declared architectural boundary --------


def test_outside_coverage_names_the_collections_and_quotes_them(views):
    """The status that is purely a boundary, so it must be the best cited."""
    view = views[Q_OUTSIDE]
    presence = view["diagnostics"]["presence"]
    assert presence, "Halvard Cindervale appears in the corpus 21 times"

    collections = {p["collection"] for p in presence}
    assert {"codex", "ephemera", "wiki"} <= collections

    for entry in presence:
        assert entry["documents"]
        assert entry["evidence_id"]
        assert entry["locator"]
        assert entry["quote"]
        assert entry["tier"]

    html = page_answer(view)
    assert "Present in the corpus, absent from the graph" in html
    # The claim must name where the limit lives, so a judge can check it.
    assert "src/graph/build.py" in html
    assert "wiki infobox rows only" in html
    assert "codex/the_annals_of_the_ashen_era" in html


def test_outside_coverage_is_unreachable_without_evidence_units(graph):
    """The defect this work fixed, pinned so it cannot come back.

    `answer_question` can only tell OUTSIDE_STRUCTURED_COVERAGE from
    UNRESOLVED_ENTITY by scanning evidence units, and `src/ui/server.py` did
    not pass them - so the demo reported a person documented 21 times across
    three collections as a name the corpus does not contain. `Engine` now loads
    them at startup.
    """
    without = answer_question(Q_OUTSIDE, graph, evidence_units=None, use_fallback=False)
    assert without.status == EvidenceStatus.UNRESOLVED_ENTITY, (
        "if this now passes without evidence units, the distinction moved and "
        "the Engine's ingest at startup may no longer be needed"
    )


def test_the_ui_engine_loads_what_outside_coverage_needs():
    """`Engine.__init__`'s signature is the fix; assert it did not regress."""
    import inspect

    from src.ui.server import Engine

    parameter = inspect.signature(Engine.__init__).parameters["evidence_units"]
    assert parameter.default is None, (
        "None means 'ingest at startup'; a different default would silently "
        "disable OUTSIDE_STRUCTURED_COVERAGE in the demo again"
    )


# -- NO_PATH / PATH_MISSING_ATTRIBUTE: how far the traversal got -------------


def test_no_path_names_both_ends_and_what_it_did_reach(views):
    view = views[Q_NO_PATH]
    diag = view["diagnostics"]

    assert diag["start"]["name"] == "The War of Drowned Light"
    assert diag["goal"]["name"] == "Ederon Fellgard"
    assert diag["hops_completed"] == 2
    assert diag["reached_count"] == 14, (
        "the chain reached the Silent Choir's fourteen members - real results "
        "that are simply not the one asked for"
    )
    assert diag["reached"]

    html = page_answer(view)
    assert "Could not join" in html
    assert "The War of Drowned Light" in html
    assert "Ederon Fellgard" in html
    assert "14 endpoint(s)" in html


def test_path_missing_attribute_shows_the_candidates_the_filter_removed(views):
    """F-022's gap, closed. The eliminated endpoints are the content here."""
    view = views[Q_MISSING_ATTR]
    diag = view["diagnostics"]

    assert diag["start"]["name"] == "Morwenna Ashgrove"
    assert diag["reached_count"] >= 1
    assert diag["asked_relation"] == "member_of"

    html = page_answer(view)
    assert "How far the traversal got" in html
    # The endpoint the type filter discarded is now visible rather than dropped.
    assert diag["reached"][0]["name"] in html


def test_relation_unavailable_shows_the_relations_the_entity_does_have(
    graph, evidence_units
):
    view = build_view(
        answer_question(
            "Which war was won by the organization that included "
            "Gravemaw Wyrm as one of its members?",
            graph,
            evidence_units=evidence_units,
            use_fallback=False,
        ),
        graph,
    )
    assert view["status"] == EvidenceStatus.RELATION_UNAVAILABLE.value
    diag = view["diagnostics"]
    assert diag["start"]["name"] == "Gravemaw Wyrm"
    assert diag["asked_relation"] == "member_of"

    present = diag["established"][0]["relations_present"]
    assert present, "the creature has edges, just not member_of"
    assert "member_of" not in present

    html = page_answer(view)
    assert "How far the traversal got" in html
    assert "Relations recorded for it" in html


# -- the front page: what can be asked, before anything is asked -------------


def test_catalogue_lists_every_entity_and_relation(graph):
    catalogue = build_catalogue(graph, load_relation_map())
    assert catalogue["counts"]["entities"] == len(graph.nodes) == 117
    assert catalogue["counts"]["edges"] == len(graph.edges) == 261
    assert catalogue["counts"]["relations"] == 15
    assert sum(r["edges"] for r in catalogue["relations"]) == len(graph.edges)
    for relation in catalogue["relations"]:
        assert relation["fields"], f"{relation['name']} maps no infobox field"


def test_index_page_offers_autocomplete_and_a_browsable_list(graph):
    catalogue = build_catalogue(graph, load_relation_map())
    html = page_index(catalogue)

    # Native autocomplete, no JavaScript and no dependency.
    assert '<datalist id="entities">' in html
    assert 'list="entities"' in html
    assert html.count("<option ") == 117

    assert "What you can ask about" in html
    assert "The relations it can follow" in html
    # Every entity is a working entry point, not just a name on a list.
    assert html.count('href="/ask?q=Who%20is%20') == 117
    assert "<script" not in html


def test_index_page_still_renders_without_a_catalogue():
    html = page_index()
    assert 'name="q"' in html
    assert "<datalist" not in html


# -- hygiene -----------------------------------------------------------------


def test_diagnostics_are_plain_serialisable_data(views):
    """No engine object may leak into the template layer through diagnostics."""
    for view in views.values():
        json.dumps(view["diagnostics"])


def test_decline_blocks_are_absent_from_an_answered_page(graph, evidence_units):
    view = build_view(
        answer_question(
            "Whose dominion encompasses the lair of the Gravemaw Wyrm?",
            graph,
            evidence_units=evidence_units,
        ),
        graph,
    )
    html = page_answer(view)
    for heading in (
        "What the system did establish",
        "The name we could not place",
        "How far the traversal got",
        "Present in the corpus, absent from the graph",
        "The relations this system knows",
    ):
        assert heading not in html, f"{heading!r} rendered on an answered page"


def test_a_hostile_span_is_escaped_in_a_decline_block(graph, evidence_units):
    view = build_view(
        answer_question(
            'Which faction won the war that <script>alert("x")</script> joined?',
            graph,
            evidence_units=evidence_units,
            use_fallback=False,
        ),
        graph,
    )
    html = page_answer(view)
    assert "<script>alert" not in html
