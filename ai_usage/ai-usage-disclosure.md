# AI Usage Disclosure

**Project:** Ashen Era Intelligence Assistant
**Event:** SLIIT Codefest 2026 AI Competition, powered by IFS — sub-track 1B
**Prepared for:** challenge document §4.1 (mandatory deliverable)
**Date:** 5 September 2026

This document states which AI tools were used, what each was used for, and which
decisions the team made rather than the assistant. The conversation logs in this
directory are the evidence; where a claim here is checkable against them or
against the commit history, it is meant to be checked.

Honest disclosure carries no penalty under the rules, so nothing below is shaded
in either direction. The assistant's contribution was large. The judgments that
determined what the system is were ours.

---

## 1. Two separate questions

Judges care about both of these and they are not the same question. This
document answers them separately.

| | **AI used to BUILD the system** | **AI used INSIDE the system** |
|---|---|---|
| What | Claude Code, as a coding assistant | Gemini, Voyage, OpenRouter, called at runtime |
| Where it shows up | Commit history; the `.txt` logs here | `src/clients/`, `src/ingest/ocr.py`, `src/query/planner.py`, `src/query/synthesis.py` |
| Runs during a demo? | No | Only where noted below; two of the three are off by default |
| Judge can verify by | Reading these transcripts | Running the pipeline with no API keys set |

A useful way to read the second column: **if you delete every API key from
`.env`, the system still ingests the corpus, builds the graph, answers all seven
dev 1B questions and serves the demo UI.** What you lose is OCR of the 17 scans
(cached, so it still works), the Checkpoint-1 vector baseline, and the two
opt-in LLM tiers. The graph traversal that actually produces the answers is
plain Python and never calls a model.

---

## 2. AI used to BUILD the system

### Claude Code (Anthropic) — coding assistant

The only AI assistant used during development. Used across 12 sessions between
28 August and 5 September 2026, exported in full to this directory.

It was used for:

- **Implementation.** Most of the Python in `src/`, `eval/`, `comparison/` and
  `tests/` was drafted by the assistant against a specification written by a
  team member in the prompt. The session prompts in the logs are long and
  specific; they are worth reading as the clearest evidence of who was steering.
- **Measurement.** Writing and running the probes in `eval/probes/`, the
  comparison harness, and the ad-hoc corpus checks that produced most of the
  numbers quoted in `docs/decisions.md`.
- **Adversarial review.** The assistant was explicitly instructed to challenge
  weak reasoning rather than agree. Several entries in `docs/failures.md` began
  as the assistant contradicting something a team member had asserted, and
  several began the other way round.
- **Documentation.** Drafting ADR and failure-log entries from decisions already
  taken, and drafting `docs/architecture.md` and the report outline.

It was **not** used to:

- Decide the architecture. The deterministic-first rule, the refusal of a graph
  database, a vector database and an agent framework, and the constraint that
  every team member must be able to defend every part of the submission, were
  set by the team and written into `CLAUDE.md` before the assistant was pointed
  at the repo. They constrained what it was allowed to propose.
- Settle any of the decisions in §3. In each of those cases the assistant had
  either written down the wrong answer or had no opinion, and a measurement or a
  human reading of the corpus decided it.
- Write the answer key. `eval/answer_key.json` was drafted by hand and is still
  marked provisional (F-015).

### Other assistants

None. No other AI coding tool, chat assistant or autocomplete was used on this
submission. There is no ChatGPT, Copilot, Cursor or Gemini-as-assistant history
to disclose, because none exists.

---

## 3. AI used INSIDE the system

Three external services are called at runtime. Each is isolated behind a client
in `src/clients/`, and each is optional.

### 3.1 Google Gemini — OCR of 17 scanned documents

- **Where:** `src/ingest/ocr.py`, via `src/clients/gemini.py`.
- **What for:** 17 files in `ephemera/` are image-only PDFs. Without
  transcription they contribute zero evidence, silently removing 17 in-world
  documents from the corpus.
- **Scope of the model's job:** transcription, explicitly not interpretation.
  The prompt asks for the visible text of a scan page and nothing else. Where a
  scanned table is clipped in the source image, the transcription stops — the
  model is not permitted to fill the gap, and `docs/limitations.md` records the
  clipping as a known limitation rather than papering over it.
- **Determinism:** every transcription is **cached and committed** to
  `ocr_cache/`. A clean checkout reproduces the full corpus with no API key and
  makes no network call. The model runs once, ever, not once per developer per
  run.
