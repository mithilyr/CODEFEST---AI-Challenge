"""Tests for the OpenRouter provider (`src/clients/openrouter.py`).

No network and no API key required: `_call_model` is the injected seam, the
same boundary `tests/test_clients.py` uses for the OCR client.

The two tests that matter most are `test_http_200_with_an_error_body_*` and
`test_unreachable_network_*`. Both pin failures the sister team found by
actually running their client in Docker, and both crashed a live request rather
than degrading. Unit tests passing is not the same claim as "this was run for
real" - these exist so that lesson costs us nothing to keep.
"""

from __future__ import annotations

import dataclasses
import json
import urllib.error

import pytest

from src.clients import openrouter
from src.clients.openrouter import (
    AllModelsExhausted,
    OpenRouterPool,
    StructuredOutputInvalid,
)
from src.clients.retry import with_retry as _real_with_retry
from src.settings import get_settings

PLAN_SCHEMA = {
    "name": "query_plan",
    "schema": {
        "type": "object",
        "properties": {"start": {"type": "string"}},
        "required": ["start"],
        "additionalProperties": False,
    },
}


@pytest.fixture
def pool(monkeypatch, tmp_path):
    """A pool with a fake key and a scratch cache, so nothing touches .cache/."""
    keyed = dataclasses.replace(
        get_settings(), openrouter_api_key="test-key-not-real", cache_dir=tmp_path
    )
    monkeypatch.setattr("src.clients.openrouter.get_settings", lambda: keyed)
    return OpenRouterPool(models=("model-a", "model-b", "model-c"))


def _responder(monkeypatch, fn):
    monkeypatch.setattr(openrouter, "_call_model", fn)


def _no_sleep_retry(operation, **kwargs):
    """The real `with_retry`, with its backoff sleeps removed.

    Retry behaviour is `retry.py`'s to test; here we only need it to actually
    retry without spending 15 seconds of wall-clock doing it.
    """
    kwargs.pop("sleep", None)
    return _real_with_retry(operation, sleep=lambda _: None, **kwargs)


# --------------------------------------------------------------------------
# The two bugs found live, not by unit tests.
# --------------------------------------------------------------------------


def test_http_200_with_an_error_body_rotates_instead_of_crashing(pool, monkeypatch):
    """LIVE BUG 1. OpenRouter answers 200 with an error body for a retired or
    misspelled model id. Indexing into "choices" raised a bare KeyError, which
    rotation did not recognise, so the whole request died."""
    calls: list[str] = []

    def fake(model, prompt, api_key, *, schema=None, timeout=60):
        calls.append(model)
        if model == "model-a":
            # Exactly the shape the real endpoint returns.
            raise RuntimeError(
                "OpenRouter returned no choices for model-a: "
                "{'message': 'No endpoints found', 'code': 404}"
            )
        return "second model answered"

    _responder(monkeypatch, fake)
    text, model = pool.generate(["hello"])

    assert text == "second model answered"
    assert model == "model-b"
    assert calls[0] == "model-a", "the failing model must actually have been tried"


