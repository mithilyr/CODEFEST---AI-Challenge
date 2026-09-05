"""The whole graph as one SVG. No dependency, no CDN, no JavaScript.

WHY NOT vis-network
---------------------
The sister prototype renders this with vis-network loaded from a CDN. It looks
good and it adds no *Python* dependency, which is how it gets past a rule like
ours - but it fails two of this project's own constraints:

  1. **It needs the network at demo time.** CLAUDE.md says never record the
     demo against a cold cache, for exactly this reason. A CDN that is slow,
     blocked by conference wifi, or simply down takes the picture with it.
  2. **Nobody here could modify it in the room.** The binding competition
     constraint is that any team member can explain and change any part of the
     submission on demand. A force-directed layout we did not write and cannot
     step through is a liability under questioning.

So the layout is computed here, in about sixty lines of arithmetic anyone on
the team can read, and the output is a static SVG the browser only has to
draw. It works offline, it works with JavaScript disabled, and it renders
identically every time.

DETERMINISM
-------------
The layout is seeded from each node's own key rather than from a random number
generator, so the same graph always produces the same picture. That matters
for a screenshot in the report matching what a judge sees when they run it,
and it is the same reason the rest of this project avoids unseeded randomness.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from src.graph.schema import Graph

WIDTH = 1100
HEIGHT = 760
ITERATIONS = 200

#: `Node.entity_type` values, plus "unknown" for the edge-only nodes that are
#: named as a link target but have no wiki page of their own.
TYPE_COLOURS = {
    "character": "#7a3b2e",
    "faction": "#3c6e47",
    "location": "#3b5a7a",
    "creature": "#a85b1f",
    "conflict": "#6a4c93",
    "artifact": "#2f7a6e",
    "unknown": "#8a8172",
}


@dataclass
class Point:
    x: float
    y: float


def _seeded_position(key: str) -> Point:
    """A stable starting position derived from the node's own key.

    Not random: `hashlib` over the key gives the same answer on every run and
    every machine, so the drawing is reproducible. An unseeded RNG would make
    the report's screenshot and the judge's screen disagree.
    """
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    angle = (int.from_bytes(digest[:4], "big") / 0xFFFFFFFF) * 2 * math.pi
    radius = 0.25 + (int.from_bytes(digest[4:8], "big") / 0xFFFFFFFF) * 0.7
    return Point(
        WIDTH / 2 + math.cos(angle) * radius * WIDTH * 0.42,
        HEIGHT / 2 + math.sin(angle) * radius * HEIGHT * 0.42,
    )


def layout(graph: Graph, iterations: int = ITERATIONS) -> dict[str, Point]:
    """Fruchterman-Reingold: edges pull, every pair pushes, motion cools.

    Plain arithmetic on 117 nodes and 261 edges. No library, and nothing here
    that a teammate could not step through in a debugger.
    """
    keys = sorted(graph.nodes)
    positions = {key: _seeded_position(key) for key in keys}
    if not keys:
        return positions

    area = WIDTH * HEIGHT
    # MEASURED. The textbook k = sqrt(area/n) wants ~84px between every pair
    # of 117 nodes, which needs more room than this canvas has, so repulsion
    # wins everywhere and 42 of 117 nodes ended up pressed against the
    # boundary clamp with their labels overlapping along the top edge.
    # Swept 0.35/0.5/0.65/0.8: 0.5 leaves 2 nodes on the boundary (from 42)
    # while keeping the closest pair furthest apart at 17.7px, so it is both
    # the least clamped and the least crowded.
    k = math.sqrt(area / len(keys)) * 0.5
    temperature = WIDTH / 8

    adjacency = [
        (e.source, e.target)
        for e in graph.edges
        if e.source in positions and e.target in positions
    ]

    for _ in range(iterations):
        disp = {key: Point(0.0, 0.0) for key in keys}

        for i, a in enumerate(keys):
            for b in keys[i + 1 :]:
                dx = positions[a].x - positions[b].x
                dy = positions[a].y - positions[b].y
                distance = max(math.hypot(dx, dy), 0.01)
                force = (k * k) / distance
                ux, uy = dx / distance, dy / distance
                disp[a].x += ux * force
                disp[a].y += uy * force
                disp[b].x -= ux * force
                disp[b].y -= uy * force

        for source, target in adjacency:
            dx = positions[source].x - positions[target].x
            dy = positions[source].y - positions[target].y
            distance = max(math.hypot(dx, dy), 0.01)
            force = (distance * distance) / k
            ux, uy = dx / distance, dy / distance
            disp[source].x -= ux * force
            disp[source].y -= uy * force
            disp[target].x += ux * force
            disp[target].y += uy * force

        # A weak pull toward the middle. Without it, repulsion pushes the
        # loosely-connected nodes outward until the boundary clamp is the only
        # thing holding them, and they pile into a line along the top edge with
        # their labels overlapping. Gravity keeps the clamp from doing any real
        # work, which is what makes the drawing legible rather than merely
        # correct.
        for key in keys:
            p = positions[key]
            disp[key].x += (WIDTH / 2 - p.x) * 0.03
            disp[key].y += (HEIGHT / 2 - p.y) * 0.03

        for key in keys:
            d = disp[key]
            magnitude = max(math.hypot(d.x, d.y), 0.01)
            step = min(magnitude, temperature)
            p = positions[key]
            p.x = min(WIDTH - 60, max(60, p.x + (d.x / magnitude) * step))
            p.y = min(HEIGHT - 40, max(40, p.y + (d.y / magnitude) * step))

        temperature = max(temperature * 0.95, 0.5)

    return positions


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_svg(graph: Graph, positions: dict[str, Point] | None = None) -> str:
    """The graph as one self-contained SVG element.

    Every edge carries its source document in a `<title>`, so hovering a line
    says which file asserted it. That is the same provenance rule the answer
    page follows: a claim on screen must be traceable to the document it came
    from, and a picture is not exempt.
    """
    positions = positions if positions is not None else layout(graph)
    parts = [
        f'<svg viewBox="0 0 {WIDTH} {HEIGHT}" width="100%" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="The Ashen Era knowledge graph: '
        f'{len(graph.nodes)} entities, {len(graph.edges)} edges">',
        "<rect width='100%' height='100%' fill='#faf8f4'/>",
        "<g stroke='#b9b2a6' stroke-width='0.8' opacity='0.75'>",
    ]

    for edge in graph.edges:
        if edge.source not in positions or edge.target not in positions:
            continue
        a, b = positions[edge.source], positions[edge.target]
        dashes = "" if edge.assertion == "asserts" else " stroke-dasharray='4 3'"
        title = _escape(f"{edge.relation} - {edge.document} ({edge.field_name}): {edge.raw}")
        parts.append(
            f"<line x1='{a.x:.1f}' y1='{a.y:.1f}' x2='{b.x:.1f}' y2='{b.y:.1f}'"
            f"{dashes}><title>{title}</title></line>"
        )
    parts.append("</g>")

    for key, node in sorted(graph.nodes.items()):
        if key not in positions:
            continue
        p = positions[key]
        colour = TYPE_COLOURS.get(node.entity_type or "unknown", TYPE_COLOURS["unknown"])
        page = node.page or "no wiki page of its own - named only as a link target"
        radius = 6 if node.page else 4
        parts.append(
            f"<circle cx='{p.x:.1f}' cy='{p.y:.1f}' r='{radius}' fill='{colour}' "
            f"stroke='#faf8f4' stroke-width='1.2'>"
            f"<title>{_escape(node.name)} ({node.entity_type or 'unknown type'})\n{_escape(page)}</title>"
            f"</circle>"
        )
        parts.append(
            f"<text x='{p.x:.1f}' y='{p.y - radius - 3:.1f}' font-size='7.5' "
            f"text-anchor='middle' fill='#3a352d' "
            f"font-family='ui-sans-serif,system-ui,sans-serif'>{_escape(node.name)}</text>"
        )

    parts.append("</svg>")
    return "".join(parts)


def legend_html() -> str:
    swatches = "".join(
        f"<span style='display:inline-flex;align-items:center;gap:.4rem;margin-right:1rem'>"
        f"<span style='width:.7rem;height:.7rem;border-radius:50%;background:{colour}'></span>"
        f"{name}</span>"
        for name, colour in TYPE_COLOURS.items()
    )
    return (
        f"<p style='font-size:.85rem;color:#5b554a'>{swatches}</p>"
        "<p style='font-size:.85rem;color:#5b554a'>"
        "Larger dots have a wiki page of their own; smaller ones are named only as a "
        "link target. Dashed lines are non-asserting edges. Hover any line for the "
        "document that asserted it.</p>"
    )
