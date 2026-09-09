# Task checklist

Updated 2026-09-06. Deadline: 9 Sep 2026, 11:30 PM.

## Blocking — before push/share

Nothing blocking, measured 30 Aug 2026. Both items this section used to carry
are done: `origin` is configured
(`github.com/mithilyr/CODEFEST---AI-Challenge`), and the `src/graph/traverse.py`
/ `tests/test_graph.py` working-tree diff it named landed in `2775add`.
`git status` is clean.

## Must do

- [ ] Human-verify `eval/answer_key.json` — two people, per
      `eval/verification/answer_key_review.md`. Measured `verification.status`:
      `single_review` ×7, `draft` ×2, 0 confirmed, all reviewed
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
      Templates match no route shape on 35/49 as first measured; on novel
      questions, 1/21. A cue-based fallback tier now runs on a template miss:
      17 correct / 26 complete evidence vs 10 / 11 for templates alone.
      **Both headline numbers have since moved more than once, not on this
      task changing**: no-route-shape went 35 → 33 (ADR-021, four questions
      reclassified to `ambiguous_entity`) → back to **35** (ADR-025 fixed one
      of those four as a misdiagnosis, F-026 - restores a *more correct*
      `relation_unavailable` for `ederon fellgards`, not a regression). The
      shipped tier's complete evidence moved 26 → **27** (ADR-024, one
      question, `rb_044`) and stayed there through ADR-025.
      **Moved again 2026-09-06, and this time on real routing changes, not
      diagnosis**: no-route-shape 35 → **36** (ADR-029's coverage guard
      declines `rb_039`, which the cue tier then answers correctly), and the
      shipped tier went 17 → 18 → 19 → **22 correct** and 27 → 28 → 31 → 29 → **31
      complete evidence** across ADR-029, ADR-031 and ADR-033. Complete
      evidence going *down* while correct went *up* is deliberate and
      explained in ADR-033: three questions had been earning it by walking
      chains the question never asked for. Honest refusal reached **6 of 6**.
      Re-derived at `HEAD` 2026-09-06 with F-032's fix committed. Reproduce with
      `python -m comparison.harness` and `python -m comparison.ablations`;
      never quote 35, 33, 26, 27 or 28 without checking which still holds.
- [x] **Decide whether an LLM planner is warranted.** Done 2026-09-01
      (ADR-020). 19/49 answerable questions reached no route, which cleared
      the gate. Built as a third tier emitting a validated plan, never an
      answer, off by default. F-025 records the live fabrication it produced
      before the grounding guard existed.
- [x] **Measure the planner tier.** Decision taken 2026-09-09: spend one
      measured sweep (ADR-048), `python -m comparison.planner_sweep`, result
      cached at `comparison/results/planner_sweep.{json,md}`. Fires on 4 of 55
      (all previously `no_template_match`); correct 22→**26**, complete
      evidence 31→**35**; refusals unaffected, 6/6. Do not re-run unless
      `src/query/planner.py`, `config/relations.yaml` or the frozen set
      changes — see `docs/numbers.md`.
- [x] Re-verify the OpenRouter model rotations before the demo:
      `python -m src.clients.openrouter --verify`. Run 2026-09-09 — it was
      not clean: `z-ai/glm-5.2:free` and `minimax/minimax-m3:free` had been
      delisted, both first-choice entries in `PHRASING_MODELS`/
      `PLANNER_MODELS` (F-038). Fixed; `--verify` now reports clean and
      `python -m pytest` is still 497/497.
- [ ] Compare the sister repo's conflict detector against `src/query/conflict.py`
      (Phase 2 of the comparison; not yet measured — F-024 showed ours
      over-fires when used as a general per-edge filter).
- [x] **AI chat logs exported.** Done 5 Sep — `ai_usage/` holds 12 session
      transcripts plus `ai-usage-disclosure.md` (`b17ad1e`), written by
      `python ai_usage/export_logs.py`. **Rerun before submission with every
      other Claude Code window closed**: a live session's `.jsonl` is still
      being appended to and exports truncated, and three of the twelve were
      open during the 5 Sep run. Then re-run the secret grep in CLAUDE.md.
