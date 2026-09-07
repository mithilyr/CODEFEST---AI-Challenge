"""Tests for the query layer: resolution, routing, evidence sufficiency,
conflict detection, and the end-to-end engine.

Each dev 1B question is used exactly once, as CLAUDE.md's plan asks - as a
regression case for a *generic* mechanism, never as a hard-coded branch. Where
a scenario has no naturally occurring corpus example (no relation field is
ever abstained on in this corpus - all 24 abstentions are attribute fields),
the test says so and constructs a controlled fixture instead of skipping the
mechanism untested.
"""

from __future__ import annotations

import pytest

from src.graph.build import build_graph, load_relation_map
from src.graph.entities import canonical_key
from src.graph.traverse import walk_relations
from src.ingest.pipeline import ingest
from src.query.conflict import check_conflict
from src.query.engine import answer_question
from src.query.evidence import (
    EvidenceStatus,
    check_abstention,
    classify_traversal,
    filter_endpoints,
)
from src.query.resolve import EntityResolver, ResolutionStatus
from src.query.route import build_gazetteer, route
from src.settings import get_settings


@pytest.fixture(scope="module")
def evidence_units(corpus_root):
    return ingest().evidence


@pytest.fixture(scope="module")
def resolver(graph):
    return EntityResolver(graph)


@pytest.fixture(scope="module")
def gazetteer(graph, resolver):
    return build_gazetteer(graph, resolver)


# --------------------------------------------------------------------------
# Entity resolution
# --------------------------------------------------------------------------


def test_exact_resolution(resolver):
    result = resolver.resolve("Gravemaw Wyrm")
    assert result.status == ResolutionStatus.EXACT
    assert result.key == "gravemaw_wyrm"


def test_normalised_resolution_folds_case_and_article(resolver):
    """`canonical_key` is ADR-011's rule; this is that tier reused, not redone."""
    result = resolver.resolve("the iron-ring cartel")
    assert result.status == ResolutionStatus.NORMALISED
    assert result.key == "iron_ring_cartel"


def test_alias_resolution_drops_a_single_word_epithet(resolver):
    result = resolver.resolve("Cerys Sablewood")
    assert result.status == ResolutionStatus.ALIAS
    assert result.key == "cerys_sablewood_the_ashen"


def test_alias_resolution_drops_a_multi_word_epithet(resolver):
    """"the Last Warden" is two words; a naive single-word epithet rule misses it."""
    result = resolver.resolve("Aldous Wrenfield")
    assert result.status == ResolutionStatus.ALIAS
    assert result.key == "aldous_wrenfield_the_last_warden"


def test_alias_never_shadows_a_real_distinct_entity(graph):
    """A collision with a real node must drop the alias rather than guess.

    Constructed rather than corpus-found: no epithet base collides with a real
    node in the measured corpus, so the guard is proven directly against a
    graph built to collide. "Ederon Fellgard" is already a real, distinct node
    (the subject of `1b_007`); adding a rigged "Ederon Fellgard the Bold" must
    not hijack that name into an alias for the impostor.
    """
    from src.graph.schema import Node

    rigged = build_graph()
    rigged.add_node(Node(key="ederon_fellgard_the_bold", name="Ederon Fellgard the Bold"))
    resolver = EntityResolver(rigged)

    result = resolver.resolve("Ederon Fellgard")
    assert result.status == ResolutionStatus.EXACT  # the real node, untouched
    assert result.key == "ederon_fellgard"  # not the rigged "..._the_bold"


def test_ambiguous_fuzzy_match_never_auto_selects(resolver):
    """ADR-011's central measurement: Caedmon/Ederon Fellgard sit at 0.839 similarity.

    A typo close to a real name must return candidates, never a single guess -
    even when one candidate is an near-exact character match.
    """
    result = resolver.resolve("Caedmon Fellgardd")
    assert result.status == ResolutionStatus.AMBIGUOUS
    assert not result.resolved
    assert len(result.candidates) >= 2
    keys = {c.key for c in result.candidates}
    assert "caedmon_fellgard" in keys


