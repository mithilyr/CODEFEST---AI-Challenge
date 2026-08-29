"""Result records for an evaluation run, and the reports they produce.

Two outputs, deliberately:

  * ``<run>.json`` - every field, including the raw retrieved text and the exact
    strings scoring compared. Machine-readable, diffable between checkpoints,
    and auditable: any verdict in the summary can be traced to the inputs that
    produced it without re-running anything.
  * ``<run>.md`` - the same run for a human, with the provisional-key banner at
    the top where nobody can miss it.

The key status is carried on every single question rather than only in the
header. A result row copied into a slide deck should still say whether the
ground truth behind it has been checked by a person.
"""

from __future__ import annotations

import json
import platform
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from eval.scoring import CATEGORY_GLOSSARY

#: Bumped when the record layout changes, so old result files stay readable
#: and a reader can tell which schema produced a number.
SCHEMA_VERSION = 1


@dataclass
class RetrievedItem:
    """One retrieved chunk, kept in full so scoring inputs stay inspectable."""

    rank: int
    score: float
    chunk_id: str
    canonical_doc_id: str
    collection: str
    locators: list[str]
    tier: int
    subtier: int
    #: The text the model actually saw. Verbose on purpose - an auditor should
    #: not have to rebuild the index to see what was in the context window.
    text: str


@dataclass
class QuestionResult:
    """Everything one question produced, and everything needed to audit it."""

    qid: str
    track: str
    question: str

    # -- ground truth ---------------------------------------------------
    expected_answer: str | None
    acceptable: list[str]
    expected_evidence: list[str]
    expected_path: list[dict]
    #: False until two humans have independently checked this entry. Carried
    #: per question, not per run: entries get verified one at a time.
    key_verified: bool
    key_verified_by: list[str]

    # -- what the system did --------------------------------------------
    predicted_answer: str | None
    retrieved: list[RetrievedItem]
    retrieved_docs: list[str]

    # -- verdict --------------------------------------------------------
    scored: bool
    correct: bool | None
    matched_string: str | None
    negated_match: str | None
    abstained: bool
    failure_category: str
    evidence_precision: float | None
    evidence_recall: float | None
    evidence_hit: list[str]

    # -- cost -----------------------------------------------------------
    latency_ms: int
    llm_calls: int
    cache_hits: int
    prompt_tokens: int | None
    response_tokens: int | None
    model: str | None

    # -- presentation ---------------------------------------------------
    has_citations: bool
    #: Whether the corpus can answer this at all, as far as the key knows.
    #: None for untraced questions - absence of a traced answer is not
    #: evidence that no answer exists.
    answerable: bool | None
    error: str | None = None


@dataclass
class RunResult:
    """One complete evaluation sweep."""

    checkpoint: str
    started_at: str
    elapsed_seconds: float
    schema_version: int = SCHEMA_VERSION
    git_commit: str = ""
    python_version: str = ""
    #: True only when every scoreable question's key entry is human-verified.
    key_fully_verified: bool = False
    questions: list[QuestionResult] = field(default_factory=list)

    # -- aggregates ------------------------------------------------------

    @property
    def scored(self) -> list[QuestionResult]:
        return [q for q in self.questions if q.scored]

    @property
    def not_scored(self) -> list[QuestionResult]:
        return [q for q in self.questions if not q.scored]

    def by_track(self) -> dict[str, tuple[int, int]]:
        """(correct, total) per track, over scored questions only."""
        out: dict[str, tuple[int, int]] = {}
        for question in self.scored:
            correct, total = out.get(question.track, (0, 0))
            out[question.track] = (correct + bool(question.correct), total + 1)
        return dict(sorted(out.items()))

    @property
    def total_llm_calls(self) -> int:
        return sum(q.llm_calls for q in self.questions)

    @property
    def total_cache_hits(self) -> int:
        return sum(q.cache_hits for q in self.questions)

    @property
    def complete_evidence_count(self) -> int:
        """Scored questions where retrieval reached every required document."""
        return sum(1 for q in self.scored if q.evidence_recall == 1.0)

    def mean_evidence(self, attribute: str) -> float | None:
        values = [
            getattr(q, attribute)
            for q in self.scored
            if getattr(q, attribute) is not None
        ]
        return sum(values) / len(values) if values else None

    # -- serialisation ---------------------------------------------------

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)


