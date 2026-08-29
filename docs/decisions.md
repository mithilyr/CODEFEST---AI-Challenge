# Architecture Decision Record

Decisions are recorded as they are made, with the evidence that drove them.
Where a measurement overturned an earlier assumption, the original assumption is
kept in the record rather than quietly edited out — being wrong and finding out
cheaply is the process working.

---

## ADR-001 — Graph-first retrieval with vector fallback

**Problem**

Sub-track 1B asks for answers that no single document contains. Dev question
`1b_007` — *"Which accord was ultimately won by the faction of which Ederon
Fellgard is a member?"* — needs two facts from two documents:

- `wiki/ederon_fellgard.md` gives `Membership → [[The Iron-Ring Cartel]]`, and
  never mentions any accord.
- The answer requires the conflict whose `Victor` is The Iron-Ring Cartel; that
  page never mentions Ederon Fellgard.

The documents share no linking vocabulary, and hop 2 is a *reverse* lookup
(given a faction, find the conflict it won). Similarity search has no mechanism
for either.

**Options considered**

1. Pure vector RAG with a larger `k` — retrieve more and hope both documents land
   in the window.
2. Pure knowledge graph — parse relations, traverse deterministically.
3. Graph-first, vector fallback — traverse when the question is relational, fall
   back to retrieval when it is not.

**Decision**

Option 3.

**Why**

Option 1 fails structurally, not by margin: raising `k` cannot manufacture a join,
and it dilutes precision. Option 2 fails on any question that is not relational,
and we cannot assume the unpublished judging set is entirely relational — the dev
set already contains questions that are not.

Option 3 also produces the evidence path as a by-product of answering, which is
what the UI needs to show and what makes the answer auditable.

**Trade-offs**

Two retrieval systems to build and maintain instead of one, and a routing
decision that can itself be wrong. Mitigated by making the fallback trigger a set
of explicit predicates (ADR-005) rather than a judgement call.

**How we will validate it**

Three measured checkpoints on identical questions: vector-only, graph-only, then
graph+fallback. If the fallback does not measurably recover questions the graph
misses, it gets deleted rather than kept for symmetry.

*Status: accepted, unvalidated — checkpoints pending.*

---

## ADR-002 — Deterministic-first, with the LLM as a counted fallback

**Problem**

Where should the system use an LLM, and where should it use ordinary code?

**Options considered**

1. LLM-driven throughout — let a model plan retrieval and traverse.
2. Deterministic throughout — no LLM at all.
3. Deterministic first at every stage, escalating to an LLM only on explicit
   failure conditions, with every escalation counted.

**Decision**

Option 3.

**Why**

Three independent constraints point the same way.

