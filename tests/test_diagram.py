"""The architecture diagram's numbers, re-derived from the live corpus.

WHY THIS FILE EXISTS
--------------------
A diagram is the one artefact nobody re-runs. `docs/diagrams/architecture.svg`
goes in the report (challenge doc §5.3) and in the repo (§5.2), and a judge will
read its numbers as claims about the system. Nothing else in this project would
notice if they drifted.

We already know that drift happens here and is invisible: ADR-019 recorded
"35 of 49" and it was **33** by the time anyone looked, because a later commit
reclassified four questions and checked only the summary metric that had not
moved (F-026). The prose was stale for three days while the committed JSON
artefact already held the new number.

So the diagram is pinned the same way `test_graph.py` pins ADR-010's twelve
templates: parse the shipped SVG, re-derive each number from the corpus, and
fail if they disagree. Updating the diagram then means updating it *correctly*
or seeing red.

These tests deliberately assert on the SVG's *text*, not on a data structure the
diagram is generated from. The diagram is hand-authored - it is a static picture
of an architecture, not a rendering of data (ADR-022), so there is nothing to
generate it from, and a test that read the same constants the picture was drawn
from would prove nothing.
"""

from __future__ import annotations

import collections
import re
from pathlib import Path

import pytest

from src.graph.build import infobox_rows
from src.graph.cells import parse_cell
from src.ingest.integrity import read_manifest
from src.ingest.pipeline import ingest_cached
from src.query.engine import answer_question

DIAGRAM = Path(__file__).resolve().parents[1] / "docs" / "diagrams" / "architecture.svg"


@pytest.fixture(scope="module")
def diagram_text() -> str:
    """The diagram's rendered text content, with markup and tspans flattened.

    Numbers are asserted against this rather than the raw file so a label split
    across a `<tspan>` still matches.
    """
    raw = DIAGRAM.read_text(encoding="utf-8")
    stripped = re.sub(r"<[^>]+>", "", raw)
    return re.sub(r"\s+", " ", stripped)


def assert_label(diagram_text: str, label: str) -> None:
    """Assert an exact rendered sentence, not merely that a number occurs.

    WHY EXACT SENTENCES. The first version of these tests collected every
    integer in the file and asked "is the measured value one of them". That
    passed a deliberate mutation of the graph box from 117 to 125, because 117
    still appeared in the UI box's "/graph renders all 117 entities". A number
    present *somewhere* proves nothing about the box that should carry it -
    which is F-026's lesson (a summary metric holding steady while the specific
    thing underneath it regressed) reproduced inside its own regression test.

    Binding each number to the sentence it belongs to is what actually pins it.
    """
    assert label in diagram_text, f"diagram no longer states: {label!r}"


# --------------------------------------------------------------------------
# The diagram is a real, parseable SVG
# --------------------------------------------------------------------------


def test_diagram_exists_and_is_well_formed_xml():
    """§5.2 and §5.3 both require the diagram; a broken one satisfies neither."""
    import xml.etree.ElementTree as ET

    assert DIAGRAM.is_file(), f"{DIAGRAM} is missing - the report requires it"
    ET.parse(DIAGRAM)  # raises on malformed markup


def test_diagram_embeds_no_external_reference():
    """Same rule the UI lives under (ADR-018): no CDN, no remote asset.

    A diagram that needs the network is a diagram that renders as a broken box
    on the judge's machine.
    """
    raw = DIAGRAM.read_text(encoding="utf-8")

    # The SVG namespace is a URL but is never fetched, so it is the one
    # permitted occurrence. Remove it, then no scheme may remain.
    assert raw.count('xmlns="http://www.w3.org/2000/svg"') == 1
    body = raw.replace('xmlns="http://www.w3.org/2000/svg"', "")

    for forbidden in ("http://", "https://", "xlink:href", "<image", "@import", "url("):
        if forbidden == "url(":
            # url(#arrow) references a local marker; url(http...) would not be local
            assert "url(#" in body, "expected local marker references"
            assert not re.search(r"url\(\s*['\"]?(?!#)", body), "only local url(#id) allowed"
            continue
        assert forbidden not in body, f"diagram must be self-contained: found {forbidden!r}"


# --------------------------------------------------------------------------
# Ingestion numbers
# --------------------------------------------------------------------------


def test_corpus_file_count_matches_the_manifest(diagram_text):
    """"341 files verified" is the integrity manifest's own count."""
    assert_label(diagram_text, f"{len(read_manifest())} files verified")


def test_ingestion_numbers_match_a_real_ingest(corpus_root, diagram_text):
    """340 scanned, 317 canonical, 22 collapsed, 30,553 evidence units."""
    result = ingest_cached()
    report = result.dedup_report

    assert_label(
        diagram_text,
        f"{report.total_files} documents scanned → "
        f"{report.canonical_documents} canonical · "
        f"{report.duplicates_collapsed} duplicates collapsed",
    )
    assert_label(diagram_text, f"EvidenceUnit × {len(result.evidence):,}")