def test_call_model_raises_informatively_when_choices_is_absent(monkeypatch):
    """The guard itself, at the level it lives: a payload with no `choices`
    must not produce a bare KeyError."""

    class FakeResponse:
        def read(self):
            return json.dumps({"error": {"message": "No endpoints found"}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(openrouter.urllib.request, "urlopen", lambda *a, **k: FakeResponse())

    with pytest.raises(RuntimeError) as caught:
        openrouter._call_model("retired/model:free", "hi", "key")

    assert "No endpoints found" in str(caught.value)
    assert not isinstance(caught.value, KeyError)


def test_unreachable_network_rotates_instead_of_crashing(pool, monkeypatch):
    """LIVE BUG 2. A container with no outbound route raises
    URLError("Network is unreachable"), which `with_retry` does not classify as
    retryable and re-raises unchanged."""

    def fake(model, prompt, api_key, *, schema=None, timeout=60):
        if model in ("model-a", "model-b"):
            raise urllib.error.URLError("Network is unreachable")
        return "third model answered"

    _responder(monkeypatch, fake)
    text, model = pool.generate(["hello"])

    assert text == "third model answered"
    assert model == "model-c"


def test_every_model_unreachable_reports_exhaustion_not_oserror(pool, monkeypatch):
    """The degraded end state must be the provider's own named error, so a
    caller can catch one thing and fall back to a template."""

    def fake(model, prompt, api_key, *, schema=None, timeout=60):
        raise urllib.error.URLError("Network is unreachable")

    _responder(monkeypatch, fake)
    with pytest.raises(AllModelsExhausted):
        pool.generate(["hello"])


# --------------------------------------------------------------------------
# Rotation, quota, caching.
# --------------------------------------------------------------------------


def test_daily_quota_retires_a_model_for_the_process(pool, monkeypatch):
    """Gemini's lesson (ADR-007) applied here: a spent daily allowance must not
    be rediscovered on every later call.

    The error text matters. `retry.with_retry` classifies by *message* against
    `DAILY_QUOTA_SIGNALS`, so the provider's own wording is what turns this
    into a retirement rather than five pointless retries - which is why the
    fake raises the message shape a provider really sends.
    """

    def fake(model, prompt, api_key, *, schema=None, timeout=60):
        if model == "model-a":
            raise RuntimeError("RequestsPerDay limit exceeded for this model")
        return f"{model} answered"

    _responder(monkeypatch, fake)
    text, model = pool.generate(["first"])

    assert model == "model-b"
    assert "model-a" in pool.usage.exhausted
    assert "model-a" not in pool.available


def test_auth_and_retired_model_errors_retire_rather_than_retry(pool, monkeypatch):
    """401/402/403/404 are not transient. Retrying them spends wall-clock to
    learn nothing."""

    def fake(model, prompt, api_key, *, schema=None, timeout=60):
        if model == "model-a":
            raise urllib.error.HTTPError(
                openrouter.API_URL, 404, "Not Found", hdrs=None, fp=None
            )
        return "ok"

    _responder(monkeypatch, fake)
    pool.generate(["x"])
    assert "model-a" in pool.usage.exhausted


def test_a_server_error_is_retried_and_never_retires_the_model(pool, monkeypatch, tmp_path):
    """A 500 is transient. It belongs to `with_retry`'s backoff, not to the
    retire-and-rotate branch that 401/404 take - otherwise one blip
    permanently removes a working model for the rest of the process.

    So the model is retried, then rotated past, and the run ends in
    AllModelsExhausted with nothing marked exhausted.
    """
    seen: list[str] = []

    def fake(model, prompt, api_key, *, schema=None, timeout=60):
        seen.append(model)
        raise urllib.error.HTTPError(openrouter.API_URL, 500, "Server Error", None, None)

    _responder(monkeypatch, fake)
    monkeypatch.setattr(openrouter, "with_retry", _no_sleep_retry)

    with pytest.raises(AllModelsExhausted):
        pool.generate(["x"])

    assert seen.count("model-a") > 1, "a 500 must be retried, not abandoned at once"
    assert pool.usage.exhausted == set(), "a transient error must not retire a model"


def test_repeated_prompts_are_served_from_cache(pool, monkeypatch):
    calls: list[str] = []

    def fake(model, prompt, api_key, *, schema=None, timeout=60):
        calls.append(prompt)
        return "answered once"

    _responder(monkeypatch, fake)
    pool.generate(["same question"])
    pool.generate(["same question"])

    assert len(calls) == 1, "the second call must not reach the network"
    assert pool.usage.cache_hits == 1


def test_the_same_prompt_asked_for_prose_and_for_a_plan_are_different_cache_entries(
    pool, monkeypatch
):
    """A schema is part of the request. Sharing a key would serve a sentence
    where a plan was wanted."""

    def fake(model, prompt, api_key, *, schema=None, timeout=60):
        return json.dumps({"start": "x"}) if schema else "a sentence"

    _responder(monkeypatch, fake)
    prose, _ = pool.generate(["identical text"])
    plan, _ = pool.generate(["identical text"], schema=PLAN_SCHEMA)

    assert prose == "a sentence"
    assert json.loads(plan) == {"start": "x"}


# --------------------------------------------------------------------------
# Structured output.
# --------------------------------------------------------------------------


def test_structured_request_sends_a_json_schema_response_format(pool, monkeypatch):
    captured: dict = {}

    class FakeResponse:
        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": '{"start": "ok"}'}}]}
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data.decode())
        return FakeResponse()

    monkeypatch.setattr(openrouter.urllib.request, "urlopen", fake_urlopen)
    value, _ = pool.generate_structured(["plan this"], PLAN_SCHEMA)

    assert value == {"start": "ok"}
    assert captured["body"]["response_format"]["type"] == "json_schema"
    assert captured["body"]["response_format"]["json_schema"]["strict"] is True


def test_a_model_ignoring_the_schema_rotates_to_the_next_one(pool, monkeypatch):
    """Not every model honours a schema every time. That is a rotation
    condition, not a raised error, because the next model may honour it."""

    def fake(model, prompt, api_key, *, schema=None, timeout=60):
        if model == "model-a":
            return "Sure! Here is your plan:"  # prose, not JSON
        return json.dumps({"start": "ederon_fellgard"})

    _responder(monkeypatch, fake)
    value, model = pool.generate_structured(["plan"], PLAN_SCHEMA)

    assert value == {"start": "ederon_fellgard"}
    assert model == "model-b"


def test_a_json_array_is_not_accepted_as_a_plan(pool, monkeypatch):
    def fake(model, prompt, api_key, *, schema=None, timeout=60):
        return "[1, 2, 3]"

    _responder(monkeypatch, fake)
    with pytest.raises(StructuredOutputInvalid):
        pool.generate_structured(["plan"], PLAN_SCHEMA)


def test_invalid_structured_output_is_never_cached(pool, monkeypatch):
    """A bad response must not be replayed from cache on the next run."""
    attempts: list[str] = []

    def fake(model, prompt, api_key, *, schema=None, timeout=60):
        attempts.append(model)
        return "not json at all"

    _responder(monkeypatch, fake)
    with pytest.raises(AllModelsExhausted):
        pool.generate(["plan"], schema=PLAN_SCHEMA)

    assert openrouter.read_cached("plan", "query_plan") is None


# --------------------------------------------------------------------------
# Construction.
# --------------------------------------------------------------------------


def test_a_missing_key_fails_with_an_actionable_message(monkeypatch, tmp_path):
    keyless = dataclasses.replace(
        get_settings(), openrouter_api_key=None, cache_dir=tmp_path
    )
    monkeypatch.setattr("src.clients.openrouter.get_settings", lambda: keyless)

    with pytest.raises(RuntimeError) as caught:
        OpenRouterPool()

    assert "OPENROUTER_API_KEY" in str(caught.value)
    assert "openrouter.ai/keys" in str(caught.value)


def test_planner_models_are_a_subset_of_what_advertises_structured_output():
    """Pins the split that the live 2026-09-01 verification produced: only 4 of
    18 free models honour a schema, and the planner may only use those. This
    test does not hit the network - `--verify` does that."""
    assert set(openrouter.PLANNER_MODELS) <= {
        "z-ai/glm-5.2:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "dots-studio/dots-3-note-preview:free",
        "liquid/lfm-2.5-2.6b:free",
    }
    assert openrouter.PLANNER_MODELS, "the planner needs at least one model"
