"""Tests for the free-tier quota machinery.

These cover the two provider limits that shaped the architecture, both of which
we discovered by hitting them rather than by reading docs:

  Gemini  ~20 requests per DAY per model. Backoff cannot recover from a daily
          cap, so it must be detected and the caller must switch models.
  Voyage  3 requests and 10,000 tokens per MINUTE without a payment method, so
          batches must be sized by token count and paced.

No network is touched. Clocks and sleeps are injected so a throttle that would
wait two minutes in production resolves instantly here.
"""

from __future__ import annotations

import pytest

from src.clients.embeddings import (
    BATCH_SIZE,
    FREE_TIER_TPM,
    TPM_SAFETY,
    _estimate_tokens,
    _make_batches,
    _RateLimiter,
)
from src.clients.retry import (
    DailyQuotaExhausted,
    is_daily_quota_error,
    retry_after_seconds,
    with_retry,
)

#: A real Gemini free-tier rejection, trimmed. Kept verbatim because our
#: detection matches on provider text, and a reworded error would silently stop
#: being classified.
GEMINI_DAILY_QUOTA_ERROR = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded "
    "your current quota... Quota exceeded for metric: "
    "generativelanguage.googleapis.com/generate_content_free_tier_requests, "
    "limit: 20, model: gemini-3.7-flash. Please retry in 27.528568123s.', "
    "'status': 'RESOURCE_EXHAUSTED', 'details': [{'quotaId': "
    "'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaValue': '20'}]}}"
)


# --------------------------------------------------------------------------
# Daily quota detection
# --------------------------------------------------------------------------


def test_daily_quota_is_distinguished_from_an_ordinary_rate_limit():
    """The remedies differ: wait a moment, versus switch model or wait a day."""
    assert is_daily_quota_error(RuntimeError(GEMINI_DAILY_QUOTA_ERROR))
    assert not is_daily_quota_error(RuntimeError("429 Too Many Requests"))


def test_daily_quota_fails_immediately_without_burning_attempts():
    """Our first OCR run wasted 5 attempts each on 13 files waiting on a daily cap."""
    calls = {"n": 0}

    def exhausted() -> None:
        calls["n"] += 1
        raise RuntimeError(GEMINI_DAILY_QUOTA_ERROR)

    slept: list[float] = []
    with pytest.raises(DailyQuotaExhausted):
        with_retry(exhausted, attempts=5, sleep=slept.append)

    assert calls["n"] == 1, "daily quota must not be retried"
    assert slept == [], "must not sleep on a limit that resets tomorrow"


def test_providers_retry_hint_is_preferred_over_our_guess():
    """Google returns a concrete RetryInfo; honouring it beats guessing."""
    assert retry_after_seconds(RuntimeError("Please retry in 27.52s.")) == 27.52
    assert retry_after_seconds(RuntimeError("'retryDelay': '38s'")) == 38.0
    assert retry_after_seconds(RuntimeError("no hint here")) is None


def test_transient_rate_limit_uses_the_hinted_delay():
    attempts = {"n": 0}

    def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("429 rate limit. Please retry in 5s.")
        return "ok"

    slept: list[float] = []
    assert with_retry(flaky, sleep=slept.append) == "ok"
    # 5s hint honoured rather than the 1s exponential default.
    assert 5.0 <= slept[0] < 6.0


# --------------------------------------------------------------------------
# Token-aware batching
# --------------------------------------------------------------------------


def test_batches_stay_within_one_minute_of_tokens():
    """A 128-item batch was ~36k tokens - over triple the per-minute cap."""
    budget = FREE_TIER_TPM * TPM_SAFETY
    pending = [(i, "x" * 3000) for i in range(40)]

    for batch in _make_batches(pending, FREE_TIER_TPM):
        tokens = sum(_estimate_tokens(text) for _, text in batch)
        assert tokens <= budget, f"batch of {len(batch)} is {tokens} tokens"


def test_batches_respect_the_item_cap_when_tokens_allow():
    """Short texts should still not exceed Voyage's 128-input limit."""
    pending = [(i, "short") for i in range(500)]
    batches = _make_batches(pending, tpm=10**9)
    assert all(len(b) <= BATCH_SIZE for b in batches)
    assert sum(len(b) for b in batches) == 500


def test_every_pending_item_appears_exactly_once():
    """Losing a chunk here would silently leave a hole in the index."""
    pending = [(i, "x" * (100 * (i % 7 + 1))) for i in range(200)]
    batched = [item for batch in _make_batches(pending, FREE_TIER_TPM) for item in batch]
    assert [i for i, _ in batched] == list(range(200))


# --------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------


def _fake_clock():
    """A controllable clock and a sleep that advances it."""
    state = {"t": 0.0}
    waits: list[float] = []

    def sleep(seconds: float) -> None:
        waits.append(seconds)
        state["t"] += seconds

    return (lambda: state["t"]), sleep, waits, state


def test_requests_below_the_limit_do_not_wait():
    clock, sleep, waits, _ = _fake_clock()
    limiter = _RateLimiter(rpm=3, tpm=10_000, clock=clock)

    limiter.acquire(1000, sleep=sleep)
    limiter.acquire(1000, sleep=sleep)

    assert waits == []


def test_request_limit_forces_a_wait():
    clock, sleep, waits, _ = _fake_clock()
    limiter = _RateLimiter(rpm=3, tpm=10_000_000, clock=clock)

    for _ in range(4):
        limiter.acquire(1, sleep=sleep)

    assert len(waits) == 1, "4th request in a minute must wait"


def test_token_limit_forces_a_wait_before_the_request_limit_does():
    """TPM binds first for our corpus: 8k budget means 3 x 3000 already exceeds it."""
    clock, sleep, waits, state = _fake_clock()
    limiter = _RateLimiter(rpm=100, tpm=10_000, clock=clock)

    for _ in range(5):
        limiter.acquire(3000, sleep=sleep)

    assert waits, "token budget must throttle even when request count is fine"
    assert state["t"] > 0


def test_window_rolls_forward_so_throttling_is_not_permanent():
    clock, sleep, waits, state = _fake_clock()
    limiter = _RateLimiter(rpm=3, tpm=10_000, clock=clock)

    for _ in range(3):
        limiter.acquire(1, sleep=sleep)
    assert waits == []

    # Advance past the window; the next call should pass without waiting.
    state["t"] += 61.0
    limiter.acquire(1, sleep=sleep)
    assert waits == []
