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

    THE NUMBER ITSELF IS PINNED, NOT RE-DERIVED. Unlike the entity/edge counts
    elsewhere in this file, "35 of 49" is not recomputed here from
    `comparison.harness` - this test only checks the SVG's text against a
    literal a human must remember to update, which is exactly the gap this
    file's own docstring describes (ADR-019's 35 went stale to 33 while only
    the summary metric was checked). It has *already* happened to this literal
    once: 35 -> 33 (ADR-021) -> 35 again, for a different and correct reason
    this time (ADR-025, F-026 fixed). Re-run `python -m comparison.harness`
    before trusting this number in the report; this test only proves the
    diagram and this string agree with each other, not that either is current.
    """
    assert "7/7" in diagram_text
    assert "35 of 49" in diagram_text


def test_diagram_does_not_claim_the_graph_answers_questions_by_itself(diagram_text):
    """ADR-016 measures evidence *coverage*, not answer correctness.

    The 7/7 on the diagram is the query layer's (ADR-017). If someone ever
    labels the graph box 7/7 as well, the two different 7/7s become one
    overstated claim.
    """
    graph_box = diagram_text.split("Graph — ")[1].split("Query")[0]
    assert "7/7" not in graph_box