# --------------------------------------------------------------------------
# Graph numbers
# --------------------------------------------------------------------------


def test_graph_numbers_match_the_built_graph(graph, diagram_text):
    """118 entities and 265 edges - the figures the no-graph-database argument rests on."""
    assert_label(
        diagram_text,
        f"Graph — {len(graph.nodes)} entities, {len(graph.edges)} edges",
    )
    # The UI box repeats the entity count; it must not be allowed to drift apart
    # from the graph box, which is how the 117/125 mutation slipped through once.
    assert_label(diagram_text, f"all {len(graph.nodes)} entities as one static SVG")


def test_relation_and_unmapped_counts_match(graph, relations, diagram_text):
    """15 relations, 0 unmapped. An unmapped field is an edge that silently never exists."""
    distinct = {edge.relation for edge in graph.edges}
    assert graph.unmapped_fields == {}
    assert_label(
        diagram_text, f"109 field names → {len(distinct)} relations · 0 unmapped"
    )


def test_cell_and_template_counts_match_the_corpus(corpus_root, diagram_text):
    """ADR-010's closed set, re-derived here as `test_graph.py` does."""
    from eval.probes.corpus_shape import wiki_pages

    counts = collections.Counter()
    for _, text in wiki_pages(corpus_root):
        for _, value in infobox_rows(text):
            counts[parse_cell(value).template] += 1

    assert_label(
        diagram_text,
        f"{sum(counts.values())} infobox cells → {len(counts)} closed templates",
    )


# --------------------------------------------------------------------------
# The claims the diagram makes about behaviour, not about counts
# --------------------------------------------------------------------------


def test_diagram_marks_both_query_tier_model_calls_off_by_default(diagram_text):
    """The dashed boxes claim "off by default". The code must actually agree.

    This is the claim a judge is most likely to test live, and F-025 is the day
    it was briefly untrue - an OPENROUTER_API_KEY in .env silently turned the
    planner on for the whole test suite.
    """
    assert diagram_text.lower().count("off by default") >= 2

    import inspect

    signature = inspect.signature(answer_question)
    assert signature.parameters["use_planner"].default is False


def test_diagram_states_the_robustness_number_beside_the_fit_number(diagram_text):
    """7/7 never appears without the robustness number beside it (CLAUDE.md's
    standing rule).

    Quoting the fit number alone is the single most misleading thing this
    submission could do, so the diagram is not allowed to do it.

    THE NUMBER IS NOW RE-DERIVED, AND THE REASON IS THIS TEST'S OWN HISTORY.
    It used to assert the literal "35 of 49" and carried a docstring explaining
    that a human had to remember to update it. On 6 Sep that literal was found
    to be *already wrong*: ADR-029 moved the figure to 36, the SVG still said
    35, and the suite was green - the exact F-026 failure this file exists to
    catch, reproduced inside the test written to warn about it. A comment
    describing a gap does not close it.

    It is now recomputed from the two committed artefacts: the frozen question
    set says which questions are answerable, the harness result says which of
    them matched no route shape. That proves the picture agrees with the last
    harness run - not that the run is current. `python -m comparison.harness`
    is still the thing to run before the report is final.
    """
    assert "7/7" in diagram_text
    assert f"{_no_route_shape('arm_a')} of {_answerable()}" in diagram_text


def test_diagram_does_not_claim_the_graph_answers_questions_by_itself(diagram_text):
    """ADR-016 measures evidence *coverage*, not answer correctness.

    The 7/7 on the diagram is the query layer's (ADR-017). If someone ever
    labels the graph box 7/7 as well, the two different 7/7s become one
    overstated claim.
    """
    graph_box = diagram_text.split("Graph — ")[1].split("Query")[0]
    assert "7/7" not in graph_box


# --------------------------------------------------------------------------
# Re-deriving the routing-robustness figure instead of remembering it
# --------------------------------------------------------------------------
#
# This file's own docstring named the gap: "35 of 49" was a literal a human had
# to remember to update, and the docstring said so while the literal was ALREADY
# WRONG - the harness had said 36 since ADR-029 and the SVG still said 35, with
# a green suite. That is exactly the F-026 failure this file exists to catch,
# reproduced inside the test written to warn about it.
#
# So it is re-derived from the two committed artefacts: the frozen question set
# supplies which questions are answerable, the harness result supplies which of
# them matched no route shape. This proves the picture agrees with the last
# harness run, not that the run is current - `python -m comparison.harness` is
# still the thing to run before the report. But it can no longer be stale in a
# direction nobody notices.

ROBUSTNESS_SET = (
    Path(__file__).resolve().parents[1]
    / "eval" / "robustness" / "routing_robustness_v1.json"
)
HARNESS_RESULT = (
    Path(__file__).resolve().parents[1]
    / "comparison" / "results" / "router_comparison.json"
)


def _answerable_rids() -> set:
    import json

    payload = json.loads(ROBUSTNESS_SET.read_text(encoding="utf-8"))
    questions = payload["questions"] if isinstance(payload, dict) else payload
    return {q["rid"] for q in questions if q.get("expected_answerable", True)}


