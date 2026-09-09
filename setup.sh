#!/usr/bin/env bash
# Auto-setup for the Ashen Era Archive Assistant (Linux / macOS).
#
# Creates the venv, installs dependencies, downloads and unpacks the archive
# if it isn't already there, writes .env, verifies integrity, and starts the
# web app. Safe to re-run: every step is skipped if already done.
#
#   ./setup.sh            # full setup, then start the server
#   ./setup.sh --no-run   # set up only, don't start the server
set -euo pipefail

# ROS (and some other toolchains) export a PYTHONPATH pointing at a different
# Python's site-packages. That leaks into any venv's pip and produces bogus
# "requires X, which is not installed" warnings about packages this project
# never asked for. Unset it for every python/pip call below so the venv stays
# isolated, without touching the user's shell environment.
unset PYTHONPATH

cd "$(dirname "${BASH_SOURCE[0]}")"

ARCHIVE_URL="https://benchdata792fda32.blob.core.windows.net/codefest2026/Ashen_Era_Archive.zip"
ARCHIVE_DIR="data/Ashen_Era_Archive"
RUN_SERVER=1
for arg in "$@"; do
  case "$arg" in
    --no-run) RUN_SERVER=0 ;;
    *) echo "unknown flag: $arg" >&2; exit 1 ;;
  esac
done

log() { printf '\n==> %s\n' "$1"; }

# --- 1. Find a Python 3.11+ interpreter --------------------------------
log "Looking for Python 3.11+"
PYBIN=""
for cand in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    ver="$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo 0.0)"
    major="${ver%%.*}"; minor="${ver##*.}"
    if [ "$major" -eq 3 ] && [ "$minor" -ge 11 ]; then
      PYBIN="$cand"
      break
    fi
  fi
done
if [ -z "$PYBIN" ]; then
  echo "No Python 3.11+ interpreter found on PATH." >&2
  echo "Install one from https://www.python.org/downloads/ and re-run this script." >&2
  exit 1
fi
echo "using $PYBIN ($("$PYBIN" --version))"

# --- 2. Create the venv --------------------------------------------------
if [ ! -x .venv/bin/python ]; then
  log "Creating virtual environment (.venv)"
  "$PYBIN" -m venv .venv
else
  log "Virtual environment already exists"
fi

# --- 3. Install dependencies --------------------------------------------
log "Installing dependencies"
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

# --- 4. .env --------------------------------------------------------------
if [ ! -f .env ]; then
  log "Creating .env from .env.example"
  cp .env.example .env
else
  log ".env already exists, leaving it alone"
fi

# --- 5. Archive -------------------------------------------------------
NEED=0
for sub in chronicles codex ephemera images wiki; do
  [ -d "$ARCHIVE_DIR/$sub" ] || NEED=1
done
if [ "$NEED" -eq 1 ]; then
  log "Downloading the Ashen Era Archive (~123 MB)"
  mkdir -p data
  tmpzip="$(mktemp -t ashen_era_archive.XXXXXX.zip)"
  tmpdir="$(mktemp -d -t ashen_era_archive.XXXXXX)"
  trap 'rm -rf "$tmpzip" "$tmpdir"' EXIT
  curl -fsSL -o "$tmpzip" "$ARCHIVE_URL"

  log "Extracting archive"
  unzip -q "$tmpzip" -d "$tmpdir"

  # The zip may or may not wrap its contents in an extra top-level folder.
  # Find whichever directory in the extraction actually holds `wiki/`, and
  # use that as the source, so both layouts end up in the same place.
  src="$tmpdir"
  if [ ! -d "$src/wiki" ]; then
    found="$(find "$tmpdir" -maxdepth 3 -type d -name wiki | head -n1 || true)"
    if [ -n "$found" ]; then
      src="$(dirname "$found")"
    fi
  fi
  if [ ! -d "$src/wiki" ]; then
    echo "Could not find the archive's 'wiki' folder after extraction." >&2
    exit 1
  fi

  rm -rf "$ARCHIVE_DIR"
  mkdir -p "$ARCHIVE_DIR"
  # Move contents (including dotfiles) rather than the folder itself, so the
  # destination path is exactly $ARCHIVE_DIR regardless of the zip's layout.
  find "$src" -mindepth 1 -maxdepth 1 -exec mv {} "$ARCHIVE_DIR"/ \;
  rm -rf "$tmpzip" "$tmpdir"
  trap - EXIT
else
  log "Archive already present at $ARCHIVE_DIR"
fi

# --- 6. Integrity check ---------------------------------------------------
log "Verifying archive integrity"
.venv/bin/python -m src.ingest.integrity

# --- 7. Run -----------------------------------------------------------
if [ "$RUN_SERVER" -eq 1 ]; then
  log "Starting the app on http://127.0.0.1:8000 (Ctrl-C to stop)"
  exec .venv/bin/python -m src.ui.server
else
  log "Setup complete. Start the app with: .venv/bin/python -m src.ui.server"
fi
