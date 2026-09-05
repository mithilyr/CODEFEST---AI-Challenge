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

### Amendment, 2026-08-30 — the conclusion did not follow from the evidence

The sentence above is wrong, and the evidence contradicting it is in this entry.

**No second reviewer ever ran.** The fourteen names were found by *corpus
enumeration* — the code block at the top of this entry. This entry diagnosed a
mechanical problem and prescribed a human remedy.

The diagnosis was right: membership is recorded in two disjoint places, so a
reviewer reading from the character-page direction sees one half. That is a
**systematic recall failure**, not a lapse in care. A second human reading the
same direction inherits the same blind spot, so a second reviewer is not the
mitigation — it is the same instrument applied twice.

**Corrected conclusion.** The demonstrated failure is systematic recall failure
in manual verification. The appropriate mitigation is **independent corpus
enumeration that reads every direction by construction**. Human review is
reserved for what enumeration genuinely cannot do: precision (is this answer
*right*?) and semantic disputes (which of several true facts does the question
select?).

`eval/completeness.py` implements this. Run against the current key it finds
**14 for `1b_006` — 6 from the faction page's `Members` row, 8 from character
pages, zero overlap** — independently corroborating the key by a different route
than the one that built it. Across all nine scoreable questions it reports **0
recall defects**.

The original conclusion is kept above rather than deleted, because the shape of
this mistake is the point: we drew a conclusion about *process* from evidence
about *instrument*, and did it inside the entry that contains the disproof.

## F-016 — Trusting that a read-only corpus stayed read-only

**Approach.** The corpus is documented as read-only competition data, held
outside the repository and excluded from git. Every measurement since ingestion
landed has been taken against whatever `CORPUS_PATH` happens to point at, with
no check that it still matches what the competition shipped.

**Result.** On 2026-08-29 a routine `python -m src.ingest.pipeline` reported:

```
files scanned       : 341      (documented: 340)
canonical documents : 318      (documented: 317)
evidence units      : 30553    (documented: 30553)  <- unchanged
```

Comparing every file against the pristine `Ashen_Era_Archive.zip`:

```
on disk but not in zip : 8    (7 x wiki/.obsidian/*, + wiki/The Iron-Ring Cartel.md, 0 bytes)
in zip but missing     : 0
content differs        : 36   -> all 36 CRLF->LF only, 0 real text changes
```

Someone had opened `wiki/` in Obsidian that evening (mtimes 21:31–22:37). It
rewrote 36 files with Unix line endings and left behind an empty note.

**Why this was dangerous.** No evidence was lost — the 36 files are
byte-identical after newline normalisation, which is why the evidence-unit count
never moved and nothing looked wrong. The damage was the empty file. It entered
ingestion as canonical document #318 carrying **zero evidence units**, and it is
titled *The Iron-Ring Cartel* — the entity at the centre of `1b_009`'s same-tier
conflict, and one of only two nodes in the corpus that page-title-keyed entity
resolution could confuse.

Had this survived into graph work, `the_iron_ring_cartel.md` would have
competed with an empty namesake node for every Cartel edge. The symptom would
have been missing or halved membership edges appearing during graph
construction — and we would have gone looking for the bug in the infobox parser,
which is where the corpus has already burned us four times (F-004, F-005,
F-006, F-008). The parser would have been correct.

This is the §5 failure class exactly: not a crash, but a plausible wrong result
with a healthy-looking number in front of it. The count that would have exposed
it — 318 against a documented 317 — was printed on every pipeline run and is
the kind of one-digit drift nobody reads.

**What changed.** All 36 files were restored from the zip and the empty note
deleted, each file re-checked as newline-only-different immediately before being
overwritten so that a file with real edits could not be silently destroyed.
The editor's vault config was removed as well, since leaving it
in place leaves the cause in place. Post-restore: 0 differ, 0 missing, 0 extra.
Ingestion is back to 340 -> 317 -> 30,553 and the baseline is unchanged at
1B 2/7, 1C 2/2.

