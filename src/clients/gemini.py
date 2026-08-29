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

This is also why response caching matters so much elsewhere in the system: a
cached answer costs no quota, and the demo must never be recorded against a cold
cache.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.clients.retry import DailyQuotaExhausted, with_retry
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


class AllModelsExhausted(RuntimeError):
    """Raised when every model in the rotation has spent its daily quota."""


@dataclass
class GeminiUsage:
    """Per-model call counts, so quota spend stays visible."""

    calls: dict[str, int] = field(default_factory=dict)
    exhausted: set[str] = field(default_factory=set)

    def record(self, model: str) -> None:
        self.calls[model] = self.calls.get(model, 0) + 1

    def summary(self) -> str:
        used = ", ".join(f"{m}={n}" for m, n in self.calls.items()) or "none"
        spent = ", ".join(sorted(self.exhausted)) or "none"
        return f"calls: {used} | exhausted: {spent}"


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

    def generate(self, contents: list, *, description: str = "Gemini call") -> tuple[str, str]:
        """Send a request, trying each available model in turn.

        Args:
            contents: Parts to send - text strings and/or types.Part instances.
            description: Used in error messages.

        Returns:
            A (text, model_used) tuple, so callers can record which model
            actually produced a result.

        Raises:
            AllModelsExhausted: If every model's daily quota is spent.
        """
        from google import genai

        client = genai.Client(api_key=self._api_key)
        last_error: Exception | None = None

        for model in self.available:

            def call() -> str:
                response = client.models.generate_content(
                    model=model, contents=contents
                )
                return (response.text or "").strip()

            try:
                text = with_retry(call, description=f"{description} [{model}]")
                self.usage.record(model)
                return text, model
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
