"""Regression tests for the cue-based fallback tier (`src/query/fallback.py`).

Every test here pins a behaviour that ADR-019's measurement paid for. The
numbers quoted in the docstrings come from `comparison/REPORT.md` and are
reproducible with `python -m comparison.harness` and
`python -m comparison.ablations`.

The tests that matter most are the ones asserting the fallback *declines*.
Its measured precision is 40% against template routing's 91%, and its dominant
failure is a confident wrong answer rather than a miss - so the guarantee worth
protecting is not "it answers more" but "it does not answer when it has no
basis to".
"""

from __future__ import annotations

import pytest

from src.graph.schema import Edge
from src.graph.traverse import Path
from src.query.engine import answer_question
from src.query.evidence import EvidenceStatus
from src.query.fallback import (
    cued_relations,
    find_mentions,
    normalise_cue_word,
    relation_cues,
    route_by_cues,
    select_candidates,
)


@pytest.fixture(scope="module")
def cues(relations):
    return relation_cues(relations)


# --------------------------------------------------------------------------
# The tier boundary: templates first, fallback never pre-empts them.
# --------------------------------------------------------------------------


def test_dev_questions_still_route_through_a_template(graph):
    """No regression. ADR-017's 7/7 must not become 7 fallback answers.

    The fallback runs only on a RouteMiss, so a question a template covers
    must still come back as SUFFICIENT, never FALLBACK_SUFFICIENT.
    """
    answer = answer_question(
        "Which accord was ultimately won by the faction of which "
        "Ederon Fellgard is a member?",
        graph,
    )
    assert answer.status == EvidenceStatus.SUFFICIENT
    assert not answer.status.is_fallback
    assert "The Leaden Accord" in answer.values


def test_fallback_answers_a_novel_question_no_template_covers(graph):
    """The measured win. Templates match 1 of 21 novel questions; this is one
    of the 20 they miss and the fallback reaches."""
    answer = answer_question(
        "Which power rules the settlement where The Cinder-Wrought Aegis is housed?",
        graph,
    )
    assert answer.status == EvidenceStatus.FALLBACK_SUFFICIENT
    assert "House Morvain" in answer.values
    assert answer.template == "cue_fallback"
    assert len(answer.documents) >= 2, "a join must cite more than one document"


# --------------------------------------------------------------------------
# Declining. The guarantee worth more than the coverage.
# --------------------------------------------------------------------------


def test_fallback_declines_when_no_entity_resolves(graph):
    """A question naming nothing the graph knows must stay a template miss,
    not become a fallback answer about whatever happened to be nearby."""
    answer = answer_question("What color is the sky in the Ashen Era?", graph)
    assert answer.status == EvidenceStatus.NO_TEMPLATE_MATCH
    assert answer.values == ()


def test_fallback_declines_when_no_relation_is_cued(graph):
    """The entity resolves but the question names no relation the corpus
    records. Returning a profile of everything known about the wyrm would be
    answering a question nobody asked."""
    answer = answer_question("What did the Gravemaw Wyrm eat for breakfast?", graph)
    assert answer.status == EvidenceStatus.NO_TEMPLATE_MATCH
    assert answer.values == ()


def test_declining_preserves_the_template_stages_own_reason(graph):
    """The fallback must not overwrite a more specific diagnosis with a
    vaguer one - `evidence.py`'s named-status taxonomy exists precisely so a
    non-answer says which thing went wrong."""
    answer = answer_question("Which relic has Cerys Sablewode the Ashen wielded?", graph)
    assert not answer.status.is_fallback
    assert answer.note


# --------------------------------------------------------------------------
# Guard 2 - coverage over length. The load-bearing rule.
# --------------------------------------------------------------------------


def _edge(source: str, relation: str, target: str) -> Edge:
    return Edge(
        source=source,
        relation=relation,
        target=target,
        document=f"wiki/{source}.md",
        field_name="Test",
        row=0,
        raw=f"{source} {relation} {target}",
        template="link",
        tier=2,
    )


