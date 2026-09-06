# Known limitations

Honest account of what the system does not do, and of defects in the source
material that we cannot fix from our side. Kept current as we find things.

---

## Corpus defects (not ours to fix)

### Scanned tables are clipped in the source images

Several of the 17 scanned ephemera render wide tables that run off the right
edge of the page image. For example, in
`muster_roll_concerning_hollowvale.scan.pdf` the title reads
`MUSTER ROLL OF HOLLOWVALE, HOLLOWREACH, AND THE SALT-BLIND LE` and the table
header ends `| Strength or Threat | Rem`, both cut mid-word by the page boundary.

We verified this is the source image, not our extraction or our OCR: the JPEG
embedded in the PDF is 1240x1754 and the text is physically absent from it. The
transcription is faithful to what is visible, which is the correct behaviour -
inventing the missing words would be worse.

**Impact: low.** In the cases we inspected, the figures also appear in the
surrounding prose, which is not clipped. The Hollowvale garrison, missing from
the clipped table row, is stated plainly in the warden's notes below it: *"The
7,594 troops recorded against it are its declared garrison."*

**Mitigation:** none attempted. A system that guessed at clipped text would
fabricate evidence, which is precisely the failure mode this project exists to
avoid.

### A corpus filename is truncated mid-word

`ephemera/interrogation_record_concerning_isolde_fellgard_the_unforgiv.txt` is
cut short — the subject is Isolde Fellgard the Unforgiven, who has a wiki page
and a graph node, reached under her full name from
`letter_concerning_isolde_fellgard_the_unforgiven.txt`.

The same class of defect as the clipped scan tables above: the source is
truncated and we do not extend it. Exact-match resolution (ADR-011) means the
truncated slug resolves to nobody rather than being fuzzily attached to the
right person, which is the correct trade — a threshold low enough to join
`the_unforgiv` to `the_unforgiven` is also low enough to join
`caedmon_fellgard` to `ederon_fellgard`, which are 0.839 similar and different
people (F-010).

**Impact: none measured.** The document is still ingested, still searched, and
still cited; only the filename-derived subject slug fails to resolve, and the
same subject is reachable from the untruncated sibling document.

---

## System limitations

### One entity in the corpus has no node in the graph

The graph's nodes come from wiki infobox rows, so an entity the wiki never
tabulates has no node, and a question about it declines by construction rather
than on evidence. **Measured, 6 Sep** — `python -m eval.probes.entity_reachability`,
ADR-030:

Of the **79** non-wiki documents that declare their own subject in the filename
(`<doctype>_concerning_<subject>`, which is the archive stating who a document
is about), **77 reach a graph node and 2 do not**. One of those two is a corpus
filename truncation, not a gap (below). So **exactly one entity the corpus
treats as first-class has no node: Halvard Cindervale** — named in 21 evidence
units, including five in the tier-1 codex Annals and three ephemera documents
titled after him.

The cause is ours, not the corpus's, and it is a single row (**F-032**):
`wiki/the_ashen_vanguard.md` writes `| Members | Halvard Cindervale; Voltaire
Hollowmere; Orin Veyra |` with no `[[links]]`, and an unlinked infobox cell can
only resolve against entities that already own a wiki page. Not fixed three days
from the deadline: it moves the graph to 118/264, reddens `tests/test_diagram.py`,
invalidates the 117/261 quoted in five documents, and changes no measured answer.

**Impact: low, and visible to the user rather than hidden.** Nothing in the
answer key, the frozen 55 or the dev 1B seven traverses this entity. A question
about him returns `EvidenceStatus.OUTSIDE_STRUCTURED_COVERAGE`, which the demo
UI renders as *"Present in the corpus, absent from the graph"*, names
`src/graph/build.py` and "wiki infobox rows only" as the reason, and quotes the
codex, ephemera and wiki passages with their authority tiers. Note that this
status needs the evidence-unit scan the UI's `Engine` loads at startup; the bare
`python -m src.query.engine` CLI degrades the same question to
`unresolved_entity`.

**A separate, weaker measurement, recorded so nobody re-derives it and
overstates it.** A capitalised-multi-word-span scan of the 27,415 non-wiki
paragraph and page units yields 741 distinct candidate names, of which 579 reach
no node. **That 579 is not an entity count.** Fifteen were sampled and
hand-checked against their documents and **0 of the 15 is a genuine entity** —
they are document titles, section headings, form-field labels, adjacent codex
field values, and verbs or conjunctions swept in beside names that do resolve.
Quote the 1 of 79, not the 579.

### OCR output is model-dependent

Transcriptions were produced by three different Gemini models, because the
free-tier daily quota is per model and we rotate through them (see ADR-007).
One document was transcribed across two models. Output is committed to
`ocr_cache/` so results are pinned and reproducible, but a re-run with
`--force` on a different day could produce slightly different text.

`OCRResult.model` records every model that contributed to each document, rather
than claiming a single one.

### Ephemera scans are treated as independent documents

Two scans share a filename stem with a digital document
(`field_report_concerning_cerys_sablewood_the_ashen`,
`interrogation_record_concerning_hesper_wrenfield`). Because same-stem ephemera
are demonstrably different documents (ADR-003), we treat the scan as its own
document rather than as an image of the digital one. If the corpus intended them
as the same document, we double-count those two sources.

We judged this the safer error: treating two genuinely different documents as
one hides a competing claim from the conflict resolver, whereas treating one
document as two slightly over-weights it. Worth re-checking once the OCR text
can be compared against the digital twin.

### Index build is slow on a fresh Voyage account

Roughly two hours, throttled to the 3 requests / 10,000 tokens per minute that a
Voyage account without a payment method receives. Adding a card removes this
(the 200M free tokens still apply; the card is identity verification only) and
`VOYAGE_TIER=paid` disables the throttle. Embeddings are cached by content hash,
so this is a one-time cost.