def test_unresolved_mention_produces_no_candidates(resolver):
    result = resolver.resolve("Xyzzybold Nonexistentson")
    assert result.status == ResolutionStatus.UNRESOLVED
    assert result.candidates == ()
    assert not result.resolved


def test_escalation_is_never_invoked_unless_resolution_is_ambiguous(graph):
    calls = []

    def escalator(mention, candidates):
        calls.append((mention, candidates))
        return None

    resolver = EntityResolver(graph, escalator=escalator)
    resolver.resolve("Gravemaw Wyrm")  # exact - must not escalate
    assert calls == []
    assert resolver.escalation_count == 0

    resolver.resolve("Caedmon Fellgardd")  # ambiguous - must escalate
    assert len(calls) == 1
    assert resolver.escalation_count == 1


def test_escalation_accepting_a_candidate_resolves_the_mention(graph):
    """The hook may accept a candidate; absent a hook, ambiguity stays open."""
    resolver = EntityResolver(
        graph, escalator=lambda mention, candidates: candidates[0].key
    )
    result = resolver.resolve("Caedmon Fellgardd")
    assert result.status == ResolutionStatus.ESCALATED
    assert result.resolved


# --------------------------------------------------------------------------
# Question routing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question,template,chain,cardinality",
    [
        (
            "Whose dominion encompasses the lair of the Gravemaw Wyrm?",
            "lair_dominion",
            ("lair_in", "ruled_by"),
            "single",
        ),
        (
            "To which shadowed redoubt must one journey to examine the relic "
            "long borne by Cerys Sablewood the Ashen since 356 AS?",
            "relic_custody",
            ("wields", "housed_in"),
            "single",
        ),
        (
            "Which war was won by the organization that included Isolde "
            "Mournvale as one of its members?",
            "victory_membership",
            ("member_of", "victor_of"),
            "single",
        ),
        (
            "Which individual was a member of the faction that ultimately "
            "won the War of Drowned Light?",
            "victory_membership",
            ("victor_of", "member_of"),
            "any_of",
        ),
        (
            "In what way is Halvard Crowhurst connected to the victors of "
            "the Purge of Blackport?",
            "victor_connection",
            ("victor_of", "member_of"),
            "single",
        ),
    ],
)
def test_route_matches_the_expected_template(
    graph, resolver, gazetteer, question, template, chain, cardinality
):
    result = route(question, graph, resolver, gazetteer)
    assert result.template == template
    assert result.chain == chain
    assert result.cardinality == cardinality


def test_victory_membership_direction_is_read_from_entity_type_not_the_question():
    """Same trigger phrase, opposite chain order - decided by what was resolved.

    This is the mechanism, not the dev set: any character-shaped mention goes
    `member_of -> victor_of`; any conflict-shaped mention goes
    `victor_of -> member_of`. `1b_005`/`1b_022` and `1b_006` are two
    observations of one rule, not two branches of code.
    """
    graph = build_graph()
    resolver = EntityResolver(graph)
    gazetteer = build_gazetteer(graph, resolver)

    from_character = route(
        "Which war did Ravena Stormwell's own faction ultimately win?",
        graph, resolver, gazetteer,
    )
    from_conflict = route(
        "Which individual was a member of the faction that ultimately won "
        "the War of Drowned Light?",
        graph, resolver, gazetteer,
    )
    assert from_character.chain == ("member_of", "victor_of")
    assert from_conflict.chain == ("victor_of", "member_of")


def test_route_logs_a_miss_for_a_question_no_template_covers(graph, resolver, gazetteer):
    result = route("What color is the sky in the Ashen Era?", graph, resolver, gazetteer)
    assert result.__class__.__name__ == "RouteMiss"
    assert result.reason


def test_head_noun_extraction_matches_every_dev_1b_question():
    from src.query.route import head_noun

    assert head_noun("Which accord was ultimately won by the faction...") == "accord"
    assert head_noun("Which war was won by the organization...") == "war"
    assert head_noun(
        "To which shadowed redoubt must one journey to examine..."
    ) == "redoubt"
    assert head_noun("Which individual was a member of the faction...") == "individual"


# --------------------------------------------------------------------------
# Type-aware traversal (1b_007's critical requirement)
# --------------------------------------------------------------------------


