# Checkpoint: baseline

> ### PROVISIONAL - ground truth is not fully verified
>
> 9 of 9 scoreable questions are not yet `confirmed`.
> ADR-014 requires **two independent reviewers** per entry; the breakdown below
> shows where each one stands.
>
> Key status: **2 draft**, **6 single_review**, **1 unresolved**
>
> Every number below is provisional. Do not quote it in the report, the video,
> or a decision until the entries are confirmed - see `eval/verification/` for
> the review pack.


- run at `2026-08-29T23:00:01` in 0.7s
- commit `7251073`, Python 3.11.16
- schema version 2
- **0 LLM call(s)**, 20 served from cache

## Score

| Track | Correct | Total |
|---|---|---|
| 1B | 2 | 7 |
| 1C | 2 | 2 |
| **all scored** | **4** | **9** |

Mean evidence recall: **0.361**  
Mean evidence precision: **0.281** (ceiling is `len(expected)/k`, not 1.0 - see `eval/scoring.py`)

**Complete evidence: 0/9** - questions where retrieval reached *every* document the answer requires. For a multi-hop question this is the number that matters: an answer produced from half the required evidence is a right answer by the wrong route, which `answer_key.json` asks us to count as a retrieval failure.

## Not scored

11 question(s) have no traced answer in the key and are recorded but never counted. They are listed here rather than dropped, so the denominator is always visible.

- `1a_v12` (1A) - What is the central emblem on the banner of House Morvain?
- `1a_v06` (1A) - In the portrait of Ignatz Ashgrove the Oathless, what object are they holding?
- `1a_008` (1A) - According to the official threat-classification plate, what numerical rating is assigned to the creature known as the Weeping Lurker?
- `1a_004` (1A) - According to the figure plate detailing weapon binding, how many shards of will are required to attune The Thrice-Bound Edge?
- `1a_013` (1A) - On the figure plate depicting 'The Cinder-Wrought Aegis', what attunement cost is listed for this entity?
- `1a_v11` (1A) - What is the central emblem on the banner of The Ashen Vanguard?
- `1a_v07` (1A) - In the portrait of Aldous Wrenfield the Last Warden, what object are they holding?
- `1a_009` (1A) - According to the figure plate, what is the recorded garrison strength of Greyfell Citadel?
- `1a_007` (1A) - According to the figure plate, what is the attunement cost listed for the Thrice-Bound Lantern?
- `1a_v21` (1A) - What motif is engraved on Gauntlet of Sorrowfell in its official illustration?
- `1a_001` (1A) - According to the figure plate illustrating Emberdeep’s forces, what is the recorded total of its garrison strength?

## Per question

`answers` is how many distinct answers the key accepts - `any_of` questions have more than one, and returning any of them is correct.

| qid | key status | correct | category | answers | conflict | ev. recall | ev. prec |
|---|---|---|---|---|---|---|---|
| `1b_007` | single_review | no | retrieval_miss | 1 (single) | n/a | 0.00 | 0.00 |
| `1b_006` | unresolved | yes | correct | 14 (any_of) | n/a | 0.33 | 0.25 |
| `1b_022` | single_review | no | retrieval_miss | 1 (single) | n/a | 0.00 | 0.00 |
| `1b_013` | single_review | no | partial_retrieval | 1 (single) | n/a | 0.50 | 0.50 |
| `1b_005` | single_review | yes | correct | 1 (single) | n/a | 0.50 | 0.20 |
| `1b_009` | single_review | no | negated_gold | 1 (single) | n/a (answer wrong) | 0.50 | 0.33 |
| `1b_003` | single_review | no | retrieval_miss | 1 (single) | n/a | 0.00 | 0.00 |
| `1c_000` | draft | yes | correct | 1 (single) | n/a | 0.67 | 0.50 |
| `1c_003` | draft | yes | correct | 1 (single) | n/a | 0.75 | 0.75 |

### Conflict handling

Questions where the corpus contradicts itself and an answer must say so. Scored separately from correctness on purpose: saying the right thing and representing a disputed claim honestly are different achievements.

- `1b_009`: **n/a (answer wrong)** - The answer was already incorrect, so how it handled the dispute is not meaningfully assessable. Scored separately rather than compounded.

### Categories present in this run

