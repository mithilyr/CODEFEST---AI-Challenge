"""Voyage AI embeddings with an on-disk cache.

WHY VOYAGE FOR BOTH BASELINE AND FALLBACK
-----------------------------------------
The baseline exists to answer one question: does the knowledge graph actually
beat the obvious approach? That comparison is only honest if the baseline is
given good embeddings. If we handicapped it with a weaker local model, a judge
could reasonably say we beat a strawman. Same embeddings on both sides means any
difference we measure comes from the retrieval strategy, which is the thing under
test.

CACHING
-------
Embeddings are cached to .cache/embeddings/ keyed by (model, text hash). Three
reasons: the free allowance is finite, re-running the evaluation must not cost
anything, and a demo recorded against a warm cache cannot fail on a rate limit.

Cache entries are content-addressed, so editing one document re-embeds only that
document's chunks rather than the whole corpus.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from src.clients.retry import with_retry
from src.settings import get_settings

#: voyage-4-lite: 1024 dimensions, cheapest of the 4-series, and the whole
#: 4-series shares a vector space - so documents embedded with a larger model
#: and queries embedded with this one remain comparable without re-indexing.
EMBEDDING_MODEL = "voyage-4-lite"
EMBEDDING_DIMENSIONS = 1024

#: Voyage accepts up to 128 inputs per request. Batching is what keeps thousands
#: of chunks to a few dozen requests instead of thousands.
BATCH_SIZE = 128

#: Free-tier limits for an account with no payment method on file: 3 requests
#: per minute and 10,000 tokens per minute. Adding a card lifts these without
#: costing anything - the 200M free tokens still apply, the card is only
#: identity verification (see the challenge appendix, section 9.1).
#:
#: We throttle to these limits rather than assuming the card is present, so the
#: system works for any team member on a fresh account. Set VOYAGE_TIER=paid in
#: .env once a card is added to remove the throttle.
FREE_TIER_RPM = 3
FREE_TIER_TPM = 10_000

#: Characters per token, used to size batches before sending. Deliberately
#: conservative: overestimating tokens costs a little throughput, while
#: underestimating costs a rejected request and a wasted minute.
CHARS_PER_TOKEN = 3.5

#: Headroom below the stated TPM, since our token estimate is approximate.
TPM_SAFETY = 0.8


class EmbeddingsUnavailableError(RuntimeError):
    """Raised when embeddings are needed but no key and no cache exist."""


@dataclass
class EmbeddingStats:
    """What a run actually cost, reported so cost stays visible."""

    requested: int = 0
    served_from_cache: int = 0
    embedded: int = 0
    api_calls: int = 0
    tokens: int = 0

    def summary(self) -> str:
        return (
            f"requested {self.requested} | cached {self.served_from_cache} | "
            f"embedded {self.embedded} | calls {self.api_calls} | "
            f"tokens {self.tokens}"
        )


class _RateLimiter:
    """Token- and request-per-minute throttle over a rolling window.

    Free-tier limits are enforced per minute, so we keep the last sixty seconds
    of events and wait only as long as the oldest relevant one requires.

    The clock is injectable so the throttle can be tested without real waiting -
    a fake sleep that does not advance time would otherwise spin forever, which
    is exactly what happened the first time this was written.
    """

    def __init__(self, rpm: int, tpm: int, *, clock=time.monotonic) -> None:
        self.rpm = rpm
        self.tpm = tpm
        self._clock = clock
        self._events: list[tuple[float, int]] = []  # (timestamp, tokens)

    def acquire(self, tokens: int, *, sleep=time.sleep) -> float:
        """Block until sending `tokens` would breach neither limit.

        Returns the total time waited, which callers can report.
        """
        waited = 0.0

        while True:
            now = self._clock()
            self._events = [(t, n) for t, n in self._events if now - t < 60.0]

            spent = sum(n for _, n in self._events)
            over_requests = len(self._events) >= self.rpm
            over_tokens = bool(self._events) and spent + tokens > self.tpm * TPM_SAFETY

            if not (over_requests or over_tokens):
                self._events.append((now, tokens))
                return waited

            delay = max(0.1, 60.0 - (now - min(t for t, _ in self._events)))
            sleep(delay)
            waited += delay


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / CHARS_PER_TOKEN))


def _make_batches(pending: list[tuple[int, str]], tpm: int) -> list[list[tuple[int, str]]]:
    """Split pending texts into batches that fit inside one minute's tokens."""
    budget = int(tpm * TPM_SAFETY)
    batches: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    current_tokens = 0

    for item in pending:
        tokens = _estimate_tokens(item[1])
        too_many = len(current) >= BATCH_SIZE
        too_big = current and current_tokens + tokens > budget
        if too_many or too_big:
            batches.append(current)
            current, current_tokens = [], 0
        current.append(item)
        current_tokens += tokens

    if current:
        batches.append(current)
    return batches


