# Answer key verification pack

9 traced questions require independent confirmation by **two** reviewers before any number scored against them may be quoted.

## How to use this

1. Two reviewers work **independently**. Do not compare notes until both    have filled in their column.
2. For each question, read the corpus text quoted beneath each hop and    decide whether the document actually supports the claim.
3. Check the citation itself, not just the excerpt - open the file if    anything looks off. The excerpt is a convenience, not the evidence.
4. Mark `unsure` freely. An unsure entry is information; a guessed    confirmation destroys the thing this pack exists to protect.
5. When both columns are filled, record the verdict and update    `verified_by` in `eval/answer_key.json` to a list of the two names.

## The one rule

> Never change an answer to make the system score better.

If the system disagrees with a confirmed key entry, the system is wrong. If review shows the key itself was wrong, fix the key and say so in `docs/decisions.md` - being wrong cheaply is the process working, but quietly moving the target is not.

The excerpts below come from the ingestion pipeline - the same text the system sees. They are **not** produced by `eval/probes/corpus_shape.py`; checking our parser against our parser would confirm nothing.

---

## `1b_003`

**Question.** To which shadowed redoubt must one journey to examine the relic long borne by Cerys Sablewood the Ashen since 356 AS?

**Key says the answer is.** `Gloamreach`

### Claimed path

**Hop 1.** `Cerys Sablewood the Ashen` --[wields]--> `The Cinder-Wrought Aegis`
  cited: `wiki/cerys_sablewood_the_ashen.md`, field `Wields`
  note: qualified 'since 356 AS', matching the question

> Corpus text at `wiki/cerys_sablewood_the_ashen.md#4`:

> | Field | Value | |---|---| | Name | [[Cerys Sablewood the Ashen]] | | Role | Major Master of Coin | | Born | 330 AS | | Secret | Unacknowledged heir to the [[Bleeding Crown]] | | Member of | [[The Ashen Vanguard]] | | Command | [[Cindermere Hold]], since 359 AS | | Wields | [[The Cinder-Wrought Aegis]], since 356 AS | | Mentor of | [[Halvard Sablewood]] |

> Corpus text at `wiki/cerys_sablewood_the_ashen.md#2`:

> [[Cerys Sablewood the Ashen]] is a major Master of Coin, born in 330 AS. Cerys is a member of [[The Ashen Vanguard]], commands [[Cindermere Hold]] since 359 AS, and has wielded [[The Cinder-Wrought Aegis]] since 356 AS. Cerys is also the mentor of [[Halvard Sablewood]]. Beneath the controlled duties of the office, Cerys carries a concealed royal inheritance: Cerys is the unacknowledged heir to the [[Bleeding Crown]].

**Hop 2.** `The Cinder-Wrought Aegis` --[housed_in]--> `Gloamreach`
  cited: `wiki/the_cinder_wrought_aegis.md`, field `Place of housing`

> Corpus text at `wiki/the_cinder_wrought_aegis.md#3`:

> | Field | Value | |---|---| | Artifact class | regalia | | Place of forging | [[Embermarch]] | | Place of housing | [[Gloamreach]] |

> Corpus text at `wiki/the_cinder_wrought_aegis.md#13`:

> Nor does the known housing of the **[[The Cinder-Wrought Aegis]]** in [[Gloamreach]] establish that the location and the artifact share an institutional or political affiliation. [[Gloamreach]] is the artifact's recorded place of housing, while [[Embermarch]] is its recorded place of forging. These statements identify locations associated with the regalia and should not be expanded into claims about ownership or patronage without support from the [[Annals/Codex]].

### Tracer's notes

> Hop 2 uses the field name 'Place of housing', not 'Housed in'. Both spellings exist in the corpus for the same relation.

### Reviewer sign-off

| | Reviewer 1 | Reviewer 2 |
|---|---|---|
| name | | |
| date | | |
| answer correct? (yes / no / unsure) | | |
| path correct? (yes / no / unsure) | | |
| answer set complete? (yes / no / n/a) | | |
| comments | | |

