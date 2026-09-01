"""Faithful port of the sister prototype's `graph/src/trust/conflicts.py`.

Arm B needs a conflict step, and using OURS for it turned out to confound the
comparison badly enough to invalidate two dev questions. This module exists so
arm B runs the sister router against the sister conflict rule, which is the
only honest way to attribute a difference to routing.

WHY OUR `src/query/conflict.py` COULD NOT STAND IN
----------------------------------------------------
MEASURED. Our `find_denial` is *paragraph-scoped*: it searches the subject's
page for a paragraph that names the object and matches a denial pattern. That
is right for the question our engine asks it ("is THIS specific claim
disputed?"), which it is only ever asked once, for `1b_009`.

Used as a general per-edge filter it over-fires. `wiki/the_iron_ring_cartel.md`
carries its victor list and its Purge-of-Blackport denial close enough
together that the paragraph naming The Leaden Accord also matches the denial
regex. So the Cartel's entirely uncontested `victor_of -> The Leaden Accord`
edge was excluded, emptying the candidate set and reporting `1b_007` and
`1b_022` as `not_found` in arm B. Those were harness artifacts, not routing
failures.

The sister rule is *structural* and does not have that failure mode:

  1. Only relations the corpus records from both ends (here: `victor_of`).
  2. Split an entity's edges of that relation into "stated on its own page"
     and "inferred from someone else's page".
  3. Zero own-page edges means the entity is SILENT - never a conflict.
     (This is F-014/ADR-015's rule: silence is not denial. The Silent Choir
     must not be flagged.)
  4. An inferred edge whose target is absent from the own-page targets is a
     structural exclusion.
  5. Same tier only - a cross-tier disagreement is `authority.py`'s job.

Because The Leaden Accord IS on the Cartel's own `Victor of` row, step 4 never
fires for it, and the edge survives. Only the Purge of Blackport - genuinely
absent from that row - is excluded.

Comparing this detector against ours on the merits is Phase 2 work. This
module is here to remove a confound from Phase 1, nothing more.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.graph.schema import Graph

#: The sister repo's `BIDIRECTIONAL_RELATIONS`. Extend only alongside a corpus
#: measurement; adding a relation here without one repeats F-007's mistake of
#: asserting a corpus shape instead of checking it.
BIDIRECTIONAL_RELATIONS = frozenset({"victor_of"})


@dataclass(frozen=True)
class RelationalConflict:
    relation: str
    entity: str
    excluded_target: str
    home_document: str
    tier: int
    status: str  # "excluded"


def find_relational_conflicts(
    graph: Graph, relations: frozenset[str] = BIDIRECTIONAL_RELATIONS
) -> list[RelationalConflict]:
    """Same-tier relational conflicts, structurally detected.

    Prose confirmation (the sister module's step 6, which upgrades `excluded`
    to `denies`) is deliberately not ported: it changes only the label, never
    whether the path is excluded, so it cannot affect a routing measurement.
    """
    findings: list[RelationalConflict] = []

    for relation in relations:
        for node in graph.page_backed:
            edges = [
                e
                for e in graph.out_edges(node.key, relation)
                if e.assertion == "asserts"
            ]
            if not edges:
                continue

            own_edges = [e for e in edges if e.document == node.page]
            if not own_edges:
                continue  # silent on this relation - not a conflict

            own_targets = {e.target for e in own_edges}
            reference_tier = own_edges[0].tier

            for edge in edges:
                if edge.document == node.page or edge.target in own_targets:
                    continue
                if edge.tier != reference_tier:
                    continue  # cross-tier is authority ranking, not this
                findings.append(
                    RelationalConflict(
                        relation=relation,
                        entity=node.key,
                        excluded_target=edge.target,
                        home_document=node.page,
                        tier=reference_tier,
                        status="excluded",
                    )
                )

    return findings


def excluded_pairs(graph: Graph) -> set[tuple[str, str]]:
    """(source, target) pairs arm B must not route through."""
    return {(c.entity, c.excluded_target) for c in find_relational_conflicts(graph)}