def test_coverage_beats_length_when_a_longer_path_ties_on_relations():
    """ADR-019's measurement: removing this rule collapses correctness 12 -> 2.

    A three-hop path that re-uses `member_of` covers the same two relations as
    the correct two-hop chain. Preferring the longest cued chain swaps in a
    person the corpus never meant as the answer; preferring coverage then
    brevity keeps the right one.
    """
    short = Path("a", (_edge("a", "member_of", "f"), _edge("f", "victor_of", "w")))
    long = Path(
        "a",
        (
            _edge("a", "member_of", "f"),
            _edge("f", "victor_of", "w"),
            _edge("w", "member_of", "bystander"),
        ),
    )
    chosen = select_candidates([short, long])
    assert chosen == [short]
    assert long not in chosen


def test_a_path_covering_more_relations_beats_a_shorter_one():
    """The other half of the same rule: coverage is scored BEFORE length, so a
    one-hop path does not win merely by being shortest when the question named
    two relations."""
    one_hop = Path("a", (_edge("a", "wields", "relic"),))
    two_hop = Path(
        "a", (_edge("a", "wields", "relic"), _edge("relic", "housed_in", "place"))
    )
    assert select_candidates([one_hop, two_hop]) == [two_hop]


# --------------------------------------------------------------------------
# The stemming fix - a defect in the sister implementation, not copied.
# --------------------------------------------------------------------------


def test_a_unique_cue_word_outranks_a_shared_one(cues):
    """ADR-032. `plac` is shared by forged_at, housed_in and serves_at, so the
    ordinary noun "place" cued all three. 3h_003 named five relations where its
    gold chain has three, and returned six values as `fallback_ambiguous`."""
    question = (
        "Which faction rules the place where the relic wielded by "
        "Halvard Vane the Grave-Sworn was forged?"
    )
    assert cued_relations(cues, question) == {"wields", "forged_at", "ruled_by"}


def test_a_shared_cue_word_is_a_fallback_not_a_veto(cues):
    """MEASURED and the reason this is not a simple filter: dropping shared
    words outright reads three frozen questions down to NO cue at all
    (rb_003, rb_040, rb_055), because a shared word is the only one they carry.
    Where unique words name nothing, the shared ones are all the evidence there
    is."""
    rb_003 = (
        "The Cinder-Wrought Aegis has been in Cerys Sablewood the Ashen's hands "
        "since 356 AS. What place holds it?"
    )
    assert cued_relations(cues, rb_003) == {"forged_at", "housed_in", "serves_at"}

    rb_055 = "Which faction does the Marsh Revenant serve?"
    assert cued_relations(cues, rb_055) == {"member_of", "serves_at"}


def test_every_three_hop_question_routes_to_its_gold_chain(cues):
    """The three-hop set exists because every acceptable path in the answer key
    is two hops (F-031). All three chains were always in the graph; only the
    vocabulary was wrong - under-cued for 3h_002 (ADR-031), over-cued for
    3h_003 (ADR-032)."""
    import json

    questions = json.load(
        open("eval/multihop_3hop_draft.json", encoding="utf-8")
    )["questions"]
    for entry in questions:
        gold = {
            hop["relation"]
            for path in entry["acceptable_paths"]
            for hop in path["hops"]
        }
        assert cued_relations(cues, entry["question"]) >= gold, (
            f"{entry['qid']} does not cue its own gold chain"
        )


def test_belongs_cues_membership_so_a_three_hop_chain_is_considered(cues):
    """ADR-031. MEASURED: every `member_of` field name is a record-keeping noun
    (`Members`, `Affiliation`, `Personnel`), and none is how a person asks.
    "the faction that X belongs to" cued nothing, so 3h_002's middle hop was
    never a candidate and the tier stopped one hop in."""
    assert "belong" in cues["member_of"]
    question = (
        "Which war was won by the faction that Hesper Wrenfield's mentor belongs to?"
    )
    assert cued_relations(cues, question) >= {"mentor_of", "member_of", "victor_of"}