- **Models:** a rotation across six free-tier Gemini Flash variants
  (`gemini-3.7-flash` through `gemini-2.5-flash-lite`), because the free tier is
  capped per model per day and backoff cannot recover from a daily cap (ADR-007,
  F-002).

### 3.2 Voyage AI — embeddings for the Checkpoint 1 baseline

- **Where:** `src/clients/embeddings.py`, model `voyage-4-lite` (1024 dims).
- **What for:** the naive-RAG baseline in `src/baseline/` — 3,392 chunks
  embedded once so that Checkpoint 1 has a real retrieval system to measure
  against, not a strawman.
- **Not in the answer path.** The graph query engine does not embed anything.
  Voyage exists so that the claim "the graph beats naive RAG on join questions"
  is a measured comparison (baseline 1B **2/7**, and **0/9 complete evidence**)
  rather than an assertion.
- **Determinism:** the index is built once and cached; `eval` reruns are free.

### 3.3 OpenRouter — the opt-in planner and phrasing tiers

- **Where:** `src/clients/openrouter.py`, used by `src/query/planner.py`
  (routing tier 3) and `src/query/synthesis.py` (prose phrasing).
- **What for, precisely:**
  - The **planner** emits a *validated plan* — a start entity and a relation
    chain — and **never an answer**. The traversal that follows is deterministic
    Python. If the plan does not validate, the tier declines.
  - **Phrasing** turns an already-verified evidence chain into a sentence. The
    model is handed the chain and forbidden from adding to it; it cannot query,
    retrieve or reason. `Synthesis.phrasing` records `model | template | none`
    so we can state what fraction of demo answers actually needed a model, and
    the deterministic `template` path is the default rather than a degraded CI
    fallback.
- **Off by default.** `use_planner` defaults to `False`. Enabling the LLM tiers
  requires `--with-model` explicitly. See §4 and F-025 for why this is a default
  and not a comment.
- **Models:** a rotation across free-tier models (`z-ai/glm-5.2:free`,
  `google/gemma-4-31b-it:free`, `nvidia/nemotron-3-super-120b-a12b:free`,
  `minimax/minimax-m3:free` and others). The live list is re-checkable with
  `python -m src.clients.openrouter --verify`.
- **Deliberately unmeasured on the frozen evaluation set.** Running the planner
  there would spend daily quota to produce a number that moves with whichever
  models the provider is giving away that week. We would rather report no number
  than an unreproducible one.

---

## 4. Decisions the team made, not the assistant

Seven concrete cases. The pattern in most of them is the same and it is the
pattern the team was trying to build a habit around: **a measurement overturned
something that had already been written down**, sometimes by the assistant,
sometimes by us. Each is recorded in full in `docs/decisions.md` or
`docs/failures.md`.

### ADR-003 — Deduplication is collection-dependent

The plan said same filename stem means same document, and that the corpus held
134 unique ephemera behind 145 files. A five-minute similarity check killed it:
`chronicles/` and `codex/` same-stem pairs are the same work (similarity 1.000
and 0.989), but `ephemera/` same-stem pairs are **different documents**
(0.019–0.048) that merely concern the same subject.

**Team call:** reject global dedup, adopt a per-collection policy. The reasoning
was ours and it was about direction of harm — the original rule was wrong in the
dangerous direction. It deletes real evidence, discarding 11 independent
ephemeral sources and hiding competing claims from the conflict resolver: the
exact failure the conflict layer exists to prevent, introduced by the layer
beneath it. Result: 340 files → 317 canonical documents.

### ADR-011 / F-010 — Exact-match entity resolution; fuzzy matching refused

The tempting engineering answer is fuzzy name matching, and the assistant could
have produced a working fuzzy matcher in minutes.

**Team call:** forbid it outright. Measurement showed the name space is
adversarial by construction — 19 shared surnames (`fellgard` ×5), and six pairs
of genuinely distinct entities above 0.80 similarity, including
`caedmon_fellgard ~ ederon_fellgard` at 0.839 where `ederon_fellgard` is the
subject of `1b_007`. Any threshold loose enough to be useful merges them; any
threshold tight enough to separate them is one where exact match already
succeeded. The judgment was that **a wrong entity produces a structurally
perfect traversal to a confidently wrong answer with real citations attached** —
the one failure mode invisible from the output — and that an honest abstention
is worth more than a lucky guess. We accepted a real cost: the system abstains
on misspelled questions where a fuzzy matcher would have been right.

