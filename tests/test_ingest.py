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

from collections import Counter
from pathlib import Path

import pytest

from eval.probes.corpus_shape import infobox_rows
from src.ingest.authority import assign_authority, load_authority_model
from src.ingest.dedup import build_canonical_documents
from src.ingest.integrity import (
    manifest_from_dir,
    read_manifest,
    verify,
    write_manifest,
)
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


# --- corpus integrity (F-016) -------------------------------------------------
#
# These reconstruct the 2026-08-29 incident: a text editor rewrote 36 corpus
# files CRLF->LF and left an empty note behind. The rewrites changed no content,
# so every evidence count stayed identical and nothing looked wrong. The note
# ingested as a canonical document under the title of a contested entity.
#
# What makes these regression tests rather than happy-path tests is that each
# one asserts the check fires on the *specific* shape of that failure.


@pytest.fixture
def mini_corpus(tmp_path: Path) -> Path:
    """A synthetic corpus obeying the archive's filename conventions."""
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "ederon_fellgard.md").write_bytes(b"# Ederon\r\nrow\r\n")
    (tmp_path / "ephemera").mkdir()
    (tmp_path / "ephemera" / "ballad_concerning_crookgate_keep.txt").write_bytes(
        b"a ballad\n"
    )
    return tmp_path


def test_manifest_round_trips(tmp_path: Path, mini_corpus: Path):
    """A written manifest must read back exactly, or verification is theatre."""
    entries = manifest_from_dir(mini_corpus)
    path = tmp_path / "m.sha256"
    write_manifest(entries, path, "test")
    assert read_manifest(path) == entries


def test_committed_manifest_covers_the_whole_shipped_archive():
    """The manifest is the baseline; a truncated one silently verifies nothing."""
    entries = read_manifest()
    assert len(entries) == 341
    assert all(len(d) == 64 for d in entries.values())
    assert "wiki/the_iron_ring_cartel.md" in entries


