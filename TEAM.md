# Team, roles and contributions

Required by the challenge document §5.3. This file is the source for the
report's team section.

---

## Members

| Name | Role | Where the work is visible |
|---|---|---|
| **Mithil** | Implementation lead; author of record on the git history | All 117 commits (`mithilyr <mithilrajapakse11@gmail.com>`); the repository at `github.com/mithilyr/CODEFEST---AI-Challenge` |
| **Yasiru** | Parallel prototype; source of the adopted cue-router design | `github.com/YasiruRF/delphi` — its cue-based router was measured against ours and partially adopted (ADR-019, `comparison/cue_router.py`, `comparison/REPORT.md`) |
| **Tatiana** | *[ROLE — to be completed by the team]* | *[TO BE COMPLETED]* |
| **Kenolee** | *[ROLE — to be completed by the team]* | *[TO BE COMPLETED]* |

> **The two placeholders above are deliberate and must be filled in before
> submission.** They are not an oversight: nothing in this repository records
> what Tatiana or Kenolee contributed, and inventing entries would be
> misrepresentation of exactly the kind §4's integrity rule forbids. Each person
> should write their own line. See *How to complete this file* below.

---

## A note on the commit history, stated plainly

**All 117 commits in this repository carry a single author,
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

*[TEAM: replace this paragraph with the true account of how you worked — e.g.
whether development ran on one machine with others reviewing, pairing, authoring
questions, or verifying. One honest paragraph is worth more than four names on a
table.]*

---

## Contributions not visible in git

Some of the work this submission depends on leaves no commit behind. Recorded
here because it is real, and because the report needs it.

| Contribution | Why it does not appear in the log | Who |
|---|---|---|
| The frozen 55-question robustness set (`eval/robustness/routing_robustness_v1.json`) | Authored by someone with **no access** to either router, to `src/query/`, or to `config/relations.yaml` — that isolation is the whole reason the number means anything (ADR-019). Committed by the implementer, authored by someone else | *[TO BE COMPLETED]* |
| Answer-key review (`eval/answer_key.json`) | Review is a judgement recorded in a JSON field, not a code change. Currently **7 `single_review`, 2 `draft`, 0 confirmed**, all by one reviewer — the F-015 failure mode, and why every eval number is still marked PROVISIONAL | *[TO BE COMPLETED]* |
| Corpus analysis that produced the ADR-009..013 findings | Measurement runs, not commits | *[TO BE COMPLETED]* |
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