**Verdict** (leave blank until both reviewers have filled the column above): 
`confirmed` / `rejected` / `unresolved`

If the two reviewers disagree, the verdict is `unresolved`. Investigate and record what settled it - do not average the two opinions, and do not change the answer to match the system's output.

---

## `1b_005`

**Question.** Which war was won by the organization that included Isolde Mournvale as one of its members?

**Key says the answer is.** `The War of Drowned Light`

### Claimed path

**Hop 1.** `Isolde Mournvale` --[member_of]--> `The Silent Choir`
  cited: `wiki/isolde_mournvale.md`, field `Member of`

> Corpus text at `wiki/isolde_mournvale.md#1`:

> [[Isolde Mournvale]] is a minor figure of the [[Ashen Era]], born in 341 AS. She serves as a falconer and is a member of [[The Silent Choir]]. Her known service is located at [[Stormmarch]]. No canonical physical details are recorded for [[Isolde Mournvale]], and her visual identity is associated only with the work of a falconer. Her canonical temperament is likewise unrecorded.

> Corpus text at `wiki/isolde_mournvale.md#3`:

> | Field | Value | |---|---| | Name | [[Isolde Mournvale]] | | Role | Falconer | | Born | 341 AS | | Member of | [[The Silent Choir]] | | Serves at | [[Stormmarch]] |

**Hop 2.** `The Silent Choir` --[victor_of]--> `The War of Drowned Light`
  cited: `wiki/the_war_of_drowned_light.md`, field `Victor`
  note: REVERSE lookup - the Silent Choir's own page has no 'Victor of' row, so this edge exists only on the conflict page

> Corpus text at `wiki/the_war_of_drowned_light.md#2`:

> The [[The War of Drowned Light]] was a conflict of concealed treachery, attrition, and unresolved vengeance. It began in **225 AS** and ended in **235 AS**, producing **64617 casualties** before collapsing into a decade of guerrilla reprisals. Although the conflict is recorded as a victory for [[The Silent Choir]], its origin remained obscured: the spark that started the war was secretly staged by [[The Silent Choir]]. The war was waged at [[Cindermere Hold]] in **228 AS**, devastated [[Gloamreach]] in **227 AS**, and was waged at [[Greyfell Citadel]] in **233 AS**. Its visual identity is associated with drowned radiance, broken banners, and remembrance through reprisals rather than triumph.

> Corpus text at `wiki/the_war_of_drowned_light.md#4`:

> | Field | Value | |---|---| | Conflict | [[The War of Drowned Light]] | | Began | 225 AS | | Ended | 235 AS | | Casualties | 64617 | | Outcome | Collapsed into a decade of guerrilla reprisals | | Victor | [[The Silent Choir]] | | Secret truth | The spark that started it was staged by [[The Silent Choir]] | | Waged at | [[Cindermere Hold]] in 228 AS; [[Greyfell Citadel]] in 233 AS | | Devastated | [[Gloamreach]] in 227 AS |

### Tracer's notes

> Proves the reverse-traversal requirement. Unlike the Iron-Ring Cartel, the Silent Choir does not record its own victories, so the graph is not symmetric and hop 2 cannot be read off the faction page.

### Reviewer sign-off

| | Reviewer 1 | Reviewer 2 |
|---|---|---|
| name | | |
| date | | |
| answer correct? (yes / no / unsure) | | |
| path correct? (yes / no / unsure) | | |
| answer set complete? (yes / no / n/a) | | |
| comments | | |

**Verdict** (leave blank until both reviewers have filled the column above): 
`confirmed` / `rejected` / `unresolved`

If the two reviewers disagree, the verdict is `unresolved`. Investigate and record what settled it - do not average the two opinions, and do not change the answer to match the system's output.

---

## `1b_006`

**Question.** Which individual was a member of the faction that ultimately won the War of Drowned Light?

**Key says the answer is.** `Ravena Stormwell`