**Closed.** `config/corpus_manifest.sha256` holds the SHA-256 of all 341 shipped
files (39 KB, generated from the zip rather than from the extracted copy, so it
cannot inherit damage the copy has already taken).
`python -m src.ingest.integrity` verifies it and exits non-zero on drift, which
also gives the clean-clone test something to assert.

Extra files are reported in two groups, because that distinction is this entry's
whole lesson: an unexpected file matters when ingestion *reads* it. A stray
`.DS_Store` is drift. A stray `.md` in `wiki/` is the incident above.

Nine regression tests reconstruct the specific failure — a CRLF-only rewrite
caught as modified, an empty note in `wiki/` flagged `extra_ingested` and
unsafe, an editor's config flagged as drift but safe to ingest. Deleting the
`extra_ingested` guard makes `test_stray_ingested_file_is_flagged_as_unsafe`
fail, which is how we know the test is load-bearing and not decorative.

**What this cost.** Nothing, because the discrepancy was chased instead of
rounded off. That is the only reason it is a log entry and not a week of graph
debugging.

## F-017 — Counting a corpus with the bug the ADR was written to forbid

**Approach.** ADR-009 established that the infobox is the first pipe table in the
file, not the `## Infobox` section, because six pages have no such heading and
one of them supplies hop 2 of `1b_003`. Its headline census reported **107**
distinct infobox field names, marked *"validated by probe"*.

**Result.** Running the probe it cites reports **109**:

```
distinct infobox field names        : 109
    of which inside a '## Infobox'  : 107
    visible only on headless pages  : ['Place of forging', 'Place of housing']
```

The 107 was the count *inside* `## Infobox` sections. The ADR's headline number
was produced by heading-keyed parsing — the exact practice the ADR exists to
forbid.

**Why it failed.** The census was written before the headless-page finding and
never re-run against it. ADR-009's own trade-offs paragraph names both missing
fields, so the two halves of the document disagreed with each other in plain
sight for a day and nobody re-ran the command in between. "Validated by probe"
was true of the decision and untrue of the number.

The sting is which two fields were dropped: `Place of housing` is the row on
`the_cinder_wrought_aegis.md` that answers `1b_003`. The measurement lost exactly
the evidence the ADR was written to protect.

**What changed.** ADR-009 amended, with the original 107 left in the table rather
than overwritten. `CLAUDE.md` corpus fact 2 corrected 107 -> 109 with the history
kept visible. The probe now prints the total, the heading-keyed subset, and the
names of the difference, so the two numbers cannot silently diverge again.

**Why this belongs next to F-016.** Both are the same failure at different
layers: a number that looked healthy because nothing re-derived it. F-016 was a
corpus that drifted from the bytes we measured; this is a document that drifted
from the command it cites. The fix in both cases was not judgement, it was
re-running the check.

---

## F-018 — A dict-keyed infobox parser, caught before it was written

**Approach.** Not ours — this one was caught in specification review, before
`src/graph/` existed. The natural shape for an infobox parser is
`fields[name] = value`, and every design sketch so far had assumed it.

**Result.** Measured across 95 wiki pages: **5 pages** carry a repeated field
name, **6** distinct (page, field) collisions, **7 cells** that a dict-keyed
parser drops with no error raised.

```
wiki/the_ashen_vanguard.md              | Belligerent   x3
wiki/the_accord_of_mournthrone.md       | Waged at      x2
wiki/the_accord_of_mournthrone.md       | Devastated    x2
wiki/ignatz_ashgrove_the_oathless.md    | Rival         x2
wiki/sabelle_mournvale_the_twice_crowned.md | Wielded relic x2
wiki/emberdeep.md                       | Serves at Emberdeep x2
```

**Why it would have failed silently.** The page parses. Nothing raises. The edge
count is simply lower than the corpus supports, and there is no output from which
the loss is visible — the same shape as F-008 and the reason ADR-012 exists.

