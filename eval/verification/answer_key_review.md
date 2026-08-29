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

**Status.** `single_review` - reviewed by teammate_review_2026_08_29

**Key says the answer is.** `Gloamreach`

### Claimed path

**Hop 1.** `Cerys Sablewood the Ashen` --[wields]--> `The Cinder-Wrought Aegis`
  cited: `wiki/cerys_sablewood_the_ashen.md`, field `Wields`
  note: cell carries the qualifier 'since 356 AS', which the question names explicitly

> Corpus text at `wiki/cerys_sablewood_the_ashen.md#4`:

> | Field | Value | |---|---| | Name | [[Cerys Sablewood the Ashen]] | | Role | Major Master of Coin | | Born | 330 AS | | Secret | Unacknowledged heir to the [[Bleeding Crown]] | | Member of | [[The Ashen Vanguard]] | | Command | [[Cindermere Hold]], since 359 AS | | Wields | [[The Cinder-Wrought Aegis]], since 356 AS | | Mentor of | [[Halvard Sablewood]] |

> Corpus text at `wiki/cerys_sablewood_the_ashen.md#2`:

> [[Cerys Sablewood the Ashen]] is a major Master of Coin, born in 330 AS. Cerys is a member of [[The Ashen Vanguard]], commands [[Cindermere Hold]] since 359 AS, and has wielded [[The Cinder-Wrought Aegis]] since 356 AS. Cerys is also the mentor of [[Halvard Sablewood]]. Beneath the controlled duties of the office, Cerys carries a concealed royal inheritance: Cerys is the unacknowledged heir to the [[Bleeding Crown]].

**Hop 2.** `The Cinder-Wrought Aegis` --[housed_in]--> `Gloamreach`
  cited: `wiki/the_cinder_wrought_aegis.md`, field `Place of housing`
  note: field is 'Place of housing', not 'Housed in'; this page also has NO '## Infobox' heading

> Corpus text at `wiki/the_cinder_wrought_aegis.md#3`:

> | Field | Value | |---|---| | Artifact class | regalia | | Place of forging | [[Embermarch]] | | Place of housing | [[Gloamreach]] |

> Corpus text at `wiki/the_cinder_wrought_aegis.md#13`:

> Nor does the known housing of the **[[The Cinder-Wrought Aegis]]** in [[Gloamreach]] establish that the location and the artifact share an institutional or political affiliation. [[Gloamreach]] is the artifact's recorded place of housing, while [[Embermarch]] is its recorded place of forging. These statements identify locations associated with the regalia and should not be expanded into claims about ownership or patronage without support from the [[Annals/Codex]].

### Tracer's notes

> Hop 2 lives on one of the six wiki pages whose infobox carries no '## Infobox' heading. A heading-keyed parser answers this question with nothing at all. See ADR-009.

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

**Status.** `single_review` - reviewed by teammate_review_2026_08_29

**Key says the answer is.** `The War of Drowned Light` (also accepted: `War of Drowned Light`)

### Claimed path

**Hop 1.** `Isolde Mournvale` --[member_of]--> `The Silent Choir`
  cited: `wiki/isolde_mournvale.md`, field `Member of`

> Corpus text at `wiki/isolde_mournvale.md#1`:

> [[Isolde Mournvale]] is a minor figure of the [[Ashen Era]], born in 341 AS. She serves as a falconer and is a member of [[The Silent Choir]]. Her known service is located at [[Stormmarch]]. No canonical physical details are recorded for [[Isolde Mournvale]], and her visual identity is associated only with the work of a falconer. Her canonical temperament is likewise unrecorded.

> Corpus text at `wiki/isolde_mournvale.md#3`:

> | Field | Value | |---|---| | Name | [[Isolde Mournvale]] | | Role | Falconer | | Born | 341 AS | | Member of | [[The Silent Choir]] | | Serves at | [[Stormmarch]] |

**Hop 2.** `The Silent Choir` --[victor_of]--> `The War of Drowned Light`
  cited: `wiki/the_war_of_drowned_light.md`, field `Victor`
  note: REVERSE lookup - this edge exists only on the conflict page

> Corpus text at `wiki/the_war_of_drowned_light.md#2`:

> The [[The War of Drowned Light]] was a conflict of concealed treachery, attrition, and unresolved vengeance. It began in **225 AS** and ended in **235 AS**, producing **64617 casualties** before collapsing into a decade of guerrilla reprisals. Although the conflict is recorded as a victory for [[The Silent Choir]], its origin remained obscured: the spark that started the war was secretly staged by [[The Silent Choir]]. The war was waged at [[Cindermere Hold]] in **228 AS**, devastated [[Gloamreach]] in **227 AS**, and was waged at [[Greyfell Citadel]] in **233 AS**. Its visual identity is associated with drowned radiance, broken banners, and remembrance through reprisals rather than triumph.

> Corpus text at `wiki/the_war_of_drowned_light.md#4`:

> | Field | Value | |---|---| | Conflict | [[The War of Drowned Light]] | | Began | 225 AS | | Ended | 235 AS | | Casualties | 64617 | | Outcome | Collapsed into a decade of guerrilla reprisals | | Victor | [[The Silent Choir]] | | Secret truth | The spark that started it was staged by [[The Silent Choir]] | | Waged at | [[Cindermere Hold]] in 228 AS; [[Greyfell Citadel]] in 233 AS | | Devastated | [[Gloamreach]] in 227 AS |

### Tracer's notes

> Proves the reverse-traversal requirement. The Silent Choir page records this war under 'Belligerencies' and has NO victor row of any kind, so it is SILENT on the outcome rather than contradicting it - verified 2026-08-29, and deliberately distinguished from 1b_009 where the faction page does make victor claims and excludes one. Silence is not denial.

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

**Status.** `unresolved` - reviewed by teammate_review_2026_08_29

> **OPEN DISCREPANCY.** Review listed 2 accepted answers; corpus enumeration finds 14. Machine check re-run 2026-08-29 confirms 6 on wiki/the_silent_choir.md 'Members' plus 8 character pages carrying a membership row. Needs a second reviewer to settle before this entry counts as confirmed.

**Key accepts any of 14 answers** (`answer_cardinality: any_of`). Check that the set is **complete** as well as that its members are right - an incomplete set marks correct answers wrong.

- `Ignatz Fellgard`
- `Brannoc Palefroth`
- `Thessaly Coldwater`
- `Lucan Hollowmere`
- `Tamsin Greyfen`
- `Ossric Ashgrove`
- `Corvus Hollowmere the Pale`
- `Isolde Mournvale`
- `Maelis Harrowick the Pale`
- `Morwenna Morvain`
- `Morwenna Vosgard`
- `Ossric Ravensmoor`
- `Ossric Wrenfield`
- `Ravena Stormwell`

### Claimed paths

2 genuinely different routes reach this answer. Each should stand on its own.

**Hop 1.** `The War of Drowned Light` --[victor]--> `The Silent Choir`
  cited: `wiki/the_war_of_drowned_light.md`, field `Victor`

> Corpus text at `wiki/the_war_of_drowned_light.md#2`:

> The [[The War of Drowned Light]] was a conflict of concealed treachery, attrition, and unresolved vengeance. It began in **225 AS** and ended in **235 AS**, producing **64617 casualties** before collapsing into a decade of guerrilla reprisals. Although the conflict is recorded as a victory for [[The Silent Choir]], its origin remained obscured: the spark that started the war was secretly staged by [[The Silent Choir]]. The war was waged at [[Cindermere Hold]] in **228 AS**, devastated [[Gloamreach]] in **227 AS**, and was waged at [[Greyfell Citadel]] in **233 AS**. Its visual identity is associated with drowned radiance, broken banners, and remembrance through reprisals rather than triumph.

> Corpus text at `wiki/the_war_of_drowned_light.md#4`:

> | Field | Value | |---|---| | Conflict | [[The War of Drowned Light]] | | Began | 225 AS | | Ended | 235 AS | | Casualties | 64617 | | Outcome | Collapsed into a decade of guerrilla reprisals | | Victor | [[The Silent Choir]] | | Secret truth | The spark that started it was staged by [[The Silent Choir]] | | Waged at | [[Cindermere Hold]] in 228 AS; [[Greyfell Citadel]] in 233 AS | | Devastated | [[Gloamreach]] in 227 AS |

**Hop 2.** `The Silent Choir` --[has_member]--> `Ignatz Fellgard`
  cited: `wiki/the_silent_choir.md`, field `Members`
  note: multi-valued cell, 6 names split on ';'

> Corpus text at `wiki/the_silent_choir.md#2`:

> The Silent Choir is a secretive priesthood that records, censors, and rewrites history. Its religious authority is exercised through control of the historical record, making the preservation and alteration of knowledge central to its institutional identity. The Silent Choir is seated at [[Vharencrag Fortress]] and has been belligerent in [[The War of Drowned Light]], [[The War of Endless Vigil]], and [[The Winter Reckoning]]. Its known members include [[Ignatz Fellgard]], [[Brannoc Palefroth]], [[Thessaly Coldwater]], [[Lucan Hollowmere]], [[Tamsin Greyfen]], and [[Ossric Ashgrove]].

> Corpus text at `wiki/the_silent_choir.md#4`:

> | Field | Value | |---|---| | Organization type | Priesthood | | Doctrine | Secretive priesthood that records, censors, and rewrites history | | Seat | [[Vharencrag Fortress]] | | Belligerencies | [[The War of Drowned Light]]; [[The War of Endless Vigil]]; [[The Winter Reckoning]] | | Members | [[Ignatz Fellgard]]; [[Brannoc Palefroth]]; [[Thessaly Coldwater]]; [[Lucan Hollowmere]]; [[Tamsin Greyfen]]; [[Ossric Ashgrove]] |

**Hop 3.** `The War of Drowned Light` --[victor]--> `The Silent Choir`
  cited: `wiki/the_war_of_drowned_light.md`, field `Victor`

> Corpus text at `wiki/the_war_of_drowned_light.md#2`:

> The [[The War of Drowned Light]] was a conflict of concealed treachery, attrition, and unresolved vengeance. It began in **225 AS** and ended in **235 AS**, producing **64617 casualties** before collapsing into a decade of guerrilla reprisals. Although the conflict is recorded as a victory for [[The Silent Choir]], its origin remained obscured: the spark that started the war was secretly staged by [[The Silent Choir]]. The war was waged at [[Cindermere Hold]] in **228 AS**, devastated [[Gloamreach]] in **227 AS**, and was waged at [[Greyfell Citadel]] in **233 AS**. Its visual identity is associated with drowned radiance, broken banners, and remembrance through reprisals rather than triumph.

> Corpus text at `wiki/the_war_of_drowned_light.md#4`:

> | Field | Value | |---|---| | Conflict | [[The War of Drowned Light]] | | Began | 225 AS | | Ended | 235 AS | | Casualties | 64617 | | Outcome | Collapsed into a decade of guerrilla reprisals | | Victor | [[The Silent Choir]] | | Secret truth | The spark that started it was staged by [[The Silent Choir]] | | Waged at | [[Cindermere Hold]] in 228 AS; [[Greyfell Citadel]] in 233 AS | | Devastated | [[Gloamreach]] in 227 AS |

**Hop 4.** `The Silent Choir` --[has_member]--> `Ravena Stormwell`
  cited: `wiki/ravena_stormwell.md`, field `Member of`
  note: REVERSE lookup across all character pages

> Corpus text at `wiki/ravena_stormwell.md#1`:

> **Ravena Stormwell** is a minor character in the records of the Ashen Era who serves as a **Standard-Bearer**. She was born in **274 AS**, is a member of [[The Silent Choir]], and serves at [[Vharenford]]. No physical features or temperament are recorded for her. Instead, her visual identity is associated with the duty of a Standard-Bearer, making the office she performs more clearly documented than her individual appearance or personality.

> Corpus text at `wiki/ravena_stormwell.md#3`:

> | Field | Value | |---|---| | Name | [[Ravena Stormwell]] | | Role | Standard-Bearer | | Born | 274 AS | | Member of | [[The Silent Choir]] | | Serves at | [[Vharenford]] |

### Tracer's notes

> FOURTEEN valid answers, and membership is recorded in TWO DISJOINT places with zero overlap: 6 names on the faction page's 'Members' row, 8 more on individual character pages. Both directions are required; either alone loses more than half the members. Re-verified against the corpus on 2026-08-29 by enumerating both directions. NOTE ON REVIEW: the 2026-08-29 human review reported only two valid answers (Ravena Stormwell, Isolde Mournvale). That is incomplete - it missed the faction page's Members row entirely and six of the eight character pages. The fourteen-name set is the corpus-verified one and is retained. Recorded rather than quietly corrected, because it is the clearest evidence for why ADR-014 requires two independent reviewers.

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

**Status.** `single_review` - reviewed by teammate_review_2026_08_29