This is a **set-valued** question - the key lists 14 acceptable answers. Check that the set is complete as well as that its members are right.

### Claimed path

**Hop 1.** `The War of Drowned Light` --[victor]--> `The Silent Choir`
  cited: `wiki/the_war_of_drowned_light.md`, field `Victor`

> Corpus text at `wiki/the_war_of_drowned_light.md#2`:

> The [[The War of Drowned Light]] was a conflict of concealed treachery, attrition, and unresolved vengeance. It began in **225 AS** and ended in **235 AS**, producing **64617 casualties** before collapsing into a decade of guerrilla reprisals. Although the conflict is recorded as a victory for [[The Silent Choir]], its origin remained obscured: the spark that started the war was secretly staged by [[The Silent Choir]]. The war was waged at [[Cindermere Hold]] in **228 AS**, devastated [[Gloamreach]] in **227 AS**, and was waged at [[Greyfell Citadel]] in **233 AS**. Its visual identity is associated with drowned radiance, broken banners, and remembrance through reprisals rather than triumph.

> Corpus text at `wiki/the_war_of_drowned_light.md#4`:

> | Field | Value | |---|---| | Conflict | [[The War of Drowned Light]] | | Began | 225 AS | | Ended | 235 AS | | Casualties | 64617 | | Outcome | Collapsed into a decade of guerrilla reprisals | | Victor | [[The Silent Choir]] | | Secret truth | The spark that started it was staged by [[The Silent Choir]] | | Waged at | [[Cindermere Hold]] in 228 AS; [[Greyfell Citadel]] in 233 AS | | Devastated | [[Gloamreach]] in 227 AS |

**Hop 2.** `The Silent Choir` --[has_member]--> `Ravena Stormwell`
  cited: `wiki/ravena_stormwell.md`, field `Member of`
  note: REVERSE lookup across all character pages

> Corpus text at `wiki/ravena_stormwell.md#1`:

> **Ravena Stormwell** is a minor character in the records of the Ashen Era who serves as a **Standard-Bearer**. She was born in **274 AS**, is a member of [[The Silent Choir]], and serves at [[Vharenford]]. No physical features or temperament are recorded for her. Instead, her visual identity is associated with the duty of a Standard-Bearer, making the office she performs more clearly documented than her individual appearance or personality.

> Corpus text at `wiki/ravena_stormwell.md#3`:

> | Field | Value | |---|---| | Name | [[Ravena Stormwell]] | | Role | Standard-Bearer | | Born | 274 AS | | Member of | [[The Silent Choir]] | | Serves at | [[Vharenford]] |

### Tracer's notes

> SET-VALUED, 14 valid answers, and membership is recorded in TWO disjoint places with no overlap between them: the faction page's 'Members' row lists 6 people, while 8 separate character pages carry 'Member of -> The Silent Choir'. Neither list mentions anyone from the other. A graph builder that reads only one direction loses more than half the membership edges. Found when the baseline answered 'Brannoc Palefroth' and our key wrongly scored it wrong - the key was reading only the character-page direction.

### Reviewer sign-off

| | Reviewer 1 | Reviewer 2 |
|---|---|---|
| name | | |
| date | | |
| answer correct? (yes / no / unsure) | | |
| path correct? (yes / no / unsure) | | |
| answer set complete? (yes / no / n/a) | | |
| comments | | |

**Verdict** (leave blank until both reviewers have filled the column above): 
`confirmed` / `rejected` / `unresolved`

If the two reviewers disagree, the verdict is `unresolved`. Investigate and record what settled it - do not average the two opinions, and do not change the answer to match the system's output.

---

## `1b_007`

**Question.** Which accord was ultimately won by the faction of which Ederon Fellgard is a member?

**Key says the answer is.** `The Leaden Accord`

### Claimed path

**Hop 1.** `Ederon Fellgard` --[member_of]--> `The Iron-Ring Cartel`
  cited: `wiki/ederon_fellgard.md`, field `Membership`

