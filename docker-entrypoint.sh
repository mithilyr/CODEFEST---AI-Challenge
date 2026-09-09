#!/usr/bin/env bash
# Runs on every container start. Downloads and unpacks the archive into the
# (normally volume-mounted) data/ directory if it isn't already there, then
# hands off to whatever command the container was started with.
set -euo pipefail

ARCHIVE_URL="https://benchdata792fda32.blob.core.windows.net/codefest2026/Ashen_Era_Archive.zip"
ARCHIVE_DIR="${CORPUS_PATH:-data/Ashen_Era_Archive}"

log() { printf '\n==> %s\n' "$1"; }

NEED=0
for sub in chronicles codex ephemera images wiki; do
  [ -d "$ARCHIVE_DIR/$sub" ] || NEED=1
done

if [ "$NEED" -eq 1 ]; then
  log "Downloading the Ashen Era Archive (~123 MB)"
  mkdir -p "$(dirname "$ARCHIVE_DIR")"
  tmpzip="$(mktemp -t ashen_era_archive.XXXXXX.zip)"
  tmpdir="$(mktemp -d -t ashen_era_archive.XXXXXX)"
  curl -fsSL -o "$tmpzip" "$ARCHIVE_URL"

  log "Extracting archive"
  unzip -q "$tmpzip" -d "$tmpdir"

  src="$tmpdir"
  if [ ! -d "$src/wiki" ]; then
    found="$(find "$tmpdir" -maxdepth 3 -type d -name wiki | head -n1 || true)"
    [ -n "$found" ] && src="$(dirname "$found")"
  fi
  if [ ! -d "$src/wiki" ]; then
    echo "Could not find the archive's 'wiki' folder after extraction." >&2
    exit 1
  fi

  rm -rf "$ARCHIVE_DIR"
  mkdir -p "$ARCHIVE_DIR"
  find "$src" -mindepth 1 -maxdepth 1 -exec mv {} "$ARCHIVE_DIR"/ \;
  rm -rf "$tmpzip" "$tmpdir"
else
  log "Archive already present at $ARCHIVE_DIR"
fi

[ -f .env ] || cp .env.example .env

log "Verifying archive integrity"
python -m src.ingest.integrity

exec "$@"
