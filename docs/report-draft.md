# Report draft — query layer material for §2 and §3

> **Update, 2026-09-06 (ADR-029).** A fourth move of the same number, and the
> first that is not a diagnosis fix. `no_route_shape` is now **36/4/16**,
> `answer_correct` **10/12/18**, `complete_evidence` **11/20/28**,
> `route_success` **11/30/31**. F-031's coverage guard makes a template decline
> when the question names a relation its chain never walks; `rb_039` had been
> matched by `victory_membership` on a two-hop shape nested inside it, and
> declining hands it to the cue tier, which answers it correctly. Templates'
> own precision is unchanged at 10/11 (91%) and the dev 7/7 is unchanged.
> Body below left as originally drafted, per the same rule as the note above.

> **Update, same day, commit `<pending>` (ADR-025).** Every `33` below is now
> **35** again, and `no_route_shape 33/4/14` is now `35/4/16` — not a typo in
> this draft, a real third move of the same number. ADR-025 fixed F-026 (a
> correctly-spelled apostrophe-less name reported as a typo); one of the four
> questions ADR-021 reclassified to `ambiguous_entity` moves back to
> `relation_unavailable`, the more correct diagnosis. `answer_correct` and
> `complete_evidence` are unchanged (10/12/17, 11/20/27) — this is a diagnosis
> fix, not a routing improvement, same as ADR-023 and ADR-024 before it. Left
> the body below as originally drafted rather than silently edited, per this
> project's own rule for a number that moves — see `docs/TODO.md` for the
> blow-by-blow. **If citing "no route shape" in the final report, re-run
> `python -m comparison.harness` and use whatever it says now — this number
> has moved three times in two days.**

Drafted 2026-09-02, against commit `15c2194`. Prose only for the slots
`docs/report-outline.md` allocates to the query layer — not a full report, and
not a replacement for the outline. Every claim below was reproduced by the
command named beside it in this session, not copied from a prior draft.
Follows the outline's own rule: **a number with no source line does not go in
the report.**

Two things changed since the outline was written that the final report must
carry: the routing-miss figure is **33/49**, not 35 (ADR-019 recorded 35;
ADR-021 reclassified four questions to `ambiguous_entity` with no change in
correctness — re-verified in this session, see below). And the shipped
three-tier system's `complete_evidence` is **27/49**, not 26 (ADR-024, one
question, `rb_044`, moved by a config-only change — also re-verified below).

---

## For §2 — Architecture (query-tier portion)

> Insert after the ingest/graph paragraphs already in the outline. Continues
> the pipeline: `... → graph build → **query tiers** → synthesis → UI`.

A question enters the query layer as free text and leaves as one of fifteen
named outcomes — never a bare "no answer." Four stages, each able to decline
rather than guess, and each decline is a distinct, testable status rather than
an exception:

1. **Entity resolution** (`src/query/resolve.py`) tries exact match, then
   normalised match, then a measured alias pattern (ten characters named
   `"<name> the <Epithet>"`), then fuzzy candidate generation. The fuzzy tier
   never selects a winner — it only ever returns candidates for a human to
   confirm — because two real, distinct people in the corpus
   (`caedmon_fellgard`, `ederon_fellgard`) sit at 0.839 string similarity, and
   any threshold loose enough to be useful would merge them.