def test_type_filter_selects_the_accord_among_three_genuine_victories(graph):
    """The Cartel really won all three; only one is an 'accord'.

    Not hard-coded: `filter_endpoints` never sees "Leaden Accord" as a
    literal - it is handed the word "accord" from the question and the graph's
    own `entity_type`/name data does the rest.
    """
    paths = walk_relations(graph, "Ederon Fellgard", ["member_of", "victor_of"])
    assert {graph.nodes[p.end].name for p in paths} == {
        "The Leaden Accord", "The Winter Reckoning", "The Purge of Blackport",
    }
    filtered, status = filter_endpoints(graph, paths, entity_type="conflict", word="accord")
    assert status == EvidenceStatus.SUFFICIENT
    assert {graph.nodes[p.end].name for p in filtered} == {"The Leaden Accord"}


def test_type_filter_falls_back_when_the_lexical_hint_matches_nothing(graph):
    """"redoubt" never appears in "Gloamreach" - the hint must not manufacture failure."""
    paths = walk_relations(graph, "Cerys Sablewood the Ashen", ["wields", "housed_in"])
    assert paths
    filtered, status = filter_endpoints(graph, paths, entity_type="location", word="redoubt")
    assert status == EvidenceStatus.SUFFICIENT
    assert {graph.nodes[p.end].name for p in filtered} == {"Gloamreach"}


def test_type_filter_is_permissive_to_untyped_endpoints(graph):
    """Most of `1b_006`'s fourteen answers are edge-only nodes with no recorded type.

    A strict-equality filter would silently drop them; the permissive rule -
    exclude only a *definite* mismatch - is what keeps all fourteen.
    """
    paths = walk_relations(graph, "The War of Drowned Light", ["victor_of", "member_of"])
    filtered, status = filter_endpoints(graph, paths, entity_type="character", word=None)
    assert status == EvidenceStatus.SUFFICIENT
    assert len(filtered) == len(paths)  # nothing dropped: unknown type is not a mismatch


def test_path_missing_attribute_when_both_filters_genuinely_exclude_everything(graph):
    """A type hint that truly matches nothing real is a named sufficiency state.

    Constructed: `walk_relations` on real data never lands on a candidate set
    where a real corpus type word eliminates everything, so a definite
    contradiction (`entity_type` mismatch) is forced deliberately.
    """
    paths = walk_relations(graph, "Ederon Fellgard", ["member_of", "victor_of"])
    filtered, status = filter_endpoints(graph, paths, entity_type="character", word=None)
    assert status == EvidenceStatus.PATH_MISSING_ATTRIBUTE
    assert filtered == []


# --------------------------------------------------------------------------
# Evidence sufficiency
# --------------------------------------------------------------------------


def test_relation_unavailable_when_the_first_hop_never_exists(graph):
    """Gravemaw Wyrm has no membership of anything - distinct from a chain
    that starts but does not complete."""
    paths = walk_relations(graph, "Gravemaw Wyrm", ["member_of", "victor_of"])
    status = classify_traversal(graph, "gravemaw_wyrm", ("member_of", "victor_of"), paths)
    assert status == EvidenceStatus.RELATION_UNAVAILABLE


def test_no_path_when_the_first_hop_exists_but_the_chain_does_not_complete(graph):
    """Ederon Coldwater is a member of House Morvain, which never records a victory."""
    key = canonical_key("Ederon Coldwater")
    assert graph.neighbours(key, "member_of"), "fixture assumption: hop 1 must exist"
    paths = walk_relations(graph, "Ederon Coldwater", ["member_of", "victor_of"])
    assert paths == []
    status = classify_traversal(graph, key, ("member_of", "victor_of"), paths)
    assert status == EvidenceStatus.NO_PATH


