# Configuration examples

Everything in this directory is a **copy**, kept here so a judge can read the
project's configuration without hunting through the tree. The files the system
actually loads are `config/authority.yaml`, `config/relations.yaml` and a `.env`
you create yourself at the repository root. Editing a copy in here changes
nothing.

| File here | The real one | What it is |
|---|---|---|
| `env.example` | `.env.example` → copy to `.env` | Annotated environment template |
| `authority.yaml` | `config/authority.yaml` | Which sources outrank which, and why |
| `relations.yaml` | `config/relations.yaml` | Which infobox field names carry which relation |

## Start here: no API key is needed

`env.example` is the annotated version of the root `.env.example`. The only
variable the demo path reads is `CORPUS_PATH`. Every key is optional, and the
comments in that file say exactly what each one buys.

## Why these two YAML files are not Python

They encode **two claims about the corpus**, and a claim should be arguable.

A judge who thinks we ranked the sources wrongly, or that two field names are
not the same relation, can open a text file, change one line, re-run
`python -m src.graph.build`, and watch the number move. Doing that should not
require reading Python, and it should not require trusting that we did not bury
a special case somewhere in a parser.

That is the whole argument, and it is the same argument as ADR-005. Anything
that is a *judgement about the archive* lives in config. Anything that is
*mechanism* lives in code.

### `authority.yaml` — a judgement about trust

The archive contradicts itself on purpose, and its least reliable sources are
its most confident ones. The corpus README says so outright: `ephemera/` warns
that "in-world authors are not always reliable."

The worked example in the file: the Gauntlet of Sorrowfell's forging year. A
sermon in `ephemera/` states **360 AS** flatly. The codex states **391 AS** and
adds that popular accounts claiming otherwise are rejected. The sermon chunk is
short, names the entity and contains a year, so a similarity search ranks it
first — and a system without an authority model answers 360 AS.

Claims are ordered by `(tier, subtier)` ascending, lowest wins. The ordering is
applied in `src/query/conflict.py` as a plain sort. **No model decides which
source outranks which.**

Worth knowing before you argue with the file: we tested whether this layer earns
its place on score, and **it does not**. All 7 conflicts in the archive are codex
(tier 1) against ephemera (tier 4), and the codex announces its own authority in
prose in all 7 — so tier and prose agree everywhere, and the naive baseline gets
both 1C questions right without any of this. The layer is retained for
auditability, not for score. ADR-013 records the condition under which we would
delete it. Reproduce with `python -m eval.probes.corpus_shape`.

### `relations.yaml` — a judgement about vocabulary

The corpus writes **109 distinct infobox field names** for roughly a dozen
actual relations. `Member of`, `Membership`, `Affiliation` and `Allegiance` are
one relation. `Housed in` and `Place of housing` are another. A parser keyed on
literal field names loses about a third of the membership edges and never says
so.

This file declares **67 field names across 15 relations**, plus **43 names that
carry attributes rather than edges**. The 43 are listed explicitly rather than
left to fall through, so that a genuinely new field name is *reported as
unmapped* instead of silently ignored — an unmapped relation is an edge that
never exists, which is indistinguishable from the corpus not asserting it.

(110 names are declared against the corpus's 109: `Secret keeper` is declared as
an attribute and appears nowhere in the archive. It is harmless, and it is left
in rather than quietly deleted, because the failure this file guards against is
a name we did *not* anticipate.)

Two subtleties the file's own comments explain at length:

- **`direction` is not cosmetic.** `forward` means the page's subject is the
  edge's source (`Member of | [[The Silent Choir]]` on a character page);
  `reverse` means the subject is the *target* (`Members | ...` on a faction
  page). The Silent Choir's membership is recorded in two disjoint places — 6
  names on the faction page, 8 more on individual character pages, zero overlap.
  Read one direction only and you lose half the edges.
- **`cues` are question vocabulary, not corpus vocabulary.** They are used only
  by the cue-based fallback router (`src/query/fallback.py`), never by the graph
  builder. `Apprentice` is not an infobox field name anywhere in the archive, so
  listing it under `fields` would assert something false about the corpus.
  ADR-024 separated the two for this reason.

## Verifying a change you make

Edit the real file under `config/`, then:

```bash
python -m src.graph.build          # 117 entities, 261 edges, 15 relations
python -m eval.probes.corpus_shape # the corpus measurements the files rest on
python -m pytest                   # 320 tests
```

If your edit dropped edges, the first command says so immediately.
