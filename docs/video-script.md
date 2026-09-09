# Demo video — recording script

Challenge requirement (CLAUDE.md, §5.2): **≤10 minutes total, with ≥3–4
minutes of unedited, continuous live demo, recorded against a warm cache —
never a cold one.** Everything below is written against what the app actually
does today; every number and every UI string quoted here was checked live
against this build on 2026-09-09, not remembered — re-verified after Yasiru's
final pull (`15bba36`, one-command setup + Docker, ADR-049) confirmed that
pull touched only setup tooling and docs, not `src/` or `eval/`: corpus
integrity, 118 entities / 265 edges all re-ran clean at that commit.

Two segments are marked **[EDITED OK]** and **[LIVE — DO NOT CUT]**. Only one
continuous take needs to be unedited; the rest can have cuts, retakes, and a
voiceover recorded separately.

---

## 0. Before you press record

Do these once, in order, **and do not skip the last one**:

1. Close every other Claude Code window. The AI-usage re-export
   (`python ai_usage/export_logs.py`) undercounts if one is left open and
   still appending to its transcript — this is F-038's sibling problem, not
   hypothetical.
2. `python -m src.ingest.integrity` — confirm `corpus matches the shipped
   archive.` A drifted corpus is a different demo than the one the report
   describes.
3. **Warm the cache.** Run the app once *before* recording and click through
   the exact steps in §2 below, off-camera. This populates:
   - `.cache/responses_openrouter/` — the planner-tier answer in step 2.4 must
     hit this cache live; a cold call adds 5–15s of visible latency and risks
     a free-tier rate limit failing on camera.
   - `ocr_cache/` — already warm; nothing to do, but don't delete it.
   Confirm the warm-up worked:
   ```
   python -m comparison.planner_sweep
   ```
   If this has already been run today (it has — `comparison/results/
   planner_sweep.json` exists), it replays entirely from cache and finishes in
   under a second. That is your warm-cache proof; you can screenshot the
   terminal output as backup evidence if a judge asks.
4. Pick a terminal font size and window size you won't need to change
   mid-recording. Resizing mid-take is the kind of thing that makes an
   "unedited" claim look edited.
5. Have three browser tabs ready but not yet opened: `localhost:8000`
   (front page), and two more you'll open live in §2.

---

## 1. Cold open — the problem [EDITED OK], ~45s

Talking head or voiceover over a static slide/terminal. Can be recorded
separately and cut in.

**Say, in your own words, covering:**
- Sub-track 1B needs answers that live in *two* documents that share no
  vocabulary — name the concrete example: dev question `1b_007`, "Which
  accord was ultimately won by the faction of which Ederon Fellgard is a
  member?" `wiki/ederon_fellgard.md` never mentions an accord; the accord's
  own page never mentions Ederon Fellgard.
- State the baseline result plainly, because it is the reason the rest of the
  video looks the way it does: a competent vector-RAG baseline scored **2/7**
  answer correctness and **0/9 complete evidence** — not one question
  retrieved every document its answer needed.
- One sentence on why: similarity search has no mechanism for a *reverse*
  lookup across a vocabulary gap. That is a structural failure, not a tuning
  problem — raising `k` does not fix it.

**Show on screen while you say it:** `docs/report.md` §1, or the architecture
diagram (`docs/diagrams/architecture.svg`) zoomed to the Checkpoint-1 box.

---

## 2. Architecture, in 60 seconds [EDITED OK]

Voiceover over the architecture diagram (`docs/diagrams/architecture.svg`),
panning through it left to right.

**Say:**
- "One pipeline, four stages, one rule: every stage resolves deterministically
  first, and escalates to a model only on a named, testable failure condition."
- Ingest: 340 files → 317 canonical documents, 30,553 evidence units, each
  citable.
- Graph: infobox rows → 118 entities, 265 edges, a plain Python dict — no
  graph database.
- Query: three tiers, each running only if the one before it declined —
  templates, then keyword cues, then an opt-in model that proposes a *route*,
  never an answer.
- "Everything from here is live."

---

## 3. LIVE DEMO [LIVE — DO NOT CUT], 4–5 minutes

Start recording this segment as one continuous take: screen only, system
audio + mic narration, no cuts, no edits, timestamp visible if your recorder
supports it. If you flub a line, keep going and note the timestamp for the
video description rather than re-cutting — an edited "live" segment defeats
the point of the requirement.

### 3.1 Boot, with the model tier on (~30s)

```
python -m src.ui.server --with-model
```

**Narrate while it builds:** "Starting the app with `--with-model` — that
turns on the two optional tiers, the LLM planner and model phrasing. Watch:
it still builds the graph the same way, because those tiers only run if the
two deterministic ones in front of them decline."

It prints:
```
building the graph ...
  118 entities, 265 edges, 30553 evidence units
  model tiers: on

  Ashen Era assistant on http://127.0.0.1:8000
```