**The part that is worse than lost edges.** `the_ashen_vanguard.md` has no
`Victor of` row at all. Its sole victor claim is an `Outcome` row reading
`Victor of The Accord of Mournthrone`. An extractor keyed on `Victor of` reads
the Vanguard as **silent** on victories — and under F-014, silence is not denial.
The ADR-013 CORRECTION classified the Accord of Mournthrone as "Agree both ways";
that verdict holds only because the row was read by a human. There was no
runnable check behind it until now.

**What changed.** ADR-009 amended: the parser must return rows as an ordered
sequence of `(field, value)` pairs; `fields[name] = value` is forbidden. PT-10 in
`eval/probes/corpus_shape.py` measures the collisions and the victor channels.
`tests/test_ingest.py` pins the Vanguard's three `Belligerent` rows and its
`Outcome`-only victor claim, so the rule fails a test rather than a demo.

**What we did not conclude.** The review that prompted this also claimed an
`Outcome` row can depend semantically on the `Belligerent` row above it. All
seven `Outcome` rows were checked: the Vanguard's names its own referent and the
other six describe how a war ended. Row multiplicity is load-bearing; row order
is not, on current evidence. We built for the first only rather than for the
more interesting claim.

## F-019 — A `seen` set that discarded the evidence, not just the route

**Approach.** Standard BFS over the graph, marking nodes visited so the search
terminates and does not revisit. This is the textbook shape and it looks obviously
correct.

**Result.** For `1b_009` - *"In what way is Halvard Crowhurst connected to the
victors of the Purge of Blackport?"* - it returned exactly one two-hop path:

```
purge_of_blackport <-[belligerent_in]<- iron_ring_cartel <-[member_of]<- halvard_crowhurst
    both hops sourced from wiki/the_iron_ring_cartel.md
```

The path is true. It is also the wrong one. The route the question needs is:

```
purge_of_blackport <-[victor_of]<- iron_ring_cartel <-[member_of]<- halvard_crowhurst
    wiki/the_purge_of_blackport.md  +  wiki/the_iron_ring_cartel.md
```

Same length, same endpoints, **half the evidence**: one document instead of two.
Evidence recall 0.50 rather than 1.00, on the question where the second document
is the entire point, because it is the one making the contested victor claim.

**Why it failed.** The `seen` set is a *node* filter, so the first path to reach
`iron_ring_cartel` won and every alternative route to the same node was discarded
unexamined. Which route wins is then decided by edge insertion order - that is,
by the alphabetical order of filenames during the build.

**Why this one is worth the entry.** Nothing was wrong with the answer, the code
raised nothing, and the path printed with real citations attached. Had the
traversal been written first and measured later, the system would have reported a
correct-looking two-hop answer for `1b_009` with the disputed claim's source
missing from the evidence - and the conflict layer, when it is built, would have
had nothing to detect a conflict in. This is the §5 failure class arriving through
a data structure rather than a parser.

It also sharpens the distinction the coverage metric has to make: **a path
existing is not the evidence existing.** Two paths of equal length can differ by
a whole document.

**What changed.** `find_paths` prunes cycles only - a node may not repeat *within
one path*, but alternative routes to it are all enumerated. At 267 edges the cost
is nothing. `test_traversal_returns_alternative_routes_not_just_the_first` pins
it, asserting both relations appear and that the `victor_of` route carries both
documents.

---

## F-020 — Reading only `[[links]]`, on a corpus that does not always use them

**Approach.** Extract edges from wiki links in infobox cells. The corpus is a
wiki; entity references are `[[Marrowwell Abbey]]`; harvesting them is the job.

**Result.** `the_ashen_vanguard.md` produced **zero** `belligerent_in` edges. Its
three `Belligerent` rows are plain text:

```
| Belligerent | The War of Drowned Light |
| Belligerent | The Accord of Mournthrone |
| Belligerent | The Leaden Accord |
```

No brackets. A link-driven parser reads the page as naming no conflicts at all.
Corpus-wide, 26 edges were missing and **10 entities were completely isolated** -
present as nodes, reachable by nothing.

**Why it failed.** We inferred the convention from the pages we had looked at.
The corpus is inconsistent about linking, and the inconsistency is invisible
because an unlinked reference and a genuinely absent relation produce identical
output: no edge, no error.

