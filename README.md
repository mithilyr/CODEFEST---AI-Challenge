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
Voyage-embedding vector RAG baseline over the deduplicated corpus, on the seven
development 1B questions:

```
1B answer correctness      2 / 7
complete evidence          0 / 7      <- the number that matters
```

Not one question retrieved every document its answer needs. **Three of seven
reached neither required document** (recall 0.00), so the join never got a chance
to fail. Both questions it scored "correct" reached exactly one required document
— of the three and two they respectively needed. Right answers by the wrong route.

Raising `k` cannot manufacture a join. So the system is **graph-first**: parse
the explicit relationships the corpus states structurally, traverse them
deterministically, and keep every hop's evidence attached.

ADR-001 planned a *vector* fallback for questions the graph could not route.
That is **not what shipped, and this line used to say otherwise.** The fallback
that exists is deterministic cue routing (ADR-019), adopted because it was
measured to recover more than the vector arm for a fraction of the machinery;
the vector index remains as the Checkpoint 1 comparison arm and is not on the
answer path. Nothing in `src/query/` or `src/ui/` imports `src/baseline/`.

---

## Quickstart

Python 3.11+. Windows paths shown; substitute `source .venv/bin/activate` and
`.venv/bin/python` on macOS or Linux.

### Run the demo

From a clean clone to a working UI at **http://127.0.0.1:8000**.
**No API key is needed for any of this** — the answer path is deterministic
Python over committed caches, and the model tiers are off by default.

