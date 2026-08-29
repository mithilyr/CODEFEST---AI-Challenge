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

> **Correction, recorded rather than edited out.** The 3,364 figure was taken
> before the chunker settled. Re-measured from the built index on 29 Aug 2026 -
> 13,893,760 bytes / 1024 dimensions / 4 bytes per float - the corpus produces
> **3,392 chunks**. The argument above is unaffected; the number is not the one
> to quote.

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

---

## ADR-009 — The infobox parser keys on table position, not on headings or field names

**Problem**

Before writing `src/graph/`, we pressure-tested the assumption that the wiki
infobox is a regular `field | value` table. It is not regular in the two ways
that matter.

**What we measured**

`python -m eval.probes.corpus_shape`, over 95 wiki pages and 651 infobox cells:

| Finding | Measurement | Consequence |
|---|---|---|
| Pages with no `## Infobox` heading | **6 of 95** | A parser keyed on the heading loses them |
| Pages whose title declares a category | **26 of 95** | Node type cannot be read off the title |
| Distinct infobox field names | **107** | CLAUDE.md said 110; 107 is the measured count |

The six headless pages are not incidental. Three of them —
`the_cinder_wrought_aegis.md`, `gauntlet_of_sorrowfell.md`,
`the_thrice_bound_lantern.md` — are artifact pages, and
`the_cinder_wrought_aegis.md` supplies hop 2 of dev question `1b_003` via its
`Place of housing` row. A heading-keyed parser answers `1b_003` with nothing at
all, and the failure is silent: the page parses, it simply yields no edges.

**Decision**

The infobox is **the first pipe table in the file**, wherever it appears and
whether or not a heading precedes it. Node type is derived from the image
filename taxonomy (`plate_NN_<category>_<subject>`,
`atmo_<style>_<category>_<subject>`), which `src/ingest/metadata.py` already
parses, and never from the wiki title.

**Trade-offs**

"First table" is a positional rule rather than a semantic one, and would break
if a page ever led with a non-infobox table. No page does; the probe asserts it.
Only two field names, `Place of forging` and `Place of housing`, appear outside
a `## Infobox` section, and both are on a headless page's leading table.

*Status: accepted, validated by probe.*

---

## ADR-010 — Infobox cells are sentences, and the sentence set is closed

**Problem**

We had assumed a cell holds an entity, a literal, or a `;`-separated list of
those. The multi-valued case was already recorded
(`Victor of | The Winter Reckoning; The Leaden Accord`). The measurement found
four further shapes, one of which corrupts edges rather than merely missing them.

**What we measured**

All 651 cells fall into **12 templates**:

| Template | Count | Note |
|---|---|---|
| literal prose | 224 | attribute, not an edge |
| bare link | 181 | the easy case |
| literal year / number | 114 | attribute |
| verb + link | 38 | `Member of [[X]]`, `Commands [[X]] since 285 AS` |
| abstention | 24 | `Contested; consult the Annals and Codex` |
| prose containing an incidental link | 23 | **must not become an edge** |
| link + year pairs | 14 | `[[Greyfell Citadel]] in 337 AS; [[Palewell Abbey]] in 338 AS` |
| **two-argument clause** | **11** | **`Fought in [[Conflict]] for [[Faction]]`** |
| link list | 11 | `;` and, once, `,` |
| secret / association relation | 6 | `Secretly sells intelligence to [[X]]` |
| link + since-qualifier | 5 | `[[The Cinder-Wrought Aegis]], since 356 AS` |

Three of these are load-bearing:

1. **Two-argument clauses are ternary facts.** `Fought in [[The Purge of
   Blackport]] for [[House Morvain]]` is one fact with two objects. Emitting two
   edges from the subject asserts that the person was "belligerent in House
   Morvain", which is false. Word order also varies — both `Fought for X in Y`
   and `Fought in X for Y` occur — so the arguments must be resolved by type,
   not by position.
2. **`since <year>` qualifiers are load-bearing.** Dev question `1b_003` asks
   for the relic borne "since 356 AS". The qualifier belongs on the edge as an
   attribute; leaving it in the value produces the node
   `silent_psalter_since_341_as`.
3. **Incidental links are not edges.** `Appearance | Hardened visual identity of
   a garrisoned settlement in the [[Ash Wastes]]` links a region inside a prose
   attribute. Extracting every link indiscriminately manufactures relations.

**Decision**

A cell parser of twelve named template handlers, each with its own test. No LLM.

**Why**

Twelve regexes cover 100% of 651 cells. An LLM call here would be slower, cost
quota we cannot spare, be less reliable than the string operation it replaces,
and — decisively — could not be defended by a teammate to a judge as well as a
named handler with a test can.

