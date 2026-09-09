# Team, roles and contributions

Required by the challenge document §5.3. This file is the source for the
report's team section.

---

## Members

| Name | Role | Where the work is visible |
|---|---|---|
| **Mithil** | Implementation lead; author of record on the git history; answer-key reviewer | Every commit (`mithilyr <mithilrajapakse11@gmail.com>`); the repository at `github.com/mithilyr/CODEFEST---AI-Challenge` |
| **Yasiru** | Parallel prototype; source of the adopted cue-router design | `github.com/YasiruRF/delphi` — its cue-based router was measured against ours and partially adopted (ADR-019, `comparison/cue_router.py`, `comparison/REPORT.md`) |
| **Tatiana** | Question authoring; code review | The independently authored question sets (below); review passes on the implementation |
| **Kenolee** | Question authoring; code review | The independently authored question sets (below); review passes on the implementation |

### Why question authoring is a first-class contribution here

It is the reason one of this submission's headline numbers means anything.

`eval/robustness/routing_robustness_v1.json` holds 55 questions, authored
2026-08-31 and frozen the same day with its sha256 recorded in the file, **before
either router was run against it**. The file records its own independence
conditions:

> The author had no access to `src/query/route.py`, `engine.py`, `resolve.py`,
> `config/relations.yaml`, or either router implementation. […] `relations.yaml`
> was withheld specifically because it is the cue-based router's vocabulary
> source; an author who read it would have biased the comparison toward that
> router.

That withholding is the whole design. A question set written by someone who has
read the router's vocabulary tests the vocabulary, not the router. Because these
questions were written blind, **36 of 49 no route shape** — and **1 of 21 on the
novel questions** — is a measurement of routing capability rather than of fit,
and the team can say so without qualification. A judge can verify the freeze
date and hash independently of anything we assert.

The set is in three groups: 28 paraphrases of the dev questions across four axes
(synonym, reordering, indirect, colloquial), 21 novel multi-hop questions traced
by hand against the wiki, and 6 that the system *should* refuse.

The 55 questions were written jointly rather than split by group — nothing in
the repo records a division of the three groups between the two authors, and
this file states that rather than inventing a split for appearances.

**Code review, with a specific pointer.** Tatiana and Kenolee independently
reviewed all 9 entries in `eval/answer_key.json` on 2026-09-09 against
`eval/verification/answer_key_review.md`, which is the second human review
the file had been missing (`verification.status` was `single_review` ×7 and
`draft` ×2, 0 `confirmed`, all by one reviewer — F-015). Both reviewers signed
off on all 9 as `answer correct: yes`, `path correct: yes`, `answer set
complete: yes`, so every entry is now `confirmed` with `reviewers: [Tatiana,
Kenolee]`. This is the checkable specific §4.1 asks for: a named file
(`eval/verification/answer_key_review.md`), a named change
(`eval/answer_key.json`'s `verification.status`), and a named date. No defect
was raised in this pass — the corpus-shape defects in the 1C conflict
inventories (missing sources in `1c_000`/`1c_003`) were found earlier, by the
AI re-derivation on 6 Sep, not by this review.

---

## A note on the commit history, stated plainly

**Every commit in this repository carries a single author,
`mithilyr <mithilrajapakse11@gmail.com>`, although the team is four people.**

We are stating this rather than leaving a judge to discover it, because the
rubric has judges read the commit history as evidence of the team's working
process (§6, Human–AI collaboration, 15%), and a one-author log cannot evidence
four contributors on its own.

What we did **not** do, and will not do: rewrite or backdate the history to
distribute authorship after the fact. §5.2 asks that the history reflect the
team's actual working process. A fabricated log would satisfy the letter of that
line and violate the point of it, and §4's integrity rule treats
misrepresentation of what a team did as disqualifying. The log is accurate; it
is simply incomplete as a record of who contributed what, and this file is the
correction.

Implementation ran on one machine, Mithil's, which is the entire reason the log
has one author: every line of `src/`, `eval/`, `comparison/` and `tests/`, and
every ADR and failure entry describing it, was committed from there. The other
three did not write code against this repository. Tatiana and Kenolee's
contribution happened in parallel and offline from it by design — the 55-question
robustness set (`eval/robustness/routing_robustness_v1.json`) had to be authored
without reading `src/query/`, `engine.py`, `resolve.py` or
`config/relations.yaml`, because an author who had read the router's vocabulary
would have biased the comparison toward it (ADR-019). They then reviewed the
implementation from outside it, the same way a judge will. Yasiru's contribution
sits outside this repository entirely: a separate, independently written
prototype (`github.com/YasiruRF/delphi`) whose cue-based router was measured
against ours after the fact and partially adopted (ADR-019,
`comparison/cue_router.py`). None of that leaves a commit here, which is the gap
this file exists to close.

---

## Contributions not visible in git

Some of the work this submission depends on leaves no commit behind. Recorded
here because it is real, and because the report needs it.

| Contribution | Why it does not appear in the log | Who |
|---|---|---|
| The frozen 55-question robustness set (`eval/robustness/routing_robustness_v1.json`) | Authored by someone with **no access** to either router, to `src/query/`, or to `config/relations.yaml` — that isolation is the whole reason the number means anything (ADR-019). Committed by the implementer, authored by someone else | Tatiana, Kenolee |
| Code review of the implementation | Review leaves no commit unless it produces one; the reviewer's name is not in the log even when the fix is | Tatiana, Kenolee |
| Answer-key review (`eval/answer_key.json`) | Review is a judgement recorded in a JSON field, not a code change. Was **7 `single_review`, 2 `draft`, 0 confirmed**, all by one reviewer — the F-015 failure mode. **Resolved 2026-09-09**: all 9 now `confirmed`, second reviewer named in each entry | Mithil (first pass, 2026-08-29); Tatiana, Kenolee (second, independent pass, 2026-09-09) |
| Corpus analysis that produced the ADR-009..013 findings | Measurement runs, not commits, and not distinct from implementation — the same person who wrote the parser ran the probes that shaped it | Mithil |
| Sister-prototype comparison (ADR-019) | A second repository, `github.com/YasiruRF/delphi` | Yasiru |

---

## How to complete this file

Each member writes their own two lines. Be specific and checkable — an ADR
number, a file, a measurement, a document. "Backend development" is not a
contribution; "authored the 55-question frozen set without access to the router,
which is what makes 36/49 meaningful" is.

Good sources to draw from:

- `docs/decisions.md` — 36 ADRs, each a decision someone made
- `docs/failures.md` — 33 logged failures, each an approach someone tried
- `ai_usage/ai-usage-disclosure.md` — §4 already lists team calls that
  overturned the assistant
- `comparison/REPORT.md` — the router comparison

**Do not claim a contribution you cannot point at.** A judge may ask any member
to explain any part of the submission on demand (§4.1), and an overstated line
here is the question they will ask first.
