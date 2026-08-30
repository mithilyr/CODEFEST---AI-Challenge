# Ashen Era Intelligence Assistant

A document assistant that answers questions whose answers live in **more than one
document**, over the Ashen Era Archive — 317 documents of fictional fantasy lore.

Built for **SLIIT Codefest 2026, AI Competition sub-track 1B — Connecting Facts
Across Thousands of Pages**, powered by IFS.

---

## The problem, and why the obvious solution does not work

Ask *"Which accord was ultimately won by the faction of which Ederon Fellgard is a
member?"* and no single page answers it. `wiki/ederon_fellgard.md` records his
membership and never mentions an accord. The page naming the accord's victor never
mentions Ederon Fellgard. The two share no vocabulary, and the second hop is a
*reverse* lookup — given a faction, find the conflict it won.

We measured what conventional semantic retrieval does with this. A competent
Voyage-embedding vector RAG baseline over the deduplicated corpus:

```
1B answer correctness      2 / 7
complete evidence          0 / 7      <- the number that matters
```

Not one question retrieved every document its answer needs. **Three of seven
reached neither required document**, so the join never got a chance to fail.
Both questions it scored "correct" reached one document of two — right answers by
the wrong route.

Raising `k` cannot manufacture a join. So the system is **graph-first with vector
fallback**: parse the explicit relationships the corpus states structurally,
traverse them deterministically, and keep every hop's evidence attached.

---

## Quickstart

Python 3.11+. Windows paths shown; substitute `source .venv/bin/activate` and
`.venv/bin/python` on macOS or Linux.

```bash
git clone https://github.com/mithilyr/CODEFEST---AI-Challenge.git
cd CODEFEST---AI-Challenge
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Get the corpus

The archive is ~123 MB of read-only competition data and is **not committed**.

```bash
curl -o Ashen_Era_Archive.zip \
  https://benchdata792fda32.blob.core.windows.net/codefest2026/Ashen_Era_Archive.zip
```

Extract it so that `data/Ashen_Era_Archive/` contains `chronicles/`, `codex/`,
`ephemera/`, `images/` and `wiki/` — or put it anywhere and set `CORPUS_PATH` in
`.env`.

### Configure

```bash
cp .env.example .env
```

Fill in the keys you need. **Everything below runs from cache without any key**;
keys are only required to re-transcribe scans or rebuild the embedding index.

| Variable | Needed for | Free tier |
|---|---|---|
| `CORPUS_PATH` | everything | — |
| `GOOGLE_API_KEY` | OCR of the 17 scanned PDFs, LLM synthesis | [aistudio.google.com](https://aistudio.google.com/apikey) |
| `VOYAGE_API_KEY` | rebuilding the embedding index | [voyageai.com](https://dashboard.voyageai.com) |
| `VOYAGE_TIER` | set to `paid` once a card is added — removes a throttle that turns a 5-minute index build into 2 hours | — |

`.env` is gitignored and must never be committed.

### Verify the setup

```bash
python -m src.ingest.integrity   # is your corpus the corpus we measured against?
python -m pytest                 # 143 tests
python -m src.ingest.pipeline    # 340 files -> 317 docs -> 30,553 evidence units
python -m src.graph.build        # 117 entities, 267 edges
```

The integrity check exists because our corpus once silently drifted from the
shipped bytes — a text editor rewrote 36 files and left an empty note behind that
ingested as a real document (`docs/failures.md`, F-016). It compares every file
against a committed manifest of 341 SHA-256 hashes and exits non-zero on any
difference.

---

## Architecture

```
Corpus ─→ Ingestion ─→ Collection-aware dedup ─→ Authority ─→ Evidence units
                                                                    │
                                    ┌───────────────────────────────┴────┐
                                    ▼                                    ▼
                          Deterministic graph                     Vector index
                     (cell parsing → provenance)              (Voyage + NumPy)
                                    │                                    │
                                    └──────────→ Question ←──────────────┘
                                                    │
                    entity resolution → traversal → sufficiency → synthesis
                                                    │
                                            answer + evidence path
