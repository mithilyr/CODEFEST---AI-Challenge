"""Tests for the demo surface.

Two kinds of test live here, and the distinction matters.

**Architectural tests** assert the UI stays a presentation layer - that
`view.py` and `render.py` never grow retrieval, traversal, entity resolution,
conflict resolution or answer composition. That constraint is the reason this
package is safe to show a judge as "thin", so it is checked mechanically
rather than left to review.

**Surface tests** assert each of the nine things the demo has to expose is
actually present for the four questions the demo is built around - `1b_013`,
`1b_007`, `1b_006` and `1b_009` - plus the two shapes a live demo is most
likely to hit by accident: a question no template matches, and a misspelled
entity.

`1b_009` gets the most detailed test in the file. It is the question whose
whole point is that the membership hop is supported while the victor hop is
disputed between two same-tier sources, and a page that blurred those two
together would look fine and be wrong.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

import pytest

from src.graph.build import build_graph
from src.query.engine import Answer, answer_question
from src.query.evidence import EvidenceStatus
from src.ui import render, view
from src.ui.render import page_answer, page_error, page_index
from src.ui.view import build_view
from src.settings import get_settings

Q_013 = "Whose dominion encompasses the lair of the Gravemaw Wyrm?"
Q_007 = "Which accord was ultimately won by the faction of which Ederon Fellgard is a member?"
Q_006 = "Which individual was a member of the faction that ultimately won the War of Drowned Light?"
Q_009 = "In what way is Halvard Crowhurst connected to the victors of the Purge of Blackport?"


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
def views(graph):
    """One view per demo question, built once - the graph is the slow part."""
    return {
        q: build_view(answer_question(q, graph), graph)
        for q in (Q_013, Q_007, Q_006, Q_009)
    }


# -- architectural: the UI must stay a presentation layer --------------------

#: Every entry point that reasons. If one of these names appears in the view
#: or render source, presentation has started doing the engine's job.
REASONING_NAMES = [
    "walk_relations",
    "find_paths",
    "neighbours",
    "out_edges",
    "in_edges",
    # NOT "route": the view legitimately holds route *data* (`_route`,
    # `view["routes"]`) and render.py has a `.route` CSS class. The thing that
    # actually matters - that neither module can reach `src.query.route.route`
    # - is asserted precisely by the import allowlist below instead.
    "check_conflict",
    "find_denial",
    "filter_endpoints",
    "classify_traversal",
    "check_abstention",
    "mentioned_in_corpus",
    "EntityResolver",
    "canonical_key",
    "parse_cell",
    "infobox_rows",
    "read_text",
]


@pytest.mark.parametrize("module", [view, render])
def test_view_and_render_import_no_reasoning_code(module):
    """The presentation modules must not call the reasoning layer.

    A source-level check on purpose: it fails when someone *writes* the call,
    not only when a test happens to exercise it.

    Matched on a word boundary, not as a bare substring. The first version of
    this test used `"route(" in code` and failed on the view's own private
    `_route(...)` helper - a guard that cries wolf on the code it is meant to
    protect gets deleted, so it is anchored properly instead.
    """
    import re

    source = Path(module.__file__).read_text(encoding="utf-8")
    # Strip the docstrings, which name these functions to explain why they are
    # absent - the prohibition is on calling them, not on discussing them.
    body = source.split('"""')
    code = "".join(body[i] for i in range(0, len(body), 2))
    offenders = [
        name
        for name in REASONING_NAMES
        if re.search(rf"\b{re.escape(name)}", code)
    ]
    assert not offenders, f"{module.__name__} reaches into the reasoning layer: {offenders}"


def test_view_imports_only_the_response_contract():
    """The view may see the contract and the node table. Nothing else.

    This is the precise form of the constraint the `route` substring check was
    reaching for: `src.query.route`, `src.query.conflict`, `src.query.resolve`
    and `src.graph.traverse` are the modules that decide things, and the view
    cannot import any of them. `src.query.evidence` is allowed for the
    `EvidenceStatus` enum alone - the statuses the glossary is keyed on.
    """
    import ast

    tree = ast.parse(Path(view.__file__).read_text(encoding="utf-8"))
    project_imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("src.")
    }
    assert project_imports == {
        "src.graph.schema",
        "src.query.engine",
        "src.query.evidence",
    }, f"unexpected reach into the project: {sorted(project_imports)}"

    evidence_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "src.query.evidence"
        for alias in node.names
    }
    assert evidence_names == {"EvidenceStatus"}, (
        "only the status enum may come from the evidence module, not its functions"
    )


def test_render_does_not_import_the_engine_at_all():
    """`render.py` sees plain dicts only, so it cannot call back into the query layer."""
    source = Path(render.__file__).read_text(encoding="utf-8")
    assert "from src.query" not in source
    assert "from src.graph" not in source
    assert "import src." not in source


