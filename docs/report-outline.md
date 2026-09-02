# Submission report — outline and evidence register

Drafted 2026-09-02. **This is the skeleton, not the report.** Its job is to fix
the structure, allocate the five pages, and bind every factual slot to the
command or artifact that produces it — so that drafting is transcription, not
recollection.

Rule for anyone writing into this: **if a number has no source line beside it,
it does not go in the report.** Three of this project's assumptions were
overturned by a five-minute check; the report is the worst place to discover a
fourth.

## Hard requirements (challenge doc §5.3)

A single PDF, **maximum 5 pages**, containing:

1. The unlisted YouTube video link, **at the top** (§5.1 — the upload timestamp
   is checked)
2. Problem statement and chosen sub-track
3. Solution overview and architecture, **with a diagram**
4. Key technical decisions and why we made them
5. What works, what doesn't, and limitations — **including approaches that failed**
6. AI Usage Disclosure
7. Team member names, roles, and contributions

Rubric weights the report can move: Problem understanding & insight 15%,
Human–AI collaboration 15%, Engineering best practices 15%, Technical judgment
& decisions 10%, Impact & relevance 10%, Presentation & documentation 10%.
Technical execution (25%) is carried by the demo and the repo, not by prose.

## Page budget

| § | Section | Pages | Rubric it serves |
|---|---|---|---|
| — | Header: video link, team, sub-track | 0.15 | mandatory |
| 1 | Problem, corpus, and why 1B is hard **here** | 0.60 | Problem understanding 15% |
| 2 | Architecture + diagram | 1.00 | Presentation 10%, Impact 10% |
| 3 | Key technical decisions | 1.25 | Technical judgment 10% |
| 4 | What works, what doesn't, failures | 1.25 | Judgment 10%, Execution 25% |
| 5 | AI Usage Disclosure | 0.50 | Human–AI collaboration 15% |
| 6 | Team, roles, contributions | 0.25 | mandatory |

Sections 3 and 4 are where this submission is differentiated. Everything else is
a requirement to satisfy efficiently, not an opportunity.

---

## §1 — Problem, corpus, and why 1B is hard here

**Claim: the corpus does not tell the whole story in any one document.**
Source: challenge doc §3; `README.md:14` worked example (`ederon_fellgard.md`
records membership and never names an accord).

**Claim: the shipped archive is 340 content files → 317 canonical documents →
30,553 evidence units.**
Source: `python -m src.ingest.pipeline`. Verify the archive first with
`python -m src.ingest.integrity` (341 files, 0 modified, 0 missing).

> **Insight worth one sentence.** The challenge doc describes "415 documents and
> about 1,277 pages". The shipped archive contains **341 files** — 340 documents
> plus `sample_questions.json` — measured, and integrity-checked against the
> download. We report what we measured and say so. Do not silently adopt 415;
> do not accuse the organisers of an error either. One neutral sentence.

**Claim: deduplication is collection-dependent.** `chronicles/` and `codex/`
ship the same work as `.docx` and `.pdf` (similarity 1.000, 0.989);
`ephemera/` same-stem files are **different documents** (0.019–0.048), so
collapsing them deletes evidence. 22 duplicates collapsed, not 340−317=23 by
filename.
Source: ADR-003; `python -m eval.probes.corpus_shape`.

