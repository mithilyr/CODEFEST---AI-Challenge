"""Gemini client with automatic rotation across free-tier models.

THE CONSTRAINT WE MEASURED
--------------------------
The Gemini free tier allows roughly **20 requests per day, per model, per
project** - the quota Google reports is
``GenerateRequestsPerDayPerProjectPerModel-FreeTier`` with a value of 20. This is
a daily cap, not a per-minute one, which has two consequences we discovered the
expensive way:

  1. Exponential backoff cannot recover from it. Our first OCR run burned five
     retry attempts on each of thirteen documents waiting for a limit that
     resets tomorrow. ``retry.py`` now raises DailyQuotaExhausted immediately
     instead.
  2. Twenty requests is less than one evaluation run. Twenty dev questions plus
     twenty-four held-out questions is 44 synthesis calls - more than two days
     of quota on a single model.

THE FIX
-------
The quota is per *model*, so each model in the rotation carries its own separate
allowance. Working through a list of free models multiplies usable capacity by
the number of models, using nothing but each model's documented free tier.

Models are ordered strongest-first, so quality degrades gracefully only once the
better models are spent. A model that reports its daily quota exhausted is
retired for the rest of the process and the next one takes over.

RESPONSE CACHING
----------------
Text responses are cached to ``.cache/responses/`` by a content address of the
prompt. A cached answer costs no quota, which is what makes an evaluation run
re-runnable at all: the first sweep of the nine scoreable questions spends nine
requests, every sweep after that spends zero. It is also why the demo must never
be recorded against a cold cache.

The cache is keyed on the **prompt alone, not on the model**. That is
deliberate. Rotation means the same prompt may be served by different models on
different days, and keying by model would force a fresh request every time the
rotation head changed - exactly when quota is scarcest. The record stores which
model actually produced the text, so provenance survives even though the key
does not carry it.

Only all-text prompts are cached. Prompts carrying image parts (OCR) are served
by ``ocr_cache/`` instead, which is committed to the repository.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.clients.retry import DailyQuotaExhausted, RetriesExhausted, with_retry
from src.settings import get_settings

#: Free-tier models in preference order, strongest first. Each carries its own
#: separate daily quota. All support text and vision input.
MODEL_ROTATION: tuple[str, ...] = (
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
)

#: Hard ceiling on a single request, in milliseconds.
#:
#: Measured: a trivial one-word completion takes ~35s from here, so latency to
#: this API is high but bounded. The SDK's default is no timeout at all, and a
#: request that hangs blocks the whole sweep - our first evaluation run stalled
#: for 19 minutes on one question with no error and no way to interrupt it.
#: 120s is roughly 3.5x the measured latency: generous for a long-context
#: synthesis, and short enough that a hung call rotates instead of stopping work.
REQUEST_TIMEOUT_MS = 120_000

#: Attempts per model while other models remain untried.
#:
#: Backing off five times on one model is the wrong move when five other models
#: are sitting there with separate quota buckets: a per-minute limit on one model
#: says nothing about the next. Rotating is both faster and more likely to work.
#: The last available model gets the full backoff, because then there is nothing
#: else to try and waiting is the only remaining option.
ATTEMPTS_WHILE_ALTERNATIVES_REMAIN = 2
ATTEMPTS_ON_LAST_MODEL = 5


class AllModelsExhausted(RuntimeError):
    """Raised when every model in the rotation has spent its daily quota."""


@dataclass
class GeminiUsage:
    """Per-model call counts, so quota spend stays visible."""

    calls: dict[str, int] = field(default_factory=dict)
    exhausted: set[str] = field(default_factory=set)
    #: Prompts served from cache. These cost no quota, and an evaluation run
    #: that reports cache_hits == questions made no API request at all.
    cache_hits: int = 0

    def record(self, model: str) -> None:
        self.calls[model] = self.calls.get(model, 0) + 1

    @property
    def total_calls(self) -> int:
        return sum(self.calls.values())

    def summary(self) -> str:
        used = ", ".join(f"{m}={n}" for m, n in self.calls.items()) or "none"
        spent = ", ".join(sorted(self.exhausted)) or "none"
        return f"calls: {used} | cache hits: {self.cache_hits} | exhausted: {spent}"


# -- response cache ------------------------------------------------------


def cache_dir() -> Path:
    return get_settings().cache_dir / "responses"


def _cache_key(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:24]


def _cache_path(key: str) -> Path:
    """Shard by the first two hex characters, as the embeddings cache does."""
    return cache_dir() / key[:2] / f"{key}.json"


def _cacheable(contents: list) -> str | None:
    """The prompt text, if this request is text-only and may be cached."""
    if contents and all(isinstance(part, str) for part in contents):
        return "\n".join(contents)
    return None


def read_cached(prompt: str) -> tuple[str, str] | None:
    """Return a cached (text, model) pair, or None."""
    path = _cache_path(_cache_key(prompt))
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        return record["text"], record["model"]
    except (json.JSONDecodeError, KeyError, OSError):
        # A truncated entry should be re-fetched, not crash a run.
        return None


def write_cached(prompt: str, text: str, model: str) -> None:
    path = _cache_path(_cache_key(prompt))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"text": text, "model": model, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
        ),
        encoding="utf-8",
    )


class GeminiPool:
    """Calls Gemini, rotating to the next model when a daily quota runs out.

    One pool per process. It remembers which models are spent so a later call
    does not waste a request rediscovering it.
    """

    def __init__(self, models: tuple[str, ...] = MODEL_ROTATION) -> None:
        settings = get_settings()
        if not settings.google_api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY is not set. Get a free key at "
                "https://aistudio.google.com/apikey and add it to .env"
            )
        self._api_key = settings.google_api_key
        self._models = models
        self.usage = GeminiUsage()

    @property
    def available(self) -> list[str]:
        """Models that have not yet reported their daily quota spent."""
        return [m for m in self._models if m not in self.usage.exhausted]

    def generate(
        self,
        contents: list,
        *,
        description: str = "Gemini call",
        use_cache: bool = True,
    ) -> tuple[str, str]:
        """Send a request, trying each available model in turn.

        Args:
            contents: Parts to send - text strings and/or types.Part instances.
            description: Used in error messages.
            use_cache: Serve an identical earlier prompt from the response
                cache. Text-only prompts only. Pass False to force a fresh
                request, which costs quota.

        Returns:
            A (text, model_used) tuple, so callers can record which model
            actually produced a result. For a cache hit the model is the one
            that produced the text originally, which may not be the current
            rotation head.

        Raises:
            AllModelsExhausted: If every model's daily quota is spent.
        """
        from google import genai
        from google.genai import types

        prompt = _cacheable(contents)
        if use_cache and prompt is not None:
            cached = read_cached(prompt)
            if cached is not None:
                self.usage.cache_hits += 1
                return cached

        client = genai.Client(
            api_key=self._api_key,
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
        )
        last_error: Exception | None = None

        candidates = self.available
        for position, model in enumerate(candidates):
            is_last = position == len(candidates) - 1

            def call() -> str:
                response = client.models.generate_content(
                    model=model, contents=contents
                )
                return (response.text or "").strip()

            try:
                text = with_retry(
                    call,
                    description=f"{description} [{model}]",
                    attempts=(
                        ATTEMPTS_ON_LAST_MODEL
                        if is_last
                        else ATTEMPTS_WHILE_ALTERNATIVES_REMAIN
                    ),
                )
                self.usage.record(model)
                if prompt is not None:
                    write_cached(prompt, text, model)
                return text, model
            except RetriesExhausted as error:
                # Transient failure on this model. Another model is another
                # quota bucket and another backend - try it rather than sleeping.
                last_error = error
                continue
            except DailyQuotaExhausted as error:
                self.usage.exhausted.add(model)
                last_error = error
                continue
            except Exception as error:  # noqa: BLE001
                # A model that is retired or rejects our request should not stop
                # the rotation - try the next one, but remember why.
                if "not_found" in str(error).lower() or "404" in str(error):
                    self.usage.exhausted.add(model)
                    last_error = error
                    continue
                raise

        raise AllModelsExhausted(
            f"{description}: all {len(self._models)} free-tier models have spent "
            f"their daily quota. {self.usage.summary()}\n"
            f"Free-tier quota is ~20 requests/day/model and resets daily "
            f"(12:30 PM Sri Lanka time). Last error: {last_error}"
        )
