"""The one measured sweep of the LLM planner tier, per `docs/TODO.md`.

ADR-020 built `src/query/planner.py` as an opt-in third routing tier and left
it deliberately unmeasured on the frozen 55-question set: running it there
spends OpenRouter's daily free-tier quota and produces a number that drifts
with the provider's free lineup, not with anything this project controls.
`docs/TODO.md` names the decision explicitly - spend one measured sweep and
cache it, or report the tier as unmeasured - and this script is that sweep,
run once, with its result committed rather than reproduced on every eval run.

WHY THIS SCRIPT AND NOT A THIRD ARM IN `comparison/harness.py`
-----------------------------------------------------------------
`harness.py`'s own module docstring states the reason Arm A is always called
with `use_planner=False`: "a comparison number that silently depends on a
model being reachable is not reproducible, and this harness exists to produce
reproducible numbers." Adding a planner arm to that file would make its
default `python -m comparison.harness` run spend quota and drift, which is
exactly what it exists to prevent. This script is separate, deliberately
named apart from the harness, and never runs as a side effect of anything else
in CI, a test, or a routine eval.

WHAT IT MEASURES
-----------------
For each of the 55 frozen questions: the shipped system as it is today
(templates -> cue tier, `use_planner=False` - i.e. `comparison.harness`'s Arm
C) against the shipped system plus the opt-in planner tier
(`use_planner=True`). `answer_question` only invokes the planner when both
deterministic tiers have already declined (`src/query/engine.py`'s own
docstring: "each running only if the previous one declined"), so Arm D is not
an independent planner-only measurement - it is what a user actually gets with
`--with-model` on, and the delta from Arm C shows exactly what the planner
tier is contributing on top of what already ships without it.

Usage:
    python -m comparison.planner_sweep
    # requires OPENROUTER_API_KEY in .env. Uses the persistent response cache
    # (src/clients/openrouter.py) - a re-run after the first costs no quota
    # for any question whose prompt has not changed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path as FsPath

from comparison.harness import (
    METRICS,
    Outcome,
    build_context,
    run_arm_a,
    score,
    summarise,
)
from src.query.engine import answer_question

QUESTION_SET = "eval/robustness/routing_robustness_v1.json"
OUT_DIR = FsPath("comparison/results")


def run_arm_d(question: str, ctx) -> Outcome:
    """Arm C plus the opt-in planner tier - the system as `--with-model` ships it."""
    answer = answer_question(
        question,
        ctx.graph,
        resolver=ctx.resolver,
        gazetteer=ctx.gazetteer,
        corpus_path=ctx.corpus,
        relation_map=ctx.relation_map,
        use_fallback=True,
        use_planner=True,
    )
    routes = tuple(
        dict.fromkeys(tuple(e.relation for e in p.edges) for p in answer.paths)
    )
    hops = min((len(p.edges) for p in answer.paths), default=None)
    return Outcome(
        status=answer.status.value,
        values=answer.values,
        documents=answer.documents,
        relation_routes=routes,
        hops=hops,
        start_key=answer.start_key,
        note=answer.note,
    )


def main() -> None:
    ctx = build_context()
    questions = json.loads(
        FsPath(QUESTION_SET).read_text(encoding="utf-8")
    )["questions"]

    rows_c, rows_d, moved = [], [], []
    for q in questions:
        outcome_c = run_arm_a(q["question"], ctx, use_fallback=True)
        row_c = score(q, outcome_c, ctx)
        rows_c.append(row_c)

        outcome_d = run_arm_d(q["question"], ctx)
        row_d = score(q, outcome_d, ctx)
        rows_d.append(row_d)

        if row_c["status"] != row_d["status"]:
            moved.append(
                {
                    "rid": q["rid"],
                    "group": q["group"],
                    "shipped_status": row_c["status"],
                    "with_planner_status": row_d["status"],
                    "shipped_correct": row_c["answer_correct"],
                    "with_planner_correct": row_d["answer_correct"],
                    "with_planner_complete_evidence": row_d["complete_evidence"],
                }
            )

    answerable = [q["rid"] for q in questions if q.get("expected_answerable", True)]

    def only(rows):
        return [r for r in rows if r["rid"] in answerable]

    def refusals(rows):
        return sum(
            1 for r in rows if r["rid"] not in answerable and r["answer_correct"]
        )

    summary_c = summarise(only(rows_c))
    summary_d = summarise(only(rows_d))

    result = {
        "set": QUESTION_SET,
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": (
            "One measured sweep per docs/TODO.md ('Measure the planner tier'). "
            "arm_c_shipped is comparison.harness's Arm C (use_planner=False), "
            "recomputed here for a same-run comparison. arm_d_with_planner adds "
            "use_planner=True; the planner tier only fires where arm_c already "
            "declined."
        ),
        "arm_c_shipped": {"per_question": rows_c, "summary": summary_c},
        "arm_d_with_planner": {"per_question": rows_d, "summary": summary_d},
        "questions_where_status_moved": moved,
        "honest_refusal_of_6": {
            "shipped": refusals(rows_c),
            "with_planner": refusals(rows_d),
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "planner_sweep.json"
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "# Planner tier sweep",
        "",
        f"Measured {result['measured_at']}. Frozen set: `{QUESTION_SET}` "
        f"({len(questions)} questions, {len(answerable)} answerable).",
        "",
        "Arm C is the shipped system (templates -> cue tier, no planner). "
        "Arm D adds the opt-in planner tier (`use_planner=True`) on top of the "
        "same shipped code path.",
        "",
        f"| metric | C shipped | D with planner |",
        f"|---|---:|---:|",
    ]
    for metric in METRICS:
        lines.append(f"| {metric} | {summary_c[metric]} | {summary_d[metric]} |")
    lines.append(
        f"| honest refusal (of 6) | {refusals(rows_c)} | {refusals(rows_d)} |"
    )
    lines.append("")
    lines.append(f"## Questions where the planner tier changed the outcome ({len(moved)})")
    lines.append("")
    if moved:
        lines.append("| rid | group | shipped status | with-planner status | correct? | complete evidence? |")
        lines.append("|---|---|---|---|---|---|")
        for m in moved:
            lines.append(
                f"| {m['rid']} | {m['group']} | {m['shipped_status']} | "
                f"{m['with_planner_status']} | {m['with_planner_correct']} | "
                f"{m['with_planner_complete_evidence']} |"
            )
    else:
        lines.append("None - the planner tier never fired, or fired and produced "
                      "the same status the shipped tiers already reached.")
    lines.append("")
    (OUT_DIR / "planner_sweep.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"answerable questions: {len(answerable)} of {len(questions)}\n")
    print(f"{'metric':<28}{'C shipped':>12}{'D w/planner':>13}")
    print("-" * 53)
    for metric in METRICS:
        print(f"{metric:<28}{summary_c[metric]:>12}{summary_d[metric]:>13}")
    print(f"\nhonest refusal (of 6): shipped={refusals(rows_c)} with_planner={refusals(rows_d)}")
    print(f"\nplanner changed the outcome on {len(moved)} of {len(questions)} questions")
    print(f"wrote {out_json} and {OUT_DIR / 'planner_sweep.md'}")


if __name__ == "__main__":
    main()
