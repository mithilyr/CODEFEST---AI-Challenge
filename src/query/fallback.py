"""Cue-based fallback routing: the tier that runs when no template matches.

WHY THIS EXISTS, WITH THE NUMBER
---------------------------------
ADR-017 built four templates and deferred anything more general until routing
robustness had been measured. It was measured (ADR-019, `comparison/REPORT.md`)
against 55 questions authored by a party with no access to either router:

    four templates alone    routed 11/49   correct 10   complete evidence 11
    cue routing alone       routed 30/49   correct 12   complete evidence 20
    templates, then cues    routed 32/49   correct 17   complete evidence 24

The templates match no route shape on 35 of 49 answerable questions, and on 21
*novel* questions they match one. That is not an implementation defect - they
do exactly what ADR-017 said - but it settles the open question: 7/7 on the dev
questions measures fit, not routing capability.

This module is the second tier. It never runs before the templates, so every
answer a template already produced is unchanged; it only ever sees questions
where `route()` returned a `RouteMiss`. Measured, the composite adds 7 correct
answers and 13 complete-evidence retrievals over templates alone, and regresses
nothing.

HOW IT ROUTES, AND WHY NOT BY WORD ORDER
------------------------------------------
Adapted from the sister prototype's `graph/src/query/router.py` (ADR-019).
It does not sequence relations from the question's word order, because English
relative clauses invert that order routinely - "Which accord was ultimately won
by the faction of which Ederon Fellgard is a member?" states `victor_of` before
`member_of` even though `member_of` is hop one.

Instead: run the existing bounded search, then keep only paths whose every edge
is a relation the question's own words name somewhere. Order-independent by
construction. The vocabulary comes from `config/relations.yaml` - the same file
`build.py` reads - so what this recognises cannot drift from what edges exist.

WHAT WAS DELIBERATELY NOT PORTED
----------------------------------
The sister router carries four guards. Ablated individually against the frozen
set (`python -m comparison.ablations`), only two earn their place here:

  coverage-over-length    KEPT. Carries the router almost entirely: removing it
                          collapses correctness 12 -> 2 and complete evidence
                          20 -> 7. See `select_candidates`.
  irregular verbs         KEPT. Worth 3 questions (12 -> 9 without it).
  consecutive-repeat      NOT PORTED. Changes nothing on our set (12 -> 12). It
                          was added against a measured failure in their stack
                          that does not reproduce in ours, and a guard with no
                          measured advantage here is code we would be unable to
                          justify.
  tie-break stopwords     KEPT, but below our resolution - the set could not
                          separate it (+1 correct, -1 complete evidence, n=49).
                          Retained because the same stopword set already governs
                          cue matching, so removing it there alone would make
                          the module inconsistent with itself. Flagged rather
                          than claimed.

One defect in their version is fixed here rather than copied: their stemmer
strips suffixes only, so `ruled`/`rules`/`ruling` fold to `rul` while the base
form `rule` does not, and never matches the cue built from the field name
`Ruled by`. Worth one question, measured.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from src.graph.build import RelationMap
from src.graph.schema import Graph
from src.graph.traverse import Path, find_paths

MAX_HOPS = 3

#: Prepositions/articles/auxiliaries that would otherwise cue every relation -
#: nearly every field name in relations.yaml contains "of" or "by".
CUE_STOPWORDS = frozenset(
    {
        "of", "by", "in", "at", "the", "a", "an", "to", "is", "was", "are",
        "were", "for", "has", "have", "on", "and", "or",
    }
)

_NON_ALNUM = re.compile(r"[^a-z0-9\s]+")

#: relations.yaml's only `victor_of` vocabulary is "victor" (field names) and
#: "won" (from the inverse `won_by`). Neither shares a strippable suffix with
#: "win", and `1b_022` asks "...ultimately win?". Irregular-verb knowledge
#: applied to the relation vocabulary generally, not a per-question case.
IRREGULAR_VERBS = {"win": "won", "wins": "won", "winning": "won"}

#: Stripped down to a 3-character floor so short cues are not hollowed out.
STRIPPABLE_SUFFIXES = ("ing", "ed", "es", "s")


def normalise_cue_word(word: str) -> str:
    """Fold a word toward the stem its cue set is keyed under.

    The trailing-"e" rule is the fix described in the module docstring: without
    it `rule` and `house` never match the `rul`/`hous` cues that `Ruled by` and
    `Housed in` produce, so "falls under whose rule?" silently fails to cue
    `ruled_by` while "which power rules..." succeeds.
    """
    if word in IRREGULAR_VERBS:
        return IRREGULAR_VERBS[word]
    for suffix in STRIPPABLE_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    if word.endswith("e") and len(word) > 3:
        return word[:-1]
    return word


def question_tokens(text: str) -> list[str]:
    """Lowercase, punctuation-folded tokens. Nothing dropped.

    No stopword is removed here, and no article either. Several corpus names
    carry "the" as a title rather than an article - `Cerys Sablewood the
    Ashen`, `Corvus Hollowmere the Pale` - and dropping it stops those names
    matching their own node keys. Stopwords are filtered where they are a
    problem (cue matching, tie-break), never in entity matching.
    """
    return _NON_ALNUM.sub(" ", text.lower()).split()


def _cue_tokens(*names: str) -> set[str]:
    out: set[str] = set()
    for name in names:
        for word in _NON_ALNUM.sub(" ", name.lower()).split():
            if word not in CUE_STOPWORDS:
                out.add(normalise_cue_word(word))
    return out


def relation_cues(relations: RelationMap) -> dict[str, set[str]]:
    """relation -> cue words, built entirely from config/relations.yaml.

    Sources per relation: its own name, its inverse's name, every field name
    mapped to it in either direction, and any `cues:` the relation declares -
    question vocabulary that is not a corpus field name (ADR-024). Built from the same config the graph
    builder reads, so a relation's recognised vocabulary can never drift from
    the edges the graph actually holds - and a new field name added to that
    file extends what this recognises with no code change here.
    """
    fields_by_relation: dict[str, list[str]] = defaultdict(list)
    for field_name, relation in relations.forward.items():
        fields_by_relation[relation].append(field_name)
    for field_name, relation in relations.reverse.items():
        fields_by_relation[relation].append(field_name)

    cues: dict[str, set[str]] = {}
    for relation, fields in fields_by_relation.items():
        inverse = relations.inverses.get(relation, relation)
        extra = relations.question_cues.get(relation, ())
        cues[relation] = _cue_tokens(relation, inverse, *fields, *extra)
    return cues


def tokens_outside_mentions(question: str, mentions: list[Mention]) -> list[str]:
    """The question's tokens with each resolved entity's own name removed.

    MEASURED: "Who is House Morvain?" cued `housed_in`, and "Who is Embercrag
    Fortress?" cued `serves_at` - in both cases from a word inside the entity's
    *name*, not from anything the asker requested. The cue scanner read the
    whole question, so a node whose name happens to contain a relation's
    vocabulary could never be asked about plainly: the router would chase a
    relation the question never mentioned, find no path, and decline.

    That made two of the 118 entity links on the front page dead - but the
    defect is not about those two questions. Any question naming House Morvain
    would carry a phantom `housed_in` cue.

    A mention's key tokens are exactly what `find_mentions` matched against, so
    removing that run removes the name and nothing else.
    """
    tokens = question_tokens(question)
    for mention in mentions:
        key_tokens = mention.key.split("_")
        width = len(key_tokens)
        for index in range(len(tokens) - width + 1):
            if tokens[index : index + width] == key_tokens:
                tokens = tokens[:index] + tokens[index + width :]
                break
    return tokens


def cued_relations(
    cues: dict[str, set[str]], question: str, *, tokens: list[str] | None = None
) -> set[str]:
    """Relations the question cues, preferring words that name only one.

    A word that names exactly one relation is evidence the question asks about
    that relation. A word shared across several is not: 7 of 65 cue words are
    shared, and the worst is `plac` - "Place of forging", "Place of housing" and
    "Place of service" all reduce to it, so the ordinary noun *place* cues
    `forged_at`, `housed_in` and `serves_at` at once.

    MEASURED (ADR-033): 3h_003 - "Which faction rules the place where the relic
    wielded by Halvard Vane the Grave-Sworn was forged?" - cued five relations
    where its gold chain has three, and returned six values as
    `fallback_ambiguous`. "wielded", "forged" and "rules" each name exactly one
    relation and together are the whole chain; "place" contributed the two
    spurious ones.

    So shared words are a **fallback, not a veto**. Dropping them outright reads
    three frozen questions down to no cue at all (`rb_003`, `rb_040`, `rb_055`),
    whose only cue word *is* a shared one - `rb_003` asks where something is
    kept using the word "place" and nothing else. Where unique words name
    nothing, the shared ones are all the evidence there is and are used.
    """
    words = question_tokens(question) if tokens is None else tokens
    cue_tokens = {normalise_cue_word(t) for t in words}
    named = {relation for relation, w in cues.items() if cue_tokens & w}

    owners: dict[str, set[str]] = defaultdict(set)
    for relation, words in cues.items():
        for word in words:
            owners[word].add(relation)
    unique = {
        next(iter(owners[t]))
        for t in cue_tokens
        if t in owners and len(owners[t]) == 1
    }
    return unique or named


@dataclass(frozen=True)
class Mention:
    key: str
    name: str
    token_count: int


def find_mentions(graph: Graph, question: str) -> list[Mention]:
    """Every known node whose key appears as a contiguous run of question tokens.

    Exact match only, per ADR-011 - a node's key is already
    `slugify + strip-leading-"the_"`, so normalising the question the same way
    and looking for that key's token sequence means a mention resolves if and
    only if the same name would have resolved as a wiki-link target during
    graph building. No separate fuzzy step that could drift from that rule.

    On overlapping spans the longer match wins, which is what stops a node
    whose name is a substring of another's being reported for the same words.
    """
    tokens = question_tokens(question)
    candidates: list[tuple[Mention, int, int]] = []

    for node in graph.nodes.values():
        key_tokens = node.key.split("_")
        n = len(key_tokens)
        if not n:
            continue
        for start in range(len(tokens) - n + 1):
            if tokens[start : start + n] == key_tokens:
                candidates.append((Mention(node.key, node.name, n), start, start + n))

    candidates.sort(key=lambda c: (-c[0].token_count, c[1]))
    kept: list[Mention] = []
    covered: set[int] = set()
    for mention, start, end in candidates:
        span = set(range(start, end))
        if span & covered:
            continue
        covered |= span
        kept.append(mention)

    seen: dict[str, Mention] = {}
    for mention in kept:
        seen.setdefault(mention.key, mention)
    return sorted(seen.values(), key=lambda m: -m.token_count)


def select_candidates(cued_paths: list[Path]) -> list[Path]:
    """Maximise distinct cued relations covered, then take the shortest.

    THE LOAD-BEARING RULE. Ablated, this is worth almost the whole router:
    removing it drops correctness 12 -> 2 and complete evidence 20 -> 7 on the
    frozen set.

    "Keep the longest cued chain" is wrong, and measurably so.
    `config/relations.yaml` maps `Known participant`/`Notable fighter` - real
    fields on conflict pages - onto `member_of`'s reverse direction, same as an
    ordinary faction's `Members` row. Legitimate for the graph's purposes, but
    it means a cued chain can validly continue *past* the correct two-hop
    answer into a third hop landing on someone the corpus never meant as the
    answer. Preferring length silently swaps that person in.

    A path that uses every cued relation at least once has said everything the
    question's words asked for; going further adds hops without adding
    relations the question named. Coverage must be scored before length,
    because a *longer* path can tie a shorter one's coverage without a plain
    length comparison noticing.
    """
    if not cued_paths:
        return []

    def coverage(path: Path) -> int:
        return len({edge.relation for edge in path.edges})

    best = max(coverage(p) for p in cued_paths)
    at_best = [p for p in cued_paths if coverage(p) == best]
    fewest = min(len(p.edges) for p in at_best)
    return [p for p in at_best if len(p.edges) == fewest]


@dataclass(frozen=True)
class FallbackRoute:
    """What the fallback tier found, or why it declined.

    `paths` is empty whenever this tier declines, and the engine then keeps the
    template stage's own `NO_TEMPLATE_MATCH` rather than inventing a new
    failure. Declining is the common case and must stay cheap to read.
    """

    paths: tuple[Path, ...]
    cued: tuple[str, ...]
    start: Mention | None
    ambiguous: bool = False
    #: True when this is a profile rather than a chain - see `profile_of`.
    profile: bool = False

    @property
    def answered(self) -> bool:
        return bool(self.paths)


#: Question shapes that ask for an entity's record rather than for one fact.
#:
#: MEASURED CORRECTION. The first version of the profile rule fired whenever an
#: entity resolved and no relation was cued. That is too broad, and two
#: existing tests caught it: "What did the Gravemaw Wyrm eat for breakfast?"
#: cues no relation either, and it was answered with a profile - returning the
#: wyrm's lair to a question about its diet. Labelled or not, that is answering
#: a question nobody asked, which is the failure F-025 is about.
#:
#: The line that holds: "Who is X?" *asks for the record*, so giving the record
#: is answering it. "What did X eat?" asks for a specific attribute the corpus
#: does not record, and the honest response is still to decline. This is a
#: closed list of question shapes, not a semantic model - the same kind of
#: deterministic rule as `route.py`'s templates, and extended only alongside a
#: question that shows it is needed.
IDENTITY_QUESTION_RE = re.compile(
    r"^\s*(?:who|what)\s+(?:is|was|are|were)\b"
    r"|^\s*tell me about\b"
    r"|^\s*describe\b"
    r"|\bwho\s+(?:is|was)\s+\w",
    re.IGNORECASE,
)


def profile_of(graph: Graph, start: Mention) -> FallbackRoute:
    """Everything the graph records about one entity, both directions.

    WHY THIS EXISTS. "Who is Ravena Stormwell?" names an entity the graph knows
    and a relation it does not - because it names no relation at all. Both
    deterministic tiers correctly declined, and the honest result was
    `no_template_match` on a question whose answer is sitting in the graph:
    ask "which faction is Ravena Stormwell a member of" and it answers The
    Silent Choir immediately. The failure was the question's *shape*, not our
    coverage.

    So when an entity resolves and nothing cues a relation, return every edge
    touching that entity as its own one-hop path. This is not a guess: each
    edge is a fact the graph already built from an infobox row, with its
    document attached. What it is *not* is an answer to a specific question -
    it is the entity's record - which is why it gets its own
    `EvidenceStatus.PROFILE` and is labelled as a profile in the UI rather
    than presented as a resolved answer.

    Deliberately narrow. It fires only when NO relation is cued. A question
    that names a relation the corpus does not record for this entity -
    "Who was Ederon Fellgard's mentor?" - still cues `mentor_of`, still finds
    no path, and still declines. Silence about a relation someone asked for is
    not an invitation to answer a different question (F-014's rule, applied to
    question shape).
    """
    edges = graph.neighbours(start.key)
    if not edges:
        return FallbackRoute((), (), start)
    return FallbackRoute(
        tuple(Path(start.key, (edge,)) for edge in edges), (), start, profile=True
    )


def route_by_cues(
    graph: Graph,
    question: str,
    relations: RelationMap,
    *,
    cues: dict[str, set[str]] | None = None,
) -> FallbackRoute:
    """Route a question no template matched. Declines rather than guesses.

    Returns an empty `FallbackRoute` when no entity resolves, no relation is
    cued, or no path survives - all three are honest non-answers, and the
    caller reports the original template miss instead of manufacturing a
    weaker-looking one.
    """
    cues = cues if cues is not None else relation_cues(relations)

    mentions = find_mentions(graph, question)
    if not mentions:
        return FallbackRoute((), (), None)

    start = mentions[0]

    # Two named entities is a "how are these connected" question: search
    # between them directly rather than by cue, which is what the relation
    # vocabulary cannot express.
    if len(mentions) >= 2:
        paths = find_paths(graph, start.key, mentions[1].key, max_hops=MAX_HOPS)
        return FallbackRoute(tuple(paths), (), start)

    # Scanned over the question *minus* the entity's own name. A cue word
    # inside a node's name is part of the name (F-035).
    cued = cued_relations(
        cues, question, tokens=tokens_outside_mentions(question, mentions)
    )
    if not cued:
        # No relation named at all. Only an *identity* question earns a
        # profile - see `IDENTITY_QUESTION_RE`.
        if IDENTITY_QUESTION_RE.search(question):
            return profile_of(graph, start)
        return FallbackRoute((), (), start)

    candidates = select_candidates(
        [
            p
            for p in find_paths(graph, start.key, max_hops=MAX_HOPS)
            if p.edges and all(e.relation in cued for e in p.edges)
        ]
    )
    if not candidates:
        return FallbackRoute((), tuple(sorted(cued)), start)

    ends: dict[str, list[Path]] = defaultdict(list)
    for path in candidates:
        ends[path.end].append(path)

    if len(ends) == 1:
        return FallbackRoute(
            tuple(next(iter(ends.values()))), tuple(sorted(cued)), start
        )

    # More than one surviving end node. Break the tie on how much of the
    # question's own wording each candidate's name accounts for. Stopwords are
    # filtered HERE and not in `question_tokens`, because "the" is grammatical
    # scaffolding in a question but a title in several corpus names.
    asked = {t for t in question_tokens(question) if t not in CUE_STOPWORDS}
    scored: list[tuple[int, list[Path]]] = []
    for end_key, paths in ends.items():
        name = graph.nodes[end_key].name if end_key in graph.nodes else end_key
        name_tokens = {t for t in question_tokens(name) if t not in CUE_STOPWORDS}
        scored.append((len(name_tokens & asked), paths))

    best = max(score for score, _ in scored)
    winners = [paths for score, paths in scored if score == best]

    if len(winners) == 1:
        return FallbackRoute(tuple(winners[0]), tuple(sorted(cued)), start)

    # Genuinely ambiguous. Reported as such rather than resolved by picking -
    # `1b_006` really does have fourteen valid answers, and a router that
    # silently returned one of them would be wrong about the corpus.
    return FallbackRoute(
        tuple(p for paths in winners for p in paths),
        tuple(sorted(cued)),
        start,
        ambiguous=True,
    )
