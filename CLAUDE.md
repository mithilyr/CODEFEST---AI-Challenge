# Ashen Era Intelligence Assistant

Context for any AI assistant working in this repository. Read before making changes.

## What this is

SLIIT Codefest 2026 AI Competition, powered by IFS. We are building an intelligent
document assistant over the Ashen Era Archive, a 317-document fantasy corpus, for
**sub-track 1B — Connecting Facts Across Thousands of Pages**.

**Deadline: 9 September 2026, 11:30 PM.** Three deliverables: a git repo with full
history, a ≤5-page PDF report, and a ≤10-minute video with ≥3–4 minutes of unedited
live demo. Incomplete submissions are not evaluated.

Team of four, part-time, roughly 120 person-hours total. Nobody has an ML background;
everyone is fluent in Python.

## The single most important constraint

> Every team member must be able to explain, justify, and modify **any part** of the
> submission on demand. Inability to do so in the final round means disqualification.

This is why the architecture is what it is. Do not introduce a dependency, framework
or abstraction that a teammate could not defend to a judge in the room. When in doubt,
write the simpler thing.

## Architectural principle

**Deterministic-first at every stage. An LLM is a fallback, not a default — and every
fallback is counted.**

Each pipeline stage tries a deterministic resolution first and escalates to an LLM only
on an explicit, testable failure condition. The harness records how often each
escalation fires, so we can say "the LLM planner handled N% of held-out questions"
and show the number.

Graph traversal — the part that actually produces the answer — is plain Python over a
parsed data structure. LLMs are confined to ambiguous entity resolution, question
shapes no template matches, and writing prose from retrieved evidence.

### Deliberately not used