```bash
git clone https://github.com/mithilyr/CODEFEST---AI-Challenge.git
cd CODEFEST---AI-Challenge
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Get the corpus (~123 MB, not committed):

```bash
curl -o Ashen_Era_Archive.zip https://benchdata792fda32.blob.core.windows.net/codefest2026/Ashen_Era_Archive.zip
```

Extract it so that **`data/Ashen_Era_Archive/` is the directory that directly
contains** `chronicles/`, `codex/`, `ephemera/`, `images/` and `wiki/`. If your
unzip tool adds an extra nesting level, move the inner folder up — or put the
archive anywhere you like and point `CORPUS_PATH` at it instead. Then:

```bash
cp .env.example .env
```

Leave every key blank. The only line that matters is `CORPUS_PATH`, which already
defaults to `data/Ashen_Era_Archive`. Now start the demo — **from the repository
root**, using the project's own interpreter:

```bash
.venv\Scripts\python.exe -m src.ui.server
```

Startup takes about six seconds (ingest 5.0s, graph 0.2s, cross-collection
attestation 1.2s). It prints the graph size, confirms
`model tiers: off - fully deterministic`, and serves on
**http://127.0.0.1:8000**. Four surfaces:

| URL | What it shows |
|---|---|
| `/` | The seven development 1B questions, an entity/relation catalogue, and the reindex control |
| `/ask?q=...` | One answer, with every hop's source document, row and authority tier |
| `/graph` | All 118 entities as one static SVG — no CDN, no JavaScript |
| `/reload` | Re-reads the corpus from disk and reports what changed (see below) |

#### If `python -m src.ui.server` fails

```
No module named 'src'
```

means one of two things, and both are worth checking before anything else:

- **You are not in the repository root.** `src/` sits beside `README.md`. Run
  `cd` into the directory containing this file first.
- **`python` is not this project's interpreter.** On a machine with several
  Python installations, a bare `python` can resolve to an unrelated virtual
  environment that has none of these dependencies. Writing
  `.venv\Scripts\python.exe` explicitly, as above, removes the ambiguity
  whether or not you ran `activate`.

#### Picking up a document added while the server is running

The graph is read from disk at startup and held, so a file added to the corpus
afterwards is invisible until something rebuilds. Click **Reindex corpus** on
the front page (or `POST /reload`). It re-reads the corpus and reports the
before/after entity, edge and evidence-unit counts, plus any infobox field name
the corpus uses that `config/relations.yaml` does not map — that last one is a
relation the graph is not reading, and the fix is a line of config, not code.

There is deliberately no file watcher: a rebuild is about six seconds, and an
explicit control that shows you what changed is easier to trust, and to
explain, than a background thread (ADR-036).

To answer one question without the browser:

```bash
python -m src.query.engine "Which accord was ultimately won by the faction of which Ederon Fellgard is a member?"
```

With no argument it runs the `1b_013` vertical slice. `python -m src.ui.server
--with-model` enables the LLM planner and model phrasing; it needs
`OPENROUTER_API_KEY` and is **off by default** on purpose (F-025), so an
unattended demo cannot spend quota or break on a cold network.

### Configure

`.env` is gitignored and must never be committed. Every key is optional;
`configuration-example/env.example` is an annotated copy explaining what each one
buys.

| Variable | Needed for | Free tier |
|---|---|---|
| `CORPUS_PATH` | everything — the only variable the demo path reads | — |
| `GOOGLE_API_KEY` | **re**-transcribing the 17 scanned PDFs, and the Checkpoint 1 baseline's generation. All 17 transcripts are committed under `ocr_cache/`, so OCR completes 17/17 from cache with this blank | [aistudio.google.com](https://aistudio.google.com/apikey) |
| `VOYAGE_API_KEY` | building the Checkpoint 1 vector index, which is **not** committed (`.cache/` is gitignored). See the caveat under *Measured results* | [voyageai.com](https://dashboard.voyageai.com) |
| `VOYAGE_TIER` | set to `paid` once a card is added — removes a throttle that turns a 5-minute index build into 2 hours | — |
| `OPENROUTER_API_KEY` | the tier-3 LLM planner and model phrasing — both off by default | [openrouter.ai](https://openrouter.ai) |

### Verify the setup

```bash
python -m src.ingest.integrity   # is your corpus the corpus we measured against?
python -m pytest                 # 443 tests
python -m src.ingest.pipeline    # 340 files -> 317 docs -> 30,553 evidence units
python -m src.graph.build        # 118 entities, 265 edges, 15 relations
```

All four run with no API key and no network.

The integrity check exists because our corpus once silently drifted from the
shipped bytes — a text editor rewrote 36 files and left an empty note behind that
ingested as a real document (`docs/failures.md`, F-016). It compares every file
against a committed manifest of 341 SHA-256 hashes and exits non-zero on any
difference.

---

## Architecture

**[`docs/architecture.md`](docs/architecture.md) is the architecture**, with the
diagram at [`docs/diagrams/architecture.svg`](docs/diagrams/architecture.svg) —
hand-authored, no toolchain, self-contained (ADR-022). Every number in that
diagram is re-derived from the live corpus by `tests/test_diagram.py`, so the
picture cannot go stale without the suite going red.

The short version. One pipeline, four stages:

1. **Corpus → evidence units** (`src/ingest/`) — discover, deduplicate, assign
   authority, load. 340 files become 317 canonical documents and 30,553
   `EvidenceUnit`s. Provenance is attached once, here, so nothing downstream
   reconstructs it and disagrees.
2. **Evidence units → graph** (`src/graph/`) — wiki infobox rows parsed one row at
   a time into 118 entities and 265 edges across 15 relations, held as a Python
   dict of lists.
3. **Question → answer** (`src/query/`) — three routing tiers, below.
4. **Answer → prose → screen** (`src/query/synthesis.py`, `src/ui/`) — the model
   rewords an already-verified chain; it never selects one.

### The three routing tiers

Each tier runs **only if the one before it declined**, and each declines rather
than guesses. A question no tier can route ends at a named `EvidenceStatus`,
never at an empty result and never at an invented answer.

| Tier | Module | Measured |
|---|---|---|
| 1 — templates | `route.py` | **7/7** on the dev 1B questions (ADR-017); matches no route shape on **36 of 49** independently written questions |
| 2 — cue fallback | `fallback.py` | **22 correct / 31 complete evidence** of 49, against templates-alone's 10 / 11 (ADR-019; counts updated by ADR-024, ADR-029, ADR-031, ADR-033) — at 40% precision against templates' 91% |
| 3 — LLM plan | `planner.py` | Emits a validated *plan*, never an answer. **Off by default**, and deliberately unmeasured on the frozen set |

**Never quote the 7/7 without the 36/49 beside it.** 7/7 measures fit to seven
development questions; 36/49 measures routing capability on questions written
independently and frozen before either router ran. Reporting the first alone
would misrepresent the system. Reproduce both with `python -m comparison.harness`.

**Deterministic-first. An LLM is a fallback, not a default — and every fallback is
counted.** Ingestion, deduplication, authority ranking, cell parsing, graph
construction, traversal, conflict extraction and scoring are all ordinary Python.
Models are confined to four isolated call sites, none of them in the traversal
that produces an answer: OCR (ingest-time, cached, zero calls at query time), the
Checkpoint 1 baseline arm, the tier-3 planner, and prose phrasing — the last two
off by default.

### Deliberately not used

- **No graph database.** 118 entities and 265 edges is a dict of lists.
- **No vector database.** 3,392 chunks is a NumPy matrix multiply in milliseconds.
- **No agent framework.** LangChain/LangGraph/CrewAI would be code we did not write.

The competition requires every team member to explain and modify any part of the
submission on demand. A dependency nobody on the team can defend to a judge is a
liability, not a feature.

---

## Repository layout

```
src/ingest/            discovery, dedup, OCR, authority, evidence units, integrity
src/clients/           Gemini rotation, Voyage embeddings, OpenRouter, retry/timeout
src/baseline/          Checkpoint 1: chunker, vector index, naive RAG
src/graph/             cell parsers, entity keys, schema + provenance, build, traversal
src/query/             the three routing tiers — resolution, routing, traversal,
                       evidence sufficiency, conflict detection, synthesis
