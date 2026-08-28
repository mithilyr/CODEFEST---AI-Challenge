"""Canonical document identity - the foundation of the evidence model.

WHY THIS RUNS BEFORE ANYTHING COUNTS EVIDENCE
---------------------------------------------
Conflict resolution ranks competing claims by source authority. If one document
is counted as several, a single unreliable source can appear to be several
independent sources corroborating each other. So identity has to be settled
before any evidence counting, conflict detection, or confidence calculation.

WHAT WE MEASURED (and what it overturned)
-----------------------------------------
The obvious rule - "same filename stem means same document" - is wrong for this
corpus, and wrong in the dangerous direction: it deletes real evidence. Measured
text similarity between same-stem files:

    chronicles/  .docx vs .pdf   similarity 1.000  (identical length)   -> duplicates
    codex/       .docx vs .pdf   similarity 0.989-0.991                 -> duplicates
    ephemera/    .docx vs .pdf   similarity 0.019
    ephemera/    .txt  vs .pdf   similarity 0.048                       -> NOT duplicates
    images/ vs codex/images/     byte-identical SHA-256                 -> duplicates

The ephemera pairs are different in-world documents that happen to concern the
same subject. For example, both of these exist:

    auction_catalogue_concerning_morwenna_vosgard.pdf
        "Catalogue of Perilous Holdings: A Sale of Sapper's Work..."
    auction_catalogue_concerning_morwenna_vosgard.txt
        "Catalogue of the Unseen Sapper: Morwenna Vosgard"

Deduplicating those would silently discard an independent source. The policy is
therefore collection-dependent rather than global.

CANONICAL TEXT VERSUS DISPLAY
-----------------------------
Deduplication picks one variant as the text source. It does not throw the others
away: the UI must still be able to show a judge the original scanned page or
figure plate. Every canonical document keeps its display variants for that
purpose. See ResponseContract.evidence[].display_asset.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from src.ingest.metadata import SourceMetadata

#: Collections whose same-stem files are genuinely the same work in two formats.
#: Verified by text-similarity measurement; see the module docstring.
DEDUPLICATED_COLLECTIONS = frozenset({"chronicles", "codex"})

#: Format preference when several variants describe one work, best first.
#: .docx outranks .pdf because Word tables survive extraction as structured rows
#: while the PDF renderer flattens them - and in the Annals and Codex Vaeloria,
#: those tables are precisely where the relations live.
FORMAT_PREFERENCE = (".md", ".txt", ".docx", ".pdf")


def _format_rank(path: Path) -> int:
    """Rank a variant by extraction quality; lower is better."""
    # A scanned PDF has no text layer at all, so it always loses to any digital
    # variant regardless of extension ordering.
    if ".scan." in path.name.lower():
        return len(FORMAT_PREFERENCE) + 1
    try:
        return FORMAT_PREFERENCE.index(path.suffix.lower())
    except ValueError:
        return len(FORMAT_PREFERENCE)


@dataclass(frozen=True)
class CanonicalDocument:
    """One logical document, with its identity and all its physical files."""

    #: Stable identity, e.g. "ephemera/sermon_concerning_malchior_cindervale.txt".
    #: Includes the extension where a collection is not deduplicated, because
    #: there the extension is part of what distinguishes one document from another.
    canonical_id: str
    collection: str
    #: Variant supplying retrieval text. None when the only variants are scans
    #: awaiting OCR.
    text_source: Path | None
    #: Every physical file mapping to this document.
    format_variants: tuple[Path, ...]
    #: Files to render in the UI - scans and plates. May overlap format_variants.
    display_variants: tuple[Path, ...]
    #: True when text must come from OCR because no digital variant exists.
    needs_ocr: bool
    doctype: str | None = None
    subject_slug: str | None = None
    #: Source authority, assigned in src/ingest/authority.py.
    tier: int | None = None
    subtier: int | None = None

    @property
    def label(self) -> str:
        """Short human-readable name for citations."""
        return Path(self.canonical_id).name


@dataclass
class DedupReport:
    """Audit trail for the deduplication pass, surfaced in the coverage report."""

    total_files: int = 0
    canonical_documents: int = 0
    duplicates_collapsed: int = 0
    needs_ocr: int = 0
    per_collection: dict[str, int] = field(default_factory=dict)
    #: canonical_id -> variants that were collapsed into it.
    collapsed: dict[str, list[str]] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"files scanned        : {self.total_files}",
            f"canonical documents  : {self.canonical_documents}",
            f"duplicates collapsed : {self.duplicates_collapsed}",
            f"awaiting OCR         : {self.needs_ocr}",
            "per collection:",
        ]
        lines += [
            f"    {name:<12} {count}" for name, count in sorted(self.per_collection.items())
        ]
        return "\n".join(lines)


def _content_hash(path: Path) -> str:
    """SHA-256 of file bytes, used to collapse identical image assets."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def _grouping_key(meta: SourceMetadata) -> tuple:
    """Identity key deciding which files collapse into one document.

    Three rules, each backed by a measurement in the module docstring:

    1. Image assets group by content hash. The 15 figure plates are duplicated
       byte-for-byte between images/ and codex/images/.
    2. chronicles/ and codex/ group by stem, collapsing .docx and .pdf renderings
       of the same work.
    3. Everything else - notably all of ephemera/ - keeps one document per file,
       because same-stem files there are genuinely different documents.
    """
    if meta.asset_kind in {"plate", "atmo_image"}:
        return ("asset", _content_hash(meta.path))
    if meta.collection in DEDUPLICATED_COLLECTIONS:
        return ("work", meta.collection, meta.stem)
    return ("file", meta.collection, meta.path.name)


