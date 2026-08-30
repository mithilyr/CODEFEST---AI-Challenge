# Task checklist

Updated 2026-08-30. Deadline: 9 Sep 2026, 11:30 PM.

## Blocking — before push/share

- [ ] Add a git remote (none configured yet) and push `main`
- [ ] Commit or discard the working-tree diff on `src/graph/traverse.py` /
      `tests/test_graph.py` (currently uncommitted — see `git status`)

## Must do

- [ ] Human-verify `eval/answer_key.json` (`verified_by` is still `null`) —
      two people, per `eval/verification/answer_key_review.md`. Recall is now
      independently corroborated (`eval/completeness.py`, 0 defects); what's
      left is precision/semantic review. Provisional only for that reason —
      not blocking implementation.
- [x] Build `src/query/` — resolution, routing, traversal, evidence
      sufficiency, conflict detection. `1b_007`'s type filter and `1b_009`'s
      conflict handling are both done and tested (ADR-017). 7/7 dev 1B
      questions answered correctly.
- [ ] Build `src/ui/` — not started.
- [ ] Rotate all API keys before 8 Sep (chat-log export day) — logs are a
      mandatory deliverable judges read.
- [ ] Export AI chat logs to `ai_usage/` as work happens, not at the end.
- [ ] Write the ≤5-page PDF report.
- [ ] Record the ≤10-minute video, ≥3–4 min unedited live demo, **against a
      warm cache** (never a cold one).

## Ongoing / process (graded, 30% of rubric)

- [ ] Atomic commits daily, messages state *why* + the measurement behind it
- [ ] Log new decisions in `docs/decisions.md` (ADR format)
- [ ] Log rejected approaches in `docs/failures.md`
- [ ] Run `python -m src.ingest.integrity` before trusting any measurement
      you didn't expect

## Assign

- [ ] Owner for `src/query/`
- [ ] Owner for `src/ui/`
- [ ] Two verifiers for the answer key