- **No graph database.** 125 measured entities is a Python dict.
- **No vector database.** 3,392 chunks is a NumPy matrix multiply in milliseconds.
  (Re-measured from the built index: 13,893,760 bytes / 1024 dims / 4 bytes = 3,392
  exactly. ADR-008's 3,364 is the stale figure.)
- **No agent framework.** LangChain/LangGraph/CrewAI would be code we did not write.

If you are tempted to add one of these, the answer is almost certainly no. Say why it
is needed and what it measurably improves, first.

## Current state

Ingestion, OCR, authority ranking and the Checkpoint 1 baseline are done and measured.
The knowledge graph is the next major piece and is **not yet built**.

| Component | State |
|---|---|
| `src/ingest/` | Done — 340 files → 317 canonical docs → 30,553 evidence units |
| `src/ingest/ocr.py` | Done — all 17 scans transcribed, cache committed |
| `src/clients/` | Done — retry, Gemini model rotation, Voyage embeddings |
| `src/baseline/` | Done — chunker, vector index, naive RAG (Checkpoint 1) |
| `eval/answer_key.json` | Drafted, **`verified_by` still null — needs human check** |
| `eval/` harness | Done — deterministic scoring, response cache, reproducible artifacts |
| `src/graph/` | **Not started** — next major piece |
| `src/query/` | Not started |
| `src/ui/` | Not started |

### Checkpoint 1 results (reproducible, not just measured)

Run them yourself — `python -m eval.run_eval --checkpoint baseline`. Cached, so it
costs no quota and takes under a second. **All numbers are PROVISIONAL until two
humans verify the answer key** (`eval/verification/answer_key_review.md`).

    1B 2/7    1C 2/2    all scored 4/9    not scored 11 (1A, untraced)
    Complete evidence: 0/9

- **1B join questions: baseline 2/7**, and the deeper number is **0/9 complete
  evidence**. Not one question retrieved every document its answer needs —
  including both 1B questions scored correct, which reached 1 of 2 each. Every 1B
  question caps at 0.50 recall. The two "correct" answers are right by the wrong
  route, which `answer_key.json` asks us to count as retrieval failures.
- **The old characterisation was wrong.** This file used to say failures are
  "retrieval never reaches the second document, or reaches it and cannot join".
  Measured: **3 of 7 reach neither document** (recall 0.00). The join never gets a
  chance to fail. The graph case is stronger than we were making it, but for a
  different reason than we wrote down.
- **Scoring caught itself being wrong.** The first sweep reported 3/7 because the
  negation guard missed "does not identify" in an answer that was a refusal. Do not
  trust a score without reading `failure_category`; `negated_gold` means the gold
  string appeared inside a denial.
- **1C conflict questions: baseline 2/2.** We predicted it would fail. It did not: the
  codex announces its own authority in prose ("The authoritative record states
  plainly…", "Popular accounts wrongly claim otherwise"), so the model follows that
  signal without our tier model. **Our earlier claim that a naive system answers
  360 AS was wrong.** The follow-up hypothesis — that the authority layer still matters
  where a source does not announce itself — **has now been tested and is not supported.**
  All 7 conflicts in the archive are codex (tier 1) vs ephemera (tier 4), and the codex
  announces itself in all 7. Tier and prose agree everywhere. The layer is retained for
  auditability, not for score; ADR-013 records the condition for deleting it.

Do not repeat the old claim in docs, the report, or the video.

## Corpus facts that will bite you

All measured. Several overturned an assumption we had already written down.

1. **Deduplication is collection-dependent.** `chronicles/` and `codex/` ship the same
   work as `.docx` and `.pdf` (similarity 1.000 and 0.989). `ephemera/` same-stem files
   are **different documents** (similarity 0.019–0.048) — collapsing them deletes real
   evidence. Plates in `images/` and `codex/images/` are byte-identical.
2. **107 distinct infobox field names express ~12 relations.** `Member of` / `Membership`
   / `Affiliation` are one relation; `Housed in` / `Place of housing` are another. A
   parser keyed on literal field names loses a third of the membership edges silently.
   (Measured 107, not the 110 previously written here — see ADR-009.)
3. **The graph is asymmetric and bidirectional.** The Iron-Ring Cartel records its own
   victories; The Silent Choir does not. The Silent Choir's members are recorded in
   **two disjoint places** — 6 on the faction page's `Members` row, 8 more on individual
   character pages, with zero overlap. Read both directions or lose half the edges.
4. **Infobox cells are sentences, not values.** Twelve templates cover all 651 cells
   (ADR-010). Multi-valued: `Victor of | The Winter Reckoning; The Leaden Accord` —
   split on `;`, then filter by type, because `1b_007` asks specifically for an *accord*.
   Two-argument: `Fought in [[Conflict]] for [[Faction]]` is **one ternary fact**, and
   both word orders occur — emitting two edges from the subject asserts something false.
   Qualified: `[[The Cinder-Wrought Aegis]], since 356 AS` — the qualifier is what
   `1b_003` asks about, so it belongs on the edge, not glued into the node name.
5. **Aliases diverge.** `the_purge_of_blackport.md` writes `[[Iron-Ring Cartel]]` without
   the leading "The" that every other reference uses. Without normalisation these are two
   nodes and `1b_009` never joins.
6. **Typographic punctuation.** The corpus uses U+2019 apostrophes. Already normalised in
   `loaders.py` — keep any new text path going through `normalise_punctuation()`.
7. **Some scanned tables are clipped in the source images.** Not our bug; see
   `docs/limitations.md`. Never invent text to fill a gap.
8. **Markdown emphasis hides every competing claim.** The ephemera wrap their decoy
   values in `**...**` (`founded in **286 AS**`) and the codex writes its own bare.
   An extractor that does not strip emphasis finds **zero** conflicts corpus-wide and
   reports full confidence — silent failure, the worst kind. See ADR-012.
9. **The infobox is the first pipe table, not the `## Infobox` section.** Six pages have
   no such heading, three of them artifact pages, one of which is hop 2 of `1b_003`.
10. **Node type is not on the wiki title.** Only 26 of 95 titles state a category. Type
    comes from the image filename taxonomy, which `metadata.py` already parses.
11. **The name space is adversarial.** 19 surnames are shared across entities
    (`fellgard` ×5); `caedmon_fellgard` and `ederon_fellgard` are 0.839 similar and
    `ederon_fellgard` is the subject of `1b_007`. Entity resolution is exact-match only
    — fuzzy matching may never silently pick a winner (ADR-011).

## Free-tier quotas — plan around these

| Provider | Limit | Consequence |
|---|---|---|
| Gemini | **~20 requests/day, per model** | A daily cap. Backoff cannot recover from it. `GeminiPool` rotates across 6 models, each with its own allowance. |
| Voyage | 3 req / 10k tokens per minute without a card | We have a card; `VOYAGE_TIER=paid` in `.env` removes the throttle. |

A full 44-question evaluation sweep costs roughly two models' daily quota. Do not burn
it on a run you have not finished debugging. Everything is cached — reruns are free.

**Never record the demo against a cold cache.**

## Commands

```bash
python -m src.ingest.integrity     # is the corpus the shipped corpus? (run first)
python -m src.ingest.pipeline      # ingest corpus, print summary
python -m src.ingest.ocr           # transcribe scans (cached; needs GOOGLE_API_KEY)
python -m pytest                   # 92 tests
python -m eval.probes.corpus_shape # reproduce every ADR-009..013 number
python -m eval.run_eval --checkpoint baseline   # reproduce Checkpoint 1
python -m eval.verify_key          # regenerate the answer-key review pack
```

Use the project venv: `.venv/Scripts/python.exe` on Windows.

## Working rules

These are graded — 30% of the rubric — and cannot be reconstructed at the end.

- **Atomic commits, daily.** Messages say *why*, and include the measurement that drove
  the change. Judges read the history to verify sustained work.
- **Record decisions in `docs/decisions.md`** using the existing ADR format. When a
  measurement overturns an earlier assumption, keep the assumption visible in the record
  rather than editing it out. Being wrong cheaply is the process working.
- **Keep a failure log** — approaches tried and rejected, with the number that killed
  them. The report requires this section.
- **Never commit API keys.** `.env` is gitignored. Rotate all keys before exporting AI
  chat logs on 8 Sep — the logs are a mandatory deliverable that judges read.
- **Do not commit the corpus** (~123 MB). `data/` is gitignored; the README documents
  the download.
- **The corpus is read-only, and that is not enforced by anything but us.** Opening it
  in an editor once cost us 36 rewritten files and a phantom document (F-016). Run
  `python -m src.ingest.integrity` before trusting a measurement you did not expect.
- **Export AI chat logs to `ai_usage/` as you go.**

## How to work here

Prefer measuring over asserting. This project has already had three assumptions
overturned by a five-minute check — deduplication, the 1C baseline failure, and the
answer key for `1b_006`. If a claim is going into a doc, the report or the video, run
the check first.

Challenge weak reasoning rather than agreeing. If something in this file is now wrong,
say so and correct it.