- [x] **Architecture diagram** — done 2026-09-02. `docs/diagrams/architecture.svg`
      (hand-authored, no toolchain, self-contained) plus `docs/architecture.md`,
      which also closes §5.2's `docs/architecture.md` item. ADR-022. Pinned by 10
      tests in `tests/test_diagram.py` that re-derive every number from the live
      corpus — verified by mutation, after the first version passed a deliberate
      117→125 change.
- [~] **Team names, roles and contributions** — `TEAM.md` now exists and is the
      source for the report's §6. Filled in 2026-09-09 from what the repo
      already records: the commit-history paragraph, who authored the frozen
      55-question set (Tatiana, Kenolee — already established, ADR-019), who
      reviewed the answer key (Mithil), and the ADR-009..013 corpus-analysis
      attribution. **One item deliberately left open, not invented**: a
      specific, checkable code-review pointer (a defect caught, a file read
      end to end, an ADR disagreed with) for Tatiana and/or Kenolee — nothing
      in the repo records one, and TEAM.md now asks for it directly rather
      than leaving the whole file blank. Fill that one paragraph if either of
      them is reachable before the deadline; ship without it otherwise, same
      as the answer-key second review.
      MEASURED 2026-09-07: all **117 commits** from 2026-08-28 to today carry a
      single author, `mithilyr <mithilrajapakse11@gmail.com>`. CLAUDE.md says a
      team of four. The rubric has judges read the commit history to verify
      sustained work, and §5.3 asks who did what — a one-author history cannot
      evidence four contributors, and it is too late to rewrite it honestly.
      Option (a) is taken: `TEAM.md` states the situation plainly rather than
      leaving a judge to discover it. Option (b) — the other three authoring
      their own commits from here to the deadline — is still open and still
      worth doing for whatever work remains.
- [x] `configuration-example/` — done. README, `authority.yaml`,
      `relations.yaml`, `env.example`. (`docs/architecture.md` done too.)
- [x] Decide F-026: `_strip_possessive` did not strip a bare trailing `s`, so
      three of 49 frozen questions were told a correctly-spelled name is a
      typo. Done 2026-09-02 (ADR-025) — the fix only suppresses a suggestion
      already about to be made when the trimmed span resolves exactly
      (never fuzzy), so it cannot widen what gets flagged as a typo. Measured
      against the risk ADR-021 flagged: 11 real entity names end in `s`, none
      collide when trimmed. No answer's correctness changed.
- [x] Rotate all API keys — done **5 Sep**, before the log export, not 8 Sep as
      planned. Do not rotate again unless a *new* key reaches a transcript.
- [x] Export AI chat logs to `ai_usage/` as work happens — 12 exported; rerun before submission (see above).
- [ ] Write the ≤5-page PDF report. Numbers come from `docs/numbers.md`, which
      is re-derived in one pass and guarded by `tests/test_docs.py` — do not
      quote a figure from memory or from an ADR. Include F-031, but tell it as
      **found and fixed the same day** (ADR-029), which reads better than the
      open version: the first guard was measured before being wired in and
      would have cost three correct answers. If §4 needs a defect that is still
      **open**, use the planner's unmeasured status or the single-reviewer key
      (F-015) — F-026, F-027 and F-031 are all closed.
- [x] Fix F-031 (a template consuming a two-hop shape inside a three-hop
      question). Done 6 Sep, ADR-029, **ahead of its own condition** — the
      entry said to wait for the report, video and team-roles items, and that
      was overridden by instruction. The gate it set was met exactly: templates'
      precision held at 10/11 = 91% and the dev 7/7 held. It also gained an
      answer nobody expected — `rb_039`'s template had been *blocking* a correct
      cue-tier result, so declining let the next tier through.
- [x] Fix both three-hop failures. Done 6 Sep. Neither needed the LLM planner,
      a prose extractor or a corpus change: all three gold chains were already
      in the graph with exactly one path each, and both failures were cue
      vocabulary in opposite directions — `3h_002` under-cued (ADR-031,
      `belongs`), `3h_003` over-cued (ADR-033, a unique cue word outranks a
      shared one). **3 of 3 now correct.** That is worth a sentence in the
      report next to the planner's status: it is evidence about where this
      system's remaining errors actually live.
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