def _answerable() -> int:
    return len(_answerable_rids())


def _no_route_shape(arm: str) -> int:
    import json

    rids = _answerable_rids()
    rows = json.loads(HARNESS_RESULT.read_text(encoding="utf-8"))[arm]["per_question"]
    return sum(1 for r in rows if r["rid"] in rids and r["no_route_shape"])


# --------------------------------------------------------------------------
# The Mermaid diagrams in docs/architecture.md
# --------------------------------------------------------------------------
#
# WHY THESE EXIST ALONGSIDE THE SVG TESTS
# ---------------------------------------
# A second picture is a second place for a number to rot, and this file's whole
# premise is that a diagram is the one artefact nobody re-runs. The Mermaid
# blocks are therefore pinned exactly as the SVG is: parsed out of the Markdown,
# flattened, and checked label by label against the live corpus.
#
# `assert_label` is reused deliberately - the same "bind each number to the
# sentence it belongs to" rule, for the same reason. A number present *somewhere*
# in a 60-line flowchart proves nothing about the box that should carry it.

ARCHITECTURE = Path(__file__).resolve().parents[1] / "docs" / "architecture.md"


@pytest.fixture(scope="module")
def mermaid_text() -> str:
    """Every ```mermaid block in architecture.md, flattened to one string.

    `<br/>` becomes a space so a label split across lines still matches, the
    same reason `diagram_text` flattens `<tspan>`.
    """
    raw = ARCHITECTURE.read_text(encoding="utf-8")
    blocks = re.findall(r"```mermaid\n(.*?)```", raw, re.S)
    assert blocks, "docs/architecture.md carries no mermaid diagram"
    joined = " ".join(blocks).replace("<br/>", " ")
    return re.sub(r"\s+", " ", joined)


def test_both_mermaid_diagrams_are_present(mermaid_text):
    """Build path and answer path. Losing one silently is the failure here."""
    assert "flowchart TD" in mermaid_text
    assert mermaid_text.count("flowchart TD") == 2


def test_mermaid_ingestion_numbers_match_a_real_ingest(corpus_root, mermaid_text):
    result = ingest_cached()
    report = result.dedup_report

    assert_label(mermaid_text, f"{len(read_manifest())} files verified")
    assert_label(
        mermaid_text,
        f"{report.canonical_documents} canonical documents "
        f"from {report.total_files} scanned",
    )
    assert_label(mermaid_text, f"{len(result.evidence):,} EvidenceUnits")


def test_mermaid_graph_numbers_match_the_built_graph(graph, mermaid_text):
    relations = {edge.relation for edge in graph.edges}
    assert graph.unmapped_fields == {}
    assert_label(
        mermaid_text,
        f"Graph — {len(graph.nodes)} entities, {len(graph.edges)} edges",
    )
    assert_label(mermaid_text, f"{len(relations)} relations · 0 unmapped field names")
    # The UI box repeats the entity count; it must not drift from the graph box,
    # which is how the 117/125 mutation slipped past the SVG tests once.
    assert_label(mermaid_text, f"draws all {len(graph.nodes)} entities")


def test_mermaid_corroboration_numbers_are_re_derived(graph, corpus_root, mermaid_text):
    """The rows `docs/numbers.md` flags as its one unguarded weak spot.

    That sheet says these went stale once already - 416/238 before F-032 added
    four corroborated edges - and nothing caught it, because `test_docs.py`
    deliberately skips the "N of M edges" shape to avoid false-positives on
    historical prose. Re-deriving them here closes that gap for the diagram at
    least, which is the copy a reader is most likely to quote from.
    """
    from src.graph.corroborate import build_index

    result = ingest_cached()
    index = build_index(graph, result.evidence)
    corroborated = index.corroborated_edges(graph)

    assert_label(mermaid_text, f"{index.units_scanned:,} units scanned")
    assert_label(
        mermaid_text,
        f"{len(corroborated)} of {len(graph.edges)} edges named outside the wiki",
    )


def test_mermaid_status_count_matches_the_enum(mermaid_text):
    """15 named outcomes. If someone adds a sixteenth, the picture must say so."""
    from src.query.evidence import EvidenceStatus

    assert_label(
        mermaid_text, f"{len(list(EvidenceStatus))} named EvidenceStatus values"
    )


def test_mermaid_never_quotes_the_fit_number_alone(mermaid_text):
    """CLAUDE.md's standing rule, enforced on the second picture too."""
    assert "7/7" in mermaid_text
    assert f"no route shape — {_no_route_shape('arm_a')} of {_answerable()}" in mermaid_text


def test_mermaid_marks_the_traversal_as_model_free(mermaid_text):
    """The load-bearing architectural claim of the whole submission.

    If the traversal box ever stops saying this, the "deterministic-first"
    argument has quietly become unsupported by its own diagram.
    """
    assert "NO model in this path" in mermaid_text
    assert "OFF BY DEFAULT" in mermaid_text
