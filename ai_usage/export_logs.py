#!/usr/bin/env python3
"""Export Claude Code session transcripts to redacted plain-text logs.

Codefest 2026 challenge doc s4.1 requires the full conversation logs with any AI
agent used during development, as .txt files, in the repository. Claude Code
stores those transcripts as JSONL under ~/.claude/projects/<slug>/. This script
converts them.

Design notes, because a teammate has to be able to defend this to a judge:

  * One .txt per session, named session-<YYYY-MM-DD>-<short-id>.txt, where the
    date is the session's first timestamp (UTC) and short-id is the first eight
    characters of the session UUID.
  * Tool *calls* are rendered as one summary line each. Tool *output* is not
    rendered -- a single `Read` of the corpus would bury the human-AI dialogue
    that the logs exist to show. Successful results collapse to a size; errors
    keep a short prefix, because a failure is part of the conversation.
  * Secrets are redacted before anything is written. See REDACTION RULES below.
  * Deterministic: same input bytes produce byte-identical output. No run
    timestamp, no dict-order dependence, sorted inputs, LF line endings.

Usage:
    python ai_usage/export_logs.py                 # export + report
    python ai_usage/export_logs.py --check         # report only, write nothing
    python ai_usage/export_logs.py --thinking full # keep full reasoning blocks

REDACTION RULES
    1. Known key shapes:  AIza..., AQ...., sk-..., sk-or-..., pa-...
    2. Assignment of any *_API_KEY / access token / secret key to a value.
    3. Any 32+ character high-entropy token, with narrow exemptions for
       40-char git SHAs and UUIDs so the logs stay checkable against the
       commit history.
Every replacement is counted and reported per file.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

DEFAULT_SOURCE = Path.home() / ".claude" / "projects" / "E--AI-Challenge-CodeFest"
DEFAULT_OUTPUT = Path(__file__).resolve().parent

REDACTED = "[REDACTED]"

# --------------------------------------------------------------------------
# Redaction
# --------------------------------------------------------------------------

# Rule 1 -- literal key shapes. Ordered so that a sk-or-v1-... key is reported
# as openrouter-key rather than as a generic sk-key.
#
# Google issues two formats and we have used both: the classic AIza... key and
# the current AI Studio key, which is `AQ.` followed by ~50 characters and
# contains a dot. Matching only AIza silently missed every key of the second
# kind -- 21 of them in the 28 Aug session. Both are matched here.
KEY_SHAPE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("google-aiza-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}")),
    ("google-aq-key", re.compile(r"\bAQ\.[0-9A-Za-z_\-\.]{20,}")),
    ("openrouter-key", re.compile(r"\bsk-or-[0-9A-Za-z_\-]{16,}")),
    ("sk-key", re.compile(r"\bsk-(?!or-)[0-9A-Za-z_\-]{16,}")),
    ("voyage-pa-key", re.compile(r"\bpa-[0-9A-Za-z_\-]{16,}")),
]

# Rule 2 -- NAME = VALUE where NAME looks like a credential. Matches
# GOOGLE_API_KEY=x, "voyage_api_key": "x", OPENROUTER_API_KEY: x, export K=x.
# Requires an actual value token, so prose like "needs GOOGLE_API_KEY" and
# unrelated settings like VOYAGE_TIER=paid are left alone.
ASSIGNMENT_PATTERN = re.compile(
    r"""(?P<name>\b[A-Za-z0-9_]*(?:API[_-]?KEY|APIKEY|ACCESS[_-]?TOKEN|SECRET[_-]?KEY|AUTH[_-]?TOKEN)\b)
        (?P<sep>["']?\s*[:=]\s*["']?)
        (?P<value>[A-Za-z0-9_\-\.]{8,})""",
    re.VERBOSE | re.IGNORECASE,
)

# Rule 3 -- high-entropy tokens, the catch-all for key formats we have not seen.
#
# The candidate alphabet is exactly the one every key we issue uses:
# [A-Za-z0-9_-]. It deliberately excludes . / + = so that paths and URLs break
# into short segments instead of matching whole. An earlier version included
# them and redacted 246 tokens, every single one of which was a file path --
# which would have gutted the logs' readability and made them look evasive.
# A dotted key such as Google's AQ.<50 chars> still trips this rule on its
# post-dot remainder, on top of being matched exactly by rule 1.
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\-]{32,}")
UUID_PATTERN = re.compile(
    r"\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z", re.I
)
GIT_SHA_PATTERN = re.compile(r"\A[0-9a-f]{40}\Z")
ENTROPY_THRESHOLD = 3.2


def shannon_entropy(text: str) -> float:
    """Bits of Shannon entropy per character."""
    if not text:
        return 0.0
    counts = Counter(text)
    n = len(text)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _looks_like_credential(token: str) -> bool:
    """Rule 3 predicate: opaque, mixed-class, high-entropy, not a known-safe id.

    Exemptions are deliberately narrow. A 40-char lowercase hex string is a git
    SHA, and keeping it lets a judge line a log up against the commit history; a
    UUID is a session or message id and appears in our own headers. Everything
    else that is long, mixed-class and high-entropy is treated as credential
    material regardless of what it actually is. Over-redaction costs
    readability; under-redaction costs a key.
    """
    if UUID_PATTERN.match(token) or GIT_SHA_PATTERN.match(token):
        return False
    classes = sum(
        bool(re.search(p, token))
        for p in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[_\-\.\+/=]")
    )
    if classes < 2:
        return False
    # Readable identifiers are not credentials. A key interleaves its alphabet
    # densely; an identifier decomposes on _ or - into whole words and whole
    # numbers. This exempts mcp__Claude_Browser__browser_batch,
    # GenerateRequestsPerDayPerProjectPerModel-FreeTier, the corpus plate names
    # (plate_047_the_iron_ring_citadel) and long test function names, none of
    # which any provider's key format can imitate.
    segments = [s for s in re.split(r"[_\-]+", token) if s]
    if len(segments) >= 2 and all(s.isalpha() or s.isdigit() for s in segments):
        if sum(1 for s in segments if s.isalpha() and len(s) >= 2) >= 2:
            return False
    return shannon_entropy(token) >= ENTROPY_THRESHOLD


def redact(text: str, counter: Counter) -> str:
    """Replace credential material in `text`, tallying each hit into `counter`."""
    if not text:
        return text

    for label, pattern in KEY_SHAPE_PATTERNS:

        def _sub(m: re.Match[str], _label: str = label) -> str:
            counter[_label] += 1
            return REDACTED

        text = pattern.sub(_sub, text)

    def _sub_assignment(m: re.Match[str]) -> str:
        if m.group("value").startswith("REDACTED"):
            return m.group(0)
        counter["key-assignment"] += 1
        return f"{m.group('name')}{m.group('sep')}{REDACTED}"

    text = ASSIGNMENT_PATTERN.sub(_sub_assignment, text)

    def _sub_token(m: re.Match[str]) -> str:
        token = m.group(0)
        if not _looks_like_credential(token):
            return token
        counter["high-entropy-token"] += 1
        return REDACTED

    return TOKEN_PATTERN.sub(_sub_token, text)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

SYSTEM_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)

# Which argument identifies each tool call. First match wins; falls back to the
# first scalar argument present.
TOOL_ARG_KEYS = (
    "command",
    "file_path",
    "pattern",
    "path",
    "query",
    "url",
    "prompt",
    "description",
    "skill",
    "notebook_path",
)
ARG_SUMMARY_LIMIT = 160


def collapse(text: str, limit: int) -> str:
    """One line, no runs of whitespace, ellipsised at `limit`."""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[:limit] + " ..."


def summarise_tool_call(name: str, args: object) -> str:
    if not isinstance(args, dict):
        return f"[tool] {name}"
    for key in TOOL_ARG_KEYS:
        if key in args and args[key] not in (None, "", [], {}):
            summary = collapse(args[key], ARG_SUMMARY_LIMIT)
            extra = ""
            if name == "Edit" and "old_string" in args:
                extra = "  (in-place edit)"
            elif name == "Grep" and key == "pattern" and args.get("path"):
                extra = f"  in {collapse(args['path'], 60)}"
            return f"[tool] {name}: {key}={summary}{extra}"
    scalars = [
        k for k, v in sorted(args.items()) if isinstance(v, (str, int, float, bool))
    ]
    if scalars:
        k = scalars[0]
        return f"[tool] {name}: {k}={collapse(args[k], ARG_SUMMARY_LIMIT)}"
    return f"[tool] {name}"


def result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "image":
                    parts.append("<image>")
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return "" if content is None else str(content)


def summarise_tool_result(block: dict) -> str:
    body = result_text(block.get("content"))
    if block.get("is_error"):
        return f"[tool result] ERROR: {collapse(body, 200)}"
    lines = body.count("\n") + 1 if body else 0
    return f"[tool result] ok ({len(body)} chars, {lines} lines, output not included)"


def blocks_of(record: dict) -> list:
    message = record.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def render_turn(record: dict, thinking_mode: str, counter: Counter) -> list[str]:
    """Return the output lines for one transcript record, or [] to skip it."""
    role = record.get("type")
    if role not in ("user", "assistant"):
        return []

    body: list[str] = []
    for block in blocks_of(record):
        btype = block.get("type")

        if btype == "text":
            text = SYSTEM_REMINDER.sub("", block.get("text", "")).strip()
            if text:
                body.append(redact(text, counter))

        elif btype == "thinking":
            if thinking_mode == "none":
                continue
            thought = (block.get("thinking") or "").strip()
            if not thought:
                continue
            if thinking_mode == "trim" and len(thought) > 1500:
                thought = thought[:1500] + "\n    ... [reasoning truncated]"
            body.append("[thinking]\n" + redact(thought, counter))

        elif btype == "tool_use":
            body.append(
                redact(
                    summarise_tool_call(block.get("name", "?"), block.get("input")),
                    counter,
                )
            )

        elif btype == "tool_result":
            body.append(redact(summarise_tool_result(block), counter))

    if not body:
        return []

    label = "USER" if role == "user" else "ASSISTANT"
    if record.get("isSidechain"):
        label += " (subagent)"
    stamp = record.get("timestamp", "unknown")
    rule = "-" * max(4, 62 - len(label) - len(stamp))
    return [f"--- {label}  {stamp} {rule}", *body, ""]


# --------------------------------------------------------------------------
# Session export
# --------------------------------------------------------------------------


def read_records(path: Path) -> tuple[list[dict], int]:
    records, bad = [], 0
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
    return records, bad


def export_session(path: Path, out_dir: Path, thinking_mode: str, write: bool) -> dict:
    records, malformed = read_records(path)
    session_id = path.stem
    stamps = sorted(r["timestamp"] for r in records if r.get("timestamp"))
    start = stamps[0] if stamps else "unknown"
    end = stamps[-1] if stamps else "unknown"
    day = start[:10] if start != "unknown" else "undated"

    counter: Counter = Counter()
    lines: list[str] = []
    turns = 0
    for record in records:
        rendered = render_turn(record, thinking_mode, counter)
        if rendered:
            lines.extend(rendered)
            turns += 1

    cwds = sorted({r["cwd"] for r in records if r.get("cwd")})
    branches = sorted({r["gitBranch"] for r in records if r.get("gitBranch")})

    header = [
        "=" * 78,
        "Ashen Era Intelligence Assistant -- AI collaboration transcript",
        "SLIIT Codefest 2026, sub-track 1B. Exported for challenge doc s4.1.",
        "",
        f"Session id      : {session_id}",
        f"Source          : {path.name}",
        f"First activity  : {start}",
        f"Last activity   : {end}",
        f"Dialogue turns  : {turns}   (of {len(records)} raw records)",
        f"Working dir     : {', '.join(cwds) if cwds else 'n/a'}",
        f"Git branch      : {', '.join(branches) if branches else 'n/a'}",
        "Assistant       : Claude Code (Anthropic)",
        "",
        "Tool calls appear as one summary line each; tool output is omitted by",
        "design so the human-AI dialogue stays legible. Credentials are replaced",
        f"with {REDACTED} by ai_usage/export_logs.py. Nothing else is edited.",
        "=" * 78,
        "",
    ]

    out_path = out_dir / f"session-{day}-{session_id[:8]}.txt"
    if write:
        with out_path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(header + lines))

    return {
        "source": path.name,
        "out": out_path.name,
        "turns": turns,
        "records": len(records),
        "malformed": malformed,
        "redactions": counter,
        "start": start,
    }


RULE_LABELS = [
    "google-aiza-key",
    "google-aq-key",
    "openrouter-key",
    "sk-key",
    "voyage-pa-key",
    "key-assignment",
    "high-entropy-token",
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--source", type=Path, default=DEFAULT_SOURCE,
        help="directory of .jsonl transcripts",
    )
    ap.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help="directory to write .txt files into",
    )
    ap.add_argument(
        "--thinking", choices=("full", "trim", "none"), default="trim",
        help="how to render assistant reasoning blocks (default: trim)",
    )
    ap.add_argument("--check", action="store_true", help="report only; write nothing")
    args = ap.parse_args(argv)

    if not args.source.is_dir():
        print(f"error: source directory not found: {args.source}", file=sys.stderr)
        return 1

    sources = sorted(args.source.glob("*.jsonl"))
    if not sources:
        print(f"error: no .jsonl transcripts in {args.source}", file=sys.stderr)
        return 1

    args.output.mkdir(parents=True, exist_ok=True)
    results = [
        export_session(p, args.output, args.thinking, write=not args.check)
        for p in sources
    ]
    results.sort(key=lambda r: (r["start"], r["out"]))

    print(f"{'output file':<34}{'turns':>7}{'  redactions by rule'}")
    print("-" * 78)
    totals: Counter = Counter()
    for r in results:
        totals.update(r["redactions"])
        n = sum(r["redactions"].values())
        detail = (
            ", ".join(f"{k}={r['redactions'][k]}" for k in RULE_LABELS if r["redactions"][k])
            or "none"
        )
        print(f"{r['out']:<34}{r['turns']:>7}  {n:>4}  {detail}")
        if r["malformed"]:
            print(f"{'':<34}{'':>7}        warning: {r['malformed']} unparseable line(s)")
    print("-" * 78)
    print(f"{'TOTAL':<34}{sum(r['turns'] for r in results):>7}  {sum(totals.values()):>4}")
    for k in RULE_LABELS:
        if totals[k]:
            print(f"    {k:<24}{totals[k]:>6}")
    if args.check:
        print("\n--check: nothing written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
