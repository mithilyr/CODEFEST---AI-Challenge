"""Evidence sufficiency: naming exactly why a traversal did or didn't answer.

The instruction this module exists to satisfy is specific: do not collapse
every non-answer into "answer seems incomplete." A judge asking "why didn't it
answer this" deserves one of a small, named set of reasons, each distinguished
because each demands a different fix:

- an unresolved mention is a typo or a name the corpus doesn't have at all;
- an entity outside structured coverage is real (it is *in* the corpus text)
  but the wiki-infobox graph never made it a node, because it is only ever
  named in prose;
- a relation unavailable at the very first hop means the question asked for a
  fact of a kind this entity's page never records;
- no path means the first hop worked but the chain didn't complete;
- a path with a missing attribute is a type filter that ran out of candidates;
- sufficient evidence is a path plus its provenance;
- an abstention is the corpus itself declining to answer, which is not the
  same as the graph having nothing (F-014's sibling case for relations rather
  than attributes);
- conflicting evidence is `src/query/conflict.py`'s job to detect, not this
  module's.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.graph.build import RelationMap, infobox_rows
from src.graph.cells import parse_cell
from src.graph.entities import canonical_key
from src.graph.schema import Graph
from src.query.resolve import ResolutionStatus


class EvidenceStatus(str, Enum):
    #: No template's trigger phrase matched at all - a routing-stage miss,
    #: logged rather than guessed at (see `route.py`'s `RouteMiss`).
    NO_TEMPLATE_MATCH = "no_template_match"
    UNRESOLVED_ENTITY = "unresolved_entity"
    AMBIGUOUS_ENTITY = "ambiguous_entity"
    OUTSIDE_STRUCTURED_COVERAGE = "outside_structured_coverage"
    RELATION_UNAVAILABLE = "relation_unavailable"
    NO_PATH = "no_path"
    PATH_MISSING_ATTRIBUTE = "path_missing_attribute"
    SUFFICIENT = "sufficient"
    ABSTENTION = "abstention"
    CONFLICTING_EVIDENCE = "conflicting_evidence"

    @property
    def is_answerable(self) -> bool:
        return self in {EvidenceStatus.SUFFICIENT, EvidenceStatus.CONFLICTING_EVIDENCE}


def resolution_status(resolution) -> EvidenceStatus | None:
    """Map a failed `Resolution` to its evidence status, or None if it succeeded."""
    if resolution.resolved:
        return None
    if resolution.status == ResolutionStatus.AMBIGUOUS:
        return EvidenceStatus.AMBIGUOUS_ENTITY
    return EvidenceStatus.UNRESOLVED_ENTITY


def mentioned_in_corpus(mention: str, evidence_units) -> bool:
    """True if `mention` appears anywhere in the ingested text.

    Distinguishes "the corpus never says this" (UNRESOLVED_ENTITY, likely a
    typo or an invented name) from "the corpus says this, but not on a wiki
    infobox" (OUTSIDE_STRUCTURED_COVERAGE, the honest limit of a graph built
    only from structured cells - ADR-016).
    """
    needle = mention.lower()
    return any(needle in unit.text.lower() for unit in evidence_units)


def classify_traversal(
    graph: Graph, start_key: str, chain: tuple[str, ...], paths: list
) -> EvidenceStatus:
    """RELATION_UNAVAILABLE vs NO_PATH: does the chain fail at hop one, or later?

    `walk_relations` itself returns an empty list either way (by design - see
    its docstring); the distinction is reconstructed here because the two
    reasons call for different remedies. Zero edges of `chain[0]` touching
    `start_key` at all means this entity's page never expresses that relation;
    at least one such edge, with the full chain still failing, means the
    relation exists here but does not lead where the question needs.
    """
    if paths:
        return EvidenceStatus.SUFFICIENT
    if not graph.neighbours(start_key, chain[0]):
        return EvidenceStatus.RELATION_UNAVAILABLE
    return EvidenceStatus.NO_PATH


def filter_endpoints(
    graph: Graph,
    paths: list,
    *,
    entity_type: str | None,
    word: str | None,
) -> tuple[list, EvidenceStatus]:
    """Narrow `paths` to endpoints matching the question's type hint.

    Two filters, asymmetric on purpose, because a type word extracted from
    free text is a hint and the two filters differ in how much a false
    negative there should cost (ADR-009: type coverage is 26/95 titles, so
    most edge-only nodes carry no type at all):

    1. **Coarse type**, applied unconditionally. Keeps a candidate whose
       `entity_type` matches, *or* is unknown (`None`) - a definite mismatch
       is excluded, an absence of information is not, because most
       non-page-backed nodes (most of `1b_006`'s fourteen answers) simply
       have no recorded type. Because unknown types already pass, letting
       this filter actually empty the set means every remaining candidate
       carries a *recorded, contradicting* type - a real finding, not a
       hint that merely didn't help, so it is allowed to produce
       PATH_MISSING_ATTRIBUTE.
    2. **Lexical**, applied with a "don't let this eliminate everything"
       fallback. Keeps a candidate whose display name contains the
       question's head noun - this is what actually separates "The Leaden
       Accord" from "The Winter Reckoning" for `1b_007`, since both are
       `entity_type == "conflict"` and the coarse filter alone cannot tell
       them apart. But "the redoubt's name doesn't literally contain the
       word redoubt" (`1b_003`'s Gloamreach) is a missed hint, not evidence
       of a gap, so a lexical filter that would empty the set is skipped.

    Returns the filtered paths and PATH_MISSING_ATTRIBUTE if genuinely nothing
    survives both filters together while candidates existed beforehand.
    """
    if not paths:
        return paths, EvidenceStatus.NO_PATH

    candidates = paths
    if entity_type is not None:
        # No fallback here: the permissive rule (an unknown type is not a
        # mismatch) already protects against most untyped candidates being
        # eliminated. If applying it still empties the set, every remaining
        # candidate carries a *definite*, recorded, contradicting type - a
        # real signal, not a hint that merely didn't help.
        candidates = [p for p in candidates if graph.nodes[p.end].entity_type in (None, entity_type)]

    if word is not None and candidates:
        # The lexical filter *does* fall back: a head noun extracted from
        # free text ("redoubt") not appearing in the corpus's own name for
        # the answer ("Gloamreach") is a missed hint, not evidence the
        # corpus lacks the attribute - see `1b_003`.
        by_word = [p for p in candidates if word in graph.nodes[p.end].name.lower()]
        if by_word:
            candidates = by_word

    if not candidates:
        return [], EvidenceStatus.PATH_MISSING_ATTRIBUTE
    return candidates, EvidenceStatus.SUFFICIENT


def check_abstention(
    graph: Graph,
    corpus_path,
    start_key: str,
    relation: str,
    relation_map: RelationMap,
) -> str | None:
    """The raw cell text, if `start_key`'s own page abstains on `relation`.

    Reuses the graph builder's own field parser (`parse_cell`,
    `infobox_rows`) rather than a second copy of the abstention rule, so this
    can never disagree with what the graph itself would have done with the
    same cell. An abstaining cell yields no edge in the graph (by design -
    `cells.py`), which makes it indistinguishable from an absent field unless
    something re-reads the row. This is that something.
    """
    node = graph.nodes.get(start_key)
    if node is None or node.page is None:
        return None

    fields = {
        name
        for name, spec in relation_map.forward.items()
        if spec == relation
    } | {name for name, spec in relation_map.reverse.items() if spec == relation}
    if not fields:
        return None

    path = corpus_path / node.page
    if not path.is_file():
        return None

    text = path.read_text(encoding="utf-8")
    for field_name, value in infobox_rows(text):
        if field_name in fields and parse_cell(value).is_abstention:
            return value
    return None
