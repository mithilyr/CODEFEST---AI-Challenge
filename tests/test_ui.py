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

from src.query.engine import Answer, answer_question
from src.query.evidence import EvidenceStatus
from src.ui import render, view
from src.ui.render import page_answer, page_error, page_index
from src.ui.view import build_view

Q_013 = "Whose dominion encompasses the lair of the Gravemaw Wyrm?"
Q_007 = "Which accord was ultimately won by the faction of which Ederon Fellgard is a member?"
Q_006 = "Which individual was a member of the faction that ultimately won the War of Drowned Light?"
Q_009 = "In what way is Halvard Crowhurst connected to the victors of the Purge of Blackport?"


@pytest.fixture(scope="module")
def views(graph):
    """One view per demo question, built once - the graph is the slow part."""
    return {
        q: build_view(answer_question(q, graph), graph)
        for q in (Q_013, Q_007, Q_006, Q_009)
    }


@pytest.fixture(scope="module")
def corroborated_view(graph, corpus_root):
    """1b_013's view, built with the attestation index attached (ADR-027)."""
    from src.graph.corroborate import build_index
    from src.ingest.pipeline import ingest

    index = build_index(graph, ingest().evidence)
    return build_view(answer_question(Q_013, graph), graph, index)


def test_a_hop_carries_no_attestations_when_none_are_supplied(views):
    """The index is optional: every existing call site passes nothing, and the
    page must render exactly as before rather than raising."""
    for view in views.values():
        for route in view["routes"]:
            for hop in route["hops"]:
                assert hop["attestations"] == []


def test_the_answer_page_shows_cross_collection_attestation(corroborated_view):
    """The deliverable: a wiki-derived answer visibly spanning other collections."""
    html = page_answer(corroborated_view)
    assert "also attested in" in html

    attested = [
        hop
        for route in corroborated_view["routes"]
        for hop in route["hops"]
        if hop["attestations"]
    ]
    assert attested, "1b_013's hops should be attested in the codex"
    for hop in attested:
        for attestation in hop["attestations"]:
            assert attestation["collection"] != "wiki"
            assert attestation["document"] in html
            assert attestation["locator"] in html


def test_attestation_is_worded_as_attestation_not_as_support(corroborated_view):
    """F-014 in a new place: a passage naming both ends is not a second
    assertion of the relation, and the page must not imply that it is."""
    html = page_answer(corroborated_view).lower()
    assert "not a second" in html
    for forbidden in ("confirms", "proves", "corroborates the claim"):
        assert forbidden not in html


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
        # 5. supporting passages. Asserted as the markup that carries them, not
        # as the words "source passage": a single-route answer now puts its
        # chain in that header instead (ADR-039), and the passages are still
        # there either way. A test that checks a label is testing the label.
        'class="passage"',
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
    """A question is user input and reaches the page; it must not reach it as markup.

    This used to assert `"<script>" not in html`, which stopped being a usable
    check when the page grew its own inline busy-state script (ADR-040). The
    property was never "the page contains no script" - it is "nothing a user
    typed becomes markup" - so it is now asserted directly: the hostile input
    appears escaped, appears nowhere unescaped, and every script tag on the
    page is the one the renderer wrote.
    """
    import re as _re

    hostile = 'Whose <script>alert("x")</script> dominion & lair?'
    v = build_view(answer_question(hostile, graph), graph)
    html = page_answer(v)

    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in html
    assert 'alert("x")' not in html, "user input reached the page as live markup"

    scripts = _re.findall(r"<script[^>]*>(.*?)</script>", html, _re.S)
    assert len(scripts) == 1, f"expected only the busy-state script, got {len(scripts)}"
    assert "askform" in scripts[0]


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


