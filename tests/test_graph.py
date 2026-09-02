"""Tests for the deterministic graph layer.

Most of these pin a measured corpus fact or guard a specific way of inventing an
edge. The cell-parser cases in particular are chosen because each one is a
plausible wrong parse that produces a confident, well-cited, wrong answer - the
failure class this project exists to prevent.

Tests needing the corpus skip cleanly when it is absent.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path


from src.graph.build import infobox_rows, load_relation_map
from src.graph.cells import parse_cell
from src.graph.entities import canonical_key, display_name, slugify
from src.graph.traverse import find_paths, walk_relations


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


# --------------------------------------------------------------------------
# Direction: the cell's own verb outranks the field name (ADR-023)
# --------------------------------------------------------------------------


def test_cell_verb_outranks_a_contradicting_field_name(relations):
    """MEASURED: `| Mentor | Mentor of [[X]] |` occurs 3x and config maps
    `Mentor` as reverse. The cell says the subject IS the mentor."""
    assert relations.lookup("Mentor") == ("mentor_of", "reverse")
    assert relations.states_forward("Mentor of [[Ignatz Marrowgate]]", "mentor_of")


def test_a_bare_link_under_a_reverse_field_stays_reverse(relations):
    """The override must not fire on the 23 reverse edges that are correct.
    `| Victor | [[The Ashen Vanguard]] |` on a conflict page really is reverse."""
    assert not relations.states_forward("[[The Ashen Vanguard]]", "victor_of")
    assert not relations.states_forward("[[Halvard Crowhurst]]", "member_of")


def test_a_cell_verb_naming_another_relation_does_not_override(relations):
    """Narrowness is the point: only a verb naming the SAME relation flips it."""
    assert not relations.states_forward("Wields the [[Hollow Edge]]", "member_of")


def test_mentor_edges_run_from_mentor_to_apprentice(graph):
    """rb_044's gold path is Ashgrove -> Marrowgate; we had it backwards."""
    pairs = {(e.source, e.target) for e in graph.edges if e.relation == "mentor_of"}
    assert ("ignatz_ashgrove_the_oathless", "ignatz_marrowgate") in pairs
    assert ("ignatz_marrowgate", "ignatz_ashgrove_the_oathless") not in pairs
    assert ("maelis_harrowick_the_pale", "ignatz_marrowgate") in pairs
    assert ("morwenna_ashgrove", "caedmon_fellgard") in pairs
    assert not any(e.inferred_inverse for e in graph.edges if e.relation == "mentor_of")


def test_direction_overrides_are_counted_not_absorbed(graph):
    """A silent flip is what caused the bug; the count is the audit trail."""
    assert graph.direction_overrides == {"Mentor -> mentor_of": 3}


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


# --------------------------------------------------------------------------
# Display names (F-021)
#
# Node keys were always correct - `slugify` collapses brackets to `_` and trims -
# so this defect was invisible to traversal and surfaced only where a name is
# read by a human or matched against text. That is exactly the UI evidence trail
# and the query layer's entity linker, which is how it was found: deterministic
# linking resolved 4 of 7 dev 1B questions, and the three misses were entities
# whose names carried `[[ ]]`.
# --------------------------------------------------------------------------


def test_display_name_strips_wiki_link_markup():
    """32 of 117 node names carried brackets, because `Name` rows are links."""
    assert display_name("[[Cerys Sablewood the Ashen]]") == "Cerys Sablewood the Ashen"


def test_display_name_strips_emphasis():
    """The ephemera wrap values in `**`; a name must not inherit them."""
    assert display_name("**The Leaden Accord**") == "The Leaden Accord"


def test_display_name_strips_the_type_disambiguator():
    """26 of 95 H1 headings carry one, e.g. `# Ashfall Colossus (creature)`."""
    assert display_name("Ashfall Colossus (creature)") == "Ashfall Colossus"


def test_display_name_handles_a_suffix_inside_the_brackets():
    """The ordering bug this test exists for.

    A heading is written `# [[Mournwatch]] (location)`, so the disambiguator sits
    *between* the name and its closing brackets. Stripping markup first leaves
    the trailing `]]` no longer at the end of the string, and removing the suffix
    afterwards orphans it - producing `Mournwatch]]`. Suffix must come first.
    """
    assert display_name("[[Mournwatch]] (location)") == "Mournwatch"


def test_display_name_leaves_a_real_name_alone():
    """Stripping must not eat hyphens, articles or capitals."""
    assert display_name("The Iron-Ring Cartel") == "The Iron-Ring Cartel"


def test_type_suffix_must_be_stripped_before_the_key_is_derived():
    """Otherwise 26 pages split into two nodes each.

    `canonical_key("Ashfall Colossus (creature)")` is `ashfall_colossus_creature`,
    which no `[[Ashfall Colossus]]` link would ever resolve to.
    """
    assert canonical_key(display_name("Ashfall Colossus (creature)")) == canonical_key(
        "[[Ashfall Colossus]]"
    )


def test_no_node_name_carries_markup(graph):
    """A name reaching the UI with `[[ ]]` in it is a citation we cannot show."""
    dirty = [n.name for n in graph.nodes.values() if any(c in n.name for c in "[]*|")]
    assert dirty == [], f"{len(dirty)} node name(s) carry markup: {dirty[:5]}"