This section's job is to show we understood *this* corpus, not "multi-hop QA".
The three sharpest specifics, one line each: the asymmetric graph (the Silent
Choir's members live in two disjoint places with **zero overlap**), the alias
divergence (`[[Iron-Ring Cartel]]` vs "The Iron-Ring Cartel"), and the
adversarial name space (19 shared surnames; `caedmon_fellgard` /
`ederon_fellgard` at **0.839** similarity).
Source: CLAUDE.md "Corpus facts", each traced to a probe.

## §2 — Architecture, with diagram

**Ready.** `docs/diagrams/architecture.svg`, explained in `docs/architecture.md`
(ADR-022). Self-contained SVG, so it drops straight into the PDF with no export
step. Every number in it is re-derived by `tests/test_diagram.py`, so the figure
in the report cannot disagree with the repo.

Depicted: `ingest → OCR → evidence units → graph build → query tiers
→ synthesis → UI`, with the three routing tiers drawn as a decision chain and
the two LLM entry points marked as *off by default*.

**Claim: 117 entities, 267 edges, 15 relations, 0 unmapped field names.**
Source: `python -m src.graph.build`.

**Claim: three tiers, each declining rather than guessing.**
Source: ADR-017, ADR-019, ADR-020; `src/query/evidence.py` `routing_tier`.

**Claim: the UI adds no reasoning of its own.**
Source: ADR-018, pinned by three architectural tests.

## §3 — Key technical decisions

One paragraph each, each ending in the measurement that decided it. Candidates,
in the order they most reward reading:

1. **Deterministic-first, LLM as a counted fallback** — ADR-002. The LLM tiers
   are *off by default*; F-025 is why (a well-formed plan, confidently wrong).
2. **No graph database / no vector DB / no agent framework** — 117 entities and
   267 edges is a Python dict; 3,392 chunks is a NumPy matmul. The binding
   reason is not performance, it is that every member must defend every part
   (challenge doc §4.1).
3. **The infobox parser keys on table position, not headings or field names** —
   ADR-009. 109 field names express ~12 relations; 6 pages have no `## Infobox`
   heading at all, one of them hop 2 of `1b_003`.
4. **Infobox cells are sentences, and the sentence set is closed** — ADR-010.
   12 templates cover **all 651 cells**, re-derived from the live corpus by
   `tests/test_graph.py::test_every_corpus_cell_falls_into_the_twelve_templates`
   on every test run.
5. **Exact-match entity resolution; fuzzy matching may never pick a winner** —
   ADR-011, and ADR-021 for how a near miss is *reported* without being
   resolved.
6. **Routing was adopted on a measured comparison, not preference** — ADR-019,
   `python -m comparison.harness`.

Pick four. Six paragraphs will not fit in 1.25 pages.

## §4 — What works, what doesn't, limitations, failed approaches

This section is the submission's strongest asset and the easiest to weaken by
overclaiming. Rules:

**Never quote 7/7 without the robustness number beside it.** Templates answer
**7/7 dev 1B** questions (ADR-017) *and* match no route shape on **35 of 49**
independently authored questions — on the 21 novel ones, **one**. Both
sentences, always together.
Source: `python -m comparison.harness`. Re-run it the day the report is
finalised — this number has moved twice already, in opposite directions, for
two legitimate reasons: ADR-019 first measured 35; ADR-021's near-miss
reporter dropped it to 33; ADR-025 fixed a misdiagnosis inside that drop
(F-026) and it is 35 again, now for the *right* reason. Do not average or
split the difference — re-derive it, don't guess at a number between two you
remember.

**The baseline comparison, stated precisely.** Vector baseline: 1B **2/7**, and
**0/9 complete evidence** — not one question retrieved every document its
answer needs. Graph: **7/7 complete evidence** on dev 1B.
Source: `python -m eval.run_eval --checkpoint baseline`; ADR-016.
Caveat that must appear: 7/7 complete evidence is **evidence coverage, not
answer correctness**, and ADR-016 says so itself.

**Every number is PROVISIONAL until the key is two-person verified.**
Source: `eval/results/baseline_latest.md` prints this banner itself: 2 draft,
6 single_review, 1 unresolved. `python -m eval.completeness` reports 0 recall
risks and 1 dispute needing a human (`1c_000`). Say this plainly — a team that
labels its own numbers provisional reads as more credible, not less.

**Failed approaches — pick four from `docs/failures.md` (F-001…F-027).** The
four that carry the most signal:
- **F-025** — an LLM plan that was well-formed, validated, and about nothing.
  Well-formedness is not relevance.
- **F-016** — opening a read-only corpus in an editor rewrote 36 files.
- **F-010** — fuzzy entity matching, killed by the 0.839 measurement.
- **F-026** — the typo reporter that calls a correctly-spelled name a typo,
  found by re-running the frozen set. **No longer open** — fixed 2026-09-02
  (ADR-025). Still worth telling as "found by re-running the frozen set, not
  by a unit test," which is the actual lesson; drop the "still open" framing
  from whatever prose gets written, or swap in a genuinely open item instead
  (the planner being unmeasured, gap 6 below, is the honest one left).

  *A fifth candidate worth weighing against these four:* **F-027** — a graph
  edge with every provenance field correct (real document, real field, real
  row, real cell) and the arrow pointing backwards; 3 of 267 edges, 37% of
  `mentor_of`. Nothing in the tests, the summary, or the score caught it — the
  score was byte-identical before and after the fix. It is the sharpest
  illustration in the repo of this section's own opening claim ("a confident,
  well-formatted, wrong result"), and unlike F-026 it is *closed*, which cuts
  the other way for a section that wants at least one open defect on display.
  Not substituted in here — that trade is an editorial call for whoever
  drafts this section, not one to make silently in the outline.

**Two claims that are dead and must not be revived.** The 1C baseline does
*not* answer 360 AS — measured, false. And the authority-tier layer is *not*
load-bearing for score: all 7 conflicts are codex-vs-ephemera and the codex
announces itself in prose in all 7 (ADR-013 + its CORRECTION). The layer is
retained for auditability; ADR-013 records the condition for deleting it.

## §5 — AI Usage Disclosure

**BLOCKED — `ai_usage/` is empty.** See the gap register.

Must state: which tools, for what, and **which decisions were made by the
team**. The rubric (15%) says evidence comes from the chat logs, the disclosure,
and the commit history — so this section should point at specific commits where
a human overrode the AI, not make general claims about collaboration.

Concrete, verifiable examples available today:
- ADR-019 adopted a cue-based router **only after** a 55-question comparison the
  team froze first — `commit 879cb6d` measured it, `d8992cd` adopted it.
- F-025: the team caught a validated-but-irrelevant plan by running it against
  nonsense questions, and added three guards.
- ADR-021's profile tier was **narrowed after two existing tests caught the
  first version answering a question nobody asked**.

## §6 — Team, roles, contributions

**BLOCKED — recorded nowhere in the repo.** Four names, roles, and what each
person owned. `docs/TODO.md` still has three unassigned owners.

---

## Gap register — what blocks the report today

Ordered by risk. The first three are mandatory-deliverable gaps, not polish.

| # | Gap | Required by | State |
|---|---|---|---|
| 1 | `ai_usage/` is **empty** — no chat logs, no `ai-usage-disclosure.md` | §4.1, §5.2, and 15% of the rubric | not started |
| ~~2~~ | ~~no architecture diagram~~ | §5.2 *and* §5.3 | **done** 2026-09-02, ADR-022 |
| 3 | Team names, roles, contributions recorded nowhere | §5.3 | not started |
| 4 | Answer key not two-person verified — every number is PROVISIONAL | ADR-014, F-015 | 2 draft, 6 single_review, 1 unresolved |
| 5 | `configuration-example/` empty (`docs/architecture.md` now done) | §5.2 recommended structure | partly done |
| 6 | Planner tier unmeasured on the frozen set | open decision, `docs/TODO.md` | deliberate; must be *stated*, not hidden |
| 7 | Video not recorded; link is the first line of the report | §5.1 | not started |

Gaps 1–3 are cheap and are worth more marks per hour than any further code.
Gap 1 in particular compounds: the logs must be exported **as work happens**,
and all API keys rotated before the export on 8 Sep.

## Drafting rule

From `docs/session-prompt.md`, and it applies to every paragraph above:

> Every factual claim must be traceable to a measurement in `eval/results/`,
> `docs/decisions.md`, or a command I can run right now. If a claim cannot be
> backed, flag it instead of writing it.