# --------------------------------------------------------------------------
# The model-routed banner
#
# A planner-tier answer used to be structurally indistinguishable from a
# deterministic one - same layout, a different word in the status pill, and the
# engine's note in the same grey box every fallback reason uses. That
# understates the tier (it exists because ADR-019 measured the deterministic
# ones missing 35 of 49 realistic questions) and understates its risk (F-025:
# a well-formed plan, relevant to nothing, that passed validation).
# --------------------------------------------------------------------------


def _planned_answer(graph) -> Answer:
    """An Answer as `engine._planned_answer` builds one, without calling a model.

    Constructed rather than obtained live on purpose: the planner is off by
    default so no test spends daily quota or depends on a provider being
    reachable (F-025), and what is under test here is rendering, not routing.
    """
    from src.graph.traverse import walk_relations

    paths = walk_relations(graph, "Gravemaw Wyrm", ["lair_in", "ruled_by"])
    assert paths, "fixture question must still traverse"
    return Answer(
        question="Tell me where the Gravemaw Wyrm sleeps, and who holds it.",
        status=EvidenceStatus.PLANNED_SUFFICIENT,
        values=("The Bleeding Crown",),
        template="llm_plan",
        chain=("lair_in", "ruled_by"),
        start_key="gravemaw_wyrm",
        paths=tuple(paths),
        documents=tuple(dict.fromkeys(d for p in paths for d in p.documents)),
        note=(
            "No deterministic tier matched. A model proposed the chain "
            "lair_in -> ruled_by from Gravemaw Wyrm (model: test/model-x); "
            "every name in it was checked against the graph before traversal, "
            "and the evidence below is the graph's, not the model's."
        ),
    )


def test_view_marks_an_llm_planned_answer_as_model_routed(graph):
    """The tier name is the engine's word; the view turns it into a flag."""
    v = build_view(_planned_answer(graph), graph)
    assert v["routed_by_model"] is True
    assert v["template"] == "llm_plan"


def test_deterministic_answers_are_not_marked_model_routed(views):
    """The flag must not fire on the tiers that never call a model."""
    for question, v in views.items():
        assert v["routed_by_model"] is False, question


def test_banner_appears_only_for_a_model_routed_answer(graph, views):
    planned = page_answer(build_view(_planned_answer(graph), graph))
    assert "ROUTED BY A LANGUAGE MODEL" in planned

    for question, v in views.items():
        assert "ROUTED BY A LANGUAGE MODEL" not in page_answer(v), question


def test_banner_states_what_the_model_did_and_did_not_do(graph):
    """The distinction the whole architecture rests on, said in the UI.

    A reader must not be able to come away thinking the model wrote the answer.
    """
    html = page_answer(build_view(_planned_answer(graph), graph))
    assert "chose <em>where to look</em>" in html
    assert "did not write the answer" in html
    assert "checked against the graph before" in html


def test_banner_shows_the_plan_the_model_proposed(graph):
    """Naming the chain is what makes the claim checkable rather than a badge."""
    html = page_answer(build_view(_planned_answer(graph), graph))
    assert "Gravemaw Wyrm" in html
    assert "lair_in" in html and "ruled_by" in html


def test_banner_precedes_the_answer_value(graph):
    """Provenance before the value, so a reader who takes only the answer
    has already been told a model chose the route to it."""
    html = page_answer(build_view(_planned_answer(graph), graph))
    assert html.index("ROUTED BY A LANGUAGE MODEL") < html.index("The Bleeding Crown")


def test_the_engine_note_is_not_printed_twice(graph):
    """It moved into the banner; leaving it below would repeat the sentence."""
    html = page_answer(build_view(_planned_answer(graph), graph))
    assert html.count("A model proposed the chain") == 1
    assert "Fallback reason" not in html


def test_a_fallback_answer_still_shows_its_reason_below(graph):
    """Removing the duplicate must not remove the non-planner case.

    The cue-fallback tier writes its own note and has no banner, so that note
    is the only place its reason appears.
    """
    v = build_view(
        answer_question(
            "Which house rules the stronghold where the relic borne by "
            "Cerys Sablewood the Ashen is kept?",
            graph,
        ),
        graph,
    )
    assert v["routed_by_model"] is False
    assert v["note"]
    assert "Fallback reason" in page_answer(v)