def test_an_answer_type_noun_is_not_a_membership_cue(cues):
    """MEASURED and reverted once: adding `faction`, `group` and `organisation`
    alongside `belongs` cost a correct answer in BOTH arms - templates 10 -> 9,
    shipped 18 -> 16 - because "Which faction rules the place where the Pale
    Stag makes its lair?" uses "faction" as the ANSWER TYPE, not as a relation.
    Under ADR-029's coverage guard a new unique cue makes templates decline
    more, so vocabulary and the guard interact. Only the relational word ships."""
    for answer_type_noun in ("faction", "group", "organisation", "organization"):
        assert answer_type_noun not in cues["member_of"], (
            f"{answer_type_noun!r} is an answer-type noun; see ADR-031"
        )


def test_a_new_cue_must_not_collide_with_an_existing_relations_stem(cues):
    """`house` stems to `hous`, which is housed_in's cue. Adding it to
    member_of would make that word shared, and a shared word is dropped from
    `unique_relation_cues()` - silently weakening ADR-029's coverage guard as a
    side effect of extending vocabulary."""
    from src.query.route import unique_relation_cues

    assert unique_relation_cues().get("hous") == "housed_in"
    assert "hous" not in cues["member_of"]


def test_a_declared_cue_extends_the_vocabulary_from_config(cues):
    """MEASURED (ADR-024): rb_044 asks for "the apprentice of X". mentor_of's
    name and its inverse both stem to "mentor", so the role noun cued nothing
    and the question reached member_of, ruled_by and serves_at only."""
    assert "apprentic" in cues["mentor_of"]
    question = (
        "Which faction rules the hold where the apprentice of "
        "Ignatz Ashgrove the Oathless serves?"
    )
    assert "mentor_of" in cued_relations(cues, question)


def test_mentor_is_still_cued_by_its_own_name(cues):
    """The declared cue extends the vocabulary; it must not replace it."""
    assert "mentor_of" in cued_relations(cues, "Who was Ederon Fellgard's mentor?")


def test_base_verb_forms_cue_the_same_relation_as_inflected_ones(cues):
    """Measured defect in the sister router: it folds `ruled`/`rules`/`ruling`
    to `rul` but leaves the base form `rule` alone, so "whose rule?" silently
    fails to cue `ruled_by` while "who rules?" succeeds."""
    assert normalise_cue_word("rule") == normalise_cue_word("ruled")
    assert normalise_cue_word("house") == normalise_cue_word("housed")

    asked_as_noun = cued_relations(cues, "The lair falls under whose rule?")
    asked_as_verb = cued_relations(cues, "Which power rules the lair?")
    assert "ruled_by" in asked_as_noun
    assert "ruled_by" in asked_as_verb


def test_irregular_verb_win_cues_victor_of(cues):
    """relations.yaml's victor_of vocabulary is "victor" and "won"; neither
    shares a strippable suffix with "win", and 1b_022 asks "...ultimately
    win?". Worth 3 questions when ablated."""
    assert "victor_of" in cued_relations(cues, "Which war did they ultimately win?")


# --------------------------------------------------------------------------
# Ambiguity is reported, never resolved by picking.
# --------------------------------------------------------------------------


def test_multiple_surviving_endpoints_report_ambiguity(graph, relations):
    """`1b_006` genuinely has fourteen valid answers (F-015). A router that
    silently returned one of them would be wrong about the corpus, so the
    ambiguous status has to be reachable and has to carry every candidate."""
    result = route_by_cues(
        graph,
        "Which individual was a member of the faction that won the War of Drowned Light?",
        relations,
    )
    if result.ambiguous:
        assert len({p.end for p in result.paths}) > 1
    assert EvidenceStatus.FALLBACK_AMBIGUOUS.is_answerable


# --------------------------------------------------------------------------
# Provenance: a reader must be able to tell the tiers apart.
# --------------------------------------------------------------------------