Open `http://127.0.0.1:8000`.

### 3.2 A question that just works (~60s)

Click one of the seven example questions on the front page — use *"Which war
did Ravena Stormwell's own faction ultimately win?"*

**Point at, while the answer renders:**
1. The answer: **The War of Drowned Light**.
2. Evidence sufficiency: `sufficient`.
3. Strategy used — say aloud: "template tier, tier one — no model touched
   this."
4. The evidence path — two hops, each with its source document and the exact
   infobox row: Ravena Stormwell is a member of The Silent Choir (her own
   page), and The Silent Choir is victor of The War of Drowned Light (the
   war's page).

**Say:** "Every step is a citation you can check yourself without trusting
the system."

### 3.3 A refusal that explains itself (~45s)

Type: `Isolde Mournvail`

**Point at:** it does not guess. It says this name is not in the corpus, and
offers `Isolde Mournvale` at 0.938 similarity and `Isolde Thornwald` at 0.750
— **and picks neither for you.**

**Say:** "Two real people in this archive are 0.839 similar to each other.
Any system that auto-corrects a name that confidently is also confident
enough to answer about the wrong person. Click a suggestion to re-ask with
that name" — click one, show it resolve.

### 3.4 The planner tier, live and cited (~75s) — the payoff beat

Type exactly: `The Gravemaw Wyrm dens in one particular site. Who rules that
site?`

**Say before it returns:** "Watch the strategy line. Templates and keyword
cues both look at this and find nothing to route on — that's tier one and two
declining. What happens next is the third tier."

**Point at the result:**
- A banner reading **"ROUTED BY A LANGUAGE MODEL"**, stating plainly: *"No
  deterministic template matched, so this route was proposed by a model
  rather than by a rule. It chose where to look; it did not write the
  answer."* It shows the proposed plan (start entity → relation chain) and
  states every name in it was checked against the graph before anything was
  traversed.
- The answer: **The Bleeding Crown**, evidence sufficiency
  `planned_sufficient`, citing `wiki/gravemaw_wyrm.md` and
  `wiki/marrowwell_abbey.md` — the same citation trail as every other answer.

**Say:** "This is one of four questions, out of the fifty-five we measured the
whole system against, where this tier is the difference between an answer and
a decline — the other fifty-one either don't need it or aren't helped by it.
That's a real but narrow contribution, and we say so in the report rather than
oversell it."

### 3.5 The honest boundary (~45s)

Click **"What you can ask."**

**Say:** "Every entity this system knows, and all fifteen kinds of connection
it can follow — this is the actual boundary, not a marketing page. Ask
anything outside this list and it declines rather than guessing."

### 3.6 Reindex, live (~30s)

Click **"Reindex corpus."**

**Say, while it runs (~6s):** "If a document changes while the server is
running, this re-reads the archive from disk — no restart needed." Point at
the before/after counts it reports.

**[END LIVE SEGMENT]** — check the elapsed time before stopping; it must read
≥3–4 minutes from the boot command in §3.1 to here. If it's short, extend
§3.2 or §3.5 rather than cutting a new question in — the whole point is one
continuous take.

---

## 4. Close [EDITED OK], ~40s

**Say:**
- The headline number, always paired: "Seven of seven on the dev questions is
  fit, not capability — the number that means something is that on 55
  questions written by teammates who never saw this code, and frozen before
  either routing approach ran against them, the plain template approach
  recognizes no question shape at all on 36 of 49."
- One honest limitation, by name: "every evaluation number in this report is
  still marked provisional — the answer key has one human reviewer, not the
  two we set out to require, and we say so on every single run rather than
  quietly dropping the caveat."
- Reproducibility, one sentence: "Anyone judging this can stand it up with one
  command — `setup.sh` on Linux/macOS, `setup.exe` on Windows, or
  `docker compose up --build` — same steps, no manual venv wrangling."
- Where to read more: `submission_report.pdf`, and the repository at
  `github.com/mithilyr/CODEFEST---AI-Challenge`.

---

## 5. After recording

1. Stop the server (`Ctrl-C`).
2. Trim only the cold-open/architecture/close segments if needed — **never
   the live segment**, not even to remove a pause or a stumble.
3. Upload **unlisted** to YouTube (or the platform the challenge specifies).
4. Paste the real link into `docs/report.md` line 6, replacing
   `[UNLISTED YOUTUBE LINK — paste before submitting]` — then rebuild:
   ```
   python docs/build_report.py
   ```
   and re-print `docs/report.html` to `submission_report.pdf` (Edge/Chrome,
   headless or File → Print, A4, background graphics on).
5. Re-run `python ai_usage/export_logs.py` one last time — recording the demo
   and writing the link back is itself session activity worth capturing, and
   this should be the very last export before the repo is pushed.
