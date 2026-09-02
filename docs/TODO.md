# Task checklist

Updated 2026-09-02. Deadline: 9 Sep 2026, 11:30 PM.

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
- [x] **Measure the query layer's weaknesses.** Done 2026-09-01 (ADR-019).
      55 independently authored questions, frozen before either router ran.
      Templates match no route shape on 35/49; on novel questions, 1/21.
      A cue-based fallback tier now runs on a template miss: 17 correct /
      26 complete evidence vs 10 / 11 for templates alone. Reproduce with
      `python -m comparison.harness` and `python -m comparison.ablations`.
- [x] **Decide whether an LLM planner is warranted.** Done 2026-09-01
      (ADR-020). 19/49 answerable questions reached no route, which cleared
      the gate. Built as a third tier emitting a validated plan, never an
      answer, off by default. F-025 records the live fabrication it produced
      before the grounding guard existed.
- [ ] **Measure the planner tier.** It is currently unmeasured on the frozen
      set — running it there spends daily quota and gives a number that moves
      with OpenRouter's free lineup. Decide whether to spend one measured
      sweep (and cache it) before the report, or to report it as unmeasured.
- [ ] Re-verify the OpenRouter model rotations before the demo:
      `python -m src.clients.openrouter --verify`.
- [ ] Compare the sister repo's conflict detector against `src/query/conflict.py`
      (Phase 2 of the comparison; not yet measured — F-024 showed ours
      over-fires when used as a general per-edge filter).
- [ ] **`ai_usage/` is empty.** Challenge doc §4.1 requires the full AI chat
      logs exported as plain `.txt` **in the repo**, plus an
      `ai_usage/ai-usage-disclosure.md` naming which tools, for what, and which
      decisions the team made. Human–AI collaboration is **15% of the rubric**
      and is judged from exactly these logs plus the commit history. Mandatory —
      incomplete submissions are not evaluated. Export as work happens.
- [x] **Architecture diagram** — done 2026-09-02. `docs/diagrams/architecture.svg`
      (hand-authored, no toolchain, self-contained) plus `docs/architecture.md`,
      which also closes §5.2's `docs/architecture.md` item. ADR-022. Pinned by 10
      tests in `tests/test_diagram.py` that re-derive every number from the live
      corpus — verified by mutation, after the first version passed a deliberate
      117→125 change.
- [ ] **Team names, roles and contributions** are recorded nowhere in the repo
      and are required in the report (§5.3). Three owners in "Assign" below are
      still unfilled.
- [ ] `configuration-example/` is named in §5.2's recommended structure and is
      empty. (`docs/architecture.md` is done — see the diagram item above.)
- [ ] Decide F-026: `_strip_possessive` does not strip a bare trailing `s`, so
      three of 49 frozen questions are told a correctly-spelled name is a typo.
      MEASURED: stripping it resolves all three exactly. Needs its own
      measurement against plurals and names ending in `s` — see ADR-021.
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