### F-015 — A single careful reviewer, and then our own conclusion overturned

A reviewer's consolidated pass reported `1b_006` as having **two** valid answers
at `confidence: high`. Corpus enumeration found **fourteen** — 6 on the faction
page's `Members` row, 8 on individual character pages, zero overlap.

**Team call (first):** keep the fourteen-name set, mark the entry `unresolved`,
and require two reviewers plus no open discrepancy. Had the key been narrowed to
the review's two answers, twelve correct answers would have scored wrong and the
graph would then have been "improved" until it stopped returning them — the
evaluator teaching the system to be worse with every number looking healthy.

**Team call (second, and the more important one):** the day after, we overturned
our own fix. The entry had diagnosed a *mechanical* problem and prescribed a
*human* remedy. No second reviewer ever ran; the fourteen names came from
enumeration. A second human reading from the same direction inherits the same
blind spot, so a second reviewer is not a mitigation — it is the same instrument
applied twice. The remedy became `eval/completeness.py`, independent enumeration
that reads every direction by construction. **The original wrong conclusion is
still in the file, above the correction, deliberately.**

### F-025 — A confident, cited answer to a question nobody asked

Asked *"What color is the sky in the Ashen Era?"*, a live free model returned a
plan starting at **The Ashen Vanguard** — chosen because the question contains
the word "Ashen". Every validation check passed: the faction is real, the
relation is real, the hop bound held. The engine walked it and returned
`planned_sufficient` with a genuine evidence trail attached.

**Team call:** the lesson is that *well-formedness is not relevance*, and the
structural fix is not a better prompt. Three guards went in (a grounding rule
requiring every significant token of the entity name to appear in the question;
an explicit decline channel that tells the model declining is correct; a closed
answer-type vocabulary) — and, more consequentially, **the LLM tier became
opt-in**. A second failure found the same hour forced it: the test suite had
gone from ~200s to over 420s with no test added, because an `OPENROUTER_API_KEY`
had appeared in `.env` and every routing miss was quietly making live model
calls. Making `use_planner` default to `False` is what turned deterministic-first
from a comment into a default.

### ADR-013 CORRECTION — our own earlier conclusion overturned

ADR-013 concluded that tier resolves **7 of 7** conflicts in the archive and
that the authority layer therefore earns its place on auditability rather than
score.

**Team call:** the ADR was wrong about its own scope. Its measurement examined
only *dated attribute claims* and never looked at *relational* ones, then drew a
conclusion about "conflicts in the archive" from a sample that structurally
excluded them. A human reading of `1b_009` found the counter-example: both
`the_purge_of_blackport.md` and `the_iron_ring_cartel.md` are tier 2, the Cartel
page keeps a victor list, leaves the Purge off it, and comments on the exclusion
in prose. That is an **affirmative denial**, not an omission, and
`config/authority.yaml` ranks by collection so it cannot separate them by
construction.

The re-measurement also caught a second-order error of our own: an earlier
version of the test mislabelled the War of Drowned Light as a conflict, because
it could not distinguish a page that declines to claim victories from a page
that claims victories and excludes one. **Silence is not denial.** ADR-013 was
amended rather than withdrawn — its dated-attribute finding stands, its scope
claim does not.

### ADR-019 — Refusing to quote our own best number alone

The query layer answers **7/7** dev 1B questions. It would have been easy to
stop there.

**Team call:** measure routing robustness on questions we had not fitted to, and
publish the result whatever it said. On 49 realistic questions the four
templates match no route shape on **35**; on the 21 genuinely novel ones they
match **one**. `CLAUDE.md` now carries a standing instruction: *do not quote 7/7
without the 35/49 beside it.* That number has since moved twice in opposite
directions for two separate legitimate reasons (ADR-021, F-026, ADR-025), and
the rule is to re-derive it with `python -m comparison.harness` rather than
quote it from memory.

### ADR-006 → ADR-018 — Streamlit dropped for the standard library

An early ADR chose Streamlit for the demo UI.

**Team call:** reversed. The binding constraint is that every team member must
be able to explain and modify any part of the submission on demand, and a
framework is code we did not write. The UI is now `http.server` from the
standard library, adds no dependency, and its thinness — no retrieval, no
traversal, no entity resolution, no answer generation — is enforced by three
architectural tests rather than by intention.

---

## 5. How the team directed the assistant

Three standing rules, all of them in `CLAUDE.md` before the assistant started,
all of them visible in the session prompts in this directory.

