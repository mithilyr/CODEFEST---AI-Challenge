"""Tests for the deterministic graph layer.

Most of these pin a measured corpus fact or guard a specific way of inventing an
edge. The cell-parser cases in particular are chosen because each one is a
plausible wrong parse that produces a confident, well-cited, wrong answer - the
failure class this project exists to prevent.

Tests needing the corpus skip cleanly when it is absent.
"""

from __future__ import annotations

import collections

import pytest

from src.graph.build import build_graph, infobox_rows, load_relation_map
from src.graph.cells import parse_cell
from src.graph.entities import canonical_key, slugify
from src.graph.traverse import find_paths
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


# --------------------------------------------------------------------------
# Entity resolution (ADR-011) - no corpus needed
# --------------------------------------------------------------------------


def test_leading_article_is_dropped_so_alias_divergence_joins():
    """1b_009 depends on this: the purge page omits the article."""
    assert canonical_key("[[Iron-Ring Cartel]]".strip("[]")) == canonical_key(
        "The Iron-Ring Cartel"
    )


def test_similar_but_distinct_entities_never_collapse():
    """caedmon/ederon Fellgard are 0.839 similar and must stay two nodes."""
    assert canonical_key("Caedmon Fellgard") != canonical_key("Ederon Fellgard")
    assert canonical_key("Gloamreach") != canonical_key("Gloammarch")
    assert canonical_key("Greyfell Citadel") != canonical_key("Ironfell Citadel")


def test_curly_apostrophes_fold_to_one_key():
    assert slugify("Halvard’s Oath") == slugify("Halvard's Oath")


# --------------------------------------------------------------------------
# Cell parsing (ADR-010) - the twelve templates, and the ways to invent an edge
# --------------------------------------------------------------------------


def test_bare_link_yields_one_edge():
    cell = parse_cell("[[Marrowwell Abbey]]")
    assert cell.template == "bare link"
    assert [r.target for r in cell.references] == ["Marrowwell Abbey"]


def test_entity_name_with_one_word_linked_is_not_an_edge():
    """`The Purge of [[Blackport]]` is a name, not a relation to Blackport.

    A short leading phrase looks exactly like a relation verb, which is why the
    verb set is closed and measured rather than inferred from length.
    """
    cell = parse_cell("The Purge of [[Blackport]]")
    assert cell.template == "prose containing an incidental link"
    assert not cell.yields_edges


def test_description_containing_a_link_is_not_an_edge():
    cell = parse_cell("Regalia bearing the name [[The Thrice-Bound Edge]]")
    assert not cell.yields_edges

    cell = parse_cell(
        "Hardened visual identity of a garrisoned settlement in the [[Ash Wastes]]"
    )
    assert not cell.yields_edges


def test_two_argument_clause_is_one_ternary_fact_not_two_edges():
    """`Fought in X for Y` must not assert "belligerent in Y"."""
    cell = parse_cell(
        "[[Voltaire Hollowmere]], fighting for [[The Ashen Vanguard]]",
        link_types={"voltaire_hollowmere": "character", "ashen_vanguard": "faction"},
    )
    assert cell.template == "two-argument clause"
    assert len(cell.references) == 1
    assert cell.references[0].qualifier == "The Ashen Vanguard"


def test_two_argument_arguments_are_assigned_by_type_not_position():
    """Both word orders occur, so position cannot decide which is the conflict."""
    types = {"purge_of_blackport": "conflict", "house_morvain": "faction"}
    a = parse_cell(
        "Fought in [[The Purge of Blackport]] for [[House Morvain]]", link_types=types
    )
    b = parse_cell(
        "Fought for [[House Morvain]] in [[The Purge of Blackport]]", link_types=types
    )
    assert a.references[0].target == b.references[0].target == "The Purge of Blackport"
    assert a.references[0].qualifier == b.references[0].qualifier == "House Morvain"


def test_since_qualifier_lands_on_the_edge_not_in_the_node_name():
    """1b_003 asks about the qualifier; gluing it to the node joins to nothing."""
    cell = parse_cell("[[The Cinder-Wrought Aegis]], since 356 AS")
    assert cell.template == "link + since-qualifier"
    reference = cell.references[0]
    assert reference.target == "The Cinder-Wrought Aegis"
    assert (reference.year, reference.year_kind) == (356, "since")