def test_banner_escapes_a_hostile_model_note(graph):
    """The note is model-influenced text reaching the page - escape it."""
    answer = _planned_answer(graph)
    hostile = Answer(**{**answer.__dict__, "note": "<script>alert(1)</script>"})
    html = page_answer(build_view(hostile, graph))
    assert "<script>alert(1)</script>" not in html
    assert escape("<script>alert(1)</script>") in html


# --------------------------------------------------------------------------
# Status colouring (F-032)
#
# `_status_class` was a three-entry lookup defaulting to "bad", which painted
# five *answerable* statuses in the same red as a failure - including
# `fallback_sufficient`, which is how the cue tier returns its 17 correct
# answers on the frozen set.
# --------------------------------------------------------------------------


def test_no_answerable_status_is_coloured_as_a_failure():
    """The defect, stated as the invariant that would have caught it."""
    mis = [
        s.value
        for s in EvidenceStatus
        if s.is_answerable and render._status_class(s.value, True) == "bad"
    ]
    assert mis == [], f"answerable but painted as failure: {mis}"


def test_only_an_unqualified_answer_is_green():
    """A cue-routed or model-routed answer is real but carries a caveat.

    Greening it would let a 40%-precision tier borrow the colour of a 91% one,
    which is the same argument that keeps their statuses distinct.
    """
    assert render._status_class("sufficient", True) == "ok"
    for qualified in (
        "fallback_sufficient",
        "fallback_ambiguous",
        "planned_sufficient",
        "planned_ambiguous",
        "profile",
    ):
        assert render._status_class(qualified, True) == "warn", qualified


def test_a_chosen_decline_is_not_coloured_as_a_failure():
    """ADR-026: a decline is a result. Abstaining on purpose is not failing."""
    assert render._status_class("abstention", False) == "warn"


def test_routing_failures_stay_red():
    """The change must not have quietly turned every decline amber."""
    for miss in ("no_template_match", "unresolved_entity", "no_path"):
        assert render._status_class(miss, False) == "bad", miss


def test_colouring_cannot_go_stale_when_a_status_is_added():
    """A rule over `answerable`, not a table that must be remembered.

    The old table had to be edited whenever the enum grew, and nothing failed
    if it was not - which is precisely how five statuses ended up red.
    """
    assert render._status_class("some_future_answerable_status", True) == "warn"
    assert render._status_class("some_future_decline", False) == "bad"


# --------------------------------------------------------------------------
# Corpus reload (ADR-036)
# --------------------------------------------------------------------------


def test_reload_page_shows_the_delta_not_just_success():
    """"It reloaded" is a claim; "7 -> 8 entities" is evidence.

    The page exists because a running server holds the graph it built at
    startup, so a document added to the corpus is invisible until something
    rebuilds. Reporting success would tell an operator nothing about whether
    the file was actually read.
    """
    from src.ui.render import page_reload

    html = page_reload(
        {
            "elapsed_seconds": 6.3,
            "before": {"entities": 118, "edges": 265, "units": 30553},
            "after": {"entities": 119, "edges": 268, "units": 30571},
            "unmapped_fields": {},
        }
    )

    assert "119" in html and "118" in html, "both sides of the delta must show"
    assert "+1" in html, "the change itself must be legible"
    assert "6.3s" in html


def test_reload_page_says_so_when_nothing_changed():
    """A no-op reload must not read as though it found something."""
    from src.ui.render import page_reload

    counts = {"entities": 118, "edges": 265, "units": 30553}
    html = page_reload(
        {"elapsed_seconds": 6.1, "before": counts, "after": dict(counts),
         "unmapped_fields": {}}
    )

    assert "unchanged" in html.lower()
    assert "Nothing changed" in html


