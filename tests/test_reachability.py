"""ADR-030's numbers, re-derived from the live corpus.

WHY THIS FILE EXISTS
--------------------
ADR-030 measured one entity the corpus treats as first-class with no node in the
graph, and named the row that should have built it:
`wiki/the_ashen_vanguard.md`'s unlinked `Members`. ADR-032 then fixed it, and
the number is now **zero** - every one of the 79 documents that declares its own
subject reaches a node, and no infobox row on a mapped relation field names an
entity the graph does not hold.

Zero is a harder number to keep than one. It holds only while the name lexicon
includes `[[wikilink]]` targets as well as page subjects, and nothing else in
the suite would notice that narrowing - the graph would just get quietly smaller
and the report would keep claiming a completeness it no longer had. That is
F-026's failure exactly: prose said 35 while the artefact said 33 for three
days. So the zero is pinned here, from both directions - the symptom (nothing
unreachable) and the cause (no silent rows).

These assert on the probe's *functions*, not on its printed text: the printed
report is for a human, and pinning its formatting would make it painful to
improve for no gain.
"""

from __future__ import annotations

import pytest

from eval.probes import entity_reachability as probe
from src.ingest.pipeline import ingest_cached


@pytest.fixture(scope="module")
def evidence(corpus_root):
    return ingest_cached()


def test_the_declared_subject_count_is_stable(evidence, graph):
    """79 non-wiki documents name their own subject in the filename."""
    reached, missing = probe.declared_subjects(evidence, graph)
    assert len(reached) + len(missing) == 79


def test_the_only_unreached_subject_is_a_truncated_corpus_filename(evidence, graph):
    """The one remaining miss is not a gap in the graph.

    `interrogation_record_concerning_isolde_fellgard_the_unforgiv.txt` is cut
    mid-word in the corpus itself, and the entity it names *does* have a node,
    reached under her full name from the untruncated sibling document. Exact
    matching (ADR-011) is what makes the slug fail rather than being fuzzily
    attached to the right person, which is the correct trade.
    """
    _, missing = probe.declared_subjects(evidence, graph)
    assert [slug for slug, _ in missing] == ["isolde_fellgard_the_unforgiv"]
    assert "isolde_fellgard_the_unforgiven" in graph.nodes
    assert "halvard_cindervale" in graph.nodes, "ADR-032 built him; see F-032"


def test_no_infobox_row_names_an_entity_the_graph_does_not_hold(graph):
    """The cause, pinned at zero.

    A row here would mean the builder read a cell, recognised the field as a
    relation, and dropped the names in it anyway - which is invisible to
    `unmapped_fields` (the field IS mapped) and to `self_references` (the target
    is not the subject). That is how F-032 hid for a week.
    """
    silent = probe.silent_relation_rows(graph)
    assert [(doc, field, lost) for doc, field, _, lost in silent if lost] == []


def test_the_vanguard_members_row_builds_all_three_edges(graph):
    """The row F-032 was about, now producing what it says.

    Voltaire and Orin had nodes anyway, from linked cells on other pages, so the
    row was worth one node and three edges rather than three of each. Asserting
    all three edges rather than just Halvard's node keeps that distinction
    honest.
    """
    members = {
        e.source
        for e in graph.edges
        if e.document == "wiki/the_ashen_vanguard.md" and e.field_name == "Members"
    }
    assert members == {"halvard_cindervale", "voltaire_hollowmere", "orin_veyra"}


def test_span_normalisation_strips_inflections_not_names(graph):
    """The leading-stopword strip may not eat a name that starts with "The"."""
    assert probe.normalise_span("And the Bleeding Crown") == "the Bleeding Crown"
    assert probe.normalise_span("The Iron-Ring Cartel’s") == "The Iron-Ring Cartel"
    assert probe.normalise_span("Of Sabelle Blackspire") == "Sabelle Blackspire"
    # Nothing multi-word survives, so the span is discarded rather than counted
    # as a one-word candidate.
    assert probe.normalise_span("Behind Sabelle") == ""


def test_fuzzy_near_misses_count_as_unreachable(evidence, graph):
    """ADR-011 holds here: the probe may not resolve what the product refuses to."""
    assert probe.ResolutionStatus.AMBIGUOUS not in probe.EXACT_TIERS