def test_abstention_is_recorded_not_treated_as_missing():
    cell = parse_cell("Contested; consult the Annals and Codex")
    assert cell.is_abstention
    assert not cell.yields_edges


def test_multi_valued_cell_splits_into_several_references():
    cell = parse_cell("[[The Winter Reckoning]]; [[The Leaden Accord]]")
    assert cell.template == "link list"
    assert len(cell.references) == 2


def test_every_corpus_cell_falls_into_the_twelve_templates(corpus_root):
    """ADR-010's closed set, re-derived. 651 cells, no residue."""
    from eval.probes.corpus_shape import wiki_pages

    counts = collections.Counter()
    for _, text in wiki_pages(corpus_root):
        for _, value in infobox_rows(text):
            counts[parse_cell(value).template] += 1

    assert sum(counts.values()) == 651
    assert len(counts) == 12
    assert counts["bare link"] == 181
    assert counts["two-argument clause"] == 11
    assert counts["abstention"] == 24


# --------------------------------------------------------------------------
# Construction and provenance
# --------------------------------------------------------------------------


def test_every_field_name_is_mapped_or_declared_an_attribute(graph):
    """An unmapped field is a relation that silently never becomes an edge."""
    assert graph.unmapped_fields == {}


def test_repeated_field_names_produce_one_edge_each(graph):
    """F-018: `fields[name] = value` would keep one of three Belligerent rows."""
    edges = [
        e
        for e in graph.edges
        if e.document == "wiki/the_ashen_vanguard.md"
        and e.field_name == "Belligerent"
    ]
    assert len(edges) == 3
    assert len({e.row for e in edges}) == 3, "row index is what keeps them apart"


def test_every_edge_carries_enough_provenance_to_be_audited(graph):
    for edge in graph.edges:
        assert edge.document and edge.field_name and edge.template
        assert edge.raw.strip()
        assert edge.tier > 0
        assert edge.row >= 0
        assert edge.assertion in {"asserts", "denies", "secret"}


def test_graph_records_entities_that_have_no_page(graph):
    """Roughly a fifth of entities exist only as link targets."""
    assert graph.edge_only
    assert len(graph.page_backed) == 95


# --------------------------------------------------------------------------
# Traversal
# --------------------------------------------------------------------------


def test_1b_013_resolves_in_two_hops_with_both_documents(graph):
    """The end-to-end smoke test: cleanest two-hop in the dev set."""
    paths = find_paths(graph, "Gravemaw Wyrm", "The Bleeding Crown", max_hops=3)
    assert len(paths) == 1
    path = paths[0]
    assert [e.relation for e in path.edges] == ["lair_in", "ruled_by"]
    assert set(path.documents) == {
        "wiki/gravemaw_wyrm.md",
        "wiki/marrowwell_abbey.md",
    }


def test_traversal_returns_alternative_routes_not_just_the_first(graph):
    """Regression: a per-search `seen` set returned only one 2-hop route.

    For 1b_009 it kept the `belligerent_in` path and discarded the `victor_of`
    one - same length, but sourced from a single document instead of the two the
    question needs. A path existing is not the evidence existing.
    """
    paths = find_paths(graph, "The Purge of Blackport", "Halvard Crowhurst", max_hops=2)
    relations = {p.edges[0].relation for p in paths}
    assert {"victor_of", "belligerent_in"} <= relations

    victor = next(p for p in paths if p.edges[0].relation == "victor_of")
    assert set(victor.documents) == {
        "wiki/the_purge_of_blackport.md",
        "wiki/the_iron_ring_cartel.md",
    }


def test_traversal_is_bidirectional(graph):
    """The Silent Choir does not record its own victories; the conflict does."""
    assert find_paths(graph, "The Bleeding Crown", "Gravemaw Wyrm", max_hops=3)


def test_unresolvable_entity_returns_no_path_rather_than_guessing(graph):
    """ADR-011: never silently pick a near neighbour."""
    assert find_paths(graph, "Caedmon Fellgardd", "The Iron-Ring Cartel") == []


def test_relation_map_loads_and_covers_the_core_relations():
    relations = load_relation_map()
    assert relations.lookup("Membership") == ("member_of", "forward")
    assert relations.lookup("Members") == ("member_of", "reverse")
    assert relations.lookup("Ruled by") == ("ruled_by", "forward")
    assert relations.lookup("Appearance") is None