def test_reload_page_surfaces_unmapped_field_names():
    """A reload is exactly when new vocabulary arrives.

    An unmapped field is a relation the corpus states and the graph never
    builds. It is reported here, with the fix named, because that fix is a line
    of config/relations.yaml rather than a code change.
    """
    from src.ui.render import page_reload

    html = page_reload(
        {
            "elapsed_seconds": 6.2,
            "before": {"entities": 118, "edges": 265, "units": 30553},
            "after": {"entities": 119, "edges": 265, "units": 30571},
            "unmapped_fields": {"Custodian of": 3, "Sworn to": 1},
        }
    )

    assert "Custodian of" in html
    assert "Sworn to" in html
    assert "relations.yaml" in html


def test_the_front_page_offers_a_reindex_control():
    """The gap is disclosed in the product, not only in the docs."""
    from src.ui.render import page_index

    html = page_index()
    assert 'action="/reload"' in html
    assert "Reindex" in html


# -- the phrased answer on the page (ADR-037) --------------------------------


def test_a_view_without_synthesis_carries_no_prose_and_renders_none(views):
    """The keys always exist; a caller that phrases nothing gets None.

    `render.py` must never have to guess whether a key is present, and the page
    must not look like it withheld a sentence it does not have.
    """
    for view in views.values():
        assert view["prose"] is None
        assert view["phrasing"] is None
        assert view["phrasing_model"] is None
        assert 'class="prose"' not in page_answer(view)


def test_the_page_renders_the_phrased_sentence_with_its_provenance(graph):
    """The sentence was computed in the query layer and is rendered verbatim.

    It had been computed and then thrown away: `server.py` put it in the view
    and `render.py` had no block for it, so every demo answer showed a bare
    entity name. That is what ADR-037 fixes.
    """
    from src.query.synthesis import synthesise

    answer = answer_question(Q_013, graph, use_planner=False)
    synthesis = synthesise(answer, graph, use_model=False)
    html = page_answer(build_view(answer, graph, None, synthesis))

    assert 'class="prose"' in html

    # Rendered verbatim, not reworded. The sentence now carries markup - answer
    # values emboldened, citations set small and italic - so it is no longer a
    # contiguous string in the source. Strip the tags back out and every
    # character the query layer wrote must still be there, in order.
    import re as _re

    body = _re.search(r'<p class="prosetext">(.*?)</p>', html, _re.S).group(1)
    assert _re.sub(r"<[^>]+>", "", body) == escape(synthesis.text, quote=True)
    # Provenance is on the page, not just in the dict: a judge asking "did an AI
    # write this?" gets the answer without reading the source.
    assert "template" in html
    assert "no model, no API key, no network" in html


def test_model_phrasing_is_labelled_as_model_on_the_page(graph):
    from src.query.synthesis import Synthesis

    answer = answer_question(Q_013, graph, use_planner=False)
    view = build_view(
        answer, graph, None, Synthesis("A phrased answer.", "model", "vendor/model:free")
    )
    html = page_answer(view)
    assert "A phrased answer." in html
    assert "vendor/model:free" in html
    assert "forbidden from adding to them" in html


def test_nothing_to_phrase_renders_no_prose_block(graph):
    """A decline's sentence is its diagnostics, not a consolation paragraph."""
    from src.query.synthesis import synthesise

    answer = answer_question("What colour is the sky in the Ashen Era?", graph, use_planner=False)
    synthesis = synthesise(answer, graph, use_model=False)
    assert synthesis.phrasing == "none"
    assert 'class="prose"' not in page_answer(build_view(answer, graph, None, synthesis))


def test_prose_is_escaped(graph):
    from src.query.synthesis import Synthesis

    answer = answer_question(Q_013, graph, use_planner=False)
    html = page_answer(
        build_view(answer, graph, None, Synthesis('<script>alert("x")</script>', "model"))
    )
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_a_profile_answer_does_not_call_its_endpoints_values(graph):
    """The bullets under a profile are the entities its record links to. Calling
    them "values the engine returned" invites a reader to pick one as the
    answer, and a profile has no such answer to pick."""
    view = build_view(answer_question("Who is Ravena Stormwell?", graph), graph)
    assert view["status"] == "profile"
    html = page_answer(view)
    assert "entities this record links to" in html
    assert "The engine returned a set" not in html