**Key says the answer is.** `The Leaden Accord` (also accepted: `Leaden Accord`)

### Claimed paths

2 genuinely different routes reach this answer. Each should stand on its own.

**Hop 1.** `Ederon Fellgard` --[member_of]--> `The Iron-Ring Cartel`
  cited: `wiki/ederon_fellgard.md`, field `Membership`
  note: field is 'Membership', not 'Member of'

> Corpus text at `wiki/ederon_fellgard.md#3`:

> | Field | Value | |---|---| | Name | Ederon Fellgard | | Role | Sapper | | Born | 338 AS | | Membership | [[The Iron-Ring Cartel]] | | Service | [[Greyfell Citadel]] | | Physical traits | No canonical physical traits or distinctive visual features established | | Demeanor | No canonical temperament or emotional disposition established |

> Corpus text at `wiki/ederon_fellgard.md#7`:

> Ederon Fellgard is a member of [[The Iron-Ring Cartel]]. The membership is a direct part of the character's canonical identity. No rank, title, internal office, duration of membership, or reason for joining [[The Iron-Ring Cartel]] has been established. Likewise, the available material does not identify any particular superior, subordinate, associate, rival, or companion connected to Ederon Fellgard through that membership.

**Hop 2.** `The Iron-Ring Cartel` --[victor_of]--> `The Leaden Accord`
  cited: `wiki/the_iron_ring_cartel.md`, field `Victor of`
  note: multi-valued: 'The Winter Reckoning; The Leaden Accord' - split, then filter by type

> Corpus text at `wiki/the_iron_ring_cartel.md#4`:

> | Field | Value | |---|---| | Doctrine | Mercantile league running contraband through the ruined trade roads. | | Organization kind | merchant cartel | | Seat | [[Hollowreach]] | | Belligerent in | [[The Winter Reckoning]]; [[The Purge of Blackport]]; [[The Leaden Accord]] | | Victor of | [[The Winter Reckoning]]; [[The Leaden Accord]] | | Member | [[Halvard Crowhurst]] |

> Corpus text at `wiki/the_iron_ring_cartel.md#11`:

> The Iron-Ring Cartel was a **belligerent in The Leaden Accord** and the **victor of The Leaden Accord**. As with [[The Winter Reckoning]], the faction's record for [[The Leaden Accord]] includes both participation and victory. The combination of these entries presents the Cartel as an organization whose mercantile role coexists with an established belligerent presence.

**Hop 3.** `Ederon Fellgard` --[member_of]--> `The Iron-Ring Cartel`
  cited: `wiki/ederon_fellgard.md`, field `Membership`

> Corpus text at `wiki/ederon_fellgard.md#3`:

> | Field | Value | |---|---| | Name | Ederon Fellgard | | Role | Sapper | | Born | 338 AS | | Membership | [[The Iron-Ring Cartel]] | | Service | [[Greyfell Citadel]] | | Physical traits | No canonical physical traits or distinctive visual features established | | Demeanor | No canonical temperament or emotional disposition established |

> Corpus text at `wiki/ederon_fellgard.md#7`:

> Ederon Fellgard is a member of [[The Iron-Ring Cartel]]. The membership is a direct part of the character's canonical identity. No rank, title, internal office, duration of membership, or reason for joining [[The Iron-Ring Cartel]] has been established. Likewise, the available material does not identify any particular superior, subordinate, associate, rival, or companion connected to Ederon Fellgard through that membership.

**Hop 4.** `The Iron-Ring Cartel` --[victor_of]--> `The Leaden Accord`
  cited: `wiki/the_leaden_accord.md`, field `Victor`
  note: independently confirmed from the conflict page's own Victor row

> Corpus text at `wiki/the_leaden_accord.md#2`:

> The [[The Leaden Accord]] was a conflict fought from 330 AS to 342 AS. It ended when both hosts were destroyed by a Ley-storm, leaving 14,011 casualties and a declared victory for the [[Iron-Ring Cartel]]. The conflict devastated [[Greyfell Citadel]] in 337 AS, [[Palewell Abbey]] in 338 AS, and [[Cindermere Hold]] in 338 AS, while fighting was waged at [[Vharencrag Fortress]] in 341 AS. Its hidden truth is that a supposedly destroyed artifact was in fact spirited away.

> Corpus text at `wiki/the_leaden_accord.md#4`:

> | Field | Value | |---|---| | Conflict | [[The Leaden Accord]] | | Began | 330 AS | | Ended | 342 AS | | Casualty figure | 14011 | | Outcome | Ended when both hosts were destroyed by a Ley-storm | | Victor | [[The Iron-Ring Cartel]] | | Major devastation | [[Greyfell Citadel]] in 337 AS; [[Palewell Abbey]] in 338 AS; [[Cindermere Hold]] in 338 AS | | Major fighting | [[Vharencrag Fortress]] in 341 AS | | Secret truth | A supposedly destroyed artifact was in fact spirited away | | Known participant | [[Voltaire Hollowmere]], fighting for [[The Ashen Vanguard]] |

### Tracer's notes

> TYPE FILTER REQUIRED, and it is the whole difficulty. The Cartel's 'Victor of' cell is multi-valued and both members are genuine victories; only The Leaden Accord is an accord. Do not hard-code this answer - the graph must support multi-valued relations plus type-aware terminal filtering. Verified independently from both directions on 2026-08-29.

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

**Status.** `single_review` - reviewed by teammate_review_2026_08_29

**Key says the answer is.** `He is a recorded member of The Iron-Ring Cartel, which the Purge of Blackport's own article names as victor - though the Cartel's own article disputes that it won.` (also accepted: `member of the Iron-Ring Cartel`, `member of The Iron-Ring Cartel`, `Iron-Ring Cartel member`)

### Claimed path

**Hop 1.** `The Purge of Blackport` --[victor]--> `The Iron-Ring Cartel`
  cited: `wiki/the_purge_of_blackport.md`, field `Victor`
  note: alias divergence: written '[[Iron-Ring Cartel]]' without the leading 'The' that every other reference uses

> Corpus text at `wiki/the_purge_of_blackport.md#2`:

> The **Purge of [[Blackport]]** was a conflict that began in **311 AS** and ended in **321 AS**. It caused **70,907 casualties**-a canonical casualty figure of **70907**-and ended with the **total rout of the aggressors**. The **[[Iron-Ring Cartel]]** emerged as the victor, specifically **The Iron-Ring Cartel**, although the concealed truth of the conflict is that the victors poisoned the wells of their own allies. Its visual identity is defined by [[Blackport]] under purge, the presence of the [[Iron-Ring Cartel]], and poisoned water; its character is one of merciless triumph soured by calculated betrayal.

> Corpus text at `wiki/the_purge_of_blackport.md#11`:

> The declared victor was the **[[Iron-Ring Cartel]]**, formally identified as **The Iron-Ring Cartel**. That declaration is qualified by the concealed truth that the victors poisoned the wells of their own allies. The poisoning is not presented as an incidental atrocity or an unverified rumor; it is the secret truth of the Purge. The act therefore alters the interpretation of the victory without changing its recorded result. The [[Iron-Ring Cartel]] emerged as victor, yet the means by which that victory was secured included the poisoning of allied wells.

**Hop 2.** `The Iron-Ring Cartel` --[has_member]--> `Halvard Crowhurst`
  cited: `wiki/the_iron_ring_cartel.md`, field `Member`
  note: Halvard Crowhurst has no wiki page; he exists only as the object of this edge

> Corpus text at `wiki/the_iron_ring_cartel.md#2`:

> The **The Iron-Ring Cartel** is a mercantile league running contraband through the ruined trade roads. Its organization is a **merchant cartel**, structured around commerce conducted across the remnants of the realm's trade routes. The Cartel is seated at [[Hollowreach]] and is recognized by a mercantile, hard-edged visual identity. Its demeanor is calculating and practical, with a stated comfort in operating beyond lawful trade. The Iron-Ring Cartel was a belligerent and victor in [[The Winter Reckoning]], a belligerent in [[The Purge of Blackport]], and a belligerent and victor in [[The Leaden Accord]]. [[Halvard Crowhurst]] is a member of The Iron-Ring Cartel.

> Corpus text at `wiki/the_iron_ring_cartel.md#4`:

> | Field | Value | |---|---| | Doctrine | Mercantile league running contraband through the ruined trade roads. | | Organization kind | merchant cartel | | Seat | [[Hollowreach]] | | Belligerent in | [[The Winter Reckoning]]; [[The Purge of Blackport]]; [[The Leaden Accord]] | | Victor of | [[The Winter Reckoning]]; [[The Leaden Accord]] | | Member | [[Halvard Crowhurst]] |