- *Correctness*: the corpus filenames and wiki markup are perfectly regular
  (verified: 100% of 340 files match their collection's pattern). A regex extracts
  document type and subject entity exactly. Asking a model for information a
  regex already yields with certainty is slower, costs money, and is less
  reliable.
- *Defensibility*: competition rules require every team member to explain and
  modify any part of the system on demand. Nobody on this team has an ML
  background. Deterministic code we wrote is code we can defend.
- *Cost*: free-tier limits are roughly 50 requests/day without a card. A design
  spending 20 LLM calls per question cannot even be evaluated across a question
  set, let alone demonstrated live.

Counting the escalations turns an assertion into a number: *"the LLM planner
handled N% of held-out questions"* is a claim we can show.

**Trade-offs**

More code than delegating to a model, and rules that need maintaining as question
shapes vary. Accepted because the alternative is a system we cannot explain,
cannot afford to run, and cannot debug.

**How we will validate it**

The harness reports per-stage fallback rates. If the deterministic path handles
only a small fraction of held-out questions, the rules were the wrong bet and the
balance shifts toward the LLM path.

*Status: accepted, unvalidated.*

---

## ADR-003 — Deduplication is collection-dependent, not global

**Problem**

The corpus ships the same filename stem in several formats. Conflict resolution
ranks competing claims by source authority, so if one document is counted as
several, a single unreliable source can appear to be several independent sources
corroborating each other. Document identity has to be settled before anything
counts evidence.

**What we originally assumed**

That same stem means same document, and the corpus therefore held 134 unique
ephemera behind 145 files. This was written into the plan.

**What we measured**

Text similarity between same-stem files, per collection:

| Collection | Pair | Similarity | Verdict |
|---|---|---|---|
| `chronicles/` | `.docx` vs `.pdf` | **1.000** (identical length) | same work |
| `codex/` | `.docx` vs `.pdf` | **0.989–0.991** | same work |
| `ephemera/` | `.docx` vs `.pdf` | **0.019** | different documents |
| `ephemera/` | `.txt` vs `.pdf` | **0.048** | different documents |
| `images/` vs `codex/images/` | plates | byte-identical SHA-256 | same asset |

The ephemera pairs are different in-world documents that merely concern the same
subject. Both of these exist, with unrelated content:

```
auction_catalogue_concerning_morwenna_vosgard.pdf
    "Catalogue of Perilous Holdings: A Sale of Sapper's Work and Siege-Breaking Vermin"
auction_catalogue_concerning_morwenna_vosgard.txt
    "Catalogue of the Unseen Sapper: Morwenna Vosgard"
```

**Options considered**

1. Global stem-based dedup — the original assumption.
2. No dedup at all — treat every file as a document.
3. Collection-dependent policy driven by the measurement.

**Decision**

Option 3. `chronicles/` and `codex/` deduplicate by stem; image assets
deduplicate by content hash; `ephemera/` never deduplicates.

**Why**

The original assumption was wrong in the dangerous direction: it deletes real
evidence. Applying it would have discarded 11 independent ephemeral sources and
hidden competing claims from the conflict resolver — the exact failure the
conflict layer exists to prevent, introduced by the layer beneath it. Option 2
avoids that but reintroduces phantom corroboration for the novels and codexes,
each of which would otherwise count twice.

Result: 340 files → **317 canonical documents**, 22 duplicates collapsed
(4 novels + 3 codexes + 15 plates).

**Trade-offs**

The policy is corpus-specific and would need re-measuring on a different archive.
Accepted, and made explicit: the rule lives in one named constant
(`DEDUPLICATED_COLLECTIONS`) with the measurement recorded beside it.

**How we will validate it**

`tests/test_ingest.py` asserts each invariant — 145 ephemera survive, novels and
codexes collapse, plates collapse across directories, and scans keep a display
variant. These are regression tests: if someone later "simplifies" dedup to a
global rule, the suite fails.

*Status: accepted, validated by measurement and tests.*

---

## ADR-004 — Canonical text source is separate from display variants

**Problem**

Deduplication picks one variant to supply retrieval text. But the UI must show a
judge the *original* document — a scanned page or a figure plate — and that
original is often not the variant carrying the text.

**Decision**

Every canonical document keeps `text_source` (one variant, for retrieval) and
`display_variants` (all renderable originals). Evidence counting and conflict
detection use `canonical_doc_id`; the UI renders `display_asset`.

**Why**

They answer different questions. "How many independent sources claim X?" must not
double-count. "Show me where that came from" must show the real page. Collapsing
both concerns into one field forces a choice between correct counting and
credible demonstration.

**Trade-offs**

Slightly more state per document. Negligible against the cost of either failure
mode.

**How we will validate it**

`test_scans_keep_a_display_variant` asserts all 17 OCR-pending scans remain
renderable despite supplying no text.

*Status: accepted, validated by tests.*

---

## ADR-005 — Source authority lives in configuration, not code

**Problem**

The archive contradicts itself, and the least reliable sources are often the most
confident. The corpus README warns: *"in-world authors are not always reliable."*
Verified example — the forging year of the Gauntlet of Sorrowfell:

| Source | Claim |
|---|---|
| `ephemera/sermon_concerning_malchior_cindervale...txt` | 360 AS |
| `wiki/gauntlet_of_sorrowfell.md` | "contested — refer to the Annals and Codex" |
| `codex_vaeloria_ii`, para 69 | **391 AS**, "Popular accounts wrongly claim otherwise" |

The sermon chunk is short, names the entity, and contains a year, so a similarity
search ranks it first. A naive system answers 360 AS.

This is not an isolated trap. Codex Vaeloria II issues the same style of
authoritative correction for at least three artifacts (Sorrowfell 391 AS, Edge of
Gloamreach 303 AS, Cinder-Wrought Aegis 342 AS).

**Options considered**

1. Ask an LLM which source looks more trustworthy.
2. Hard-code a ranking in Python.
3. Declare the ranking in `config/authority.yaml`, applied by dumb code.

**Decision**

Option 3. Four tiers by collection (codex 1, wiki 2, chronicles 3, ephemera 4),
with ephemera sub-ranked across all 12 in-world document types — administrative
records (ledger, decree, muster roll) above performative ones (ballad, sermon).

**Why**

This ranking is the single most consequential judgement the system makes, so it
must be inspectable and arguable, not buried in a function. A judge can be shown
the file and can disagree with it specifically. Option 1 reintroduces exactly the
unreliability we are trying to defeat, and costs a call per claim; option 2 works
but hides the reasoning.

**Trade-offs**

A config file that must stay in sync with the corpus. Guarded by a test asserting
every doctype present in the corpus has a declared subtier.

**How we will validate it**

`test_authority_ordering_defeats_the_sorrowfell_decoy` asserts
codex < wiki < sermon. The end-to-end regression is that the assembled system
answers 391 AS.

*Status: accepted; ordering validated, end-to-end pending.*

---

## ADR-006 — Streamlit for the demonstration UI

**Problem**

The live demo is directly scored, and the UI must make the evidence path visible.
But total team capacity is roughly 100–144 person-hours, and the retrieval engine
plus evaluation harness plus documentation consume most of it.

**Options considered**

1. React frontend against a FastAPI backend.
2. Streamlit.
3. CLI plus a generated HTML report.

**Decision**

Option 2, behind a strict JSON response contract so option 1 remains reachable if
time allows.

**Why**

A React build meeting the required spec — evidence path, expandable evidence
cards, source viewer, conflict panel — is 30–40 hours against roughly 15–20
available. Beyond speed: `st.graphviz_chart` renders the per-question evidence
path natively; `streamlit run` is one command with no Node toolchain, which
directly serves the rubric's *"can a judge set up and run your project from the
README alone?"*; and one Python codebase rather than two matters when every team
member must be able to modify any part on demand.

**Trade-offs**

Streamlit cannot make graphviz nodes clickable. Mitigated by numbering nodes in
the path and matching them to numbered expanders below — documented as a known
limitation rather than hidden. Less visual polish than a bespoke frontend.

**How we will validate it**

The clean-clone test: a team member who did not write the setup follows the
README only and reaches a working query.

*Status: accepted, unvalidated.*

---

## ADR-007 — Rotate across free-tier models instead of retrying one

**Problem**

Our first OCR run transcribed 4 of 17 scans and failed the other 13. The retry
layer, which we had written specifically to survive rate limits, made things
worse rather than better.

**What we measured**

The provider error names the quota exactly:

```
Quota exceeded for metric:
  generativelanguage.googleapis.com/generate_content_free_tier_requests
  limit: 20, model: gemini-3.7-flash
quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier
```

**~20 requests per day, per model, per project** — a daily cap, not the
per-minute limit we had assumed. Two consequences:

1. Exponential backoff cannot recover from it. We spent five attempts on each of
   thirteen documents sleeping through a limit that resets tomorrow.
2. Twenty requests is less than one evaluation run. Twenty dev questions plus
   twenty-four held-out questions is 44 synthesis calls, before any development
   iteration.

**Options considered**

1. Wait for the daily reset and run in stages across several days.
2. Pay for quota.
3. Rotate across models, since the quota is scoped per model.

**Decision**

Option 3, plus fail-fast detection so option 1 remains available as a fallback.

**Why**

The quota is per *model*, so each model in the rotation carries its own separate
allowance — six free models give roughly six times the daily capacity, using
nothing but each model's documented free tier. Option 1 alone would have made
every evaluation run a multi-day affair with twelve days total. Option 2 is
unnecessary and the challenge states the problem is solvable with free
resources.

Rotation took the OCR cache from 4/17 to 12/17 in a single run.

**Trade-offs**

Transcriptions may come from different models, so a multi-page document can span
two. `OCRResult.model` records every model that contributed rather than
pretending one did. Quality varies slightly across the rotation, which is
acceptable for transcription of clean single-column scans and is why the
strongest models are tried first.

**How we will validate it**

`tests/test_quota.py` holds a verbatim provider error and asserts that a daily
quota fails immediately without sleeping. Per-model call counts are reported at
the end of every run, so quota spend is visible rather than inferred.

*Status: accepted, validated — 4/17 to 12/17 on the first rotating run.*

---

## ADR-008 — Size embedding batches by tokens, not by item count

**Problem**

The first index build was rejected outright by Voyage.

**What we measured**

A Voyage account with no payment method on file is limited to **3 requests and
10,000 tokens per minute**. Our batches were 128 items of roughly 36,000 tokens
— over triple the per-minute allowance in a single request.

Corpus scale: 3,364 chunks, ~962k tokens. That is 0.5% of the 200M free token
allowance, so tokens were never the constraint. Throughput was.

**Options considered**

1. Reduce the batch size to a fixed smaller number.
2. Require every team member to add a payment card.
3. Size batches by estimated token count and pace them with a rolling-window
   limiter.

**Decision**

Option 3, with option 2 documented as the fast path.

**Why**

A fixed smaller batch size is a guess that breaks as soon as chunk lengths
change — our chunks range from a short table row to 2,856 characters, so any
constant is either wasteful or over the limit. Token-aware batching adapts.

Requiring a card would work (and the challenge appendix recommends it: the card
is identity verification, the 200M free tokens still apply) but the system
should not *depend* on it, because any team member on a fresh account must be
able to run the build.

Throttled, the full index takes about two hours. With a card, a few minutes.
`VOYAGE_TIER=paid` removes the throttle.

**Trade-offs**

Two hours is slow, but it is a one-time cost: embeddings are cached by content
hash, so only edited documents are ever re-embedded, and evaluation runs cost
nothing.

**How we will validate it**

Tests assert that every batch stays inside one minute's token budget, that no
chunk is lost or duplicated during batching, and that the rolling window rolls
forward so throttling is not permanent. The limiter takes an injectable clock —
without one, a fake sleep that does not advance time spins forever, which is
what happened on the first attempt.

*Status: accepted, validated by tests; full index build in progress.*
