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

---

## System limitations

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