**Compounding.** This is the same page as F-018, which has no `Victor of` row and
records its only victory in an `Outcome` row. Two independent extraction
assumptions both fail on `the_ashen_vanguard.md`, and the ADR-013 CORRECTION's
treatment of the Accord of Mournthrone depends on that page being read correctly.

**What changed.** A plain-text cell on a *mapped relation field* is resolved
against known entity names by **exact match on the canonical key** - the same
ladder as ADR-011, with no fuzzy rung. A value matching nothing yields no edge
rather than a guess, and multi-valued cells resolve only if every part resolves.
The method is recorded on the edge as `extraction="exact_name_match"`, because a
name match and a link do not carry the same confidence and a reviewer should be
able to filter on the difference.

Result: 241 -> 267 edges, isolated entities 10 -> 0.

**What we did not do.** Substring or similarity matching against entity names.
That would resolve `The Purge of Blackport` inside prose and manufacture
relations from descriptions - ADR-010's incidental-link failure by another route.
Exact match only, on literal cells only.

---

## F-021 — A "never let this filter empty the set" rule applied to both filters

**Approach.** `src/query/evidence.py`'s type-aware filter for `1b_007`'s answer
narrows candidate paths by two hints in sequence: a coarse `entity_type` check,
then a lexical check against the question's head noun. The first version gave
both filters the same fallback - "if applying this filter would leave nothing,
skip it and keep what we had" - reasoning that a hint extracted from free text
should never be trusted enough to manufacture a failure on its own.

**Result.** `PATH_MISSING_ATTRIBUTE`, the sufficiency state that exists
specifically to name "a type filter ran out of candidates," was unreachable.
`candidates` starts as the non-empty input and is only ever reassigned when a
filter's result is *also* non-empty - so the final `if not candidates` check
could never fire. Caught writing the regression test for that status, not by
inspection: the test constructed a deliberate type mismatch and got `SUFFICIENT`
back with the original, unfiltered set.

**Why it failed.** The two filters are not the same kind of hint, and giving
them the same fallback erased the distinction. The lexical filter is genuinely
soft - `1b_003`'s "redoubt" not appearing in "Gloamreach" is a wording mismatch,
not evidence the corpus lacks the location. The coarse type filter is not soft
in the same way: it already has its own leniency built in (`entity_type is
None` counts as a pass, because `1b_006`'s edge-only nodes mostly carry no
recorded type at all). If applying that *already-permissive* filter still
empties the set, every remaining candidate carries a type the corpus explicitly
recorded as a mismatch - a real finding, not a hint that merely didn't help.

**What changed.** The coarse type filter now applies unconditionally, with no
"undo if empty" fallback; only the lexical filter keeps the fallback.
`test_path_missing_attribute_when_both_filters_genuinely_exclude_everything` and
`test_type_filter_falls_back_when_the_lexical_hint_matches_nothing`
(`tests/test_query.py`) pin both halves of the distinction so the same mistake
can't come back as a "simplification."


---

## F-022 - Asserting the type filter was invisible in the UI, without rendering the page

**Approach.** Before writing `src/ui/`, I probed what `Answer` carries about
`1b_007` and measured that `filter_endpoints` discards what it eliminates: the
traversal returns **5 candidate paths**, the filter keeps **2**, and the 3
dropped ones - along with the type hint that dropped them (`accord` ->
`conflict`) - appear nowhere on the returned `Answer`. I reported to the team
that `1b_007`'s differentiator therefore could not be shown in the UI without
extending the response contract, and wrote a regression test asserting
`"The Winter Reckoning" not in html`.

**Result.** That test failed on the real rendered page. `The Winter Reckoning`
*is* on the page - in the `raw` cell of the surviving `victor_of` hop, which
reads `[[The Winter Reckoning]]; [[The Leaden Accord]]`.