def test_abstention_is_detected_from_the_raw_infobox_row_even_though_it_yields_no_edge(
    graph, tmp_path
):
    """No relation field is ever abstained on in this corpus - all 24 abstentions
    are attribute fields (Founded, Forging date, ...). The mechanism is real
    and generic regardless, so it is proven with a controlled fixture: a copy
    of a real page with one relation cell replaced by the corpus's own
    abstention wording.
    """
    relation_map = load_relation_map()
    fake_wiki = tmp_path / "wiki"
    fake_wiki.mkdir()
    (fake_wiki / "gravemaw_wyrm.md").write_text(
        "# Gravemaw Wyrm (creature)\n\n"
        "## Infobox\n\n"
        "| Field | Value |\n|---|---|\n"
        "| Lair | Contested; consult the Annals and Codex |\n",
        encoding="utf-8",
    )
    quote = check_abstention(graph, tmp_path, "gravemaw_wyrm", "lair_in", relation_map)
    assert quote == "Contested; consult the Annals and Codex"


def test_abstention_is_none_when_the_field_is_simply_absent(graph, tmp_path):
    """Missing is not abstaining - only an explicit refusal counts."""
    relation_map = load_relation_map()
    fake_wiki = tmp_path / "wiki"
    fake_wiki.mkdir()
    (fake_wiki / "gravemaw_wyrm.md").write_text(
        "# Gravemaw Wyrm (creature)\n\n## Infobox\n\n| Field | Value |\n|---|---|\n",
        encoding="utf-8",
    )
    quote = check_abstention(graph, tmp_path, "gravemaw_wyrm", "lair_in", relation_map)
    assert quote is None


def test_repeated_field_names_keep_distinct_provenance_through_the_query_layer(graph):
    """F-018's fix must survive being read back by the query layer, not just the graph.

    `the_ashen_vanguard.md` carries three `Belligerent` rows; every edge built
    from them must still resolve to its own row and its own raw cell text.
    """
    edges = [
        e for e in graph.edges
        if e.document == "wiki/the_ashen_vanguard.md" and e.field_name == "Belligerent"
    ]
    assert len(edges) == 3
    assert len({e.row for e in edges}) == 3
    assert len({e.why() for e in edges}) == 3  # each explanation is distinguishable


def test_contextual_qualifier_survives_into_the_evidence_trail(graph):
    """A two-argument clause's qualifier ("fought ... for X") must be visible
    in the evidence, not silently dropped once the edge becomes part of a path."""
    edge = next(e for e in graph.edges if e.qualifier is not None)
    assert edge.qualifier in edge.raw  # the qualifier is drawn from the cell itself
    assert edge.why().count(edge.raw) == 1  # explanation quotes the raw cell verbatim


def test_provenance_is_reconstructable_for_every_hop_of_the_vertical_slice(graph):
    """Every hop of `1b_013` must point back to a document, field, row and raw
    cell - the "why do you believe this" requirement from `schema.py`."""
    paths = walk_relations(graph, "Gravemaw Wyrm", ["lair_in", "ruled_by"])
    assert len(paths) == 1
    for edge in paths[0].edges:
        assert edge.document and edge.field_name and edge.raw and edge.template
        assert edge.row >= 0 and edge.tier >= 1
        assert edge.document in edge.why()


# --------------------------------------------------------------------------
# Conflict detection: same-tier contradiction vs silence (critical for 1b_009)
# --------------------------------------------------------------------------


def test_same_tier_contradiction_is_detected_and_not_resolved_by_tier(graph):
    report = check_conflict(
        graph, get_settings().require_corpus(),
        subject_key="iron_ring_cartel", relation="victor_of", object_key="purge_of_blackport",
    )
    assert report.asserting_edges  # the Purge's own page names the Cartel victor
    assert report.denial is not None  # the Cartel's own page explicitly declines
    assert report.denial.tier == report.asserting_edges[0].tier  # both tier 2, wiki
    assert report.status == "unresolved_same_tier"
    assert report.must_surface


def test_silence_is_not_a_conflict(graph):
    """The Silent Choir's page never mentions victory at all for this war -
    that is silence, not a denial, and must not be reported as a contradiction.

    Same graph shape as `1b_009` (a belligerent_in edge on the faction's own
    page, a victor_of edge only on the conflict's page) - what differs is
    prose, and only prose, which is exactly what this module has to read to
    tell the two apart.
    """
    report = check_conflict(
        graph, get_settings().require_corpus(),
        subject_key="silent_choir", relation="victor_of",
        object_key=canonical_key("The War of Drowned Light"),
    )
    assert report.asserting_edges  # the war's own page names the Choir victor
    assert report.denial is None  # but the Choir's own page never disputes it
    assert report.status == "uncontested"
    assert not report.must_surface


# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# F-031 / ADR-029: a template must consume the whole question
# --------------------------------------------------------------------------


def test_a_template_declines_a_longer_question_containing_its_shape(
    graph, resolver, gazetteer
):
    """F-031: `victory_membership` matched the two-hop shape nested inside a
    three-hop question, walked from the wrong entity, and answered confidently.

    The correct answer is The War of Drowned Light by
    `mentor_of -> member_of -> victor_of`; the template returned The War of
    Endless Vigil, which is "which war did Hesper's OWN faction win".
    """
    from src.query.route import RouteMiss

    question = (
        "Which war was won by the faction that Hesper Wrenfield's mentor belongs to?"
    )
    result = route(question, graph, resolver, gazetteer)
    assert isinstance(result, RouteMiss)
    assert "mentor_of" in result.reason
    assert "F-031" in result.reason


def test_the_guard_ignores_cue_words_shared_across_relations(
    graph, resolver, gazetteer
):
    """MEASURED (ADR-029): guarding on the whole cue vocabulary declines three
    questions the templates answer correctly, because seven cue words are
    shared and several are ordinary nouns - "place" alone cues forged_at,
    housed_in and serves_at. Only a word naming exactly one relation counts."""
    from src.query.route import RouteResult, unique_relation_cues

    unique = unique_relation_cues()
    # NOT "military" any more. It was shared between serves_at ("Military
    # service") and belligerent_in ("Military action", "Military involvement",
    # "Military record") until ADR-034 moved `Military service` to
    # belligerent_in, where the verb in its one and only cell says it belongs:
    # `Fought for [[The Ashen Vanguard]] in [[The Leaden Accord]]`. All four
    # `Military *` field names now name one relation, so the word does too.
    for shared in ("plac", "conflict", "record", "major"):
        assert shared not in unique, f"{shared!r} names more than one relation"
    assert unique.get("military") == "belligerent_in"

    # rb_041: contains "place" and means nothing by it.
    result = route(
        "Which faction rules the place where the Pale Stag of Omens makes its lair?",
        graph,
        resolver,
        gazetteer,
    )
    assert isinstance(result, RouteResult)
    assert result.template == "lair_dominion"


def test_the_guard_leaves_every_dev_question_routed(graph, resolver, gazetteer):
    """The gate F-031 set for its own fix: if the dev 7/7 moves at all, revert."""
    import json

    from src.query.route import RouteResult

    key = json.load(open("eval/answer_key.json", encoding="utf-8"))["questions"]
    dev_1b = [q for q in key if q["qid"].startswith("1b_")]
    assert len(dev_1b) == 7
    for entry in dev_1b:
        result = route(entry["question"], graph, resolver, gazetteer)
        assert isinstance(result, RouteResult), (
            f"{entry['qid']} lost its template route: {getattr(result, 'reason', '')}"
        )


# End-to-end: the engine, all seven dev 1B questions
# --------------------------------------------------------------------------


def test_1b_013_vertical_slice_end_to_end(graph):
    """The exact deliverable: answer, both hops, evidence, sources, status."""
    answer = answer_question(
        "Whose dominion encompasses the lair of the Gravemaw Wyrm?", graph
    )
    assert answer.status == EvidenceStatus.SUFFICIENT
    assert answer.values == ("The Bleeding Crown",)
    assert len(answer.paths) == 1
    assert [e.relation for e in answer.paths[0].edges] == ["lair_in", "ruled_by"]
    assert set(answer.documents) == {
        "wiki/gravemaw_wyrm.md", "wiki/marrowwell_abbey.md",
    }
    for edge in answer.paths[0].edges:
        assert edge.document and edge.field_name and edge.raw


def test_1b_005_reverse_traversal(graph):
    answer = answer_question(
        "Which war was won by the organization that included Isolde "
        "Mournvale as one of its members?",
        graph,
    )
    assert answer.status == EvidenceStatus.SUFFICIENT
    assert answer.values == ("The War of Drowned Light",)
    assert answer.conflict is None  # this template never runs the conflict check