def git_commit() -> str:
    """The commit a run was produced at, so a number can be tied to a tree."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def new_run(checkpoint: str) -> RunResult:
    return RunResult(
        checkpoint=checkpoint,
        started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        elapsed_seconds=0.0,
        git_commit=git_commit(),
        python_version=platform.python_version(),
    )


# -- reporting -----------------------------------------------------------

PROVISIONAL_BANNER = """> ### PROVISIONAL - ground truth is not yet verified
>
> {unverified} of {total} scoreable questions have `verified_by: null` in
> `eval/answer_key.json`. The answer key was traced by an AI assistant reading
> the corpus, and **no human has independently confirmed it**.
>
> Every number below is provisional. Do not quote any of it in the report, the
> video, or a decision until two reviewers have signed off the entries - see
> `eval/verification/` for the review pack and ADR-014 for the process.
"""

VERIFIED_BANNER = """> ### Verified
>
> All {total} scoreable questions have been independently confirmed by two
> reviewers. These numbers may be quoted.
"""


def _fmt(value: float | None, places: int = 3) -> str:
    return "-" if value is None else f"{value:.{places}f}"


def render_markdown(run: RunResult) -> str:
    """The human-readable report."""
    scored, unscored = run.scored, run.not_scored
    unverified = [q for q in scored if not q.key_verified]

    lines = [f"# Checkpoint: {run.checkpoint}", ""]
    lines.append(
        PROVISIONAL_BANNER.format(unverified=len(unverified), total=len(scored))
        if unverified
        else VERIFIED_BANNER.format(total=len(scored))
    )
    lines += [
        "",
        f"- run at `{run.started_at}` in {run.elapsed_seconds:.1f}s",
        f"- commit `{run.git_commit or 'unknown'}`, Python {run.python_version}",
        f"- schema version {run.schema_version}",
        f"- **{run.total_llm_calls} LLM call(s)**, {run.total_cache_hits} served from cache",
        "",
        "## Score",
        "",
        "| Track | Correct | Total |",
        "|---|---|---|",
    ]
    for track, (correct, total) in run.by_track().items():
        lines.append(f"| {track} | {correct} | {total} |")
    total_correct = sum(c for c, _ in run.by_track().values())
    lines += [
        f"| **all scored** | **{total_correct}** | **{len(scored)}** |",
        "",
        f"Mean evidence recall: **{_fmt(run.mean_evidence('evidence_recall'))}**  ",
        f"Mean evidence precision: **{_fmt(run.mean_evidence('evidence_precision'))}** "
        f"(ceiling is `len(expected)/k`, not 1.0 - see `eval/scoring.py`)",
        "",
        f"**Complete evidence: {run.complete_evidence_count}/{len(scored)}** - questions "
        "where retrieval reached *every* document the answer requires. For a "
        "multi-hop question this is the number that matters: an answer produced "
        "from half the required evidence is a right answer by the wrong route, "
        "which `answer_key.json` asks us to count as a retrieval failure.",
        "",
    ]

    if unscored:
        lines += [
            "## Not scored",
            "",
            f"{len(unscored)} question(s) have no traced answer in the key and are "
            "recorded but never counted. They are listed here rather than dropped, "
            "so the denominator is always visible.",
            "",
        ]
        lines += [f"- `{q.qid}` ({q.track}) - {q.question}" for q in unscored]
        lines.append("")

    lines += ["## Per question", "", "| qid | key | correct | category | ev. recall | ev. prec | latency |", "|---|---|---|---|---|---|---|"]
    for question in scored:
        lines.append(
            f"| `{question.qid}` "
            f"| {'verified' if question.key_verified else '**provisional**'} "
            f"| {'yes' if question.correct else 'no'} "
            f"| {question.failure_category} "
            f"| {_fmt(question.evidence_recall, 2)} "
            f"| {_fmt(question.evidence_precision, 2)} "
            f"| {question.latency_ms} ms |"
        )

    seen = {q.failure_category for q in scored}
    lines += ["", "### Categories present in this run", ""]
    lines += [
        f"- **{name}** - {CATEGORY_GLOSSARY[name]}"
        for name in CATEGORY_GLOSSARY
        if name in seen
    ]

    lines += ["", "## Detail", ""]
    for question in scored:
        lines += [
            f"### `{question.qid}` - {question.failure_category}",
            "",
            f"**Q.** {question.question}",
            "",
            f"**Expected.** {question.expected_answer}",
            "",
            f"**Predicted.** {question.predicted_answer or '(no answer)'}",
            "",
            f"- matched: `{question.matched_string or '-'}`"
            + (
                f"  |  **negated match: `{question.negated_match}`**"
                if question.negated_match
                else ""
            ),
            f"- required documents: {', '.join(f'`{d}`' for d in question.expected_evidence) or '-'}",
            f"- reached: {', '.join(f'`{d}`' for d in question.evidence_hit) or '**none**'}",
            f"- retrieved: {', '.join(f'`{d}`' for d in question.retrieved_docs)}",
            "",
        ]

    lines += [
        "---",
        "",
        "Reproduce with:",
        "",
        "```bash",
        f"python -m eval.run_eval --checkpoint {run.checkpoint}",
        "```",
        "",
        "The full record, including the text of every retrieved chunk, is in the "
        "matching `.json` file beside this one.",
        "",
    ]
    return "\n".join(lines)


def results_dir() -> Path:
    return Path(__file__).resolve().parent / "results"


def write_results(run: RunResult) -> tuple[Path, Path]:
    """Write both artifacts and return their paths."""
    directory = results_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{run.checkpoint}_{run.started_at.replace(':', '-')}"
    json_path = directory / f"{stem}.json"
    md_path = directory / f"{stem}.md"
    json_path.write_text(run.to_json(), encoding="utf-8")
    md_path.write_text(render_markdown(run), encoding="utf-8")

    # A stable filename for the most recent run of each checkpoint, so the
    # README and the report can link to something that does not move.
    latest = directory / f"{run.checkpoint}_latest.md"
    latest.write_text(render_markdown(run), encoding="utf-8")
    return json_path, md_path