**Why it failed.** The measurement was right and the conclusion drawn from it
was wrong. I checked what the *endpoints* carried and generalised to what the
*page* could show, forgetting that ADR-010's multi-valued cell keeps both
values in one string, and that the UI renders each hop's cell verbatim. The
multi-valued relationship is visible in the evidence panel already, sitting
directly above an answer that names one of its two values - which is most of
the differentiator, obtained for free.

**The residual gap is narrower than claimed, and is real.** What the page still
cannot show is the *filter decision*: that a type hint ran, which word it was,
and which candidates it removed. `1b_007`'s other two dropped paths
(`The Purge of Blackport`, and the second `Winter Reckoning` route) are not
represented at all. Closing that needs three additive fields on `Answer`
(`type_hint_word`, `type_hint_entity_type`, `filtered_out`) - not a behaviour
change - and it is deliberately **not** done yet: the instruction for this
checkpoint was to build against the existing contract, and doing so surfaced
the true size of the gap instead of the assumed one.

**What changed.** `tests/test_ui.py::test_1b_007_multi_valued_cell_is_visible_in_the_evidence`
now asserts the opposite of what I first wrote, and says why in its docstring.
The general lesson is the one CLAUDE.md already states and I still skipped:
render the thing before describing what it cannot do.

---

## F-023 - An architectural guard that matched bare substrings

**Approach.** `src/ui/` is only defensible as "a thin presentation layer" if
that stays true, so `tests/test_ui.py` checks the UI source for the names of
every reasoning entry point (`walk_relations`, `check_conflict`,
`filter_endpoints`, `route(`, ...) and fails if one appears. The first version
used a plain `name in code` substring test.

**Result.** It failed immediately on the code it was written to protect.
`"route("` matched the view's own private `_route(...)` helper. Loosening the
needle to `"route"` then matched `view["routes"]` and render.py's `.route` CSS
class as well.

**Why it failed.** `route` is a word this layer legitimately owns - the view's
whole job is to arrange route *data* for display. A substring guard cannot tell
"holds a route" from "computes a route", so it flags honest code, and a guard
that cries wolf on honest code is a guard someone deletes.

**What changed.** Two checks instead of one. The name list is matched on a word
boundary (`route` no longer hits `_route`), and `route` is dropped from it
entirely, replaced by
`test_view_imports_only_the_response_contract`, which parses the view's AST and
asserts its `src.*` imports are exactly `{src.graph.schema, src.query.engine,
src.query.evidence}` - and that only `EvidenceStatus` comes from the last.
That states the real constraint: the view cannot import the modules that
decide things. It is both stricter and quieter than the substring test.


---

## F-024 — A comparison harness that could not reproduce the result we already had

**What we tried.** Measuring our four-template router against a sister repo's
cue-based router (ADR-019) on an independently authored question set, scoring
route success, answer correctness, complete evidence and traversal depth for
both arms.

**What killed it, four times.** The first run reported our own engine at 6/7 on
the dev questions, where ADR-017 records 7/7. That gap was the tell: the
harness was wrong, not the engine. Four separate causes, all ours:

1. **Per-edge conflict filtering.** We applied `src/query/conflict.py`'s
   `check_conflict` to every edge of every candidate path. It is
   paragraph-scoped — right for the one question our engine asks it, far too
   broad as a general filter. `wiki/the_iron_ring_cartel.md` carries its victor
   list close enough to its Purge-of-Blackport denial that the paragraph naming
   The Leaden Accord also matched the denial pattern, so the Cartel's
   *uncontested* `victor_of -> The Leaden Accord` edge was excluded. That
   emptied the candidate set and reported `1b_007` and `1b_022` as `not_found`
   **for the sister arm**. Published, it would have understated a teammate's
   work by two questions on a defect of our own making.
2. **Bespoke answer matching.** We wrote a fresh string comparison instead of
   using `eval/scoring.py`, so it lacked the negation guard ADR-014 exists for
   and could not score `1b_009`, whose gold answer is a prose sentence.
3. **Direction-sensitive route comparison.** `walk_relations` deliberately does
   not fix direction, but the scorer compared relation tuples in order, so a
   correct answer reached from the other end counted as a wrong route.