def test_1b_022_generalises_the_same_mechanism_to_a_different_character(graph):
    answer = answer_question(
        "Which war did Ravena Stormwell's own faction ultimately win?", graph
    )
    assert answer.status == EvidenceStatus.SUFFICIENT
    assert answer.values == ("The War of Drowned Light",)


def test_1b_007_type_filter_end_to_end(graph):
    answer = answer_question(
        "Which accord was ultimately won by the faction of which Ederon "
        "Fellgard is a member?",
        graph,
    )
    assert answer.status == EvidenceStatus.SUFFICIENT
    assert answer.values == ("The Leaden Accord",)
    # Both corroborating documents (ADR-016) must survive into the answer.
    assert set(answer.documents) >= {
        "wiki/ederon_fellgard.md", "wiki/the_iron_ring_cartel.md",
    }


def test_1b_003_qualified_custody_chain(graph):
    answer = answer_question(
        "To which shadowed redoubt must one journey to examine the relic "
        "long borne by Cerys Sablewood the Ashen since 356 AS?",
        graph,
    )
    assert answer.status == EvidenceStatus.SUFFICIENT
    assert answer.values == ("Gloamreach",)


def test_1b_006_multi_valued_answer_is_not_forced_to_one(graph):
    answer = answer_question(
        "Which individual was a member of the faction that ultimately won "
        "the War of Drowned Light?",
        graph,
    )
    assert answer.status == EvidenceStatus.SUFFICIENT
    assert len(answer.values) == 14
    assert "Brannoc Palefroth" in answer.values
    assert "Ravena Stormwell" in answer.values


def test_1b_009_surfaces_membership_and_the_disputed_victor_status(graph):
    answer = answer_question(
        "In what way is Halvard Crowhurst connected to the victors of the "
        "Purge of Blackport?",
        graph,
    )
    assert answer.status == EvidenceStatus.CONFLICTING_EVIDENCE
    assert answer.values == ("Halvard Crowhurst",)  # membership is uncontested
    assert answer.conflict.must_surface
    assert answer.conflict.denial is not None


def test_explicit_abstention_via_the_engine(tmp_path):
    """End-to-end: a routed question whose first hop is abstained, not absent.

    Uses a minimal synthetic graph rather than the real corpus graph: the
    real graph already has the true `lair_in` edge, which would make the
    traversal succeed regardless of what `corpus_path` points at (the graph's
    edges, not the raw files, drive traversal). Abstention only becomes
    visible when the edge genuinely is not there - exactly the situation
    `cells.py` produces for a real abstained cell (it yields no edge).
    """
    from src.graph.schema import Graph, Node

    synthetic = Graph()
    synthetic.add_node(
        Node(key="gravemaw_wyrm", name="Gravemaw Wyrm", entity_type="creature",
             page="wiki/gravemaw_wyrm.md")
    )

    relation_map = load_relation_map()
    fake_wiki = tmp_path / "wiki"
    fake_wiki.mkdir()
    (fake_wiki / "gravemaw_wyrm.md").write_text(
        "# Gravemaw Wyrm (creature)\n\n## Infobox\n\n"
        "| Field | Value |\n|---|---|\n"
        "| Lair | Contested; consult the Annals and Codex |\n",
        encoding="utf-8",
    )
    answer = answer_question(
        "Whose dominion encompasses the lair of the Gravemaw Wyrm?",
        synthetic,
        corpus_path=tmp_path,
        relation_map=relation_map,
    )
    assert answer.status == EvidenceStatus.ABSTENTION
    assert "Contested" in answer.note