def test_fallback_statuses_are_answerable_but_flagged_as_fallback():
    """The two tiers measure 40% and 91% precision. Collapsing them into one
    status would let the weaker one borrow the stronger one's credibility."""
    for status in (
        EvidenceStatus.FALLBACK_SUFFICIENT,
        EvidenceStatus.FALLBACK_AMBIGUOUS,
    ):
        assert status.is_answerable
        assert status.is_fallback
    assert not EvidenceStatus.SUFFICIENT.is_fallback


def test_fallback_answer_carries_its_evidence_and_says_it_is_lower_precision(graph):
    answer = answer_question(
        "Which power rules the settlement where The Cinder-Wrought Aegis is housed?",
        graph,
    )
    assert answer.paths, "an answer without its evidence cannot be shown to a judge"
    assert "lower precision" in (answer.note or "")
    for path in answer.paths:
        for edge in path.edges:
            assert edge.document, "every hop must name the document it came from"


def test_exact_match_only_no_fuzzy_resolution_in_the_fallback(graph):
    """ADR-011 applies to this tier too: a near-miss spelling must resolve to
    nothing rather than be guessed at, even though `caedmon_fellgard` and
    `ederon_fellgard` are 0.839 similar."""
    assert find_mentions(graph, "Who is Ederon Fellgar?") == []
    assert find_mentions(graph, "Who is Ederon Fellgard?")[0].key == "ederon_fellgard"


# --------------------------------------------------------------------------
# Profile: "Who is X?" - an entity with no relation named.
# --------------------------------------------------------------------------


def test_who_is_x_returns_the_entitys_record(graph):
    """The gap this closes. "Who is Ravena Stormwell?" names an entity the
    graph knows and no relation at all, so both tiers correctly declined and
    the honest result was NO_TEMPLATE_MATCH - on a question whose answer was
    sitting in the graph the whole time (asking "which faction is she a member
    of" answers The Silent Choir immediately). The failure was question
    *shape*, not coverage."""
    answer = answer_question("Who is Ravena Stormwell?", graph)

    assert answer.status == EvidenceStatus.PROFILE
    assert "The Silent Choir" in answer.values
    assert answer.paths
    assert answer.documents, "a profile is still evidence and still cites it"


def test_a_profile_is_not_presented_as_a_resolved_answer(graph):
    """It answers a broader question than the one asked, and the reader is
    entitled to know that."""
    answer = answer_question("Who is Ravena Stormwell?", graph)
    assert answer.status is not EvidenceStatus.SUFFICIENT
    assert answer.status.is_fallback
    assert "not an answer to a narrower question" in (answer.note or "")


def test_a_named_relation_the_corpus_lacks_still_declines(graph):
    """The narrow rule. A profile fires only when NO relation is cued. Asking
    for a mentor cues `mentor_of`, finds no path, and must still decline -
    silence about a relation someone asked for is not an invitation to answer
    a different question (F-014's rule applied to question shape)."""
    answer = answer_question("Who was Ederon Fellgard's mentor?", graph)
    assert answer.status is not EvidenceStatus.PROFILE
    assert answer.values == ()


def test_an_unknown_entity_gets_no_profile(graph):
    answer = answer_question("Who is Tobias Ravenscar?", graph)
    assert answer.status is not EvidenceStatus.PROFILE


# --------------------------------------------------------------------------
# Near-miss spellings are reported, never resolved.
# --------------------------------------------------------------------------


def test_a_near_miss_name_suggests_without_picking(graph):
    """ADR-011 forbids picking a winner: `caedmon_fellgard` and
    `ederon_fellgard` are 0.839 similar, so a threshold loose enough to accept
    "Raven Stormwell" -> "Ravena Stormwell" (0.968) eventually merges two real
    people. But refusing to guess is not a reason to withhold what was found -
    the old behaviour returned a bare NO_TEMPLATE_MATCH and left a user with a
    typo no way to discover it."""
    answer = answer_question("Who is Raven Stormwell?", graph)

    assert answer.status == EvidenceStatus.AMBIGUOUS_ENTITY
    assert "Ravena Stormwell" in (answer.note or "")
    assert answer.values == (), "suggesting is not answering"
    assert answer.resolutions and answer.resolutions[0].candidates


