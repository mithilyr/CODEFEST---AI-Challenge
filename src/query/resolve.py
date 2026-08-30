"""Entity resolution: a mention in question text to a graph key, or a refusal.

ADR-011 already settled the hard part - no fuzzy matching may *select* a
winner, because six pairs of genuinely distinct entities sit at >= 0.80 string
similarity (`caedmon_fellgard` ~ `ederon_fellgard` at 0.839, the subject of
`1b_007`). This module adds two tiers ADR-011's own scope stopped short of -
alias resolution and candidate generation - while keeping that rule intact:
fuzzy matching here only ever produces candidates for a human or an LLM
escalation to choose between (F-010).

Five tiers, tried in order, each one a stricter-to-looser test:

1. **Exact** - the mention is byte-identical to a node's display name.
2. **Normalised** - `canonical_key` agrees once case, punctuation and a
   leading article are folded away. This is ADR-011's own rule, reused.
3. **Alias** - a measured naming pattern, not a lookup table of specific
   names: seven wiki characters are named `"<name> the <Epithet>"`
   (`Corvus Hollowmere the Pale`, `Maelis Harrowick the Pale`, `Cerys
   Sablewood the Ashen`, ...). Dropping the epithet is a real alias a question
   may use, verified against the corpus rather than assumed - see
   `_build_epithet_aliases`.
4. **Fuzzy candidates** - `difflib` similarity over every known key. Never
   returns a single winner; the result is always `AMBIGUOUS` with candidates
   attached, because ADR-011 measured that any threshold loose enough to
   catch a genuine variant is loose enough to merge Caedmon and Ederon
   Fellgard.
5. **Escalation** - an injectable callback tried only on an `AMBIGUOUS`
   result. Absent by default: none of the known 1B questions need it, and
   CLAUDE.md's rule is that an LLM call must be justified by a measured gap,
   not added speculatively. Every invocation is counted either way.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from enum import Enum

from src.graph.entities import canonical_key
from src.graph.schema import Graph, Node

#: `"<base>, the <Epithet>"`-style names, e.g. "Cerys Sablewood the Ashen" and
#: "Aldous Wrenfield the Last Warden" (a multi-word epithet). The epithet is a
#: distinguishing title, always capitalised, always the last word(s) of the
#: display name - never part of the given/family name, which the corpus never
#: repeats the lowercase word "the" inside of.
_EPITHET_RE = re.compile(r"^(?P<base>.+?)\s+the\s+(?P<epithet>[A-Z][A-Za-z\-]*(?:\s+[A-Z][A-Za-z\-]*)*)$")

#: Fuzzy floor. Below this, a candidate is noise rather than a variant spelling.
#: Set beneath the 0.839 Caedmon/Ederon Fellgard similarity ADR-011 measured,
#: because the floor's job is to admit candidates for a human to look at, not
#: to separate genuine variants from genuine distinct entities - that decision
#: is exactly the one this module refuses to make automatically.
FUZZY_FLOOR = 0.72

#: How many fuzzy candidates to surface. Enough to show the real variant is in
#: the list without dumping the whole node set on a reviewer.
FUZZY_LIMIT = 5


class ResolutionStatus(str, Enum):
    EXACT = "exact"
    NORMALISED = "normalised"
    ALIAS = "alias"
    AMBIGUOUS = "ambiguous"
    ESCALATED = "escalated"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class Candidate:
    """One fuzzy near-match, with the similarity that produced it."""

    key: str
    name: str
    similarity: float


@dataclass(frozen=True)
class Resolution:
    """The outcome of resolving one mention against one graph."""

    mention: str
    status: ResolutionStatus
    key: str | None = None
    node: Node | None = None
    candidates: tuple[Candidate, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.key is not None


#: An escalator is given the unresolved mention and its fuzzy candidates, and
#: may return a key to accept or None to leave it unresolved. It is never
#: called by default (see module docstring).
Escalator = "Callable[[str, tuple[Candidate, ...]], str | None] | None"


@dataclass
class EntityResolver:
    """Resolves mentions against one graph, tier by tier.

    Built once per graph (the alias index and the fuzzy candidate pool are
    both O(nodes) to build), then called once per mention.
    """

    graph: Graph
    escalator: object = None  # Escalator, see the module-level type alias.
    escalation_count: int = field(default=0, init=False)

    _exact: dict[str, str] = field(default_factory=dict, init=False)
    _alias: dict[str, str] = field(default_factory=dict, init=False)
    _pool: tuple[tuple[str, str], ...] = field(default_factory=tuple, init=False)
    #: The alias's literal surface text alongside the key it resolves to, so
    #: `route.py`'s gazetteer can scan question text for "Cerys Sablewood" and
    #: not just the full "Cerys Sablewood the Ashen" the node is keyed under.
    alias_surfaces: tuple[tuple[str, str], ...] = field(default_factory=tuple, init=False)

    def __post_init__(self) -> None:
        for node in self.graph.nodes.values():
            self._exact.setdefault(node.name, node.key)
        self._alias, self.alias_surfaces = _build_epithet_aliases(self.graph)
        self._pool = tuple((n.key, n.name) for n in self.graph.nodes.values())

    def resolve(self, mention: str) -> Resolution:
        mention = mention.strip()
        if not mention:
            return Resolution(mention, ResolutionStatus.UNRESOLVED)

        if mention in self._exact:
            key = self._exact[mention]
            return Resolution(mention, ResolutionStatus.EXACT, key, self.graph.nodes[key])

        norm = canonical_key(mention)
        if norm in self.graph.nodes:
            return Resolution(
                mention, ResolutionStatus.NORMALISED, norm, self.graph.nodes[norm]
            )

        if norm in self._alias:
            key = self._alias[norm]
            return Resolution(mention, ResolutionStatus.ALIAS, key, self.graph.nodes[key])

        candidates = self._fuzzy(norm)
        if not candidates:
            return Resolution(mention, ResolutionStatus.UNRESOLVED)

        result = Resolution(mention, ResolutionStatus.AMBIGUOUS, candidates=candidates)

        if self.escalator is not None:
            self.escalation_count += 1
            chosen = self.escalator(mention, candidates)
            if chosen and chosen in self.graph.nodes:
                return Resolution(
                    mention,
                    ResolutionStatus.ESCALATED,
                    chosen,
                    self.graph.nodes[chosen],
                    candidates=candidates,
                )

        return result

    def _fuzzy(self, norm: str) -> tuple[Candidate, ...]:
        """Candidates only - see F-010. Never returns a sole automatic winner."""
        scored = [
            (difflib.SequenceMatcher(None, norm, key).ratio(), key, name)
            for key, name in self._pool
        ]
        scored = [s for s in scored if s[0] >= FUZZY_FLOOR]
        scored.sort(key=lambda s: -s[0])
        return tuple(
            Candidate(key, name, round(score, 3))
            for score, key, name in scored[:FUZZY_LIMIT]
        )


def _build_epithet_aliases(graph: Graph) -> tuple[dict[str, str], tuple[tuple[str, str], ...]]:
    """`"<base> the <Epithet>"` -> the node's key, for every such name.

    A collision - the stripped base already naming a *different* node - drops
    the alias rather than guessing between them. None occur in the measured
    corpus, but the rule must not silently merge two entities if the corpus
    grows.

    Returns the normalised-key lookup used by `resolve()`, plus the raw
    `(surface text, key)` pairs `route.py` needs to scan free text for the
    alias itself, not just its canonical key.
    """
    aliases: dict[str, str] = {}
    surfaces: list[tuple[str, str]] = []
    for node in graph.nodes.values():
        match = _EPITHET_RE.match(node.name)
        if not match:
            continue
        base = match.group("base")
        base_key = canonical_key(base)
        if base_key in graph.nodes and base_key != node.key:
            continue  # ambiguous with a real node; refuse rather than guess.
        aliases[base_key] = node.key
        surfaces.append((base, node.key))
    return aliases, tuple(surfaces)
