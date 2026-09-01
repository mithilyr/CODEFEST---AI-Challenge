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

`src/ui/graphview.py` draws all 117 entities and 267 edges as one static SVG:
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
