# Task checklist

Updated 2026-08-30. Deadline: 9 Sep 2026, 11:30 PM.

## Blocking — before push/share

Nothing blocking, measured 30 Aug 2026. Both items this section used to carry
are done: `origin` is configured
(`github.com/mithilyr/CODEFEST---AI-Challenge`), and the `src/graph/traverse.py`
/ `tests/test_graph.py` working-tree diff it named landed in `2775add`.
`git status` is clean.

## Must do

- [ ] Human-verify `eval/answer_key.json` — two people, per
      `eval/verification/answer_key_review.md`. Measured `verification.status`:
      `single_review` ×6, `draft` ×2, `unresolved` ×1, all seven reviewed
      entries by the same reviewer (F-015). There is no `verified_by` field;
      this line named one until 30 Aug. Recall is now
      independently corroborated (`eval/completeness.py`, 0 defects); what's
      left is precision/semantic review. Provisional only for that reason —
      not blocking implementation.
- [x] Build `src/query/` — resolution, routing, traversal, evidence
      sufficiency, conflict detection. `1b_007`'s type filter and `1b_009`'s
      conflict handling are both done and tested (ADR-017). 7/7 dev 1B
      questions answered correctly.
- [x] Build `src/ui/` — stdlib `http.server`, no new dependency, all nine
      demo surfaces rendered, thinness pinned by three architectural tests
      (ADR-018). 19 new tests, 203 total.
- [ ] **Next: measure the query layer's weaknesses, not polish the UI.**
      Routing robustness on re-worded questions is the first measurement —
      template hit rate, entity resolution, evidence completeness, answer
      correctness, `NO_TEMPLATE_MATCH` and ambiguous-resolution frequency.
      Do not add an LLM planner before that number exists (ADR-017's gate).
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
- [x] Owner for `src/ui/` — first version built; needs a reviewer
- [ ] Two verifiers for the answer key