def test_subject_name_prefers_the_heading_over_the_filename(graph):
    """`the_iron_ring_cartel.md` has no `Name` row at all.

    It previously fell through to the de-slugged filename and became "the iron
    ring cartel", losing both the capitals and the hyphen the corpus writes. The
    H1 heading is the only source that preserves them, and all 95 wiki pages
    have one.
    """
    assert graph.nodes["iron_ring_cartel"].name == "The Iron-Ring Cartel"


def test_every_dev_1b_question_links_at_least_one_entity(graph):
    """Deterministic entity linking, measured on the questions that matter.

    Exact substring match of a known node name against the question text. This
    was 4/7 while names carried markup; the three misses were Cerys Sablewood
    the Ashen, Isolde Mournvale and Ravena Stormwell, all bracketed.
    """
    key = json.loads(
        (Path(__file__).resolve().parent.parent / "eval" / "answer_key.json").read_text(
            encoding="utf-8"
        )
    )
    names = [n.name for n in graph.nodes.values()]

    unlinked = []
    for question in key["questions"]:
        if question["track"] != "1B":
            continue
        text = question["question"].lower()
        if not any(name.lower() in text for name in names):
            unlinked.append(question["qid"])

    assert unlinked == [], f"no entity linked for {unlinked}"


# --------------------------------------------------------------------------
# Relation-sequence traversal
#
# The measurement behind this: an unconstrained two-hop search returns 5-87
# candidates per dev 1B question, and the shortest path landing on the right
# answer is often wrong about why it got there.
# --------------------------------------------------------------------------


def test_walk_follows_the_named_relation_not_a_shorter_wrong_one(graph):
    """The failure this function exists to prevent.

    Isolde Mournvale is in The Silent Choir, which both *fought in* and *won*
    The War of Drowned Light. Two two-hop routes reach the same node, and an
    unconstrained search returns the `belligerent_in` one. Fighting in a war is
    not winning it, so an answer citing that edge is unsupported even though the
    endpoint is right.
    """
    won = walk_relations(graph, "Isolde Mournvale", ["member_of", "victor_of"])
    assert {graph.nodes[p.end].name for p in won} == {"The War of Drowned Light"}
    assert [e.relation for e in won[0].edges] == ["member_of", "victor_of"]


def test_walk_traverses_reverse_edges(graph):
    """The Silent Choir records no victories of its own.

    Its `victor_of` edge is written on the conflict's page, so this hop is a
    reverse lookup - the capability similarity search lacks and sub-track 1B is
    about. Constraining the relation must not accidentally constrain direction.
    """
    victor_edge = next(
        e
        for e in graph.out_edges("silent_choir", "victor_of")
        if e.document == "wiki/the_war_of_drowned_light.md"
    )
    assert victor_edge.document != "wiki/the_silent_choir.md"
    assert walk_relations(graph, "Ravena Stormwell", ["member_of", "victor_of"])


def test_walk_returns_every_endpoint_for_a_set_valued_question(graph):
    """1b_006 has 14 valid answers and the walk must not silently pick one."""
    members = walk_relations(
        graph, "The War of Drowned Light", ["victor_of", "member_of"]
    )
    names = {graph.nodes[p.end].name for p in members}
    assert len(names) > 5
    assert "Brannoc Palefroth" in names


def test_walk_keeps_corroborating_edges_between_the_same_pair(graph):
    """The Cartel's win of the Leaden Accord is asserted on both pages.

    Deduplicating by endpoint would discard the second assertion, which is
    exactly the corroboration the conflict layer needs to weigh.
    """
    paths = walk_relations(graph, "Ederon Fellgard", ["member_of", "victor_of"])
    to_accord = [p for p in paths if graph.nodes[p.end].name == "The Leaden Accord"]
    documents = {p.edges[-1].document for p in to_accord}
    assert len(documents) == 2, documents


def test_walk_returns_empty_when_the_shape_does_not_apply(graph):
    """Distinct from an unknown entity, and the sufficiency layer needs both."""
    assert walk_relations(graph, "Gravemaw Wyrm", ["member_of", "victor_of"]) == []
    assert walk_relations(graph, "No Such Entity", ["member_of"]) == []


def test_walk_narrows_candidates_far_below_an_unconstrained_search(graph):
    """5-87 candidates unconstrained; 1-14 constrained. Measured on 1b_007."""
    unconstrained = find_paths(graph, "Ederon Fellgard", max_hops=2)
    constrained = walk_relations(graph, "Ederon Fellgard", ["member_of", "victor_of"])
    assert len(constrained) < len(unconstrained) / 3
    assert {graph.nodes[p.end].name for p in constrained} == {
        "The Leaden Accord",
        "The Purge of Blackport",
        "The Winter Reckoning",
    }


def test_every_hop_carries_auditable_provenance(graph):
    """An edge that cannot explain itself is a citation we cannot defend."""
    path = walk_relations(graph, "Gravemaw Wyrm", ["lair_in", "ruled_by"])[0]
    for edge in path.edges:
        assert edge.document and edge.field_name and edge.raw and edge.template
        assert edge.row >= 0 and edge.tier >= 1
        assert edge.document in edge.why()