src/ui/                the demo: stdlib http.server, HTML rendering, graph SVG
eval/                  answer key, deterministic scorer, harness, corpus probes,
                       completeness check, the frozen routing-robustness set
comparison/            the router comparison and guard ablations behind ADR-019
config/                authority.yaml, relations.yaml, corpus_manifest.sha256
configuration-example/ annotated copies of the above, readable without the tree
docs/                  ADRs, failure log, limitations, architecture, diagram, TODO
tests/                 443 tests
ai_usage/              exported AI collaboration transcripts (deliverable §4.1)
ocr_cache/             the 17 scan transcripts, committed so OCR needs no key
data/                  where the corpus goes; gitignored, ships empty
```

Two configuration files are deliberately *not* code, so a judge can disagree with
a line without touching Python: `config/authority.yaml` ranks source
trustworthiness, and `config/relations.yaml` declares which infobox field names
carry which relation — 67 field names across 15 relations, plus 43 names declared
non-relational so that a genuinely new one is *reported* rather than silently
ignored. `configuration-example/README.md` explains both at length.

---

## Commands

Everything here runs **with no API key**, from the committed caches, unless the
line says otherwise.

```bash
# Setup and verification
python -m src.ingest.integrity                   # verify corpus against the manifest
python -m src.ingest.pipeline                    # ingest, print summary
python -m src.ingest.ocr                         # transcribe scans (17/17 from cache)
python -m src.graph.build                        # build graph, print coverage
python -m pytest                                 # 443 tests

# Answering
python -m src.ui.server                          # the demo, http://127.0.0.1:8000
python -m src.ui.server --with-model             # + LLM planner and phrasing (needs a key)
python -m src.query.engine "<question>"          # one question end-to-end