def test_view_touches_the_graph_only_for_display_names():
    """`_display` is the whole of the UI's graph access."""
    source = Path(view.__file__).read_text(encoding="utf-8")
    code = "".join(source.split('"""')[i] for i in range(0, len(source.split('"""')), 2))
    assert code.count("graph.nodes") == 1, (
        "the view should read graph.nodes exactly once, inside _display"
    )


# -- the nine demo surfaces --------------------------------------------------


def test_every_required_surface_is_present_for_a_conflicted_answer(views):
    """All nine surfaces on one page - `1b_009` is the only one that has all of them."""
    html = page_answer(views[Q_009])
    for heading in (
        "Ask",                                  # 1. question input
        "Answer",                               # 2. final answer
        "Strategy used",                        # 3. strategy
        "Evidence path",                        # 4. every hop
        "source passage",                       # 5. supporting passages
        "Source documents and tiers",           # 6. source tier
        "Conflict, and how it was handled",     # 7. conflicts + handling
        "Evidence sufficiency",                 # 8. sufficiency
    ):
        assert heading in html, f"missing demo surface: {heading}"


def test_fallback_reason_is_shown_verbatim_when_there_is_one(graph):
    """Surface 9. The engine's note is printed, not reworded."""
    answer = answer_question("What did the Gravemaw Wyrm eat for breakfast?", graph)
    v = build_view(answer, graph)
    assert v["status"] == EvidenceStatus.NO_TEMPLATE_MATCH.value
    assert v["answerable"] is False
    assert v["note"]
    html = page_answer(v)
    assert "Fallback reason" in html
    # Escaped, not reworded. The note contains an apostrophe
    # ("template's"), so the literal string is not in the markup - which is
    # the escaping working, not the note being edited.
    assert escape(v["note"], quote=True) in html


# -- 1b_013: the vertical slice ---------------------------------------------


def test_1b_013_renders_answer_strategy_and_both_hops(views):
    v = views[Q_013]
    assert v["status"] == "sufficient"
    assert v["values"] == ["The Bleeding Crown"]
    assert v["template"] == "lair_dominion"
    assert v["chain"] == ["lair_in", "ruled_by"]
    assert len(v["routes"]) == 1
    hops = v["routes"][0]["hops"]
    assert [h["relation"] for h in hops] == ["lair_in", "ruled_by"]
    # Every hop carries the row it was read from, which is the whole claim.
    for hop in hops:
        assert hop["document"].startswith("wiki/")
        assert hop["field_name"]
        assert hop["raw"]
        assert hop["tier"] == 2
    assert [d["document"] for d in v["documents"]] == [
        "wiki/gravemaw_wyrm.md",
        "wiki/marrowwell_abbey.md",
    ]
    html = page_answer(v)
    assert "The Bleeding Crown" in html
    assert "wiki/gravemaw_wyrm.md" in html


# -- 1b_007: multi-value relationship + type filtering -----------------------


def test_1b_007_shows_the_single_surviving_value_with_its_evidence(views):
    v = views[Q_007]
    assert v["values"] == ["The Leaden Accord"]
    assert v["chain"] == ["member_of", "victor_of"]
    # Two routes survive the type filter and both land on the same endpoint -
    # the corroboration ADR-016 keeps deliberately, so both are drawn.
    assert len(v["routes"]) == 2
    assert {r["endpoint_name"] for r in v["routes"]} == {"The Leaden Accord"}
    html = page_answer(v)
    assert "The Leaden Accord" in html


def test_1b_007_multi_valued_cell_is_visible_in_the_evidence(views):
    """The multi-valued relationship shows up where it actually lives: the cell.

    Written after the first version of this test asserted the opposite and
    failed. The reasoning was that `Answer` drops the endpoints the type
    filter eliminated, so the filtering story could not be shown - true of the
    *endpoints*, but it missed that one hop's `raw` cell is literally
    `[[The Winter Reckoning]]; [[The Leaden Accord]]`. The multi-valued
    relationship ADR-010 parses is therefore on the page already, in the
    source passage, next to an answer that names only one of the two.

    What is still not shown is the *filter decision* - which word narrowed it,
    and what else was considered and dropped. That gap is F-022.
    """
    victor_cells = [
        h["raw"]
        for r in views[Q_007]["routes"]
        for h in r["hops"]
        if h["relation"] == "victor_of"
    ]
    multi = [c for c in victor_cells if ";" in c]
    assert multi, "expected at least one multi-valued victor cell"
    assert "The Winter Reckoning" in multi[0] and "The Leaden Accord" in multi[0]

    html = page_answer(views[Q_007])
    assert "The Winter Reckoning" in html, "the discarded sibling value is visible"
    # ...but it is not offered as an answer.
    assert views[Q_007]["values"] == ["The Leaden Accord"]


# -- 1b_006: many values, many routes ----------------------------------------