def _cache_dir() -> Path:
    return get_settings().cache_dir / "embeddings" / EMBEDDING_MODEL


def _key(text: str) -> str:
    """Content address for one text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _shard_path(key: str) -> Path:
    """Group entries into 256 shards so no directory holds 30k files."""
    return _cache_dir() / key[:2] / f"{key}.json"


def _read_cached(text: str) -> list[float] | None:
    path = _shard_path(_key(text))
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A truncated cache entry should be re-fetched, not crash the run.
        return None


def _write_cached(text: str, vector: list[float]) -> None:
    path = _shard_path(_key(text))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(vector), encoding="utf-8")


def embed(
    texts: list[str],
    *,
    input_type: str = "document",
    stats: EmbeddingStats | None = None,
    progress: bool = False,
) -> list[list[float]]:
    """Embed texts, serving from cache where possible.

    Args:
        texts: Texts to embed. Order is preserved in the result.
        input_type: "document" when indexing, "query" when searching. Voyage
            embeds the two asymmetrically, and using the wrong one measurably
            degrades retrieval.
        stats: Optional accumulator so callers can report cost.
        progress: Print batch progress for long indexing runs.

    Returns:
        One vector per input text, in the same order.

    Raises:
        EmbeddingsUnavailableError: If any text is uncached and no key is set.
    """
    stats = stats or EmbeddingStats()
    stats.requested += len(texts)

    vectors: list[list[float] | None] = []
    pending: list[tuple[int, str]] = []

    for index, text in enumerate(texts):
        cached = _read_cached(text)
        if cached is None:
            vectors.append(None)
            pending.append((index, text))
        else:
            vectors.append(cached)
            stats.served_from_cache += 1

    if not pending:
        return [v for v in vectors if v is not None]

    api_key = get_settings().voyage_api_key
    if not api_key:
        raise EmbeddingsUnavailableError(
            f"{len(pending)} text(s) are not in the embedding cache and "
            "VOYAGE_API_KEY is not set.\n"
            "Set VOYAGE_API_KEY in .env (200M free tokens from "
            "https://dashboard.voyageai.com), or run against the prebuilt index."
        )

    import voyageai

    client = voyageai.Client(api_key=api_key)

    # An account with a payment method on file is not rate-limited the way a
    # fresh one is. VOYAGE_TIER=paid skips the throttle entirely.
    throttled = os.getenv("VOYAGE_TIER", "free").strip().lower() != "paid"
    limiter = _RateLimiter(FREE_TIER_RPM, FREE_TIER_TPM) if throttled else None

    batches = _make_batches(pending, FREE_TIER_TPM if throttled else 10**9)

    if progress:
        mode = "free tier (throttled)" if throttled else "paid tier"
        print(f"  {len(pending)} to embed in {len(batches)} batch(es), {mode}")

    for batch_number, batch in enumerate(batches, start=1):
        payload = [text for _, text in batch]
        if limiter:
            limiter.acquire(sum(_estimate_tokens(t) for t in payload))

        def call():
            return client.embed(payload, model=EMBEDDING_MODEL, input_type=input_type)

        response = with_retry(call, description=f"Voyage embed ({EMBEDDING_MODEL})")
        stats.api_calls += 1
        stats.tokens += getattr(response, "total_tokens", 0)
        stats.embedded += len(batch)

        for (index, text), vector in zip(batch, response.embeddings):
            vectors[index] = vector
            _write_cached(text, vector)

        if progress:
            print(
                f"  batch {batch_number}/{len(batches)} "
                f"({stats.embedded}/{len(pending)} embedded, "
                f"{stats.tokens} tokens)",
                flush=True,
            )

    missing = [i for i, v in enumerate(vectors) if v is None]
    if missing:  # pragma: no cover - provider contract violation
        raise RuntimeError(f"Provider returned no vector for indices {missing[:5]}")

    return [v for v in vectors if v is not None]


def embed_query(text: str) -> list[float]:
    """Embed a single search query.

    Separate from :func:`embed` only to make the input_type impossible to get
    wrong at call sites.
    """
    return embed([text], input_type="query")[0]