4. **Unnormalised relation vocabulary.** The answer key writes `victor` and
   `has_member` where `config/relations.yaml` writes `victor_of` and
   `member_of` — the gap the README already reports. Unnormalised, every
   correct `victor_of` route looked like a wrong one.

**The number that killed it.** Arm A at 6/7 instead of 7/7, and arm B at 2/7
before any fix. After all four: arm A reproduces 7/7 exactly, and arm B rises
to 3/7 on the dev questions — the remaining losses being genuine.

**What we do instead.** The harness is calibrated against a result we already
know before any new number from it is trusted, and it reuses `eval/scoring.py`
rather than reimplementing scoring. Each fix is documented at its site in
`comparison/harness.py` and `comparison/sister_conflicts.py`.

**The lesson worth keeping.** Three of these four bugs flattered our own arm and
penalised the other. None was deliberate, and that is the point: when you build
the instrument that measures your work against someone else's, the errors do not
distribute randomly. The calibration step is not a formality.

---

## F-025 — A validated plan that was well-formed, relevant to nothing, and confidently wrong

**What we tried.** An LLM planner tier (ADR-020) that proposes a relation chain
which `validate_plan` checks against the graph before anything is traversed.
The validation rule was: the start entity must exist, every relation must be
defined in `config/relations.yaml`, and the chain must be within the hop bound.

**What killed it.** Asked *"What color is the sky in the Ashen Era?"* — a
question the corpus cannot answer at all — a live free model returned:

```json
{"start_entity": "The Ashen Vanguard", "relations": ["in_region"],
 "answer_type": "plan"}
```

It picked **The Ashen Vanguard** because the question contains the word
"Ashen". Validation accepted it: that faction is real and `in_region` is real.
The engine walked it and returned `planned_sufficient` with a genuine evidence
trail attached — a confident, well-cited answer to a question nobody asked,
which is the precise failure this whole project exists to prevent. The second
nonsense probe, *"What did the Gravemaw Wyrm eat for breakfast?"*, also
returned a confident answer.

**The lesson.** *Well-formedness is not relevance.* Every check we had asked
"is this plan constructible?" and none asked "is this plan about the question?"
A schema, a name check and a hop bound all passed a plan that shared a single
word with the prompt. `answer_type: "plan"` in the same response is the tell —
the model was not reasoning about the corpus at all, and nothing in the
pipeline noticed.

**What we do instead.** Three guards, each with its own regression test:

1. **Grounding** (`planner.is_grounded`). Every significant token of the
   entity's name must appear in the question. "Ashen Vanguard" needs both
   "ashen" and "vanguard"; sharing one word is not naming it. Deliberately
   looser than `fallback.find_mentions`' contiguous-run rule, because handling
   rephrasing is the planner's whole purpose.
2. **An explicit decline channel.** The prompt now tells the model to return an
   empty plan when no relation can express the question — naming colour, diet,
   appearance, feelings and motive as examples — and says plainly that
   declining is correct. `validate_plan` reports an empty relation list as a
   decline, not an error.
3. **A closed answer-type vocabulary.** An unrecognised word becomes "no type
   hint" rather than a filter.

Verified after the fix: both nonsense questions return `no_template_match`, and
*"Tell me where the Gravemaw Wyrm sleeps at night"* still routes correctly to
Marrowwell Abbey.

**A second failure found the same hour.** The suite went from ~200s to over
420s with no test added. Cause: an `OPENROUTER_API_KEY` had appeared in `.env`,
and every test whose question reached a routing miss was making live model
calls — spending daily quota to produce results that depended on a provider
being up. Fixed by making `use_planner` default to **False**: the LLM tier is
opted into, never out of. Deterministic-first as a default rather than as a
comment.

**Kept, because it will recur.** Both failures are the same shape: a component
that is correct in isolation becomes wrong once it is wired to something real.
Neither showed up in a unit test. Both showed up within minutes of running the
thing against the actual world — which is the same lesson the sister team wrote
down after Docker (ADR-022 in their repo), arrived at independently here.