# -- the sharpened answer page (ADR-038) -------------------------------------


def _synth(graph, question):
    from src.query.synthesis import synthesise

    answer = answer_question(question, graph, use_planner=False)
    return build_view(answer, graph, None, synthesise(answer, graph, use_model=False))


def test_an_answered_page_shows_the_sentence_and_not_a_duplicate_value_list(graph):
    """The sentence states the answer and the join. Repeating the bare values
    underneath was duplication that pushed the evidence off the screen."""
    html = page_answer(_synth(graph, Q_013))
    assert 'class="prose"' in html
    assert 'class="values"' not in html
    assert 'class="answer"' not in html


def test_the_answer_values_are_emboldened_inside_the_sentence(graph):
    view = _synth(graph, Q_013)
    html = page_answer(view)
    for value in view["values"]:
        assert f"<b>{escape(value, quote=True)}</b>" in html


def test_nothing_the_engine_did_not_return_is_emboldened(graph):
    """The bold strings come from `view["values"]`, which the engine produced."""
    import re as _re

    view = _synth(graph, Q_013)
    body = _re.search(r'<p class="prosetext">(.*?)</p>', page_answer(view), _re.S).group(1)
    bolded = set(_re.findall(r"<b>(.*?)</b>", body))
    assert bolded <= {escape(v, quote=True) for v in view["values"]}


def test_citations_are_marked_so_they_can_be_set_small_and_italic(graph):
    """The marker survives ADR-042 and still matters.

    The template sentence no longer carries a citation tail, so `1b_013` has
    nothing to mark. Two things still do: `1b_009`, whose dispute clause names
    the records that assert and deny (content, not a footnote), and any model
    that cites despite being told not to - which is exactly when the styling
    needs to keep it out of the way.
    """
    from src.query.synthesis import Synthesis

    html = page_answer(_synth(graph, Q_009))
    assert 'class="cite"' in html, "the dispute clause names two documents"
    assert ".cite { font-size: .78em; font-style: italic;" in html

    answer = answer_question(Q_013, graph, use_planner=False)
    cited = Synthesis(
        "The Bleeding Crown (source: wiki/marrowwell_abbey.md).", "model", "m"
    )
    assert 'class="cite"' in page_answer(build_view(answer, graph, None, cited))


def test_the_phrasing_provenance_is_behind_a_disclosure(graph):
    """Still on the page and still one click away - just not competing with the
    answer for the top of the screen."""
    html = page_answer(_synth(graph, Q_013))
    assert '<details class="prosemeta"><summary>How this answer was written</summary>' in html
    assert "no model, no API key, no network" in html


def test_the_supporting_surfaces_are_collapsed_on_an_answered_page(graph):
    """Every surface stays one click away; none of them competes with the answer."""
    import re as _re

    html = page_answer(_synth(graph, Q_013))
    for title in (
        "Strategy used",
        "Evidence sufficiency",
        "Evidence path",
        "Source documents and tiers",
    ):
        assert _re.search(rf'<details class="sect"><summary>{title}', html), title
    # `open` appears on none of them: the answer is what a reader sees first.
    assert '<details class="sect" open><summary>Strategy used' not in html


def test_evidence_sufficiency_is_open_on_a_decline(graph):
    """The named reason IS the result when there is no answer - collapsing it by
    default would undo ADR-026."""
    view = _synth(graph, "What colour is the sky in the Ashen Era?")
    assert view["answerable"] is False
    html = page_answer(view)
    assert '<details class="sect" open><summary>Evidence sufficiency' in html
    # The partial-evidence blocks are not collapsed at all.
    assert "<h2>What the system recognised</h2>" in html