def build_canonical_documents(
    files: list[SourceMetadata],
) -> tuple[list[CanonicalDocument], DedupReport]:
    """Collapse physical files into canonical documents.

    Args:
        files: Output of :func:`src.ingest.metadata.discover`.

    Returns:
        The canonical documents sorted by id for reproducibility, and a
        :class:`DedupReport` recording exactly what was collapsed. The report is
        the audit trail - "we deduplicated" is not a claim we want to make
        without being able to show precisely what merged into what.
    """
    groups: dict[tuple, list[SourceMetadata]] = defaultdict(list)
    for meta in files:
        # Corpus-root files (README.txt) document the archive; they are not
        # evidence about the world, so they stay out of the document set.
        if meta.collection == "root":
            continue
        groups[_grouping_key(meta)].append(meta)

    documents: list[CanonicalDocument] = []
    report = DedupReport(total_files=len(files))

    for key, members in groups.items():
        members = sorted(members, key=lambda m: (_format_rank(m.path), str(m.path)))
        primary = members[0]

        digital = [m for m in members if not m.is_scan and m.is_document]
        scans = [m for m in members if m.is_scan]
        images = [m for m in members if not m.is_document]

        text_source = digital[0].path if digital else None
        needs_ocr = text_source is None and bool(scans)

        # A scan is always worth showing even when a digital twin supplies the
        # text - it is the original document a judge will want to see.
        display = [m.path for m in scans] + [m.path for m in images]

        canonical_id = (
            f"{primary.collection}/{primary.stem}"
            if key[0] in {"work", "asset"}
            else f"{primary.collection}/{primary.path.name}"
        )

        documents.append(
            CanonicalDocument(
                canonical_id=canonical_id,
                collection=primary.collection,
                text_source=text_source,
                format_variants=tuple(m.path for m in members),
                display_variants=tuple(display),
                needs_ocr=needs_ocr,
                doctype=primary.doctype,
                subject_slug=primary.subject_slug,
            )
        )

        if len(members) > 1:
            report.duplicates_collapsed += len(members) - 1
            report.collapsed[canonical_id] = [m.path.name for m in members]

    documents.sort(key=lambda d: d.canonical_id)
    report.canonical_documents = len(documents)
    report.needs_ocr = sum(d.needs_ocr for d in documents)
    for document in documents:
        report.per_collection[document.collection] = (
            report.per_collection.get(document.collection, 0) + 1
        )

    return documents, report