---

## F-026 — A typo reporter that calls a correctly-spelled name a typo

**What we tried.** The near-miss reporter of ADR-021: on a routing miss, scan
word windows, and if the resolver classifies one as `AMBIGUOUS` at ≥0.90,
report the candidates instead of returning a bare `no_template_match`. Guarded
by `_strip_possessive`, which was written *specifically* because
`Ederon Fellgard's` scored 0.938 against the real name and was announced as a
typo on a question that spelled it perfectly.

**What killed it.** Re-running `python -m comparison.harness` against the frozen
55-question set — not a unit test — found the same bug in the form the guard
does not cover. Three of 49 answerable questions:

```
rb_008  isolde mournvales group won what war
rb_016  ederon fellgards faction won which accord
rb_028  what war did ravena stormwells lot end up winning
```

All three names are spelled **correctly**. The user simply omitted the
apostrophe. `_strip_possessive` strips `'s`, `’s`, `'` and `’` — not a bare
trailing `s` — so the span reaches the resolver as `isolde mournvales`, scores
0.970 against `Isolde Mournvale`, and the system announces *"'isolde
mournvales' is not a name in the corpus."*

MEASURED, by resolving both forms directly:

```
isolde mournvales   AMBIGUOUS      isolde mournvale   NORMALISED (resolved)
ederon fellgards    AMBIGUOUS      ederon fellgard    NORMALISED (resolved)
ravena stormwells   AMBIGUOUS      ravena stormwell   NORMALISED (resolved)
```

`rb_016` is the sharpest case: it previously returned `relation_unavailable`, a
*more specific and more correct* diagnosis, and the new reporter replaced it
with a spelling complaint. That is a regression in diagnosis quality, on a
change whose entire purpose was to diagnose better.

**The lesson.** *A guard written for one surface form of a problem does not
cover the problem.* `_strip_possessive` was added after this exact failure with
an apostrophe, and its docstring says so. Nobody asked which other spellings of
"possessive" exist. The test suite could not catch it — all 298 pass — because
the case only appears in questions written by someone other than the person who
wrote the guard, which is what the frozen set is for.

**Second lesson, about measurement hygiene.** `626631e`'s commit message
records the frozen set as "unchanged where it matters: 17 correct, 26 complete
evidence" — true, and it checked arm C. It did not check arm A, where the
count moved 35 → 33 and these three questions changed status. A summary metric
held steady while a per-question behaviour regressed underneath it. Diff the
per-question records, not just the totals.

**Status: closed by ADR-025.** The obvious fix — strip a bare trailing `s` —
was withheld here because it is not obviously safe against plurals and against
names that legitimately end in `s`. ADR-025 is that measurement: 11 real
entity names end in `s`, none of their bare-`s`-stripped forms collide with a
different entity, and the fix is scoped to *suppress* a false suggestion
rather than *generate* new ones — it never widens what counts as a typo, only
narrows a false positive. `rb_016` now returns `relation_unavailable` again,
the more specific diagnosis this entry names as correct; `rb_008` and `rb_028`
return `no_template_match`. No answer's correctness changed. Left here rather
than deleted, per this file's own rule: a mistake fixed is still worth the
record of how it was found.

## F-027 — A graph that read direction from the field name and ignored the cell saying otherwise

**What we tried.** `config/relations.yaml` maps each infobox field name to a
relation *and a direction*, and `build_graph` read direction from that map
alone. It is the obvious design and it is right for 264 of 267 edges.

**What killed it.** Tracing why `rb_044` fails. Its hand-traced gold path opens
`Ignatz Ashgrove the Oathless --mentor_of--> Ignatz Marrowgate`, and the built
graph had that edge pointing the other way. The row is

```
| Mentor | Mentor of [[Ignatz Marrowgate]] |
```

The field name `Mentor` is mapped reverse; the cell says `Mentor of`, which is
forward. The builder never looked at the cell, even though `parse_cell` had
already extracted `mentor of` into its closed `RELATION_VERBS` set. Three edges
were inverted — 3 of 267, and **3 of 8 `mentor_of` edges**, so 37% of that
relation was backwards.