def test_a_surfaced_conflict_is_open(graph):
    """A same-tier contradiction a reader must click to discover is one the demo
    did not surface (`1b_009`)."""
    html = page_answer(_synth(graph, Q_009))
    assert '<details class="sect" open><summary>Conflict, and how it was handled' in html


def test_the_checkpoint_footer_is_gone(graph):
    """It was also wrong: an LLM does phrase answers on this path now."""
    for html in (page_answer(_synth(graph, Q_013)), page_index()):
        assert "Checkpoint 2" not in html
        assert "no LLM in this path" not in html


# -- the path, stated once and clearly ---------------------------------------


def test_the_evidence_path_states_the_whole_chain_on_one_line(graph):
    """The hop blocks carry the provenance; this says what was joined to what.

    `1b_013`: Gravemaw Wyrm -> lair_in -> Marrowwell Abbey -> ruled_by ->
    The Bleeding Crown.
    """
    from src.ui.render import _chain_line

    view = _synth(graph, Q_013)
    route = view["routes"][0]
    assert _chain_line(route, plain=True) == (
        "Gravemaw Wyrm \u2192 lair_in \u2192 Marrowwell Abbey \u2192 ruled_by "
        "\u2192 The Bleeding Crown"
    )

    html = page_answer(view)
    assert 'class="chain"' in html
    # Endpoint marked as the endpoint, so the eye lands on the answer.
    assert '<span class="cnode end">The Bleeding Crown</span>' in html


def test_a_single_route_puts_its_chain_in_the_collapsed_header(graph):
    """The evidence path is collapsed by default, so the one thing a reader
    most wants from it - what joined to what - is in the label."""
    html = page_answer(_synth(graph, Q_013))
    assert "Gravemaw Wyrm \u2192 lair_in \u2192 Marrowwell Abbey" in html
    assert 'class="sumchain"' in html


def test_many_routes_keep_a_generic_header(graph):
    """`1b_006` has fourteen routes; fourteen chains would not fit in a label
    and would not help. Each route states its own chain inside instead."""
    view = _synth(graph, Q_006)
    assert len(view["routes"]) == 14
    html = page_answer(view)
    assert 'class="sumchain"' not in html
    assert "every hop, with its source passage" in html
    assert html.count('class="chain"') == 14


def test_the_chain_marks_the_disputed_relation(graph):
    """`1b_009`: the victor hop is disputed and the member hop is not, and the
    one-line summary must not flatten that distinction."""
    from src.ui.render import _chain_line

    view = _synth(graph, Q_009)
    chain = _chain_line(view["routes"][0])
    assert '<span class="rel disputed">victor_of</span>' in chain
    assert '<span class="rel">member_of</span>' in chain


def test_the_chain_follows_the_engines_own_hop_order(graph):
    """Hop N's target is hop N+1's subject by construction - the line is read
    off `route["hops"]`, never reassembled."""
    from src.ui.render import _chain_line

    for question in (Q_013, Q_007, Q_009):
        route = _synth(graph, question)["routes"][0]
        plain = _chain_line(route, plain=True)
        expected = [route["start_name"]]
        for hop in route["hops"]:
            expected += [hop["relation"], hop["to_name"]]
        assert plain == escape(" \u2192 ".join(expected), quote=True)


# -- the busy state (ADR-040) ------------------------------------------------


def test_the_form_still_works_with_scripting_off(graph):
    """The script is feedback about a request, never a precondition for one.

    With JavaScript disabled the form submits exactly as it always has and the
    busy message is simply never shown - the `busy` class is the only thing the
    script adds, and CSS hides the message without it.
    """
    html = page_index()
    assert '<form id="askform" action="/ask" method="get">' in html
    assert 'name="q"' in html
    assert '<button type="submit">Ask</button>' in html, "not pre-disabled"
    assert ".busymsg { display: none;" in html