**How we will validate it**

The probe prints the template histogram and the eleven two-argument cells by
name. If a template handler is deleted or a new corpus shape appears, the
histogram moves.

*Status: accepted, validated by probe.*

---

## ADR-011 — Entity resolution is exact-match; fuzzy matching may never pick a winner

**Problem**

A wrong entity produces a structurally perfect traversal to a confidently wrong
answer, with real citations attached. This is the worst failure mode the system
has, because the evidence panel makes it look right.

**What we measured**

Across 125 distinct entity names in the wiki:

- **20 given names** are shared by more than one entity — `ignatz` x5,
  `morwenna` x4, `halvard` x4, `isolde` x4, `ossric` x3.
- **19 surnames** are shared — `fellgard` x5, `ashgrove` x5, `wrenfield` x4,
  `hollowmere` x4.
- **6 pairs of genuinely distinct entities** sit at >= 0.80 string similarity:
  `caedmon_fellgard ~ ederon_fellgard` (0.839),
  `gloaming_reach ~ gloamreach` (0.833),
  `morwenna_morvain ~ morwenna_vane` (0.828),
  `caedmon_hollowmere ~ lucan_hollowmere` (0.824),
  `greyfell_citadel ~ ironfell_citadel` (0.812),
  `gloammarch ~ gloamreach` (0.800).

The name space appears to be adversarial by construction. `gloamreach`,
`gloammarch` and `The Gloaming Reach` are three different places — a settlement,
a settlement and a region.

**Options considered**

1. Fuzzy match on the closest name above a threshold.
2. Embedding-similarity match.
3. Exact match on the normalised name; on failure, escalate — never guess.

**Decision**

Option 3. Normalisation is: lowercase, collapse non-alphanumerics to `_`, drop a
leading `the_`. Nothing else. An unresolved mention escalates to disambiguation
against the candidate list and, failing that, abstains.

**Why**

Options 1 and 2 both resolve `caedmon_fellgard` to `ederon_fellgard` at any
threshold loose enough to be useful, and `ederon_fellgard` is the subject of
`1b_007`. A threshold tight enough to separate them is tight enough that exact
match would have succeeded anyway, so the fuzzy layer buys nothing and risks the
one failure we cannot detect from the output.

Dropping the leading article was verified rather than assumed: it merges exactly
**5** name pairs across the corpus (`iron_ring_cartel`, `ash_wastes`,
`gloaming_reach`, `pale_coast`, `weeping_marshes`), every one of which is
genuinely the same entity, and collides nothing else. `1b_009` needs this merge —
`the_purge_of_blackport.md` writes `[[Iron-Ring Cartel]]` while every other page
writes `[[The Iron-Ring Cartel]]`.

**Trade-offs**

The system will abstain on a misspelled question where a fuzzy matcher would
have guessed right. Accepted: an abstention is recoverable and honest, a
confidently wrong sourced answer is neither.

*Status: accepted, validated by probe.*

---

## ADR-012 — Claims are extracted structurally, and emphasis is stripped first

**Problem**

Conflict resolution needs competing claims. Getting the *extraction* wrong
breaks the layer in both directions, and the two failures are not symmetric.

**What we measured**

Three extraction strategies over the same 30,553 evidence units:

| Strategy | Contested keys | Failure mode |
|---|---|---|
| Proximity window (entity within 140 chars of a dated claim) | ~20 | **False positives.** Attributed Hollowvale's 286 AS to Vharencrag Fortress because both appear in one decree; produced four competing "founding years" for regions like `The Ash Wastes` that are merely named near other places' foundings. |
| Subject-anchored, no emphasis handling | **0** | **Silent total failure**, see below. |
| Subject-anchored + emphasis stripped + entity-resolved anaphora | **7** | — |

The silent failure is the important one. **Every competing claim in the corpus is
wrapped in Markdown emphasis and every authoritative one is not:**

```
codex     : Gloamreach's founded is 246 AS.
ephemera  : Gloamreach was founded in **286 AS**.
codex     : Gauntlet of Sorrowfell's forged is 391 AS.
ephemera  : Its forged year is **360 AS**.
```

An extractor that does not strip `**` sees zero competing claims, finds no
conflict anywhere in the archive, and reports full confidence. A conflict layer
that silently never fires is worse than no conflict layer, because nothing in
the output distinguishes the two.

The decoys are also **anaphoric** — "Its forged year is 360 AS" — and the
referent must be resolved. Two obvious resolutions are both wrong, and were
caught by measurement rather than by reasoning:

- *By filename subject*: `sermon_concerning_malchior_cindervale...` is about a
  character, but the sentence concerns the Gauntlet of Sorrowfell named in the
  sentence before. Files the claim against the wrong entity.
- *By nearest capitalised phrase*: the sentence preceding "Its forged year is
  354 AS" ends on "the Sundering". Also wrong.

Nearest preceding mention of a **known graph entity** resolves both correctly.

**Decision**

Extract a claim only where the entity is the grammatical subject, or is the
nearest preceding known entity for an anaphoric subject. Strip inline emphasis
before matching. Never use a proximity window.

**Trade-offs**

Structural extraction under-detects relative to a proximity window — it finds
claims it can attribute, and stays silent otherwise. That is the correct
direction to fail for a layer whose output is "these sources disagree".

*Status: accepted, validated by probe.*

---

## ADR-013 — Tier alone resolves every measured conflict, so the authority model stays as it is

**Problem**

Checkpoint 1 found the naive baseline scoring **2/2** on the 1C conflict
questions, because the codex announces its own authority in prose and the model
follows that signal. CLAUDE.md recorded the open question honestly: *the
authority layer may still matter where a source does not announce itself — that
is now a hypothesis to test, not a demonstrated result.*

This ADR tests it.

**What we measured**

Structure-anchored extraction (ADR-012) finds **7 contested attribute keys**
across the whole archive:

| Key | Authoritative | Competing | Tier split | Codex announces? |
|---|---|---|---|---|
| `gauntlet_of_sorrowfell.forged` | 391 AS | 360 AS | 1 vs 4 | yes |
| `gloamreach.founded` | 246 AS | 286 AS | 1 vs 4 | yes |
| `ashreach.founded` | 122 AS | 134 AS | 1 vs 4 | yes |
| `emberdeep.founded` | 65 AS | 34 AS | 1 vs 4 | yes |
| `mournwatch.founded` | 232 AS | 244 AS | 1 vs 4 | yes |
| `edge_of_gloamreach.forged` | 303 AS | 326 AS | 1 vs 4 | yes |
| `cinder_wrought_aegis.forged` | 342 AS | 354 AS | 1 vs 4 | yes |

- **Tier resolves 7 of 7.** Every conflict is codex (tier 1) against ephemera
  (tier 4). There is not one tie at the winning tier.
- **The codex announces itself in 7 of 7.** We could not find a single conflict
  where the authoritative source is silent.

**What this means, stated plainly**

The hypothesis is **not supported**. On this corpus there is no measured case
where the tier model is needed and prose-following would fail. Two apparent
counter-examples were checked and both dissolved: Vharencrag Fortress showed a
"conflict" that was Hollowvale's year captured by a proximity window, and
Blackford's was Edge of Gloamreach's forging site.

**Decision**

Keep the authority model exactly as ADR-005 specifies. Do not extend it, and do
not claim in the report or the video that it rescues answers the baseline gets
wrong — on the 1C dev questions it demonstrably does not.

**Why keep it at all**

Three reasons that survive the measurement, none of which is "it improves the
1C score":

1. **It is what makes the answer auditable.** The conflict panel shows a judge
   which sources disagreed and why one won. Prose-following produces the same
   answer with no account of the alternatives.
2. **It generalises past the announcement.** The tier ordering and the
   announcement agree on all 7 measured conflicts, so tier costs nothing and
   covers the case where the corpus stops announcing. The held-out set is 24
   unseen questions over the same archive; 5 of these 7 conflicts are untested
   by the dev set.
3. **It is a config file, not a subsystem.** `config/authority.yaml` is 100
   lines of declaration applied by dumb code. The cost of keeping it is close to
   zero, which is the only reason a layer with an unproven score benefit is
   allowed to stay.

If a checkpoint later shows the conflict layer changing no answer *and* the
conflict panel proving unpersuasive in the demo, delete it. That is the
condition, recorded in advance.

*Status: accepted; hypothesis tested and NOT supported; layer retained on
auditability grounds, with a stated deletion condition.*

---

## ADR-014 — Deterministic scoring, a response cache, and a provisional-until-verified answer key

**Problem**

The project's stated rule is *measure before asserting*. Its headline
measurement — the Checkpoint 1 baseline, quoted in CLAUDE.md as 2/7 on 1B joins
and 2/2 on 1C conflicts — existed only as prose in a commit message.
`eval/results/` was empty and no harness existed. Nobody could re-derive the
numbers, including us.

Three separate decisions were needed to fix that honestly.

### 1. Scoring is deterministic, not an LLM judge

**Options considered**

1. An LLM judge grading each answer against the key.
2. Substring matching against the acceptable answers.
3. Deterministic matching with an explicit negation guard.

**Decision:** option 3.