> Corpus text at `wiki/ederon_fellgard.md#3`:

> | Field | Value | |---|---| | Name | Ederon Fellgard | | Role | Sapper | | Born | 338 AS | | Membership | [[The Iron-Ring Cartel]] | | Service | [[Greyfell Citadel]] | | Physical traits | No canonical physical traits or distinctive visual features established | | Demeanor | No canonical temperament or emotional disposition established |

> Corpus text at `wiki/ederon_fellgard.md#7`:

> Ederon Fellgard is a member of [[The Iron-Ring Cartel]]. The membership is a direct part of the character's canonical identity. No rank, title, internal office, duration of membership, or reason for joining [[The Iron-Ring Cartel]] has been established. Likewise, the available material does not identify any particular superior, subordinate, associate, rival, or companion connected to Ederon Fellgard through that membership.

**Hop 2.** `The Iron-Ring Cartel` --[victor_of]--> `The Leaden Accord`
  cited: `wiki/the_iron_ring_cartel.md`, field `Victor of`
  note: cell is multi-valued: 'The Winter Reckoning; The Leaden Accord' - split on ';' then filter by type

> Corpus text at `wiki/the_iron_ring_cartel.md#4`:

> | Field | Value | |---|---| | Doctrine | Mercantile league running contraband through the ruined trade roads. | | Organization kind | merchant cartel | | Seat | [[Hollowreach]] | | Belligerent in | [[The Winter Reckoning]]; [[The Purge of Blackport]]; [[The Leaden Accord]] | | Victor of | [[The Winter Reckoning]]; [[The Leaden Accord]] | | Member | [[Halvard Crowhurst]] |

> Corpus text at `wiki/the_iron_ring_cartel.md#11`:

> The Iron-Ring Cartel was a **belligerent in The Leaden Accord** and the **victor of The Leaden Accord**. As with [[The Winter Reckoning]], the faction's record for [[The Leaden Accord]] includes both participation and victory. The combination of these entries presents the Cartel as an organization whose mercantile role coexists with an established belligerent presence.

### Tracer's notes

> TYPE FILTER REQUIRED. The Cartel won two conflicts; only The Leaden Accord is an accord. A system that ignores the word 'accord' has a 50% chance of answering The Winter Reckoning. Hop 1 uses field name 'Membership', not 'Member of'.

### Reviewer sign-off

| | Reviewer 1 | Reviewer 2 |
|---|---|---|
| name | | |
| date | | |
| answer correct? (yes / no / unsure) | | |
| path correct? (yes / no / unsure) | | |
| answer set complete? (yes / no / n/a) | | |
| comments | | |

**Verdict** (leave blank until both reviewers have filled the column above): 
`confirmed` / `rejected` / `unresolved`

If the two reviewers disagree, the verdict is `unresolved`. Investigate and record what settled it - do not average the two opinions, and do not change the answer to match the system's output.

---

## `1b_009`

**Question.** In what way is Halvard Crowhurst connected to the victors of the Purge of Blackport?

**Key says the answer is.** `He is a member of the Iron-Ring Cartel, the faction recorded as victor of the Purge of Blackport.`

### Claimed path

**Hop 1.** `The Purge of Blackport` --[victor]--> `Iron-Ring Cartel`
  cited: `wiki/the_purge_of_blackport.md`, field `Victor`

> Corpus text at `wiki/the_purge_of_blackport.md#2`:

> The **Purge of [[Blackport]]** was a conflict that began in **311 AS** and ended in **321 AS**. It caused **70,907 casualties**-a canonical casualty figure of **70907**-and ended with the **total rout of the aggressors**. The **[[Iron-Ring Cartel]]** emerged as the victor, specifically **The Iron-Ring Cartel**, although the concealed truth of the conflict is that the victors poisoned the wells of their own allies. Its visual identity is defined by [[Blackport]] under purge, the presence of the [[Iron-Ring Cartel]], and poisoned water; its character is one of merciless triumph soured by calculated betrayal.

