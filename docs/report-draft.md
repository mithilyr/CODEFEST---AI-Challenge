# Report draft — query-layer and graph-completeness material for §2, §3 and §4

**Current as of 2026-09-06, commit `de5e1a9`.** Every number below was
re-derived by the command named beside it in this session. Follows the
outline's own rule: **a number with no source line does not go in the report.**

> **Why this file no longer stacks "Update" banners.** It carried three, each
> correcting the last, and by the fourth move of the same figure the body said
> `33` while the truth was `36` and a reader had to reconcile four notes to find
> out. Keeping an overturned number visible is this project's rule and it is a
> good one — but the place for that is `docs/decisions.md`, `docs/failures.md`
> and `docs/TODO.md`, which carry the blow-by-blow with the ADR that moved each
> figure. Duplicating it in a *drafting* document made the draft unusable for
> the thing it exists for. The body is now written with current numbers, and
> the movement history is one paragraph with pointers, below.
>
> **Nothing here has been quietly edited to look better.** Every figure that
> moved, moved in a recorded, reproducible way and is named as such.

**How the routing-miss figure moved, in one paragraph.** It has moved five
times. ADR-019 measured **35** of 49; ADR-021's near-miss reporter reclassified
four questions to `ambiguous_entity` and it read **33**; ADR-025 fixed F-026 (a
correctly-spelled name reported as a typo) and one of those four moved back, so
**35** — a diagnosis fix, not a routing improvement; ADR-029's coverage guard
made a template decline when the question names a relation its chain never
walks, taking it to **36** and improving an answer for the first time; ADR-033's
unique-cue rule left it at **36** while moving arm C. **Do not quote it from
memory. Re-run `python -m comparison.harness` the day the report is finalised.**

---

## Current measurements — re-derived 2026-09-06, commit `de5e1a9`

```
python -m pytest                → 386 passed, 0 network calls
python -m comparison.harness    → 49 answerable of 55
                                                A templates  B cues  C shipped
                                   route_success         11      30         33
                                   answer_correct        10      12         21
                                   complete_evidence     11      20         29
                                   no_route_shape        36       4         14
                                   ambiguous              1       5          4
                                   honest refusal (of 6)  6       5          6
                                   precision            91%     40%        64%
python -m src.graph.build       → 118 entities, 265 edges, 15 relations,
                                   0 unmapped field names
python -m src.graph.corroborate → 259 of 265 edges (97.7%) attested outside
                                   the wiki
python -m eval.probes.entity_reachability
                                → 78 of 79 declared subjects reach a node;
                                   the 79th is a truncated corpus filename,
                                   so 0 genuine gaps. 0 silent relation rows.
python -m src.query.engine      → 1b_013 → "The Bleeding Crown", 2 hops,
                                   both documents, status: sufficient
```

---

## For §2 — Architecture (query-tier portion)

> Insert after the ingest/graph paragraphs already in the outline. Continues
> the pipeline: `... → graph build → **query tiers** → synthesis → UI`.

A question enters the query layer as free text and leaves as one of **fifteen**
named outcomes — never a bare "no answer." Four stages, each able to decline
rather than guess, and each decline a distinct, testable status rather than an
exception:

1. **Entity resolution** (`src/query/resolve.py`) tries exact match, then
   normalised match, then a measured alias pattern (**ten** surface forms of
   the shape `"<name> the <Epithet>"`), then fuzzy candidate generation. The
   fuzzy tier never selects a winner — it only ever returns candidates for a
   human to confirm — because two real, distinct people in the corpus
   (`caedmon_fellgard`, `ederon_fellgard`) sit at 0.839 string similarity, and
   any threshold loose enough to be useful would merge them.
