"""Typed access to the answer key.

The v2 key stopped forcing every question into one expected string, because
human review on 2026-08-29 showed the corpus does not fit that shape:

  * ``1b_006`` has fourteen valid answers, recorded in two disjoint places.
  * ``1b_007`` needs a type filter to choose between two genuine victories.
  * ``1b_009`` turns on a wiki-vs-wiki contradiction that no source tier can
    resolve, because both sides sit at tier 2.

This module is the only thing that reads the file's shape, so the rest of the
harness works in terms of accepted answers, required evidence and conflicts
rather than JSON keys.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ANSWER_KEY_PATH = Path(__file__).resolve().parent / "answer_key.json"

#: Two independent reviewers, per ADR-014. One consolidated review is not two.
REQUIRED_REVIEWERS = 2


@dataclass(frozen=True)
class AcceptedAnswer:
    """One valid answer and its surface variants.

    An alias is another way of writing the *same* answer. A different valid
    answer is a separate AcceptedAnswer - collapsing the two would make it
    impossible to tell "we accept either name" from "we accept either spelling".
    """

    answer: str
    aliases: tuple[str, ...] = ()

    @property
    def surface_forms(self) -> tuple[str, ...]:
        return (self.answer, *self.aliases)


@dataclass(frozen=True)
class Claim:
    """One source's position on a contested fact."""

    #: asserts | denies | silent
    stance: str
    source: str
    tier: int | None = None
    value: str | None = None
    field_name: str | None = None
    quote: str | None = None


@dataclass(frozen=True)
class Conflict:
    """Sources disagreeing about one subject-relation."""

    subject: str
    relation: str
    object: str | None
    claims: tuple[Claim, ...]
    same_tier: bool
    #: authority | unresolved | none
    resolution: str
    must_surface: bool
    why_unresolvable: str | None = None

    @property
    def asserted_values(self) -> tuple[str, ...]:
        return tuple(c.value for c in self.claims if c.stance == "asserts" and c.value)


@dataclass(frozen=True)
class Verification:
    """Who has checked this entry, and whether that is enough."""

    status: str
    reviewers: tuple[str, ...] = ()
    reviewed_on: str | None = None
    discrepancy: str | None = None

    @property
    def is_confirmed(self) -> bool:
        """Confirmed needs TWO independent reviewers and no open discrepancy.

        A single consolidated review does not clear this, however confident it
        is. The 1b_006 review is exactly why: one reviewer reported two valid
        answers where the corpus has fourteen, and a second reviewer is the
        mechanism that would have caught it.
        """
        return (
            self.status == "confirmed"
            and len(self.reviewers) >= REQUIRED_REVIEWERS
            and not self.discrepancy
        )


@dataclass(frozen=True)
class KeyEntry:
    """Ground truth for one question."""

    qid: str
    track: str
    question: str
    answer_cardinality: str
    accepted_answers: tuple[AcceptedAnswer, ...]
    required_evidence: tuple[str, ...]
    acceptable_paths: tuple[dict, ...]
    conflicts: tuple[Conflict, ...]
    expected_conflict_status: str
    confidence: str
    notes: str
    verification: Verification
    distractors: tuple[dict, ...] = ()

    @property
    def all_surface_forms(self) -> list[str]:
        """Every string that counts as naming a correct answer.

        Longest first, so a match reports the most specific form it found
        rather than a short alias that happens to be a prefix.
        """
        forms = [f for a in self.accepted_answers for f in a.surface_forms]
        return sorted(forms, key=len, reverse=True)

    @property
    def must_surface_conflict(self) -> bool:
        return self.expected_conflict_status == "must_surface"

    @property
    def disputed_claims(self) -> list[str]:
        """Values a system must not present as settled fact."""
        return [
            value
            for conflict in self.conflicts
            if conflict.must_surface
            for value in (conflict.asserted_values or (conflict.object,))
            if value
        ]


def _conflict(raw: dict) -> Conflict:
    return Conflict(
        subject=raw.get("subject", ""),
        relation=raw.get("relation", ""),
        object=raw.get("object"),
        claims=tuple(
            Claim(
                stance=c.get("stance", "asserts"),
                source=c.get("source", ""),
                tier=c.get("tier"),
                value=c.get("value"),
                field_name=c.get("field"),
                quote=c.get("quote"),
            )
            for c in raw.get("claims", [])
        ),
        same_tier=bool(raw.get("same_tier")),
        resolution=raw.get("resolution", "none"),
        must_surface=bool(raw.get("must_surface")),
        why_unresolvable=raw.get("why_unresolvable"),
    )


def _entry(raw: dict) -> KeyEntry:
    verification = raw.get("verification") or {}
    return KeyEntry(
        qid=raw["qid"],
        track=raw.get("track", ""),
        question=raw.get("question", ""),
        answer_cardinality=raw.get("answer_cardinality", "single"),
        accepted_answers=tuple(
            AcceptedAnswer(answer=a["answer"], aliases=tuple(a.get("aliases", [])))
            for a in raw.get("accepted_answers", [])
        ),
        required_evidence=tuple(raw.get("required_evidence", [])),
        acceptable_paths=tuple(raw.get("acceptable_paths", [])),
        conflicts=tuple(_conflict(c) for c in raw.get("conflicts", [])),
        expected_conflict_status=raw.get("expected_conflict_status", "none"),
        confidence=raw.get("confidence", "unknown"),
        notes=raw.get("notes", ""),
        verification=Verification(
            status=verification.get("status", "draft"),
            reviewers=tuple(verification.get("reviewers", [])),
            reviewed_on=verification.get("reviewed_on"),
            discrepancy=verification.get("discrepancy"),
        ),
        distractors=tuple(raw.get("distractors", [])),
    )


def load_key(path: Path | None = None) -> dict[str, KeyEntry]:
    raw = json.loads((path or ANSWER_KEY_PATH).read_text(encoding="utf-8"))
    return {e["qid"]: _entry(e) for e in raw["questions"]}


def load_raw(path: Path | None = None) -> dict:
    return json.loads((path or ANSWER_KEY_PATH).read_text(encoding="utf-8"))


def required_documents(entry: KeyEntry) -> list[str]:
    """Documents the answer must be grounded in.

    Includes the sources of *rejected* and *silent* claims for conflict
    questions: a system that never retrieves the sermon cannot know there was a
    disagreement to resolve, so those documents are part of the evidence the
    answer needs rather than distractors to be avoided.
    """
    docs = list(entry.required_evidence)
    for conflict in entry.conflicts:
        docs.extend(claim.source for claim in conflict.claims if claim.source)
    for path in entry.acceptable_paths:
        docs.extend(hop["source"] for hop in path.get("hops", []) if hop.get("source"))
    return list(dict.fromkeys(docs))
