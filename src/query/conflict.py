"""Same-tier contradiction detection - the piece `config/authority.yaml`
promises exists here.

Authority tiers rank *documents*: codex over wiki over chronicles over
ephemera. They cannot rank two wiki pages against each other, and `1b_009` is
exactly that case - `wiki/the_purge_of_blackport.md` names the Iron-Ring
Cartel as victor; `wiki/the_iron_ring_cartel.md` records participation in the
same conflict and, in prose, explicitly declines to call it a victory. Both
are tier 2. ADR-013's tier model was measured against dated attribute claims
and does not cover this shape, and the instruction for this phase is explicit:
do not resolve it by tier, because there is no tier difference to resolve it
with.

**Silence is not a conflict.** `1b_005` and `1b_022` have the identical graph
shape - a faction's own page records it as a belligerent in a war, says
nothing about victory, and the war's own page names it victor - and that is
not a contradiction, because the faction's page never claims otherwise. What
makes `1b_009` different is not structural (both are "silent" at the level of
infobox edges, since the graph has no `denies` edges at all yet - see
ADR-016). It is a sentence: "This record establishes participation without
assigning the Cartel the status of victor." Distinguishing the two therefore
requires reading that sentence, which is what this module does - a small,
closed, measured regex over prose, in the same spirit as `cells.py`'s
abstention pattern, not a general claim extractor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.graph.schema import Edge, Graph

#: Words that mark a sentence as being ABOUT victory - the pattern must find
#: one of these near a negation to count as a denial. Kept explicit and
#: closed, for the same reason `1b_009`'s answer key keeps its own
#: `assertion_markers` list explicit: a rule a reviewer can read and disagree
#: with, rather than one that has to be reverse-engineered from behaviour.
_VICTORY_WORDS = r"(?:victor|victory|victorious|winner)"

#: A negation within ~80 characters of a victory word, in the same paragraph
#: as a mention of the disputed object. Verified against the one passage this
#: exists to catch: "establishes participation without assigning the Cartel
#: the status of victor." Also checked NOT to fire on
#: `wiki/the_silent_choir.md`, which never uses any victory word at all in
#: connection with The War of Drowned Light - that page is silent, not
#: denying, and the absence of a victory word is exactly why this pattern
#: correctly does not match it.
_DENIAL_RE = re.compile(
    rf"\bwithout\b[^.]{{0,80}}\b{_VICTORY_WORDS}\b"
    rf"|\b(?:does not|did not|is not|are not)\b[^.]{{0,60}}\b{_VICTORY_WORDS}\b",
    re.I,
)


@dataclass(frozen=True)
class Denial:
    """One paragraph that explicitly declines to assert a claim."""

    document: str
    tier: int
    quote: str


@dataclass(frozen=True)
class ConflictReport:
    """What is known about whether `relation(subject, object)` is disputed."""

    subject_key: str
    relation: str
    object_key: str
    asserting_edges: tuple[Edge, ...]
    denial: Denial | None

    @property
    def status(self) -> str:
        if not self.asserting_edges:
            return "no_assertion"
        if self.denial is None:
            return "uncontested"
        if self.denial.tier == self.asserting_edges[0].tier:
            return "unresolved_same_tier"
        return "resolved_by_tier"

    @property
    def must_surface(self) -> bool:
        return self.status == "unresolved_same_tier"


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.replace("**", "").split("\n\n") if p.strip()]


def find_denial(
    graph: Graph, corpus_path, subject_key: str, object_key: str
) -> Denial | None:
    """Search `subject_key`'s own page for a paragraph denying its tie to `object_key`.

    Only the subject's *own* page is searched - a denial is only meaningful as
    a claim the subject's own record makes about itself. `object_key`'s
    display name is matched with and without a leading "The", the same
    article-drop `route.py`'s gazetteer uses, because the corpus does not
    write the article consistently.
    """
    node = graph.nodes.get(subject_key)
    if node is None or node.page is None:
        return None

    path = corpus_path / node.page
    if not path.is_file():
        return None

    object_node = graph.nodes.get(object_key)
    names = [object_node.name] if object_node else []
    if names and names[0].lower().startswith("the "):
        names.append(names[0][4:])

    text = path.read_text(encoding="utf-8")
    for paragraph in _paragraphs(text):
        lower = paragraph.lower()
        if not any(name.lower() in lower for name in names):
            continue
        if _DENIAL_RE.search(paragraph):
            return Denial(document=node.page, tier=_tier_of(graph, subject_key), quote=paragraph)
    return None


def _tier_of(graph: Graph, key: str) -> int:
    """The tier of `key`'s own page.

    Read off an edge whose `document` is that page specifically - a node has
    edges sourced from *other* pages too (an in-edge from whoever names it),
    and those carry the other page's tier, not this one's. Every edge
    `build.py` writes carries the tier of the unit it was parsed from, so this
    needs no second lookup table, only the right edge.
    """
    node = graph.nodes.get(key)
    for edge in graph.neighbours(key):
        if node and edge.document == node.page:
            return edge.tier
    for edge in graph.neighbours(key):
        return edge.tier
    return 0


def check_conflict(
    graph: Graph, corpus_path, subject_key: str, relation: str, object_key: str
) -> ConflictReport:
    """Everything known about whether `relation(subject_key, object_key)` is disputed."""
    asserting = tuple(
        e
        for e in graph.out_edges(subject_key, relation)
        if e.target == object_key and e.assertion == "asserts"
    )
    denial = find_denial(graph, corpus_path, subject_key, object_key)
    return ConflictReport(subject_key, relation, object_key, asserting, denial)
