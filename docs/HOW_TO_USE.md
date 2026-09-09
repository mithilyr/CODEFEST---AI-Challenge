# How to use the Ashen Era Archive Assistant

One document: how to get it running, on whatever machine you have, and how to
use it once it's up. `README.md` covers the same ground plus the reasoning
behind every choice (architecture, what was measured, what was rejected) — if
you want the *why*, that's the file to read. This one is just the *how*.

You need **a few hundred MB of free disk space** either way. **No API key, no
account, and no internet connection is needed once the archive is
downloaded** — every setup path below downloads it once and every path after
that works offline.

---

## Pick one setup path

| You have | Use |
|---|---|
| Docker | [Docker](#docker) — the most isolated option; nothing installs on your machine outside the container |
| Linux or macOS, no Docker | [`setup.sh`](#linux--macos-setupsh) |
| Windows, no Docker | [`setup.exe`](#windows-setupexe) |
| None of the above, or you want to run each step yourself | [Manual setup](#manual-setup) — what all three scripts above do, one command at a time |

All four end up in the same place: the app running at `http://127.0.0.1:8000`
(or `http://localhost:8000` for Docker), backed by the full archive at
`data/Ashen_Era_Archive`. Every path is safe to re-run — each one checks what
it already did and skips it, so running it again after an interrupted first
attempt just picks up where it left off.

### Docker

From the project root:

```bash
docker compose up --build
```

First run builds the image, then downloads the ~123 MB archive into a named
Docker volume (`archive-data`) and verifies it — this takes a few minutes.
Every run after that reuses the volume, so nothing downloads again unless you
delete it. Open **http://localhost:8000**. `Ctrl-C` stops it; `docker compose
down` removes the container but keeps the volume (and therefore the archive).

Without compose:

```bash
docker build -t ashen-era .
docker run -p 8000:8000 -v ashen-era-data:/app/data ashen-era
```

To enable the optional model tiers (never required — see
[Optional: API keys](#optional-api-keys-you-dont-need-these)), add them as
environment variables in `docker-compose.yml` or with `-e` on `docker run`.

### Linux / macOS: `setup.sh`

```bash
./setup.sh
```

Finds a Python 3.11+ interpreter, creates `.venv`, installs dependencies,
downloads and unpacks the archive if `data/Ashen_Era_Archive` isn't already
complete, writes `.env` from `.env.example` if missing, verifies integrity,
then starts the app on **http://127.0.0.1:8000**. `Ctrl-C` stops it.

Run `./setup.sh --no-run` to do everything except the last step — useful if
you want to start the server yourself afterward:

```bash
.venv/bin/python -m src.ui.server
```

### Windows: `setup.exe`

Double-click `setup.exe` in the project folder, or from a terminal:

```
setup.exe
```

Same steps as `setup.sh` — Python 3.11+ detection (via the `py` launcher,
falling back to `python`/`python3` on PATH), venv, dependencies, archive
download and extraction, `.env`, integrity check, then it starts the app. It's
a standalone binary: you need Python 3.11+ installed to run the *app*, but not
to run `setup.exe` itself. `setup.exe --no-run` sets up without starting the
server.

If it can't find Python 3.11+, install one from
[python.org](https://www.python.org/downloads/) — check "Add python.exe to
PATH" during install — and run `setup.exe` again.

**Rebuilding it.** `setup.exe` is built from Go source in
`scripts/setup-windows/`. After changing that source:

```bash
scripts/build-setup-exe.sh
```

This runs `go vet` and the Go test suite before rebuilding, so a broken change
fails the build instead of shipping. Requires Go — it cross-compiles to
Windows from any platform, no Windows machine or Wine needed.

### Manual setup

What the three scripts above automate, one command at a time — see
`README.md`'s "User manual, part 1" for the full version with explanations.
In short:

```bash
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS/Linux:    source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # Windows: copy .env.example .env
curl -o Ashen_Era_Archive.zip https://benchdata792fda32.blob.core.windows.net/codefest2026/Ashen_Era_Archive.zip
# unzip it so data/Ashen_Era_Archive directly contains chronicles/, codex/, ephemera/, images/, wiki/
python -m src.ingest.integrity
python -m src.ui.server
```

---

## Using the app

Open the app in a browser. Three links across the top: **Ask**, **Graph**,
and **What you can ask**.

### Asking a question

Type a question into the box and press **Ask**, or click one of the seven
example questions on the front page. An answered question shows, in order:

1. **The answer** — usually a name.
2. **Evidence sufficiency** — `sufficient` means every step the question
   needed was found and sourced.
3. **Strategy used** — which question pattern matched, which connections were
   followed, and which name it started from.
4. **The evidence path** — every step, with the document it came from, the
   exact infobox row, and how trustworthy that source is. You can check the
   answer yourself without trusting the system.
5. **Source documents and tiers** — every document involved, with its
   ranking.

For example, *"Which war did Ravena Stormwell's own faction ultimately win?"*
answers **The War of Drowned Light**, showing two steps: Ravena Stormwell is a
member of The Silent Choir (her own page, row 3), and The Silent Choir is the
victor of The War of Drowned Light (the war's page, row 5).

### When it declines to answer

The system refuses rather than guesses, and always says why. Three cases:

- **The name isn't in the archive** — it says so plainly.
- **The name is nearly right** — e.g. asking about "Isolde Mournvail" gets
  back `Isolde Mournvale` (0.938 similarity) and `Isolde Thornwald` (0.750),
  and **it does not pick one for you**. Click a suggestion to re-ask with that
  name.
- **The question needs a connection the system doesn't track** — it follows
  15 kinds of connection, all listed on **What you can ask**; anything outside
  that list is declined, and it still shows whatever it did establish along
  the way.

### Graph and What you can ask

**Graph** draws every entity and connection as one static image — no
JavaScript, nothing loaded from the internet.

**What you can ask** is the system's own honest boundary: every entity it
knows, grouped by type, and all 15 connections it can follow, with the
infobox field names it reads and the everyday words a question might use
instead.

**Reindex corpus** (front page button) re-reads the archive from disk in
about six seconds — use it if you add or edit a document while the app is
running.

### From the command line

```bash
python -m src.query.engine "Which war did Ravena Stormwell's own faction ultimately win?"
```

Same answer, same evidence, printed as text. Use `.venv/bin/python` (or
`.venv\Scripts\python.exe` on Windows) if you're not inside an activated venv.

---

## Optional: API keys you don't need

Every key in `.env.example` is optional and the app runs fully offline
without any of them. Filling one in only changes:

| Key | What it unlocks |
|---|---|
| `GOOGLE_API_KEY` | Re-running OCR on the 17 scanned pages — their transcripts already ship in the repo, so this is only for reproducing that step from scratch |
| `VOYAGE_API_KEY` | Rebuilding the vector-search comparison baseline — its prebuilt index already ships in `.cache/index/` |
| `OPENROUTER_API_KEY` | The optional LLM planner tier and model-phrased answers, via `python -m src.ui.server --with-model` |

---

## Troubleshooting

| What you see | What it means |
|---|---|
| `corpus matches the shipped archive` never appears after `python -m src.ingest.integrity` | The archive is in the wrong folder, or a file was edited. Check `CORPUS_PATH` in `.env`, then re-extract |
| `ModuleNotFoundError` | The venv isn't active — activate it, or use `.venv/bin/python` / `.venv\Scripts\python.exe` directly |
| The page won't load | Check the terminal is still running |
| `OSError: [Errno 98] Address already in use` (or the page won't load and nothing looks wrong) | Something else already has port 8000 — often an unrelated container. `docker ps` shows it if so. Use a different port instead: `python -m src.ui.server --port 8001`, or edit the `"8000:8000"` line in `docker-compose.yml` |
| No Python 3.11+ found (`setup.sh` / `setup.exe`) | Install one from [python.org](https://www.python.org/downloads/) and re-run the script |
| It complains about an API key | It shouldn't — the demo needs none. Check you didn't pass `--with-model` |
| Dependency warnings mentioning packages you never installed (e.g. from `pip install -r requirements.txt`) | Something on your machine sets a global `PYTHONPATH` (ROS is a common cause) that leaks into the venv. Every script here (`setup.sh`, `setup.exe`, `docker-entrypoint.sh`) already clears it; if you're running `pip` by hand, use `env -u PYTHONPATH pip install -r requirements.txt` (`set PYTHONPATH=` first on Windows) |

For anything not covered here, `README.md`'s own troubleshooting table and
"How it works" section have the deeper explanation.