- **correct** - An acceptable answer appeared and was not negated.
- **negated_gold** - The gold string appeared but inside a negation - the over-crediting trap. A substring scorer would have marked this correct.
- **retrieval_miss** - Wrong, and retrieval reached none of the required documents.
- **partial_retrieval** - Wrong, and retrieval reached some but not all required documents - the join failure sub-track 1B exists to fix.

## Detail

### `1b_007` - retrieval_miss

**Q.** Which accord was ultimately won by the faction of which Ederon Fellgard is a member?

**Expected.** The Leaden Accord

**Predicted.** Based on the provided passages, there is no mention of **Ederon Fellgard** or which faction he belongs to. Therefore, the provided sources do not contain enough information to answer the question.

- matched: `-`
- required documents: `wiki/ederon_fellgard.md`, `wiki/the_iron_ring_cartel.md`, `wiki/the_leaden_accord.md`
- reached: **none**
- retrieved: `wiki/the_accord_of_mournthrone.md`, `wiki/the_ashen_vanguard.md`, `wiki/the_bleeding_crown.md`, `codex/the_annals_of_the_ashen_era`

### `1b_006` - correct

**Q.** Which individual was a member of the faction that ultimately won the War of Drowned Light?

**Expected.** Ignatz Fellgard

**Predicted.** Brannoc Palefroth [2], [3]

- matched: `Brannoc Palefroth`
- required documents: `wiki/the_war_of_drowned_light.md`, `wiki/the_silent_choir.md`, `wiki/ravena_stormwell.md`
- reached: `wiki/the_war_of_drowned_light.md`
- retrieved: `wiki/the_ashen_vanguard.md`, `wiki/the_winter_reckoning.md`, `wiki/the_war_of_drowned_light.md`, `wiki/the_bleeding_crown.md`

### `1b_022` - retrieval_miss

**Q.** Which war did Ravena Stormwell's own faction ultimately win?

**Expected.** The War of Drowned Light

**Predicted.** Based on the provided passages, there is no mention of Ravena Stormwell or her faction, so it is impossible to answer which war her faction won using only these sources.

- matched: `-`
- required documents: `wiki/ravena_stormwell.md`, `wiki/the_war_of_drowned_light.md`
- reached: **none**
- retrieved: `wiki/the_ashen_vanguard.md`, `wiki/the_war_of_endless_vigil.md`, `wiki/the_winter_reckoning.md`, `wiki/the_bleeding_crown.md`

### `1b_013` - partial_retrieval

**Q.** Whose dominion encompasses the lair of the Gravemaw Wyrm?

**Expected.** The Bleeding Crown

**Predicted.** Based on the provided sources, the text does not state whose dominion encompasses Marrowwell Abbey (the lair of the Gravemaw Wyrm). The records identify no affiliation with any faction, household, order, or organized host [1, 5].

- matched: `-`
- required documents: `wiki/gravemaw_wyrm.md`, `wiki/marrowwell_abbey.md`
- reached: `wiki/gravemaw_wyrm.md`
- retrieved: `wiki/gravemaw_wyrm.md`, `codex/codex_vaeloria_ii_armory_of_relics_and_bestiary`

### `1b_005` - correct

**Q.** Which war was won by the organization that included Isolde Mournvale as one of its members?

**Expected.** The War of Drowned Light

**Predicted.** The War of Drowned Light was recorded as won by The Silent Choir, the organization of which Isolde Mournvale was a member [1][2].

- matched: `The War of Drowned Light`
- required documents: `wiki/isolde_mournvale.md`, `wiki/the_war_of_drowned_light.md`
- reached: `wiki/isolde_mournvale.md`
- retrieved: `chronicles/the_ashen_chronicles_volume_i_the_kindling_years`, `wiki/isolde_mournvale.md`, `wiki/the_ashen_vanguard.md`, `wiki/the_bleeding_crown.md`, `codex/the_annals_of_the_ashen_era`

### `1b_009` - negated_gold

**Q.** In what way is Halvard Crowhurst connected to the victors of the Purge of Blackport?

**Expected.** He is a recorded member of The Iron-Ring Cartel, which the Purge of Blackport's own article names as victor - though the Cartel's own article disputes that it won.