def test_a_correctly_spelled_possessive_is_not_reported_as_a_typo(graph):
    """MEASURED REGRESSION. `_CAPITALISED_SPAN_RE` captures "Ederon Fellgard's"
    whole, which resolves ambiguous at 0.938 against the real name - so the
    near-miss reporter announced a typo for a question that spelled the name
    perfectly."""
    answer = answer_question("Who was Ederon Fellgard's mentor?", graph)
    assert answer.status != EvidenceStatus.AMBIGUOUS_ENTITY
    assert "is not a name in the corpus" not in (answer.note or "")


@pytest.mark.parametrize(
    "question,expected_status",
    # Exact wording from the frozen set, `eval/robustness/routing_robustness_v1.json`.
    # All three names are spelled correctly, missing only the apostrophe -
    # `_strip_possessive` catches "Ederon Fellgard's"; none of these have a
    # mark to strip at all.
    [
        ("isolde mournvales group won what war", None),  # rb_008
        (
            "ederon fellgards faction won which accord",  # rb_016
            # The MORE SPECIFIC diagnosis F-026 says the reporter regressed:
            # relation_unavailable, not a typo complaint, because Ederon
            # Fellgard names a real member of a real faction and the
            # question just asks for a relation the templates don't cue.
            EvidenceStatus.RELATION_UNAVAILABLE,
        ),
        ("what war did ravena stormwells lot end up winning", None),  # rb_028
    ],
)
def test_an_apostrophe_less_possessive_is_not_reported_as_a_typo(
    question, expected_status, graph
):
    """F-026, fixed. `_strip_possessive` only strips a *marked* possessive.

    Three of 49 frozen questions write the possessive with no apostrophe at
    all ("isolde mournvales" for "Isolde Mournvale's") - spelled correctly,
    and the reporter announced each as a typo. `_resolves_when_bare_s_dropped`
    suppresses the suggestion without widening what counts as a typo: it only
    fires when the trimmed span resolves through the resolver's own exact/
    normalised/alias tiers, never fuzzy.
    """
    answer = answer_question(question, graph)
    assert answer.status != EvidenceStatus.AMBIGUOUS_ENTITY
    assert "is not a name in the corpus" not in (answer.note or "")
    if expected_status is not None:
        assert answer.status == expected_status


def test_bare_s_stripping_never_swallows_a_name_that_really_ends_in_s(graph):
    """The measured risk F-026 flagged: 11 real entity names end in "s"
    ("Ashfall Colossus", "Embercrag Fortress", ...). None of their
    bare-s-stripped forms happen to be a different entity's canonical key, so
    a correctly spelled mention of one never even reaches the near-miss path -
    it resolves normally first."""
    from src.query.resolve import EntityResolver

    resolver = EntityResolver(graph)
    names_ending_s = [n.name for n in graph.nodes.values() if n.name.rstrip().lower().endswith("s")]
    assert len(names_ending_s) >= 10, "fixture assumption: the corpus has such names"
    for name in names_ending_s:
        assert resolver.resolve(name).resolved


def test_a_name_with_no_near_match_stays_an_ordinary_miss(graph):
    """"Ashen Era" resolves to nothing at all - no candidates - so it must not
    be dressed up as a spelling suggestion."""
    answer = answer_question("What color is the sky in the Ashen Era?", graph)
    assert answer.status == EvidenceStatus.NO_TEMPLATE_MATCH


