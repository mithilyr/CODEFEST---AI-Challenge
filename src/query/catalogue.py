"""What the system can be asked about, as plain data for the front page.

The measured problem this answers is upstream of any single decline: a judge at
the live demo has no way to know what the corpus contains, so their first
question is a guess, and a guess against a closed 117-entity graph most likely
misses. `python -m comparison.harness` puts a number on it - the four templates
match no route shape on 35 of 49 independently written questions.

Publishing the entity list and the relation vocabulary does not widen what the
system can answer by one question. It stops the judge discovering the boundary
by failing at it, which is the difference between a system that looks narrow
and one that looks broken.

Returned as plain dicts so `src/ui/render.py` can render it while importing
nothing from `src.query` or `src.graph` - the property ADR-018's tests pin.
"""

from __future__ import annotations

from collections import Counter

from src.graph.build import RelationMap
from src.graph.schema import Graph


def build_catalogue(graph: Graph, relation_map: RelationMap) -> dict:
    """Every entity and every relation, with the counts that bound them."""
    entities = [
        {
            "key": node.key,
            "name": node.name,
            "type": node.entity_type or "unrecorded",
            # A node with no page exists only as a link target. Shown, because
            # "we know the name but no page documents it" is a real and
            # different state from "we have its record" (ADR-016).
            "page": node.page,
        }
        for node in sorted(graph.nodes.values(), key=lambda n: n.name.lower())
    ]

    edges_by_relation = Counter(edge.relation for edge in graph.edges)
    relations = []
    for name in sorted(
        set(relation_map.forward.values()) | set(relation_map.reverse.values())
    ):
        relations.append(
            {
                "name": name,
                "inverse": relation_map.inverses.get(name),
                "edges": edges_by_relation.get(name, 0),
                "fields": sorted(
                    f for f, r in relation_map.forward.items() if r == name
                )
                + sorted(f for f, r in relation_map.reverse.items() if r == name),
                # Question vocabulary, separate from field names by ADR-024 -
                # what a person says, not what the corpus writes.
                "cues": sorted(relation_map.question_cues.get(name, [])),
            }
        )

    by_type = Counter(e["type"] for e in entities)
    return {
        "entities": entities,
        "relations": relations,
        "counts": {
            "entities": len(entities),
            "edges": len(graph.edges),
            "relations": len(relations),
            "page_backed": sum(1 for e in entities if e["page"]),
            "by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
        },
    }