**Predicted.** Based on the provided passages, no connection between Halvard Crowhurst and the victors of the Purge of Blackport is established. The text only records that Halvard Crowhurst is a member of The Iron-Ring Cartel, which was a belligerent in the Purge of Blackport, but does not identify the victors of that conflict [3].

- matched: `-`  |  **negated match: `member of the Iron-Ring Cartel`**
- required documents: `wiki/the_purge_of_blackport.md`, `wiki/the_iron_ring_cartel.md`
- reached: `wiki/the_iron_ring_cartel.md`
- retrieved: `wiki/halvard_vane_the_grave_sworn.md`, `wiki/the_bleeding_crown.md`, `wiki/the_iron_ring_cartel.md`

### `1b_003` - retrieval_miss

**Q.** To which shadowed redoubt must one journey to examine the relic long borne by Cerys Sablewood the Ashen since 356 AS?

**Expected.** Gloamreach

**Predicted.** To examine **The Cinder-Wrought Aegis** (the relic borne by Cerys Sablewood the Ashen since 356 AS [1]), one must journey to **Vharencrag Fortress**, where the relic was recorded in the field report [2]. (If conveyance of the relic is required under contract, it is to be taken to **Embercrag Fortress** in the Shattered Vale [3]).

**Sources:** [1], [2], [3]

- matched: `-`
- required documents: `wiki/cerys_sablewood_the_ashen.md`, `wiki/the_cinder_wrought_aegis.md`
- reached: **none**
- retrieved: `chronicles/the_ashen_chronicles_volume_ii_the_long_reprisal`, `ephemera/field_report_concerning_vharencrag_fortress.docx`, `ephemera/contract_concerning_chalice_of_ashdeep.txt`, `chronicles/the_ashen_chronicles_volume_i_the_kindling_years`

### `1c_000` - correct

**Q.** State the precise year in the Age of Shadows that marks the true founding of Gloamreach.

**Expected.** 246 AS

**Predicted.** The true founding of Gloamreach is **246 AS** [1][2]. 

*(Note: While contract ephemera claims 286 AS [3], the established gazetteer record explicitly rejects alternative accounts in favor of 246 AS [1]).*

- matched: `246 AS`
- required documents: `codex/codex_vaeloria_i_gazetteer_of_the_sundered_realms`, `ephemera/contract_concerning_the_sceptre_of_final_winter.txt`, `wiki/gloamreach.md`
- reached: `codex/codex_vaeloria_i_gazetteer_of_the_sundered_realms`, `ephemera/contract_concerning_the_sceptre_of_final_winter.txt`
- retrieved: `codex/codex_vaeloria_i_gazetteer_of_the_sundered_realms`, `ephemera/contract_concerning_the_sceptre_of_final_winter.txt`, `chronicles/the_ashen_chronicles_volume_ii_the_long_reprisal`, `ephemera/field_report_concerning_gloamreach.txt`

### `1c_003` - correct

**Q.** In which year was the 'Gauntlet of Sorrowfell' actually forged?

**Expected.** 391 AS

**Predicted.** The authoritative record states the Gauntlet of Sorrowfell was forged in **391 AS** [1, 2]. 

However, accounts conflict across sources:
* Another sermon lists its forging year as **360 AS** [5].
* Other texts state that its forging date is unrecorded or disputed [3, 4].

- matched: `391 AS`
- required documents: `codex/codex_vaeloria_ii_armory_of_relics_and_bestiary`, `ephemera/sermon_concerning_malchior_cindervale_the_flame_touched.txt`, `ephemera/quartermaster_ledger_concerning_crookvale.txt`, `wiki/gauntlet_of_sorrowfell.md`
- reached: `codex/codex_vaeloria_ii_armory_of_relics_and_bestiary`, `ephemera/sermon_concerning_malchior_cindervale_the_flame_touched.txt`, `wiki/gauntlet_of_sorrowfell.md`
- retrieved: `codex/codex_vaeloria_ii_armory_of_relics_and_bestiary`, `ephemera/sermon_concerning_ignatz_fellgard.txt`, `wiki/gauntlet_of_sorrowfell.md`, `ephemera/sermon_concerning_malchior_cindervale_the_flame_touched.txt`

---

Reproduce with:

```bash
python -m eval.run_eval --checkpoint baseline
```

The full record, including the text of every retrieved chunk, is in the matching `.json` file beside this one.