def test_outside_structured_coverage_vs_unresolved_entity(graph, evidence_units):
    """Something real but outside the graph, versus a name that is nowhere.

    The fixture used to be Halvard Cindervale. It is not any more, and the
    reason is the point of ADR-032: he had no node because of a defect (F-032),
    not because the corpus put him beyond the graph's reach. `Court Chronicler`
    is the honest article - an in-world office the wiki itself wikilinks, named
    in all four collections, and not one of the six categories a node is typed
    with. The graph legitimately does not hold it.
    """
    real_but_uncovered = answer_question(
        "Which war was won by the organization that included Court "
        "Chronicler as one of its members?",
        graph,
        evidence_units=evidence_units,
    )
    assert real_but_uncovered.status == EvidenceStatus.OUTSIDE_STRUCTURED_COVERAGE

    truly_unknown = answer_question(
        "Which war was won by the organization that included Xyzzybold "
        "Nonexistentson as one of its members?",
        graph,
        evidence_units=evidence_units,
    )
    assert truly_unknown.status == EvidenceStatus.UNRESOLVED_ENTITY


def test_the_vanguard_membership_row_now_answers(graph, evidence_units):
    """ADR-032's user-visible gain, pinned.

    `| Members | Halvard Cindervale; Voltaire Hollowmere; Orin Veyra |` on
    `the_ashen_vanguard.md` is unlinked, and until ADR-032 it built nothing, so
    this question declined with `outside_structured_coverage`. It now answers.
    If somebody narrows the name lexicon again, this goes red before the
    reachability probe does.
    """
    answer = answer_question(
        "Which war was won by the organization that included Halvard "
        "Cindervale as one of its members?",
        graph,
        evidence_units=evidence_units,
    )
    assert answer.status == EvidenceStatus.SUFFICIENT
    assert "halvard_cindervale" in graph.nodes


def test_no_template_match_is_logged_not_guessed(graph):
    answer = answer_question("What color is the sky in the Ashen Era?", graph)
    assert answer.status == EvidenceStatus.NO_TEMPLATE_MATCH
    assert answer.note


def test_unresolvable_entity_in_a_routed_question_returns_no_path_rather_than_guessing(graph):
    """ADR-011 end to end: a near-miss spelling must never silently traverse."""
    answer = answer_question(
        "Whose dominion encompasses the lair of the Caedmon Fellgardd?", graph
    )
    assert not answer.status.is_answerable


# -- a cue word inside an entity's own name is part of the name (F-035) ------


def test_a_cue_word_inside_an_entity_name_is_not_a_relation_request(graph):
    """MEASURED: "Who is House Morvain?" cued `housed_in` and "Who is Embercrag
    Fortress?" cued `serves_at`, both from a word in the entity's *name*. The
    router chased a relation nobody asked for, found no path, and declined."""
    from src.graph.build import load_relation_map
    from src.query.fallback import route_by_cues

    relations = load_relation_map()
    for name in ("House Morvain", "Embercrag Fortress"):
        result = route_by_cues(graph, f"Who is {name}?", relations)
        assert result.cued == (), f"{name}: phantom cue {result.cued}"
        assert result.profile, f"{name}: an identity question must yield a profile"


def test_every_entity_the_front_page_lists_leads_to_an_answer(graph):
    """The entity list offers 118 links; each must go somewhere.

    Two were dead before F-035 and seven more answered through cue routing
    instead of the profile path - a relation-routed reply to an identity
    question, which is a different question than the one asked.
    """
    from src.query.evidence import EvidenceStatus

    statuses = {}
    for node in graph.nodes.values():
        answer = answer_question(f"Who is {node.name}?", graph, use_planner=False)
        statuses.setdefault(answer.status, []).append(node.name)

    assert set(statuses) == {EvidenceStatus.PROFILE}, {
        status.value: names[:5] for status, names in statuses.items()
    }


def test_masking_removes_the_name_and_nothing_else(graph):
    from src.query.fallback import find_mentions, tokens_outside_mentions

    question = "Which region is Embercrag Fortress in?"
    mentions = find_mentions(graph, question)
    remaining = tokens_outside_mentions(question, mentions)

    assert "embercrag" not in remaining and "fortress" not in remaining
    assert "region" in remaining, "the actual relation word must survive"


def test_a_relation_named_outside_the_entity_name_still_cues(graph):
    """The mask must not disarm the router - only the name is removed."""
    from src.graph.build import load_relation_map
    from src.query.fallback import route_by_cues

    result = route_by_cues(
        graph, "Which region is Embercrag Fortress in?", load_relation_map()
    )
    assert "in_region" in result.cued
    assert result.answered
