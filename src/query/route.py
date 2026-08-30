"""Question routing: text in, a relation chain to walk out - or a logged miss.

CLAUDE.md's instruction for this stage is explicit: identify the small number
of structural shapes actually present in the 1B questions, implement those as
deterministic templates, and do not build a general semantic planner before a
template has been shown to fail. Measured on the seven dev 1B questions, there
are exactly **four** shapes, and three of them are the same two-hop chain read
in different directions:

| Template               | Chain                        | Seen in                  |
|-------------------------|------------------------------|---------------------------|
| `lair_dominion`          | `lair_in -> ruled_by`         | 1b_013                    |
| `relic_custody`          | `wields -> housed_in`         | 1b_003                    |
| `victory_membership`     | `member_of <-> victor_of`     | 1b_005, 1b_022, 1b_007, 1b_006 |
| `victor_connection`      | `victor_of -> member_of`, goal fixed | 1b_009             |

`victory_membership` is one template, not two: which relation is walked first
is decided by the resolved entity's *type* (a character starts from
`member_of`; a conflict starts from `victor_of`), not by which dev question is
being asked. That is what "generic mechanism, not a hard-coded question" means
in practice - the same trigger phrase and the same code path answer "which war
did X's faction win" and "who was a member of the faction that won war Y"
because the graph already stores both directions (ADR-016).

A question matching no trigger is not guessed at - `route()` returns `None`
and the caller logs the miss (`RouteMiss`), per the instruction to surface a
template failure rather than reach for an LLM planner on the first gap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.graph.schema import Graph
from src.query.resolve import EntityResolver, Resolution

#: Question-text nouns naming the *kind* of answer wanted, mapped to the
#: coarse entity types `src/graph` assigns (ADR-009's taxonomy). Deliberately
#: not exhaustive - an unmapped noun just means no type filter is applied,
#: which is the safe default (ADR-011's "never guess" spirit applied here).
TYPE_WORDS: dict[str, str] = {
    "war": "conflict", "accord": "conflict", "reckoning": "conflict",
    "conflict": "conflict", "purge": "conflict", "battle": "conflict",
    "redoubt": "location", "location": "location", "place": "location",
    "fortress": "location", "citadel": "location", "abbey": "location",
    "individual": "character", "person": "character", "member": "character",
    "character": "character",
    "faction": "faction", "organization": "faction", "organisation": "faction",
    "order": "faction", "cartel": "faction", "choir": "faction",
    "relic": "artifact", "artifact": "artifact", "weapon": "artifact",
    "creature": "creature", "wyrm": "creature", "beast": "creature",
}

#: "Which/what <noun phrase> was/is/did/must ..." - the head noun is the last
#: word of the captured phrase. Verified against all seven dev 1B questions;
#: see the module test for the exact matches.
_HEAD_NOUN_RE = re.compile(
    r"\b(?:which|what)\s+([a-z]+(?:\s+[a-z]+)?)\s+(?:was|is|were|did|must)\b", re.I
)

_MIN_ALIAS_LEN = 4


@dataclass(frozen=True)
class Mention:
    """One entity mention found in the question text."""

    surface: str
    start: int
    end: int
    resolution: Resolution


@dataclass(frozen=True)
class RouteResult:
    """What a matched template says to do: walk `chain` from `start_key`."""

    template: str
    start_key: str
    chain: tuple[str, ...]
    cardinality: str  # "single" | "any_of"
    type_hint_word: str | None = None
    type_hint_entity_type: str | None = None
    goal_key: str | None = None
    check_conflict: bool = False


@dataclass(frozen=True)
class RouteMiss:
    """A question that matched no deterministic template.

    Recorded rather than raised, per CLAUDE.md: "log when a question fails to
    match a deterministic template" so the miss rate is a number the harness
    can report, not an exception swallowed somewhere.
    """

    question: str
    reason: str


def build_gazetteer(graph: Graph, resolver: EntityResolver) -> list[tuple[str, str]]:
    """`(surface form, node key)` pairs to scan question text for.

    Every node's display name, plus two derived forms that reuse resolution
    tiers already validated elsewhere rather than re-deriving them:

    - names starting with "The " also register with the article dropped
      (`1b_006` writes "the War of Drowned Light" where only "War of Drowned
      Light" is the proper noun - the same rule `canonical_key` applies,
      ADR-011, reused here at the text-scanning stage);
    - every epithet alias the resolver knows (`resolve.py`'s "Cerys Sablewood"
      for "Cerys Sablewood the Ashen") also registers, so a question phrased
      with the shorter form still finds the node.
    """
    entries: list[tuple[str, str]] = []
    for node in graph.nodes.values():
        if len(node.name) >= _MIN_ALIAS_LEN:
            entries.append((node.name, node.key))
        if node.name.lower().startswith("the ") and len(node.name) - 4 >= _MIN_ALIAS_LEN:
            entries.append((node.name[4:], node.key))
    for surface, key in resolver.alias_surfaces:
        if len(surface) >= _MIN_ALIAS_LEN:
            entries.append((surface, key))
    return entries


def extract_mentions(
    text: str, graph: Graph, resolver: EntityResolver, gazetteer: list[tuple[str, str]]
) -> list[Mention]:
    """Longest-match, non-overlapping scan of `text` against known entity names.

    A gazetteer scan rather than an NER model: the entity set is closed (the
    graph's own nodes), so a substring match is exact where a model would be a
    dependency doing a simpler job worse.
    """
    spans: list[tuple[int, int, str, str]] = []
    for surface, key in gazetteer:
        pattern = re.compile(r"\b" + re.escape(surface) + r"\b", re.I)
        for match in pattern.finditer(text):
            spans.append((match.start(), match.end(), match.group(0), key))

    spans.sort(key=lambda s: (-(s[1] - s[0]), s[0]))
    accepted: list[tuple[int, int, str, str]] = []
    for start, end, surface, key in spans:
        if any(start < a_end and end > a_start for a_start, a_end, _, _ in accepted):
            continue
        accepted.append((start, end, surface, key))
    accepted.sort(key=lambda s: s[0])

    mentions = []
    for start, end, surface, key in accepted:
        # The gazetteer already narrowed this to a known key; resolving the
        # matched surface text (rather than assuming the tier) keeps this
        # honest about *which* tier actually matched - exact, normalised, or
        # alias - instead of asserting one.
        resolution = resolver.resolve(surface)
        if not resolution.resolved:
            continue
        mentions.append(Mention(surface, start, end, resolution))
    return mentions


def head_noun(text: str) -> str | None:
    match = _HEAD_NOUN_RE.search(text)
    if not match:
        return None
    return match.group(1).split()[-1].lower()


def _victory_membership_trigger(lower: str) -> bool:
    has_group = any(w in lower for w in ("member", "faction", "organization", "organisation"))
    has_victory = any(w in lower for w in ("won", "win", "victor"))
    return has_group and has_victory


def _connection_trigger(lower: str) -> bool:
    return "connected to" in lower and "victor" in lower


def _lair_trigger(lower: str) -> bool:
    return "lair" in lower and any(w in lower for w in ("dominion", "rule", "whose"))


def _relic_trigger(lower: str) -> bool:
    has_relic = any(w in lower for w in ("relic", "wields", "wielded", "borne by", "borne"))
    has_place = any(w in lower for w in ("journey", "examine", "redoubt", "housed"))
    return has_relic and has_place


def route(
    question: str, graph: Graph, resolver: EntityResolver, gazetteer: list[tuple[str, str]]
) -> RouteResult | RouteMiss:
    """Match `question` against the four templates, in a fixed priority order.

    `victor_connection` is checked before `victory_membership` because both
    can mention "victor"; the connection trigger is the more specific phrase
    ("connected to ... victor") and must win when both would otherwise fire.
    """
    lower = question.lower()
    mentions = extract_mentions(question, graph, resolver, gazetteer)
    noun = head_noun(question)
    type_hint = TYPE_WORDS.get(noun) if noun else None

    if _connection_trigger(lower):
        conflicts = [m for m in mentions if m.resolution.node.entity_type == "conflict"]
        if len(conflicts) == 1:
            conflict_mention = conflicts[0]
            others = [m for m in mentions if m is not conflict_mention]
            if others:
                return RouteResult(
                    template="victor_connection",
                    start_key=conflict_mention.resolution.key,
                    chain=("victor_of", "member_of"),
                    cardinality="single",
                    goal_key=others[0].resolution.key,
                    check_conflict=True,
                )
        return RouteMiss(
            question,
            "victor_connection trigger fired but did not find exactly one "
            f"conflict entity plus a goal entity (found {len(mentions)} mention(s))",
        )

    if _lair_trigger(lower):
        if not mentions:
            return RouteMiss(question, "lair_dominion trigger fired with no resolved entity")
        return RouteResult(
            template="lair_dominion",
            start_key=mentions[0].resolution.key,
            chain=("lair_in", "ruled_by"),
            cardinality="single",
        )

    if _relic_trigger(lower):
        if not mentions:
            return RouteMiss(question, "relic_custody trigger fired with no resolved entity")
        return RouteResult(
            template="relic_custody",
            start_key=mentions[0].resolution.key,
            chain=("wields", "housed_in"),
            cardinality="single",
            type_hint_word=noun,
            type_hint_entity_type=type_hint,
        )

    if _victory_membership_trigger(lower):
        if not mentions:
            return RouteMiss(question, "victory_membership trigger fired with no resolved entity")
        start = mentions[0]
        if start.resolution.node.entity_type == "conflict":
            chain: tuple[str, ...] = ("victor_of", "member_of")
            cardinality = "any_of"
        else:
            chain = ("member_of", "victor_of")
            cardinality = "single"
        return RouteResult(
            template="victory_membership",
            start_key=start.resolution.key,
            chain=chain,
            cardinality=cardinality,
            type_hint_word=noun,
            type_hint_entity_type=type_hint,
        )

    return RouteMiss(question, "no deterministic template's trigger phrase matched")