> Corpus text at `wiki/the_purge_of_blackport.md#4`:

> | Field | Value | |---|---| | Conflict | The Purge of [[Blackport]] | | Began | 311 AS | | Ended | 321 AS | | Casualties | 70,907 | | Outcome | Ended with the total rout of the aggressors | | Victor | [[Iron-Ring Cartel]] | | Major setting | [[Blackport]] | | Related location and year | Waged at [[Fenspire]] in 319 AS | | Related region and year | Devastated [[Gloamreach]] in 320 AS | | Concealed truth | The victors poisoned the wells of their own allies |

**Hop 2.** `The Iron-Ring Cartel` --[has_member]--> `Halvard Crowhurst`
  cited: `wiki/the_iron_ring_cartel.md`, field `Member`

> Corpus text at `wiki/the_iron_ring_cartel.md#2`:

> The **The Iron-Ring Cartel** is a mercantile league running contraband through the ruined trade roads. Its organization is a **merchant cartel**, structured around commerce conducted across the remnants of the realm's trade routes. The Cartel is seated at [[Hollowreach]] and is recognized by a mercantile, hard-edged visual identity. Its demeanor is calculating and practical, with a stated comfort in operating beyond lawful trade. The Iron-Ring Cartel was a belligerent and victor in [[The Winter Reckoning]], a belligerent in [[The Purge of Blackport]], and a belligerent and victor in [[The Leaden Accord]]. [[Halvard Crowhurst]] is a member of The Iron-Ring Cartel.

> Corpus text at `wiki/the_iron_ring_cartel.md#4`:

> | Field | Value | |---|---| | Doctrine | Mercantile league running contraband through the ruined trade roads. | | Organization kind | merchant cartel | | Seat | [[Hollowreach]] | | Belligerent in | [[The Winter Reckoning]]; [[The Purge of Blackport]]; [[The Leaden Accord]] | | Victor of | [[The Winter Reckoning]]; [[The Leaden Accord]] | | Member | [[Halvard Crowhurst]] |

### Tracer's notes

> TWO TRAPS. (1) Alias: the conflict page writes '[[Iron-Ring Cartel]]' without the leading 'The', while every other reference writes '[[The Iron-Ring Cartel]]'. Without alias normalisation these are separate nodes and the join fails outright. (2) Source disagreement: the Cartel's own page lists the Purge of Blackport as a belligerency only, and names its victories as The Winter Reckoning and The Leaden Accord - so the conflict page and the faction page disagree about whether the Cartel won. The question's hedged phrasing ('in what way') appears deliberate. A strong answer surfaces the disagreement rather than asserting a clean victory. Halvard Crowhurst has NO wiki page of his own; he exists only as the object of a Member edge.

### Reviewer sign-off

| | Reviewer 1 | Reviewer 2 |
|---|---|---|
| name | | |
| date | | |
| answer correct? (yes / no / unsure) | | |
| path correct? (yes / no / unsure) | | |
| answer set complete? (yes / no / n/a) | | |
| comments | | |

**Verdict** (leave blank until both reviewers have filled the column above): 
`confirmed` / `rejected` / `unresolved`

If the two reviewers disagree, the verdict is `unresolved`. Investigate and record what settled it - do not average the two opinions, and do not change the answer to match the system's output.

---

## `1b_013`

**Question.** Whose dominion encompasses the lair of the Gravemaw Wyrm?

**Key says the answer is.** `The Bleeding Crown`

### Claimed path

**Hop 1.** `Gravemaw Wyrm` --[lair_in]--> `Marrowwell Abbey`
  cited: `wiki/gravemaw_wyrm.md`, field `Lair`

> Corpus text at `wiki/gravemaw_wyrm.md#2`:

> The **Gravemaw Wyrm** is a threat-rating 8 creature and a sky hunter whose presence makes open skies perilous wherever it ranges. It is a grave-associated predator, possessing a vast wyrm-like form, a pronounced maw, and a silhouette suited to hunting through the air. Relentlessly predatory, the Gravemaw Wyrm carries the cold inevitability of death from above. Its lair is recorded as [[Marrowwell Abbey]], making the abbey both a significant point of reference in accounts of the creature and a place of particular danger to those exposed beneath its hunting grounds.

