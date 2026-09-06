"""ADR-030's numbers, re-derived from the live corpus.

WHY THIS FILE EXISTS
--------------------
ADR-030 puts a number in `docs/limitations.md` and in the report: **one** entity
the corpus treats as first-class has no node in the graph, and the row that
should have built it is `wiki/the_ashen_vanguard.md`'s `Members`. That is a
limitation we chose to disclose rather than fix three days from the deadline,
which makes it exactly the kind of claim that rots quietly - F-026 again, where
prose said 35 and the artefact said 33 for three days.

So it is pinned. If somebody fixes the unlinked-cell resolution, these tests go
red and say so, rather than the report continuing to disclose a limitation the
system no longer has.

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


def test_exactly_two_declared_subjects_reach_no_node(evidence, graph):
    """And ADR-030 adjudicated them: one real gap, one truncated filename.

    `isolde_fellgard_the_unforgiv` is the corpus's own filename truncation -
    `interrogation_record_concerning_isolde_fellgard_the_unforgiv.txt` - and the
    entity it names *does* have a node, reached under its full name. Only
    `halvard_cindervale` is genuinely absent.
    """
    _, missing = probe.declared_subjects(evidence, graph)
    assert [slug for slug, _ in missing] == [
        "halvard_cindervale",
        "isolde_fellgard_the_unforgiv",
    ]
    assert "isolde_fellgard_the_unforgiven" in graph.nodes
    assert "halvard_cindervale" not in graph.nodes


def test_one_infobox_row_names_an_entity_the_graph_does_not_hold(graph):
    """The cause, not just the symptom.

    `| Members | Halvard Cindervale; Voltaire Hollowmere; Orin Veyra |` carries
    no `[[links]]`, and an unlinked cell can only resolve against entities that
    own a wiki page. None of those three does, so the row yields no edge - and
    Halvard, unlike the other two, is named in no other infobox, so he gets no
    node at all.
    """
    silent = probe.silent_relation_rows(graph)
    naming = [(doc, field, lost) for doc, field, _, lost in silent if lost]
    assert naming == [
        ("wiki/the_ashen_vanguard.md", "Members", ["Halvard Cindervale"])
    ]


def test_the_other_two_members_are_nodes_by_another_route(graph):
    """So the row costs one node and three edges, not three nodes.

    Stated because the honest number depends on it: Voltaire and Orin exist
    because *other* pages name them in linked cells.
    """
    assert "voltaire_hollowmere" in graph.nodes
    assert "orin_veyra" in graph.nodes
    assert not any(
        e.document == "wiki/the_ashen_vanguard.md" and e.field_name == "Members"
        for e in graph.edges
    )


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
