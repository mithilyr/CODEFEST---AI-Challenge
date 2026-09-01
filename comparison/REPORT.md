# Router comparison — measured report

**Phase 1 deliverable.** Our four-template router (`src/query/route.py`) against the
sister prototype's cue-based router (`github.com/YasiruRF/delphi`, their ADR-019),
on one independently authored question set.

Nothing has been merged, ported into `src/`, or changed on `main`. This branch
(`comparison/router-eval`) holds the comparison only.

Run date 2026-08-31. Reproduce with:

```bash
python -m comparison.harness --set eval/robustness/routing_robustness_v1.json
python -m comparison.ablations
```

---

## Headline

| | arm A (four templates) | arm B (cue-based) |
|---|---|---|
| routed | **11 / 49 (22%)** | **30 / 49 (61%)** |
| answered correctly | 10 | **12** |
| complete evidence | 11 | **20** |
| precision when routed | **10/11 (91%)** | 12/30 (40%) |
| matched no route shape | **40 / 55** | 5 / 55 |
| honest refusal on unanswerable | **6 / 6** | 5 / 6 |

Answerable questions n=49; the 6 expected-unanswerable are scored inverted and
reported separately.

**Neither router wins outright, and the two fail in opposite directions.**

- Arm A is **precise and brittle**. When a template fires it is almost always right
  (91%), but a template fires on only 22% of realistic questions.
- Arm B is **broad and noisy**. It routes 2.7× as often and retrieves complete
  evidence for nearly twice as many questions, at less than half the precision.

Both convert their coverage into a similar number of correct answers (10 vs 12).
The difference that matters is **complete evidence: 11 vs 20**, on the metric this
project treats as the one that counts.

---

## The number that answers ADR-017's gate

ADR-017 deferred a planner until routing robustness had been measured. It has been.

> **The four templates match no route shape on 35 of 49 answerable questions (71%).**

Broken down: on the 28 paraphrases of our own dev questions, arm A matches 11 of 28.
On 21 novel questions over the same corpus, it matches **1 of 21**.

That last figure is the finding. The templates were fitted to seven questions and do
not generalise past re-wordings of them. This is not a defect of the implementation —
it does exactly what ADR-017 said it would — but it settles the open question. Our
7/7 on dev questions is a measure of fit, not of routing capability.

Arm A's honesty is intact throughout: of the 40 no-match cases it guessed at none.
It returns `no_template_match`, which is the designed behaviour and the reason its
precision stays at 91%.

---

## Where each arm actually fails

### Arm A — 38 answerable failures, all one shape

`no_template_match` ×35, `relation_unavailable` ×2, `path_missing_attribute` ×1,
`unresolved_entity` ×1. There is essentially one failure mode: the question does not
contain a trigger phrase. No wrong answers, no wrong routes, no over-deep traversal.

### Arm B — 18 routed-but-wrong, four shapes

1. **Stops one hop short and returns the intermediate node** (7 cases). The final
   relation is never cued, so the walk halts early and answers with the waypoint.
   `rb_003` returns *The Cinder-Wrought Aegis* where the answer is *Gloamreach*;
   `rb_023` returns *Marrowwell Abbey* where the answer is *The Bleeding Crown*.
   This is the most common and most dangerous failure: the output is confident,
   well-formed, and wrong, with a real evidence trail attached to it.
2. **Overshoots to three hops** (4 cases, `unnecessary_depth` 8 overall). Extra cued
   relations let the walk run past the answer.
3. **Ambiguity explosion** (5 `any_of` cases). `rb_047` returns
   *Hollowreach / Vault Chitin / Crookvale* for a question with one answer.
4. **Conflict-shaped questions** (4 cases, the `1b_009` paraphrases). Arm B returns
   the entity without surfacing the dispute.

Note on (4): our scorer credits a conflict question when the arm reports
`conflicting_evidence`, a status **arm B structurally cannot produce**. That would
have been a 4-question bias in arm A's favour. It did not fire — arm A returned
`no_template_match` on all four, so both arms scored 0/4. The headline numbers are
unaffected, but the asymmetry is recorded here rather than left latent.

---

## Guard ablations (Phase 2 input)

Each of the sister router's four guards switched off individually, same frozen set.

| variant | routed | correct | complete evidence | precision |
|---|---|---|---|---|
| as written | 30 | 12 | 20 | 40% |
| − coverage selection | 30 | **2** | **7** | **7%** |
| − irregular verbs | 30 | 9 | 17 | 30% |
| − tie-break stopwords | 30 | 13 | 19 | 43% |
| − consecutive-repeat guard | 30 | 12 | 20 | 40% |
| + symmetric stemming *(not theirs)* | 30 | 13 | 21 | 43% |

**Guard 2, relation-coverage-over-path-length, carries almost the entire router.**
Removing it collapses correctness 12 → 2 and complete evidence 20 → 7. Whatever else
is decided, this is the idea worth taking: prefer the path that covers every relation
the question named, then the shortest — not the longest chain, and not the shortest
by hop count alone.

**Guard 4, irregular verbs, is worth 3 questions** (12 → 9). Small, real, and cheap.

**Guard 1, consecutive-repeat prevention, changes nothing on this set** (12 → 12). It
was added against a measured failure in *their* stack; it does not reproduce here. Per
the critical-evaluation rule, it has no measured advantage in our system and should
not be ported on their evidence alone.

**Guard 3, tie-break stopwords, is neutral-to-negative here** (+1 correct, −1 complete
evidence). Below noise on a 49-question set. Not portable on this evidence.

### One defect found in arm B, and its size