> Corpus text at `wiki/gravemaw_wyrm.md#4`:

> | Field | Value | |---|---| | Name | Gravemaw Wyrm | | Threat rating | 8 | | Habit | Sky hunter | | Lair | [[Marrowwell Abbey]] |

**Hop 2.** `Marrowwell Abbey` --[ruled_by]--> `The Bleeding Crown`
  cited: `wiki/marrowwell_abbey.md`, field `Ruled by`

> Corpus text at `wiki/marrowwell_abbey.md#1`:

> [[Marrowwell Abbey]] is a rebuilt religious stronghold standing in [[The Gloaming Reach]]. Ruled by [[The Bleeding Crown]], it maintains a garrison of 6656 despite not being a core holding. Its rebuilt form presents a severe, marrow-white silhouette beneath the dim character of the Reach, while its overall demeanor combines religious austerity with military vigilance. The date of its founding is contested among sources and is not established here; readers seeking the authoritative treatment should consult the [[Annals]] and the [[Codex]].

> Corpus text at `wiki/marrowwell_abbey.md#3`:

> | Field | Value | |---|---| | Region | [[The Gloaming Reach]] | | Garrison strength | 6656 | | Status | Rebuilt; not a core holding | | Ruled by | [[The Bleeding Crown]] | | Appearance | Severe, marrow-white presence beneath the dim character of [[The Gloaming Reach]] | | Demeanor | Grimly steadfast; combines religious austerity with military vigilance |

### Tracer's notes

> Cleanest two-hop in the set: no aliases, no type filter, no disagreement. Useful as the smoke test for traversal.

### Reviewer sign-off

| | Reviewer 1 | Reviewer 2 |
|---|---|---|
| name | | |
| date | | |
| answer correct? (yes / no / unsure) | | |
| path correct? (yes / no / unsure) | | |
| answer set complete? (yes / no / n/a) | | |
| comments | | |

**Verdict** (leave blank until both reviewers have filled the column above): 
`confirmed` / `rejected` / `unresolved`

If the two reviewers disagree, the verdict is `unresolved`. Investigate and record what settled it - do not average the two opinions, and do not change the answer to match the system's output.

---

## `1b_022`

**Question.** Which war did Ravena Stormwell's own faction ultimately win?

**Key says the answer is.** `The War of Drowned Light`

### Claimed path

**Hop 1.** `Ravena Stormwell` --[member_of]--> `The Silent Choir`
  cited: `wiki/ravena_stormwell.md`, field `Member of`

> Corpus text at `wiki/ravena_stormwell.md#1`:

> **Ravena Stormwell** is a minor character in the records of the Ashen Era who serves as a **Standard-Bearer**. She was born in **274 AS**, is a member of [[The Silent Choir]], and serves at [[Vharenford]]. No physical features or temperament are recorded for her. Instead, her visual identity is associated with the duty of a Standard-Bearer, making the office she performs more clearly documented than her individual appearance or personality.

> Corpus text at `wiki/ravena_stormwell.md#3`:

> | Field | Value | |---|---| | Name | [[Ravena Stormwell]] | | Role | Standard-Bearer | | Born | 274 AS | | Member of | [[The Silent Choir]] | | Serves at | [[Vharenford]] |

**Hop 2.** `The Silent Choir` --[victor_of]--> `The War of Drowned Light`
  cited: `wiki/the_war_of_drowned_light.md`, field `Victor`
  note: REVERSE lookup

> Corpus text at `wiki/the_war_of_drowned_light.md#2`:

> The [[The War of Drowned Light]] was a conflict of concealed treachery, attrition, and unresolved vengeance. It began in **225 AS** and ended in **235 AS**, producing **64617 casualties** before collapsing into a decade of guerrilla reprisals. Although the conflict is recorded as a victory for [[The Silent Choir]], its origin remained obscured: the spark that started the war was secretly staged by [[The Silent Choir]]. The war was waged at [[Cindermere Hold]] in **228 AS**, devastated [[Gloamreach]] in **227 AS**, and was waged at [[Greyfell Citadel]] in **233 AS**. Its visual identity is associated with drowned radiance, broken banners, and remembrance through reprisals rather than triumph.

> Corpus text at `wiki/the_war_of_drowned_light.md#4`:

> | Field | Value | |---|---| | Conflict | [[The War of Drowned Light]] | | Began | 225 AS | | Ended | 235 AS | | Casualties | 64617 | | Outcome | Collapsed into a decade of guerrilla reprisals | | Victor | [[The Silent Choir]] | | Secret truth | The spark that started it was staged by [[The Silent Choir]] | | Waged at | [[Cindermere Hold]] in 228 AS; [[Greyfell Citadel]] in 233 AS | | Devastated | [[Gloamreach]] in 227 AS |

### Tracer's notes

> Same answer and same second hop as 1b_005, reached from a different character. Good pair for checking that traversal generalises rather than memorises.

### Reviewer sign-off

| | Reviewer 1 | Reviewer 2 |
|---|---|---|
| name | | |
| date | | |
| answer correct? (yes / no / unsure) | | |
| path correct? (yes / no / unsure) | | |
| answer set complete? (yes / no / n/a) | | |
| comments | | |

**Verdict** (leave blank until both reviewers have filled the column above): 
`confirmed` / `rejected` / `unresolved`

If the two reviewers disagree, the verdict is `unresolved`. Investigate and record what settled it - do not average the two opinions, and do not change the answer to match the system's output.

---

## `1c_000`

**Question.** State the precise year in the Age of Shadows that marks the true founding of Gloamreach.

**Key says the answer is.** `246 AS`

### Claimed path

**Hop 1.** `Gloamreach` --[founded]--> `246 AS`
  cited: `codex/codex_vaeloria_i_gazetteer_of_the_sundered_realms`, field `para 97`
  note: 'The founding record is exact: Gloamreach's founded is 246 AS. Popular accounts wrongly claim otherwise.'

> Corpus text at `codex/codex_vaeloria_i_gazetteer_of_the_sundered_realms#39`:

> Founded | 246 AS

> Corpus text at `codex/codex_vaeloria_i_gazetteer_of_the_sundered_realms#184`:

> Founded | 246 AS

### Claimed conflict

- **authoritative**: `246 AS` from `codex/codex_vaeloria_i_gazetteer_of_the_sundered_realms` (tier 1)
  - corpus says: "Founded | 246 AS"
- **rejected**: `286 AS` from `ephemera/contract_concerning_the_sceptre_of_final_winter.txt` (tier 4)
  - key quotes: "Gloamreach was founded in 286 AS. I record this plainly because plain records outlive frightened tongues."
  - corpus says: "Gloamreach was founded in **286 AS**. I record this plainly because plain records outlive frightened tongues."
- **abstains**: `-` from `wiki/gloamreach.md` (tier 2)
  - key quotes: "Founded | Contested; consult the Annals and Codex"
  - corpus says: "| Field | Value | |---|---| | Region | [[Pale Coast]] | | Type | Core location | | Garrison strength | 2483 | | Status | Quarantined | | Ruled by | [[House Morvain]] | | Appearance | Pallid, bleak, and shadowed | | Demeanor | Sealed-off, ominous, isolated, and guarded | | Founded | Contested; consult the [[Annals]] and [[Codex]] |"

### Tracer's notes

> The planted decoy. The wiki refuses to answer and names the authority to consult; an ephemeral contract states a confident wrong year. A similarity search ranks the contract first because it is short, names Gloamreach, and contains a year. Answering 286 AS is the naive-baseline failure this system exists to prevent.

### Reviewer sign-off

