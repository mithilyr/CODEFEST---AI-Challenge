# Failure log

Approaches tried and rejected, each with the measurement that killed it.

This exists because the report requires it, but it earns its place independently:
every entry below is a mistake that looked completely reasonable beforehand, and
several of them fail *silently* — producing a confident, well-formatted, wrong
result rather than an error. Those are the ones worth writing down.

Entries are newest last. Each records: the approach, what we expected, what we
measured, and what changed as a result.

---

## F-001 — Global stem-based deduplication

**Approach.** Treat files sharing a filename stem as one document, corpus-wide.
Written into the plan before anything was measured.

**Hypothesis.** `auction_catalogue_concerning_morwenna_vosgard.pdf` and `.txt`
are the same in-world document in two formats, so the corpus holds 134 unique
ephemera behind 145 files.

**Experiment.** Text similarity between same-stem files, per collection.

**Result.**

| Collection | Similarity | Verdict |
|---|---|---|
| `chronicles/` | 1.000 | same work |
| `codex/` | 0.989–0.991 | same work |
| `ephemera/` | **0.019–0.048** | **different documents** |

**Why it failed.** The ephemera pairs are unrelated in-world documents that
merely concern the same subject — one is a sale catalogue of siege equipment,
the other a catalogue of a person. Collapsing them deletes real evidence.

**What changed.** Deduplication became collection-dependent (ADR-003). The rule
lives in one named constant with the measurement recorded beside it, and
`tests/test_ingest.py` fails if anyone "simplifies" it back to a global rule.

**Failure mode: silent.** Nothing errors. Eleven independent sources vanish and
the conflict resolver stops seeing disagreements it was built to catch.

---

## F-002 — Exponential backoff as the answer to rate limits

**Approach.** Wrap API calls in retry-with-backoff and assume transient limits
resolve themselves.

**Hypothesis.** OCR failures on 13 of 17 scans were transient rate limiting.

**Experiment.** Read the provider's actual error text instead of catching it
generically.

**Result.**

```
limit: 20, model: gemini-3.7-flash
quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier
```

**Why it failed.** ~20 requests **per day, per model** is a daily cap. We spent
five retry attempts on each of thirteen documents sleeping through a limit that
resets tomorrow. Backoff cannot recover from a daily quota by construction.

**What changed.** `retry.py` distinguishes daily quota from transient limits and
fails fast on the former; `GeminiPool` rotates across six models, each with its
own allowance (ADR-007). OCR went from 4/17 to 12/17 on the first rotating run.

---

## F-003 — Fixed-size embedding batches

**Approach.** Batch 128 chunks per embedding request.

**Result.** Rejected outright by Voyage: a fresh account with no card is limited
to 3 requests and 10,000 tokens per minute, and 128 chunks is ~36,000 tokens —
triple the per-minute allowance in a single request.

**Why it failed.** Chunks range from a short table row to 2,856 characters, so
any constant batch size is either wasteful or over the limit.

**What changed.** Token-aware batching with a rolling-window limiter (ADR-008).
A secondary lesson: the limiter's first test spun forever, because a fake sleep
that does not advance time makes a rolling window never roll. The clock is
injectable now.

---

## F-004 — Parsing the infobox by its `## Infobox` heading

**Approach.** Locate the infobox section by its Markdown heading, then read the
table beneath it. The obvious reading of a corpus that looks perfectly regular.

**Hypothesis.** All 95 wiki pages carry a `## Infobox` section.

**Experiment.** Count them (`eval/probes/corpus_shape.py`).

**Result.** **6 of 95 pages have no such heading.** Three are artifact pages:
`the_cinder_wrought_aegis.md`, `gauntlet_of_sorrowfell.md`,
`the_thrice_bound_lantern.md`.

**Why it failed.** `the_cinder_wrought_aegis.md` supplies hop 2 of dev question
`1b_003` through its `Place of housing` row. A heading-keyed parser returns
nothing for that page, so the question cannot be answered at all.

**What changed.** The infobox is defined as the **first pipe table in the file**,
wherever it appears (ADR-009).

**Failure mode: silent.** The page parses successfully and yields zero edges.
There is no error to notice — only a question that quietly stops working.

---

## F-005 — Reading node type from the wiki title

**Approach.** Titles look like `# [[Vault Chitin]] (creature)`, so parse the
category from the parenthesised suffix.

**Result.** **Only 26 of 95 titles carry a category.** The rest are bare
(`# Ashreach`), or wikilinked without a category
(`# [[Cerys Sablewood the Ashen]]`).

**Why it failed.** Type is load-bearing: `1b_007` asks which *accord* a faction
won, and the faction won two conflicts of which only one is an accord. Without
type the question is a coin flip.

