"""Generate the human review pack for the answer key.

    python -m eval.verify_key

The answer key was traced by an AI assistant reading the corpus. Until two
people have independently confirmed each entry against the source text, it is a
draft, and every number scored against it is provisional.

This script does the mechanical half of that job: for each traced question it
pulls **the actual passage from the corpus** at every cited location and writes
it into a review sheet, so a reviewer reads what the document says rather than
hunting through 317 files.

It deliberately does not pull anything from `eval/probes/corpus_shape.py`. The
probe is our parser and may be wrong in the same way the key is wrong; checking
one against the other would confirm nothing. Reviewers check against the source
text only.

The reviewer's job is to answer, per question:

  * does the cited document actually say what the key claims it says?
  * does the path lead from the question to the answer?
  * is the answer the *only* defensible one, or is the set incomplete?

A reviewer who cannot confirm an entry marks it rejected and says why. Nobody
edits an answer to make the system score better - that is the one move that
would make the whole harness worthless.
"""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

from eval.run_eval import ANSWER_KEY_PATH, load_key

PACK_DIR = Path(__file__).resolve().parent / "verification"

#: Characters of surrounding context to show around a cited location.
EXCERPT_CHARS = 700


def corpus_passages(doc_id: str, locator: str | None) -> list[tuple[str, str]]:
    """Return (evidence_id, text) for a cited document, narrowed by locator.

    Ingestion is the only reader of the corpus in this project, so the review
    pack shows exactly the text the system itself sees. If ingestion is dropping
    something, the reviewer sees that too, which is worth knowing.
    """
    from src.ingest.pipeline import ingest_cached

    units = [u for u in ingest_cached().evidence if u.canonical_doc_id == doc_id]
    if not units:
        return []

    if locator:
        wanted = re.sub(r"\s+", " ", locator.strip().lower())
        exact = [u for u in units if u.locator.lower() == wanted]
        if exact:
            return [(u.evidence_id, u.text) for u in exact]

    return [(u.evidence_id, u.text) for u in units]


def find_supporting(doc_id: str, needles: list[str], limit: int = 2) -> list[tuple[str, str]]:
    """Passages in a document containing any of the given strings."""
    out: list[tuple[str, str]] = []
    for evidence_id, text in corpus_passages(doc_id, None):
        haystack = text.lower()
        if any(needle.lower() in haystack for needle in needles if needle):
            out.append((evidence_id, text))
        if len(out) >= limit:
            break
    return out


