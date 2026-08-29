"""Nodes, edges and the provenance every edge has to carry.

The design rule is one sentence: **an edge must be able to answer "why do you
believe this?"** without consulting anything but itself. That is not decoration.
The failure this project exists to prevent is a confidently wrong answer with
real-looking citations attached, and the only defence is that every hop in a path
can be traced to the row it came from.

So an edge carries its source document, the field name and row index it was read
from, the raw cell text, the authority tier of the source, and whether the claim
was asserted, denied or framed as secret. `assertion` in particular is not
optional: ADR-013's correction and F-014 both turn on the difference between a
page that denies a claim and a page that is silent about it, and a graph that
stores only assertions cannot represent the first.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Node:
    """One entity. `key` is the canonical form; `name` is as the corpus wrote it."""

    key: str
    name: str
    #: character | faction | location | creature | conflict | artifact | None
    entity_type: str | None = None
    #: The wiki page this entity has, where it has one. Entities that appear only
    #: as link targets are real nodes with no page - roughly a third of them.
    page: str | None = None

    @property
    def is_page_backed(self) -> bool:
        return self.page is not None


@dataclass(frozen=True)
class Edge:
    """One relation between two entities, with the evidence for it.

    Everything after `target` exists so the edge can be audited. Dropping any of
    it makes some question unanswerable: without `field` you cannot explain which
    row produced the edge, without `tier` the conflict resolver cannot rank
    sources, without `assertion` a denial reads as an assertion.
    """

    source: str
    relation: str
    target: str

    # -- provenance ---------------------------------------------------------
    #: Canonical document id, e.g. "wiki/the_iron_ring_cartel.md".
    document: str
    #: The infobox field name the edge was read from, e.g. "Victor of".
    field_name: str
    #: 0-based row index within the infobox, so repeated field names stay
    #: distinguishable. `the_ashen_vanguard.md` has three `Belligerent` rows.
    row: int
    #: The cell exactly as written, kept so a human can check the parse.
    raw: str
    #: Which of the twelve ADR-010 handlers produced this edge.
    template: str
    #: Source authority tier, from config/authority.yaml.
    tier: int
    #: asserts | denies | secret
    assertion: str = "asserts"
    #: How the target was identified. "link" is a `[[wiki link]]`.
    #: "exact_name_match" means the cell named the entity in plain text and the
    #: name matched a known entity exactly after normalisation - never fuzzily.
    #: Recorded because the two carry different confidence and a reviewer should
    #: be able to filter on it.
    extraction: str = "link"

    # -- qualifiers ---------------------------------------------------------
    #: In-world year attached to the edge, e.g. 356 from ", since 356 AS".
    year: int | None = None
    #: How the year relates to the fact: "since" | "in".
    year_kind: str | None = None
    #: Second argument of a ternary fact - the faction someone fought *for*.
    qualifier: str | None = None
    #: True when the edge was derived by inverting a cell read on the other page.
    inferred_inverse: bool = False

    def why(self) -> str:
        """One line a human can check against the corpus."""
        where = f"{self.document} | {self.field_name} (row {self.row})"
        return f"{where}: {self.raw!r} [{self.template}, tier {self.tier}]"


@dataclass
class Graph:
    """Adjacency over `Edge`, with no database underneath it.

    125 entities and a few hundred edges is a Python dict. A graph database here
    would be a dependency a teammate would have to defend to a judge, in exchange
    for nothing measurable at this size.
    """

    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    _out: dict[str, list[Edge]] = field(default_factory=lambda: defaultdict(list))
    _in: dict[str, list[Edge]] = field(default_factory=lambda: defaultdict(list))
    #: Field names seen in the corpus that config/relations.yaml does not map.
    #: Surfaced rather than swallowed: an unmapped field is a lost relation.
    unmapped_fields: dict[str, int] = field(default_factory=dict)

    def add_node(self, node: Node) -> None:
        """Add a node, preferring a page-backed record over an edge-only one."""
        existing = self.nodes.get(node.key)
        if existing is None or (node.is_page_backed and not existing.is_page_backed):
            self.nodes[node.key] = node

    def add_edge(self, edge: Edge) -> None:
        self.edges.append(edge)
        self._out[edge.source].append(edge)
        self._in[edge.target].append(edge)

    def out_edges(self, key: str, relation: str | None = None) -> list[Edge]:
        edges = self._out.get(key, [])
        return [e for e in edges if relation is None or e.relation == relation]

    def in_edges(self, key: str, relation: str | None = None) -> list[Edge]:
        edges = self._in.get(key, [])
        return [e for e in edges if relation is None or e.relation == relation]

    def neighbours(self, key: str, relation: str | None = None) -> list[Edge]:
        """Edges touching `key` in either direction.

        Traversal has to be bidirectional because the corpus is: the Iron-Ring
        Cartel records its own victories and The Silent Choir does not, so a
        query that only follows out-edges answers one and abstains on the other.
        """
        return self.out_edges(key, relation) + self.in_edges(key, relation)

    @property
    def page_backed(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.is_page_backed]

    @property
    def edge_only(self) -> list[Node]:
        return [n for n in self.nodes.values() if not n.is_page_backed]

    def summary(self) -> str:
        by_relation: dict[str, int] = defaultdict(int)
        for edge in self.edges:
            by_relation[edge.relation] += 1
        isolated = sum(
            1 for k in self.nodes if not self._out.get(k) and not self._in.get(k)
        )
        lines = [
            f"entities             : {len(self.nodes)}",
            f"    page-backed      : {len(self.page_backed)}",
            f"    edge-only        : {len(self.edge_only)}",
            f"    isolated         : {isolated}",
            f"edges                : {len(self.edges)}",
        ]
        lines += [
            f"    {relation:<20} {count}"
            for relation, count in sorted(by_relation.items(), key=lambda x: -x[1])
        ]
        if self.unmapped_fields:
            lines.append(f"unmapped field names : {len(self.unmapped_fields)}")
            for name, count in sorted(
                self.unmapped_fields.items(), key=lambda x: -x[1]
            ):
                lines.append(f"    {name} ({count})")
        return "\n".join(lines)
