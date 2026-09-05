"""What the engine established before it declined.

WHY THIS MODULE EXISTS
----------------------
A decline is a result. `src/query/evidence.py` already makes every one of them
a *named* result rather than an empty one, and that naming is the project's
core claim - the system stops at `RELATION_UNAVAILABLE` instead of inventing a
plausible answer.

But a name is not evidence. On screen, `no_template_match` and a stack trace
look the same: a red word where an answer should be. Measured on the frozen
robustness set, **23 of 55 questions decline, and 18 of those 23 are
`no_template_match` carrying nothing but a one-line reason** - no entities, no
relations, no citations. A judge typing their own question at the live demo
most likely sees exactly that, and cannot tell a principled refusal from a
crash.

So this module collects, at each decline site, the things the engine *did*
establish on the way: which names in the question resolved, what the graph
records about them, which relations exist where the question asked for one that
does not, how far a traversal got before it stopped. Everything carries the
document it came from, exactly as the SUFFICIENT path does.

WHY IT LIVES IN `src/query/` AND NOT IN `src/ui/`
-------------------------------------------------
Because collecting it is reasoning. It reads edges, walks neighbourhoods,
consults the relation map and scans evidence units - all of which
`src/ui/view.py` is forbidden to do by ADR-018's three architectural tests, and
those tests are what makes "the UI adds no reasoning" a fact rather than a
promise. The presentation layer transcribes what this module produced; it
derives nothing.

Nothing here changes any status, any answer, or any traversal. It is read-only
over state the engine already computed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.graph.build import RelationMap
from src.graph.schema import Graph
from src.query.resolve import EntityResolver
from src.query.route import extract_mentions

#: Facts shown per entity before the list is truncated. The graph's busiest
#: node (`The Silent Choir`) carries 20 edges; showing all of them for every
#: resolved entity in a multi-entity question buries the point. The total is
#: always reported alongside, so truncation is visible rather than silent.
_MAX_FACTS = 12

#: Endpoints listed when a traversal reached somewhere other than the goal.
#: `1b_006`-shaped chains reach fourteen; more than this and the block stops
#: being readable, so the count is stated and the list is cut.
_MAX_REACHED = 10


@dataclass(frozen=True)
class EntityRef:
    """One entity, with the page that documents it - a citation, not just a name."""

    key: str
    name: str
    entity_type: str | None = None
    #: The wiki page this entity has, where it has one. Roughly a third of
    #: nodes exist only as link targets and have none; that absence is itself
    #: worth showing, so it is not filled in with a guess.
    page: str | None = None
    #: Populated only where the value came from a fuzzy comparison, so a reader
    #: sees the number the resolver declined to act on (ADR-011).
    similarity: float | None = None


@dataclass(frozen=True)
class Fact:
    """One edge touching an entity, with the infobox row it was read from."""

    relation: str
    #: "out" when the entity is the edge's source, "in" when it is the target.
    #: Shown because the corpus is asymmetric (ADR-016) and a reader should see
    #: which page actually made the claim.
    direction: str
    other: EntityRef
    document: str
    field_name: str
    row: int
    raw: str
    tier: int


@dataclass(frozen=True)
class Neighbourhood:
    """Everything the graph records about one entity."""

    entity: EntityRef
    facts: tuple[Fact, ...]
    #: Distinct relation names this entity has edges for, sorted. This is the
    #: direct answer to "why did my question about it not work".
    relations_present: tuple[str, ...]
    #: Total before `_MAX_FACTS` truncation, so a cut list says so.
    fact_count: int


@dataclass(frozen=True)
class CorpusPresence:
    """Where a name appears in the corpus, for an entity the graph has no node for."""

    collection: str
    tier: int
    documents: tuple[str, ...]
    unit_count: int
    #: One real citation from that collection - id, locator and the text.
    evidence_id: str
    locator: str
    quote: str


@dataclass(frozen=True)
class Diagnostics:
    """Partial evidence for a decline. Every field is optional by design.

    Different declines establish different things, and a block the engine could
    not fill stays empty rather than being padded with something plausible.
    """

    #: Entities named in the question that DID resolve, with their records.
    established: tuple[Neighbourhood, ...] = ()
    #: The span the engine took to be an entity but could not resolve.
    span: str | None = None
    #: Near-miss spellings at or above the reporting floor (ADR-021). A
    #: suggestion for the user to confirm - never applied automatically.
    suggestions: tuple[EntityRef, ...] = ()
    #: Every candidate an ambiguous mention matched.
    candidates: tuple[EntityRef, ...] = ()
    #: The relation the question asked for, where one was identified.
    asked_relation: str | None = None
    #: The full relation vocabulary, so the boundary reads as declared.
    relation_vocabulary: tuple[str, ...] = ()
    #: Traversal endpoints, for a chain that ran but landed elsewhere.
    start: EntityRef | None = None
    goal: EntityRef | None = None
    reached: tuple[EntityRef, ...] = ()
    reached_count: int = 0
    hops_completed: int = 0
    #: Where an out-of-graph name does appear in the corpus.
    presence: tuple[CorpusPresence, ...] = field(default_factory=tuple)


# -- small builders ----------------------------------------------------------


def entity_ref(graph: Graph, key: str, similarity: float | None = None) -> EntityRef:
    node = graph.nodes.get(key)
    if node is None:
        return EntityRef(key=key, name=key, similarity=similarity)
    return EntityRef(
        key=node.key,
        name=node.name,
        entity_type=node.entity_type,
        page=node.page,
        similarity=similarity,
    )


def relation_vocabulary(relation_map: RelationMap) -> tuple[str, ...]:
    """Every relation the system can traverse, from config/relations.yaml.

    Read off the same map the graph builder used, so this cannot drift into
    advertising a relation the builder does not actually produce.
    """
    return tuple(
        sorted(set(relation_map.forward.values()) | set(relation_map.reverse.values()))
    )


def neighbourhood(graph: Graph, key: str) -> Neighbourhood:
    """Everything the graph records about `key`, with each row's provenance."""
    edges = graph.neighbours(key)
    facts = []
    for edge in edges[:_MAX_FACTS]:
        outgoing = edge.source == key
        other_key = edge.target if outgoing else edge.source
        facts.append(
            Fact(
                relation=edge.relation,
                direction="out" if outgoing else "in",
                other=entity_ref(graph, other_key),
                document=edge.document,
                field_name=edge.field_name,
                row=edge.row,
                raw=edge.raw,
                tier=edge.tier,
            )
        )
    return Neighbourhood(
        entity=entity_ref(graph, key),
        facts=tuple(facts),
        relations_present=tuple(sorted({e.relation for e in edges})),
        fact_count=len(edges),
    )


