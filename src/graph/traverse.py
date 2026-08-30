"""Bounded, deterministic traversal. Plain BFS over a dict of lists.

Traversal is bidirectional because the corpus is asymmetric: the Iron-Ring Cartel
records its own victories on its page and The Silent Choir does not, so a search
that only follows out-edges answers one faction and abstains on the other. Every
returned path carries the edges it used, not just the node names - a path without
its evidence cannot be shown to a judge, and this project's whole claim is that
the evidence travels with the answer.

There is no scoring and no heuristic here. Paths come back in order of length,
and choosing between them is the query layer's job, made against the question's
own constraints (1b_007 needs an *accord*, which is a type filter, not a
shorter path).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

from src.graph.entities import canonical_key
from src.graph.schema import Edge, Graph


@dataclass(frozen=True)
class Path:
    """A traversal from one entity to another, with the evidence for each hop."""

    start: str
    edges: tuple[Edge, ...]

    @property
    def end(self) -> str:
        if not self.edges:
            return self.start
        last = self.edges[-1]
        return last.target if last.source == self._node_before_last() else last.source

    @property
    def nodes(self) -> tuple[str, ...]:
        current = self.start
        out = [current]
        for edge in self.edges:
            current = edge.target if edge.source == current else edge.source
            out.append(current)
        return tuple(out)

    @property
    def documents(self) -> tuple[str, ...]:
        """Every document the path relies on, in order, deduplicated."""
        return tuple(dict.fromkeys(edge.document for edge in self.edges))

    def _node_before_last(self) -> str:
        return self.nodes[-2] if len(self.nodes) > 1 else self.start

    def explain(self) -> str:
        lines = []
        current = self.start
        for edge in self.edges:
            nxt = edge.target if edge.source == current else edge.source
            arrow = "->" if edge.source == current else "<-"
            lines.append(f"  {current} {arrow}[{edge.relation}]{arrow} {nxt}")
            lines.append(f"      {edge.why()}")
            current = nxt
        return "\n".join(lines)


def find_paths(
    graph: Graph,
    start: str,
    goal: str | None = None,
    *,
    max_hops: int = 3,
    relation: str | None = None,
) -> list[Path]:
    """Breadth-first search from `start`, shortest paths first.

    Args:
        graph: The graph to search.
        start: Entity name or canonical key to begin from.
        goal: Entity to reach. When None, every node within `max_hops` is
            returned, which is what a "what can I reach from here" query needs.
        max_hops: Depth bound. Bounded because an unbounded search over a
            connected graph returns everything and answers nothing.
        relation: Restrict traversal to a single relation, when the question
            names one.

    Returns:
        Paths ordered by length. Empty when the goal is unreachable, which is a
        result - "no path" is different from "no answer", and the sufficiency
        layer needs to be able to tell them apart.
    """
    start_key = _resolve(graph, start)
    goal_key = _resolve(graph, goal) if goal else None
    if start_key is None or (goal is not None and goal_key is None):
        return []

    found: list[Path] = []
    queue: deque[tuple[str, tuple[str, ...], tuple[Edge, ...]]] = deque(
        [(start_key, (start_key,), ())]
    )

    while queue:
        node, visited, edges = queue.popleft()
        if len(edges) >= max_hops:
            continue
        for edge in graph.neighbours(node, relation):
            nxt = edge.target if edge.source == node else edge.source
            # Only cycles are pruned, never alternative routes. A per-search
            # `seen` set would keep just the first path to reach each node, and
            # for 1b_009 that silently returned the `belligerent_in` route
            # instead of the `victor_of` one - same length, half the evidence,
            # and the wrong relation for the question. "A path exists" is not
            # "the evidence the answer needs exists".
            if nxt in visited:
                continue
            path = Path(start_key, edges + (edge,))
            if goal_key is None or nxt == goal_key:
                found.append(path)
            queue.append((nxt, visited + (nxt,), edges + (edge,)))

    return sorted(found, key=lambda p: len(p.edges))


def _resolve(graph: Graph, name: str | None) -> str | None:
    """Exact match on the canonical key, or nothing (ADR-011).

    No fuzzy fallback. A mention that does not resolve is reported as
    unresolved so the caller can escalate or abstain; guessing produces a
    structurally perfect traversal to a confidently wrong answer, which is the
    worst failure this system has.
    """
    if name is None:
        return None
    key = canonical_key(name)
    return key if key in graph.nodes else None


def walk_relations(
    graph: Graph,
    start: str,
    relations: Sequence[str],
) -> list[Path]:
    """Follow one specific relation per hop, in order.

    WHY THIS EXISTS, AND WHY `find_paths` IS NOT ENOUGH
    ---------------------------------------------------
    `find_paths` answers "what can I reach", which is the wrong question once you
    know what you are looking for. Measured on the seven dev 1B questions, an
    unconstrained two-hop search returns between 5 and 87 candidate paths, and
    the shortest path that lands on the right answer is frequently wrong about
    *why*.

    `1b_005`, `1b_007` and `1b_022` all ask which conflict a faction won. The
    shortest path reaching the correct conflict goes through `belligerent_in` -
    the faction fought in it - while the answer key requires `victor_of`. Both
    edges exist, both are two hops, and both end on the same node. A selector
    that reads only the endpoint scores those correct while having retrieved
    evidence that does not support the claim: fighting in a war is not winning
    it.

    Constraining each hop to a named relation collapses 5-87 candidates to 1-14
    and makes the route auditable, because the relation sequence *is* the claim
    being made.

    Direction is deliberately not specified. The graph is asymmetric (the Silent
    Choir records no victories of its own, so its `victor_of` edge exists only on
    the conflict's page), and forcing a direction would lose exactly the reverse
    lookups sub-track 1B is about. The edge itself records which way it was
    written, so provenance survives.

    Args:
        graph: The graph to walk.
        start: Entity name or canonical key to begin from.
        relations: One relation name per hop, in order.

    Returns:
        Every path following that exact sequence. Empty when the sequence does
        not apply to this entity, which is a usable signal rather than an error:
        the sufficiency layer reads it as "the corpus does not assert this
        shape", distinct from "the entity is unknown".
    """
    start_key = _resolve(graph, start)
    if start_key is None or not relations:
        return []

    frontier: list[tuple[str, tuple[str, ...], tuple[Edge, ...]]] = [
        (start_key, (start_key,), ())
    ]

    for relation in relations:
        advanced: list[tuple[str, tuple[str, ...], tuple[Edge, ...]]] = []
        for node, visited, edges in frontier:
            for edge in graph.neighbours(node, relation):
                nxt = edge.target if edge.source == node else edge.source
                # Prune cycles only. Two edges may legitimately connect the same
                # pair - the Cartel's victory over the Leaden Accord is asserted
                # on both the Cartel's page and the Accord's - and dropping the
                # second would discard corroboration the conflict layer needs.
                if nxt in visited:
                    continue
                advanced.append((nxt, visited + (nxt,), edges + (edge,)))
        frontier = advanced
        if not frontier:
            return []

    return [Path(start_key, edges) for _, _, edges in frontier]