**What changed.** Type comes from the image filename taxonomy
(`plate_NN_<category>_<subject>`, `atmo_<style>_<category>_<subject>`), which
`src/ingest/metadata.py` already parses with complete regularity (ADR-009).

**Note on our own process.** The first version of this measurement reported 3 of
95, because the probe's regex was missing `re.MULTILINE`. The corrected figure is
26. Worth recording: a measurement can be wrong in the same direction as the
assumption it is testing, and the only defence is that the probe is short enough
to read.

---

## F-006 — Treating infobox cells as values

**Approach.** A cell holds an entity, a literal, or a `;`-separated list.

**Result.** All 651 cells fall into **12 templates**, four of which are not
values at all. The dangerous one appears 11 times:

```
Fought in [[The Purge of Blackport]] for [[House Morvain]]
Fought for [[The Bleeding Crown]] in [[The Accord of Mournthrone]]
```

**Why it failed.** This is one **ternary** fact with two objects. Extracting
every link as an edge from the subject asserts that a person was "belligerent in
House Morvain", which is false. Both word orders occur, so the arguments cannot
be resolved by position — only by type.

Two further shapes: `since 356 AS` qualifiers (which `1b_003` asks about
directly, and which end up glued into node names like
`silent_psalter_since_341_as` if ignored), and prose attributes containing
incidental links (`Appearance | ... a garrisoned settlement in the [[Ash
Wastes]]`) that must not become relations.

**What changed.** Twelve named template handlers, each with its own test
(ADR-010). No LLM: twelve regexes cover 100% of the cells, and a named handler
with a test is more defensible to a judge than a model's output.

---

## F-007 — Proximity-window claim extraction

**Approach.** To find competing claims, look for an entity name within ~140
characters of a dated assertion.

**Result.** ~20 "conflicts", of which most were fabricated. Two examples:

- **Vharencrag Fortress** appeared to have a contested founding year. It does
  not: every source says 84 AS. The window had captured *Hollowvale's* 286 AS
  from a decree that happens to name both places.
- Regions — `The Ash Wastes`, `The Gloaming Reach`, `The Pale Coast` — appeared
  to have four competing founding years each. They are merely named near the
  foundings of the settlements inside them.

**Why it failed.** Proximity is not attribution. In a corpus where documents
routinely name five entities per paragraph, a window captures whichever entity
is nearest, not the one the sentence is about.

**What changed.** Claims are extracted only where the entity is the grammatical
subject, or is the nearest preceding *known* entity for an anaphoric subject
(ADR-012).

**Failure mode: loud but plausible.** The false conflicts looked real enough to
be written into an ADR before they were checked. They were caught only by asking
"is this entity a region?" — a question nobody had a reason to ask.

---

## F-008 — Structural claim extraction without stripping Markdown emphasis

**Approach.** Having fixed F-007, extract claims where the entity is the
sentence subject.

**Result.** **Zero conflicts found in the entire archive.**

**Why it failed.** Every competing claim in the corpus is wrapped in Markdown
emphasis and every authoritative one is not:

```
codex     : Gloamreach's founded is 246 AS.
ephemera  : Gloamreach was founded in **286 AS**.
codex     : Gauntlet of Sorrowfell's forged is 391 AS.
ephemera  : Its forged year is **360 AS**.
```

A regex expecting `founded in 286 AS` never matches `founded in **286 AS**`.

**What changed.** Emphasis is stripped before matching (ADR-012). With that one
line, the same extractor finds 7 conflicts including both dev-set ones.

**Failure mode: silent, and the worst in this log.** The conflict layer does not
error, does not warn, and does not fire. It reports no disagreement anywhere in
the archive with complete confidence. A conflict layer that never fires is worse
than no conflict layer, because nothing in the output tells you which one you
have.

---

## F-009 — Resolving anaphora by the document's filename subject

**Approach.** Ephemera filenames encode their subject
(`sermon_concerning_malchior_cindervale_the_flame_touched.txt`), and ingestion
already carries it as `subject_slug`. Use it to resolve "Its forged year is
360 AS".

**Result.** Wrong referent. That sermon is *about* Malchior Cindervale, but the
sentence concerns the Gauntlet of Sorrowfell, named in the sentence before.

**Second attempt: nearest preceding capitalised phrase.** Also wrong — the
sentence before "Its forged year is 354 AS" ends on "the Sundering".

**What changed.** Nearest preceding mention of a **known graph entity**, which
resolves both correctly (ADR-012).

**Why this matters more than it looks.** Both wrong versions file a real claim
against the wrong entity. The result is a confidently sourced, fully cited,
completely wrong answer — the failure the evidence panel is least able to
expose, because everything about it looks right.