```

**Deterministic-first. An LLM is a fallback, not a default — and every fallback is
counted.** Ingestion, deduplication, authority ranking, cell parsing, graph
construction, traversal, conflict extraction and scoring are all ordinary Python.
LLMs are confined to ambiguous entity disambiguation, question shapes no template
matches, OCR, and writing prose from evidence already retrieved.

### Deliberately not used

- **No graph database.** 117 entities and 267 edges is a dict of lists.
- **No vector database.** 3,392 chunks is a NumPy matrix multiply in milliseconds.
- **No agent framework.** LangChain/LangGraph/CrewAI would be code we did not write.

The competition requires every team member to explain and modify any part of the
submission on demand. A dependency nobody on the team can defend to a judge is a
liability, not a feature.

---

## Repository layout

```
src/ingest/     discovery, dedup, OCR, authority, evidence units, integrity
src/clients/    Gemini model rotation, Voyage embeddings, retry/timeout
src/baseline/   Checkpoint 1: chunker, vector index, naive RAG
src/graph/      cell parsers, entity keys, schema+provenance, build, traversal
eval/           answer key, deterministic scorer, harness, corpus probes
config/         authority.yaml, relations.yaml, corpus_manifest.sha256
docs/           ADRs, failure log, limitations, roadmap
tests/          143 tests
```

Two configuration files are deliberately *not* code, so a judge can disagree with
a line without touching Python: `config/authority.yaml` ranks source
trustworthiness, and `config/relations.yaml` maps 109 infobox field names onto 15
relations.

---

## Commands

```bash
python -m src.ingest.integrity                   # verify corpus against manifest
python -m src.ingest.pipeline                    # ingest, print summary
python -m src.ingest.ocr                         # transcribe scans (cached)
python -m src.graph.build                        # build graph, print coverage
python -m eval.probes.corpus_shape               # reproduce every ADR-009..013 number
python -m eval.run_eval --checkpoint baseline    # reproduce Checkpoint 1
python -m eval.verify_key                        # regenerate answer-key review pack
python -m eval.completeness                      # is the key narrower than the corpus?
python -m pytest                                 # 143 tests
```

Everything is cached. Re-running costs no API quota.

---

## Measured results

> **All scores below are PROVISIONAL.** The answer key has cleared independent
> *completeness* checking — `python -m eval.completeness` reports **0 recall
> defects** across all 9 scoreable questions, corroborating `1b_006`'s fourteen
> answers by a route independent of the graph. *Precision* review (is each answer
> right?) is still outstanding, so the harness continues to warn and we are not
> quoting these numbers as final.

### Checkpoint 1 — vector RAG baseline

```
1B  2/7      1C  2/2      all scored  4/9      complete evidence  0/9
```

Reproduce with `python -m eval.run_eval --checkpoint baseline` — cached, under a
second, no quota.

### Checkpoint 2 — deterministic graph (in progress)

```
entities 117  (95 page-backed, 22 edge-only, 0 isolated)
edges    267  across 15 relations, 0 unmapped field names
```

On the seven dev 1B questions, a bounded traversal reaches the answer entity and
touches **every required document for 7 of 7**, against the baseline's 0 of 7.

**Read that number carefully.** It measures *evidence coverage*, not answer
correctness. There is no query layer yet — nothing selects among candidate paths.
And endpoint-reachability flatters the graph: constraining each hop to the exact
relation sequence the answer key specifies gives **5 of 7**, because reaching the
right node by the wrong relation is not the same as having the evidence for the
claim. Fighting in a war is not winning it.

Two of those five misses are a **vocabulary mismatch, not a graph gap** — the
answer key names the relation `victor` where `config/relations.yaml` calls it
`victor_of`. The edges exist. Reconciling the two vocabularies is open work, and
we are reporting the unreconciled number rather than the flattering one.

---

## What this system does not do

Honesty about limits is part of the design, not an apology for it. See
`docs/limitations.md` for the full account.

- **Prose relations are invisible to the graph.** It reads infoboxes only. That is
  deliberate for this checkpoint — it keeps the measurement clean about what
  *structure* alone recovers.
- **One conflict question is not representable from infoboxes.** For `1b_009`, the
  Iron-Ring Cartel's page omits the Purge of Blackport from its `Victor of` row.
  Under our own rule that **silence is not denial**, an omission is not a
  contradiction — the actual denial is in prose and needs the claim extractor. The
  graph holds one assertion and one silence, and must not be read as having
  captured the disagreement.
- **Some scanned tables are clipped in the source images.** A system that guessed
  at the missing text would fabricate evidence, which is the failure this project
  exists to prevent. We transcribe what is visible.
- **Entity resolution is exact-match only.** It will abstain on a misspelled
  question where a fuzzy matcher would have guessed right. That trade is
  deliberate: `caedmon_fellgard` and `ederon_fellgard` are 0.839 similar and any
  threshold loose enough to be useful merges them.

---

## How this project works

Three of our assumptions were overturned by five-minute checks, and the record of
that is a deliverable rather than an embarrassment.

- **`docs/decisions.md`** — ADR-001..016. Where a measurement overturned an earlier
  decision, the original stays in the record with the correction beside it.
- **`docs/failures.md`** — F-001..020. Every approach tried and rejected, with the
  number that killed it. Nothing is removed after being fixed.
- **`docs/limitations.md`** — what the system does not do, and defects in the source
  material we cannot fix from our side.

Two entries worth reading if you want the flavour of the project: **F-015**, where
one careful reviewer reported "high confidence" on an answer with two valid
values and the corpus turned out to have fourteen; and **F-019**, where a textbook
BFS returned a correct-looking two-hop path sourced from one document instead of
the two the question needed, decided by nothing more principled than filename
ordering.

### Working rules

- Atomic commits whose messages say *why* and cite the measurement that drove them.
- Measure before asserting. If a claim is going into a doc, the report or the
  video, run the check first and show the evidence.
- Never commit API keys, `.env`, or the corpus archive.
- A component is not done because it executes — it is done when it has tests, its
  failure cases are covered, its provenance is preserved, and the docs are updated.

---

## Status

Ingestion, OCR, authority ranking, the Checkpoint 1 baseline and the deterministic
graph are built and measured. The query layer (`src/query/`) and UI (`src/ui/`)
are not yet started. Answer-key verification and the frozen held-out set are the
gating work — every number here stays provisional until they land.

See `docs/TODO.md` for the current sprint.