def test_the_page_loads_no_script_and_no_asset_from_anywhere(graph):
    """One inline snippet, and nothing fetched. That is the invariant that
    matters - not "no JavaScript", which was the wrong thing to pin."""
    import re as _re

    for html in (page_index(), page_answer(_synth(graph, Q_013))):
        opens = _re.findall(r"<script[^>]*>", html)
        assert len(opens) == 1, f"expected one script tag, got {opens}"
        assert "src=" not in opens[0]
        for remote in ("http://", "https://", "//cdn", "cdnjs", "unpkg"):
            assert remote not in html


def test_the_busy_message_names_the_slow_part_only_when_a_model_is_used(graph):
    """A deterministic run answers in about 11ms; promising a wait for the
    model when no model will be called would be a lie the page tells itself."""
    off = page_index(model_phrasing=False)
    assert "Searching the archive" in off
    assert "phrasing with a model" not in off

    on = page_index(model_phrasing=True)
    assert "phrasing with a model can take a few seconds" in on

    # The answer page carries the same flag, so the wording does not change
    # between the front page and a follow-up question.
    view = _synth(graph, Q_013)
    assert "phrasing with a model" in page_answer(view, model_phrasing=True)
    assert "phrasing with a model" not in page_answer(view, model_phrasing=False)


def test_the_busy_state_is_reset_on_back_navigation(graph):
    """The back button restores a page from the browser's cache with the button
    still disabled and still reading "Searching" - which looks exactly like the
    hang this exists to prevent."""
    html = page_index()
    assert 'window.addEventListener("pageshow", reset)' in html
    assert 'button.textContent = "Ask"' in html


def test_the_submit_button_is_disabled_out_of_band(graph):
    """Disabling a submit button inside its own submit handler cancels the
    submission in some browsers. The timeout lets the request start first."""
    html = page_index()
    assert "setTimeout(function () { button.disabled = true; }, 0)" in html


def test_the_spinner_respects_reduced_motion(graph):
    html = page_index()
    assert "@media (prefers-reduced-motion: reduce) { .spinner { animation: none; } }" in html


# -- a sentence may not quietly drop answers (ADR-041) -----------------------


def test_a_sentence_that_names_one_of_fourteen_is_corrected_on_the_page(graph):
    """The regression ADR-038 introduced and this catches.

    Asked `1b_006`, which has fourteen equally valid answers, a model wrote one
    of them with two correct citations attached - and ADR-038 had just removed
    the value list that would have exposed it. Measured, not hypothetical: the
    live model named 1 of 14.
    """
    from src.query.synthesis import Synthesis

    answer = answer_question(Q_006, graph, use_planner=False)
    assert len(answer.values) == 14

    partial = Synthesis(
        "Corvus Hollowmere the Pale was a member of The Silent Choir, which "
        "won the War of Drowned Light.",
        "model",
        "vendor/model:free",
    )
    html = page_answer(build_view(answer, graph, None, partial))

    assert "names 1 of 14 answers" in html
    for value in answer.values:
        assert escape(value, quote=True) in html, f"{value} is missing from the page"


def test_a_sentence_naming_every_answer_renders_alone(graph):
    """The deterministic template names all fourteen, so nothing is appended -
    the clean single-box layout is preserved wherever it is honest."""
    from src.query.synthesis import synthesise

    answer = answer_question(Q_006, graph, use_planner=False)
    view = build_view(answer, graph, None, synthesise(answer, graph, use_model=False))
    html = page_answer(view)
    assert 'class="unstated"' not in html
    for value in answer.values:
        assert escape(value, quote=True) in html


def test_a_single_answer_never_triggers_the_guard(graph):
    """One value that the sentence happens to word differently is not an
    omission worth a warning box - the guard is about a dropped *set*."""
    from src.query.synthesis import Synthesis

    answer = answer_question(Q_013, graph, use_planner=False)
    assert len(answer.values) == 1
    view = build_view(answer, graph, None, Synthesis("A sentence.", "model", "m"))
    assert 'class="unstated"' not in page_answer(view)