---

## F-010 — Fuzzy entity matching

**Approach.** Resolve a question's entity mention to the closest graph node above
a similarity threshold.

**Result.** Measured across 125 entity names: **20 shared given names**, **19
shared surnames** (`fellgard` ×5, `ashgrove` ×5), and 6 pairs of genuinely
distinct entities above 0.80 similarity:

```
0.839  caedmon_fellgard  ~  ederon_fellgard
0.833  gloaming_reach    ~  gloamreach
0.828  morwenna_morvain  ~  morwenna_vane
0.824  caedmon_hollowmere ~ lucan_hollowmere
0.812  greyfell_citadel  ~  ironfell_citadel
0.800  gloammarch        ~  gloamreach
```

**Why it failed.** The name space appears adversarial by construction.
`ederon_fellgard` is the subject of `1b_007`; any threshold loose enough to be
useful also merges it with `caedmon_fellgard`. A threshold tight enough to
separate them is tight enough that exact matching would have succeeded anyway —
so the fuzzy layer buys nothing and risks the one error the output cannot show.

**What changed.** Exact match on the normalised name only. Fuzzy matching may
*generate candidates*; it may never *select a winner*. Unresolved mentions
escalate to disambiguation, then abstain (ADR-011).

---

## F-011 — Substring scoring in the evaluation harness

**Approach.** Score an answer correct when an acceptable string appears in it.

**Result.** Marks this **correct**:

> there is no mention of who the victors were

**Why it failed.** The answer key warns about exactly this in its own preamble,
and it is not a contrived case — a retrieval system that finds nothing produces
denials phrased around the words in the question.

**What changed.** Matching requires the gold string to appear in a sentence that
does not deny it (ADR-014). Two bugs surfaced while building the guard, both
caught by tests rather than by review:

- A 90-character negation window marked a *correct* answer wrong, because an
  unrelated denial two sentences later fell inside it. Negation is now scoped to
  the sentence.
- Folding to ASCII *before* normalising typographic punctuation deleted the
  U+2019 apostrophe rather than converting it, so `Sorrowfell's` and
  `Sorrowfell's` could never match — on a corpus that uses U+2019 throughout.

---

## What this log is telling us

Seven of the eleven entries fail **silently**: F-001, F-004, F-005, F-006,
F-008, F-009, F-011. They produce a well-formed, confident, wrong result rather
than an error.

That is the argument for the whole architecture in one observation. A pipeline
whose failures are silent cannot be debugged by looking at its output, so the
system has to be built out of parts small enough to test individually and
transparent enough to audit afterwards — which is also, conveniently, what makes
it defensible in a room.

---

## F-012 — A negation guard built from a phrase list

**Approach.** Having established that substring scoring over-credits (F-011),
guard it with a list of negation phrases: `does not mention`, `does not state`,
`does not specify`, `no mention`, and twenty more.

**Hypothesis.** The list covers how a refusal is phrased.

**Experiment.** The first real evaluation sweep. It reported **1B 3/7** against
the 2/7 previously recorded.

**Result.** The extra "correct" was `1b_009`, whose answer is a refusal:

> Based on the provided passages, no connection between Halvard Crowhurst and
> the victors of the Purge of Blackport is established. The text only records
> that Halvard Crowhurst is a member of The Iron-Ring Cartel, which was a
> belligerent in the Purge of Blackport, but **does not identify** the victors
> of that conflict.

The gold string `member of the Iron-Ring Cartel` sits in the second sentence.
That sentence *is* negated — by `does not identify`, which was not in the list.
`mention`, `state` and `specify` were. `identify` was not.

**Why it failed.** A phrase list has to anticipate every verb a language model
might reach for, and there is no reason to think any list is complete. The
failure is silent and biased upward: a missing phrase can only ever turn a wrong
answer into a right one, never the reverse. A scorer whose errors all point the
same way is worse than no scorer, because the number looks plausible.

**What changed.** Negation is matched as a **construction**, not a phrase:
auxiliary + `not`, `no <evidence-noun>`, `not <participle>`. The verbatim
answer is a regression test, and so are the three real answers that must stay
correct — so a rule that over-fires breaks the build rather than quietly
deflating the score.

**Worth noting about the process.** This was caught only because the harness
disagreed with a number already written down. Had we had no prior 2/7 to
contradict, 3/7 would have gone into the report. The value of the old figure was
not that it was right — it was that it was *there to be contradicted*.

---

## F-013 — No request timeout, and retry stacked on top of rotation

**Approach.** Rely on `with_retry` (5 attempts, exponential backoff to 60s) plus
six-model rotation to survive free-tier limits.

