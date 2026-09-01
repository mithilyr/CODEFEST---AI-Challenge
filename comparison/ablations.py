"""Ablate arm B's guards one at a time against the frozen robustness set.

Phase 2 asks whether each of the sister router's four guards fixes a
reproducible failure in our system. This answers the prior question - does it
fix a reproducible failure in *its own* system - by switching each one off and
re-measuring. A guard that changes nothing when removed is a guard with no
measured value on this corpus, whatever its author's reasoning was.

Also runs one guard the sister router does NOT have: symmetric stemming, added
here after the as-written run showed its stemmer folds `ruled`/`rules`/`ruling`
to `rul` but leaves the base form `rule` alone, so it never matches. See
`cue_router.normalize_cue_word`.

    python -m comparison.ablations
"""

from __future__ import annotations

import json
from pathlib import Path as FsPath

from comparison.cue_router import relation_cues
from comparison.harness import build_context, run_arm_b, score, summarise

VARIANTS: tuple[tuple[str, dict], ...] = (
    ("as_written", {}),
    ("plus_symmetric_stemming", {"use_symmetric_stemming": True}),
    ("minus_consecutive_repeat", {"use_no_consecutive_repeat": False}),
    ("minus_coverage_selection", {"use_coverage_selection": False}),
    ("minus_tiebreak_stopwords", {"use_tiebreak_stopwords": False}),
    ("minus_irregular_verbs", {"use_irregular_verbs": False}),
)


def main(argv: list[str] | None = None) -> None:
    ctx = build_context()
    path = FsPath("eval/robustness/routing_robustness_v1.json")
    questions = json.loads(path.read_text(encoding="utf-8"))["questions"]
    answerable = [q for q in questions if q["expected_answerable"]]

    out: dict[str, dict] = {}
    print(f"ARM B GUARD ABLATIONS - {path} (answerable n={len(answerable)})\n")
    header = f"{'variant':<30}{'routed':>8}{'correct':>9}{'complete':>10}{'precision':>11}{'depth':>7}"
    print(header)
    print("-" * len(header))

    for label, guards in VARIANTS:
        ctx.cues = relation_cues(
            ctx.relation_map,
            strip_final_e=bool(guards.get("use_symmetric_stemming")),
        )
        rows = [score(q, run_arm_b(q["question"], ctx, **guards), ctx) for q in questions]
        ans = [r for r, q in zip(rows, questions) if q["expected_answerable"]]
        routed = sum(1 for r in ans if r["route_success"])
        correct = sum(1 for r in ans if r["answer_correct"])
        complete = sum(1 for r in ans if r["complete_evidence"])
        summary = summarise(rows)
        out[label] = {
            "guards": guards,
            "routed": routed,
            "correct": correct,
            "complete_evidence": complete,
            "precision_when_routed": round(correct / routed, 4) if routed else None,
            "whole_set": summary,
        }
        pct = f"{correct / routed:.0%}" if routed else "n/a"
        print(
            f"{label:<30}{routed:>8}{correct:>9}{complete:>10}{pct:>11}"
            f"{summary['unnecessary_depth']:>7}"
        )

    dest = FsPath("comparison/results/ablations.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
