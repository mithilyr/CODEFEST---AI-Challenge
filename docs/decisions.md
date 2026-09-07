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

*Status: SUPERSEDED IN PART. The graph-first half shipped. The vector fallback
did not.*

**What actually happened, recorded here rather than by editing the decision
above.** The checkpoints this ADR asked for were run. Checkpoint 1 measured the
vector arm at **1B 2/7 correct, 0/9 complete evidence** — not one question
retrieved every document its answer needs. The graph then answered 7/7 of the
dev 1B questions with complete evidence.

The fallback question was reopened on measurement, not preference. ADR-019
measured the four templates against 49 independently authored questions frozen
before either router ran, found **36 of 49 matched no route shape**, and
compared two candidate fallbacks. A **deterministic cue router** was adopted;
the vector arm was not. This ADR's own deletion clause — "if the fallback does
not measurably recover questions the graph misses, it gets deleted rather than
kept for symmetry" — is what settled it.

So the shipped answer path is **templates → deterministic cue fallback → an
opt-in LLM planner** (ADR-020). `src/baseline/` remains as the Checkpoint 1
comparison arm and is imported by `eval/run_eval.py` alone; nothing in
`src/query/` or `src/ui/` references it.

This status line said "accepted, unvalidated — checkpoints pending" until
6 Sep, long after the checkpoints had run, and `README.md` described the system
as "graph-first with vector fallback" for as long. Both were wrong and both are
corrected. The decision is left standing as written, per the project's rule that
an assumption overturned by measurement stays visible in the record.

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
| *(corrected 2026-08-29 — see amendment below)* | **109** | 107 was itself a heading-keyed count |

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

### Amendment, 2026-08-29 — the field-name count was itself heading-keyed

`python -m eval.probes.corpus_shape` reports **109** distinct field names, not
the 107 in the table above. The 107 is the count of field names appearing
**inside a `## Infobox` section**. The two it omits are exactly the two this
ADR's own trade-offs paragraph names:

```
distinct infobox field names        : 109
    of which inside a '## Infobox'  : 107
    visible only on headless pages  : ['Place of forging', 'Place of housing']
```

The decision is unaffected and the argument is strengthened: the headline number
of the ADR that exists to stop heading-keyed parsing was itself produced by
heading-keyed parsing, and it dropped `Place of housing` — the row on
`the_cinder_wrought_aegis.md` that supplies hop 2 of `1b_003`. The measurement
lost precisely the field the ADR was written to protect.

The original 107 is left in the table rather than overwritten, per the working
rule on keeping overturned assumptions visible. The probe now prints both
numbers so the distinction cannot silently drift again.

### Amendment, 2026-08-29 — rows are a sequence, not a mapping

ADR-009 settles *where* the infobox is. It does not say how rows are keyed, and
the 651-cell census counted colliding rows without noticing they collide.

`python -m eval.probes.corpus_shape` (PT-10) measures:

| Finding | Measurement |
|---|---|
| Pages with a repeated field name | **5 of 95** |
| Distinct (page, field) collisions | **6** |
| Cells a dict-keyed parser drops | **7** |

```
wiki/the_ashen_vanguard.md | Belligerent x3
    The War of Drowned Light
    The Accord of Mournthrone
    The Leaden Accord
```

Also `Rival` ×2 (`ignatz_ashgrove_the_oathless.md`), `Wielded relic` ×2
(`sabelle_mournvale_the_twice_crowned.md`), `Waged at` ×2 and `Devastated` ×2
(`the_accord_of_mournthrone.md`), `Serves at Emberdeep` ×2 (`emberdeep.md`).

**Decision.** The parser must return infobox rows as an **ordered sequence of
`(field, value)` pairs**. `fields[name] = value` is forbidden: it keeps the last
row, drops the rest, raises nothing, and the page still parses.

**Why this is load-bearing, not tidiness.** `the_ashen_vanguard.md` has **no
`Victor of` row at all**. Its only victor claim is an `Outcome` row reading
`Victor of The Accord of Mournthrone`. The probe measures the channels:

```
field names that DESIGNATE a victor:
     6  Victor
     2  Victor of
     1  Outcome
victor designations NOT on a 'Victor*' field : 1
    wiki/the_ashen_vanguard.md | Outcome | <-- page has NO Victor* row at all
```

An extractor keyed on `Victor of` reads the Vanguard as **silent** on victories.
Under F-014 and ADR-015, silence is not denial — so this would not merely lose an
edge, it would misclassify the page's stance. The ADR-013 CORRECTION classified
"Accord of Mournthrone" as *"Agree both ways"*, a verdict that holds only if that
`Outcome` row was read.

**What we did not conclude.** The spec that prompted this check also claimed an
`Outcome` row can depend semantically on the `Belligerent` row above it. All
seven `Outcome` rows in the corpus were checked: the Vanguard's names its own
referent, and the other six are conflict-page descriptions of how a war ended,
not victor designations. Row *order* is not load-bearing on current evidence;
row *multiplicity* is. We are building for the second only.

Two victor *mentions* were excluded as prose rather than designations —
`Concealed truth` and `Secret truth`, both reading "The victors poisoned the
wells of their own allies". The probe prints its exclusions.

**Validation.** PT-10 in `eval/probes/corpus_shape.py`. The victor-channel check
existed only as a table in this file before now; it is runnable code.

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

**Amendment, 30 Aug 2026 — the field was never called `verified_by`.**

The paragraphs above are kept as written because the decision they record still
stands. The *implementation* diverged: `eval/answer_key.json` has no
`verified_by` key at all (`grep -c verified_by` returns 0). Each question
instead carries a `verification` object whose `status` is one of `draft`,
`single_review` or `unresolved`, with a `reviewers` list beside it. Measured
today:

    single_review  6      all seven reviewed entries name the same one reviewer
    draft          2      no review at all
    unresolved     1

So the gate is unchanged — nothing has cleared two reviewers — but the state is
worse than "null" suggested: two entries have never been looked at. CLAUDE.md,
README.md and docs/TODO.md all repeated the wrong field name until today and
have been corrected. The single-reviewer half of this is F-015.

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

---

## ADR-013 CORRECTION — a same-tier relational conflict exists, and tier cannot resolve it

**What ADR-013 concluded**

That tier resolves **7 of 7** conflicts in the archive, that the codex announces
itself in all 7, and that the authority layer therefore earns its place on
auditability rather than on score.

**What was wrong with it**

The measurement behind it examined only **dated attribute claims** — `founded`
and `forged` years extracted by `eval/probes/corpus_shape.py`. It never looked
at **relational** claims, and it drew a conclusion about "conflicts in the
archive" from a sample that structurally excluded them.

Human review of `1b_009` on 2026-08-29 found the counter-example, and it was
confirmed by reading both pages verbatim:

| Source | Tier | Claim |
|---|---|---|
| `wiki/the_purge_of_blackport.md` | 2 | `Victor \| [[Iron-Ring Cartel]]`, and in prose: *"The Iron-Ring Cartel emerged as the victor"* |
| `wiki/the_iron_ring_cartel.md` | 2 | `Victor of \| [[The Winter Reckoning]]; [[The Leaden Accord]]` — the Purge is **excluded**, and the prose says so twice: *"This record establishes participation without assigning the Cartel the status of victor."* |

This is an **affirmative denial**, not an omission. The Cartel page keeps a
victor list, puts two conflicts on it, leaves this one off, and then comments on
the exclusion. Both sources are `wiki/` at tier 2 with identical subtier.
`config/authority.yaml` ranks by collection, so it cannot separate them, by
construction.

**What we re-measured**

All six victor edges declared on conflict pages, checked against what the
faction's own page says:

| Outcome | Count | Detail |
|---|---|---|
| Agree both ways | 4 | Leaden Accord, Winter Reckoning, War of Endless Vigil, Accord of Mournthrone |
| **Contradicted** | **1** | **Purge of Blackport / Iron-Ring Cartel** |
| Faction page silent | 1 | War of Drowned Light / The Silent Choir |

The silent case matters as much as the contradicted one. The Silent Choir's page
lists the war under `Belligerencies` and carries **no victor row at all** — it
makes no victory claims about anything, and states outright that outcomes are
not detailed. Absence of a claim from a page that never makes such claims is
silence, not denial. `1b_005` and `1b_022` therefore remain clean two-hop
questions, and must not be mislabelled as conflicts.

An earlier version of this measurement did mislabel them, by testing only "is
this conflict in the faction's belligerent list and absent from its victor
list". That test cannot tell a page that declines to claim victories from a page
that claims victories and excludes one. The corrected test asks whether the
faction page makes victor claims **at all**.

**What changes**

1. ADR-013's *conclusion about dated attributes stands* — those 7 are still
   tier-decided and codex-announced. Its *scope claim* does not: it was never a
   statement about the whole archive.
2. The conflict resolver needs a **same-tier** branch. Tier is not a total order
   over claims, and on the one relational conflict we have it provides no
   signal at all.
3. `expected_conflict_status: must_surface` enters the answer key. Where the
   corpus contradicts itself and authority cannot adjudicate, the correct
   system behaviour is to **report the disagreement**, not to pick a side.

**Trade-offs**

We now have one measured same-tier conflict, which is a sample of one. We are
not building a general conflict-arbitration framework on it. The change is
narrow: represent the conflict, surface it, and decline to resolve what the
corpus does not resolve.

*Status: ADR-013 amended, not withdrawn. Scope corrected; the dated-attribute
finding stands.*

---

## ADR-015 — The answer key represents the corpus, not the scorer's convenience

**Problem**

The v1 answer key gave every question one `answer`, one `expected_path`, and a
flat `acceptable` list. Human review on 2026-08-29 showed three questions that
do not fit that shape, and the misfit was not cosmetic — each one would have
produced a wrong score.

| Question | Why v1 could not represent it |
|---|---|
| `1b_006` | Fourteen valid answers, recorded in two disjoint places. A single `answer` field invites narrowing the set, and a narrowed set marks correct answers wrong. |
| `1b_007` | Two genuine victories in one multi-valued cell; only one is an *accord*. The distractor is not an error to be filtered out of the key — it is a correct fact that the question's type word excludes. |
| `1b_009` | A wiki-vs-wiki contradiction at the same tier. v1 had a `conflict` block, but it assumed an `authoritative` winner. There isn't one. |

**Decision**

Schema v2. Every question carries `accepted_answers` (each with its own
aliases), `answer_cardinality`, `required_evidence`, `acceptable_paths`,
`conflicts`, `expected_conflict_status`, `confidence` and `verification`.

Two distinctions the schema now enforces:

- **An alias is not an alternative answer.** `Leaden Accord` is a spelling of
  `The Leaden Accord`; `Isolde Mournvale` is a different answer from
  `Ravena Stormwell`. Collapsing them makes it impossible to tell "we accept
  either spelling" from "we accept either person", and the second is a claim
  about the corpus.
- **Silence is not denial.** `Claim.stance` is `asserts | denies | silent`.
  Without it, `1b_005` and `1b_009` look like the same kind of question and are
  not.

**Scoring consequence**

Conflict handling is scored as a **separate dimension** from correctness:
`surfaced | asserted_as_fact | not_mentioned | n/a`. Saying the right thing and
representing a disputed claim honestly are different achievements, and a system
can do the first while failing the second.

It is gated behind correctness — a wrong answer scores `n/a (answer wrong)`.
Judging how a wrong answer handled a nuance compounds one failure into two and
measures nothing.

The trigger is explicit rather than inferred. `1b_009`'s conflict carries
`assertion_markers: [victor, victors, victorious, won, victory, prevailed]`,
because the contested proposition is *"the Cartel won"*, not *"the Cartel
exists"*. An entity-mention test penalises the careful answer
"Halvard Crowhurst is a recorded member of the Iron-Ring Cartel", which asserts
nothing contested. Keeping the markers in the key makes the rule auditable and
arguable, which is the same reason `config/authority.yaml` is a file.

**What we did not do**

We did not narrow `1b_006` to the two answers the review returned. Corpus
enumeration finds fourteen — six on the faction page's `Members` row, eight more
on individual character pages, zero overlap — and the review missed the faction
row entirely. The entry is marked `unresolved` with the discrepancy recorded,
rather than silently corrected in either direction.

This is the clearest argument in the project for ADR-014's two-reviewer rule.
One careful reviewer, working alone and reporting high confidence, found 2 of
14. `verification.is_confirmed` therefore requires two reviewers **and** no open
discrepancy; a single consolidated review is `single_review`, not `confirmed`.

**Trade-offs**

The key is longer and takes more care to edit. Accepted: it is the ground truth
every architectural decision from Checkpoint 2 onward is scored against, and a
ground truth that cannot express the corpus is worse than a long one.

**How we will validate it**

`tests/test_eval.py` asserts that `1b_006` keeps all fourteen answers and
accepts any of them, that `1b_009`'s conflict is recorded as same-tier and
unresolved with both an `asserts` and a `denies` claim, that no entry is
confirmed while the review remains a single pass, and that asserting a disputed
claim as fact is flagged while merely naming the entity is not.

*Status: accepted, validated by tests. All nine entries remain unconfirmed —
six `single_review`, one `unresolved`, two `draft` (1C was not reviewed).*

## ADR-016 — The graph is infobox rows with provenance, in plain Python

**Problem**

Checkpoint 1 measured the thing the graph has to beat: the vector baseline
answered 2 of 7 1B questions and assembled **complete evidence for none of
them**. Three of seven reached neither required document. The question this ADR
answers is whether explicit structure recovers the evidence similarity search
could not assemble.

**What we built**

Five modules, no dependencies beyond PyYAML and the standard library:

| Module | Job |
|---|---|
| `cells.py` | The twelve ADR-010 templates as named handlers |
| `entities.py` | Canonical keys; exact match only (ADR-011) |
| `schema.py` | `Node`, `Edge`, `Graph` - dicts and lists |
| `build.py` | Row-by-row construction from `EvidenceUnit`s |
| `traverse.py` | Bounded bidirectional BFS returning paths with evidence |

The builder consumes ingested evidence rather than re-reading the corpus, so the
document id, authority tier and locator attached once during ingestion travel
onto every edge instead of being reconstructed.

**Measured result**

```
entities 117  (95 page-backed, 22 edge-only, 0 isolated)
edges    267  across 15 relations, 0 unmapped field names

complete required evidence, 7 dev 1B questions:
    graph   7/7
    vector  0/7   (Checkpoint 1)
```

**This is evidence coverage, not answer correctness.** There is no query layer
yet - no routing, no answer selection, no synthesis. What is measured is that a
bounded traversal from the question's entity reaches the answer entity *and*
touches every document the answer key requires. `1b_007` returns five candidate
paths and needs a type filter to choose the accord; `1b_009` returns nine and
needs conflict handling. "A path exists" and "the system answers correctly" are
different claims and this ADR only supports the first.

**Decisions**

1. **Provenance is not optional.** Every edge carries `document`, `field_name`,
   `row`, `raw`, `template`, `tier`, `assertion` and `extraction`. `Edge.why()`
   renders one line a human can check against the page. An edge that cannot
   explain itself is a citation we cannot defend.
2. **`row` is part of the identity.** Five pages repeat a field name (F-018), so
   edges are keyed by row index and never by field name.
3. **Field-to-relation mapping lives in `config/relations.yaml`**, not in code,
   for ADR-005's reason: it is a claim about the corpus and a judge should be
   able to disagree with one line without touching Python. 109 field names
   collapse to 15 relations.
4. **Unmapped field names are reported, never swallowed.** A relation expressed
   under an unmapped field is an edge that silently never exists, which looks
   identical to the corpus not asserting it. Currently zero unmapped.
5. **Plain-text entity references resolve by exact name match.** See F-020 -
   this recovers 26 edges and connects 10 otherwise isolated entities. The
   method is recorded on the edge (`extraction`) because a name match and a
   `[[link]]` carry different confidence.
6. **No graph database.** 117 nodes and 267 edges is a dict of lists. Neo4j
   would be a dependency a teammate must defend to a judge in exchange for
   nothing measurable at this size.

**What the graph does not do**

`1b_009`'s conflict is **not representable from infoboxes alone**. The purge
page asserts the Cartel as victor in its `Victor` row. The Cartel's own page
carries `Belligerent in` including the Purge, and a `Victor of` row that omits
it. Under F-014 that omission is **silence, not denial** - and the actual denial
("participation without assigning the Cartel the status of victor") is prose,
reachable only by ADR-012's claim extractor. The graph correctly represents one
assertion and one silence; it must not be read as having captured the
contradiction.

**Trade-offs**

Infobox-only means prose relations are invisible. That is deliberate for this
checkpoint - it keeps the measurement clean about what *structure* recovers -
and it is why the number above is evidence coverage rather than a score.

*Status: accepted, validated by 21 tests and the 7/7 coverage measurement.*

---

## ADR-017 — The query layer: four templates, no planner, one prose-reading rule

**Problem**

ADR-016 measured evidence coverage, not answers: `1b_007` returns five candidate
paths and needs a type filter; `1b_009` returns nine and needs conflict
handling; nothing yet resolves a question's own text to a graph key or a
relation chain. This ADR is the query layer that closes that gap -
`question -> entity -> route -> bounded traversal -> sufficient evidence ->
answer` - built and measured against all seven dev 1B questions as regression
cases, none of them hard-coded.

**What we built**

Five modules, still no dependency beyond the standard library:

| Module | Job |
|---|---|
| `resolve.py` | Mention -> key: exact, normalised, alias, fuzzy candidates (never a winner) |
| `route.py` | Question text -> relation chain, by trigger phrase, not by entity |
| `evidence.py` | Names the eight-plus sufficiency states a traversal can end in |
| `conflict.py` | Same-tier contradiction detection - the piece `authority.yaml` promised |
| `engine.py` | `answer_question()`: wires the above into one call |

**The four templates.** Measured on the seven dev 1B questions, not designed in
advance: `lair_dominion` (`lair_in -> ruled_by`), `relic_custody` (`wields ->
housed_in`), `victory_membership` (`member_of <-> victor_of`, direction read off
the resolved entity's *type*, not the question), and `victor_connection`
(`victor_of -> member_of` with a fixed goal, plus a conflict check). Three
questions - `1b_005`, `1b_022`, `1b_006` - are one template exercised in both
directions, which is the generalisation test the instructions asked for: the
same trigger phrase and the same code path answer "which war did X's faction
win" and "who was a member of the faction that won war Y" because the graph
already stores both directions.

**Entity resolution adds two tiers ADR-011 stopped short of.** Alias resolution
is a measured naming pattern, not a lookup table: ten wiki characters are named
`"<name> the <Epithet>"` (`Corvus Hollowmere the Pale`, `Aldous Wrenfield the
Last Warden` - the second needed the epithet rule to accept multiple words,
caught writing the test for the first). Fuzzy candidate generation reuses
ADR-011's own measurement (`caedmon_fellgard` ~ `ederon_fellgard` at 0.839) to
justify never selecting a winner - `resolve("Caedmon Fellgardd")` always returns
`AMBIGUOUS` with candidates, even though one candidate is a near-exact match.
An escalation hook exists and is counted, but is not wired to a live model: none
of the seven dev questions need it, and CLAUDE.md's rule is that an LLM call
must be justified by a measured gap, not added speculatively.

**Type-aware traversal, proven on `1b_007` specifically.** `filter_endpoints`
applies two filters in sequence with *different* fallback rules - see F-021,
which records the version that made this dead code. The coarse `entity_type`
filter is unconditional (already permissive to unknown types, so a further
empty result is a real signal); the lexical filter against the question's head
noun falls back when it would empty the set, because a hint like "redoubt" not
appearing in "Gloamreach" is a wording gap, not a corpus gap. `1b_007`'s three
genuine victories collapse to one exact match on the word "accord" - the graph
never sees the literal string "Leaden Accord" as a special case.

**Evidence sufficiency, named rather than inferred.** Nine states:
`no_template_match`, `unresolved_entity`, `ambiguous_entity`,
`outside_structured_coverage`, `relation_unavailable`, `no_path`,
`path_missing_attribute`, `sufficient`, `abstention`, `conflicting_evidence`.
Two are worth explaining because the corpus does not hand them over easily:

- **`outside_structured_coverage` vs `unresolved_entity`.** Measured, not
  invented: `Halvard Cindervale` is a real, richly described character - tier-1
  codex prose, an ephemera contract, a birth year, a faction membership - with
  **no wiki page**, so the wiki-infobox-only graph has no node for him at all.
  That is `OUTSIDE_STRUCTURED_COVERAGE`: a genuine corpus entity the graph's
  own deliberate limit (ADR-016) does not reach. A name that appears nowhere in
  the corpus (`mentioned_in_corpus` over all 30,553 evidence units returns
  false) is `UNRESOLVED_ENTITY` instead - a different remedy (fix a typo vs.
  extend the graph past infoboxes).
- **`relation_unavailable` vs `no_path`.** `walk_relations` itself returns an
  empty list either way, by its own design (its docstring is explicit that
  this is deliberate). The distinction is reconstructed by checking whether
  any edge of the *first* relation in the chain touches the start entity at
  all: zero means this entity's page never expresses that relation kind; at
  least one, with the chain still failing, means the relation exists but does
  not lead where the question needs (`Ederon Coldwater` is a member of House
  Morvain, which never records a victory - `NO_PATH`; `Gravemaw Wyrm` has no
  membership of anything - `RELATION_UNAVAILABLE`).

**`1b_009`'s conflict, and why it needed a prose rule.** The graph alone cannot
tell `1b_009` apart from `1b_005`/`1b_022` - all three have the identical edge
shape (a `belligerent_in` edge on the faction's own page, a `victor_of` edge
only on the conflict's page), because ADR-016 never extracts a `denies` edge
from prose. What differs is one sentence on `wiki/the_iron_ring_cartel.md`:
*"This record establishes participation without assigning the Cartel the
status of victor."* `conflict.py`'s `_DENIAL_RE` is a small, closed regex over
paragraphs of the *claimed subject's own page* - a negation within ~80
characters of a victory word - in the same spirit as `cells.py`'s abstention
pattern, not a general claim extractor. Verified against both sides: it fires
on the Cartel's page (same tier, 2, as the assertion - `unresolved_same_tier`,
`must_surface: True`) and does not fire on `wiki/the_silent_choir.md`, which
never uses any victory word at all in connection with The War of Drowned
Light - silence, correctly read as silence, not a denial.

**Measured result**

```
7/7 dev 1B questions answered correctly through the generic mechanism, none
hard-coded:
    1b_013  The Bleeding Crown            (vertical slice)
    1b_005  The War of Drowned Light      (reverse traversal)
    1b_022  The War of Drowned Light      (same mechanism, different character)
    1b_007  The Leaden Accord             (type filter over 3 genuine victories)
    1b_003  Gloamreach                    (qualified custody chain)
    1b_006  14 members, exact match to the answer key's set (any_of, not forced to 1)
    1b_009  Halvard Crowhurst + CONFLICTING_EVIDENCE, must_surface: True

41 new tests, 184 total (was 143). Every required scenario from the task has a
named test: exact/normalised/alias/ambiguous resolution, reverse traversal,
multi-valued relationships, type filtering, repeated field names, a contextual
qualifier, explicit abstention, no-path, path-with-insufficient-evidence,
complete evidence, same-tier contradiction, a silent source, and provenance
preservation.
```

**What we did not do**

No LLM planner - four trigger-phrase templates covered every dev question, so
CLAUDE.md's "measure insufficiency before building the fallback" gate was never
crossed. No vector fallback - same reasoning, and no dev question produced an
explicit insufficiency that would justify one. No general claim extractor for
`1b_009` - one closed regex, tested against both the page it must fire on and
the page it must not.

**Trade-offs**

The four templates are trigger-phrase matches on English wording, which is
exactly as brittle as that sounds outside this dev set - a fifth genuinely new
question shape will log a `NO_TEMPLATE_MATCH` miss rather than being answered.
That miss is the intended signal for when a fifth template (or, if the miss
rate justifies it, an LLM router) earns its place; CLAUDE.md's rule is to let
that number accumulate before reaching for either.

*Status: accepted, validated by 41 tests and the 7/7 dev-question measurement above.*


---

## ADR-018 - The demo UI: stdlib http.server, and a presentation layer with a test to keep it one

**Problem**

The query layer answers 7/7 dev 1B questions but has no surface. The
competition needs 3-4 minutes of unedited live demo, and the thing being
demonstrated is not the answer string - a vector baseline can produce
"The Bleeding Crown" - it is the evidence path, the tiers, and what the system
does when sources disagree. Nine surfaces have to be visible at once.

**Decision 1: stdlib `http.server`, no framework**

Streamlit was the obvious alternative and was rejected. CLAUDE.md's binding
constraint is that every team member can explain and modify any part of the
submission on demand; Streamlit's rerun model and session state are behaviour a
teammate would have to defend to a judge in exchange for nothing this page
needs. There is no client-side state here - the whole interaction is a GET with
a query string. The result is 3 modules a Python programmer reads top to bottom
and **zero new entries in requirements.txt**.

The graph is built once at startup (~5.5s measured) and held. Rebuilding per
request would make the demo feel broken and prove nothing.

**Decision 2: the UI renders the contract; it does not compose an answer**

`src/ui/view.py` turns one `Answer` into a plain dict; `src/ui/render.py` turns
that dict into HTML and imports nothing from `src.query` or `src.graph` at all.
The line drawn, and enforced:

- reading a property the engine already computed (`EvidenceStatus.is_answerable`,
  `ConflictReport.status`, `.must_surface`) and printing it verbatim - allowed;
- grouping edges by path, collecting the tiers those edges already carry, and
  looking a node's display name up by key - allowed;
- comparing two tiers to decide a winner, re-running a traversal, re-applying a
  type filter, or writing a sentence from `values` + `status` + `conflict` -
  **absent**.

That last one is the interesting constraint. `1b_009`'s expected answer in the
key is prose, and `Answer` carries no prose field. The UI does **not**
manufacture the sentence. It shows the supported hop, the disputed hop, and
both sources at their tiers, and lets the reader draw the conclusion. Composing
that sentence would be answer generation in presentation code, which is exactly
the layering this project refuses.

**One join, deliberately allowed and named.** `_is_disputed` marks a hop when
its relation and its two endpoints match the ones `check_conflict` already
reported. It locates the engine's finding among the hops being drawn; it never
decides that something is in dispute. With no report, or one the engine did not
flag `must_surface`, nothing is ever marked - pinned by
`test_disputed_marking_ignores_a_report_the_engine_did_not_flag`.

**Decision 3: the thinness is a test, not a promise**

Three architectural tests, because "it's a thin layer" is worth nothing to a
judge if the next commit can quietly make it false:

| Test | Asserts |
|---|---|
| `test_view_imports_only_the_response_contract` | the view's `src.*` imports are exactly `{graph.schema, query.engine, query.evidence}`, and only `EvidenceStatus` from the last |
| `test_render_does_not_import_the_engine_at_all` | render.py sees plain dicts only |
| `test_view_and_render_import_no_reasoning_code` | no reasoning entry point is named in either module's code |

F-023 records the version of the third that false-positived on the view's own
`_route` helper.

**Measured result**

```
19 new tests, 203 total (was 184). All four demo questions render every
surface they have:

  1b_013  sufficient            1 route,   2 hops,  2 docs   tier 2
  1b_007  sufficient            2 routes,  4 hops,  3 docs   tier 2
  1b_006  sufficient           14 routes, 28 hops, 10 docs   tier 2
  1b_009  conflicting_evidence  1 route,   2 hops,  2 docs   tier 2 vs tier 2
          -> exactly 1 hop marked disputed, and it is the victor_of hop;
             the member_of hop is not marked.

Plus the two shapes a live demo hits by accident:
  no_template_match  -> the engine's own miss reason, printed verbatim
  ambiguous_entity   -> candidates listed with similarities, none selected
```

**What we did not do**

No LLM anywhere in this path - the page is the deterministic engine's output
and nothing else. No CSS beyond legibility: the instruction for this checkpoint
was that the evidence and explanation surfaces work before anything is made
pretty. No change to `src/query/` or `src/graph/` to make the UI easier - the
one place that pinched (`1b_007`'s filter decision is not on `Answer`) is
recorded as F-022 and left alone rather than fixed by widening the contract
mid-checkpoint.

**Trade-offs**

`1b_009`'s page requires the viewer to read two panels and draw the conclusion,
where a synthesised sentence would state it. That is the honest trade and it is
the right one for a judge audience: the sentence would be the system's least
verifiable output on the question whose whole point is that the evidence does
not settle itself.

*Status: accepted, validated by 19 tests and the four-question render above.*


---

## ADR-019 — Cue-based fallback routing, adopted from a measured comparison, not from a sister repo's say-so

**Context**

ADR-017 built four templates and set an explicit gate: measure routing
robustness on differently-worded questions before building anything more
general. A teammate's parallel repo (`github.com/YasiruRF/delphi`) had
meanwhile adopted our architecture wholesale and built a template-free,
cue-based router on top of it. That made the gate answerable by measurement
rather than by preference, and made it necessary — adopting their design
because it exists, or refusing it because it is theirs, would both be
decisions made without a number.

**What we measured**

A 55-question set was authored by a party with no access to either router, to
`src/query/route.py`/`engine.py`/`resolve.py`, or to `config/relations.yaml`.
That last file was withheld specifically because it is the cue router's own
vocabulary source: an author who read it would have written questions in its
words and handed that router the result. The set was frozen, with its sha256
recorded in the file, before either router ran against it
(`eval/robustness/routing_robustness_v1.json`). It holds 28 paraphrases of our
dev questions across four axes, 21 novel multi-hop questions, and 6 that should
be refused.

Only path *selection* differed between arms. Same graph, same `find_paths`,
same corpus, same scorer (`eval/scoring.py`, negation guard included). Both
arms ran with LLM escalation disabled, so the comparison measures routing and
not "has a model".

```
                     routed   correct   complete evidence   precision
four templates        11/49       10           11              91%
cue-based             30/49       12           20              40%
templates, then cues  32/49       17           24              53%
```

**The number that closed ADR-017's gate**

The four templates match no route shape on **35 of 49** answerable questions.
On the 21 *novel* questions they match **one**. That is not a defect — they do
exactly what ADR-017 said they would — but it settles the question the gate was
about: our 7/7 on the dev questions measures fit, not routing capability. A
template set fitted to seven questions does not generalise past re-wordings of
them, and now we have the number rather than the suspicion.

**Decision**

Add cue-based routing as a **second tier**, never a replacement
(`src/query/fallback.py`). Templates run first, so every answer they already
produced is unchanged and nothing regresses; the fallback only ever sees a
`RouteMiss`. Measured on the integrated engine: **17 correct and 26 complete
evidence, against 10 and 11 for templates alone.**

Its answers get their own statuses — `FALLBACK_SUFFICIENT` and
`FALLBACK_AMBIGUOUS` — rather than reusing `SUFFICIENT`. The two tiers measure
91% and 40% precision, and collapsing them would let the weaker one borrow the
stronger one's credibility. `EvidenceStatus.is_fallback` exists so the UI can
say which tier answered, and `src/ui/view.py` does.

**What we took, and what we refused**

The sister router carries four guards. Ablated individually against the frozen
set (`python -m comparison.ablations`):

| guard | effect when removed | decision |
|---|---|---|
| coverage-over-length | correct 12 → **2** | ported |
| irregular verbs | correct 12 → 9 | ported |
| consecutive-repeat | correct 12 → 12 | **not ported** |
| tie-break stopwords | +1 correct, −1 complete evidence | kept, flagged as below our resolution |

Coverage-over-length carries the router almost entirely. Consecutive-repeat
prevention was added against a measured failure in *their* stack that does not
reproduce in ours; a guard with no measured advantage here is code we could not
justify to a judge, so it stayed out. We also did not import their folder
structure, their ADR numbering, their conflict detector, their model list, or
Flask and Docker.

One defect in their implementation was fixed rather than copied: their stemmer
folds `ruled`/`rules`/`ruling` to `rul` but leaves the base form `rule` alone,
so "falls under whose rule?" never cues `ruled_by` while "which power rules..."
does. Worth one question, measured.

**Four harness bugs, and why they are recorded here**

The first numbers this comparison produced were wrong, and all four causes were
ours (F-024). The worst used our paragraph-scoped `find_denial` as a per-edge
filter, which excluded the Iron-Ring Cartel's *uncontested* Leaden Accord edge
and turned `1b_007` and `1b_022` into false `not_found`s for the sister arm —
a result that, published, would have understated a teammate's work by two
questions. The calibration that caught it: with all four fixed, arm A
reproduces ADR-017's 7/7 exactly. A comparison harness that cannot reproduce
the result you already know is not measuring what you think it is.

**Trade-offs, stated plainly**

Precision falls from 91% to 57% and honest refusals from 6/6 to 5/6. We are
trading abstentions for a mix of right and wrong answers, and the fallback's
dominant failure is not a miss but a **confident wrong answer**: it stops one
hop short and returns the waypoint — "The Cinder-Wrought Aegis" where the
answer is "Gloamreach" — with a real evidence trail attached. That is worse
than a miss for a project whose claim is that answers are checkable. The
separate status, the UI label, and the tests that pin the declining behaviour
are what we are relying on to keep that trade honest. If it stops being
honest, the fallback tier comes out.

**What would overturn this**

49 answerable questions is small, and differences of one or two (the stemming
fix, tie-break stopwords) are not resolvable at that size. Group A is
paraphrases of questions the templates were fitted to, which flatters arm A
rather than the fallback. A larger, differently-authored set could move any of
these numbers.

*Status: accepted, validated by 13 new tests (216 total) and reproducible via
`python -m comparison.harness` and `python -m comparison.ablations`.*

---

## ADR-020 — OpenRouter as a second provider, a plan-emitting third routing tier, and phrasing with counted provenance

**Context**

ADR-019 left two numbers on the table. After both deterministic tiers run, 19
of 49 answerable questions (39%) still reach no route at all, and the system
had no way to turn a verified chain into a sentence. The written plan for this
work set an explicit gate: introduce a planner *only* if neither deterministic
approach handles novel question structures adequately, and then only as a
fallback that emits a constrained plan — never as the primary reasoning engine,
and never answering directly.

39% is inadequate. The gate is cleared, and this ADR records what was built
against it.

**Decision 1 — a second provider, with a verified model list**

`src/clients/openrouter.py`. Gemini's ~20 requests/day/model is survivable for
OCR, which runs once and is cached forever, and not survivable for anything
invoked per question. Gemini stays the OCR client, untouched.

The sister repo's model list was *not* inherited. Checked live against
`https://openrouter.ai/api/v1/models` on 2026-09-01: 420 models, 18 free-tier,
and all four of their ids still exist. Re-verify with
`python -m src.clients.openrouter --verify`, which fails loudly if a
configured model has disappeared.

That check earned a correction their version does not have: **only 4 of the 18
free models advertise `structured_outputs`.** A planner whose output is not
schema-checkable is a planner we would have to trust, so the rotations are
split — `PHRASING_MODELS` (any free model) and `PLANNER_MODELS` (schema-capable
only).

Both of the sister repo's live-found bugs are kept as regression tests rather
than rediscovered: OpenRouter answering HTTP 200 with an error body, and a
host with no outbound route raising an `OSError` that `retry.py` does not
classify as retryable. Each crashed a live request in their stack.

**Decision 2 — the planner emits a plan, never an answer**

`src/query/planner.py`. The model receives the entity and relation
vocabularies and the question, and returns `{start_entity, relations,
answer_type}` under a strict JSON schema. It never sees the corpus, never
receives evidence, and has no tools.

    question -> [template] -> [cue fallback] -> LLM plan -> VALIDATE -> walk_relations

`validate_plan` is the entire safety boundary and rejects rather than repairs.

**Decision 3 — deterministic by default**

`answer_question(use_planner=...)` defaults to **False**. Deterministic-first
is stated as a default rather than as a comment, with two concrete
consequences: no test and no eval sweep can silently spend daily quota or
depend on a model being reachable, and every measured number stays
reproducible. `src/ui/server.py --with-model` opts in.

This was not the original design. It became obvious when the test suite went
from 200s to over 420s because an API key had appeared in `.env` and every
test hitting a routing miss started making live calls (F-025).

**Decision 4 — phrasing, with provenance as a field**

`src/query/synthesis.py` turns a verified chain into prose.
`Synthesis.phrasing` records `model | template | none`, so the report can state
what fraction of demo answers needed a model — and so the honest answer to
"did the AI write this?" is a field, not a claim. The template path is the
default, uses identical evidence, and is what runs with no key or no network.
The evidence trail is always rendered alongside the prose, never replaced by
it.

**Decision 5 — the graph visualiser is ours, not vis-network**

`src/ui/graphview.py` draws all 117 entities and 261 edges as one static SVG:
~60 lines of Fruchterman-Reingold, seeded from node keys so the drawing is
byte-identical every run. No CDN, no JavaScript, no dependency.

The sister repo's vis-network version adds no *Python* dependency, which is how
it would pass a rule like ours — but it needs the network at demo time, which
CLAUDE.md's "never record the demo against a cold cache" exists to prevent, and
nobody here could modify it under questioning.

Tuning it was itself a measurement: the textbook `k = sqrt(area/n)` pressed 42
of 117 nodes against the boundary clamp with overlapping labels. Sweeping the
scale (0.35/0.5/0.65/0.8) gave 0.5 as both least-clamped and least-crowded — 2
nodes on the boundary, closest pair 17.7px. A regression test pins it.

**What we did NOT build**

No Docker, and no launcher. The written plan says to consider them only after
the core evaluation is stable and not to add them merely because the sister
repo has them. There is no measured problem they solve for a team that runs
`python -m src.ui.server`, and under this project's own critical-evaluation
rule — *what measured failure does this fix?* — the answer is none. Revisit if
a judge cannot start the app.

**Trade-offs**

The planner is the first component where model output influences what gets
traversed. `validate_plan` bounds that, but it bounds *well-formedness*, and
F-025 records the day it turned out that was not enough. The mitigations are a
grounding check, an explicit decline channel, a distinct `EvidenceStatus`, and
a UI that labels which tier answered.

The planner is also unmeasured on the frozen set. Running it there would spend
daily quota and produce a number that changes with the provider's free lineup;
it is deliberately excluded, and the routing numbers in ADR-019 remain
deterministic-only. That means the 39% figure this ADR is justified by is a
measurement of what the planner is *for*, not of how well it does it.

*Status: accepted. 269 tests, 66 of them new. Model list re-verifiable with
`python -m src.clients.openrouter --verify`.*

---

## ADR-021 — Question shape is a routing failure of its own, and a near-miss spelling is reported rather than resolved

**Problem**

Two commits (`626631e`, `885b5fd`) shipped on 1 Sep with no ADR. Both touch the
boundary ADR-011 draws — *resolution is exact match, and fuzzy matching may
never pick a winner* — and one of them adds a seventh answerable
`EvidenceStatus`. A judge who reads ADR-011 and then finds `difflib`
similarity scanning in `src/query/engine.py` has no document reconciling the
two. This ADR is that document, written three days late.

The triggering observation was that *"Who is Ravena Stormwell?"* returned
nothing, and tracing it found **two independent causes**, not one.

**What we measured**

1. **Shape, not coverage.** *"Who is Ravena Stormwell?"* — spelled correctly —
   also failed. It names an entity the graph knows and no relation at all, so
   both deterministic tiers declined correctly. Yet
   *"which faction is Ravena Stormwell a member of"* answers The Silent Choir
   immediately from the same graph. The evidence was present; the question
   shape had no route.
2. **A near-miss was found and then discarded.** The resolver scores
   `Ravena Stormwell` at **0.968** against the typo and correctly refuses to
   pick it — ADR-011's reason holds: `caedmon_fellgard` and `ederon_fellgard`
   sit at **0.839**, so any threshold loose enough to accept 0.968 eventually
   merges two real people. But the engine then returned a bare
   `no_template_match` and never mentioned the candidate, leaving a user with a
   typo no route to the right spelling.

**Decision**

1. **`EvidenceStatus.PROFILE` and `fallback.profile_of`.** When an entity
   resolves and *no* relation is cued, return every edge touching that entity
   as a one-hop path. Each fact is one the graph already built from an infobox
   row, with its document attached — so this is not a guess. It is also not an
   answer to a narrow question, which is why it carries its own status and says
   so, rather than borrowing `SUFFICIENT`'s credibility.
2. **Only identity-shaped questions earn a profile.** `IDENTITY_QUESTION_RE` is
   a closed list — `who/what is|was|are|were`, `tell me about`, `describe`.
   The first version fired whenever no relation was cued, so *"What did the
   Gravemaw Wyrm eat for breakfast?"* was answered with the wyrm's lair. Two
   existing tests caught it. Labelled or not, that is F-025's failure exactly:
   answering a question nobody asked. The line that holds is that *"Who is X?"*
   asks for the record, so giving the record answers it.
3. **Near misses are reported, never resolved.** `AMBIGUOUS_ENTITY` now carries
   the candidates and their similarities, and the note names ADR-011 and tells
   the user to retry with the exact name. **Nothing is resolved automatically
   at any similarity.** Reporting is safe precisely where guessing is not.
4. **The reporting floor is 0.90, and governs display only.** MEASURED: real
   typos score 0.941 (`halward crowhurst`), 0.947 (`gloamreac`), 0.966
   (`Ederon Fellgar`), 0.968 (`Raven Stormwell`); the worst noise — a window
   swallowing a correctly-spelled name plus a neighbour, `was Ederon Fellgard`
   — tops out at **0.882**. 0.90 sits in that gap. It is deliberately far above
   the resolver's own `FUZZY_FLOOR` of 0.72, because that floor decides what we
   *show* and never what we *pick*.
5. **The scan is over word windows, not capitalised spans.** The first version
   used `_CAPITALISED_SPAN_RE`, so `halward crowhurst` (lowercase, v/w typo)
   got no suggestion while `Halward Crowhurst` did — though the resolver scores
   both at 0.941. People typing into a search box do not capitalise, and they
   paste entity keys with underscores. Windows are 1–4 tokens (the longest
   corpus name, `Cerys Sablewood the Ashen`, is four); function-word-only
   windows are skipped, which measured **77ms → 49ms** per question on the miss
   path with no change to any suggestion produced.

**Effect on the frozen set — and a correction to ADR-019**

Re-running `python -m comparison.harness` today:

```
metric                  A templates   B cues   C shipped
route_success                    11       30          30
answer_correct                   10       12          17
complete_evidence                11       20          26
no_route_shape                   33        4          14
```

Arm C is unchanged (**17 correct / 26 complete evidence**) and arm B is
byte-identical, so ADR-019's adoption argument stands untouched. **Arm A moved**:
four questions were reclassified from `no_template_match` / `relation_unavailable`
to `ambiguous_entity`, so the templates tier's `no_route_shape` count is now
**33 of 49, not the 35 ADR-019 records**. No answer changed correctness. ADR-019's
headline should be read as 33/49 from this commit forward; the 35 was correct when
written and is retained here rather than edited out of that ADR.

**Measured limitation — the suggestion misdiagnoses a correct spelling**

Three of those four reclassified questions are **apostrophe-less possessives**:

```
rb_008  isolde mournvales group won what war
rb_016  ederon fellgards faction won which accord
rb_028  what war did ravena stormwells lot end up winning
```

Every one of those names is spelled correctly. The system reports *"'isolde
mournvales' is not a name in the corpus"*, which is true of the span and
misleading about the question. `_strip_possessive` handles `'s` and `’s` — this
is the same bug in the form it does not handle. MEASURED: stripping a bare
trailing `s` makes all three resolve exactly (`NORMALISED`), which would also
let the cue tier route them. That fix is **not made here**, because stripping a
bare `s` is not obviously safe against plurals and names ending in `s`, and it
deserves its own measurement rather than being smuggled into a documentation
commit. Logged as **F-026**. The fourth, `rb_050` (`Cerys Sablewode` →
`Sablewood`, 0.960), is a genuine typo correctly reported.

**Why not fuzzy resolution after all**

Because ADR-011's number has not moved. 0.839 between two real people is still
below 0.90, but the gap is 0.06 and it is the *only* thing separating a helpful
suggestion from a silently merged identity. A suggestion a human accepts costs
one keystroke; a merge nobody sees costs a wrong answer with real citations
attached — the failure mode this project exists to prevent.

*Status: accepted, retroactive. Pinned by the tests added in `626631e` and
`885b5fd` (`tests/test_fallback.py`); 298 tests total. Reproduce the frozen-set
numbers with `python -m comparison.harness`.*

---

## ADR-022 — The architecture diagram is a hand-authored SVG, pinned by tests

**Problem**

An architecture diagram is required twice — challenge doc §5.2 ("include
architecture and design diagrams") and §5.3 ("solution overview and
architecture, with a diagram") — and Presentation & documentation (10% of the
rubric) names it explicitly. `docs/diagrams/` was empty.

The question is not whether to draw one. It is what a diagram is *made of* in a
project whose binding constraint is that every team member must explain and
modify any part of the submission on demand.

**Options considered**

| Option | Cost | Why not |
|---|---|---|
| Mermaid in Markdown | none to author | Renders on GitHub, but the report is a **PDF**. Exporting needs `mermaid-cli` and therefore Node — a toolchain, in a Python repo, for one picture |
| Graphviz / PlantUML | a new dependency + a binary | Same problem, plus a layout engine whose output we do not control and cannot nudge |
| Generate SVG from the graph | reuses `src/ui/graphview.py`'s approach | **The diagram is not a rendering of data.** It is a static picture of a design. There is nothing to generate it *from*, so this would mean inventing a data structure whose only consumer is the picture |
| Hand-authored SVG | ~200 lines of XML | Chosen |

**Decision**

`docs/diagrams/architecture.svg`, written by hand, checked in.

**Why**

1. **No toolchain at all.** A browser renders it, GitHub renders it inline from
   Markdown, and Word and LaTeX both import it for the PDF. Nothing has to be
   installed, and nothing can break between now and 9 September.
2. **A teammate can change it with a text editor.** Every box is a `<rect>` and
   every label is a `<text>`; fixing a number means editing that number. This is
   the same standard the rest of the repo is held to, and there is precedent —
   `src/ui/graphview.py` already emits SVG by hand with no CDN and no JS.
3. **Self-contained, like the UI.** No external reference of any kind, enforced
   by a test. A diagram that needs the network renders as a broken box on the
   judge's machine.

**The part that matters more than the format**

**A diagram is the one artefact nobody re-runs.** Its numbers are claims, and
nothing in this project would have noticed them going stale — which is not
hypothetical: ADR-019 recorded "35 of 49" and the true figure was **33** for
three days, while the committed comparison JSON already held the new number
(F-026). Prose drifts silently; artefacts do not.

So the diagram is pinned the way ADR-010's twelve templates are pinned. Ten
tests in `tests/test_diagram.py` re-derive every number from the live corpus —
file count from the integrity manifest, ingestion counts from a real ingest,
entities and edges from the built graph, cells and templates by re-parsing the
wiki — and fail if the picture disagrees. Three further tests assert claims
rather than counts: that both query-tier model calls are marked *off by default*
**and that `answer_question`'s signature actually agrees**, that `7/7` never
appears without `33 of 49` beside it, and that the graph box does not borrow the
query layer's `7/7` (ADR-016 measures evidence coverage, not correctness — two
different claims that would read as one).

**A mistake worth recording, because it was the guarded failure reproducing
itself inside its own guard**

The first version of these tests collected every integer in the file and asked
whether the measured value was among them. Verified by mutation, as any
assertion of this kind should be: changing the graph box from **117 to 125**
left the suite **green**, because `117` still appeared in the UI box's
"/graph renders all 117 entities". A number present *somewhere* proves nothing
about the box that should carry it.

That is F-026 exactly — a summary check holding steady while the specific thing
underneath it regressed — recreated in the test written to prevent it. The tests
now assert exact rendered sentences (`f"Graph — {n} entities, {m} edges"`), and
both mutations fail as they should.

**Trade-offs**

Hand-authored SVG means no automatic layout: moving a box means moving the
arrows that touch it. At this size (about twenty boxes) that is minutes of work,
and it buys a picture with no build step, no dependency, and no way to drift
from the measurements without the suite noticing. If the architecture starts
changing weekly, revisit.

*Status: accepted. 308 tests, 10 of them new. Diagram rendered and visually
verified end-to-end; number pins verified by deliberate mutation.*

**AMENDMENT (2026-09-06).** `docs/architecture.md` now also carries **two
Mermaid flowcharts** — a build path and an answer path. The SVG stays exactly
as this ADR decided: it is the artefact that goes in the PDF and must survive
being opened offline on a judge's machine, which is what the no-toolchain,
no-CDN, self-contained rule is for. The Mermaid blocks are the *in-repo reading
aid*: they render on GitHub and in editors, they diff as text, and they answer
"what calls what" in a way an SVG's coordinates cannot.

This does not reopen the toolchain question. Nothing builds them — they are
fenced code blocks in a Markdown file, rendered by whatever is already reading
it, and if nothing renders them they degrade to readable text rather than to a
broken image. No dependency was added and none can be.

**Both pictures are pinned the same way.** `tests/test_diagram.py` parses the
Mermaid out of the Markdown, flattens it, and re-derives every number in it
from the live corpus — file count, canonical documents, evidence units,
entities, edges, relations, unmapped fields, corroborated edges, and the
`EvidenceStatus` count — using the same `assert_label` rule that binds a number
to the sentence it belongs to. A second picture is a second place for a number
to rot, and the answer to that is a second set of pins, not fewer pictures.

**This amendment was written because the first picture was already stale.** The
SVG said *"35 of 49"* while `comparison.harness` had said **36** since ADR-029,
and the suite was green — because `test_diagram_states_the_robustness_number_
beside_the_fit_number` asserted a literal string, and its own docstring
explained at length that a human had to remember to update it. A comment
describing a gap does not close it. That test now re-derives the figure from
the frozen question set and the committed harness result, so the picture and
the artefact cannot disagree silently. The literal is gone.

Two limits worth stating rather than discovering later:

- Re-deriving from `comparison/results/router_comparison.json` proves the
  picture agrees with **the last harness run**, not that the run is current.
  `python -m comparison.harness` before the report is final is still required,
  and `docs/numbers.md` says so.
- The corroboration figures were the sheet's one openly unguarded row. The
  Mermaid copy of *"259 of 265"* is now re-derived; the table in
  `docs/numbers.md` still is not.

## ADR-023 — When a cell's own verb contradicts the field name, the cell wins and the disagreement is counted

**Problem**

`src/graph/build.py` took edge direction from one place: the field name, looked
up in `config/relations.yaml`. Three rows in the corpus are written

```
| Mentor | Mentor of [[Ignatz Marrowgate]] |
```

The field name is `Mentor`, which config maps as **reverse** — "the cell names
my mentor". The cell text is `Mentor of [[X]]`, which says the opposite: the
page's subject **is** the mentor. The two disagree, the builder trusted the
field name, and three edges pointed backwards.

`rb_044`'s hand-traced gold path is
`Ashgrove --mentor_of--> Marrowgate --serves_at--> Cindermere Hold --ruled_by--> Ashen Vanguard`.
Hop 1 was inverted in the graph. The graph was asserting, with a real citation
attached, that Ignatz Marrowgate mentored Ignatz Ashgrove. It is the other way
round.

**What we measured**

1. **Scale: 3 of 267 edges, 3 of 8 `mentor_of` edges.** Every edge whose cell
   carries a leading verb naming the same relation the field name mapped, where
   the field name said reverse. Exactly three, all `Mentor`.
2. **The other 23 reverse edges are correct.** Enumerated all 26 reverse-built
   edges. The remaining 23 are bare-link cells under genuinely reverse fields —
   `Victor | [[The Ashen Vanguard]]` on a conflict page, `Members | [[A]]; [[B]]`
   on a faction page. The cell states no verb, so nothing contradicts the field.
   The reverse mapping is sound; only the contradicting rows were wrong.
3. **No corpus row uses `Mentor` in the reverse sense config assumes.** All nine
   `Mentor*` rows in the wiki: `Mentor of | [[X]]` ×3 (forward field, bare cell),
   `Mentorship | Mentor of [[X]]` ×3 (forward field, agreeing cell), and
   `Mentor | Mentor of [[X]]` ×3 (reverse field, contradicting cell). The
   `reverse: [Mentor]` entry fired three times and was wrong all three.

**Decision**

The cell's leading verb outranks the field name **when, and only when, the verb
resolves to the same relation the field name mapped**. `RelationMap.states_forward`
answers that question; `build_graph` flips the direction and records the flip in
`Graph.direction_overrides`, printed by the CLI beside `unmapped_fields`.

Deliberately narrow, for the reason ADR-009 keys the parser on table position
rather than on field names: a rule that fires on "the cell contains a verb"
would reach cells like `Personnel | [[Orin Veyra]] serves at [[Fenspire]]`,
which is a two-argument fact ADR-010 already handles, not a direction
disagreement. Requiring the verb to name *the same relation* keeps the rule to
the case we measured.

**Why not just delete `Mentor` from the reverse list**

One line, and it fixes today's three rows. Rejected because it fixes the
instance and not the class: a future `| Mentor | [[X]] |` with a bare cell —
the sense the config entry was written for — would then be read forward and be
wrong, and nothing would say so. The rule adopted here reads that row correctly
in both senses, because the bare cell states no verb and the field name still
decides.

**Why the override is counted rather than absorbed**

Same reason `unmapped_fields` is printed. A silent flip is precisely what caused
this bug: the builder resolved a contradiction without recording that a
contradiction existed, so nothing distinguished "config and corpus agree" from
"config and corpus disagree and we picked one". `direction_overrides` currently
reads `{'Mentor -> mentor_of': 3}`. If that number moves, a reviewer sees it.

**Effect on the frozen set: none**

MEASURED, `python -m comparison.harness`, before and after:

```
metric                  A templates   B cues   C shipped
route_success                    11       30          30
answer_correct                   10       12          17
complete_evidence                11       20          26
no_route_shape                   33        4          14
```

Byte-identical. **This fix moved no score.** It is recorded as a correctness fix,
not an improvement, and must not be reported as one. `rb_044` still fails: it now
traverses three hops but the cue router matches `member_of`, `ruled_by` and
`serves_at` and never `mentor_of`, because *"apprentice of"* is not in the cue
vocabulary for that relation. That is a separate gap and gets its own
measurement.

The justification for committing it anyway is that the graph was asserting a
false fact about two named people with a citation attached — the failure class
this project exists to prevent (ADR-016). A wrong edge that no current question
happens to traverse is still wrong, and the next question to traverse it would
have been answered confidently and incorrectly.

*Status: accepted. 313 tests, 5 of them new; the three corpus edges and the
override count are pinned. Reproduce the direction survey with
`python -m src.graph.build` and read the `direction overrides` line.*

## ADR-024 — A relation's question vocabulary is declared in config, separately from its field names

**Problem**

`relation_cues` builds a relation's recognised vocabulary from three sources,
all of them in `config/relations.yaml`: the relation's own name, its inverse's
name, and every field name mapped to it. That is ADR-019's guarantee — the
router's vocabulary cannot drift from the edges the graph holds.

It has a gap. `mentor_of`'s name is `mentor_of` and its inverse is
`mentored_by`; both stem to `mentor`. Every field name is `Mentor of`,
`Mentorship`, `Mentor` — also `mentor`. So the relation's entire vocabulary is
one word, and a question naming the *other party's role* cues nothing.

MEASURED: `rb_044` — *"Which faction rules the hold where the apprentice of
Ignatz Ashgrove the Oathless serves?"* — cued `member_of`, `ruled_by` and
`serves_at`, and never `mentor_of`, which is hop 1 of its gold path.

**Decision**

Relations may declare a `cues:` list. It is read into
`RelationMap.question_cues` and consumed only by `relation_cues`. The graph
builder never reads it.

The separation is the point. Field names describe **how the corpus writes a
fact**; cues describe **how a person asks about it**. `Apprentice` is not an
infobox field name anywhere in the archive — we checked all 95 wiki pages.
Listing it under `fields:` would have been the smaller diff and would have
asserted something false about the corpus, and worse, it would have mapped a
future `| Apprentice | [[X]] |` row in whichever direction we happened to write
— the ADR-023 bug, pre-installed. A test pins that `Apprentice` stays invisible
to `RelationMap.lookup` and `is_known`.

**What we measured**

`python -m comparison.harness`, before and after, diffed per question:

```
metric                  A templates   B cues   C shipped
answer_correct                   10       12          17     (unchanged)
complete_evidence                11       20      26 -> 27
no_route_shape                   33        4          14     (unchanged)
ambiguous                         4        5           9     (unchanged)
```

**Exactly one question changed**: `rb_044`, `complete_evidence` False → True.
Arms A and B are byte-identical. Nothing regressed.

**What this is not**

It is not a routing improvement, and must not be reported as one.

1. **`answer_correct` did not move.** `rb_044` now finds the gold route
   `mentor_of → serves_at → ruled_by` and *"The Ashen Vanguard"* is among its
   values — alongside thirteen others, because the cue tier also walks
   `member_of → ruled_by → serves_at`. It returns `fallback_ambiguous`, which is
   the tier declining rather than guessing, and is the correct behaviour at
   ADR-019's measured 40% precision. The question is still wrong.
2. **One of 55 frozen questions contains the word "apprentice"** — the one that
   motivated the change. Adding a cue because a specific question needs it and
   then quoting the resulting number is fitting to the set, which is the trap
   CLAUDE.md records for 7/7. The justification here is linguistic, not
   scored: `apprentice` is the role noun for the party at the other end of
   `mentor_of`, and the relation already declares that party in `inverse:`.
   The measurement's job was to show nothing *broke*, and it did that.

**What it exposes**

The single-word-vocabulary gap is not unique to `mentor_of`. Any relation whose
name, inverse and field names share a stem has the same blind spot, and the
frozen set cannot detect it because a question has to use the missing word for
the miss to show. Deliberately not fixed here: adding role nouns for other
relations would be unmeasurable additions on this set, which is how a cue list
turns into a pile of unfalsifiable guesses. It wants its own probe over the
relation table, not a speculative edit.

*Status: accepted. 316 tests, 3 of them new — two pinning the cue, one pinning
that it never reaches the builder. Reproduce with `python -m comparison.harness`.*

---

## ADR-025 — F-026's typo reporter fix: suppress, don't widen

**Problem**

F-026 recorded, deliberately open: the near-miss reporter's `_strip_possessive`
only strips a *marked* possessive (`'s`, `’s`). Three of 49 frozen questions
write the possessive with no apostrophe at all -

```
rb_008  isolde mournvales group won what war
rb_016  ederon fellgards faction won which accord
rb_028  what war did ravena stormwells lot end up winning
```

- all three names spelled correctly - and the reporter announced each as a
typo. `rb_016` is the sharp case: it previously returned
`relation_unavailable`, a *more specific and more correct* diagnosis, and the
near-miss reporter replaced it with a spelling complaint.

F-026 left the obvious fix unmade on purpose: "stripping a bare trailing `s`
is not obviously safe against plurals and names ending in `s`... it needs its
own measurement."

**The measurement**

Two questions, both answerable without guessing: does a bare-`s` strip
manufacture a *new* false suggestion, and does it ever swallow a name that
legitimately ends in `s`?

1. **11 real entity names end in "s"** ("Ashfall Colossus", "Embercrag
   Fortress", "The Weeping Marshes", "The High Spires", "Ignatz Ashgrove the
   Oathless", "The Psalter of Seven Sorrows", "Pale Stag of Omens", "The Crown
   of Burned Names", "Vharencrag Fortress", "The Ash Wastes", "The
   Cinder-Wrought Aegis"). Checked every one: none of their bare-`s`-stripped
   forms collide with a *different* entity's canonical key. A correctly
   spelled mention of any of them resolves normally before the near-miss
   reporter ever sees it - the reporter only runs after ordinary resolution
   has already failed.
2. Resolution past ADR-011's boundary is still exact/normalised/alias only,
   never fuzzy. A bare-`s` strip can only suppress a suggestion when the
   trimmed span is *byte-for-byte* a real canonical key - which is why a
   genuine English plural near a name ("the wyrms lair") cannot accidentally
   trigger it: `canonical_key("wyrm")` is not `canonical_key("gravemaw_wyrm")`.

**Decision**

`_resolves_when_bare_s_dropped` (`src/query/engine.py`) is checked only where
`_best_near_miss` was about to suggest a typo, and only *suppresses* that
suggestion - it is never added as a new source of suggestions. The asymmetry
is the point: F-026's risk was about widening what gets flagged as a typo, not
about missing genuine ones, so the fix is scoped to exactly the failure
measured and no further.

**Measured result**

```
python -m comparison.harness, before -> after:
    ambiguous (arm A)          4  -> 1     (the 3 false positives gone)
    no_route_shape (arm A)    33  -> 35    (2 of the 3 correctly reclassified
                                             as no_template_match)
    no_route_shape (arm C)    14  -> 16    (same 2, in the shipped tier)
    answer_correct  (all arms)     unchanged: 10 / 12 / 17
    complete_evidence (all arms)   unchanged: 11 / 20 / 27
```

**This moved no score**, by design - same shape as ADR-023 and ADR-024. What
moved is diagnosis quality: `rb_016` (`ederon fellgards`) now returns
`relation_unavailable` again, matching the pre-regression behaviour F-026
names as more correct, because Ederon Fellgard names a real member of a real
faction and the question just asks for a relation shape no template covers.
`rb_008` and `rb_028` now return `no_template_match` instead of a spelling
complaint about a name spelled correctly.

Reading `no_route_shape` moving **up** (33→35) as a regression would be
exactly the mistake ADR-021 itself warns about: a summary bucket does not say
whether the *reason* inside it is honest. Three questions that were wrongly
told "this is not a name" are now told, correctly, "no template covers this
shape" or "the relation this needs is not here." `no_route_shape` counting
both is the bucket's own coarseness, not a new defect - see the trade-off
note below.

**What we did not do**

Did not touch `_strip_possessive` itself, and did not add bare-`s` stripping
as a candidate span for *generating* typo suggestions - only for suppressing
one already about to be made. Widening the suggestion surface was never the
problem F-026 identified and would reopen exactly the risk it flagged.

**Trade-off, stated plainly**

`no_route_shape` bundling `NO_TEMPLATE_MATCH` and `PROFILE` (per
`comparison/harness.py`) but not `RELATION_UNAVAILABLE` means the bucket now
undercounts arm A's genuine "we understood the entity, not the shape" cases by
one (`rb_016`) relative to a bucket that grouped all non-answers together.
That is the harness's existing metric definition, unchanged by this ADR; a
future metric revision might fold `RELATION_UNAVAILABLE` in explicitly, and if
it does, these numbers move again for a third, equally legitimate reason.

*Status: accepted. 320 tests, 4 of them new
(`tests/test_fallback.py::test_an_apostrophe_less_possessive_is_not_reported_as_a_typo`
and its sibling pinning the "real names ending in s" measurement). Reproduce
with `python -m comparison.harness`. F-026 updated to record this as closed.*


---

## ADR-026 - A decline renders what it established, because an uninspectable result is indistinguishable from a bug

**Problem**

Technical execution and robustness is 25% of the rubric, and judges assess it
on whether the system works end-to-end *on inputs the team did not script*. The
submission includes a live demo where a judge may type their own question.

Measured, and the number is not close: `python -m comparison.harness` reports
the four templates match **no route shape on 35 of 49** independently authored
questions; on the 21 novel ones they match **one** (ADR-019, ADR-025). Running
the shipped three-tier engine over the frozen robustness set, **23 of 55
questions decline**, and **18 of those 23 are `no_template_match`**.

So on a judge-typed question the most likely outcome is a decline. Those
declines are architecturally correct - each ends at a named `EvidenceStatus`
rather than at an invented answer, and that is this project's central claim.
But the page showed the status string and nothing else, and **a bare status
string in a red pill looks exactly like a crash**. A principled refusal that
reads as breakage loses the 25% just as thoroughly as breakage would.

**Decision**

Every declining status renders the partial evidence the engine established on
the way to declining, with the same citations the `SUFFICIENT` path already
carries - document id and locator for everything displayed.

| Status | What the page now shows |
|---|---|
| `NO_TEMPLATE_MATCH` | the entities in the question that *did* resolve, each with its full neighbourhood - every edge, its relation, and the infobox row it was read from - plus the 15-relation vocabulary from `config/relations.yaml` |
| `UNRESOLVED_ENTITY` | the span read as a name, and a link to the entity list |
| `AMBIGUOUS_ENTITY` | every candidate with its type, source document and similarity; near misses at >=0.90 (ADR-021) offered as a **suggestion the user clicks**, never applied |
| `RELATION_UNAVAILABLE` | the resolved entity, the relation asked for, and the relations it *does* have edges for |
| `NO_PATH` / `PATH_MISSING_ATTRIBUTE` | start, goal, hops completed, and the endpoints the traversal did reach - stated as "could not join X to Y", naming both |
| `OUTSIDE_STRUCTURED_COVERAGE` | that the graph is wiki-infobox-only, and which collections *do* carry the name, quoted with evidence ids |

Plus, on `/`: a `<datalist>` autocomplete over all 117 entity names and a
browsable list grouped by type, with the relation vocabulary and each
relation's field names and question cues. Every entity name links to
`Who is X?`, which routes to `PROFILE` - so the list is a set of working entry
points, not a catalogue. This widens what the system can answer by **exactly
nothing**. It stops the boundary being discovered by failing at it.

**Where the collecting happens, and why not in the UI**

Collecting this is reasoning: it reads edges, walks neighbourhoods, consults
the relation map and scans 30,553 evidence units. `src/ui/view.py` is forbidden
to do any of that by ADR-018's three architectural tests, and those tests are
the only reason "the UI adds no reasoning" is a fact rather than a claim.

So it lives in **`src/query/diagnostics.py`**, hangs off `Answer.diagnostics`,
and the UI transcribes it into dicts and draws them. The thinness tests were
not relaxed by one line - the view's `src.*` imports are still exactly
`{graph.schema, query.engine, query.evidence}`, it still touches `graph.nodes`
exactly once, and `render.py` still imports nothing from the project at all.
`Diagnostics` reaches the view as an attribute of `Answer`, which needs no new
import.

**Measured result**

```
All 23 declines on the frozen robustness set now carry diagnostics; 0 do not.

  no_template_match     18   -> resolved entities + their records + vocabulary
  relation_unavailable   2   -> the relations the entity does have
  path_missing_attribute 1   -> the endpoints the type filter removed (F-022's gap)
  ambiguous_entity       1   -> candidates + a clickable corrected question
  unresolved_entity      1   -> the span, and the entity list

22 new tests, 342 total (was 320). The router comparison is byte-identical
before and after: 35 / 4 / 16 no_route_shape across the three arms, every
other metric unchanged. This ADR adds no reasoning and changes no answer.
```

**What this is not**

It is not a widening of the system's reach, and deliberately so. No template
was added, no threshold was loosened, nothing is auto-corrected. A 0.960
near-miss is still not resolved - it is *offered*, as a link the user chooses,
because ADR-011's reason for exact-match-only (`caedmon_fellgard` and
`ederon_fellgard` at 0.839 are different people) is unaffected by how helpfully
the refusal is presented. F-028 is the one defect this work fixed, and it was a
reporting defect, not a routing one.

**Trade-offs**

A decline page is now long - the `no_path` case lists fourteen endpoints and a
neighbourhood. That is the right direction for a judge reading it once, and the
wrong direction for a user asking twenty questions. Accepted for this
checkpoint, because the failure mode being fixed is "looks broken", and terseness
is what caused it.

`Engine` now ingests at startup (~5s, once) to make
`OUTSIDE_STRUCTURED_COVERAGE` reachable at all - see F-028. That is real
startup cost bought for one status, and it is worth it: that status is the only
one that explains an architectural boundary rather than a corpus gap, and it was
silently unreachable in the demo.

*Status: accepted, validated by 22 tests, the 23/23 diagnostics measurement, and
an unchanged router comparison.*


## ADR-027 — The other three collections corroborate edges; they cannot build them

**Problem**

`src/graph/build.py` line 196 reads `if unit.collection == "wiki":`. The answer
graph is built from wiki infobox rows and from nothing else. The other 167
canonical documents — 4 chronicles, 18 codex, 145 ephemera — are fully
ingested into evidence units carrying document id, locator and authority tier,
and the shipped answer path never touched one of them.

The sub-track is *"Connecting Facts Across Thousands of Pages"*. A judge who
greps that line concludes we solved a smaller problem than the track describes,
and they would be reading the code correctly.

**What we did NOT do, and why**

Delete the filter and build edges from the other collections. It yields
**zero** additional edges: only wiki pages carry infobox pipe tables, and the
builder parses table rows. Removing the filter makes the builder walk 27,415
more paragraphs and emit nothing. This was checked before any code was written.

A prose relation extractor over those collections was measured and rejected
separately on 2 Sep: of the 13 frozen questions that route but answer wrong,
**9 already have complete evidence**, and the 4 that do not name only wiki
pages in `required_evidence`. More edges was not the constraint.

**Decision**

A corroboration layer, not a graph extension. For each pair of entities the
graph already connects, find the non-wiki passages that name **both** ends, and
attach up to three to the edge with their document, locator, collection and
tier. `src/graph/corroborate.py`. The graph is not modified: a test asserts the
edge list is byte-identical before and after.

Three constraints, all inherited rather than invented:

1. **Exact names only.** The scan reuses `route.py`'s gazetteer — the same
   surface forms, article-drop and epithet aliases that question text is
   scanned against — so ADR-011 holds here unchanged. The scan *strategy*
   differs (one combined alternation instead of `extract_mentions`' per-surface
   compile) because this runs over the corpus rather than over one question.
2. **An ambiguous surface is reported, never resolved.** A form naming two
   nodes is dropped and recorded. The corpus currently produces none; the
   behaviour is tested with an injected collision rather than left unexercised.
3. **The wiki cannot corroborate itself.** The edge was parsed from a wiki
   page, so a wiki paragraph restating it is one source agreeing with itself.

**MEASURED**

Reproduce with `python -m src.graph.corroborate`:

```
units scanned        : 27415
edges                : 267
corroborated edges   : 255  (95.5%)
attestation cap/edge : 3
attestations attached, by collection:
    codex         416   on 238 distinct edges
    chronicles    114   on  85 distinct edges
    ephemera       25   on  23 distinct edges
```

**255 of 267 edges (95.5%)** are independently named outside the wiki. Of the
12 that are not, **6 are self-loops** — an edge from a node to itself, where
"both ends" is one end (F-030) — so against the 261 edges that connect two
distinct entities the figure is **255 of 261, 97.7%**. Report the 255/267 with
the self-loop note; do not quote 97.7% without it.

The collection split is the interesting number. The **codex** restates infobox
facts in near-verbatim prose — *"Gravemaw Wyrm lairs in Marrowwell Abbey"* is a
tier-1 codex sentence attesting `1b_013`'s first hop. The **chronicles** are
82% of the corpus by evidence unit and produce 114 attestations on 85 edges,
mostly incidental co-mention in scenes. Volume is not evidence.

**Co-mention is not proof, and the page says so**

A passage naming both ends is evidence that the archive discusses them
together. It is **not** a second assertion of the relation. The answer page is
worded *"also attested in N other documents — these name both ends of the hop;
they are not a second assertion of it"*, and a test forbids the words
"confirms" and "proves" in the rendered page. F-014's lesson — silence is not
denial — in its mirror form: proximity is not agreement.

**Why the conflict machinery is NOT wired to these units**

The brief for this work asked that disagreeing corroborations route into
`src/query/conflict.py`. Measured first, and the answer is no.

`_DENIAL_RE` matches **5** units across the entire non-wiki corpus, **0** of
which are attached to any edge, and **all 5 are false positives**. Two of them
*affirm* the claim they appear to deny:

```
"...the final line had been entered without triumph or lament:
 The Silent Choir victor of The War of Drowned Light."
"...without removing The Ashen Vanguard's status as victor."
```

The pattern is tuned for wiki infobox-page prose (*"the record does not
identify a victor"*) and does not survive contact with narrative. Wiring it
would let a tier-1 codex passage be rendered as a denial against a tier-2 wiki
edge — manufacturing a conflict that does not exist and resolving it *against*
the truth, with a real citation attached. That is precisely the failure this
project exists to prevent. A test pins the zero so the decision is revisited if
the corpus or the pattern changes.

This also matches what CLAUDE.md already records: all 7 measured corpus
conflicts are codex (tier 1) vs ephemera (tier 4), and the codex announces its
own authority in prose. Nothing in the corroborating units contradicts an edge.

**Cost**

One pass over 27,415 units, ~2s, built once at `Engine.__init__` beside the
ingest that already happens there. A request costs one dict lookup per hop. No
new dependency; no cache file; the graph is untouched.

*Status: accepted. 359 tests, 14 of them new. Graph counts unchanged at 117/267,
so `tests/test_diagram.py` and `docs/diagrams/architecture.svg` are unaffected.*

**AMENDMENT (same day, ADR-028).** F-030's six self-loops are now fixed at the
source and no longer built, so the graph holds **261** edges. The corroboration
numerator is untouched — the same 255 edges are attested — and the figure this
ADR reported as 255/267 (95.5%) is now **255/261, 97.7%**, which is the number
this ADR already identified as the honest one. Quote 255/261. The 95.5% above
is left as written because it was correct against the graph of the day.*

## ADR-028 — A row is a self-reference if its target resolves to the page's subject, whatever the field is called

**Problem**

`build.py` skipped title rows with `_SELF_FIELDS = frozenset({"Name"})` — a
closed list of field names, one entry long. F-030 measured what that misses:
six rows across six wiki pages name the page's own subject under a field name
that is a genuine relation somewhere else.

```
wiki/the_leaden_accord.md         | Conflict | [[The Leaden Accord]] |
wiki/the_winter_reckoning.md      | Conflict | [[The Winter Reckoning]] |
wiki/the_war_of_drowned_light.md  | Conflict | [[The War of Drowned Light]] |
wiki/the_war_of_endless_vigil.md  | Conflict | [[The War of Endless Vigil]] |
wiki/the_accord_of_mournthrone.md | Conflict | [[The Accord of Mournthrone]] |
wiki/ironfell_citadel.md          | Location | [[Ironfell Citadel]] |
```

Each produced an edge from a node to itself. `Conflict` is a real
`belligerent_in` field on a *character* page and a title row on the conflict's
own page, so this cannot be decided from the field name at all — only from the
target.

**Decision**

Skip a reference whose canonical key equals the page subject's key, at the
point of emission, regardless of field name. `_SELF_FIELDS` stays for the
literal `Name` field; the target test is what actually does the work.

Skipped rows are **counted**, not swallowed: `Graph.self_references` is keyed
`"<field> on <document>"` and printed by the CLI beside `unmapped_fields` and
`direction_overrides`. Same reason as both of those — a corpus fact resolved
silently is indistinguishable from a corpus fact that was never there. This is
ADR-023's rule applied to a second kind of disagreement.

**MEASURED**

```
edges                : 261        (was 267)
    in_region            31        (was 32)
    belligerent_in       21        (was 26)
self-reference rows  : 6 (skipped, F-030)
entities             : 117  page-backed 95, edge-only 22, isolated 0
```

Entities, page-backed, edge-only and isolated are all unchanged: the six
targets were already nodes by virtue of other edges, so removing the self-loops
removed no entity and orphaned none. 15 relations, 0 unmapped, unchanged.

**Effect on answers: none.** `python -m comparison.harness` is byte-identical
and the seven dev 1B questions still answer 7/7. No route in either set ever
walked a self-loop — a hop that returns to where it started cannot advance a
traversal, which is exactly why nothing noticed for a week.

**Effect on ADR-027's corroboration figure**

The numerator does not move. 255 edges are attested outside the wiki, before
and after. The denominator drops from 267 to 261, so the figure goes from
**255/267 (95.5%)** to **255/261 (97.7%)** — and 97.7% was already the number
ADR-027 said was the honest one, because six of its twelve misses were these
self-loops, uncorroborable by construction. The fix makes the headline figure
and the honest figure the same number. **Quote 255/261, 97.7%.**

**Why it was deferred once, and why it is done now**

F-030 recorded it as found-but-unfixed on 6 Sep: the count is re-derived by
`tests/test_diagram.py`, printed in `docs/diagrams/architecture.svg`, and
quoted in CLAUDE.md, README.md, `docs/architecture.md`,
`configuration-example/README.md` and the report outline. That is a wide blast
radius three days from the deadline for a defect that changes no answer.

Done now because the ripple is exactly what the diagram test exists to catch,
and it caught it — the suite went red on the stale SVG label the moment the
count moved, which is the design working rather than a cost. Every call site
moved together in one commit, and the historical statements in ADR-016,
ADR-023 and the failure log keep their original numbers: those measured 267
edges and were correct when written.

*Status: accepted. 360 tests, 1 of them new (the self-reference count). SVG
updated to "117 entities, 261 edges" and re-pinned.*

## ADR-029 — A template must consume the whole question, and only an unambiguous cue counts as unconsumed

**Problem**

F-031. `victory_membership` fires on the substring shape `member_of ->
victor_of`. Given *"Which war was won by the faction that Hesper Wrenfield's
mentor belongs to?"* it matched, resolved the start entity to Hesper, walked
two hops from *Hesper*, and returned **The War of Endless Vigil** with
`status: sufficient` and a clean citation trail. That is the answer to *"which
war did Hesper's own faction win"* — a different question. The mentor hop was
never walked, and nothing in the router asked whether the template had accounted
for the whole question.

It is ADR-017's `walk_relations` constraint one layer up. That guard exists
because the shortest path to the right endpoint took the wrong relation — right
endpoint, wrong route. This is right *shape*, wrong question.

**Decision**

After a template produces a `RouteResult`, `_covers_the_question` compares the
relations the question names against the chain the template will walk. If the
question names a relation the chain never walks, the template **declines** and
the question falls through to the next tier. A decline is a result (ADR-026); a
confident wrong answer is not.

**The measurement that shaped the rule, not just confirmed it**

The obvious version — guard on the full cue vocabulary — was built first and
measured before being wired in. It fails:

```
DEV (answer_key)  routed 7    would decline 0
FROZEN 55         routed 13   would decline 5   <- rb_023, rb_025, rb_039, rb_041, rb_043
3-HOP draft       routed 1    would decline 1
```

Three of those five — `rb_023`, `rb_025`, `rb_041` — are **currently answered
correctly**. The cause is the cue-vocabulary contamination first measured on
2 Sep: 7 of 65 cue words are shared across relations, and several are ordinary
nouns that arrive from field names carrying their own values.

```
plac       -> forged_at, housed_in, serves_at    ("Place of forging/housing/service")
conflict   -> belligerent_in, waged_at
record     -> belligerent_in, wields             ("Later weapon record")
major, military, personnel, serv
```

*"Which faction rules the **place** where the Pale Stag makes its lair?"*
contains "place" and means nothing by it. A word shared across relations is not
evidence that the question asks about any of them.

So the rule adopted counts **only cue words that name exactly one relation** —
58 of 65. Restricting it that way costs nothing and still catches F-031, because
`mentor` names only `mentor_of`.

**MEASURED, before and after, `python -m comparison.harness`**

```
metric                  A templates   B cues   C shipped
route_success              11 -> 11    30       30 -> 31
answer_correct             10 -> 10    12       17 -> 18
complete_evidence          11 -> 11    20       27 -> 28
no_route_shape             35 -> 36     4       16
```

**Templates' own precision is unchanged at 10/11 = 91%**, and the dev 7/7 is
unchanged — the two conditions F-031 set for keeping the fix, both pinned by
tests. `python -m comparison.ablations` is byte-identical (arm B is untouched).

Arm C **improved**: `rb_039` — *"Which faction won the war in which the Vault
Chitin was unleashed?"* — was being matched by `victory_membership` and failing
with `relation_unavailable`. Declining hands it to the cue tier, which answers
**The Bleeding Crown** with complete evidence. The template had been *blocking*
a correct answer, which is the second cost of routing a question you cannot
answer and the one nobody was counting.

`no_route_shape` for templates therefore moves **35 → 36**. That is the fourth
move of this number and the first that is not a diagnosis fix; CLAUDE.md's
standing rule to re-derive it rather than quote it from memory is now
underwritten by four separate movements.

**What this does NOT fix**

The three-hop questions are still not answered correctly. Measured on
`eval/multihop_3hop_draft.json`:

- `3h_001` — **correct** (`House Morvain`), via the cue tier.
- `3h_003` — `fallback_ambiguous`: the gold value is among six returned.
- `3h_002`, F-031's own question — the cue tier walks `mentor_of` one hop and
  stops, returning **Corvus Hollowmere the Pale**. Still wrong.

So the confident wrong answer from a *template* is gone; a wrong answer from the
tier that declares itself 40%-precision and shows its chain is what replaced it.
That is an improvement in honesty and in detectability — a reader who asked
"which war" and is handed a person's name sees the failure immediately, where
"The War of Endless Vigil" looked exactly like an answer — but it is **not** a
solution to three-hop routing, and must not be reported as one.

**Cost**

`route()` keeps its signature; the unique-cue map is built lazily and cached, so
no call site changed. `route.py` imports two pure vocabulary helpers from
`fallback.py` (`normalise_cue_word`, `question_tokens`) — tier 1 reaching into
tier 2's module is not ideal, but they are shared vocabulary utilities rather
than that tier's decision logic, and duplicating the stemmer would let the two
drift.

**On the timing.** F-031 set its own condition: fix this only after the report,
the video and the team-roles item land, none of which have. That condition was
overridden by explicit instruction. The protocol it specified was followed
exactly — measure, fix, re-measure, revert if templates' precision or the dev
7/7 moves — and neither moved.

*Status: accepted. 379 tests, 3 of them new: the F-031 question declines, a
shared cue word does not trigger the guard, and all seven dev questions still
route.*

## ADR-030 — Cross-collection entity reachability, measured

**The question ADR-027 did not ask**

ADR-027 measured **edges**: 255 of 261 edges between existing nodes are named
by a codex, chronicle or ephemera passage. Nobody had measured the **node set**.

`build.py` builds nodes from wiki infobox rows, so an entity that only the
codex, chronicles or ephemera name has no node at all, and a question about it
declines *by construction* rather than on evidence. That is a different and
strictly prior boundary to the one ADR-027 measured, and it was undocumented.

It also matters for ADR-027's own reasoning. That ADR justified not building a
prose relation extractor partly on the grounds that "the 4 wrong answers name
only wiki pages in `required_evidence`". `required_evidence` was itself derived
from the wiki-built graph, so that argument cannot by itself prove prose adds
nothing — it is partly circular. **The decision still stands; this measurement
is what widens its base.**

**Method**

`eval/probes/entity_reachability.py`, read-only, modifying nothing:

    python -m eval.probes.entity_reachability

Three measurements, in ascending order of precision:

1. **Corpus-wide name scan.** Over the 27,415 non-wiki paragraph and page
   units, two extractors: `route.py`'s gazetteer (reused through
   `corroborate.py`'s `scan_surfaces`, so the surface forms are byte-identical
   to the ones the answer path recognises — ADR-027 made the same call for the
   same reason), plus capitalised multi-word spans for names the gazetteer has
   never heard of. Resolution is **exact only** — `EXACT`, `NORMALISED`,
   `ALIAS`. A fuzzy near-miss counts as *unreachable*, because ADR-011 forbids
   fuzzy resolution from picking a winner and a probe may not quietly do what
   the product refuses to.
2. **Declared subjects.** Every non-wiki document is named
   `<doctype>_concerning_<subject>`, already parsed into
   `EvidenceUnit.subject_slug`. The corpus is *declaring* who each document is
   about, so this needs no extractor and carries no extraction noise.
3. **Silent relation rows.** Infobox rows on a mapped relation field that
   produced no edge, read from the graph's own public output (`Edge.document`,
   `Edge.row`) against an independent re-parse of the page. This finds the
   *cause*, not just the symptom.

