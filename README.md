# Ashen Era Archive Assistant

**Ask a question whose answer is spread across several documents, and get the
answer with every source it was built from.**

Built for SLIIT Codefest 2026, AI Competition sub-track 1B — *Connecting Facts
Across Thousands of Pages* — powered by IFS.

---

## What this is, and why we built it this way

The Ashen Era Archive is a 317-document collection of invented fantasy lore:
wiki pages, chronicles, an authoritative codex, and a pile of unreliable
in-world letters, sermons and contracts. Some questions about it cannot be
answered from any single page.

Take a real one: *"Which accord was ultimately won by the faction of which
Ederon Fellgard is a member?"* Ederon Fellgard's page says which faction he
belongs to and never mentions an accord. The page naming the accord's winner
never mentions Ederon Fellgard. You have to read one page, carry a fact across
to another, and join them.

The usual approach is to turn every document into vectors and retrieve the
passages most similar to the question. We built that first and measured it, so
we would be comparing against something real rather than a straw man. On the
seven development questions it answered 2 of 7 — and more tellingly, it never
once retrieved *all* the documents an answer needed. Three of the seven
retrieved neither required document. The two pages share no vocabulary, so no
amount of similarity search brings them together, and retrieving more passages
cannot manufacture a connection that similarity cannot see.

So we do something different. Most wiki pages carry a small fact table — an
infobox — with rows like `Member of | The Iron-Ring Cartel`. We read those rows
and turn them into a network of named connections between people, factions,
places, wars and artifacts. Answering a question then means walking that
network: find the person, follow "member of" to their faction, follow "victor
of" to the war that faction won. Every step records which document and which row
it came from, so the answer arrives with its evidence attached.

Two commitments shape everything else:

- **Ordinary code first, AI only where it is needed.** The part that actually
  produces an answer is plain Python walking a data structure. No AI model is
  involved in it. Models are used in three narrow places, all optional, and the
  system counts how often each is used so we can report it honestly.
- **Say "I don't know" rather than guess.** If a question names something not in
  the archive, or asks for a kind of connection we do not track, the system says
  exactly that and shows what it *did* work out. It never invents an answer to
  look useful. A confident wrong answer with citations is worse than no answer.

---

## What it is built with

**Language:** Python 3.11.

**No web framework, and no AI framework.** The web interface is Python's
built-in `http.server`. There is no Django, Flask, FastAPI, LangChain, or vector
database. The competition requires every team member to be able to explain and
change any part of the submission on demand, so a dependency nobody on the team
could defend is a liability rather than a shortcut.

The entire dependency list is eight packages:

| Package | Used for |
|---|---|
| `numpy` | The comparison baseline's similarity search — one matrix multiply |
| `pdfplumber` | Reading text out of PDFs |
| `python-docx` | Reading Word documents |
| `PyYAML` | Loading the two configuration files |
| `python-dotenv` | Loading settings from `.env` |
| `pytest` | The test suite |
| `google-genai` | Google Gemini — reading 17 scanned pages, done once, results saved |
| `voyageai` | Voyage AI — embeddings, used only by the comparison baseline |
| *(OpenRouter)* | Called over plain HTTP, no package needed. Optional, off by default |

**Outside services.** All three are optional, and none is needed to run the app:

| Service | What it does here | Needed to run the app? |
|---|---|---|
| [Google AI Studio](https://aistudio.google.com/apikey) (Gemini) | Read 17 scanned PDF pages that have no text layer | No — the transcripts are saved in the repository |
| [Voyage AI](https://dashboard.voyageai.com) | Embeddings, for the comparison baseline only | No — only to rebuild that baseline |
| [OpenRouter](https://openrouter.ai) | Optional AI help with unusual questions, and with wording answers | No — off by default |

---

## User manual, part 1: getting it running

You need **Python 3.11 or newer** and a few hundred MB of disk space. **You do
not need an API key, an account with anyone, or an internet connection** once
the files are downloaded.

Windows commands are shown. On macOS or Linux use `source .venv/bin/activate`
and `.venv/bin/python` instead.

**1. Download the code.**

```bash
git clone https://github.com/mithilyr/CODEFEST---AI-Challenge.git
```

```bash
cd CODEFEST---AI-Challenge
```

**2. Create a private Python environment and install the eight packages.**

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

**3. Download the archive.** It is about 123 MB, and is not stored in the code
repository.

```bash
curl -o Ashen_Era_Archive.zip https://benchdata792fda32.blob.core.windows.net/codefest2026/Ashen_Era_Archive.zip
```

Unzip it so that the folder `data/Ashen_Era_Archive` is the one **directly
containing** `chronicles`, `codex`, `ephemera`, `images` and `wiki`. If your
unzip tool adds an extra folder in between, move the inner one up. You can also
put the archive anywhere else and point `CORPUS_PATH` at it in the next step.

**4. Create the settings file.**

```bash
cp .env.example .env
```

**Leave every key blank.** The only setting that matters is `CORPUS_PATH`, and
it already points at `data/Ashen_Era_Archive`. See
[`configuration-example/`](configuration-example/) for an annotated copy
explaining what each optional key would buy you.

**5. Check it worked.** This confirms the archive is complete and unmodified:

```bash
python -m src.ingest.integrity
```

It should end with `corpus matches the shipped archive.` If it does not, a file
has been altered or is missing — re-extract the archive.

**6. Start the app.**

```bash
python -m src.ui.server
```

It prints a short summary and then a web address:

```
building the graph ...
  118 entities, 265 edges, 30553 evidence units
  model tiers: off - fully deterministic (pass --with-model to enable)

  Ashen Era assistant on http://127.0.0.1:8000
```

Open **http://127.0.0.1:8000** in a browser. Press `Ctrl-C` in the terminal to
stop it.

### If something goes wrong

| What you see | What it means |
|---|---|
| `corpus matches the shipped archive` never appears | The archive is in the wrong folder, or a file was edited. Check `CORPUS_PATH`, then re-extract |
| `ModuleNotFoundError` | The environment is not active. Run `.venv\Scripts\activate` again |
| The page will not load | Check the terminal is still running. If the port is in use, run `python -m src.ui.server --port 8001` |
| It complains about an API key | It should not. The demo needs none — check you did not pass `--with-model` |

---

## User manual, part 2: using the app

Three pages, linked across the top: **Ask**, **Graph**, and **What you can ask**.

### Asking a question

Type a question into the box and press **Ask**. If you would rather start from
something known to work, the front page lists seven example questions — click
any one to run it.

An answered question shows, in order:

1. **The answer** — usually a name.
2. **Evidence sufficiency** — `sufficient` means every step the question needed
   was found and sourced.
3. **Strategy used** — which question pattern matched, which connections were
   followed, and which name it started from.
4. **The evidence path** — the important part. Every step is listed with the
   document it came from, the exact infobox row, and how trustworthy that source
   is. You can check the answer yourself without trusting the system.
5. **Source documents and tiers** — every document involved, with its ranking.

For example, *"Which war did Ravena Stormwell's own faction ultimately win?"*
answers **The War of Drowned Light** and shows the two steps behind it: Ravena
Stormwell is a member of The Silent Choir (from her own page, row 3), and The
Silent Choir is the victor of The War of Drowned Light (from the war's page,
row 5).

### When it will not answer — and why that is the point

The system refuses rather than guesses, and every refusal explains itself. There
are three kinds you will meet.

**The name is not in the archive.** Ask about something the archive never
mentions and it says so plainly, instead of returning something vaguely related.

**The name is nearly right.** Ask about "Isolde Mournvail" and it replies that
this is not a name in the corpus, offers `Isolde Mournvale` at 0.938 similarity
and `Isolde Thornwald` at 0.750, and **does not pick one for you**. Click a
suggestion to ask again using that name. It behaves this way because the archive
contains two different real people whose names are 0.839 similar — any system
loose enough to fix your typo automatically is also loose enough to quietly
answer about the wrong person.

**The question needs a connection we do not track.** The system follows 15 kinds
of connection, all listed on the **What you can ask** page. A question outside
that list is declined, and the page shows the full list so you can see where the
boundary is. It still displays anything it did establish along the way.

In every case the page names the reason in the engine's own words, rather than
showing an empty result.

### The other two pages

**Graph** draws all the entities and their connections as a single picture. It
is a plain image — no JavaScript, and nothing loaded from the internet.

**What you can ask** is the honest boundary of the system: every entity it knows
grouped by type, and all 15 connections it can follow, each listed with the
infobox field names it reads and the everyday words a question might use
instead. If you want to know what this system can and cannot do, read this page.

**Reindex corpus**, a button on the front page, re-reads the archive from disk
in about six seconds. Use it if you add or edit a document while the app is
running.

### Asking from the command line

```bash
python -m src.query.engine "Which war did Ravena Stormwell's own faction ultimately win?"
```

Same answer, same evidence, printed as text.

---

## How it works

Full detail, with a diagram, is in [`docs/architecture.md`](docs/architecture.md).
In outline, four stages:

**1. Read the archive.** 340 files are found and duplicates collapsed — the same
work often ships as both `.docx` and `.pdf` — leaving 317 distinct documents,
broken into 30,553 individually citable passages. Each passage remembers where
it came from and how reliable that source is. Seventeen scanned pages have no
text layer; those were read once by Gemini and the transcripts are saved in the
repository, so this stage needs no API key.

**2. Build the network.** Every wiki infobox row becomes a connection. The
result is **118 entities and 265 edges** across 15 kinds of connection — small
enough to be a plain Python dictionary, which is why there is no graph database.
Names are matched exactly, never approximately.

**3. Answer the question.** Three methods are tried in order, each handing over
only if it declines:

| | Method | What it does |
|---|---|---|
| 1 | Templates | Recognises known question shapes and follows a fixed route. Precise, but narrow |
| 2 | Keyword cues | Matches everyday words in the question against the connection vocabulary. Wider reach, less precise |
| 3 | AI planner | Asks a model to *propose a route*, which is then checked against the real network. It never writes an answer. **Off by default** |

If all three decline, the question is refused with a named reason. That is a
result, not an error, and the app displays it as one.

**4. Show it.** The answer is rendered with its full evidence trail. The
interface adds no reasoning of its own — it only displays what the engine
returned, and tests exist purely to keep it that way, failing if the display
code so much as imports the reasoning code.

### Two files that are deliberately not code

`config/authority.yaml` ranks how far each kind of source is to be trusted, and
`config/relations.yaml` records which infobox field names mean the same
connection — `Member of`, `Membership`, `Affiliation` and `Allegiance` are all
one thing. Both are plain text with comments, so a reader who disagrees with a
line can change it and re-run the build without touching any Python.
[`configuration-example/`](configuration-example/) explains both.

---

## What we measured

Every figure below can be reproduced with the command beside it. None costs
money or needs a key, except where marked.

| | Result | Command |
|---|---|---|
| Documents read | 340 files → 317 documents → 30,553 passages | `python -m src.ingest.pipeline` |
| Network built | 118 entities and 265 edges, across 15 connections | `python -m src.graph.build` |
| Independently corroborated | 259 of the 265 connections also appear in other collections | `python -m src.graph.corroborate` |
| Tests | 490 passing, no network calls | `python -m pytest` |
| Vector-search baseline | 2 of 7 correct; 0 of 9 with complete evidence | `python -m eval.run_eval --checkpoint baseline` * |
| Our answers, development set | 7 of 7 correct, with complete evidence | `python -m pytest tests/test_query.py` |
| Our answers, 49 frozen questions | 22 correct, 31 with complete evidence | `python -m comparison.harness` |
| Refusing when it should | 6 of 6 unanswerable questions declined | `python -m comparison.harness` |

\* needs a Voyage key and a one-off index build. Everything else runs offline.

**Two caveats, which matter more than the numbers.**

**The 7 of 7 is not the headline.** Those seven are the questions we developed
against, so they measure fit, not ability. The honest measure is the second set:
49 questions written by teammates who had not seen the code, and frozen before
either method ran against them. On those, the narrow template method recognises
no question shape at all in 36 of 49. The three-method system answers 22. Never
quote the 7/7 without the 36/49 beside it.

**Every score is provisional.** The answer key was reviewed by one person, not
the two we required of ourselves. Automated checks found no gaps in it, but no
second human reviewer was available before the deadline, and we have not
relabelled anything to look better. The evaluation harness prints this warning
itself on every run.

---

## Where to read more

| File | What is in it |
|---|---|
| [`docs/engineering-notes.md`](docs/engineering-notes.md) | The detailed technical README this one replaced — every number with its caveats |
| [`docs/architecture.md`](docs/architecture.md) | The full architecture, with the diagram |
| [`docs/numbers.md`](docs/numbers.md) | Every figure we allow ourselves to quote, and the command that re-derives it |
| [`docs/decisions.md`](docs/decisions.md) | Why each choice was made, including those later proved wrong |
| [`docs/failures.md`](docs/failures.md) | Approaches tried and abandoned, with the measurement that killed each one |
| [`docs/limitations.md`](docs/limitations.md) | What this system cannot do |
| [`TEAM.md`](TEAM.md) | Who did what |

### How the code is organised

```
src/ingest/            reading the archive, removing duplicates, ranking sources
src/graph/             turning infobox rows into the network
src/query/             the three answering methods
src/ui/                the web app
src/baseline/          the vector-search comparison
src/clients/           talking to Gemini, Voyage and OpenRouter
config/                the two editable configuration files
configuration-example/ annotated copies of them, with the reasoning
eval/                  the answer key, the scoring, and the frozen question sets
comparison/            the measurement behind the three-method design
docs/                  architecture, decisions, failures, limitations, numbers
tests/                 490 tests
ai_usage/              our AI collaboration transcripts, a required deliverable
```