def test_the_model_is_told_to_name_every_answer(graph):
    """The prompt fix. The hops were always all there; what was missing was any
    statement that the endpoints are a set."""
    from src.query.synthesis import synthesise

    class _Pool:
        def __init__(self):
            self.prompts = []

        def generate(self, contents, **kw):
            self.prompts.append("\n".join(contents))
            return "phrased", "fake/model:free"

    pool = _Pool()
    synthesise(answer_question(Q_006, graph, use_planner=False), graph, pool=pool)
    prompt = pool.prompts[0]

    assert "This question has 14 answers, ALL equally valid" in prompt
    assert "must name every one" in prompt
    assert "Ravena Stormwell" in prompt and "Thessaly Coldwater" in prompt
    assert "name EVERY one of them" in prompt


def test_a_single_answer_prompt_does_not_claim_a_set(graph):
    from src.query.synthesis import synthesise

    class _Pool:
        def __init__(self):
            self.prompts = []

        def generate(self, contents, **kw):
            self.prompts.append("\n".join(contents))
            return "phrased", "fake/model:free"

    pool = _Pool()
    synthesise(answer_question(Q_013, graph, use_planner=False), graph, pool=pool)
    assert "ALL equally valid" not in pool.prompts[0]


# -- navigation and the footer (ADR-043) -------------------------------------


def test_every_page_carries_a_visible_way_home(graph):
    """The title has always linked home and has always rendered as plain text
    (`color: inherit; text-decoration: none`), so nobody found it. A real nav
    row is the fix; the title keeps its link but now shows a hover underline so
    it stops being a hidden trapdoor."""
    from src.ui.render import page_graph

    for html in (
        page_index(),
        page_answer(_synth(graph, Q_013)),
        page_graph("<svg></svg>", "", 117, 261),
        page_error("boom"),
    ):
        assert '<nav class="nav">' in html
        assert '<a href="/" class="on">Ask</a>' in html or '<a href="/">Ask</a>' in html
    assert "h1 a:hover { text-decoration: underline;" in page_index()


def test_the_graph_view_is_reachable_by_link(graph):
    """It was reachable only by typing the URL - a built, tested demo surface
    that a judge had no way to discover."""
    for html in (page_index(), page_answer(_synth(graph, Q_013))):
        assert '<a href="/graph">Graph</a>' in html


def test_the_current_page_is_marked_in_the_nav(graph):
    from src.ui.render import page_graph

    assert '<a href="/" class="on">Ask</a>' in page_index()
    assert '<a href="/graph" class="on">Graph</a>' in page_graph("<svg></svg>", "", 117, 261)


def test_the_tagline_moved_to_the_footer_and_was_reworded(graph):
    """From the bottom of the page, "every hop below" pointed at nothing."""
    html = page_answer(_synth(graph, Q_013))
    assert "<footer>" in html
    assert "Every hop above cites the infobox row it was read from." in html
    assert "Every hop below" not in html
    # It is the last thing on the page, not a second heading at the top.
    assert html.index("<footer>") > html.index('<h2>Answer</h2>')


def test_the_footer_document_count_matches_the_corpus(corpus_root):
    """A hard-coded number in a page nothing re-runs is how F-026 happened, and
    the corpus can be reloaded at runtime (ADR-036) - so it is re-derived here,
    the way `tests/test_docs.py` re-derives graph counts asserted in prose."""
    from src.ingest.pipeline import ingest
    from src.ui.render import CORPUS_DOCUMENTS

    result = ingest()

    # `documents`, not the documents that produced evidence units. Measured:
    # 317 canonical documents, of which only 247 yield any evidence - the other
    # 70 are image plates with no text layer. The footer's claim is about the
    # size of the corpus queried, so 317 is the honest number; asserting 247
    # here would have quietly redefined what the page says.
    assert CORPUS_DOCUMENTS == len(result.documents)
    assert f"over {len(result.documents)} documents" in page_index()