def test_1b_006_renders_all_fourteen_values_and_every_route(views):
    v = views[Q_006]
    assert len(v["values"]) == 14
    assert len(v["routes"]) == 14
    assert len(v["documents"]) == 10
    html = page_answer(v)
    for name in v["values"]:
        assert name in html, f"{name} missing from the page"
    # Each route still shows both of its hops - a 14-answer question must not
    # quietly collapse into a bare list with the evidence dropped.
    assert all(len(r["hops"]) == 2 for r in v["routes"])
    assert html.count("parsed by:") == 28


# -- 1b_009: supported membership, disputed victory, same tier ---------------


def test_1b_009_marks_the_victor_hop_disputed_and_leaves_membership_alone(views):
    """The heart of the demo: one hop disputed, one not, and the UI decides neither."""
    v = views[Q_009]
    assert v["status"] == "conflicting_evidence"

    hops = v["routes"][0]["hops"]
    disputed = [h for h in hops if h["disputed"]]
    supported = [h for h in hops if not h["disputed"]]

    assert len(disputed) == 1, "exactly one hop is in dispute"
    assert disputed[0]["relation"] == "victor_of"
    assert len(supported) == 1
    assert supported[0]["relation"] == "member_of", (
        "the membership hop is uncontested and must not be marked disputed"
    )


def test_1b_009_shows_both_sides_at_the_same_tier_without_resolving(views):
    v = views[Q_009]
    conflict = v["conflict"]
    assert conflict["status"] == "unresolved_same_tier"
    assert conflict["must_surface"] is True

    assert conflict["asserted_by"], "the asserting source must be shown"
    assert conflict["denied_by"] is not None, "the disputing source must be shown"

    # The point of the question: authority ranking cannot settle this.
    assert conflict["denied_by"]["tier"] == conflict["asserted_by"][0]["tier"] == 2

    html = page_answer(v)
    assert "wiki/the_purge_of_blackport.md" in html   # asserts
    assert "wiki/the_iron_ring_cartel.md" in html     # disputes
    assert "same authority tier" in html
    assert "unresolved_same_tier" in html
    # The page must not announce a winner.
    for verdict in ("we conclude", "the correct answer is", "therefore the victor"):
        assert verdict not in html.lower()


def test_no_hop_is_marked_disputed_when_there_is_no_conflict(views):
    """The dispute marker is driven by the engine's report, never invented."""
    for question in (Q_013, Q_007, Q_006):
        v = views[question]
        assert v["conflict"] is None
        assert not any(h["disputed"] for r in v["routes"] for h in r["hops"])


def test_disputed_marking_ignores_a_report_the_engine_did_not_flag(graph):
    """`must_surface` False means nothing is marked, even with a report attached."""
    answer = answer_question(Q_009, graph)
    assert answer.conflict is not None and answer.conflict.must_surface

    class _NotSurfaced:
        must_surface = False
        status = "uncontested"
        subject_key = answer.conflict.subject_key
        relation = answer.conflict.relation
        object_key = answer.conflict.object_key
        asserting_edges = answer.conflict.asserting_edges
        denial = None

    quiet = Answer(
        question=answer.question, status=answer.status, values=answer.values,
        template=answer.template, chain=answer.chain, start_key=answer.start_key,
        goal_key=answer.goal_key, paths=answer.paths, documents=answer.documents,
        conflict=_NotSurfaced(),
    )
    v = build_view(quiet, graph)
    assert not any(h["disputed"] for r in v["routes"] for h in r["hops"])


# -- resolution failures the demo can hit live -------------------------------


def test_ambiguous_entity_lists_candidates_without_choosing(graph):
    """ADR-011 in the UI: near-matches are shown, never selected."""
    v = build_view(
        answer_question("Whose dominion encompasses the lair of the Grarmaw Wyrmm?", graph),
        graph,
    )
    assert v["status"] == EvidenceStatus.AMBIGUOUS_ENTITY.value
    assert v["answerable"] is False
    assert v["values"] == []
    html = page_answer(v)
    assert "exact-match only" in html


# -- rendering hygiene -------------------------------------------------------


def test_every_dynamic_value_is_escaped(graph):
    """A question is user input and reaches the page; it must not reach it as markup."""
    hostile = 'Whose <script>alert("x")</script> dominion & lair?'
    v = build_view(answer_question(hostile, graph), graph)
    html = page_answer(v)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_index_and_error_pages_render(graph):
    index = page_index()
    assert "Ashen Era" in index
    assert 'name="q"' in index
    # Every demo question is one click away, so the live demo never mistypes one.
    assert index.count('href="/ask?q=') == len(render.DEMO_QUESTIONS)
    assert "1b_009" in index

    error = page_error("boom")
    assert "boom" in error


def test_view_returns_plain_data_only(views):
    """No engine object leaks into the template layer."""
    import json

    for v in views.values():
        json.dumps(v)  # raises TypeError if anything non-serialisable slipped in