The worst part is what it looked like from outside: a well-formed edge with a
real document, a real field name, a real row index and a real raw cell. Every
provenance field ADR-016 requires was present and correct. Only the arrow was
wrong. Nothing in the summary output, the tests, or the harness said so.

**What we did instead.** ADR-023: the cell's verb outranks the field name when
it names the same relation, and every flip is counted in
`Graph.direction_overrides` and printed. The rejected cheaper fix — deleting
`Mentor` from the reverse list — is recorded there too.

**What it cost, honestly.** Nothing on the scoreboard.
`python -m comparison.harness` is byte-identical before and after: 17 correct,
26 complete evidence. `rb_044` still fails, for an unrelated reason (the cue
router has no `mentor_of` cue for *"apprentice of"*). The edge is now true and
no question yet asks it. That is the whole lesson: a wrong edge is not detected
by the score, and waiting for a score to reveal it means shipping a confident
citation for a false fact.

**Generalises to.** Any place where two sources in the corpus state the same
thing at different specificity and the code silently prefers one. We now have
two: emphasis-stripping (ADR-012) and this. Worth a sweep for a third.


---

## F-028 - A status the demo could never reach, telling judges a real person did not exist

**Approach.** `EvidenceStatus.OUTSIDE_STRUCTURED_COVERAGE` exists to separate
two very different declines: "the corpus has never heard this name" and "this
is a real, documented entity that the wiki-infobox-only graph (ADR-016) has no
node for". ADR-017 introduced it with Halvard Cindervale as the worked example -
tier-1 codex prose, an ephemera contract, a faction membership, and no wiki
infobox.

`engine.answer_question` can only draw that distinction by scanning evidence
units, so the check is guarded: `if evidence_units is not None`.

**Result.** `src/ui/server.py` never passed them. Measured with the UI's exact
call signature, "Which faction won the war that Halvard Cindervale was a member
of?" returns **`UNRESOLVED_ENTITY`** - whose gloss on screen reads "does not
appear anywhere in the corpus - most likely a typo or an invented name."

He appears **21 times**, across three collections and three authority tiers:

    codex      5 passages, 1 doc,  tier 1   codex/the_annals_of_the_ashen_era#198
    wiki       8 passages, 2 docs, tier 2   wiki/fenthrone.md, wiki/the_ashen_vanguard.md
    ephemera   8 passages, 3 docs, tier 4   contract + petition (incl. a scan)

So the demo's most defensible decline - the one that explains an *architectural
boundary we chose* rather than a gap in the corpus - was unreachable, and in its
place the system confidently told a judge that a documented person was probably
a typo. Exactly the confidently-wrong-with-a-straight-face failure this project
exists to prevent, in the component built to prevent it.

**Why it failed.** The guard is correct and the wiring was never done. Nothing
caught it because no test asserted the status was *reachable through the path
the demo actually uses* - the engine tests pass `evidence_units` directly, so
they exercised a code path the product did not. A status can be fully
implemented, fully tested, and still dead in the only place it matters.

**What changed.** `Engine.__init__` loads evidence units at startup (~5s, once,
`ingest()`) and passes them on every call.
`tests/test_declines.py::test_outside_coverage_is_unreachable_without_evidence_units`
pins the underlying distinction, and
`::test_the_ui_engine_loads_what_outside_coverage_needs` asserts the
`Engine` signature that fixes it - so removing the wiring to save 5 seconds of
startup fails the suite with a message saying why. The page now names the
collections, quotes a passage from each with its evidence id and locator, and
points at `src/graph/build.py`'s `if unit.collection == "wiki":` as the line
that draws the boundary.

**The general lesson.** Two of this project's failure entries are now the same
shape: F-021's `PATH_MISSING_ATTRIBUTE` was unreachable dead code, and this one
was unreachable in production while live in tests. Both were *named states that
could not occur*. A named state deserves a test that reaches it the way the
product does, not the way the unit test finds convenient.