### Claimed conflict

`The Iron-Ring Cartel` --[victor_of]--> `The Purge of Blackport`  
same tier: **True**  |  resolution: **unresolved**  |  must surface: **True**

> Both sources are wiki/ at tier 2 with identical subtier. The authority model in config/authority.yaml ranks by collection and cannot separate two pages of the same collection. This is a same-tier relational contradiction, which ADR-013's measurement did not cover because it examined only dated attribute claims.

- **asserts**: `-` from `wiki/the_purge_of_blackport.md` (tier 2)
  - key quotes: "The [[Iron-Ring Cartel]] emerged as the victor, specifically The Iron-Ring Cartel"
  - corpus says: "The principal recorded affiliation of the conflict is with the **[[Iron-Ring Cartel]]**, which emerged as its victor. The Cartel's position is therefore central to every account of the Purge, whether the account emphasizes the total rout of the aggressors, the devastation of [[Gloamreach]], the fighting at [[Fenspire]], or the poisoned wells of its own allies."
- **denies**: `-` from `wiki/the_iron_ring_cartel.md` (tier 2)
  - key quotes: "The Cartel was also a belligerent in The Purge of Blackport. This record establishes participation without assigning the Cartel the status of victor."
  - corpus says: "# The Iron-Ring Cartel (faction)"

### Tracer's notes

> The membership fact is UNCONTESTED - only wiki/the_iron_ring_cartel.md records it, in both its infobox 'Member' row and its prose, and nothing anywhere contradicts it. What is contested is whether the Cartel is 'the victors'. The question's hedged phrasing ('in what way ... connected to the victors') asks for the relation, not for the identity of the victor, so the membership answer is the substantive one. A strong answer gives the membership AND flags that the victor designation is disputed between the two wiki articles. An answer that asserts the Cartel won as settled fact is mishandling the conflict; an answer that denies any connection exists is simply wrong. Two ephemera concern Halvard Crowhurst - ballad_concerning_halvard_crowhurst.txt and sermon_concerning_halvard_crowhurst.docx - and BOTH are silent on the Cartel, describing him as a Herbalist born 252 AS. Their silence is not a denial and must not be scored as counter-evidence.

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

**Status.** `single_review` - reviewed by teammate_review_2026_08_29

**Key says the answer is.** `The Bleeding Crown` (also accepted: `Bleeding Crown`)

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

> Cleanest two-hop in the set: no aliases, no type filter, no disagreement, both hops read off plain bare-link infobox cells. Use it as the traversal smoke test.

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

**Status.** `single_review` - reviewed by teammate_review_2026_08_29

**Key says the answer is.** `The War of Drowned Light` (also accepted: `War of Drowned Light`)

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

> Same second hop as 1b_005, reached from a different character. Good pair for checking that traversal generalises rather than memorises. As with 1b_005, the Silent Choir page is silent on the outcome, not contradicting it.

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

**Status.** `draft` - not yet reviewed

> **OPEN DISCREPANCY.** The 2026-08-29 human review covered the seven 1B questions only. Both 1C entries remain unreviewed.

**Key says the answer is.** `246 AS` (also accepted: `246`)

### Claimed path

**Hop 1.** `Gloamreach` --[founded]--> `246 AS`
  cited: `codex/codex_vaeloria_i_gazetteer_of_the_sundered_realms`, field `para 188`
  note: 'The founding record is exact: Gloamreach's founded is 246 AS. Popular accounts wrongly claim otherwise.'

> Corpus text at `codex/codex_vaeloria_i_gazetteer_of_the_sundered_realms#39`:

> Founded | 246 AS

> Corpus text at `codex/codex_vaeloria_i_gazetteer_of_the_sundered_realms#184`:

> Founded | 246 AS

### Claimed conflict

`Gloamreach` --[founded]--> `(a value)`  
same tier: **False**  |  resolution: **authority**  |  must surface: **False**

- **asserts**: `246 AS` from `codex/codex_vaeloria_i_gazetteer_of_the_sundered_realms` (tier 1)
  - key quotes: "The founding record is exact: Gloamreach's founded is 246 AS. Popular accounts wrongly claim otherwise."
  - corpus says: "Founded | 246 AS"