# Reproducing the measurements
python -m eval.probes.corpus_shape               # every ADR-009..013 number
python -m comparison.harness                     # ADR-019's router comparison (36/49, 22/31)
python -m comparison.ablations                   # ADR-019's guard ablations
python -m eval.completeness                      # is the answer key narrower than the corpus?
python -m eval.verify_key                        # regenerate the answer-key review pack
python -m eval.run_eval --checkpoint baseline    # Checkpoint 1 — needs VOYAGE_API_KEY, see below
python -m src.clients.openrouter --verify        # are the model rotations still live?
```

---

## Measured results

> **All scores below are PROVISIONAL.** The answer key has cleared independent
> *completeness* checking — `python -m eval.completeness` reports **0 recall
> defects** across all 9 scoreable questions, corroborating `1b_006`'s fourteen
> answers by a route independent of the graph. *Precision* review (is each answer
> right?) is still outstanding, so the harness continues to warn and we are not
> quoting these numbers as final. Per-entry state, from `python -m
> eval.verify_key`: **`single_review` ×7, `draft` ×2**, and **0 of 9 confirmed by two
> reviewers** — every entry names the same single human reviewer, which is the
> failure mode `docs/failures.md` F-015 records.
>
> On 6 Sep an **AI re-derivation** worked all nine answers from the primary
> documents without reading the recorded answer first. It agreed with every
> one, and found two defects in the 1C conflict inventories (F-028). Recorded
> per entry under `verification.independent_recheck`. It does **not** advance
> any status: it was not a second human, and not blind — the same agent had
> seen the key earlier in the session. Corroboration, not confirmation.

### Checkpoint 1 — vector RAG baseline

```
1B  2/7      1C  2/2      all scored  4/9      not scored  11
complete evidence   0/7 on 1B      0/9 across all scored questions
```

> **Reproducing this needs a Voyage key and one index build.** The vector index
> lives under `.cache/`, which is gitignored, so a fresh clone does not have it —
> `python -m eval.run_eval --checkpoint baseline` reports the index as missing and
> stops. Rebuilding embeds 3,392 chunks with `VOYAGE_API_KEY` set (~5 minutes at
> `VOYAGE_TIER=paid`, ~2 hours without), and the build is not currently exposed as
> a runnable module — see `docs/TODO.md`. **Nothing else in this README depends on
> it.** The graph, the query engine and the whole demo are independent of the
> baseline arm.

### Checkpoint 2 — deterministic graph and query layer

```
entities 117  (95 page-backed, 22 edge-only, 0 isolated)
edges    261  across 15 relations, 3 direction overrides, 6 self-references skipped
```

On the seven dev 1B questions the query layer answers **7 of 7 correctly**
through four generic templates — entity resolution, routing, bounded traversal,
type filtering and same-tier conflict detection, none of the seven hard-coded
(ADR-017). It also touches every required document for 7 of 7, against the
baseline's 0 of 7.

**Read those numbers with the routing measurement beside them.** On 49
independently authored questions, frozen before either router ran, the templates
match no route shape on **36**. The shipped three-tier system answers **21
correctly with 31 complete evidence**, against templates-alone's **10 / 11** — at
40% precision where templates hold 91%. It declines all **6 of 6** questions
whose answer the corpus does not contain. 7/7 measures fit; 36/49 measures
routing capability, and the second is the honest headline. Reproduce with
`python -m comparison.harness`.

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
  threshold loose enough to be useful merges them. A near miss is *reported* at
  ≥0.90 similarity and resolved by nobody but the user (ADR-021, ADR-025).
- **The tier-3 planner is unmeasured on the frozen set.** Running it there would
  spend daily quota and produce a number that moves with the provider's free
  lineup. We report it as unmeasured rather than quote a figure we cannot
  reproduce.

---

## How this project works

Three of our assumptions were overturned by five-minute checks, and the record of
that is a deliverable rather than an embarrassment.

- **`docs/decisions.md`** — ADR-001..025. Where a measurement overturned an earlier
  decision, the original stays in the record with the correction beside it.
- **`docs/failures.md`** — F-001..027. Every approach tried and rejected, with the
  number that killed it. Nothing is removed after being fixed.
- **`docs/limitations.md`** — what the system does not do, and defects in the source
  material we cannot fix from our side.
- **`docs/architecture.md`** — the architecture in full, with the diagram.

Three entries worth reading if you want the flavour of the project: **F-015**,
where one careful reviewer reported "high confidence" on an answer with two valid
values and the corpus turned out to have fourteen; **F-019**, where a textbook
BFS returned a correct-looking two-hop path sourced from one document instead of
the two the question needed, decided by nothing more principled than filename
ordering; and **F-025**, where a schema-valid, name-checked, hop-bounded LLM plan
answered a question nobody had asked — confidently, and with citations.

### Working rules

- Atomic commits whose messages say *why* and cite the measurement that drove them.
- Measure before asserting. If a claim is going into a doc, the report or the
  video, run the check first and show the evidence.
- Never commit API keys, `.env`, or the corpus archive.
- A component is not done because it executes — it is done when it has tests, its
  failure cases are covered, its provenance is preserved, and the docs are updated.

---

## Status

Ingestion, OCR, authority ranking, the Checkpoint 1 baseline, the deterministic
graph, the query layer and the demo UI are built and measured.

Since the query layer landed, the work has been measuring what it cannot do and
correcting what it got wrong. Every one of these moved a *diagnosis* rather than a
score, which is the point:

- **ADR-019** — routing robustness measured on 49 frozen questions. The templates
  match no route shape on 35 of them. A cue-based second tier was adopted from
  that comparison, not from an assumption about what would help.
- **ADR-020** — OpenRouter as a second provider, and a third tier that emits a
  validated plan and never an answer. Off by default (F-025).
- **ADR-021** — question *shape* is a routing failure of its own; a near-miss
  spelling is reported, never resolved.
- **ADR-022** — the architecture diagram, hand-authored and pinned by tests that
  re-derive every number in it from the live corpus.
- **ADR-023 / F-027** — when a cell's own verb contradicts the field name, the
  cell wins. Three of 267 edges pointed backwards; fixing it changed no score.
- **ADR-024** — a relation's *question* vocabulary is declared in config
  separately from its corpus field names.
- **ADR-025 / F-026** — the typo reporter no longer calls a correctly spelled
  apostrophe-less possessive a misspelling. Suppress, don't widen.

The query engine remains **Checkpoint 2, not a finished reasoning system**. The
gating work is unchanged and is not code: answer-key precision review by a second
human. Every number here stays provisional until that lands.

See `docs/TODO.md` for the current sprint.
