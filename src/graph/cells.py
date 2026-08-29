"""Infobox cells are sentences, and the sentence set is closed (ADR-010).

Twelve named handlers cover all 651 cells in the corpus. No model is involved:
twelve regexes are faster, cost no quota, are more reliable than a model at this
job, and - decisively - a teammate can defend a named handler with a test to a
judge in a way they cannot defend a prompt.

The parser's job is as much *refusing* to emit an edge as emitting one. Three
templates are load-bearing for that reason:

- **Prose containing an incidental link** (23 cells) must yield no edge.
  `Appearance | Hardened visual identity of a garrisoned settlement in the
  [[Ash Wastes]]` links a region inside a description. Harvesting every `[[link]]`
  manufactures a relation the corpus never asserted.
- **Two-argument clauses** (11 cells) are one ternary fact, not two edges.
  `Fought in [[The Purge of Blackport]] for [[House Morvain]]` says the subject
  was a belligerent in a conflict, on a side. Emitting two edges from the subject
  additionally asserts "belligerent in House Morvain", which is false. Both word
  orders occur, so arguments are assigned by target type, never by position.
- **Abstentions** (24 cells) are an explicit refusal by the source, not missing
  data. `Contested; consult the Annals and Codex` names where to look. Collapsing
  it to "no value" throws away the signpost and makes a deliberate silence
  indistinguishable from a gap.

Qualifiers stay on the edge rather than in the node name. `[[The Cinder-Wrought
Aegis]], since 356 AS` is what 1b_003 asks about; gluing the year into the target
produces the node `the_cinder_wrought_aegis_since_356_as`, which joins to nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: A wiki link. The corpus uses no `[[target|label]]` piped form - checked.
LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

#: A year in the in-world calendar, e.g. "356 AS".
YEAR_RE = re.compile(r"\b(\d+)\s*AS\b")

#: Wording that marks a source declining to state a value, rather than a value.
_ABSTENTION_RE = re.compile(
    r"contested|consult|not recorded|unrecorded|no canonical|none recorded"
    r"|no year|no physical|disputed",
    re.I,
)

_VERB_LINK_RE = re.compile(r"^(?P<verb>[A-Za-z][A-Za-z\s',-]*?)\s*\[\[", re.I)

#: The closed set of leading phrases that introduce a genuine relation, taken by
#: enumerating every phrase preceding a single link in the corpus. A closed list
#: rather than a heuristic because the alternative - "a short phrase is a verb" -
#: misfires on exactly the cells ADR-010 warns about: `The Purge of [[Blackport]]`
#: is an entity name with one word linked, and `Regalia bearing the name [[X]]`
#: is a description. Both are short, and an edge from either is invented.
RELATION_VERBS = frozenset(
    {
        "member of",
        "commands",
        "wields",
        "mentor of",
        "rival of",
        "serves at",
        "unleashed in",
        "waged at",
        "devastated",
    }
)

#: Leading phrases whose relation the page frames as concealed. Kept apart
#: because "the source says this is secret" is a property of the claim, and a
#: conflict resolver may weigh a concealed assertion differently from an open one.
SECRET_VERBS = frozenset(
    {
        "secretly sells intelligence to",
        "unacknowledged heir to",
        "swore a hidden oath to",
    }
)

#: Trailing article left over once a verb phrase is matched, e.g. "Wields the".
_TRAILING_ARTICLE = re.compile(r"\s+the$", re.I)

#: "... since 399 AS" trailing a verb + link cell.
_TRAILING_SINCE = re.compile(r"\bsince\s+(?P<year>\d+)\s*AS\s*$", re.I)

#: "[[X]], since 356 AS"
_SINCE_RE = re.compile(r"^\s*\[\[(?P<target>[^\]]+)\]\]\s*,?\s*since\s+(?P<year>\d+)\s*AS\s*$", re.I)

#: "[[Greyfell Citadel]] in 337 AS; [[Palewell Abbey]] in 338 AS"
_LINK_YEAR_RE = re.compile(r"\[\[(?P<target>[^\]]+)\]\]\s*in\s+(?P<year>\d+)\s*AS", re.I)

#: Separators used for multi-valued cells. `,` occurs once; `;` is the norm.
_SPLIT_RE = re.compile(r"\s*[;,]\s*")

#: Bare literals: a year, a number, or prose with no link at all.
_YEAR_ONLY_RE = re.compile(r"^\s*\d+\s*AS\s*$", re.I)
_NUMBER_ONLY_RE = re.compile(r"^\s*[\d,]+\s*$")


@dataclass(frozen=True)
class Reference:
    """One entity a cell points at, with whatever the cell qualified it by."""

    target: str
    #: In-world year attached to *this* target, e.g. 356 from "since 356 AS".
    year: int | None = None
    #: "since" | "in" | None - how the year relates to the fact.
    year_kind: str | None = None
    #: For a ternary fact, the second argument, e.g. the faction fought for.
    qualifier: str | None = None


@dataclass(frozen=True)
class ParsedCell:
    """What one infobox cell asserts.

    `template` is always set, and always one of the twelve measured names, so a
    histogram over parsed cells can be compared against the probe. `references`
    is empty for every template that must not become an edge - which is most of
    the corpus by volume.
    """

    template: str
    references: tuple[Reference, ...] = ()
    #: Verb phrase that introduced the relation, where the cell supplied one.
    verb: str | None = None
    #: True when the source explicitly declined to state a value.
    is_abstention: bool = False
    #: True when the page frames the claim as concealed.
    is_secret: bool = False
    raw: str = ""

    @property
    def yields_edges(self) -> bool:
        return bool(self.references)


def _links(value: str) -> list[str]:
    return [m.strip() for m in LINK_RE.findall(value)]


def _strip_links(value: str) -> str:
    """The cell with its links removed, to judge how much prose surrounds them."""
    return LINK_RE.sub("", value).strip()


def parse_cell(value: str, *, link_types: dict[str, str] | None = None) -> ParsedCell:
    """Classify one infobox cell and extract whatever entities it asserts.

    Args:
        value: The raw cell text, links included.
        link_types: Optional map of canonical entity key -> entity type, used to
            assign the arguments of a two-argument clause by type rather than by
            position. Both word orders occur in the corpus, so position is not
            reliable. Without it, a ternary cell still parses but keeps the
            corpus's own order.

    Returns:
        A :class:`ParsedCell`. Cells that must not become edges return with an
        empty `references` tuple rather than raising.
    """
    raw = value.strip()

    if _ABSTENTION_RE.search(raw):
        return ParsedCell("abstention", is_abstention=True, raw=raw)

    links = _links(raw)

    if not links:
        if _YEAR_ONLY_RE.match(raw):
            return ParsedCell("literal year", raw=raw)
        if _NUMBER_ONLY_RE.match(raw):
            return ParsedCell("literal number", raw=raw)
        return ParsedCell("literal prose", raw=raw)

    since = _SINCE_RE.match(raw)
    if since:
        return ParsedCell(
            "link + since-qualifier",
            references=(
                Reference(since.group("target"), int(since.group("year")), "since"),
            ),
            raw=raw,
        )

    link_years = list(_LINK_YEAR_RE.finditer(raw))
    if link_years and len(link_years) == len(links):
        return ParsedCell(
            "link + year pairs",
            references=tuple(
                Reference(m.group("target"), int(m.group("year")), "in")
                for m in link_years
            ),
            raw=raw,
        )

    if len(links) == 1:
        if not _strip_links(raw):
            return ParsedCell("bare link", references=(Reference(links[0]),), raw=raw)

        verb = _known_verb(raw)
        if verb in SECRET_VERBS:
            return ParsedCell(
                "secret / association relation",
                references=(Reference(links[0]),),
                verb=verb,
                is_secret=True,
                raw=raw,
            )
        if verb in RELATION_VERBS:
            since = _TRAILING_SINCE.search(raw)
            return ParsedCell(
                "verb + link",
                references=(
                    Reference(
                        links[0],
                        int(since.group("year")) if since else None,
                        "since" if since else None,
                    ),
                ),
                verb=verb,
                raw=raw,
            )
        return ParsedCell("prose containing an incidental link", raw=raw)

    # Two or more links.
    if _is_link_list(raw, links):
        return ParsedCell(
            "link list", references=tuple(Reference(t) for t in links), raw=raw
        )

    if len(links) == 2:
        return _two_argument(raw, links, link_types)

    return ParsedCell("prose containing an incidental link", raw=raw)


def _known_verb(raw: str) -> str | None:
    """The leading phrase before a link, if it is one the corpus uses as a verb.

    Returns the phrase lowercased with any trailing article dropped, so
    "Wields the [[X]]" and "Wields [[X]]" resolve to the same verb. Returns None
    for a phrase outside the closed set, which is how prose keeps its links.
    """
    match = _VERB_LINK_RE.match(raw)
    if not match:
        return None
    phrase = _TRAILING_ARTICLE.sub("", match.group("verb").strip()).lower()
    return phrase if phrase in RELATION_VERBS or phrase in SECRET_VERBS else None


def _is_link_list(raw: str, links: list[str]) -> bool:
    """True when the cell is only links and separators."""
    parts = [p for p in _SPLIT_RE.split(raw) if p.strip()]
    return len(parts) == len(links) and all(
        LINK_RE.fullmatch(p.strip()) for p in parts
    )


def _two_argument(
    raw: str, links: list[str], link_types: dict[str, str] | None
) -> ParsedCell:
    """`Fought in [[Conflict]] for [[Faction]]` - one fact with two objects.

    The subject is the page; the primary object is the conflict; the faction is
    a qualifier on the edge, not a second edge from the subject. Both word orders
    occur, so when types are known the conflict is chosen by type and not by
    position.
    """
    from src.graph.entities import canonical_key

    primary, secondary = links[0], links[1]
    if link_types:
        types = {t: link_types.get(canonical_key(t)) for t in links}
        conflicts = [t for t in links if types[t] == "conflict"]
        others = [t for t in links if types[t] != "conflict"]
        if len(conflicts) == 1 and len(others) == 1:
            primary, secondary = conflicts[0], others[0]

    return ParsedCell(
        "two-argument clause",
        references=(Reference(primary, qualifier=secondary),),
        verb=_known_verb(raw),
        raw=raw,
    )
