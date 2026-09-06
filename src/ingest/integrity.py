"""Corpus integrity: is the archive on disk the archive the competition shipped?

The corpus is read-only competition data, held outside the repository and too
large to commit. Every measurement in this project is taken against whatever
``CORPUS_PATH`` points at, and until now nothing checked that it still matched
what we were handed.

It did not. On 2026-08-29 a text editor opened on ``wiki/`` rewrote 36 files
with Unix line endings and left behind an empty note. The rewrites were
harmless - identical content, so the evidence-unit count never moved. The empty
note was not: it ingested as a canonical document carrying zero evidence, under
the title of an entity central to one of our conflict questions. See F-016.

So this module answers one question with one command, and the manifest it reads
is 341 hashes in a 39 KB text file - small enough to commit, which is the whole
point. It covers the archive as shipped, including the ``README.txt`` and
``sample_questions.json`` that ingestion itself skips. A judge or a teammate
extracting the archive for the first time can confirm they have the same bytes
we measured against, instead of assuming it.

    python -m src.ingest.integrity                  # verify CORPUS_PATH
    python -m src.ingest.integrity --generate ...   # rebuild the manifest

The manifest is plain ``sha256sum`` format, so it is also checkable with
coreutils and diffs legibly in review. Regenerating it is a deliberate act with
its own flag, because a manifest that silently re-baselines to whatever is on
disk records nothing.

Extra files are reported in two groups. That distinction is the lesson of F-016:
an unexpected file matters when ingestion *reads* it, and is mostly noise when
ingestion skips it. A stray ``.DS_Store`` is not the same event as a stray
``.md`` in ``wiki/``.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from src.settings import PROJECT_ROOT, get_settings

#: The committed manifest of the shipped archive.
MANIFEST_PATH = PROJECT_ROOT / "config" / "corpus_manifest.sha256"

#: Read in blocks so a 123 MB archive does not become 123 MB of resident memory.
_BLOCK_SIZE = 1024 * 1024


def hash_bytes(data: bytes) -> str:
    """Return the SHA-256 hex digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file, read incrementally."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(_BLOCK_SIZE):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class IntegrityReport:
    """The difference between the corpus on disk and the shipped manifest."""

    #: In the manifest, absent from disk.
    missing: list[str] = field(default_factory=list)
    #: Present in both, different bytes.
    modified: list[str] = field(default_factory=list)
    #: On disk, not in the manifest, and ingestion reads them.
    extra_ingested: list[str] = field(default_factory=list)
    #: On disk, not in the manifest, and ingestion skips them.
    extra_ignored: list[str] = field(default_factory=list)
    #: Files that matched.
    verified: int = 0

    @property
    def is_clean(self) -> bool:
        """True when the corpus is byte-identical to the shipped archive.

        Files ingestion ignores still count as drift. They are reported
        separately because they are usually benign, not because they are
        nothing - the empty note in F-016 looked benign too.
        """
        return not (
            self.missing
            or self.modified
            or self.extra_ingested
            or self.extra_ignored
        )

    @property
    def is_safe_to_ingest(self) -> bool:
        """True when nothing ingestion reads differs from the shipped archive."""
        return not (self.missing or self.modified or self.extra_ingested)

    def summary(self) -> str:
        """A short report, in the style of the ingestion summary."""
        lines = [
            f"files verified       : {self.verified}",
            f"missing              : {len(self.missing)}",
            f"modified             : {len(self.modified)}",
            f"extra (ingested)     : {len(self.extra_ingested)}",
            f"extra (ignored)      : {len(self.extra_ignored)}",
        ]
        for label, paths in (
            ("missing", self.missing),
            ("modified", self.modified),
            ("extra, INGESTED", self.extra_ingested),
            ("extra, ignored", self.extra_ignored),
        ):
            for path in paths:
                lines.append(f"    {label}: {path}")

        if self.is_clean:
            lines.append("corpus matches the shipped archive.")
        elif self.is_safe_to_ingest:
            lines.append(
                "corpus differs, but only in files ingestion does not read."
            )
        elif not (self.missing or self.modified):
            # Added files only. This is somebody handing the system a document,
            # which is a normal thing to do and the case the final round poses -
            # not the F-016 failure, where the shipped archive changed underneath
            # us. Both used to print the same accusation, so the system's first
            # response to a judge's own file was to report it as drift. The check
            # is unchanged; only what it says about this case is.
            lines.append(
                f"corpus has grown: {len(self.extra_ingested)} document(s) added "
                "that ingestion will read. This is expected when documents are "
                "supplied deliberately - reindex to include them. Measurements "
                "taken now are not comparable with earlier checkpoints, because "
                "the corpus is no longer the one those numbers were derived from."
            )
        else:
            lines.append(
                "CORPUS DRIFT: files ingestion reads are missing or modified "
                "against the shipped archive. Measurements taken now are not "
                "comparable with earlier checkpoints, and this is the shape of "
                "F-016 - an editor rewrote 36 files and left a phantom document "
                "behind. See docs/failures.md."
            )
        return "\n".join(lines)