**MEASURED**

```
distinct candidate names      : 741
  reach one of the 117 nodes  : 162  (21.9%)
  reach no node               : 579  (78.1%)
      ephemera   426     chronicles 121     codex 75

declared subjects             : 79
  reach a graph node          : 77   (97.5%)
  reach no node               : 2    (2.5%)

silent relation rows          : 26
  naming an entity the graph does not hold : 1
```

**The 579 is not an entity count and must never be quoted as one**

The brief for this work predicted the capitalised-span extractor would produce
noise, and it does. Fifteen of the 579 were sampled (seed 20260906, fixed in the
probe, so the sample is the same fifteen forever) and hand-checked against the
documents that name them. **0 of the 15 is an entity the corpus treats as
first-class.** All fifteen are one of:

| What it actually is | Sample members |
|---|---|
| Document title or title fragment | `Articles of Falconry and Service Concerning Ignatz Cindervale`; `Decree of Ashen Silence Concerning House Morvain and Maelis Harrowick the Pale Let`; `Pale Coast Concerning Gloamreach` |
| Section heading | `Conditions of Sale`; `Field Recognition`; `The Silent Accounting` (Volume IV's own subtitle) |
| Form-field labels run together | `Mark Attestation` — a petition's signature block |
| Two adjacent codex field values | `Hollowreach Housed` — `Forged at: Hollowreach` / `Housed in: Crookvale` |
| Verb or adverb swept in before a name that *does* resolve | `Bring the Sceptre of Final Winter`; `Describe Gloamreach`; `Perhaps Korvath` |
| Two names conjoined by "and" | `Ashreach and Embercrag Fortress` — both are nodes, separately |
| A signature formula wrapping a name that resolves | `Mark of Malchior Cindervale the Flame-Touched` |
| A bare definite-noun short form | `The Hold` — prose shorthand for a keep; no page, no infobox |
| Prose fragment | `Storehouses Held Stores` |

Every proper noun *inside* those spans that is an entity already has a node.
The honest reading of 579 is therefore **an upper bound dominated by extraction
noise**, and the hand-check puts the true rate at or near zero. An inflated
number would be worse than a small true one; this one is small.

**The number that survives: one**

Of the 79 documents that declare their own subject, two reach no node, and one
of the two is not a real gap.
`interrogation_record_concerning_isolde_fellgard_the_unforgiv.txt` is the
**corpus's own filename truncation** — `_the_unforgiv`, cut mid-word — and
`isolde_fellgard_the_unforgiven` *is* a node, reached under its full name from
`letter_concerning_isolde_fellgard_the_unforgiven.txt`. It belongs beside the
clipped scan tables already in `limitations.md`, not here.

That leaves **exactly one entity the corpus treats as first-class and the graph
has no node for: `halvard_cindervale`.** He is named in 21 evidence units — 5 in
the tier-1 codex Annals, 8 across three ephemera documents, and 8 in the wiki
itself.

**Why he has no node, which is the part worth having measured**

This is not a corpus boundary. It is a defect on our side, and it is one row:

```
wiki/the_ashen_vanguard.md
| Members | Halvard Cindervale; Voltaire Hollowmere; Orin Veyra |
```

That is an infobox row on a mapped relation field, and it produces **no edges at
all**. The cell carries no `[[links]]`, and `build.py`'s pass 1 resolves an
unlinked cell only against entities that **own a wiki page** — the `known` map
is built from page subjects. None of those three owns one, so the row resolves
to nothing and is dropped without appearing in `unmapped_fields` (the *field* is
mapped) or in `self_references` (it is not a self-reference).

Compare `wiki/the_silent_choir.md`, whose `Members` row *is* linked and yields
six `member_of` edges. The field name is not the problem; the linking is.

The general statement is: **an unlinked infobox cell can only name an entity
that already owns a wiki page.** Page-less entities — 22 of the 117 nodes exist
only as link targets — are unreachable from unlinked cells. Corpus-wide this
costs **one node and three edges**, and one node rather than three only because
Voltaire Hollowmere and Orin Veyra are built from linked cells on *other* pages
(`the_leaden_accord.md`, `fenspire.md`).

Logged as **F-032**.

**Decision: measure, disclose, do not fix**

Three days from the deadline, with the report and the video unwritten, this goes
into `docs/limitations.md` with a number attached and is not fixed. The
reasoning is F-031's, checked against F-030's counter-precedent rather than
assumed. **F-031 was itself fixed later the same day (ADR-029), its deferral
condition overridden by instruction** — so the precedent is being cited for its
*test*, not for its outcome. The test is whether a proof exists that the ripple
is safe:

- **The blast radius is real and unproven.** A fix moves the graph to 118
  entities and 264 edges. `tests/test_diagram.py` re-derives every number in
  `docs/diagrams/architecture.svg` from the live corpus and goes red; CLAUDE.md,
  README.md, `docs/architecture.md`, `configuration-example/README.md` and the
  report outline all quote 117/261; and the frozen 49-question harness result
  would need re-running to show no regression.
- **It changes no measured answer.** Nothing in `answer_key.json`, in the frozen
  55, or in the dev 1B seven traverses Halvard Cindervale.
- **No test proves this ripple safe.** F-030 overturned its own deferral
  because `test_diagram.py` *proved* the ripple safe, and ADR-029 overrode
  F-031's because a measured before-and-after sweep proved that one. Neither is
  available here without re-running `comparison.harness` and `eval.run_eval`,
  which is the cost, not the fix. Deferring an unproven change on a short
  calendar is not the same as deferring an inconvenient one — and if somebody
  wants it fixed, the route is the same one ADR-029 took: run the sweep first,
  and revert if any answer's correctness moves.

**The boundary is disclosed in the product, not only in the docs**

`EvidenceStatus.OUTSIDE_STRUCTURED_COVERAGE` already exists for exactly this
case, and Halvard Cindervale is already its canonical test fixture
(`tests/test_declines.py`, `Q_OUTSIDE`). Verified live through the UI engine:

```
Which faction won the war that Halvard Cindervale was a member of?
  -> outside_structured_coverage
     codex     tier 1  codex/the_annals_of_the_ashen_era
     ephemera  tier 4  contract_… .docx / contract_… .pdf / petition_… .scan.pdf
     wiki      tier 2  wiki/fenthrone.md, wiki/the_ashen_vanguard.md
```

The rendered page says *"Present in the corpus, absent from the graph"*, names
`src/graph/build.py` and *"wiki infobox rows only"* as the reason, and quotes
the passages with their tiers. A user who asks about the one unreachable entity
is told the truth about why, with citations they can open. That is the whole
argument for measuring this rather than guessing at it.

**One caveat on that, stated because it is not obvious.** The status only fires
where an evidence-unit scan is available. `python -m src.query.engine` does not
load evidence units and degrades the same question to `unresolved_entity`; the
demo UI's `Engine` loads them at startup, which is what `test_declines.py` pins.
Demo this from the UI, not from the bare CLI.

**What this does to ADR-027's claim**

It widens the base rather than overturning it. ADR-027 argued that the other
three collections corroborate but cannot build; this measures the node set that
argument depends on and finds the wiki bounds it almost exactly — 77 of 79
declared subjects reachable, the 78th a filename truncation, the 79th a one-row
defect of ours rather than a limit of the wiki. **The corpus does not carry a
population of prose-only entities that a relation extractor would have found.**
That is the evidence ADR-027 reasoned toward from `required_evidence` and could
not, on its own, supply.

*Status: accepted. 379 tests, 6 of them new (`tests/test_reachability.py`).
Graph untouched at 117/261, so `tests/test_diagram.py` and the architecture SVG
are unaffected and no eval sweep was re-run — no number moved.*

**AMENDMENT (same day, ADR-032).** The decision above — measure, disclose, do
not fix — was overturned on instruction, and the sweep it asked for was run:
`comparison.harness` and `comparison.ablations` byte-identical, `eval.run_eval`
scores identical, dev 1B 7/7 intact. The graph is now **118 entities, 265
edges** and the reachability number is **0 genuine gaps of 79**, not 1.

Two things in this ADR should be read as of its date rather than as current:

- The 579 unreachable spans are **578**, and the 77-of-79 is **78 of 79** -
  the 79th being the truncated filename, which was never a gap, so the count of
  genuine gaps is **zero**. Say 78 of 79 and then say why; "79 of 79" would be
  an overclaim of exactly the kind this ADR's own hand-check refused. The
  hand-check is unaffected — the same fifteen names, still 0 genuine entities.
- The claim that the boundary is "disclosed in the product" via
  `OUTSIDE_STRUCTURED_COVERAGE` **was true and is now true of something else.**
  Halvard Cindervale has a node, so he is no longer that status's example. It
  now fires on the 12 wikilink targets that have no node — all of them events,
  offices or documents rather than entities. ADR-032 records the measurement.

What this ADR got right and is worth keeping: the method, the hand-check that
refused to inflate 579 into an entity count, and the identification of the
*cause* rather than only the symptom. The fix was one row's worth of lexicon,
and it was findable only because the node set had been measured.*


## ADR-031 — A relation's question vocabulary is not its field names, and an answer-type noun is not a cue

**Problem**

`3h_002` — *"Which war was won by the faction that Hesper Wrenfield's mentor
belongs to?"* — was answered **Corvus Hollowmere the Pale**, a person, to a
question asking for a war. Measured cause, and it is not depth and not evidence:

```
gold chain    mentor_of -> member_of -> victor_of
exists in graph                       1 path
cued by the question   mentor_of, victor_of      MISSING: member_of
```

The chain is in the graph. `member_of`'s entire cue vocabulary comes from its
field names — `Members`, `Membership`, `Affiliation`, `Allegiance`, `Personnel`,
`Castellan` — and every one is a **record-keeping noun**. None is how a person
asks. "the faction that X **belongs to**" cued nothing, so the middle hop was
never a candidate and the tier walked one hop and stopped.

This is ADR-024's gap in a second relation. It was predicted there: *"any
relation whose name, inverse and field names share a stem has the same blind
spot, and the frozen set cannot detect it."*

**Decision**

`member_of` declares `cues: [belongs]`. One word.

**What we tried first, and what it cost**

`cues: [belongs, faction, group, organisation, organization]` — the obvious
version, all the words a person might use for a faction. **Measured, and
reverted:**

```
                    baseline    all five    [belongs] only
arm A answer_correct     10          9           10
arm A no_route_shape     36         37           36
arm C answer_correct     18         16           19
arm C ambiguous           6         11            8
```

It cost a correct answer in **both** arms. The cause is that `faction`, `group`
and `organisation` are **answer-type nouns**, not relation cues. *"Which faction
rules the place where the Pale Stag makes its lair?"* names a faction as the
thing it wants back, not as a relation to traverse — and under ADR-029's
coverage guard a newly-unique cue word makes templates **decline more**, so
`rb_041` stopped routing and lost an answer it had been getting right.

`belongs` is the discriminating word because it is relational in a way the
nouns are not: it can only describe a tie between two entities.

**The interaction worth writing down**

ADR-024 lets a relation declare cue words. ADR-029's guard counts only words
naming **exactly one** relation. Those two features are coupled in both
directions, and neither ADR said so:

- Adding a word that **collides** with an existing cue makes it shared, which
  drops it from `unique_relation_cues()` and **weakens** the coverage guard.
  `house` stems to `hous`, which is `housed_in`'s cue — it was a candidate here
  and was rejected for exactly this reason.
- Adding a word that is **unique** strengthens the guard, making templates
  decline on questions that merely contain it. That is what cost `rb_041`.

**So check collisions before adding any cue**, and re-run the harness rather
than reasoning about it. Three tests pin this: the shipped cue, the rejected
answer-type nouns, and `hous` still belonging to `housed_in` alone.

**MEASURED, isolated**

`config/relations.yaml` was the only file toggled between the two runs, so the
delta is the cue and nothing else:

```
                     baseline   with [belongs]
arm A  answer_correct    10          10     unchanged - 91% precision held
arm A  no_route_shape    36          36     unchanged
arm B                30/12/20    30/12/20   unchanged
arm C  answer_correct    18          19     +1
arm C  complete_evidence 28          31     +3
arm C  ambiguous          6           8     +2   <- the cost
```

`comparison.ablations` is byte-identical. `3h_002` now answers **The War of
Drowned Light** correctly; `3h_001` is unchanged and correct; `3h_003` is
unchanged at six values.

**A caveat on the absolute figures.** These runs were taken while F-032's fix
was in progress in the working tree, so the graph underneath them was 118
entities / 265 edges rather than the committed 117 / 261. The *delta* is valid —
only `relations.yaml` moved between the two runs — but **re-derive the
absolutes with `python -m comparison.harness` once F-032 lands**, per CLAUDE.md's
standing rule for exactly this number.

**What is still not fixed**

`3h_003` still returns six values as `fallback_ambiguous`. Its problem is the
opposite one: it is **over**-cued, because `plac` matches "place" and pulls in
`housed_in` and `serves_at` — the contamination ADR-029 documented. Two of the
three three-hop questions now answer correctly, and the third is a chain-
selection problem that lives where arm B's 40% precision lives. Not attempted
here.

*Status: accepted. 3 new tests. The +2 ambiguous is a real cost and is recorded
as one, not netted away against the +1 correct.*

## ADR-032 — The name lexicon reads wikilinks, so an unlinked cell can name a page-less entity

*Two sessions appended to this file concurrently on 6 Sep and both reached for
032. Settled as 032 here and 033 for the other; if a commit message or a stale
cross-reference says otherwise, this heading is the one to trust.*

**Problem**

F-032, measured by ADR-030. `build.py` resolves an unlinked infobox cell against
a lexicon of **page subjects only**, so a cell naming an entity that owns no wiki
page resolves to nothing. It is silent: the field *is* mapped, so
`unmapped_fields` never sees it; the target is not the page's subject, so
`self_references` never sees it. The row falls out of the loop at
`if not named: continue`.

Corpus-wide it bit twice, and one of the two cost an entity outright:

```
wiki/the_ashen_vanguard.md              | Members   | Halvard Cindervale; Voltaire Hollowmere; Orin Veyra
wiki/aldous_wrenfield_the_last_warden.md | Mentor of | Thessaly Coldwater
```

Halvard Cindervale is named in 21 evidence units — 5 in the tier-1 codex Annals,
8 across three ephemera documents titled after him, 8 in the wiki — and had **no
node**.

**The fix F-032 proposed does not work, which is why it was measured first**

F-032's own condition said "extend pass 1's `known` map with link-target names".
Measured: Halvard Cindervale is a `[[wikilink]]` target in **prose only**
(`fenthrone.md`, `the_ashen_vanguard.md`) and appears in **no infobox cell** as a
link. Adding infobox link targets alone puts Voltaire and Orin in the lexicon and
still not Halvard — and `_resolve_unlinked` is all-or-nothing, so the `Members`
row would still resolve to nothing and **the change would have done nothing at
all.** Writing the fix as specified and re-running the sweep would have produced
a green suite, an unchanged graph, and a closed failure-log entry that fixed
nothing.

**Decision**

The lexicon reads **every `[[wikilink]]` target on a wiki page, prose included**,
after page subjects so their spelling wins.

The line this does not cross is the one ADR-027 drew. **A wikilink is markup, not
prose.** It is the wiki declaring that a string names an entity, and this reads
it for *names* and nothing else. Every edge still comes from an infobox row;
`_resolve_unlinked` is unchanged and still demands a literal template, an exact
canonical-key match on the whole cell part, and all parts resolving or none.
This is not the prose relation extractor ADR-027 measured and rejected, and the
four recovered edges are the evidence: they came from rows the corpus had
already written, not from sentences we parsed for relations.

**MEASURED**

```
                          before      after
entities                     117        118
  page-backed                 95         95
  edge-only                   22         23
edges                        261        265
  member_of                   54         57
  mentor_of                    8          9
rows whose resolution changes            2   (measured before writing the fix)
```

`python -m eval.probes.entity_reachability`:

```
declared subjects            79         79
  reach a graph node         77         79
silent rows naming an entity the graph does not hold
                              1          0
```

**Proof it is safe, which is the whole reason this was allowed**

F-032 and ADR-030 both said this stays deferred until a sweep proves the ripple
safe. The sweep was run before and after — and then run **again**, because
another session committed a routing change (ADR-031's `belongs` cue) between the
two halves of the first run, which would have made the proof a comparison
against a superseded baseline. The second run was done in a throwaway
`git worktree` at `83948d9` with **only `src/graph/build.py` changed**, so
nothing else in the working tree could contribute to the result. Both runs
agree:

| Gate | Result |
|---|---|
| `python -m comparison.harness` | **byte-identical** |
| `python -m comparison.ablations` | **byte-identical** |
| `python -m eval.run_eval --checkpoint baseline` | scores identical (1B 2/7, 1C 2/2, 4/9) |
| dev 1B 7/7 (`tests/test_query.py`) | holds |
| `python -m src.graph.corroborate` | 255/261 → **259/265**, still 97.7% |

**All four new edges are corroborated.** That is the strongest single line here:
edges recovered by widening a name lexicon are not more speculative than the ones
already in the graph — the codex, chronicles and ephemera name both ends of every
one of them. `tests/test_corroborate.py` asserts it rather than leaving it as a
remark, so a future widening that invents edges the archive never mentions will
drop that figure and be seen.

**One answer moved, and it moved the right way.** *"Which war was won by the
organization that included Halvard Cindervale as one of its members?"* went from
`outside_structured_coverage` to `sufficient`. Pinned in `tests/test_query.py`;
it is the only user-visible gain and it should not be able to regress silently.

**What this costs: the canonical example of a decline**

Halvard Cindervale was `EvidenceStatus.OUTSIDE_STRUCTURED_COVERAGE`'s test
fixture (`Q_OUTSIDE`), and he is not an example of it any more. That is worth
stating rather than quietly re-pointing, because it changes what the status
*means* in the demo: there is no longer a **person** the graph fails to hold.

Measured what is left: 12 of the wiki's 119 distinct `[[wikilink]]` targets have
no node, and **none of them is an entity of a kind the graph types** —
`Sundering`, `Ley-ruins`, `Ashen Era` (events and periods); `Court Chronicler`,
`Quartermaster`, `Choir Novice`, `Sapper` (in-world offices); `Annals`, `Codex`
(the documents themselves); `Mournthrone`, `Sunder-Kings`, `Annals/Codex`.

`Q_OUTSIDE` is now *"Which faction won the war that Court Chronicler was a member
of?"* — an office the wiki wikilinks, named in all four collections, tier 1
through 4, including `codex/the_annals_of_the_ashen_era`, which is the document
the existing assertion already checked for. Every other assertion in that test
passes unchanged. **The status is more honest than it was**: it now fires only on
things the graph legitimately does not model, never on something it dropped.

**Why this was fixed now, having been deferred twice**

ADR-030 deferred it, and correctly: the deferral test this repo has settled on is
*"does a proof exist that the ripple is safe?"* — F-030 was overturned because
`test_diagram.py` supplied one, F-031 because ADR-029 ran the sweep. Neither
existed for F-032 at the time. This ADR is what supplies it. The instruction to
fix was explicit; the protocol F-032 named was followed exactly, including
measuring the proposed fix first and discovering it was wrong.

**Ripple, all of it in this commit.** `docs/diagrams/architecture.svg`,
CLAUDE.md, README.md, `docs/architecture.md`,
`configuration-example/README.md`, `ai_usage/ai-usage-disclosure.md`,
`docs/report-outline.md`, `docs/limitations.md`, `tests/conftest.py`, and the
counts pinned in `test_diagram.py`, `test_corroborate.py`, `test_declines.py`
and `test_reachability.py`. `tests/test_diagram.py` went red on the stale SVG the
moment the count moved, which is the design working.

*Status: accepted. 386 tests, 1 of them new here. `docs/limitations.md` keeps the
entry, rewritten from "one entity has no node" to the completeness claim and the
12 concepts that remain outside — the boundary did not disappear, it moved to a
place where it is the correct boundary.*


## ADR-033 — A cue word that names one relation outranks one that names several; a shared word is a fallback, not a veto

**Problem**

`3h_003` — *"Which faction rules the place where the relic wielded by Halvard
Vane the Grave-Sworn was forged?"* — returned **six values** as
`fallback_ambiguous`. Its gold chain is three relations; the question cued
**five**:

```
gold chain             wields -> forged_at -> ruled_by      exists, 1 path
cued                   forged_at, housed_in, ruled_by, serves_at, wields
```

`housed_in` and `serves_at` are spurious, and both arrive from the same word.
`Place of forging`, `Place of housing` and `Place of service` all reduce to the
stem `plac`, so the ordinary noun **place** cues three relations at once. This
is the vocabulary contamination ADR-029 documented, reaching chain *selection*
rather than the coverage guard.

**Decision**

In `cued_relations`, a relation named by a **unique** cue word (one naming
exactly one relation) is preferred. Shared words are consulted only when no
unique word names anything.

`unique or named` — one line. The `or` is the whole design.

**Why a fallback and not a filter**

Dropping shared words outright was measured first and is wrong. It changes 15 of
55 frozen questions and reads **three of them down to no cue at all**, because a
shared word is the only one they carry:

```
rb_003  "...What place holds it?"                    plac only
rb_040  "Who prevailed in the conflict where..."     conflict only
rb_055  "Which faction does the Marsh Revenant serve?"  serv only
```

Where unique words name nothing, the shared ones are all the evidence there is.
A test pins both `rb_003` and `rb_055` keeping their full cue sets.

**MEASURED** — `src/query/fallback.py` was the only file toggled between runs:

```
                       before    after
arm A  answer_correct     10       10     unchanged - templates untouched
arm A  no_route_shape      36       36     unchanged
arm B                  30/12/20  30/12/20  unchanged (its own cue router)
arm C  answer_correct      19       21     +2
arm C  complete_evidence   31       29     -2
arm C  ambiguous            8        4     halved
arm C  unnecessary_depth    4        0     eliminated
honest refusal (of 6)       5        6     +1
```

`comparison.ablations` is byte-identical.

**All three three-hop questions now answer correctly.** `3h_003` returns **The
Ashen Vanguard**, a single value, where it returned six.

**The -2 complete evidence is real and is not netted away**

Per question, nothing lost correctness. Three gained it (`rb_021` gaining
complete evidence with it, `rb_047`, and `rb_054` — an *unanswerable* question
that now declines instead of guessing, which is why honest refusal reached 6 of
6). Three lost complete evidence only: `rb_005`, `rb_044`, `rb_045`.

Those three were earning it by **breadth**. Walking five cued chains touches more
documents than walking three, and some of the extra ones happened to be
required. Narrowing to the relations the question actually names loses that
accidental coverage. `answer_key.json`'s own convention already calls this out —
*"a right answer reached without the required evidence is a retrieval failure"* —
and the mirror holds: required evidence reached by walking chains the question
never asked for is not retrieval either. The lower number is the more honest one.

**Where this leaves the three-hop set**

Both three-hop failures were vocabulary, in opposite directions: `3h_002`
under-cued (ADR-031), `3h_003` over-cued (here). Neither needed a prose
extractor, a corpus change, or the LLM planner — the chains were in the graph
the whole time, each with exactly one path. That is worth stating in the report
next to the planner's own status, because it is evidence about where this
system's remaining errors actually live.

*Status: accepted. 386 tests, 3 new. Absolute figures were measured while
F-032's fix was uncommitted in the working tree (graph 118/265); the deltas are
isolated to this file, but re-derive the absolutes with
`python -m comparison.harness` once that lands.*

## ADR-034 — Prose relations are an independent check on the infobox mapping, not a source of edges

**The question ADR-027 and ADR-030 left between them**

ADR-027 measured *existing edges* (255 of 261 attested outside the wiki).
ADR-030/032 measured the *node set* (78 of 79 declared subjects reachable, the
79th a filename truncation, so 0 genuine gaps). Neither asked whether the codex,
chronicles or ephemera assert a **relation** that no infobox row produced.

ADR-027 rejected a prose relation extractor partly on the grounds that "the 4
wrong answers name only wiki pages in `required_evidence`" — and ADR-030 already
recorded that this is partly circular, because `required_evidence` was derived
from the wiki-built graph. This ADR closes that gap by measuring directly.

**Method**

`eval/probes/prose_relations.py`, read-only:

    python -m eval.probes.prose_relations

Twelve verb patterns, each mapping to a relation `config/relations.yaml`
already defines — the probe never invents a relation name, because an edge under
a relation nothing else uses is an edge no template can traverse. Entities
resolve through `corroborate.scan_surfaces`, which is `route.py`'s gazetteer, so
the surface forms are byte-identical to the ones the answer path recognises and
ADR-011 holds unchanged. Every candidate is classified against the built graph
as CONFIRMS / INVERTED / NEW.

**MEASURED**

```
182 raw candidates in codex / chronicles / ephemera
    CONFIRMS : 158      prose restating an edge the graph already holds
    INVERTED :  15
    NEW      :   9      (7 distinct triples)
```

All 7 distinct NEW triples were hand-checked against the documents that state
them. **6 of 7 are correct extractions; 1 is a false positive** — "In The Purge
of Blackport, Maelis Greyfen fought for House Morvain" yielded
`belligerent_in house_morvain`, a faction where a conflict belongs. That is the
two-argument ternary ADR-010 describes, and both of its correct edges already
exist.

A first pass without guards scored **2 of 12**. Three guards, each a measured
failure mode, took it to 6 of 7: a pronoun between subject and verb (anaphora —
F-009's lesson in a new place), a coordinating conjunction between subject and
verb (the verb heads a second predicate: "Halvard Cindervale is a member of The
Ashen Vanguard **and serves at** Fenthrone" yielded `ashen_vanguard serves_at
fenthrone`), and an object more than 40 characters past the verb. Every guard
**declines** a candidate rather than repairing it.

**What the 6 turned out to be — and this is the finding**

Only **2** are facts the graph lacks entirely: `vharenford ruled_by
ashen_vanguard` and `corvus_duskbane serves_at vharenford`, both tier-1 codex.

The other **4 are relation-typing errors in `config/relations.yaml`**. The graph
held the same entity pair under the wrong relation:

| Wiki row | Was | Prose says | Now |
|---|---|---|---|
| `the_winter_reckoning.md` `Notable fighter` | `member_of` | "fought in The Winter Reckoning" | `belligerent_in` |
| `the_leaden_accord.md` `Known participant` | `member_of` | "fought in The Leaden Accord" | `belligerent_in` |
| `palewell_abbey.md` `Serving figure` | `member_of` | "serves at Palewell Abbey" | `serves_at` |
| `sabelle_….md` `Military service` | `serves_at` | "Fought for … in …" | `belligerent_in` |

The graph asserted `brannoc_palefroth member_of winter_reckoning`: membership in
a war. The field names sit on pages that are not factions — a war, an accord, an
abbey — so the cell was never recording membership. Each of the four field names
occurs **exactly once** in the corpus, so the blast radius was four rows,
checked before the move.

**Decision**

Fix the four mappings. Do **not** ingest prose into the graph: the two genuinely
new edges do not justify a new parser, schema normalisation and the
re-derivation cascade, three days out. The probe ships as a measurement.

**The sweep, run before and after per ADR-029's protocol**

```
                        before   after
answer_correct (C)          21      22
complete_evidence (C)       29      31
route_success (C)           33      34
no_route_shape (C)          14      13
graph                  118/265  118/265     labels moved, nothing created
eval.run_eval                     identical
templates-only arm (A)            identical
```

`comparison.ablations` moved with the cue tier: `as_written` precision 40% → 45%.
Graph counts are unchanged, so `tests/test_diagram.py` and the architecture SVG
are unaffected. 395 tests green.

**One question regressed, and it was right for the wrong reason (F-033)**

`rb_011` — "Which figures counted themselves among the victors of the War of
Drowned Light?" — went from `fallback_ambiguous` **correct** to
`fallback_sufficient` **wrong**, returning the winning faction where the question
asks for people.

The cause is not the relation fix. `Serving figure` contributed the token
**"figure"** to whichever relation it was filed under, and the question contains
"figures". Filed under `member_of`, that accidentally cued `member_of` — the
relation that answers the question, for a reason having nothing to do with
membership. Moving the field moved the accident with it. Adding "figure" to
`CUE_STOPWORDS` does not restore the answer; only the accidental cue did.

**This is kept rather than reverted**, and the reasoning is the project's own:
an answer produced by an accident of vocabulary is not a capability, and
`member_of`'s cue vocabulary being too thin to route this question honestly is
the real defect. The regression is in the shape this project treats as worst —
a decline becoming a confident wrong answer — so it is recorded here rather than
netted off against the +2. **Revisit condition:** if `member_of` gains a
legitimate cue that routes `rb_011`, re-run the sweep and expect 23.

*Status: accepted. 395 tests. Two existing tests updated, both pinning facts
that legitimately changed: "military" now names one relation, and rb_055's cue
set narrowed to `{serves_at}` while still answering correctly.*

## ADR-035 — Which folders build the graph is config, not code

**The failure this fixes, measured before it was fixed**

The final round requires adapting the solution to requirements announced on the
day, so "can this read a corpus we did not build?" was tested rather than
assumed. A synthetic replacement archive — new entities, same conventions —
ingested and built a graph with **zero code changes**, and answered 2 of 3
two-hop questions correctly with full evidence chains. The one miss was
`no_template_match`, consistent with the 35-of-49 no-route-shape figure.

Then the same corpus with its folders renamed to `manuals/`, `specs/`, `logs/`:

```
INGEST: 10 docs, 18 units   collections seen: {manuals: 16, specs: 1, logs: 1}
GRAPH:  0 nodes, 0 edges
```

Ingestion was perfect. Every file was read, every collection assigned correctly.
`build.py` filtered on the literal string `"wiki"`, so nothing matched and the
graph came out empty — **silently**. `corroborate.py` held the same problem in a
frozenset of three literal names.

That is the worst failure shape this project recognises. Not a wrong answer, not
a decline: a system that reads every file, answers nothing, and reports no
problem. A corpus with different folder names and a corpus with no infoboxes at
all were indistinguishable from the outside.

**Decision**

`sources.builds` and `sources.corroborates` in `config/relations.yaml`, beside
the field-name vocabulary that is already there. ADR-005's reason, unchanged: a
collection name is a claim about the corpus, not a fact about the code, and a
judge should be able to disagree with one line without touching Python.

Two guards come with it, because a config key that can be wrong silently is no
better than a literal that was:

- **A collection may not be in both lists.** An edge parsed from a page is not
  corroborated by that same page (ADR-027). Raised, not resolved — either
  resolution would be a guess at what the editor meant.
- **A build that matches no collection raises, naming what the corpus has.**
  The person reading that error is holding a corpus they did not create and has
  no reason to guess that a folder name is the problem, so the message says so:

```
No evidence in any building collection ['wiki']. The corpus has:
['logs', 'manuals', 'specs']. Set `sources.builds` in config/relations.yaml
to the collection that carries infoboxes.
```

**MEASURED after the change**

```
renamed corpus, config untouched   -> raises, naming manuals/specs/logs
renamed corpus, two-line config edit -> 7 nodes, 12 edges
shipped corpus                     -> 118 nodes, 265 edges, unchanged
comparison.harness                 -> byte-identical to before the change
```

400 tests, 5 of them new (`tests/test_sources.py`). Graph counts unchanged, so
`tests/test_diagram.py` and the architecture SVG are unaffected.

**What this does and does not buy**

It buys one thing precisely: a corpus whose folders are named differently is now
a config edit rather than a code edit, and a corpus that cannot build says why.

It does **not** make the system corpus-independent, and the report must not
claim that. Three constraints remain, all still real:

- The parser takes the **first pipe table** on a page as the infobox. A wiki
  using YAML frontmatter or HTML tables still builds zero edges.
- Node type comes from the **image filename taxonomy**
  (`plate_<NN>_<category>_<subject>.png`).
- New scanned PDFs need fresh OCR, and Gemini's free tier is ~20 requests/day
  **per model** — a daily cap backoff cannot recover from.

The honest claim is "the relation vocabulary and the source collections are
both config", not "it adapts to anything".

**One caveat on the evidence, stated because it is easy to overclaim**

The synthetic corpus was written by us, so it used our conventions — a wiki-like
folder of pipe-table infoboxes. It demonstrates that no entity name, document
name or corpus fact is compiled into the logic (verified separately: every
corpus-specific proper noun in `src/` is in a docstring). It does **not**
demonstrate that an arbitrary third-party corpus works, and the folder-rename
result above is exactly what happens when one assumption of ours goes unmet.

*Status: accepted. 400 tests. The graph, the harness and the eval are unmoved;
this ADR changes what happens to a corpus we have not seen, not to this one.*

## ADR-036 — A corpus reload is a button, the cache has a fingerprint, and an added file is not drift

**The question**

The final round requires adapting to requirements announced on the day. If a
judge drops a document into the corpus, does the system pick it up? Measured
rather than assumed, and the answer had three parts, two of them defects.

**MEASURED before changing anything**

```
new documents, rebuilt      2 wiki + 1 codex file: 7 -> 8 nodes, 12 -> 15 edges,
                            and a two-hop question routed through both new files
                            and answered with per-hop citations
running server              does NOT pick them up - Engine.__init__ builds once,
                            no watcher, no reload, no mtime check
full cold rebuild           6.3s on the real corpus
                            (ingest 5.0s, graph 0.2s, corroboration 1.2s)
```

**Decision 1: a reload endpoint, not a file watcher**

`POST /reload` (and `GET /reload`, because a judge may reach it from the address
bar and a 405 in that moment reads as broken) rebuilds into locals and swaps
under a lock, so a failed reload leaves the previous corpus serving rather than
a half-built one. `Engine._lock` exists because the server is a
`ThreadingHTTPServer` and a question must not traverse a half-swapped graph.

A watcher was rejected: it is a race condition to debug and a background thread
to explain, three days from a deadline, and 6.3s is inside the time it takes to
ask "does it pick that up?". **Explicit beats magical when a judge is watching**
— they can see the machine do the work rather than trust that it did.

The result page prints before/after counts rather than reporting success:
"it reloaded" is a claim, "7 → 8 entities" is evidence. It also surfaces
`unmapped_fields`, because a reload is exactly when new vocabulary arrives and
the fix is a line of `config/relations.yaml`, not code.

**Verified end to end**

```
startup    7 entities, 12 edges
ask        "To which vault must one journey to examine the relic long borne by
            Sabine Trawley?"  ->  unresolved_entity
           [a file is added to wiki/]
reload     0.05s   7 -> 8 entities, 12 -> 13 edges, 16 -> 18 units
ask        same question  ->  sufficient, "Kestrel Vault"
```

**Decision 2: the ingestion cache gets a fingerprint**

`ingest_cached()` returned `.cache/corpus.v1.json` whenever the file existed —
no mtime, no hash, no fingerprint. **It was correct only by luck**, and the luck
was verified: fresh and cached ingests were byte-identical on 6 Sep, same 30,553
units, same ids, zero text differences.

The luck runs out the moment a document is added — the very scenario above.
`tests/test_diagram.py` asserts file counts, evidence-unit counts and
corroboration counts *through that function*, and all three change when a
document is added. A stale cache would have kept the suite that exists to stop
the architecture diagram going stale green, while asserting pre-drop numbers.
Same failure class as ADR-035's folder-name literal: correct by luck, silent
when the luck runs out.

`corpus_fingerprint()` hashes every file's path, size and mtime; a mismatch
rebuilds. Path/size/mtime rather than contents because hashing 123 MB on every
launch would cost more than the 5s ingest the cache exists to avoid;
`python -m src.ingest.integrity` remains the content check, as a deliberate
separate step.

**Decision 3: an added file is not drift**

The integrity checker printed the same message for a missing file, a modified
file and an added one:

> CORPUS DRIFT: ingestion would read files that are not the shipped archive.

So the system's first response to a judge's own document was to report it as
drift. The check is unchanged; what it says about the added-files case is not.
`CORPUS DRIFT` is now reserved for **missing or modified** files — the actual
F-016 shape, where an editor rewrote 36 files. Added files report "corpus has
grown … reindex to include them", and still say the measurements are no longer
comparable, because they are not.

`tests/test_ingest.py` pins both halves: added files must not say CORPUS DRIFT,
modified files must.

**Cost**

421 tests, 11 of them new. `comparison.harness` byte-identical. No graph
counts moved, so `tests/test_diagram.py` and the architecture SVG are unaffected.

**What this does not claim**

The system still does not update *automatically*, and the report should say so
in those words. It updates in about six seconds when asked, and it now tells you
what changed when you ask. A new scanned PDF still needs OCR under Gemini's
~20/day per-model cap, and no button fixes that.

*Status: accepted.*


---

## ADR-037 - The answer is a statement, and the sentence was already being written and thrown away

**Problem**

The demo's Answer panel showed a bare entity name - `The Bleeding Crown` - and
nothing else. For a sub-track whose whole subject is *connecting facts across
documents*, the one thing the headline did not convey was the connection. A
judge had to read the evidence path and reconstruct the join themselves.

Two separate causes, and the first was embarrassing:

1. **The sentence already existed and never reached the page.**
   `src/query/synthesis.py` has phrased answers since ADR-020.
   `src/ui/server.py` computed one on every request and wrote it into the view
   as `view["prose"]`. `src/ui/render.py` **had no block for it** - `grep -n
   prose src/ui/render.py` matched one unrelated word in a decline caption.
   Every demo answer since then discarded a sentence it had already paid for.

2. **The deterministic phrasing was a data dump, not a statement.** It rendered
   `"<values>. Route: A -> B -> C. Sources: ..."`. Measured on `1b_006`, which
   has fourteen answers reached the identical way, that produced **fourteen
   near-identical arrow chains inside one sentence**, 1,100 characters, with
   `The Silent Choir` repeated fourteen times. A reader also had to decode what
   `->` meant at each hop, which differs per relation.

**Decision**

*Render what synthesis produces*, and make what it produces readable.

`build_view` now takes the `Synthesis` as a parameter rather than the server
bolting three keys onto the returned dict, so `prose`, `phrasing` and
`phrasing_model` are always present and `render.py` never guesses whether a key
exists. A caller that phrases nothing gets `None` and no block renders.

`template_sentence` words each hop in **the direction the chain walked it**,
from a 15-entry relation phrase map, and states routes sharing a prefix once:

    before  The Bleeding Crown. Route: Gravemaw Wyrm -> Marrowwell Abbey ->
            The Bleeding Crown. Sources: ...

    after   The Bleeding Crown. Gravemaw Wyrm has its lair in Marrowwell
            Abbey, which is ruled by The Bleeding Crown. Sources: ...

    1b_006  before: 14 arrow chains, ~1,100 chars, "The Silent Choir" x14
            after:  one statement, "The War of Drowned Light was won by The
                    Silent Choir, which counts among its members those 14"

Direction matters and is not cosmetic: `1b_006` walks `victor_of` *backwards*,
from the war to the faction that won it. Phrasing it forward would assert that
the war won the faction. `test_a_reverse_hop_is_worded_in_the_direction_it_was_walked`
pins that.

**A conflict names its disputed hop.** `1b_009`'s sentence previously stated
the contested hop ("The Purge of Blackport was won by The Iron-Ring Cartel") as
flatly as the uncontested one, leaving the caveat stranded in the lead with
nothing to attach to. It now adds: *"The disagreement is over whether The
Iron-Ring Cartel is named victor of The Purge of Blackport:
wiki/the_purge_of_blackport.md asserts it, and wiki/the_iron_ring_cartel.md
declines to."* Both sides named, neither preferred - every value read off the
report `conflict.py` already produced.

**Why this does not breach ADR-018**

ADR-018 says the UI composes no answers, and it still composes none. The
sentence is written in `src/query/` from a chain that was already routed,
walked, filtered and conflict-checked; `render.py` escapes it and puts it in a
box. The three thinness tests are untouched and green.

The related ADR-018 statement - that the page does *not* write `1b_009`'s
sentence and instead shows both sides - is **narrowed, not reversed**. The
evidence trail, the conflict panel with both tier-2 sources, and the bare value
all still render underneath, so the sentence is checkable against the rows that
produced it rather than standing in for them. What changed is that a reader is
no longer required to do the join themselves before they can see what was
found.

**The default stays deterministic**

Phrasing has two paths and the keyless one is the default, unchanged by this
ADR. `--with-model` opts in. Both were verified live:

```
template  The Bleeding Crown. Gravemaw Wyrm has its lair in Marrowwell Abbey,
          which is ruled by The Bleeding Crown. Sources: ...

model     The Gravemaw Wyrm's lair is located in Marrowwell Abbey
          (wiki/gravemaw_wyrm.md, field 'Lair'). Marrowwell Abbey is ruled by
          The Bleeding Crown, so the dominion that encompasses the lair belongs
          to The Bleeding Crown (wiki/marrowwell_abbey.md, field 'Ruled by').
          [nvidia/nemotron-3-super-120b-a12b:free]

model, on 1b_009: "...yet the cartel source denies that it was the victor,
          indicating a disagreement between the sources." - it did not pick a
          side, which is what `_CONFLICT_STATUSES` instructs.
```

The model reads better and the template is now good enough that losing it costs
prose polish rather than comprehension. That is deliberate: CLAUDE.md's "never
record the demo against a cold cache" applies to the sentence as much as to the
answer, and a demo whose headline degrades to gibberish when the network drops
is a demo with a single point of failure. `phrasing` is rendered on the page,
so a judge asking "did an AI write this?" reads the answer rather than the
source.

**Measured result**

```
11 new tests, 432 total (was 421).

  every relation that produces edges has a phrase   15/15
  1b_013  one clause per hop, no arrows
  1b_006  14 answers, "The Silent Choir" stated once (was 14x)
  1b_009  dispute named, both documents cited, no side taken
  keyless run renders `template` + "no model, no API key, no network"
  a view with no synthesis renders no prose block and does not raise
```

**Trade-offs**

The phrase map is 15 hand-written pairs in `synthesis.py` rather than in
`config/relations.yaml` beside ADR-024's `cues:`. The distinction is
deliberate: `cues` change *what gets answered* and belong where a judge can
argue with them; these change only how a finished answer is worded and cannot
affect retrieval. If that judgement is wrong the move is mechanical, and
`test_every_relation_in_the_graph_has_a_phrase` keeps the map honest either way.

*Status: accepted, validated by 11 tests, a live run of both phrasing paths, and
the three ADR-018 thinness tests still passing.*


---

## ADR-038 - One answer box, and every audit surface one click behind it

**Problem**

ADR-037 put a phrased sentence on the answer page. ADR-026 put partial evidence
on every decline. ADR-027 added attestation. Each was right on its own and the
result was a page with ten stacked open panels, where the thing a reader wanted
- the answer - was one card among ten and the sentence was immediately followed
by a bullet list repeating the same values.

For a submission, that reads as an engineering artefact rather than a product.
The evidence has to remain reachable in one click, because being able to check
every hop is the entire claim; it does not have to be the first thing on screen.

**Decision**

*The answer section is the sentence, and nothing else.* The duplicate value list
is gone when a sentence exists - the sentence already states the values, and
they are now emboldened inside it. The bare list survives only as a fallback for
a caller that passes no synthesis, so a page can never show neither.

*Four surfaces collapse:* Strategy used, Evidence sufficiency, Evidence path,
Source documents and tiers. `<details>`/`<summary>`, so no JavaScript and no
dependency - the same constraint `graphview.py` works under.

*Two things refuse to collapse, and the exceptions are the point:*

| Case | Behaviour | Why |
|---|---|---|
| A surfaced conflict | open | A same-tier contradiction a reader must click to discover is one the demo did not surface. `1b_009` exists to prevent exactly that |
| A decline | Evidence sufficiency open, partial-evidence blocks not collapsed at all | The named reason *is* the result when there is no answer. Collapsing it would undo ADR-026 and restore the "looks like a crash" failure it was written to fix |

*Citations set small and italic* (`.cite`), matched in three shapes because
three writers produce them - the model brackets with U+3010/3011, or
parenthesises, and `template_sentence` writes bare paths after "Sources:". A
citation should be checkable without competing with the sentence for attention.

*The phrasing provenance moves behind a disclosure* - still present, still one
click away, no longer a paragraph of explanation above the fold.

*The footer is deleted.* It read "Checkpoint 2 - deterministic engine, no LLM in
this path", which stopped being true when ADR-037 rendered model phrasing.

**Emboldening is a join, not a judgement**

The bold strings are `view["values"]` - what the engine returned. `_bold_values`
applies them to text runs only, never inside a tag or a citation, longest first
so "Corvus Hollowmere the Pale" is not half-matched by "Corvus Hollowmere".
`test_nothing_the_engine_did_not_return_is_emboldened` asserts the set of
emboldened strings is a subset of the engine's own values, and
`test_the_page_renders_the_phrased_sentence_with_its_provenance` strips the
markup back out and compares to the original sentence character for character -
so this can add emphasis and can never edit prose.

ADR-018's three thinness tests are untouched and green.

**Measured result**

```
9 new tests, 443 total (was 434).

  answered   1 answer card, 4 collapsed surfaces, values bold in the sentence
  1b_009     conflict panel open without a click, both tier-2 sources visible
  decline    evidence sufficiency open, partial-evidence blocks open
  no page contains "Checkpoint 2" or "no LLM in this path"
```

**Two bugs found while writing it, both from escapes eaten before they landed**

`content: "\25B8"` for the disclosure triangle rendered as a control character
followed by "B8": the CSS lives in a non-raw Python string, where `\25` is an
*octal* escape. The glyph is now written literally. Separately, a `\b` in the
citation regex reached the file as a literal backspace byte (0x08) and silently
matched nothing, so bare `Sources: wiki/...` paths were never marked - a regex
that fails open looks like it works. Both are the same lesson: an escape that
passes through two layers of quoting should be verified against behaviour, not
against the source reading correctly.

**Trade-offs**

A judge who wants the evidence now clicks for it. That is the right default for
a five-minute demo and the wrong one for an auditor, so nothing was removed and
nothing was made conditional - every surface renders exactly as before, one
`<summary>` away. If the video needs a panel open on camera, adding `open` to
`_details` is one argument.

*Status: accepted, validated by 9 tests and a live pass over an answered
question, a conflict and a decline.*


---

## ADR-039 - The path, stated once, on one line

**Problem**

The evidence path rendered every hop with its full provenance - document,
field, row, parsed-by, raw cell, attestations. That is what makes an answer
checkable and none of it is negotiable. But it is five or six lines per hop,
and the question a reader asks first is not "which row was this read from", it
is **what was joined to what**. That was the one thing the section never said;
you had to assemble it from the hop blocks yourself.

ADR-038 then collapsed the section by default, which made the gap worse: the
join was now behind a click *and* still had to be reconstructed once you got
there.

**Decision**

One line per route, in the order the chain was walked:

    Gravemaw Wyrm -> lair_in -> Marrowwell Abbey -> ruled_by -> The Bleeding Crown

Rendered above that route's hop blocks, with the endpoint marked so the eye
lands on the answer, and the relation pill coloured red where the engine
flagged that hop disputed - `1b_009`'s `victor_of` is contested and its
`member_of` is not, and a one-line summary that flattened those together would
be a worse lie than not having one.

**With exactly one route, the chain also becomes the collapsed header.** The
section reads `Evidence path - The Purge of Blackport -> victor_of -> The
Iron-Ring Cartel -> member_of -> Halvard Crowhurst` before anything is opened,
so the join is visible at a glance and the provenance is one click behind it.
With fourteen routes (`1b_006`) the header stays generic, because fourteen
chains in a `<summary>` would not fit and would not help; each route states its
own chain inside instead.

**It is read, not reassembled.** `_chain_line` walks `route["hops"]`, which the
view built from the engine's own `Path`. Hop N's target is hop N+1's subject by
construction, so the line cannot disagree with the blocks beneath it.
`test_the_chain_follows_the_engines_own_hop_order` rebuilds the expected string
from the same hops and compares.

**Measured result**

```
5 new tests, 448 total (was 443).

  1b_013  Gravemaw Wyrm -> lair_in -> Marrowwell Abbey -> ruled_by ->
          The Bleeding Crown, in the collapsed header and in the route card
  1b_009  victor_of marked disputed, member_of not
  1b_006  14 chains, one per route; header stays generic
```

**One test changed, and why that was right**

`test_every_required_surface_is_present_for_a_conflicted_answer` asserted the
literal words "source passage" as its proxy for surface 5. A single-route answer
now puts its chain in that header, so the phrase moved - while every passage was
still on the page. The test now asserts `class="passage"`, the markup that
actually carries the surface. A test that checks a label is testing the label.

*Status: accepted, validated by 5 tests and a live pass over an answered
question, a conflict and a fourteen-route answer.*


---

## ADR-040 - A visible busy state, and the first JavaScript in the project

**Problem**

Submitting a question gave no acknowledgement at all. The page is a plain GET
and the browser sits on the old document until the response arrives, so a user
who clicked Ask could not tell the difference between "working" and "my click
did not register" - and the natural response to that is to click again.

Measured on the running server: a cached or fully deterministic answer returns
in **~11ms**, which needs no indicator. The case that actually feels dead is
`--with-model` on a question nobody has asked before, which waits on one
OpenRouter round-trip. So the problem is real and concentrated in exactly one
path.

**Decision, and the constraint it crosses**

`graphview.py` renders 117 entities with no script and no CDN, and that has been
a stated property. This adds **one inline `<script>`, about fifteen lines**, and
the distinction that makes it acceptable is narrow but real:

> The script changes nothing about what the server does or what the page says.
> With scripting off the form submits exactly as it always has and the message
> never appears. It is feedback about a request already in flight, not
> behaviour any result depends on.

The invariant worth pinning was never "no JavaScript" - it is **no dependency
and nothing fetched**. That is now asserted explicitly: exactly one `<script>`
tag, no `src`, and no `http://`, `https://`, `cdnjs` or `unpkg` anywhere in
either page.

**The message names the slow part**

Two wordings, because only one is true at a time:

    deterministic   "Searching the archive..."
    --with-model    "Searching the archive... phrasing with a model can take
                     a few seconds"

Promising a wait for a model that will never be called would be the page lying
about its own architecture, and CLAUDE.md's rule is that an LLM call is visible
and counted rather than hidden inside a spinner. The flag is the server's own
`use_model_phrasing`, plumbed into `page_index` and `page_answer` - it cannot be
read off a result, because the message has to be right *before* the request is
sent.

**Two browser details that are not incidental**

- The submit button is disabled on a `setTimeout(..., 0)` rather than inline.
  Disabling a submit button *inside its own submit handler* cancels the
  submission in some browsers, which would turn a loading indicator into a
  page that genuinely does nothing.
- `pageshow` resets the label and the disabled flag. The back button restores a
  page from the browser's cache with the button still disabled and still
  reading "Searching" - which looks exactly like the hang this exists to
  prevent.

The spinner is CSS, and honours `prefers-reduced-motion`.

**Scope**

The Ask form only, on both pages. The dev-question links, the 117 entity links
and the Reindex button are plain navigations that were considered and left
alone for now - the entity and question links hit the ~11ms deterministic path,
and Reindex is a separate case worth its own treatment.

**Measured result**

```
6 new tests, 454 total (was 448).

  form still carries action/method and an enabled button (works with JS off)
  exactly one script tag, no src, no remote host on either page
  wording differs correctly between --with-model and deterministic
  pageshow reset present; disable is out-of-band
```

**Two tests changed, and why neither was a loosening**

`test_index_page_offers_autocomplete_and_a_browsable_list` asserted
`"<script" not in html`. That was pinning "no JavaScript", which is no longer
the property; it now asserts one inline script and nothing fetched, which is
stricter about the thing that matters.

`test_every_dynamic_value_is_escaped` asserted `"<script>" not in html` as its
XSS check, which the page's own script broke. The property was never "the page
contains no script" but "nothing a user typed becomes markup", so it now
asserts the hostile input appears escaped, appears nowhere unescaped, and that
every script on the page is the renderer's own. That is a stronger test than
the substring it replaced.

*Status: accepted, validated by 6 tests and a live check of the busy state in a
browser.*


---

## ADR-041 - A phrased answer may not quietly drop answers the engine returned

**Problem**

Reported from the running demo, and reproduced: asked `1b_006` - "Which
individual was a member of the faction that ultimately won the War of Drowned
Light?", which has **fourteen** equally valid answers - the page displayed:

> **Corvus Hollowmere the Pale** was a member of The Silent Choir, which won
> the War of Drowned Light *(source: wiki/the_war_of_drowned_light.md, field
> 'Victor')* *(source: wiki/corvus_hollowmere_the_pale.md, field 'Membership')*

One of fourteen, phrased as though it were the answer, with two correct
citations attached. Measured:

```
engine values                : 14
model prose named            :  1 / 14
values list rendered on page : False
```

Two independent defects, and the second is the serious one:

1. The model was handed all fourteen paths and phrased one. The hops were all
   in the prompt; nothing in it said the endpoints were a *set*.
2. **ADR-038 had removed the value list whenever prose was present**, on the
   reasoning that the sentence already states the values. True for one answer,
   false for fourteen - and it deleted the only thing on the page that would
   have exposed the omission.

A confident, well-sourced, incomplete answer is precisely the failure this
project exists to prevent, and presentation had removed the check that caught
it. See F-034.

**Decision**

*Tell the model the endpoints are a set.* When `len(values) > 1` the prompt now
carries, above the chain, `This question has N answers, ALL equally valid. Your
sentence must name every one:` followed by the list, plus a standing rule that
naming a few and stopping presents one answer as the answer.

*And do not rely on that.* `_unstated_values_block` compares the rendered
sentence against the engine's own `values`. Any value the sentence does not
name is listed, under a plain statement - "The sentence above names 1 of 14
answers" - so an omission is visible on the page rather than inferred from a
route count further down. A sentence that names all of them renders alone,
which keeps ADR-038's clean single-box layout wherever it is honest.

The guard checks a string against values the engine produced. It does not
decide what the answer is, re-rank anything, or edit the sentence - it decides
whether the *display* is complete, which is presentation's own business.

**Measured result**

```
Prompt fix, verified live against the model:

  before   1 / 14 values named, no correction on the page
  after   14 / 14 values named, each individually cited, guard correctly silent

Guard, verified deterministically with a synthetic one-of-fourteen sentence:

  "The sentence above names 1 of 14 answers" rendered, all 14 listed

5 new tests, 459 total (was 454).
```

**Why both halves, when the prompt fix worked**

Because the prompt fix is a request and the guard is a check. The model
complied this time on this question with this rotation head; none of those are
guaranteed next week. The guard costs one string comparison and turns a silent
under-report into a visible one, which is the same trade the whole evidence
trail makes.

**Trade-offs**

The guard is substring matching, so a sentence that refers to a value without
naming it exactly ("all fourteen members") would trip it and show a list that
is arguably redundant. That is the right direction to fail: a redundant list
costs a reader three seconds, and a missing one cost this demo thirteen
answers.

*Status: accepted, validated by 5 tests, a live model run naming 14/14, and a
deterministic check of the guard itself.*

