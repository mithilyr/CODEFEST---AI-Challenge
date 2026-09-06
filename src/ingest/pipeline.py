"""End-to-end ingestion: corpus files in, citable evidence units out.

    discover  ->  deduplicate  ->  assign authority  ->  load text blocks

The output is a list of EvidenceUnit: one citable block of text with its
canonical document, its position in that document, and its source authority.
Everything downstream - the graph builder, the vector index, the conflict
resolver - consumes these, so provenance is attached once here rather than
reconstructed in three places.

Ingestion is cached to .cache/corpus.json. Parsing the four novels alone takes a
few seconds, and a judge running the app should not pay that on every launch.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from src.ingest.authority import assign_authority, load_authority_model
from src.ingest.dedup import CanonicalDocument, DedupReport, build_canonical_documents
from src.ingest.loaders import UnsupportedFormatError, load
from src.ingest.metadata import discover
from src.ingest.ocr import OCRUnavailableError, transcribe
from src.settings import get_settings

#: Bumped whenever a change alters ingestion output, so a stale cache is
#: rebuilt rather than silently reused.
CACHE_VERSION = 1


@dataclass(frozen=True)
class EvidenceUnit:
    """One citable block of text, carrying everything a citation needs."""

    #: Stable id, e.g. "wiki/gauntlet_of_sorrowfell.md#12".
    evidence_id: str
    canonical_doc_id: str
    collection: str
    #: Human-readable position within the document, e.g. "para 69".
    locator: str
    #: paragraph | heading | table_row | page
    kind: str
    text: str
    tier: int
    subtier: int
    doctype: str | None
    subject_slug: str | None
    #: Original file to show in the UI, where one exists (scan or plate).
    display_asset: str | None


@dataclass
class IngestionResult:
    """Everything the ingestion pass produced, plus its audit trail."""

    documents: list[CanonicalDocument]
    evidence: list[EvidenceUnit]
    dedup_report: DedupReport
    #: Documents that could not be read, as (canonical_id, reason).
    failures: list[tuple[str, str]]
    elapsed_seconds: float
    #: Scans whose text came from a cached or freshly generated transcription.
    scans_transcribed: int = 0
    #: Scans with no transcription available, contributing no evidence.
    scans_skipped: int = 0

    def summary(self) -> str:
        lines = [
            self.dedup_report.summary(),
            f"evidence units       : {len(self.evidence)}",
            f"scans transcribed    : {self.scans_transcribed}",
            f"scans without text   : {self.scans_skipped}",
            f"read failures        : {len(self.failures)}",
            f"elapsed              : {self.elapsed_seconds:.1f}s",
        ]
        if self.failures:
            lines.append("failures:")
            lines += [f"    {cid}: {reason}" for cid, reason in self.failures[:10]]
        return "\n".join(lines)


def _evidence_for(
    document: CanonicalDocument, model
) -> tuple[list[EvidenceUnit], str | None]:
    """Read one document into evidence units.

    Returns the units and an error string, exactly one of which is meaningful.
    A document that cannot be read is reported rather than raised, so one bad
    file does not abort ingestion of the other 316.
    """
    if document.text_source is None:
        # A scan with no digital twin: its text can only come from OCR. A missing
        # transcription is reported as a skip rather than an error, so ingestion
        # still succeeds on a machine with no API key and no committed cache.
        if not document.needs_ocr or not document.format_variants:
            return [], None
        try:
            blocks = transcribe(
                document.format_variants[0], cache_only=True
            ).to_blocks()
        except OCRUnavailableError:
            return [], None
        except Exception as error:  # noqa: BLE001 - reported, not swallowed
            return [], f"OCR failed: {type(error).__name__}: {error}"
    else:
        try:
            blocks = load(document.text_source)
        except (UnsupportedFormatError, OSError, ValueError) as error:
            return [], f"{type(error).__name__}: {error}"

    display = str(document.display_variants[0]) if document.display_variants else None

    return [
        EvidenceUnit(
            evidence_id=f"{document.canonical_id}#{index}",
            canonical_doc_id=document.canonical_id,
            collection=document.collection,
            locator=block.locator,
            kind=block.kind,
            text=block.text,
            tier=document.tier,
            subtier=document.subtier,
            doctype=document.doctype,
            subject_slug=document.subject_slug,
            display_asset=display,
        )
        for index, block in enumerate(blocks)
    ], None


def ingest(corpus_path: Path | None = None) -> IngestionResult:
    """Run the full ingestion pass over the corpus.

    Args:
        corpus_path: Override the configured corpus location. Defaults to the
            path from settings.

    Returns:
        An :class:`IngestionResult` with documents, evidence units, and the
        audit trail for both deduplication and read failures.
    """
    started = time.perf_counter()
    settings = get_settings()
    root = Path(corpus_path) if corpus_path else settings.require_corpus()

    files = discover(root)
    documents, dedup_report = build_canonical_documents(files)
    documents = assign_authority(documents)
    model = load_authority_model()

    evidence: list[EvidenceUnit] = []
    failures: list[tuple[str, str]] = []

    transcribed = 0
    skipped = 0

    for document in documents:
        units, error = _evidence_for(document, model)
        evidence.extend(units)
        if error:
            failures.append((document.canonical_id, error))
        if document.needs_ocr:
            transcribed += bool(units)
            skipped += not units and not error

    return IngestionResult(
        documents=documents,
        evidence=evidence,
        dedup_report=dedup_report,
        failures=failures,
        elapsed_seconds=time.perf_counter() - started,
        scans_transcribed=transcribed,
        scans_skipped=skipped,
    )


def cache_path() -> Path:
    """Location of the ingestion cache."""
    return get_settings().cache_dir / f"corpus.v{CACHE_VERSION}.json"


def corpus_fingerprint() -> str:
    """A hash of every corpus file's path, size and mtime.

    WHY THIS EXISTS (ADR-036). `ingest_cached` used to return the cache whenever
    the file existed - no mtime check, no hash, no fingerprint. It was correct
    only by luck: ingestion output had not changed since the cache was written,
    verified byte-identical on 6 Sep (30,553 units, same ids, zero text
    differences).

    The luck runs out the moment a document is added, which is exactly the
    scenario the final round poses. `tests/test_diagram.py` asserts file counts,
    evidence-unit counts and corroboration counts *through this function*, and
    all three change when a document is added - so a stale cache would have kept
    the suite green while asserting pre-drop numbers. The suite that exists to
    stop the architecture diagram going stale would have been the thing going
    stale, silently.

    Path, size and mtime rather than file contents: hashing 123 MB on every
    launch would cost more than the 5s ingest the cache exists to avoid, and a
    corpus edit that preserves all three is not a case this project needs to
    survive. `python -m src.ingest.integrity` is the content check, and it is a
    separate deliberate step.
    """
    corpus = get_settings().require_corpus()
    digest = hashlib.sha256()
    for path in sorted(p for p in corpus.rglob("*") if p.is_file()):
        stat = path.stat()
        rel = path.relative_to(corpus).as_posix()
        digest.update(f"{rel}\0{stat.st_size}\0{int(stat.st_mtime)}\0".encode())
    return digest.hexdigest()


def ingest_cached(force: bool = False) -> IngestionResult:
    """Ingest, reusing a cached result only when the corpus has not changed.

    Args:
        force: Rebuild even if a valid cache exists.
    """
    path = cache_path()
    fingerprint = corpus_fingerprint()

    if not force and path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("fingerprint") != fingerprint:
            # The corpus moved under the cache. Rebuilding is 5s; serving the
            # old answer is a wrong number with a citation attached, which is
            # the failure this project exists to prevent.
            return _write_cache(path, ingest(), fingerprint)
        return IngestionResult(
            documents=[],  # Not needed by cache consumers; rebuild with force=True.
            evidence=[EvidenceUnit(**unit) for unit in payload["evidence"]],
            dedup_report=DedupReport(**payload["dedup_report"]),
            failures=[tuple(f) for f in payload["failures"]],
            elapsed_seconds=payload["elapsed_seconds"],
            scans_transcribed=payload.get("scans_transcribed", 0),
            scans_skipped=payload.get("scans_skipped", 0),
        )

    return _write_cache(path, ingest(), fingerprint)


def _write_cache(path: Path, result: IngestionResult, fingerprint: str) -> IngestionResult:
    """Persist an ingestion result under the fingerprint it was produced from."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "fingerprint": fingerprint,
                "evidence": [asdict(unit) for unit in result.evidence],
                "dedup_report": asdict(result.dedup_report),
                "failures": [list(f) for f in result.failures],
                "elapsed_seconds": result.elapsed_seconds,
                "scans_transcribed": result.scans_transcribed,
                "scans_skipped": result.scans_skipped,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    return result


if __name__ == "__main__":  # pragma: no cover - operator entry point
    print(ingest().summary())
