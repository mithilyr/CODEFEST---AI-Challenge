"""Cross-collection attestation: what the rest of the archive says about an edge.

The graph is built from wiki infobox rows and nothing else, and that is correct
- only wiki pages carry infobox pipe tables, so the other 167 documents cannot
contribute edges (ADR-027 records the check). What they *can* do is attest: a
codex passage or a chronicle scene that names both ends of an edge is
independent evidence that the edge describes something the archive talks about
outside the one table it was parsed from.

This module is a lookup over evidence already ingested, not a second retrieval
system. Every unit it returns already carries its canonical document id, its
locator and its authority tier from `src/ingest/pipeline.py`; nothing is
re-derived here.

Three rules, each of them a constraint inherited rather than invented:

- **Exact names only.** The scan uses `route.py`'s gazetteer - the same surface
  forms, the same article-drop, the same epithet aliases - so ADR-011's rule
  that resolution never picks a winner fuzzily holds here unchanged.
- **An ambiguous surface form is reported, not resolved.** Where one surface
  form maps to more than one node key, it is dropped from the scan and recorded
  in `CorroborationIndex.ambiguous_surfaces`. Silently choosing would attach a
  citation to the wrong person, which is the failure this project exists to
  prevent.
- **Co-mention is not proof of the relation.** A paragraph naming both ends is
  evidence that the archive discusses them together, and the page says exactly
  that ("also attested in") rather than claiming the passage asserts the edge.
  F-014's lesson in a new place: do not read more into a source than it says.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from src.graph.schema import Edge, Graph
from src.ingest.pipeline import EvidenceUnit
from src.query.resolve import EntityResolver
from src.query.route import build_gazetteer

#: How many attestations to attach to one edge. The answer page renders every
#: one of them, and an edge attested in 80 chronicle paragraphs would bury the
#: hop it belongs to. Ordering is deterministic (see `_rank`), so the cap keeps
#: the most authoritative rather than an arbitrary slice.
DEFAULT_CAP = 3

#: Collections whose units may corroborate. The wiki is excluded on purpose:
#: the edge was parsed from a wiki page, so a wiki paragraph restating it is
#: the same source agreeing with itself, not independent attestation.
#: Kept as the default for callers that pass no relation map, and as the value
#: `tests/test_corroborate.py` asserts against for the shipped corpus. The live
#: value comes from `sources.corroborates` in config/relations.yaml (ADR-035);
#: this literal is what that key ships as, not a second source of truth.
CORROBORATING_COLLECTIONS = frozenset({"chronicles", "codex", "ephemera"})


@dataclass(frozen=True)
class Attestation:
    """One non-wiki passage naming both ends of an edge."""

    evidence_id: str
    document: str
    collection: str
    locator: str
    tier: int
    quote: str


@dataclass
class CorroborationIndex:
    """Attestations for every (subject, object) pair the graph connects."""

    #: frozenset({subject_key, object_key}) -> attestations, already capped.
    pairs: dict[frozenset, tuple[Attestation, ...]] = field(default_factory=dict)
    #: Surface forms dropped because they name more than one node. Reported,
    #: never resolved (ADR-011).
    ambiguous_surfaces: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: Units scanned, for the measurement in ADR-027.
    units_scanned: int = 0
    cap: int = DEFAULT_CAP

    def for_edge(self, edge: Edge) -> tuple[Attestation, ...]:
        return self.pairs.get(frozenset((edge.source, edge.target)), ())

    def corroborated_edges(self, graph: Graph) -> list[Edge]:
        return [e for e in graph.edges if self.for_edge(e)]


def _rank(attestation: Attestation) -> tuple:
    """Sort key: highest authority first, then stable by document and locator.

    Tier ascends with distance from the record (tier 1 is the codex), so a
    plain ascending sort puts the most authoritative attestation first. The
    remaining fields make the cap reproducible rather than dependent on the
    order units happened to be ingested in.
    """
    return (attestation.tier, attestation.document, attestation.locator)


def scan_surfaces(graph: Graph, resolver: EntityResolver | None = None):
    """(compiled pattern, surface -> key, ambiguous) for the gazetteer.

    The gazetteer is `route.py`'s, so the surface forms recognised here are
    exactly the ones question text is scanned against. The scan strategy
    differs - one combined alternation rather than `extract_mentions`' per
    surface compile - because this runs over the whole corpus rather than over
    one question, and that function compiles its patterns per call. Ordering
    the alternation longest-first reproduces its longest-match rule.
    """
    resolver = resolver or EntityResolver(graph)
    by_surface: dict[str, set[str]] = defaultdict(set)
    for surface, key in build_gazetteer(graph, resolver):
        by_surface[surface.lower()].add(key)

    surface_to_key: dict[str, str] = {}
    ambiguous: dict[str, tuple[str, ...]] = {}
    for surface, keys in by_surface.items():
        if len(keys) == 1:
            surface_to_key[surface] = next(iter(keys))
        else:
            ambiguous[surface] = tuple(sorted(keys))

    ordered = sorted(surface_to_key, key=len, reverse=True)
    pattern = re.compile(r"\b(" + "|".join(re.escape(s) for s in ordered) + r")\b", re.I)
    return pattern, surface_to_key, ambiguous


def build_index(
    graph: Graph,
    evidence: list[EvidenceUnit],
    *,
    cap: int = DEFAULT_CAP,
    resolver: EntityResolver | None = None,
    collections: frozenset[str] | None = None,
) -> CorroborationIndex:
    """Attach non-building passages to the pairs of entities the graph connects.

    One pass over the corroborating units, not one pass per edge: the pairs a
    unit can attest are exactly the pairs among the entities it names, so the
    work is proportional to the corpus rather than to corpus x edges.

    Args:
        collections: Which collections may attest. Read from
            `sources.corroborates` in config/relations.yaml when omitted
            (ADR-035), so a corpus with differently named folders needs a
            config edit rather than a code edit.
    """
    if collections is None:
        from src.graph.build import load_relation_map

        collections = load_relation_map().corroborates or CORROBORATING_COLLECTIONS
    pattern, surface_to_key, ambiguous = scan_surfaces(graph, resolver)
    wanted = {
        frozenset((e.source, e.target)) for e in graph.edges if e.source != e.target
    }

    found: dict[frozenset, list[Attestation]] = defaultdict(list)
    scanned = 0
    for unit in evidence:
        if unit.collection not in collections:
            continue
        if unit.kind not in ("paragraph", "page"):
            continue
        scanned += 1
        keys = {surface_to_key[m.group(1).lower()] for m in pattern.finditer(unit.text)}
        if len(keys) < 2:
            continue
        ordered_keys = sorted(keys)
        for i, first in enumerate(ordered_keys):
            for second in ordered_keys[i + 1 :]:
                pair = frozenset((first, second))
                if pair in wanted:
                    found[pair].append(
                        Attestation(
                            evidence_id=unit.evidence_id,
                            document=unit.canonical_doc_id,
                            collection=unit.collection,
                            locator=unit.locator,
                            tier=unit.tier,
                            quote=unit.text,
                        )
                    )

    return CorroborationIndex(
        pairs={p: tuple(sorted(a, key=_rank)[:cap]) for p, a in found.items()},
        ambiguous_surfaces=ambiguous,
        units_scanned=scanned,
        cap=cap,
    )


def summary(graph: Graph, index: CorroborationIndex) -> str:
    """The ADR-027 measurement, printed."""
    corroborated = index.corroborated_edges(graph)
    by_collection: dict[str, int] = defaultdict(int)
    edges_by_collection: dict[str, set] = defaultdict(set)
    for edge in corroborated:
        for att in index.for_edge(edge):
            by_collection[att.collection] += 1
            edges_by_collection[att.collection].add(
                (edge.source, edge.relation, edge.target)
            )

    share = 100 * len(corroborated) / len(graph.edges) if graph.edges else 0.0
    lines = [
        f"units scanned        : {index.units_scanned}",
        f"edges                : {len(graph.edges)}",
        f"corroborated edges   : {len(corroborated)}  ({share:.1f}%)",
        f"attestation cap/edge : {index.cap}",
        "attestations attached, by collection:",
    ]
    for collection in sorted(by_collection, key=lambda c: -by_collection[c]):
        lines.append(
            f"    {collection:12} {by_collection[collection]:4}"
            f"   on {len(edges_by_collection[collection])} distinct edges"
        )
    if index.ambiguous_surfaces:
        lines.append(
            f"ambiguous surfaces   : {len(index.ambiguous_surfaces)}"
            " (reported, never resolved)"
        )
        for surface, keys in sorted(index.ambiguous_surfaces.items()):
            lines.append(f"    {surface!r} -> {list(keys)}")
    return "\n".join(lines)


def main() -> None:
    from src.graph.build import build_graph
    from src.ingest.pipeline import ingest

    result = ingest()
    graph = build_graph(result)
    index = build_index(graph, result.evidence)
    print(summary(graph, index))


if __name__ == "__main__":
    main()