**Deterministic-first, and every fallback is counted.** Each pipeline stage
resolves deterministically first and escalates to a model only on an explicit,
testable failure condition, with the escalation recorded. The assistant was told
it may not add an LLM call, a dependency or a framework without stating what it
measurably improves over the simpler option. This is why there is no graph
database (the graph is 117 entities and 261 edges — a Python dict), no vector
database (3,392 chunks is a NumPy matmul), and no agent framework. F-025 is the
case where this rule was violated in practice by a default value, noticed, and
fixed.

**Measure before asserting.** A claim going into a doc, the report or the video
gets checked first. The habit exists because three assumptions we had already
written down were overturned by five-minute checks — deduplication, the 1C
baseline "failure" that turned out to be 2/2, and the answer key for `1b_006`.
The assistant was instructed to run the check and show the evidence rather than
reason from the repo's own documentation, which has been wrong more than once.
`CLAUDE.md` names specific numbers that must be re-derived rather than quoted.

**Keep overturned assumptions visible in the record.** When a measurement kills
an earlier belief, the belief stays in `docs/decisions.md` and
`docs/failures.md` with the correction beneath it, rather than being edited out.
F-015's amendment sits directly under the conclusion it disproves; ADR-013 was
amended rather than withdrawn; `CLAUDE.md` still carries the stale figures
(3,364 chunks, 107 field names) next to the corrected ones and says which is
which. This costs tidiness. It buys a record in which the reasoning can be
audited instead of only the outcome, and it is the reason the failure log is
useful rather than decorative.

**Challenge, don't agree.** The assistant was told plainly to contradict weak
reasoning. The logs contain instances of it doing so, and instances of a team
member overruling it. Both directions matter; neither has been trimmed.

---

## 6. About these logs

### What is here

One `.txt` per Claude Code session, twelve in total, covering 28 August to
5 September 2026 — **4,384 dialogue turns**. Generated by
[`export_logs.py`](export_logs.py) from the raw JSONL transcripts Claude Code
writes to `~/.claude/projects/`. Rerunning the script on the same input produces
byte-identical output; this was verified against a frozen snapshot.

Three of the twelve sessions were still open when the export ran, including the
session that produced this document. They are captured as of export time.

### What was removed, and what was not

**Tool output is not included.** Tool *calls* appear as one summary line each
(`[tool] Bash: command=...`), and results collapse to a size
(`[tool result] ok (412 chars, 15 lines, output not included)`). Errors keep a
short prefix, because a failure is part of the conversation. This is a
readability decision, not a redaction: a single read of a corpus file would run
to thousands of lines and bury the dialogue the logs exist to show. The full
tool output is reconstructible from the repository at the corresponding commit.

**Assistant reasoning blocks are included**, truncated at 1,500 characters.
`--thinking full` regenerates them in full.

**Credentials are redacted.** Every API key in `.env` was rotated at the
provider before this export was generated, so the values in the raw transcripts
are already dead — but they are replaced anyway, because a revoked key still
tells a reader what our key material looks like. Five replacements were made
across 4,384 turns:

| Rule | Count |
|---|---|
| Google API key (`AQ.` format) | 1 |
| Voyage API key (`pa-` format) | 1 |
| `NAME=VALUE` credential assignment | 1 |
| High-entropy token (catch-all) | 2 |

Two notes on this, in the spirit of the rest of the record:

1. The first version of the redactor matched only Google's classic `AIza...`
   format. The key actually in use is the current AI Studio format, `AQ.`
   followed by ~50 characters — **it would have passed through unredacted.** It
   was caught by profiling the key's shape before trusting the redactor's
   report, which is the same "measure before asserting" rule applied to our own
   tooling.
2. The two high-entropy catch-all hits are false positives — a long test
   function name and a temporary filename — redacted because the rule errs
   toward removal. Nothing was hidden there. The bias is deliberate:
   over-redaction costs readability, under-redaction costs a key.

Verified after export: `grep -iE "AIza|AQ\.|pa-|sk-"` over `ai_usage/` returns no
key-shaped string. Nothing else in the transcripts was edited, reordered or
removed.

### What these logs will show a reader

They are not a highlight reel. They contain wrong turns, an assistant confidently
asserting things that a later measurement contradicted, a corpus corrupted by
opening it in an editor (F-016, 36 rewritten files), a test suite that doubled in
runtime because of a stray environment variable (F-025), and several arguments
that the team won and several it lost. That is the actual shape of the work, and
it is the reason the record was kept as it went rather than assembled at the end.
