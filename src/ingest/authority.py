"""Source authority assignment.

Loads config/authority.yaml and stamps every canonical document with a
(tier, subtier) pair. Lower is more authoritative.

This module is deliberately small and deliberately dumb. Deciding which source
outranks which is the single most consequential judgement the system makes - it
is what turns "360 AS" (a sermon) into "391 AS" (the codex) - so the ranking
lives in readable configuration that a judge can be shown and argued with, and
the code here does nothing but apply it. No LLM is involved at any point.

See config/authority.yaml for the tier definitions and the reasoning behind them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import yaml

from src.ingest.dedup import CanonicalDocument

#: Fallback tier for a collection the config does not name. Chosen to be the
#: least authoritative so an unrecognised source is never trusted by default.
UNKNOWN_TIER = 99
UNKNOWN_SUBTIER = 99

DEFAULT_CONFIG_PATH = Path("config/authority.yaml")


@dataclass(frozen=True)
class AuthorityModel:
    """The loaded authority configuration."""

    #: collection -> tier number.
    tiers: dict[str, int]
    #: collection -> human-readable label, for the UI evidence panel.
    labels: dict[str, str]
    #: collection -> why this tier, for the UI and the report.
    rationales: dict[str, str]
    #: ephemera doctype -> subtier number.
    ephemera_subtiers: dict[str, int]
    #: ephemera doctype -> why this subtier.
    doctype_rationales: dict[str, str]
    default_ephemera_subtier: int
    default_subtier: int

    def rank(self, collection: str, doctype: str | None) -> tuple[int, int]:
        """Return the (tier, subtier) rank for a source.

        Args:
            collection: Corpus folder the document came from.
            doctype: In-world document type, for ephemera only.

        Returns:
            A (tier, subtier) tuple. Sorting claims by this tuple ascending puts
            the most authoritative source first.
        """
        tier = self.tiers.get(collection, UNKNOWN_TIER)

        if collection != "ephemera":
            return tier, self.default_subtier

        if doctype is None:
            return tier, self.default_ephemera_subtier

        return tier, self.ephemera_subtiers.get(doctype, self.default_ephemera_subtier)

    def explain(self, collection: str, doctype: str | None) -> str:
        """One-line justification for a document's rank, shown in the UI.

        The evidence panel needs to tell a reader *why* one source outranked
        another, not merely that it did.
        """
        label = self.labels.get(collection, "Unrecognised source")
        if collection == "ephemera" and doctype:
            reason = self.doctype_rationales.get(doctype, "")
            return f"{label} ({doctype.replace('_', ' ')}) - {reason}".strip(" -")
        return f"{label} - {self.rationales.get(collection, '').strip()}".strip(" -")


@lru_cache(maxsize=4)
def load_authority_model(config_path: Path = DEFAULT_CONFIG_PATH) -> AuthorityModel:
    """Read and validate the authority configuration.

    Cached, because it is consulted once per claim during conflict resolution.

    Raises:
        FileNotFoundError: If the config is missing - the system must not fall
            back to a silent default here, because an unranked corpus would
            resolve conflicts arbitrarily.
    """
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Authority config not found at {path.resolve()}. "
            "This file decides which sources outrank which; the system will not "
            "resolve conflicts without it."
        )

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    tier_block = raw.get("tiers", {})
    subtier_block = raw.get("ephemera_subtiers", {})

    return AuthorityModel(
        tiers={name: entry["tier"] for name, entry in tier_block.items()},
        labels={name: entry.get("label", name) for name, entry in tier_block.items()},
        rationales={
            name: entry.get("rationale", "").strip() for name, entry in tier_block.items()
        },
        ephemera_subtiers={
            name: entry["subtier"] for name, entry in subtier_block.items()
        },
        doctype_rationales={
            name: entry.get("rationale", "").strip()
            for name, entry in subtier_block.items()
        },
        default_ephemera_subtier=raw.get("default_ephemera_subtier", 3),
        default_subtier=raw.get("default_subtier", 1),
    )


def assign_authority(
    documents: list[CanonicalDocument],
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> list[CanonicalDocument]:
    """Stamp every canonical document with its (tier, subtier) rank."""
    model = load_authority_model(config_path)
    return [
        replace(document, tier=tier, subtier=subtier)
        for document in documents
        for tier, subtier in [model.rank(document.collection, document.doctype)]
    ]