def manifest_from_zip(zip_path: Path, prefix: str | None = None) -> dict[str, str]:
    """Hash every file in the distributed archive.

    This is the authoritative source: the zip is what the competition shipped,
    and generating from it rather than from an extracted copy means the manifest
    cannot inherit damage the extracted copy has already taken.

    Args:
        zip_path: The ``Ashen_Era_Archive.zip`` as distributed.
        prefix: Leading path component to strip. Inferred when omitted.

    Returns:
        Relative POSIX path -> SHA-256 hex digest.
    """
    with zipfile.ZipFile(zip_path) as archive:
        names = [n for n in archive.namelist() if not n.endswith("/")]
        if prefix is None:
            roots = {n.split("/", 1)[0] for n in names if "/" in n}
            prefix = f"{roots.pop()}/" if len(roots) == 1 else ""
        return {
            name[len(prefix):]: hash_bytes(archive.read(name))
            for name in names
            if name.startswith(prefix)
        }


def manifest_from_dir(root: Path) -> dict[str, str]:
    """Hash every file under ``root``, keyed by relative POSIX path."""
    return {
        path.relative_to(root).as_posix(): hash_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def write_manifest(entries: dict[str, str], path: Path, source: str) -> None:
    """Write a manifest in ``sha256sum`` format, sorted for a stable diff.

    Args:
        entries: Relative path -> digest.
        path: Destination.
        source: Provenance note recorded in the header, so a reader can tell
            what the hashes were taken from without reading the commit log.
    """
    lines = [
        "# Ashen Era Archive - integrity manifest",
        "#",
        f"# generated from: {source}",
        f"# files: {len(entries)}",
        "#",
        "# Verify with:  python -m src.ingest.integrity",
        "# Regenerating is deliberate - see src/ingest/integrity.py and F-016.",
        "",
    ]
    lines += [f"{digest}  {rel}" for rel, digest in sorted(entries.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_manifest(path: Path = MANIFEST_PATH) -> dict[str, str]:
    """Parse a ``sha256sum``-format manifest, ignoring blank and comment lines."""
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, rel = line.partition("  ")
        if not rel:
            raise ValueError(f"malformed manifest line: {line!r}")
        entries[rel] = digest
    return entries


def _ingested_paths(root: Path) -> set[str]:
    """Relative paths that ingestion would actually read.

    Imported lazily: discovery pulls in the loader stack, and integrity checking
    should stay usable even if that stack is mid-change.
    """
    from src.ingest.metadata import discover

    return {
        Path(record.path).resolve().relative_to(root.resolve()).as_posix()
        for record in discover(root)
    }


def verify(
    root: Path | None = None, manifest: dict[str, str] | None = None
) -> IntegrityReport:
    """Compare the corpus on disk against the shipped manifest.

    Args:
        root: Corpus directory. Defaults to the configured ``CORPUS_PATH``.
        manifest: Expected hashes. Defaults to the committed manifest.

    Returns:
        An :class:`IntegrityReport`. Never raises on drift - drift is a result,
        not an error, and the caller decides what it means.
    """
    root = root or get_settings().require_corpus()
    expected = manifest if manifest is not None else read_manifest()
    on_disk = manifest_from_dir(root)

    missing = sorted(set(expected) - set(on_disk))
    modified = sorted(
        rel for rel in set(expected) & set(on_disk) if expected[rel] != on_disk[rel]
    )
    extra = set(on_disk) - set(expected)

    ingested = _ingested_paths(root) if extra else set()
    return IntegrityReport(
        missing=missing,
        modified=modified,
        extra_ingested=sorted(extra & ingested),
        extra_ignored=sorted(extra - ingested),
        verified=len(set(expected) & set(on_disk)) - len(modified),
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 when the corpus matches, 1 when it drifts."""
    parser = argparse.ArgumentParser(
        prog="python -m src.ingest.integrity",
        description="Verify the corpus against the shipped archive manifest.",
    )
    parser.add_argument(
        "--generate",
        metavar="SOURCE",
        help="Rebuild the manifest from a .zip or an extracted directory. "
        "Deliberate act: overwrites the committed baseline.",
    )
    parser.add_argument(
        "--allow-ignored",
        action="store_true",
        help="Exit 0 when the only drift is in files ingestion does not read.",
    )
    args = parser.parse_args(argv)

    if args.generate:
        source = Path(args.generate)
        entries = (
            manifest_from_zip(source)
            if source.suffix == ".zip"
            else manifest_from_dir(source)
        )
        write_manifest(entries, MANIFEST_PATH, source.name)
        print(f"wrote {len(entries)} hashes to {MANIFEST_PATH}")
        return 0

    report = verify()
    print(report.summary())
    if report.is_clean:
        return 0
    return 0 if args.allow_ignored and report.is_safe_to_ingest else 1


if __name__ == "__main__":
    sys.exit(main())