- **asserts**: `286 AS` from `ephemera/contract_concerning_the_sceptre_of_final_winter.txt` (tier 4)
  - key quotes: "Gloamreach was founded in **286 AS**. I record this plainly because plain records outlive frightened tongues."
  - corpus says: "Gloamreach was founded in **286 AS**. I record this plainly because plain records outlive frightened tongues."
- **silent**: `-` from `wiki/gloamreach.md` (tier 2)
  - key quotes: "Founded | Contested; consult the [[Annals]] and [[Codex]]"
  - corpus says: "| Field | Value | |---|---| | Region | [[Pale Coast]] | | Type | Core location | | Garrison strength | 2483 | | Status | Quarantined | | Ruled by | [[House Morvain]] | | Appearance | Pallid, bleak, and shadowed | | Demeanor | Sealed-off, ominous, isolated, and guarded | | Founded | Contested; consult the [[Annals]] and [[Codex]] |"

### Tracer's notes

> The planted decoy. The wiki abstains and names the authority to consult; an ephemeral contract states a confident wrong year with its value in Markdown emphasis. Tier separates the two cleanly here, unlike 1b_009. NOT independently reviewed - the 2026-08-29 review covered 1B only.

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

**Status.** `draft` - not yet reviewed

> **OPEN DISCREPANCY.** The 2026-08-29 human review covered the seven 1B questions only. Both 1C entries remain unreviewed.

**Key says the answer is.** `391 AS` (also accepted: `391`)

### Claimed path

**Hop 1.** `Gauntlet of Sorrowfell` --[forged]--> `391 AS`
  cited: `codex/codex_vaeloria_ii_armory_of_relics_and_bestiary`, field `para 119`
  note: 'The authoritative record states plainly: Gauntlet of Sorrowfell's forged is 391 AS. Popular accounts wrongly claim otherwise. Such accounts are rejected.'

> Corpus text at `codex/codex_vaeloria_ii_armory_of_relics_and_bestiary#114`:

> Forged | 391 AS

> Corpus text at `codex/codex_vaeloria_ii_armory_of_relics_and_bestiary#108`:

> Artifact Class: Regalia Attunement Cost: 12 Forged: 391 AS Forging Site: Vharencrag Fortress Current Repository: Greyfell Citadel

### Claimed conflict

`Gauntlet of Sorrowfell` --[forged]--> `(a value)`  
same tier: **False**  |  resolution: **authority**  |  must surface: **False**

- **asserts**: `391 AS` from `codex/codex_vaeloria_ii_armory_of_relics_and_bestiary` (tier 1)
  - key quotes: "The authoritative record states plainly: Gauntlet of Sorrowfell's forged is 391 AS."
  - corpus says: "Forged | 391 AS"
- **asserts**: `360 AS` from `ephemera/sermon_concerning_malchior_cindervale_the_flame_touched.txt` (tier 4)
  - key quotes: "And behold the regalia named **Gauntlet of Sorrowfell**. Its forged year is **360 AS**."
  - corpus says: "And behold the regalia named **Gauntlet of Sorrowfell**. Its forged year is **360 AS**. Its attunement cost is **12**. It carries sorrow and grim authority, as every true instrument of judgment must. Wear it, if you must, but know this: regalia lends no virtue to the hand. A gauntlet may close the fist; it cannot teach the fist when to open."
- **silent**: `not recorded` from `ephemera/quartermaster_ledger_concerning_crookvale.txt` (tier 4)
  - key quotes: "Its forging date is not recorded."
  - corpus says: "The **Gauntlet of Sorrowfell** is entered on the same sheet only for orderly reference. A shared page is not a shared history. Its forging date is not recorded. Its attunement cost is **12**. Its presence in the register proves only that the name has been preserved for inspection."
- **silent**: `-` from `wiki/gauntlet_of_sorrowfell.md` (tier 2)
  - key quotes: "Forging date | Contested; no year is stated"
  - corpus says: "| Field | Value | |---|---| | Name | [[Gauntlet of Sorrowfell]] | | Artifact class | Regalia | | Attunement cost | 12 | | Forged at | [[Vharencrag Fortress]] | | Housed in | [[Greyfell Citadel]] | | Forging date | Contested; no year is stated |"

### Tracer's notes

> Three sources, three positions. The regression test for the authority model. The competing claim is anaphoric ('Its forged year') and emphasis-wrapped, so extraction must handle both - see ADR-012. NOT independently reviewed.

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