**Result.** The first evaluation sweep processed 3 questions in 12 minutes, then
**hung for 19 minutes on a single question** with no error and no way to
interrupt it. It had to be killed.

**Why it failed.** Two compounding faults.

1. The `google-genai` SDK defaults to **no timeout**. A request that never
   returns blocks forever, and `with_retry` cannot help — it only catches
   exceptions, and a hung socket does not raise one.
2. Retry and rotation multiply. Five attempts per model across six models is up
   to 30 minutes of backoff for one question, which is the wrong trade when each
   model carries a *separate* quota bucket: a per-minute limit on one model says
   nothing about the next.

**What changed.** A 120s request ceiling — measured against ~35s typical latency
for a trivial completion, so roughly 3.5x headroom. Attempts per model dropped to
2 while alternatives remain, with the full 5 reserved for the last available
model, where waiting is the only option left.

**The measurement that made the fix cheap.** Because responses are cached, the
corrected re-run cost **0 API calls and 0.8 seconds**. The cache turned an
80-minute sweep into a free one, which is the difference between an evaluation
you run once and an evaluation you can iterate against.

---

## F-014 — Concluding "tier resolves every conflict" from a sample that excluded relational claims

**Approach.** ADR-013 measured every contested attribute in the archive, found
7 of 7 resolved by source tier with the codex announcing itself each time, and
concluded the authority layer provides no measurable benefit on this corpus.

**Result.** Human review found `1b_009`: `wiki/the_purge_of_blackport.md` names
the Iron-Ring Cartel as victor; `wiki/the_iron_ring_cartel.md` keeps a victor
list, excludes the Purge from it, and states twice in prose that participation
is recorded *"without assigning the Cartel the status of victor"*. Both are
`wiki/` at **tier 2**. Tier cannot separate them.

**Why it failed.** The measurement extracted `founded` and `forged` **years**.
It never looked at relations, so a relational conflict could not appear in it.
The conclusion was then stated as though it covered the archive.

The failure is not the measurement — the 7 dated conflicts really are
tier-decided. The failure is the **scope of the claim drawn from it**. A sample
that structurally excludes a category cannot support a conclusion about that
category, and nothing in the number itself signals the gap.

**What changed.** ADR-013 amended rather than withdrawn: the dated-attribute
finding stands, the archive-wide claim does not. Re-measured all six victor
edges bidirectionally — 4 agree, 1 contradicted, 1 faction-page-silent. The
conflict resolver now needs a same-tier branch, and `must_surface` enters the
answer key for conflicts authority cannot adjudicate.

**A second error inside the correction.** The first version of the re-measurement
reported **two** contradicted edges, having also flagged the Silent Choir over
the War of Drowned Light. That was wrong: the Choir's page carries no victor row
at all and says outcomes are not detailed, so it is *silent*, not contradicting.
The test had been "in the belligerent list and absent from the victor list",
which cannot distinguish a page that declines to claim victories from a page
that claims victories and excludes one. Corrected to ask whether the faction
page makes victor claims **at all**. Silence is not denial — and had this stood,
`1b_005` and `1b_022` would have been mislabelled as conflict questions.

---

## F-015 — A single careful reviewer

**Approach.** ADR-014 specifies two independent reviewers per answer-key entry.
The 2026-08-29 review arrived as one consolidated pass over the seven 1B
questions, with per-question confidence ratings.

**Result.** It reported `1b_006` as having **two** valid answers, Ravena
Stormwell and Isolde Mournvale, at `confidence: high`.

Corpus enumeration finds **fourteen**:

```
wiki/the_silent_choir.md  Members row : 6 names
character pages with a membership row : 8 names
overlap between the two sets          : 0
```

The review missed the faction page's `Members` row entirely and six of the eight
character pages.

**Why it failed.** Membership is recorded in two disjoint places, and a reviewer
reading from the character-page direction sees only that half. This is the same
corpus property the graph builder has to handle (CLAUDE.md corpus fact 3) — it
catches humans exactly as it catches parsers.

**What changed.** The fourteen-name set was retained, not narrowed. The entry is
marked `unresolved` with the discrepancy recorded in the key itself, and
`verification.is_confirmed` now requires two reviewers **and** no open
discrepancy.

**Why this is the most useful entry in the log.** Had the key been narrowed to
the review's two answers, twelve correct answers would have been scored wrong,
and the graph would then have been "improved" until it stopped returning them.
The evaluator would have taught the system to be worse, with every number
looking healthy throughout. One reviewer, working carefully and reporting high
confidence, is not a safety mechanism — the second reviewer is the mechanism.
