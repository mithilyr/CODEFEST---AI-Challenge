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

**Claim: 117 entities, 261 edges, 15 relations, 0 unmapped field names.**
Source: `python -m src.graph.build`.

**Claim: three tiers, each declining rather than guessing.**
Source: ADR-017, ADR-019, ADR-020; `src/query/evidence.py` `routing_tier`.

**Claim: every answered hop arrives carrying attestation from the other three
collections.** The graph is built from wiki infobox rows, because only wiki
pages have infobox tables — but each edge is matched against the 27,415
non-wiki paragraphs and carries up to three passages that name both of its
ends, with document, locator, collection and tier.
Source: ADR-027; `python -m src.graph.corroborate`.

> **CAVEAT — the diagram does not show this yet.** `architecture.svg` depicts
> `ingest → OCR → evidence units → graph → tiers → synthesis → UI` and has no
> corroboration box. `tests/test_diagram.py` re-derives every *number* in the
> figure and would not notice a missing *component*, so the guard that protects
> the rest of §2 does not cover this. Either add the box before the figure goes
> in the PDF, or do not make the claim beside a diagram that contradicts it.
> Logged as gap 8.

**Claim: the UI adds no reasoning of its own.**
Source: ADR-018, pinned by three architectural tests.

## §3 — Key technical decisions

One paragraph each, each ending in the measurement that decided it. Candidates,
in the order they most reward reading:

1. **Deterministic-first, LLM as a counted fallback** — ADR-002. The LLM tiers
   are *off by default*; F-025 is why (a well-formed plan, confidently wrong).
2. **No graph database / no vector DB / no agent framework** — 117 entities and
   261 edges is a Python dict; 3,392 chunks is a NumPy matmul. The binding
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
**7/7 dev 1B** questions (ADR-017) *and* match no route shape on **36 of 49**
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

**Every number is PROVISIONAL until the key is two-person verified.** Decided
2026-09-06: no second human reviewer is available before the deadline, so
nothing has been relabelled. **Write this paragraph, close to verbatim, and put
it near the 7/7 rather than in a footnote:**

> The answer key these numbers are scored against is single-reviewer.
> Measured: 0 of 9 entries confirmed — 7 reviewed once by one team member on
> 29 August, 2 (both 1C) never human-reviewed at all. Recall is independently
> corroborated: `eval/completeness.py` enumerates the corpus in every
> direction and reports 0 recall defects across all nine, with one open
> semantic dispute on `1c_000`. What that check cannot do is judge precision —
> whether a recorded answer is the *right* one — and that is exactly what a
> second reviewer is for. So **7/7 on the dev questions is a self-graded
> result on a key this team authored**, and the honest externally-facing
> number is the 49-question comparison the team froze before either router
> ran: templates match no route shape on 35 of them. We know this distinction
> matters because we have already been caught by it: one careful reviewer
> reported 2 valid answers for `1b_006` where the corpus has 14 (F-015), and
> the fourteen were found by enumeration, not by a person.

Source: `eval/answer_key.json` `_about.verification_state`, re-derived from the
entries by a test so it cannot go stale; `python -m eval.completeness`;
`python -m eval.run_eval --checkpoint baseline`, which prints
*"PROVISIONAL: 9/9 key entries are unverified"* itself; F-015 and its amendment.

**And the key is not the only reason 7/7 needs qualifying.** F-031, found 6 Sep:
on a *three*-hop question the `victory_membership` template matches the two-hop
shape nested inside it, walks from the wrong start entity, and answers
**confidently and wrongly** — `sufficient`, one value, a clean citation trail.
Every acceptable path in `answer_key.json` is two hops, so the dev set cannot
expose this by construction. That is the sharpest illustration in the repo of
this section's own opening claim, and unlike F-026 and F-027 it is **open**.
Source: F-031; reproduce with
`python -m src.query.engine "Which war was won by the faction that Hesper Wrenfield's mentor belongs to?"`.

> **Do not soften this into "lightly reviewed" or omit the 0 of 9.** A judge who
> opens `eval/answer_key.json` sees `0 confirmed` in the first block of the
> file. Volunteering it is worth more than the 7/7 it qualifies; being caught
> holding it back costs the 7/7 *and* the credibility of every other number. `python -m eval.completeness` reports 0 recall
risks and 1 dispute needing a human (`1c_000`). Say this plainly — a team that
labels its own numbers provisional reads as more credible, not less.

**Failed approaches — pick four from `docs/failures.md` (F-001…F-030).** The
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

**The cross-collection claim, stated precisely.** **255 of 261 edges (97.7%)**
are independently named by a codex, chronicle or ephemera passage — 416
attestations from the codex on 238 edges, 114 from the chronicles on 85, 25
from the ephemera on 23. So an answer assembled from wiki infoboxes visibly
spans collections, with citations a judge can open.
Source: ADR-027, ADR-028; `python -m src.graph.corroborate`.
Two caveats that must travel with it, because both are the section's own rule:
- **Co-mention is not proof.** A passage naming both ends is evidence the
  archive discusses them together, not a second assertion of the relation. The
  page says "also attested in", and a test forbids "confirms"/"proves" in the
  rendered HTML. F-014's lesson mirrored: proximity is not agreement.
- **Volume is not evidence.** The chronicles are 82% of the corpus by evidence
  unit and produce the *fewest* useful attestations per unit; the codex, at 808
  paragraphs, carries the restatements. Worth one sentence — it is the most
  counter-intuitive measurement in the repo.