def established_entities(
    question: str,
    graph: Graph,
    resolver: EntityResolver,
    gazetteer: list[tuple[str, str]],
) -> tuple[Neighbourhood, ...]:
    """The entities the question named that the system does know.

    Reuses `route.extract_mentions` - the same gazetteer scan routing itself
    used - rather than a second, subtly different entity finder. If routing saw
    an entity, this shows it; if routing saw none, the empty result is the true
    statement that nothing in the question was recognised.
    """
    seen: dict[str, None] = {}
    for mention in extract_mentions(question, graph, resolver, gazetteer):
        if mention.resolution.key is not None:
            seen.setdefault(mention.resolution.key, None)
    return tuple(neighbourhood(graph, key) for key in seen)


def corpus_presence(mention: str, evidence_units) -> tuple[CorpusPresence, ...]:
    """Which collections mention `mention`, with one real citation from each.

    This is what separates `OUTSIDE_STRUCTURED_COVERAGE` from
    `UNRESOLVED_ENTITY` in a way a reader can check: the graph is built only
    from wiki infobox rows (`src/graph/build.py`), so a person described at
    length in tier-1 codex prose and never given an infobox is invisible to it.
    Saying so is only credible with the documents named.
    """
    needle = mention.lower()
    by_collection: dict[str, list] = {}
    for unit in evidence_units:
        if needle in unit.text.lower():
            by_collection.setdefault(unit.collection, []).append(unit)

    out = []
    for collection in sorted(by_collection):
        units = by_collection[collection]
        first = units[0]
        out.append(
            CorpusPresence(
                collection=collection,
                tier=first.tier,
                documents=tuple(sorted({u.canonical_doc_id for u in units})),
                unit_count=len(units),
                evidence_id=first.evidence_id,
                locator=first.locator,
                quote=first.text[:400],
            )
        )
    return tuple(out)


