# The number sheet

Every figure the report, the video and the README are allowed to quote, with the
command that re-derives it. **Re-derive before the report is final and before
the demo is recorded.** Nothing here may be quoted from memory.

Last re-derived **2026-09-06** at commit `c573865`, whole sheet in one pass.

> **Why this file exists.** Eight stale numbers were found in one afternoon by
> grepping rather than trusting — including the sentence in `README.md` whose
> entire job is to stop a stale number being quoted, which was itself quoting
> one. A single sheet is cheaper to re-check than nine documents.

## Corpus

| Claim | Value | Command |
|---|---|---|
| Files scanned | 340 | `python -m src.ingest.pipeline` |
| Canonical documents | **317** | ″ |
| Evidence units | **30,553** | ″ |
| Duplicates collapsed | 22 | ″ |
| Scans transcribed | 17 of 17, 0 without text | ″ |
| Collections | wiki 150, ephemera 145, codex 18, chronicles 4 | ″ |
| Integrity | run this **first**, before trusting any surprise | `python -m src.ingest.integrity` |

The challenge document describes "415 documents"; the shipped archive contains
341 files (340 plus `sample_questions.json`). Report what we measured, in one
neutral sentence. Do not silently adopt 415, and do not accuse the organisers.

## Graph

| Claim | Value | Command |
|---|---|---|
| Entities | **118** (95 page-backed, 23 edge-only, 0 isolated) | `python -m src.graph.build` |
| Edges | **265** across 15 relations | ″ |
| Unmapped field names | **0** | ″ |
| Direction overrides | 3 (`Mentor -> mentor_of`, ADR-023) | ″ |
| Self-reference rows skipped | 6 (F-030, ADR-028) | ″ |

The graph builds **118 entities and 265 edges**. That sentence is deliberately
written in the shape `tests/test_docs.py` scans for — the table above states the
same two numbers, but a table row is not a pairing and the guard cannot read it.

Guarded: `tests/test_docs.py` re-derives the "N entities … M edges" pairing in
every live document from the graph that actually builds, so this pair cannot go
stale silently. `docs/diagrams/architecture.svg` is pinned by
`tests/test_diagram.py` the same way.

## Cross-collection attestation

| Claim | Value | Command |
|---|---|---|
| Units scanned | 27,415 | `python -m src.graph.corroborate` |
| Corroborated edges | **259 of 265 (97.7%)** | ″ |
| codex | 421 attestations on 242 distinct edges | ″ |
| chronicles | 115 on 86 | ″ |
| ephemera | 26 on 24 | ″ |

> **NOT GUARDED — the known weak spot.** `test_docs.py` checks the
> `entities … edges` pairing only; it deliberately skips fractions like
> "259 of 265 edges", because that shape also appears in historical prose and
> would false-positive. **These five rows went stale once already** (they were
> 416/238, 114/85, 25/23 before F-032 added four corroborated edges) and nothing
> caught it. Re-derive them by hand.

Wording that must travel with the claim: these passages **name both ends** of an
edge. Co-mention is not proof, and the answer page says "also attested in", never
"confirms". A test forbids the words *confirms* and *proves* in the rendered page.

## Node set (ADR-030)

| Claim | Value | Command |
|---|---|---|
| Entities the corpus treats as first-class with no node | **0** | `python -m eval.probes.entity_reachability` |
| Declared document subjects resolving | 78 of 79; the 79th is a corpus filename truncated mid-word | ″ |
| Infobox rows naming an entity the graph lacks | **0** | ″ |

**Quote "0 gaps of 79". Never quote the 578.** That figure is the capitalised-span
scan's upper bound and is dominated by extraction noise — a hand-check of 15
found 0 real entities (document titles, headings, prose fragments).

## Query layer

| Claim | Value | Command |
|---|---|---|
| Templates, dev 1B | **7/7** correct, 7/7 complete evidence | `python -m comparison.harness` |
| Templates, frozen 49 | no route shape on **36**; 10 correct / 11 routed = **91%** | ″ |
| Shipped three tiers | **22 correct / 31 complete evidence** | ″ |
| Ambiguous / unnecessary depth | 4 / 0 | ″ |
| Honest refusal | **6 of 6** unanswerable questions declined | ″ |
| Cue tier precision | 40% (ADR-019), against templates' 91% | `python -m comparison.ablations` |
| Three-hop set | **3 of 3** correct | `eval/multihop_3hop_draft.json` |

**Never quote 7/7 without 36/49 beside it.** 7/7 measures fit to seven
development questions; 36/49 measures routing capability on questions written
independently and frozen before either router ran.

**This number has moved five times**, in both directions, for five legitimate
reasons — ADR-019 (35) → ADR-021 (33) → ADR-025 (35) → ADR-029 (36), with
ADR-031 and ADR-033 moving the correct/complete counts but not the 36. Re-derive
it; do not average remembered values.

**Complete evidence fell 31 → 29 while correct rose 19 → 21**, and that is
deliberate: three questions had been earning complete evidence by walking chains
the question never asked for (ADR-033). The lower number is the more honest one.

## Baseline (Checkpoint 1)

| Claim | Value | Command |
|---|---|---|
| 1B join questions | **2/7** | `python -m eval.run_eval --checkpoint baseline` |
| 1C conflict questions | 2/2 | ″ |
| All scored | 4/9, 11 not scored | ″ |
| Complete evidence | **0/9** — the number that matters | ″ |

Cached; costs no quota. The 1C result was predicted to fail and did not — the
codex announces its own authority in prose. Do not revive the claim that a naive
system answers 360 AS; it was measured false.

## Answer key — every number above is PROVISIONAL

| Claim | Value | Command |
|---|---|---|
| Confirmed entries | **0 of 9** | `python -m eval.completeness` |
| Status | 7 `single_review` (one reviewer), 2 `draft` (both 1C) | ″ |
| Recall risks | **0** | ″ |
| Precision risks | 0 | ″ |
| Open disputes | 1 (`1c_000`) | ″ |

`eval/run_eval` prints *"PROVISIONAL: 9/9 key entries are unverified"* itself.
`eval/answer_key.json`'s `_about.verification_state` says the same in the first
block a reader sees, and a test re-derives it from the entries.

No second human reviewer was available before the deadline (decided 6 Sep).
Nothing has been relabelled. An AI re-derivation agreed with all nine and does
**not** count — not a second human, not blind (F-029).

## Tests

**388 passing**, 0 network calls. `python -m pytest`.

## Before submission

1. `python -m src.ingest.integrity` — is the corpus still the shipped corpus?
2. Re-run every command above; correct any figure that moved.
3. **By hand:** the corroboration rows, which no test guards.
4. `python ai_usage/export_logs.py` with every other Claude Code window closed.
5. Warm the cache before recording the demo. Never record against a cold one.