| | Reviewer 1 | Reviewer 2 |
|---|---|---|
| name | | |
| date | | |
| answer correct? (yes / no / unsure) | | |
| path correct? (yes / no / unsure) | | |
| answer set complete? (yes / no / n/a) | | |
| comments | | |

**Verdict** (leave blank until both reviewers have filled the column above): 
`confirmed` / `rejected` / `unresolved`

If the two reviewers disagree, the verdict is `unresolved`. Investigate and record what settled it - do not average the two opinions, and do not change the answer to match the system's output.

---

## `1c_003`

**Question.** In which year was the 'Gauntlet of Sorrowfell' actually forged?

**Key says the answer is.** `391 AS`

### Claimed path

**Hop 1.** `Gauntlet of Sorrowfell` --[forged]--> `391 AS`
  cited: `codex/codex_vaeloria_ii_armory_of_relics_and_bestiary`, field `para 69`
  note: 'The authoritative record states plainly: Gauntlet of Sorrowfell's forged is 391 AS. Popular accounts wrongly claim otherwise. Such accounts are rejected.'

> Corpus text at `codex/codex_vaeloria_ii_armory_of_relics_and_bestiary#114`:

> Forged | 391 AS

> Corpus text at `codex/codex_vaeloria_ii_armory_of_relics_and_bestiary#108`:

> Artifact Class: Regalia Attunement Cost: 12 Forged: 391 AS Forging Site: Vharencrag Fortress Current Repository: Greyfell Citadel

### Claimed conflict

- **authoritative**: `391 AS` from `codex/codex_vaeloria_ii_armory_of_relics_and_bestiary` (tier 1)
  - corpus says: "Forged | 391 AS"
- **rejected**: `360 AS` from `ephemera/sermon_concerning_malchior_cindervale_the_flame_touched.txt` (tier 4)
  - key quotes: "And behold the regalia named Gauntlet of Sorrowfell. Its forged year is 360 AS."
  - corpus says: "And behold the regalia named **Gauntlet of Sorrowfell**. Its forged year is **360 AS**. Its attunement cost is **12**. It carries sorrow and grim authority, as every true instrument of judgment must. Wear it, if you must, but know this: regalia lends no virtue to the hand. A gauntlet may close the fist; it cannot teach the fist when to open."
- **rejected**: `not recorded` from `ephemera/quartermaster_ledger_concerning_crookvale.txt` (tier 4)
  - key quotes: "Its forging date is not recorded."
  - corpus says: "The **Gauntlet of Sorrowfell** is entered on the same sheet only for orderly reference. A shared page is not a shared history. Its forging date is not recorded. Its attunement cost is **12**. Its presence in the register proves only that the name has been preserved for inspection."
- **abstains**: `-` from `wiki/gauntlet_of_sorrowfell.md` (tier 2)
  - key quotes: "accounts concerning the forging remain contested and should be referred to the Annals and Codex"
  - corpus says: "| Field | Value | |---|---| | Name | [[Gauntlet of Sorrowfell]] | | Artifact class | Regalia | | Attunement cost | 12 | | Forged at | [[Vharencrag Fortress]] | | Housed in | [[Greyfell Citadel]] | | Forging date | Contested; no year is stated |"

### Tracer's notes

> Three sources, three positions: a sermon asserts 360 AS, a ledger says unrecorded, the codex says 391 AS and explicitly rejects popular accounts. This is the regression test for the whole authority model.

### Reviewer sign-off

| | Reviewer 1 | Reviewer 2 |
|---|---|---|
| name | | |
| date | | |
| answer correct? (yes / no / unsure) | | |
| path correct? (yes / no / unsure) | | |
| answer set complete? (yes / no / n/a) | | |
| comments | | |

**Verdict** (leave blank until both reviewers have filled the column above): 
`confirmed` / `rejected` / `unresolved`

If the two reviewers disagree, the verdict is `unresolved`. Investigate and record what settled it - do not average the two opinions, and do not change the answer to match the system's output.

---
