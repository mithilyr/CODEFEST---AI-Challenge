"""Tests for cross-collection attestation (`src/graph/corroborate.py`, ADR-027).

The measurement these pin is the one the report quotes: how much of the graph
the other three collections independently name. They also pin two *refusals* -
that a corroborating passage is never read as an assertion of the relation, and
that the shipped denial pattern is not wired to these units - because both were
decided by a measurement that could drift.
"""

from __future__ import annotations

import pytest

from src.graph.build import build_graph
from src.graph.corroborate import (
    CORROBORATING_COLLECTIONS,
    Attestation,
    build_index,
    scan_surfaces,
)
from src.ingest.pipeline import ingest
from src.query.conflict import _DENIAL_RE


@pytest.fixture(scope="module")
def ingested(corpus_root):
    return ingest()


@pytest.fixture(scope="module")
def index(graph, ingested):
    return build_index(graph, ingested.evidence)


# --------------------------------------------------------------------------
# The measurement (ADR-027)
# --------------------------------------------------------------------------


def test_most_edges_are_attested_outside_the_wiki(graph, index):
    """MEASURED: 255 of 267 edges are named by a non-wiki passage.

    The remaining 12 are 6 self-loops (excluded by construction - a page naming
    itself, see F-030) and 6 genuine misses.
    """
    corroborated = index.corroborated_edges(graph)
    assert len(corroborated) == 255
    assert len(graph.edges) == 267


def test_self_loops_are_never_corroborated(graph, index):
    """F-030: 6 edges run from a node to itself, so "both ends" is one end."""
    loops = [e for e in graph.edges if e.source == e.target]
    assert len(loops) == 6
    assert all(not index.for_edge(e) for e in loops)


def test_attestations_come_only_from_the_other_collections(graph, index):
    """A wiki paragraph restating a wiki infobox is one source agreeing with
    itself, which is not attestation."""
    for edge in graph.edges:
        for attestation in index.for_edge(edge):
            assert attestation.collection in CORROBORATING_COLLECTIONS
            assert attestation.collection != "wiki"


def test_the_codex_is_the_dominant_attesting_collection(graph, index):
    """MEASURED: codex 416 attestations, chronicles 114, ephemera 25. The codex
    restates infobox facts in prose; the novels mostly co-mention in passing."""
    counts = {}
    for edge in graph.edges:
        for attestation in index.for_edge(edge):
            counts[attestation.collection] = counts.get(attestation.collection, 0) + 1
    assert counts["codex"] > counts["chronicles"] > counts["ephemera"]


# --------------------------------------------------------------------------
# Provenance and the cap
# --------------------------------------------------------------------------


def test_every_attestation_carries_a_full_citation(graph, index):
    """The whole point is that a judge can open the document and check."""
    for edge in graph.edges:
        for attestation in index.for_edge(edge):
            assert attestation.document
            assert attestation.locator
            assert attestation.evidence_id
            assert attestation.tier > 0
            assert attestation.quote.strip()


def test_the_cap_is_respected_and_keeps_the_highest_authority(graph, index):
    """Ranking is by tier ascending, so a codex passage outranks a novel."""
    for edge in graph.edges:
        attestations = index.for_edge(edge)
        assert len(attestations) <= index.cap
        tiers = [a.tier for a in attestations]
        assert tiers == sorted(tiers)


def test_the_cap_is_deterministic_across_builds(graph, ingested):
    """A cap that kept an arbitrary slice would make the demo unreproducible."""
    first = build_index(graph, ingested.evidence)
    second = build_index(graph, ingested.evidence)
    for edge in graph.edges:
        assert [a.evidence_id for a in first.for_edge(edge)] == [
            a.evidence_id for a in second.for_edge(edge)
        ]


def test_a_named_pair_really_does_appear_in_the_passage(graph, index):
    """Spot-check the mechanism rather than trusting the count: 1b_013's first
    hop is restated almost verbatim by the bestiary codex."""
    edge = next(
        e
        for e in graph.edges
        if e.source == "gravemaw_wyrm" and e.target == "marrowwell_abbey"
    )
    attestations = index.for_edge(edge)
    assert attestations
    quote = attestations[0].quote.lower()
    assert "gravemaw wyrm" in quote
    assert "marrowwell abbey" in quote
    assert attestations[0].collection == "codex"


# --------------------------------------------------------------------------
# The two refusals
# --------------------------------------------------------------------------


def test_an_ambiguous_surface_form_is_reported_and_never_scanned(graph):
    """ADR-011 holds here: a surface naming two nodes is dropped, not guessed.

    The corpus currently produces none, so the behaviour is exercised with an
    injected collision rather than left untested until one appears.
    """
    _, surface_to_key, ambiguous = scan_surfaces(graph)
    assert ambiguous == {}

    class _TwoNodeGraph:
        nodes = {
            "a_fellgard": type("N", (), {"key": "a_fellgard", "name": "Grey Fellgard"})(),
            "b_fellgard": type("N", (), {"key": "b_fellgard", "name": "Grey Fellgard"})(),
        }
        edges: list = []

    _, surfaces, collisions = scan_surfaces(_TwoNodeGraph())
    assert "grey fellgard" in collisions
    assert collisions["grey fellgard"] == ("a_fellgard", "b_fellgard")
    assert "grey fellgard" not in surfaces


def test_no_attached_attestation_is_treated_as_a_denial(graph, index):
    """MEASURED, and the reason the conflict machinery is NOT wired to these.

    `_DENIAL_RE` is tuned for wiki infobox-page prose. Across the whole non-wiki
    corpus it matches 5 units and all 5 are false positives - two of them
    *affirm* the claim they appear to deny ("entered without triumph or lament:
    The Silent Choir victor of The War of Drowned Light"). None is attached to
    an edge. If this assertion ever fails, read ADR-027 before wiring anything:
    a false denial at tier 1 would manufacture a conflict and resolve it
    against the truth.
    """
    matched = [
        a
        for e in graph.edges
        for a in index.for_edge(e)
        if _DENIAL_RE.search(a.quote)
    ]
    assert matched == []


def test_corroboration_never_adds_or_alters_an_edge(graph, ingested):
    """It is a lookup layer. The graph it describes must be untouched."""
    before = [(e.source, e.relation, e.target) for e in graph.edges]
    build_index(graph, ingested.evidence)
    after = [(e.source, e.relation, e.target) for e in graph.edges]
    assert before == after
    assert len(build_graph().edges) == 267