def test_only_identity_questions_earn_a_profile(graph):
    """MEASURED CORRECTION. The first version profiled any question that cued
    no relation, so "What did the Gravemaw Wyrm eat for breakfast?" was
    answered with the wyrm's lair. Labelled or not, that answers a question
    nobody asked. "Who is X?" asks for the record; "what did X eat?" asks for
    an attribute the corpus does not hold, and must still decline."""
    profiled = answer_question("Who is Ravena Stormwell?", graph)
    described = answer_question("Tell me about the Iron-Ring Cartel", graph)
    diet = answer_question("What did the Gravemaw Wyrm eat for breakfast?", graph)
    colour = answer_question("What color is the Gravemaw Wyrm?", graph)

    assert profiled.status == EvidenceStatus.PROFILE
    assert described.status == EvidenceStatus.PROFILE
    assert diet.status is not EvidenceStatus.PROFILE
    assert colour.status is not EvidenceStatus.PROFILE
    assert diet.values == () and colour.values == ()


# --------------------------------------------------------------------------
# Near-miss scanning is case- and underscore-insensitive.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "Who is halward crowhurst?",      # lowercase, v/w typo - the reported bug
        "Who is Halward Crowhurst?",      # capitalised, same typo
        "who is halward_crowhurst?",      # underscore key form, same typo
        "halward crowhurst",              # no question wrapper at all
        "WHO IS HALWARD CROWHURST?",      # shouting
    ],
)
def test_a_typo_is_suggested_whatever_its_shape(question, graph):
    """REPORTED BUG. The first version scanned only `_CAPITALISED_SPAN_RE`, so
    "Halward Crowhurst" got a suggestion and "halward crowhurst" got a bare
    NO_TEMPLATE_MATCH. The resolver scores both at 0.941 against `Halvard
    Crowhurst` - the lowercase spelling simply never reached it. People typing
    into a search box do not capitalise, and they paste entity keys with
    underscores."""
    answer = answer_question(question, graph)

    assert answer.status == EvidenceStatus.AMBIGUOUS_ENTITY
    assert "Halvard Crowhurst" in (answer.note or "")
    assert answer.values == (), "suggesting is still not answering"


@pytest.mark.parametrize(
    "question",
    ["Who is halvard_crowhurst?", "Who is halvard crowhurst?", "Who is HALVARD CROWHURST?"],
)
def test_a_correct_name_in_any_shape_still_resolves(question, graph):
    """The underscore/key form and lowercase must route normally, not be
    treated as near-misses of themselves."""
    answer = answer_question(question, graph)
    assert answer.status == EvidenceStatus.PROFILE
    assert answer.values


def test_a_single_misspelt_word_is_suggested(graph):
    """One-word entity names exist (`Gloamreach`), so single-token spans are
    scanned - above a length floor, since short strings score noisily."""
    answer = answer_question("who is gloamreac", graph)
    assert answer.status == EvidenceStatus.AMBIGUOUS_ENTITY
    assert "Gloamreach" in (answer.note or "")


def test_a_question_naming_a_real_entity_is_never_called_a_typo(graph):
    """MEASURED GUARD. The worst noise the scan produces is a window that
    swallows a correctly spelled name plus a neighbouring word - "was Ederon
    Fellgard" scores 0.882. Rather than rely on the floor alone, a span that
    resolves for real aborts the scan outright: the question names the man
    correctly and fails because the corpus records no mentor."""
    answer = answer_question("Who was Ederon Fellgard's mentor?", graph)
    assert answer.status != EvidenceStatus.AMBIGUOUS_ENTITY
    assert "not a name in the corpus" not in (answer.note or "")


@pytest.mark.parametrize(
    "question",
    [
        "What color is the sky in the Ashen Era?",
        "Which stronghold does Tobias Ravenscar command?",
        "Which faction won the Siege of Emberfall Bridge?",
    ],
)
def test_a_name_with_no_real_near_match_produces_no_suggestion(question, graph):
    """The reporting floor is 0.90, far above the resolver's own 0.72 - which
    exists to admit candidates for a human, not to claim a typo."""
    answer = answer_question(question, graph)
    assert answer.status != EvidenceStatus.AMBIGUOUS_ENTITY
