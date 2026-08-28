"""Tests for the ingestion layer.

These are mostly regression tests for corpus facts we measured rather than
assumed. Several encode findings that overturned an earlier design - notably
that ephemera files sharing a filename stem are *different documents*, which is
why deduplication is collection-dependent. If a future change breaks that, the
system would start silently discarding evidence, and these tests are what
catches it.

Tests needing the corpus skip cleanly when it is absent, so `pytest` still passes
on a fresh clone before the archive has been downloaded.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ingest.authority import assign_authority, load_authority_model
from src.ingest.dedup import build_canonical_documents
from src.ingest.loaders import load
from src.ingest.metadata import (
    EPHEMERA_DOCTYPES,
    discover,
    slugify,
    strip_extensions,
)
from src.settings import get_settings


@pytest.fixture(scope="module")
def corpus_root() -> Path:
    """Path to the corpus, or skip the test if it has not been downloaded."""
    settings = get_settings()
    if not settings.corpus_path.is_dir():
        pytest.skip(f"Corpus not present at {settings.corpus_path}; see README.md")
    return settings.corpus_path


@pytest.fixture(scope="module")
def documents(corpus_root: Path):
    """Canonical documents with authority ranks assigned."""
    files = discover(corpus_root)
    docs, report = build_canonical_documents(files)
    return assign_authority(docs), report


# --------------------------------------------------------------------------
# Filename metadata - no corpus required
# --------------------------------------------------------------------------


def test_slugify_normalises_punctuation_and_case():
    assert slugify("The Thrice-Bound Edge") == "the_thrice_bound_edge"
    assert slugify("the thrice bound edge") == "the_thrice_bound_edge"
    assert slugify("  The  Thrice_Bound  Edge ") == "the_thrice_bound_edge"


def test_strip_extensions_handles_scan_double_extension():
    assert (
        strip_extensions("ballad_concerning_crookgate_keep.scan.pdf")
        == "ballad_concerning_crookgate_keep"
    )
    assert strip_extensions("aldous_wrenfield.md") == "aldous_wrenfield"


def test_all_twelve_ephemera_doctypes_are_declared():
    """The authority config must rank every doctype the corpus actually uses."""
    model = load_authority_model()
    missing = EPHEMERA_DOCTYPES - set(model.ephemera_subtiers)
    assert not missing, f"doctypes with no authority subtier: {sorted(missing)}"


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------


def test_every_ephemera_file_yields_a_doctype(corpus_root: Path):
    """The <doctype>_concerning_<subject> convention holds for all 145 files.

    The authority sub-ranking depends on this. A file that parses to no doctype
    would silently fall back to the default subtier.
    """
    files = discover(corpus_root)
    ephemera = [f for f in files if f.collection == "ephemera"]
    assert len(ephemera) == 145
    assert all(f.doctype in EPHEMERA_DOCTYPES for f in ephemera)


def test_scans_are_detected(corpus_root: Path):
    """17 ephemera are image-only PDFs requiring OCR."""
    files = discover(corpus_root)
    assert sum(f.is_scan for f in files) == 17


def test_image_assets_carry_entity_category(corpus_root: Path):
    """Plate and atmo filenames encode the entity they depict."""
    files = discover(corpus_root)
    images = [f for f in files if f.asset_kind in {"plate", "atmo_image"}]
    assert len(images) == 85  # 15 plates x2 locations + 55 wiki art
    assert all(f.subject_slug for f in images)


# --------------------------------------------------------------------------
# Deduplication - the evidence-model invariants
# --------------------------------------------------------------------------


def test_novels_and_codexes_collapse_across_formats(documents):
    """chronicles/ and codex/ ship the same work as .docx and .pdf.

    Measured text similarity: 1.000 for the novels, 0.989-0.991 for the codexes.
    """
    docs, _ = documents
    assert len([d for d in docs if d.collection == "chronicles"]) == 4
    codex_works = [d for d in docs if d.collection == "codex" and d.text_source]
    assert len(codex_works) == 3


def test_docx_is_preferred_over_pdf_for_deduplicated_works(documents):
    """DOCX wins because Word tables survive extraction as structured rows.

    The Annals and Codex Vaeloria keep their relations in tables; the PDF
    renderer flattens those to prose and loses the field/value structure.
    """
    docs, _ = documents
    for document in docs:
        if document.collection in {"chronicles", "codex"} and document.text_source:
            assert document.text_source.suffix == ".docx", document.canonical_id


def test_ephemera_are_never_deduplicated_by_stem(documents):
    """Same-stem ephemera are different documents, so all 145 survive.

    Measured similarity between same-stem ephemera pairs was 0.019-0.048. For
    example both of these exist and are unrelated in content:
        auction_catalogue_concerning_morwenna_vosgard.pdf
        auction_catalogue_concerning_morwenna_vosgard.txt
    Collapsing them would discard an independent source, which would in turn
    corrupt conflict resolution by hiding a competing claim.
    """
    docs, _ = documents
    assert len([d for d in docs if d.collection == "ephemera"]) == 145


def test_identical_plates_collapse_across_directories(documents):
    """The 15 figure plates are byte-identical in images/ and codex/images/."""
    docs, report = documents
    plates = [d for d in docs if "plate_" in d.canonical_id]
    assert len(plates) == 15
    assert all(len(d.format_variants) == 2 for d in plates)


def test_scans_keep_a_display_variant(documents):
    """A scan must remain renderable even though it supplies no text yet.

    The UI has to be able to show a judge the original page.
    """
    docs, _ = documents
    scans = [d for d in docs if d.needs_ocr]
    assert len(scans) == 17
    assert all(d.display_variants for d in scans)


# --------------------------------------------------------------------------
# Source authority
# --------------------------------------------------------------------------


def test_authority_ordering_defeats_the_sorrowfell_decoy(documents):
    """The planted trap: a sermon confidently states the wrong forging year.

    ephemera sermon says 360 AS; Codex Vaeloria II says 391 AS and explicitly
    rejects "popular accounts". Ranking must put the codex first and the sermon
    last, or the system answers 360 AS like a naive retriever would.
    """
    docs, _ = documents
    by_id = {d.canonical_id: d for d in docs}

    codex = by_id["codex/codex_vaeloria_ii_armory_of_relics_and_bestiary"]
    wiki = by_id["wiki/gauntlet_of_sorrowfell.md"]
    sermon = by_id[
        "ephemera/sermon_concerning_malchior_cindervale_the_flame_touched.txt"
    ]

    rank = lambda d: (d.tier, d.subtier)  # noqa: E731 - local readability
    assert rank(codex) < rank(wiki) < rank(sermon)


def test_administrative_ephemera_outrank_performative_ephemera():
    """Within ephemera, a ledger should beat a ballad."""
    model = load_authority_model()
    assert model.rank("ephemera", "quartermaster_ledger") < model.rank(
        "ephemera", "ballad"
    )
    assert model.rank("ephemera", "decree") < model.rank("ephemera", "sermon")


def test_unknown_collection_is_least_authoritative():
    """An unrecognised source must never be trusted by default."""
    model = load_authority_model()
    assert model.rank("something_new", None) > model.rank("ephemera", "ballad")


# --------------------------------------------------------------------------
# Loaders
# --------------------------------------------------------------------------


def test_scanned_pdf_yields_no_text(corpus_root: Path):
    """Scans have no text layer, which is how OCR routing is triggered."""
    scan = corpus_root / "ephemera" / "ballad_concerning_crookgate_keep.scan.pdf"
    assert load(scan) == []


def test_docx_tables_are_read_as_rows(corpus_root: Path):
    """Registry relations live in tables; losing them would gut the graph."""
    blocks = load(corpus_root / "codex" / "the_annals_of_the_ashen_era.docx")
    rows = [b for b in blocks if b.kind == "table_row"]
    assert len(rows) > 400
    assert any("Aldous Wrenfield" in b.text for b in rows)


def test_typographic_punctuation_is_normalised(corpus_root: Path):
    """U+2019 apostrophes would break plain-ASCII matching downstream."""
    blocks = load(
        corpus_root / "codex" / "codex_vaeloria_ii_armory_of_relics_and_bestiary.docx"
    )
    assert not any(ord(ch) > 127 for b in blocks for ch in b.text)
    assert any("Gauntlet of Sorrowfell's forged is 391 AS" in b.text for b in blocks)


def test_locators_are_present_and_human_readable(corpus_root: Path):
    """Every block must be citable; an uncitable block is unusable as evidence."""
    blocks = load(corpus_root / "wiki" / "gauntlet_of_sorrowfell.md")
    assert blocks
    assert all(b.locator.strip() for b in blocks)