**Why not option 1.** Three reasons, in the order they decided it. *Quota*: a
judged sweep costs one extra call per question, doubling spend on the scarcest
resource in the project (~20 requests/day/model). *Reproducibility*: the entire
point is that a number can be re-derived; a judge that may grade the same answer
differently on two runs turns the baseline into an estimate. *Defensibility*: a
teammate can read forty lines of matching rules and defend every verdict in the
room. Nobody can defend a model's opinion under questioning.

**Why not option 2.** `answer_key.json` warns about this in its own preamble,
and it is not hypothetical. An answer reading

    there is no mention of who the victors were

contains the gold phrase and a substring scorer marks it **correct**. The guard
is therefore the whole difference between a scoring function and a scoring
function that works.

**How the guard works.** Negation is scoped to the *sentence* containing the
match, not to a character window. Two failures during implementation drove this:

- A 90-character window marked a genuinely correct answer wrong, because an
  unrelated denial two sentences later fell inside the window.
- Splitting on semicolons as well as sentence enders marked a genuine refusal
  correct, because `The forging date is not recorded; some accounts say 391 AS`
  put the gold token in its own clause. Semicolons do not split — the negation
  governs the whole statement.

Both are regression tests in `tests/test_eval.py`.

A third bug worth recording: the first `normalise()` ran the ASCII fold before
typographic normalisation, which **deleted** U+2019 rather than converting it.
`Sorrowfell's` folded to `sorrowfells` while `Sorrowfell's` folded to
`sorrowfell s`, and the two could never match — on a corpus that uses U+2019
throughout. Fixed by routing through the ingestion pipeline's existing
`normalise_punctuation()`, which is what CLAUDE.md already instructs for any new
text path.

### 2. Gemini responses are cached

**Problem**

`gemini.py` documented a response cache in its module docstring — *"a cached
answer costs no quota, and the demo must never be recorded against a cold
cache"* — and did not implement one. Every evaluation sweep cost ~20 requests,
so debugging the harness would have consumed a day's quota per attempt.

**Decision**

Content-addressed cache at `.cache/responses/`, sharded like the embeddings
cache, keyed on **the prompt alone and not the model**.

**Why not key by model.** Rotation means an identical prompt may be served by
different models on different days. Keying by model forces a fresh request every
time the rotation head changes — precisely when quota is scarcest. The stored
record carries the model that produced the text, so provenance survives even
though the key does not.

**Trade-off.** A cached answer may come from a model no longer at the head of
the rotation. Accepted and recorded, because the alternative is an evaluation
that cannot be re-run. Image prompts are never cached here; OCR has its own
committed cache.

### 3. The answer key is provisional until two humans verify it

**Problem**

All nine traced entries carry `verified_by: null`. The key was produced by an AI
assistant tracing the corpus — the same kind of process that produced three
assumptions this project has already had to overturn. Scoring against it and
reporting the result as fact would be exactly the failure the harness exists to
prevent, dressed up as rigour.

**Decision**

Results are marked provisional per question, not per run. Every row in the
Markdown report says whether its ground truth has been checked, so a number
copied into a slide still carries its own health warning. `verified_by` must be
a list of **two** names; a single reviewer does not clear it.

`python -m eval.verify_key` generates `eval/verification/answer_key_review.md`:
for each traced question it pulls the actual passage from the corpus at every
cited location, so a reviewer reads what the document says instead of searching
317 files.

**The pack deliberately does not use `eval/probes/corpus_shape.py`.** The probe
is our parser and may be wrong in the same way the key is wrong; checking one
against the other would confirm nothing. Excerpts come from the ingestion
pipeline — the same text the system itself sees — so a reviewer also sees it if
ingestion is dropping something.

**The one rule, recorded so it cannot be quietly relaxed:** never change an
answer to make the system score better. If the system disagrees with a confirmed
entry, the system is wrong. If review shows the key was wrong, fix the key and
record it here.

**Trade-offs**

Verification is human time this team does not have much of — nine questions,
two reviewers. Accepted, because every architectural decision from Checkpoint 2
onward is scored against this key, and an unverified key silently invalidates
all of them at once.

**How we will validate it**

`tests/test_eval.py` asserts the negation guard rejects the exact over-crediting
string, that evidence recall is `None` rather than `0.0` for untraced questions,
that unscored questions appear in the report rather than shrinking the
denominator, and that a repeat prompt is served from cache with
`total_calls == 0`. One test asserts that every key entry is still unverified —
it fails deliberately when that changes, forcing whoever verifies the key to
come back and update this ADR.

*Status: accepted; harness validated by tests, baseline numbers provisional
pending human verification of the key.*