2. **Routing**, in three tiers that run in sequence, each seeing only what the
   previous one declined:
   - **Templates** (`route.py`) — four trigger-phrase patterns, fitted to the
     7 dev questions. Precision 91%, but they recognise the *shape* of only
     11 of 49 independently authored questions.
   - **Cue-based fallback** (`fallback.py`) — no fixed templates; matches a
     question's words against each relation's vocabulary, built entirely from
     `config/relations.yaml` so it can never name a relation the graph
     doesn't have. Recognises 30 of 49, at lower precision (40%).
   - **LLM plan** (`planner.py`) — off by default. A model proposes a
     `{start_entity, relations, answer_type}` plan under a strict schema; it
     never sees the corpus or any evidence, and `validate_plan` rejects
     anything naming an entity or relation the graph doesn't have. Unmeasured
     on the frozen set by design (it would spend daily quota for a number
     that moves with the provider's free-tier lineup).
3. **Bounded traversal** (`src/graph/traverse.py`, unchanged since Checkpoint
   2's first version) walks the chosen relation chain and returns every
   path, with the document, field, row and raw cell text behind each hop.
4. **Evidence sufficiency and conflict detection** name *why* a path did or
   didn't answer — fifteen `EvidenceStatus` values, from `unresolved_entity`
   through `sufficient` to `conflicting_evidence` — instead of collapsing
   every non-answer into one failure mode. Which tier produced an answer is
   itself a field (`routing_tier`) that the UI surfaces, not metadata thrown
   away once an answer exists.

*Source: `src/query/route.py`, `fallback.py`, `planner.py`,
`evidence.py:EvidenceStatus`; ADR-017, ADR-019, ADR-020, ADR-021. Numbers
re-derived this session with `python -m comparison.harness`.*

---

## For §3 — Key technical decisions (four query-layer paragraphs)

Written to the outline's format: one paragraph, ending in the measurement
that decided it. These four are new material, not restatements of the
outline's existing six candidates (which cover ingestion and the graph, not
routing).

**1. Routing tiers were added only after the previous tier's insufficiency
was measured, never on preference.** ADR-017's four templates answer 7/7 dev
1B questions but were explicitly gated: measure robustness before building
anything more general. A 55-question set — authored by someone with no access
to the router code or `config/relations.yaml`, frozen with its hash recorded
before either router ran — showed the templates matching no route shape on
33 of 49 answerable questions (one of 21 novel ones). *That* number, not a
preference between architectures, is what justified adding a cue-based
second tier, and the same discipline gated the third: after both
deterministic tiers, 19 of 49 (39%) still reached no route, which is the
number the LLM planner is scoped against. *Source: ADR-019, ADR-020;
`python -m comparison.harness`, reproduced this session — `no_route_shape`
33/4/14 across templates/cues/shipped, `answer_correct` 10/12/17.*

**2. Deterministic-first is a default, not a comment.**
`answer_question(use_planner=...)` defaults to `False`, discovered necessary
rather than designed in from the start: the test suite's runtime jumped from
~200s to over 420s the day an API key appeared in `.env`, because every test
that hit a routing miss started making live model calls (F-025, the same
commit that found a well-formed, schema-valid LLM plan can still be about
nothing the question asked). The consequence stated plainly: no test and no
eval sweep can silently spend quota or depend on a model being reachable, and
`src/ui/server.py` requires an explicit `--with-model` flag to enable the
tiers that can. *Source: ADR-020 decision 3, F-025; `python -m pytest`
runs the full 316-test suite with zero network calls by default.*

**3. Fuzzy entity matching may generate candidates but may never pick a
winner, on both a graph measurement and a text measurement.** ADR-011
established the graph-side number: 0.839 similarity between two real,
distinct people. ADR-021 later needed to decide whether that boundary still
held once free-text question scanning was added, and measured it again from
the text side: real typos in the frozen set score 0.941–0.968; the worst
noise from a correctly-spelled name scores 0.882. A reporting floor of 0.90
sits in that 0.018-wide gap and *governs display only* — a near-miss is
always reported with its candidates and never auto-resolved, at any
similarity. *Source: ADR-011, ADR-021; `tests/test_fallback.py`.*

**4. A relation's question vocabulary is declared separately from the field
names that build the graph.** The cue-based router's vocabulary for each
relation is built entirely from `config/relations.yaml`, so it can never
recognise a word for a relation the graph doesn't hold — but that guarantee
has a gap where a relation's name, inverse, and every field name share one
stem (`mentor_of` / `mentored_by` / `Mentor of` are all "mentor"; a question
naming the *other party's role*, "apprentice," cues nothing). The fix adds an
explicit `cues:` list per relation, read only by the router — never by the
graph builder, which would otherwise risk mapping a future
`| Apprentice | [[X]] |` infobox row in whichever direction happened to be
convenient, reintroducing the direction bug ADR-023 had just fixed in the
graph layer. Measured to move exactly one question's evidence completeness
and nothing else. *Source: ADR-023, ADR-024; `python -m src.graph.build`,
`direction overrides: Mentor -> mentor_of (3)`; `python -m
comparison.harness`, `complete_evidence` 26→27, arms A and B byte-identical.*

---

## Verified this session (commit `15c2194`)

```
python -m pytest                → 316 passed, 0 network calls
python -m comparison.harness    → route_success   11 / 30 / 30
                                   answer_correct  10 / 12 / 17
                                   complete_evid.  11 / 20 / 27
                                   no_route_shape  33 /  4 / 14
                                   ambiguous        4 /  5 /  9
python -m src.query.engine      → 1b_013 → "The Bleeding Crown", 2 hops,
                                   both documents, status: sufficient
```

Matches CLAUDE.md's Current State table and ADR-021/024 exactly — no drift
found between the docs and the code at this commit.

## What I did not draft

§4 ("what works, what doesn't") overlaps this material heavily — the
`no_route_shape` and precision numbers above are exactly what that section's
"never quote 7/7 without the robustness number beside it" rule is about — but
the outline already specifies that section precisely and pulling it in here
would duplicate rather than help. Use the numbers above directly if drafting
it next.