def test_manifest_rejects_a_malformed_line(tmp_path: Path):
    """Fail loudly: a manifest parsed to {} would report a clean corpus."""
    path = tmp_path / "bad.sha256"
    path.write_text("# comment\nnot-a-valid-line\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_manifest(path)


def test_clean_corpus_verifies_clean(mini_corpus: Path):
    report = verify(mini_corpus, manifest_from_dir(mini_corpus))
    assert report.is_clean and report.is_safe_to_ingest
    assert report.verified == 2


def test_real_corpus_matches_the_shipped_archive(corpus_root: Path):
    """The corpus we measure against must be the corpus we were given."""
    report = verify(corpus_root)
    assert report.is_clean, report.summary()


def test_newline_only_rewrite_is_detected_as_modified(mini_corpus: Path):
    """The F-016 rewrite: identical text, different bytes.

    Content-level checks cannot see this - the evidence-unit count did not move.
    Only hashing catches it.
    """
    expected = manifest_from_dir(mini_corpus)
    target = mini_corpus / "wiki" / "ederon_fellgard.md"
    original = target.read_bytes()
    target.write_bytes(original.replace(b"\r\n", b"\n"))

    assert target.read_bytes().decode().splitlines() == original.decode().splitlines()
    report = verify(mini_corpus, expected)
    assert report.modified == ["wiki/ederon_fellgard.md"]
    assert not report.is_safe_to_ingest


def test_stray_ingested_file_is_flagged_as_unsafe(mini_corpus: Path):
    """The F-016 note itself: empty, unexpected, and read by ingestion.

    Zero bytes means zero evidence units, so it is invisible to every count the
    pipeline prints except the document total.
    """
    expected = manifest_from_dir(mini_corpus)
    (mini_corpus / "wiki" / "The Iron-Ring Cartel.md").write_bytes(b"")

    report = verify(mini_corpus, expected)
    assert report.extra_ingested == ["wiki/The Iron-Ring Cartel.md"]
    assert not report.is_clean
    assert not report.is_safe_to_ingest

    # The safety verdict above is what this test is for and it is unchanged.
    # The WORDING changed in ADR-036: an added file now reads as "corpus has
    # grown", because added and modified are different situations and used to
    # print the same accusation. A judge handing the system a document was told
    # their file was drift. `CORPUS DRIFT` is now reserved for missing or
    # modified files - the actual F-016 shape.
    summary = report.summary()
    assert "corpus has grown" in summary
    assert "CORPUS DRIFT" not in summary
    assert "not comparable with earlier checkpoints" in summary


def test_stray_ignored_file_is_drift_but_not_unsafe(mini_corpus: Path):
    """An editor's config is reported, but does not invalidate measurements."""
    expected = manifest_from_dir(mini_corpus)
    vault = mini_corpus / "wiki" / ".obsidian"
    vault.mkdir()
    (vault / "workspace.json").write_text("{}", encoding="utf-8")

    report = verify(mini_corpus, expected)
    assert report.extra_ignored == ["wiki/.obsidian/workspace.json"]
    assert report.extra_ingested == []
    assert not report.is_clean
    assert report.is_safe_to_ingest


def test_missing_file_is_reported(mini_corpus: Path):
    expected = manifest_from_dir(mini_corpus)
    (mini_corpus / "wiki" / "ederon_fellgard.md").unlink()

    report = verify(mini_corpus, expected)
    assert report.missing == ["wiki/ederon_fellgard.md"]
    assert not report.is_safe_to_ingest


# --- infobox row structure (F-017, F-018) -------------------------------------
#
# Corpus facts the graph parser has to obey, pinned before src/graph/ exists so
# the rule fails a test rather than a demo. Both were found by re-running a
# measurement a document claimed to have already made.


def _rows(corpus_root: Path, page: str) -> list[tuple[str, str]]:
    return infobox_rows((corpus_root / "wiki" / page).read_text(encoding="utf-8"))


def test_field_name_census_is_not_heading_keyed(corpus_root: Path):
    """109 field names exist; 107 is the heading-keyed subset (F-017).

    ADR-009 forbids keying on `## Infobox`, then quoted a count produced by
    doing exactly that. The two dropped fields include `Place of housing`, which
    is hop 2 of `1b_003`.
    """
    pages = [(p.name, p.read_text(encoding="utf-8"))
             for p in sorted((corpus_root / "wiki").glob("*.md"))]
    everywhere = {f for _, text in pages for f, _ in infobox_rows(text)}
    in_section = {
        f for _, text in pages if "## Infobox" in text for f, _ in infobox_rows(text)
    }

    assert len(everywhere) == 109
    assert len(in_section) == 107
    assert everywhere - in_section == {"Place of forging", "Place of housing"}


def test_repeated_field_names_are_not_collapsible_to_a_mapping(corpus_root: Path):
    """A dict-keyed parser drops 7 cells corpus-wide, silently (F-018)."""
    dropped = 0
    collisions = 0
    for page in sorted((corpus_root / "wiki").glob("*.md")):
        rows = infobox_rows(page.read_text(encoding="utf-8"))
        counts = Counter(field for field, _ in rows)
        dropped += len(rows) - len(counts)
        collisions += sum(1 for total in counts.values() if total > 1)

    assert dropped == 7, "a mapping-based parser would lose this many cells"
    assert collisions == 6, "distinct (page, field) pairs that repeat"


def test_ashen_vanguard_has_three_belligerent_rows(corpus_root: Path):
    """The worked example: three rows, one field name, no error on collapse."""
    rows = _rows(corpus_root, "the_ashen_vanguard.md")
    belligerents = [v for f, v in rows if f == "Belligerent"]

    assert belligerents == [
        "The War of Drowned Light",
        "The Accord of Mournthrone",
        "The Leaden Accord",
    ]
    assert len({f for f, _ in rows}) < len(rows)


def test_ashen_vanguard_victor_claim_is_not_on_a_victor_field(corpus_root: Path):
    """Silence is not denial, and this page is not silent (F-014, F-018).

    The Vanguard carries no `Victor of` row. Its only victor designation is an
    `Outcome` row. An extractor keyed on the field name reads the page as making
    no victor claim, which is a stance, not an absence - and the ADR-013
    CORRECTION's verdict for the Accord of Mournthrone depends on reading it.
    """
    rows = _rows(corpus_root, "the_ashen_vanguard.md")

    assert not [f for f, _ in rows if "victor" in f.lower()]
    assert ("Outcome", "Victor of The Accord of Mournthrone") in rows


def test_modified_file_still_reads_as_drift(mini_corpus: Path):
    """CORPUS DRIFT is reserved for the F-016 shape, and still fires for it.

    ADR-036 softened the message for *added* files. A file the manifest knows
    about whose bytes changed is the case F-016 actually records - an editor
    rewrote 36 files - and it must keep saying so, or the reword would have
    traded one silent failure for another.
    """
    expected = manifest_from_dir(mini_corpus)
    target = next((mini_corpus / "wiki").glob("*.md"))
    target.write_text("rewritten by something helpful\n", encoding="utf-8")

    report = verify(mini_corpus, expected)
    assert report.modified
    assert not report.is_safe_to_ingest
    assert "CORPUS DRIFT" in report.summary()
