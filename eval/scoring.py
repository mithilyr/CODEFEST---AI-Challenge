"""Deterministic scoring for evaluation runs.

WHY NOT AN LLM JUDGE
--------------------
Three reasons, in the order they mattered to the decision.

  1. *Quota.* A judged sweep costs one call per question on top of the answer
     itself, doubling the most scarce resource we have (~20 requests/day/model).
  2. *Reproducibility.* The point of this harness is that a number can be
     re-derived. A judge that may score the same answer differently on two runs
     turns the baseline into an estimate.
  3. *Defensibility.* A teammate can read forty lines of matching rules and
     defend every verdict to a judge. Nobody can defend a model's opinion.

THE TRAP THIS MODULE EXISTS TO AVOID
------------------------------------
``eval/answer_key.json`` warns about it in its own preamble: substring matching
over-credits. An answer reading

    "there is no mention of who the victors were"

contains the phrase "the victors were" and would score correct against a naive
``gold in predicted``. So a match is only accepted when the matched span is not
sitting inside a negation or an abstention. That check is the whole difference
between a scoring function and a scoring function that works.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

#: Negation, matched against the *normalised* form of a sentence (lowercase,
#: punctuation folded to spaces - so "doesn't" arrives as "doesn t").
#:
#: These are patterns rather than a list of phrases because the list version
#: failed in production. It enumerated "does not mention", "does not state",
#: "does not specify" - and the baseline wrote **"does not identify"**, which
#: nobody had thought of. That one gap scored a refusal as a correct answer and
#: inflated the reported 1B result from 2/7 to 3/7. Enumerating verbs is a losing
#: game; match the construction instead.
NEGATION_PATTERNS = (
    # auxiliary + not: "does not identify", "is not established", "were not"
    r"\b(?:does|do|did|is|are|was|were|has|have|had|would|could|should|can|will)\s+not\b",
    # contractions, post-normalisation
    r"\b(?:cannot|can\s+t|isn\s+t|aren\s+t|wasn\s+t|doesn\s+t|don\s+t|didn\s+t|couldn\s+t)\b",
    # "no <evidence-noun>"
    r"\bno\s+(?:mention|record|records|evidence|information|connection|indication"
    r"|reference|references|account|accounts|basis|data|details|detail|year|source"
    r"|sources|statement|way\s+to)\b",
    # "not <evidence-participle>"
    r"\bnot\s+(?:mentioned|stated|recorded|established|identified|specified|provided"
    r"|found|given|listed|named|possible|determinable|clear|available|attested)\b",
    r"\bnothing\s+(?:is|in|about|to)\b",
    r"\bunable\s+to\b",
    r"\bimpossible\s+to\b",
    r"\binsufficient\b",
    r"\bunrecorded\b",
    r"\bsilent\s+on\b",
)

_NEGATION_RE = re.compile("|".join(NEGATION_PATTERNS))

#: Kept for the abstention check, which asks a different question: is the answer
#: as a whole a refusal, regardless of where the gold string sits?
ABSTENTION_EXTRA = (
    "i cannot",
    "i can t",
    "i do not have",
    "unable to answer",
    "cannot answer",
    "does not contain enough information",
    "not contain enough information",
)

#: An answer that declines. Distinct from a wrong answer: abstention is a
#: different failure to diagnose, and for some questions the right behaviour.
_ABSTENTION_RE = re.compile(
    "|".join(NEGATION_PATTERNS + tuple(re.escape(p) for p in ABSTENTION_EXTRA))
)

#: Sentence boundaries. Negation is scoped to the sentence containing a match:
#: a denial in a *different* sentence is about something else, and a character
#: window cannot tell the difference. Semicolons deliberately do not split -
#: "The forging date is not recorded; some accounts say 391 AS" is one claim,
#: and the negation governs the whole of it.
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def normalise(text: str) -> str:
    """Fold text to a comparable form.

    Typographic punctuation goes through the ingestion pipeline's own
    ``normalise_punctuation`` first, so U+2019 becomes a plain apostrophe rather
    than being deleted by the ASCII fold. Deleting it would make "Sorrowfell's"
    fold to "sorrowfells" while "Sorrowfell's" folds to "sorrowfell s", and the
    two would never match - which is exactly the bug this ordering prevents.

    Punctuation then becomes spaces rather than vanishing, so "391AS" does not
    match "391 AS" by accident of deletion.
    """
    from src.ingest.loaders import normalise_punctuation

    folded = unicodedata.normalize("NFKD", normalise_punctuation(text))
    folded = folded.encode("ascii", "ignore").decode("ascii").lower()
    folded = re.sub(r"[^a-z0-9]+", " ", folded)
    return re.sub(r"\s+", " ", folded).strip()


def sentences(text: str) -> list[str]:
    """Split into sentences, each normalised for comparison."""
    parts = SENTENCE_SPLIT_RE.split(text)
    return [normalise(part) for part in parts if normalise(part)]


def _spans(haystack: str, needle: str) -> list[tuple[int, int]]:
    """Every occurrence of needle in haystack, on word boundaries."""
    if not needle:
        return []
    pattern = re.compile(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])")
    return [(m.start(), m.end()) for m in pattern.finditer(haystack)]


def is_negated(sentence: str) -> bool:
    """Does this sentence deny rather than assert? Sentence must be normalised."""
    return bool(_NEGATION_RE.search(sentence))


def is_abstention(answer: str) -> bool:
    """Is the whole answer a refusal to commit?"""
    return bool(_ABSTENTION_RE.search(normalise(answer)))


@dataclass(frozen=True)
class AnswerVerdict:
    """The outcome of matching one predicted answer against the key."""

    correct: bool
    #: The acceptable string that matched, if any.
    matched: str | None
    #: Set when a gold string was present but sat inside a negation. This is the
    #: over-crediting trap being caught, and it is worth seeing in the report
    #: rather than silently folded into "wrong".
    negated_match: str | None
    abstained: bool

    @property
    def label(self) -> str:
        if self.correct:
            return "correct"
        if self.negated_match:
            return "negated_gold"
        if self.abstained:
            return "abstained"
        return "wrong_answer"


def score_answer(predicted: str, acceptable: list[str]) -> AnswerVerdict:
    """Match a predicted answer against every acceptable form.

    An answer is correct when at least one acceptable string appears in a
    sentence that does not deny it. Set-valued questions list every valid answer
    and any one counts, which is the convention ``answer_key.json`` declares.
    """
    clauses = sentences(predicted)
    negated: str | None = None

    for candidate in acceptable:
        needle = normalise(candidate)
        matched_anywhere = False
        for clause in clauses:
            if not _spans(clause, needle):
                continue
            matched_anywhere = True
            if not is_negated(clause):
                return AnswerVerdict(True, candidate, None, False)
        if matched_anywhere:
            negated = negated or candidate

    return AnswerVerdict(False, None, negated, is_abstention(predicted))


@dataclass(frozen=True)
class EvidenceVerdict:
    """How well retrieval covered the documents the answer actually needs."""

    expected: list[str]
    retrieved: list[str]
    hit: list[str] = field(default_factory=list)

    @property
    def recall(self) -> float | None:
        """Fraction of required documents that retrieval reached.

        None when the question has no traced path - 1A questions are read off
        figure plates and have no document path to recall.
        """
        if not self.expected:
            return None
        return len(self.hit) / len(self.expected)

    @property
    def precision(self) -> float | None:
        """Fraction of retrieved documents that were required.

        Bounded above by len(expected)/k: with k=5 and a two-hop question the
        ceiling is 0.4, so this number diagnoses dilution rather than grading
        the run. Read it against that ceiling, never as a percentage of ideal.
        """
        if not self.expected or not self.retrieved:
            return None
        return len(self.hit) / len(self.retrieved)


def score_evidence(expected_docs: list[str], retrieved_docs: list[str]) -> EvidenceVerdict:
    """Compare required documents against retrieved ones, order-insensitively."""
    unique_retrieved = list(dict.fromkeys(retrieved_docs))
    retrieved_set = set(unique_retrieved)
    hit = [doc for doc in dict.fromkeys(expected_docs) if doc in retrieved_set]
    return EvidenceVerdict(
        expected=list(dict.fromkeys(expected_docs)),
        retrieved=unique_retrieved,
        hit=hit,
    )


def failure_category(answer: AnswerVerdict, evidence: EvidenceVerdict) -> str:
    """Classify a result into a diagnosis, not just pass/fail.

    The distinction that matters for sub-track 1B is *where* a join question
    broke. CLAUDE.md claims baseline failures are "retrieval never reaches the
    second document, or reaches it and cannot join" - these categories are what
    turn that claim into two separate counts.
    """
    if answer.correct:
        return "correct"
    if answer.negated_match:
        return "negated_gold"

    recall = evidence.recall
    if recall is None:
        return "abstained" if answer.abstained else "wrong_answer"
    if recall == 0:
        return "retrieval_miss"
    if recall < 1:
        return "partial_retrieval"
    return "synthesis_failure"


#: What each category means, printed into the Markdown report so a reader does
#: not have to open this file to interpret the table.
CATEGORY_GLOSSARY = {
    "correct": "An acceptable answer appeared and was not negated.",
    "negated_gold": (
        "The gold string appeared but inside a negation - the over-crediting "
        "trap. A substring scorer would have marked this correct."
    ),
    "abstained": "The system declined to answer.",
    "wrong_answer": "Answered, but no acceptable form appeared.",
    "retrieval_miss": "Wrong, and retrieval reached none of the required documents.",
    "partial_retrieval": (
        "Wrong, and retrieval reached some but not all required documents - the "
        "join failure sub-track 1B exists to fix."
    ),
    "synthesis_failure": (
        "Wrong despite retrieval reaching every required document. The evidence "
        "was present and the answer still did not follow."
    ),
    "not_scored": "No traced answer in the key. Recorded, never counted.",
    "error": "The run raised before producing an answer.",
}