**The node set, measured — the boundary the corroboration figure does not
cover.** 255/261 measures edges *between entities the graph already holds*. The
graph's nodes come from wiki infobox rows, so an entity only the prose names has
no node and a question about it declines by construction. **Measured 6 Sep
(ADR-030):** of the **79** non-wiki documents that declare their own subject in
the filename, **77 reach a graph node**. Of the two that do not, one is a corpus
filename truncated mid-word, leaving **exactly one entity the corpus treats as
first-class with no node — Halvard Cindervale**, named in 21 evidence units
across the codex, the ephemera and the wiki.
Source: `python -m eval.probes.entity_reachability`; ADR-030; F-032.

Three things must travel with that number, in this order:

- **The cause is ours, and it is one row.** `wiki/the_ashen_vanguard.md` writes
  `| Members | Halvard Cindervale; Voltaire Hollowmere; Orin Veyra |` with no
  `[[links]]`, and an unlinked infobox cell can only resolve against entities
  that already own a wiki page. It is a defect (F-032), not a limit of the
  corpus, and it is disclosed rather than fixed: the fix moves the graph to
  118/264, reddens `tests/test_diagram.py`, invalidates the 117/261 quoted in
  five documents, and changes no measured answer three days out.
- **The user is told, not just the reader of this report.** The question returns
  `EvidenceStatus.OUTSIDE_STRUCTURED_COVERAGE`, and the demo renders *"Present
  in the corpus, absent from the graph"* with the reason, the file that imposes
  it, and quoted codex/ephemera/wiki passages with tiers. This is the strongest
  live demo of the decline machinery in the repo — **show it from the UI**, not
  from `python -m src.query.engine`, which lacks the evidence-unit scan the
  status needs and degrades to `unresolved_entity`.
- **Do not quote the 579.** The probe's second, noisier extractor finds 741
  distinct capitalised names outside the wiki, 579 of which reach no node. A
  hand-check of 15 found **0 genuine entities** — document titles, section
  headings, form labels, and verbs swept in beside names that do resolve. The
  honest number is 1 of 79. Quoting 579 would be exactly the overclaim this
  section exists to avoid.

This is also what repairs a soft spot in ADR-027's reasoning, and saying so is
worth a sentence: ADR-027 declined to build a prose relation extractor partly
because the wrong answers named only wiki pages in `required_evidence` — which
was itself derived from the wiki-built graph, so the argument was partly
circular. This measurement supplies the non-circular half: **the corpus does not
carry a population of prose-only entities an extractor would have found.**

**A refusal worth reporting as a result.** We did not wire the corroborating
passages into the conflict detector. `_DENIAL_RE` matches 5 units across the
whole non-wiki corpus, **0** attached to any edge, and **all 5 are false
positives** — two of them *affirm* the claim they appear to deny ("entered
without triumph or lament: The Silent Choir victor of The War of Drowned
Light"). Wiring it would let a tier-1 codex passage render as a denial of a
tier-2 wiki edge, manufacturing a conflict and resolving it against the truth.
A test pins the zero.
Source: ADR-027; `tests/test_corroborate.py`.

**Two claims that are dead and must not be revived.** The 1C baseline does
*not* answer 360 AS — measured, false. And the authority-tier layer is *not*
load-bearing for score: all 7 conflicts are codex-vs-ephemera and the codex
announces itself in prose in all 7 (ADR-013 + its CORRECTION). The layer is
retained for auditability; ADR-013 records the condition for deleting it.

## §5 — AI Usage Disclosure

**Ready.** `ai_usage/` holds **12 session transcripts** plus
`ai-usage-disclosure.md`, exported by `python ai_usage/export_logs.py`
(commit `b17ad1e`). All three API keys were rotated **5 Sep**, before the
export. **Rerun the export before submission with every other Claude Code
window closed** — a live session exports truncated, and three of the twelve
were open during the 5 Sep run.

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

Re-checked 2026-09-06. Three of the seven closed since this table was written.

| # | Gap | Required by | State |
|---|---|---|---|
| ~~1~~ | ~~`ai_usage/` empty~~ | §4.1, §5.2, 15% of rubric | **done** — 12 transcripts + disclosure, `b17ad1e`; keys rotated 5 Sep. Rerun the export with other sessions closed |
| ~~2~~ | ~~no architecture diagram~~ | §5.2 *and* §5.3 | **done** 2026-09-02, ADR-022 |
| 3 | Team names, roles, contributions recorded nowhere | §5.3 | **not started — now the top risk** |
| 4 | Answer key not two-person verified — every number is PROVISIONAL | ADR-014, F-015 | 7 single_review, 2 draft, **0 confirmed**; one human. An AI re-derivation agreed with all nine and does *not* close it (F-029) |
| ~~5~~ | ~~`configuration-example/` empty~~ | §5.2 recommended structure | **done** — README, `authority.yaml`, `relations.yaml`, `env.example` |
| 6 | Planner tier unmeasured on the frozen set | open decision, `docs/TODO.md` | deliberate; must be *stated*, not hidden |
| 7 | Video not recorded; link is the first line of the report | §5.1 | not started |
| 8 | `architecture.svg` has no corroboration box, but §2 and §4 now claim the layer | §5.2 | **new** — the diagram test pins numbers, not components, so nothing catches this |

**Gaps 3 and 7 are the only mandatory-deliverable gaps left**, and 3 is four
names in a file. Gap 4 cannot be closed by more AI review — F-029 records that
attempt and why it failed; the honest move is to label the numbers provisional,
which the harness already does itself.

Gap 8 is cheap and worth doing *before* the figure is exported: making the claim
in §4 beside a diagram that omits the component is the kind of small
inconsistency a judge notices and generalises from.

## Drafting rule

From `docs/session-prompt.md`, and it applies to every paragraph above:

> Every factual claim must be traceable to a measurement in `eval/results/`,
> `docs/decisions.md`, or a command I can run right now. If a claim cannot be
> backed, flag it instead of writing it.