Their stemmer strips suffixes only, so `ruled`/`rules`/`ruling` fold to `rul` while the
base form `rule` does not, and never matches the cue built from the field name
`Ruled by`. Measured: "falls under whose **rule**?" fails to cue `ruled_by`;
"which power **rules**..." succeeds. Same for `house` vs `hous`.

**Correcting it is worth one question** (12 → 13 correct, 20 → 21 complete evidence).
I initially expected this to explain much of arm B's low precision. It does not, and
that hypothesis is withdrawn — the 40% precision is a property of cue-based routing on
this corpus, not an artifact of a stemming bug.

---

## Method, and what would invalidate this

**Question set.** 55 questions, frozen before either router ran, sha256
`f3ad401148d0…b7d8` recorded in the file. 28 paraphrases (4 axes × 7 dev questions),
21 novel multi-hop, 6 expected-unanswerable. Authored by a party with no access to
either router, to `route.py`/`engine.py`/`resolve.py`, or to `config/relations.yaml` —
that last withheld specifically because it is arm B's vocabulary source, and an author
who read it would have biased the set toward arm B.

**Controlled variable.** Only path *selection* differs. Same graph, same `find_paths`,
same corpus, same conflict rule, same scorer (`eval/scoring.py`, including its negation
guard). Arm A runs unmodified through `answer_question`.

**LLM escalation disabled in both arms.** Arm B's router escalates to OpenRouter on an
unresolved entity or uncued relation; running that live would measure "has an LLM"
rather than "routes better". Those points are counted instead: **arm B would have
escalated on 11 of 55 questions** (6 paraphrase, 1 novel, 4 unanswerable). That is the
deterministic failure rate Phase 4 asked for.

**Four harness bugs were found and fixed before these numbers were trusted**, all mine,
each documented at its fix site:

1. Per-edge conflict filtering using our paragraph-scoped `find_denial` excluded the
   Cartel's uncontested Leaden Accord edge, turning `1b_007` and `1b_022` into false
   `not_found`s for arm B. Replaced with a port of their structural rule
   (`comparison/sister_conflicts.py`).
2. Bespoke string matching replaced with `eval/scoring.py`, so the comparison cannot
   grade on a kinder curve than our own eval harness.
3. Route comparison made direction-insensitive, per `walk_relations`' own rule.
4. Answer-key relation names normalised — the key writes `victor`/`has_member` where
   `relations.yaml` writes `victor_of`/`member_of`, the unreconciled gap the README
   already reports. Unnormalised it flagged arm A wrong-route on two correct answers.

**Validation.** With all four fixed, arm A reproduces ADR-017's 7/7 exactly on the dev
questions — correct, complete evidence, zero wrong routes. The harness is calibrated
against the one result we already know.

**What would invalidate this.** A 49-question answerable set is small; differences of
one or two questions (guards 1 and 3, the stemming fix) are not resolvable at this
size. The novel questions are one author's reading of the corpus. And group A is
paraphrases of questions arm A was fitted to, which if anything flatters arm A.

---

## Recommendation

Do not adopt either router wholesale. The measured case is:

1. **Port guard 2 (coverage-over-length) on its own merits** — it is the one component
   with a large, reproducible effect, and it is a *selection* rule that would apply to
   whatever produces candidate paths. Needs a regression test against our stack before
   it goes in.
2. **Do not port guards 1 and 3** on this evidence. Neither shows a measured advantage
   here. Re-test if the question set grows.
3. **Guard 4 (irregular verbs) is a judgement call** — 3 questions, trivially cheap,
   but only meaningful if cue matching is adopted at all.
4. **Keep our router's abstention behaviour.** 91% precision and 6/6 honest refusals
   are the strongest numbers in this table and they belong to arm A.

**On the template-vs-cue question, the honest answer is that neither is adequate
alone.** Arm A cannot see 71% of realistic questions. Arm B sees them and is wrong
about 60% of what it sees — and its dominant failure mode returns a confident wrong
answer rather than an abstention, which is worse than a miss for this project's claims.

That combination is the empirical case Phase 4 asked for, and it points at the
structure Phase 4 already specified: deterministic routing first, escalation only on
an explicit unresolved state, with the planner emitting a constrained plan that
deterministic traversal then validates and walks. The measurement says the
deterministic layer needs broader *reach* than four templates and stricter
*stopping* than cue coverage alone.

Phase 2 (individual guard porting with regression tests) and the ADR recording this
decision are the next steps. No code has moved into `src/`.

---

## Addendum, 2026-09-01 — three arms, and what shipped

The harness now runs **three** arms, because the cue tier was adopted and ships
inside `answer_question`. Reproducing arm A's templates-only column therefore
requires switching the fallback off explicitly (`use_fallback=False`), which the
harness does. An ADR that tells a reader to run a command has to keep producing
the number it quotes.

```
metric                        A templates   B cues   C shipped
route_success                          11       30          30
entity_resolution_success              13       46          32
answer_correct                         10       12          17
complete_evidence                      11       20          26
no_route_shape                         35        4          16
unnecessary_depth                       0        8           3
honest refusal (of 6)                   6        5           5
```

**Arm C is the shipped system** — templates first, cue fallback on a miss. It
beats both single-tier arms on the two numbers that matter (17 correct, 26
complete evidence) while inheriting arm B's cost: one honest refusal traded
away, and 16 questions still matching no route shape at all.

A third tier (an LLM planner, ADR-020) exists but is **off by default and not
measured here**. Running it against this set would spend daily quota and produce
a number that moves with OpenRouter's free-model lineup, so every figure in this
report remains deterministic and reproducible offline. What the planner is *for*
is the 19 answerable questions arm C still cannot route; how well it does that
is unmeasured, and is stated as unmeasured rather than estimated.

Reproduce all three:

```bash
python -m comparison.harness
python -m comparison.ablations
```
