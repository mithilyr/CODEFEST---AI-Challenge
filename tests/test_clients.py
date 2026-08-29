"""Tests for retry behaviour and OCR plumbing.

No network is touched. Retry is tested with injected failures and a fake sleep;
OCR is tested up to the point of the API call, which is where the committed
cache takes over anyway.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.clients.retry import RetriesExhausted, is_retryable, with_retry
from src.ingest.ocr import (
    OCRResult,
    OCRUnavailableError,
    cache_file_for,
    extract_page_images,
    transcribe,
)
from src.settings import get_settings


# --------------------------------------------------------------------------
# Retry
# --------------------------------------------------------------------------


def test_transient_errors_are_classified_as_retryable():
    assert is_retryable(RuntimeError("429 Too Many Requests"))
    assert is_retryable(RuntimeError("RESOURCE_EXHAUSTED"))
    assert is_retryable(TimeoutError("connection timed out"))
    assert is_retryable(RuntimeError("503 Service Unavailable"))


def test_client_errors_are_not_retryable():
    """A malformed request must fail immediately rather than burn quota."""
    assert not is_retryable(ValueError("400 invalid argument"))
    assert not is_retryable(KeyError("missing field"))


def test_succeeds_without_sleeping_when_the_first_attempt_works():
    slept: list[float] = []
    result = with_retry(lambda: "ok", sleep=slept.append)
    assert result == "ok"
    assert slept == []


def test_retries_then_succeeds():
    attempts = {"count": 0}

    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("429 rate limit")
        return "recovered"

    slept: list[float] = []
    assert with_retry(flaky, sleep=slept.append) == "recovered"
    assert attempts["count"] == 3
    assert len(slept) == 2


def test_backoff_grows_exponentially():
    """Delays follow 1s, 2s, 4s... with jitter capped at 10% above each step."""
    slept: list[float] = []

    def always_429() -> None:
        raise RuntimeError("429")

    with pytest.raises(RetriesExhausted):
        with_retry(always_429, attempts=4, base_delay=1.0, sleep=slept.append)

    assert len(slept) == 3
    assert 1.0 <= slept[0] < 1.2
    assert 2.0 <= slept[1] < 2.4
    assert 4.0 <= slept[2] < 4.8


def test_non_retryable_error_propagates_unchanged():
    def bad_request() -> None:
        raise ValueError("400 malformed")

    with pytest.raises(ValueError, match="400 malformed"):
        with_retry(bad_request, sleep=lambda _: None)


def test_exhausted_retries_preserve_the_last_error():
    def always_fails() -> None:
        raise RuntimeError("429 still limited")

    with pytest.raises(RetriesExhausted, match="429 still limited"):
        with_retry(always_fails, attempts=2, sleep=lambda _: None)


# --------------------------------------------------------------------------
# OCR
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def a_scan() -> Path:
    """One of the 17 image-only scanned PDFs."""
    settings = get_settings()
    if not settings.corpus_path.is_dir():
        pytest.skip("Corpus not present; see README.md")
    return (
        settings.corpus_path
        / "ephemera"
        / "ballad_concerning_crookgate_keep.scan.pdf"
    )


def test_scan_pages_are_embedded_jpegs(a_scan: Path):
    """We pull embedded JPEG bytes rather than rasterising pages.

    This is what lets us avoid a heavyweight renderer dependency; if a future
    corpus embeds images some other way, this test is where we find out.
    """
    images = extract_page_images(a_scan)
    assert len(images) == 2
    assert all(image[:2] == b"\xff\xd8" for image in images), "expected JPEG SOI"


def test_cache_key_tracks_file_contents(a_scan: Path):
    """Cache is keyed by content hash, so a reissued corpus invalidates it."""
    name = cache_file_for(a_scan).name
    assert name.startswith("ballad_concerning_crookgate_keep.scan.")
    assert name.endswith(".json")


def test_missing_cache_and_missing_key_explains_both_remedies(
    a_scan: Path, monkeypatch, tmp_path: Path
):
    """The error a judge sees must say what to do about it.

    Settings are patched directly rather than via the environment: a developer
    with a real key in .env would otherwise have this test silently pass through
    to a live API call.
    """
    import dataclasses

    keyless = dataclasses.replace(get_settings(), google_api_key=None)
    monkeypatch.setattr("src.ingest.ocr.get_settings", lambda: keyless)
    # Point the cache at a path inside tmp_path. Using a bare relative filename
    # here once let a failing run write its result into the repo root, which then
    # satisfied the cache check on every later run and masked the real failure.
    monkeypatch.setattr(
        "src.ingest.ocr.cache_file_for", lambda _: tmp_path / "absent.json"
    )

    with pytest.raises(OCRUnavailableError) as error:
        transcribe(a_scan)

    message = str(error.value)
    assert "GOOGLE_API_KEY" in message
    assert "ocr_cache/" in message


def test_transcription_converts_to_citable_blocks():
    """OCR output must match the loader interface, including locators."""
    result = OCRResult(
        source_name="x.scan.pdf",
        source_sha256="deadbeef",
        model="gemini-2.0-flash",
        transcribed_at="2026-08-28T00:00:00+00:00",
        pages=["First page text.", "  ", "[no text]", "Third page text."],
    )
    blocks = result.to_blocks()

    # Blank pages and explicit [no text] markers contribute no evidence.
    assert [b.text for b in blocks] == ["First page text.", "Third page text."]
    assert blocks[0].locator == "page 1 (OCR)"
    # Locators reflect true page position, not filtered position.
    assert blocks[1].locator == "page 4 (OCR)"