# -- per-status builders, called from the engine's decline sites -------------


def for_template_miss(
    question: str,
    graph: Graph,
    resolver: EntityResolver,
    gazetteer: list[tuple[str, str]],
    relation_map: RelationMap,
) -> Diagnostics:
    """`NO_TEMPLATE_MATCH` / the terminal `RELATION_UNAVAILABLE`.

    The dominant decline by a wide margin, and the one that carried the least.
    A judge sees which of their names the system recognised, everything it
    knows about each, and the closed relation vocabulary that bounds what it
    could have been asked - so the miss reads as a declared boundary.
    """
    return Diagnostics(
        established=established_entities(question, graph, resolver, gazetteer),
        relation_vocabulary=relation_vocabulary(relation_map),
    )


def for_unresolved_mention(
    graph: Graph,
    resolution,
    relation_map: RelationMap,
    evidence_units=None,
) -> Diagnostics:
    """`UNRESOLVED_ENTITY`, `AMBIGUOUS_ENTITY` and `OUTSIDE_STRUCTURED_COVERAGE`.

    All three are "a name did not become a node", and they differ in what the
    corpus says about it, so all three get the same shape filled to different
    depths: the span, the candidates the resolver found and declined to choose
    between, and - for a name the corpus does mention - where.
    """
    candidates = tuple(
        entity_ref(graph, c.key, similarity=c.similarity)
        for c in resolution.candidates
    )
    return Diagnostics(
        span=resolution.mention,
        candidates=candidates,
        # A suggestion is a candidate the reporting floor let through. It is
        # the same data, named differently, because the page must present it as
        # something the user confirms rather than something already applied.
        suggestions=tuple(
            c for c in candidates if c.similarity is not None and c.similarity >= 0.90
        ),
        relation_vocabulary=relation_vocabulary(relation_map),
        presence=corpus_presence(resolution.mention, evidence_units)
        if evidence_units is not None
        else (),
    )


def for_relation_unavailable(
    graph: Graph, start_key: str, chain: tuple[str, ...], relation_map: RelationMap
) -> Diagnostics:
    """`RELATION_UNAVAILABLE`: the entity is known, the relation is not recorded for it."""
    return Diagnostics(
        start=entity_ref(graph, start_key),
        established=(neighbourhood(graph, start_key),),
        asked_relation=chain[0] if chain else None,
        relation_vocabulary=relation_vocabulary(relation_map),
    )


def for_no_path(
    graph: Graph,
    start_key: str,
    chain: tuple[str, ...],
    paths,
    goal_key: str | None,
    relation_map: RelationMap,
) -> Diagnostics:
    """`NO_PATH` / `PATH_MISSING_ATTRIBUTE`: the chain ran and landed elsewhere.

    `reached` is the honest content here - "could not join X to Y" is only
    useful next to where the traversal actually got, which is frequently a
    perfectly good set of endpoints that simply are not the one asked for.
    """
    ends: dict[str, None] = {}
    for path in paths:
        ends.setdefault(path.end, None)
    reached = [entity_ref(graph, key) for key in ends]
    return Diagnostics(
        start=entity_ref(graph, start_key),
        goal=None if goal_key is None else entity_ref(graph, goal_key),
        reached=tuple(reached[:_MAX_REACHED]),
        reached_count=len(reached),
        hops_completed=max((len(p.edges) for p in paths), default=0),
        asked_relation=chain[0] if chain else None,
        established=(neighbourhood(graph, start_key),),
        relation_vocabulary=relation_vocabulary(relation_map),
    )