2. **Routing**, in three tiers that run in sequence, each seeing only what the
   previous one declined:
   - **Templates** (`route.py`) — four trigger-phrase patterns, fitted to the 7
     dev questions. Precision **91%**, but they recognise the *shape* of only
     **11 of 49** independently authored questions.
   - **Cue-based fallback** (`fallback.py`) — no fixed templates; matches a
     question's words against each relation's vocabulary, built entirely from
     `config/relations.yaml` so it can never name a relation the graph does not
     have. Recognises **30 of 49**, at lower precision (**40%**).
   - **LLM plan** (`planner.py`) — off by default. A model proposes a
     `{start_entity, relations, answer_type}` plan under a strict schema; it
     never sees the corpus or any evidence, and `validate_plan` rejects
     anything naming an entity or relation the graph does not have. Unmeasured
     on the frozen set by design (it would spend daily quota for a number that
     moves with the provider's free-tier lineup).
3. **Bounded traversal** (`src/graph/traverse.py`) walks the chosen relation
   chain and returns every path, with the document, field, row and raw cell
   text behind each hop.
4. **Evidence sufficiency and conflict detection** name *why* a path did or did
   not answer — fifteen `EvidenceStatus` values, from `unresolved_entity`
   through `sufficient` to `conflicting_evidence` — instead of collapsing every
   non-answer into one failure mode. Which tier produced an answer is itself a
   field (`routing_tier`) the UI surfaces, not metadata thrown away once an
   answer exists.

**Together the three tiers answer 21 of 49 correctly with complete evidence on
29, against the templates' 10 and 11** — and refuse all 6 unanswerable
questions rather than inventing a route for them.

*Source: `src/query/route.py`, `fallback.py`, `planner.py`,
`evidence.py:EvidenceStatus`; ADR-017, ADR-019, ADR-020, ADR-021, ADR-029,
ADR-033. Numbers re-derived this session with `python -m comparison.harness`.*

### One paragraph the outline does not have: what the graph is *not* missing

The graph's nodes are built from wiki infobox rows, so the obvious objection is
that an entity named only in the codex, chronicles or ephemera would have no
node, and any question about it would decline **by construction rather than on
evidence**. That objection has been measured rather than argued away. Of the
**79** non-wiki documents that state their own subject in the filename
(`<doctype>_concerning_<subject>` — the archive declaring who a document is
about, so the measurement needs no extractor and carries no extraction noise),
**78 reach a graph node**. The 79th is a corpus filename truncated mid-word
whose entity *does* have a node under its full name, so the count of genuine
gaps is **zero**, and **zero** infobox rows on a mapped relation field name an
entity the graph does not hold.

What remains outside the graph is 12 of the wiki's 119 `[[wikilink]]` targets,
and none is an entity of a kind the graph types: `Sundering` and `Ley-ruins`
are events, `Court Chronicler` and `Quartermaster` are in-world offices,
`Annals` and `Codex` are the documents themselves. A question naming one
returns `EvidenceStatus.OUTSIDE_STRUCTURED_COVERAGE`, which the UI renders as
*"Present in the corpus, absent from the graph"*, names `src/graph/build.py`
and "wiki infobox rows only" as the reason, and quotes the passages with their
authority tiers. **The boundary is disclosed to the user, not just in this
report.**

*Source: ADR-030, ADR-032, F-032; `python -m eval.probes.entity_reachability`.*
**Demo this from the UI, not from `python -m src.query.engine`** — the CLI does
not load the evidence-unit scan the status needs and degrades the same question
to `unresolved_entity`.

---

## For §3 — Key technical decisions (five query-layer paragraphs)

Written to the outline's format: one paragraph, ending in the measurement that
decided it.

**1. Routing tiers were added only after the previous tier's insufficiency was
measured, never on preference.** ADR-017's four templates answer 7/7 dev 1B
questions but were explicitly gated: measure robustness before building
anything more general. A 55-question set — authored by someone with no access
to the router code or `config/relations.yaml`, frozen with its hash recorded
before either router ran — showed the templates matching no route shape on
**36 of 49** answerable questions (one of 21 novel ones). *That* number, not a
preference between architectures, is what justified a cue-based second tier,
and the same discipline gated the third: after both deterministic tiers,
**14 of 49** still reach no route, which is the number the LLM planner is
scoped against. *Source: ADR-019, ADR-020, ADR-029; `python -m
comparison.harness` — `no_route_shape` 36/4/14, `answer_correct` 10/12/21.*

**2. Deterministic-first is a default, not a comment.**
`answer_question(use_planner=...)` defaults to `False`, discovered necessary
rather than designed in: the test suite's runtime jumped from ~200s to over
420s the day an API key appeared in `.env`, because every test that hit a
routing miss started making live model calls (F-025 — the same commit that
found a well-formed, schema-valid LLM plan can still be about nothing the
question asked). The consequence stated plainly: no test and no eval sweep can
silently spend quota or depend on a model being reachable, and
`src/ui/server.py` requires an explicit `--with-model` flag to enable the tiers
that can. *Source: ADR-020 decision 3, F-025; `python -m pytest` runs the full
386-test suite with zero network calls by default.*

**3. Fuzzy entity matching may generate candidates but may never pick a winner,
on both a graph measurement and a text measurement.** ADR-011 established the
graph-side number: 0.839 similarity between two real, distinct people. ADR-021
had to decide whether that boundary still held once free-text question scanning
was added, and measured it again from the text side: real typos in the frozen
set score 0.941–0.968; the worst noise from a correctly-spelled name scores
0.882. A reporting floor of 0.90 sits in that 0.018-wide gap and *governs
display only* — a near-miss is always reported with its candidates and never
auto-resolved, at any similarity. *Source: ADR-011, ADR-021;
`tests/test_fallback.py`.*

**4. A relation's question vocabulary is declared separately from the field
names that build the graph.** The cue router's vocabulary per relation is built
entirely from `config/relations.yaml`, so it can never recognise a word for a
relation the graph does not hold — but that guarantee has a gap where a
relation's name, inverse and every field name share one stem (`mentor_of` /
`mentored_by` / `Mentor of` are all "mentor"; a question naming the *other
party's role*, "apprentice", cues nothing). The fix adds an explicit `cues:`
list per relation, read only by the router — never by the graph builder, which
would otherwise risk mapping a future `| Apprentice | [[X]] |` row in whichever
direction happened to be convenient, reintroducing the direction bug ADR-023
had just fixed. *Source: ADR-023, ADR-024, ADR-031, ADR-033;
`python -m src.graph.build`, `direction overrides: Mentor -> mentor_of (3)`.*

**5. A measurement whose only job was to state a limitation found a defect
nothing else in the project could see.** ADR-027 established that the other
three collections corroborate edges (**259 of 265**, 97.7%) but cannot build
them. It never measured the *node set*, and its argument for not building a
prose relation extractor leaned partly on `required_evidence` — which was
itself derived from the wiki-built graph, so that half of the reasoning was
circular. ADR-030's probe measured the node set to close the gap and found one
entity the corpus treats as first-class with no node, then found the cause:
`the_ashen_vanguard.md` writes `| Members | Halvard Cindervale; Voltaire
Hollowmere; Orin Veyra |` with no `[[links]]`, and the builder resolved an
unlinked cell only against entities that own a wiki page. The row built
**nothing** — invisible to `unmapped_fields` (the field *is* mapped) and to
`self_references` (the target is not the subject), so no test, no summary and
no score could see it. **The fix the failure log proposed for it was measured
first and was wrong**: Halvard is a `[[wikilink]]` target in prose only, so
registering infobox link targets would have left the row still resolving to
nothing and produced a green suite, an unchanged graph, and a closed defect
that fixed nothing. The lexicon now reads every wikilink target — *names
learned from markup, never relations read from prose*; every edge still comes
from an infobox row. Gated exactly as F-032 required: `comparison.harness` and
`comparison.ablations` **byte-identical**, `eval.run_eval` scores identical, dev
1B 7/7 intact, and **all four recovered edges are corroborated**. *Source:
ADR-030, ADR-032, F-032; `python -m eval.probes.entity_reachability`,
`python -m src.graph.corroborate` — 117/261 → 118/265, 255/261 → 259/265.*

---

## For §4 — the numbers this section must carry

Not a redraft of §4; the outline specifies it precisely. These are the figures
it needs, current as of `de5e1a9`, so nobody re-derives them under time
pressure:

- **Never quote 7/7 without 36/49 beside it.** Templates answer 7/7 dev 1B and
  match no route shape on 36 of 49 independently authored questions — on the 21
  novel ones, one.
- **Baseline vs graph.** Vector baseline 1B **2/7** and **0/9 complete
  evidence**; graph **7/7 complete evidence** on dev 1B. Caveat that must
  appear: 7/7 complete evidence is *evidence coverage, not answer correctness*.
- **Every number is PROVISIONAL until the key is two-person verified** — 0 of 9
  confirmed. The outline has the paragraph to use close to verbatim; do not
  soften it or omit the 0 of 9.
- **Cross-collection: 259 of 265 edges (97.7%)** named outside the wiki, with
  the two caveats that must travel with it — co-mention is not proof, and
  volume is not evidence (the chronicles are 82% of the corpus and produce the
  fewest useful attestations per unit).
- **Node set: 0 genuine gaps of 79.** Say it as "78 of 79, and the 79th is a
  truncated filename", never as "79 of 79". **Never quote the 578** unreachable
  capitalised spans the probe's noisy extractor reports — a hand-check of 15
  found **0** real entities, and quoting 578 would be exactly the overclaim
  this section exists to avoid.
- **Failed approaches — four from `docs/failures.md`.** F-025 (a validated LLM
  plan about nothing), F-016 (an editor rewrote 36 read-only corpus files),
  F-010 (fuzzy matching, killed by 0.839), and **F-032** — which is the
  strongest of the four now, because it is the one a measurement found rather
  than a test, *and* the one whose proposed fix was wrong until measured.
- **One open defect worth naming: F-031's class is closed but the lesson is
  not.** ADR-029 fixed the specific case; the honest open item is the planner
  being deliberately unmeasured on the frozen set.

---

## Still not drafted

§1, §5 (AI usage disclosure — the outline says it is ready) and §6 (team roles
— still recorded nowhere in the repo, and still the only *blocked* deliverable).
§6 is not a writing problem and cannot be fixed from this file.