def _excerpt(text: str, focus: list[str]) -> str:
    """Trim a passage around the first focus string, or from the start."""
    flat = re.sub(r"\s+", " ", text).strip()
    if len(flat) <= EXCERPT_CHARS:
        return flat
    lowered = flat.lower()
    position = next(
        (lowered.find(f.lower()) for f in focus if f and f.lower() in lowered), -1
    )
    if position < 0:
        return flat[:EXCERPT_CHARS] + " ..."
    start = max(0, position - EXCERPT_CHARS // 3)
    return ("... " if start else "") + flat[start : start + EXCERPT_CHARS] + " ..."


def render_question(entry: dict) -> str:
    qid = entry["qid"]
    focus = [entry.get("answer", "")] + entry.get("acceptable", [])

    lines = [
        f"## `{qid}`",
        "",
        f"**Question.** {entry['question']}",
        "",
        f"**Key says the answer is.** `{entry.get('answer')}`",
        "",
    ]
    if len(entry.get("acceptable", [])) > 2:
        lines += [
            f"This is a **set-valued** question - the key lists "
            f"{len(entry['acceptable'])} acceptable answers. Check that the set is "
            "complete as well as that its members are right.",
            "",
        ]

    lines += ["### Claimed path", ""]
    for step, hop in enumerate(entry.get("expected_path", []), start=1):
        lines += [
            f"**Hop {step}.** `{hop['from']}` --[{hop['relation']}]--> `{hop['to']}`",
            f"  cited: `{hop['source']}`" + (f", field `{hop['field']}`" if hop.get("field") else ""),
        ]
        if hop.get("note"):
            lines.append(f"  note: {hop['note']}")
        lines.append("")

        passages = corpus_passages(hop["source"], hop.get("field"))
        if not passages:
            lines += [
                "> **NO TEXT FOUND at this citation.** Ingestion returns nothing "
                "for this document. Flag this - the citation may be wrong, or the "
                "document may not be reaching the pipeline.",
                "",
            ]
            continue

        focus_strings = [hop.get("to", ""), hop.get("field", "")] + focus
        shown = passages[:1] if len(passages) == 1 else find_supporting(
            hop["source"], [hop.get("to", ""), hop.get("from", "")]
        ) or passages[:1]
        for evidence_id, text in shown:
            lines += [
                f"> Corpus text at `{evidence_id}`:",
                "",
                textwrap.indent(_excerpt(text, focus_strings), "> "),
                "",
            ]

    conflict = entry.get("conflict")
    if conflict:
        lines += ["### Claimed conflict", ""]
        for role in ("authoritative", "rejected", "abstains"):
            records = conflict.get(role)
            if not records:
                continue
            records = records if isinstance(records, list) else [records]
            for record in records:
                lines.append(
                    f"- **{role}**: `{record.get('value', '-')}` from "
                    f"`{record.get('source')}` (tier {record.get('tier', '?')})"
                )
                if record.get("quote"):
                    lines.append(f"  - key quotes: \"{record['quote']}\"")
                found = find_supporting(
                    record.get("source", ""), [str(record.get("value", ""))], limit=1
                )
                if found:
                    lines.append(f"  - corpus says: \"{_excerpt(found[0][1], [str(record.get('value', ''))])}\"")
                else:
                    lines.append(
                        "  - **could not locate this value in that document** - check it"
                    )
        lines.append("")

    if entry.get("notes"):
        lines += ["### Tracer's notes", "", f"> {entry['notes']}", ""]

    lines += [
        "### Reviewer sign-off",
        "",
        "| | Reviewer 1 | Reviewer 2 |",
        "|---|---|---|",
        "| name | | |",
        "| date | | |",
        "| answer correct? (yes / no / unsure) | | |",
        "| path correct? (yes / no / unsure) | | |",
        "| answer set complete? (yes / no / n/a) | | |",
        "| comments | | |",
        "",
        "**Verdict** (leave blank until both reviewers have filled the column above): ",
        "`confirmed` / `rejected` / `unresolved`",
        "",
        "If the two reviewers disagree, the verdict is `unresolved`. Investigate and "
        "record what settled it - do not average the two opinions, and do not change "
        "the answer to match the system's output.",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def build_pack() -> Path:
    key = load_key()
    raw = json.loads(ANSWER_KEY_PATH.read_text(encoding="utf-8"))
    entries = raw["questions"]

    lines = [
        "# Answer key verification pack",
        "",
        f"{len(entries)} traced questions require independent confirmation by "
        "**two** reviewers before any number scored against them may be quoted.",
        "",
        "## How to use this",
        "",
        "1. Two reviewers work **independently**. Do not compare notes until both "
        "   have filled in their column.",
        "2. For each question, read the corpus text quoted beneath each hop and "
        "   decide whether the document actually supports the claim.",
        "3. Check the citation itself, not just the excerpt - open the file if "
        "   anything looks off. The excerpt is a convenience, not the evidence.",
        "4. Mark `unsure` freely. An unsure entry is information; a guessed "
        "   confirmation destroys the thing this pack exists to protect.",
        "5. When both columns are filled, record the verdict and update "
        "   `verified_by` in `eval/answer_key.json` to a list of the two names.",
        "",
        "## The one rule",
        "",
        "> Never change an answer to make the system score better.",
        "",
        "If the system disagrees with a confirmed key entry, the system is wrong. "
        "If review shows the key itself was wrong, fix the key and say so in "
        "`docs/decisions.md` - being wrong cheaply is the process working, but "
        "quietly moving the target is not.",
        "",
        "The excerpts below come from the ingestion pipeline - the same text the "
        "system sees. They are **not** produced by `eval/probes/corpus_shape.py`; "
        "checking our parser against our parser would confirm nothing.",
        "",
        "---",
        "",
    ]
    lines += [render_question(entry) for entry in entries]

    PACK_DIR.mkdir(parents=True, exist_ok=True)
    path = PACK_DIR / "answer_key_review.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    path = build_pack()
    key = load_key()
    unverified = [q for q, e in key.items() if not e.get("verified_by")]
    print(f"wrote {path}")
    print(f"  {len(key)} traced questions, {len(unverified)} awaiting verification")
    print(f"  {', '.join(sorted(unverified))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
