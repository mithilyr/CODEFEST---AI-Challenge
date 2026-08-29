"""Tests for the evaluation harness.

The scoring tests carry real strings from the corpus and from the answer key,
not invented ones, so a change in scoring behaviour shows up against the data we
actually score.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from eval.harness import QuestionResult, new_run, render_markdown
from eval.run_eval import expected_docs, has_citations, load_key
from eval.scoring import (
    failure_category,
    is_abstention,
    normalise,
    score_answer,
    score_evidence,
)


# -- normalisation -------------------------------------------------------


def test_normalise_folds_the_corpus_curly_apostrophe():
    """The corpus uses U+2019. An answer typed with U+0027 must still match."""
    assert normalise("Sorrowfell’s forged") == normalise("Sorrowfell's forged")


def test_normalise_does_not_glue_tokens_together():
    """Deleting punctuation instead of replacing it would make '391AS' match
    '391 AS'. Punctuation becomes a space so that cannot happen."""
    assert normalise("391 AS") == "391 as"
    assert normalise("391AS") != normalise("391 AS")


# -- the over-crediting trap ---------------------------------------------


def test_negated_gold_is_not_scored_correct():
    """The trap answer_key.json warns about in its own preamble.

    'there is no mention of who the victors were' contains the gold phrase and
    a substring scorer marks it correct. It must not be.
    """
    predicted = "Unfortunately there is no mention of who the victors were."
    verdict = score_answer(predicted, ["the victors were"])
    assert verdict.correct is False
    assert verdict.negated_match == "the victors were"
    assert verdict.label == "negated_gold"


def test_negated_gold_survives_the_real_1c_shape():
    """The wiki abstention for the Sorrowfell forging date names the year
    nowhere, but a model echoing the wiki can still emit the gold token inside
    a refusal."""
    predicted = "The forging date is not recorded; some accounts say 391 AS but this is contested."
    assert score_answer(predicted, ["391 AS"]).correct is False


def test_a_plain_correct_answer_still_matches():
    predicted = "The Gauntlet of Sorrowfell was forged in 391 AS according to the codex [2]."
    verdict = score_answer(predicted, ["391 AS", "391"])
    assert verdict.correct is True
    assert verdict.matched == "391 AS"


def test_a_negation_far_away_does_not_poison_a_good_answer():
    """The window is one clause. A denial about something else, later in a long
    answer, must not retract a correct claim made earlier."""
    predicted = (
        "The Gauntlet of Sorrowfell was forged in 391 AS. "
        + "Separately, the archive records nothing about its later bearers, and "
        + "there is no mention of where it was kept before the codex entry, nor "
        + "any account of who commissioned it in the first place."
    )
    assert score_answer(predicted, ["391 AS"]).correct is True


def test_word_boundaries_prevent_a_substring_year_match():
    """'246' must not match inside '1246'."""
    assert score_answer("founded in 1246 AS", ["246 AS"]).correct is False


def test_set_valued_questions_accept_any_member():
    """1b_006 lists 14 acceptable individuals; any one counts."""
    acceptable = ["Ravena Stormwell", "Brannoc Palefroth", "Isolde Mournvale"]
    assert score_answer("Brannoc Palefroth was a member.", acceptable).correct is True


def test_abstention_is_detected_separately_from_wrongness():
    assert is_abstention("I cannot determine this from the provided sources.")
    assert not is_abstention("The answer is Gloamreach.")


# -- evidence ------------------------------------------------------------


def test_evidence_recall_and_precision():
    verdict = score_evidence(
        ["wiki/a.md", "wiki/b.md"],
        ["wiki/a.md", "wiki/z.md", "wiki/y.md", "wiki/x.md", "wiki/w.md"],
    )
    assert verdict.recall == 0.5
    assert verdict.precision == pytest.approx(0.2)
    assert verdict.hit == ["wiki/a.md"]


def test_evidence_is_none_when_the_question_has_no_traced_path():
    """1A questions are read off figure plates. No path means recall is
    undefined, not zero - reporting 0.0 would understate the run."""
    verdict = score_evidence([], ["wiki/a.md"])
    assert verdict.recall is None
    assert verdict.precision is None


def test_duplicate_retrievals_do_not_inflate_precision():
    """Two chunks from one document are one document reached."""
    verdict = score_evidence(["wiki/a.md"], ["wiki/a.md", "wiki/a.md"])
    assert verdict.precision == 1.0


# -- failure categories --------------------------------------------------


def _verdicts(predicted, acceptable, expected, retrieved):
    return (
        score_answer(predicted, acceptable),
        score_evidence(expected, retrieved),
    )


def test_category_separates_the_two_1b_failure_shapes():
    """CLAUDE.md claims baseline joins fail because retrieval never reaches the
    second document, or reaches it and cannot join. These are the two counts
    that turn that sentence into a measurement."""
    answer, evidence = _verdicts("Wrong.", ["Gloamreach"], ["wiki/a.md", "wiki/b.md"], ["wiki/z.md"])
    assert failure_category(answer, evidence) == "retrieval_miss"

    answer, evidence = _verdicts("Wrong.", ["Gloamreach"], ["wiki/a.md", "wiki/b.md"], ["wiki/a.md"])
    assert failure_category(answer, evidence) == "partial_retrieval"

    answer, evidence = _verdicts(
        "Wrong.", ["Gloamreach"], ["wiki/a.md", "wiki/b.md"], ["wiki/a.md", "wiki/b.md"]
    )
    assert failure_category(answer, evidence) == "synthesis_failure"


def test_correct_beats_every_other_category():
    answer, evidence = _verdicts("Gloamreach.", ["Gloamreach"], ["wiki/a.md"], ["wiki/z.md"])
    assert failure_category(answer, evidence) == "correct"


# -- the key itself ------------------------------------------------------


def test_answer_key_is_loadable_and_every_entry_has_what_scoring_needs():
    key = load_key()
    assert key, "answer key is empty"
    for qid, entry in key.items():
        assert entry.get("acceptable"), f"{qid} has no acceptable answers"
        assert entry.get("expected_path") is not None, f"{qid} has no path"


def test_conflict_questions_require_the_rejected_sources_as_evidence():
    """A system that never retrieves the sermon cannot know a disagreement
    existed, so the decoy documents are required evidence, not distractors."""
    key = load_key()
    required = expected_docs(key["1c_003"])
    assert any("sermon" in doc for doc in required)
    assert any("codex" in doc for doc in required)


def test_key_verification_status_is_reported_not_assumed():
    """Guards the whole provisional-results contract: if someone sets
    verified_by to a single name, that is still not two independent reviewers."""
    key = load_key()
    unverified = [q for q, e in key.items() if not e.get("verified_by")]
    assert len(unverified) == len(key), (
        "Some key entries now claim verification. If that is real, update this "
        "test and ADR-014. If it is not, the provisional banner is lying."
    )


# -- reporting -----------------------------------------------------------


def _question(**overrides) -> QuestionResult:
    base = dict(
        qid="1b_013",
        track="1B",
        question="Whose dominion encompasses the lair of the Gravemaw Wyrm?",
        expected_answer="The Bleeding Crown",
        acceptable=["The Bleeding Crown"],
        expected_evidence=["wiki/gravemaw_wyrm.md", "wiki/marrowwell_abbey.md"],
        expected_path=[],
        key_verified=False,
        key_verified_by=[],
        predicted_answer="The Bleeding Crown [1]",
        retrieved=[],
        retrieved_docs=["wiki/gravemaw_wyrm.md"],
        scored=True,
        correct=True,
        matched_string="The Bleeding Crown",
        negated_match=None,
        abstained=False,
        failure_category="correct",
        evidence_precision=1.0,
        evidence_recall=0.5,
        evidence_hit=["wiki/gravemaw_wyrm.md"],
        latency_ms=12,
        llm_calls=0,
        cache_hits=1,
        prompt_tokens=None,
        response_tokens=None,
        model="gemini-3.7-flash",
        has_citations=True,
        answerable=True,
    )
    base.update(overrides)
    return QuestionResult(**base)


def test_report_shouts_when_the_key_is_unverified():
    run = new_run("baseline")
    run.questions = [_question()]
    report = render_markdown(run)
    assert "PROVISIONAL" in report
    assert "Do not quote" in report


def test_report_stops_shouting_once_the_key_is_verified():
    run = new_run("baseline")
    run.questions = [_question(key_verified=True, key_verified_by=["ana", "ben"])]
    report = render_markdown(run)
    assert "PROVISIONAL" not in report
    assert "Verified" in report


def test_unscored_questions_are_listed_not_dropped():
    """1A must appear in the report with its own count, so the denominator for
    the scored questions is never mistaken for the whole question set."""
    run = new_run("baseline")
    run.questions = [
        _question(),
        _question(qid="1a_008", track="1A", scored=False, correct=None,
                  failure_category="not_scored", expected_answer=None,
                  acceptable=[], expected_evidence=[], evidence_recall=None,
                  evidence_precision=None, evidence_hit=[], answerable=None),
    ]
    report = render_markdown(run)
    assert "Not scored" in report
    assert "1a_008" in report
    assert "| **all scored** | **1** | **1** |" in report


def test_run_is_json_serialisable_for_diffing_between_checkpoints():
    run = new_run("baseline")
    run.questions = [_question()]
    payload = json.loads(run.to_json())
    assert payload["questions"][0]["qid"] == "1b_013"
    assert payload["schema_version"] >= 1


def test_citation_detection():
    assert has_citations("The answer is X [3].")
    assert has_citations("See wiki/gloamreach.md")
    assert not has_citations("The answer is X.")


# -- response cache ------------------------------------------------------


def test_response_cache_serves_a_repeat_prompt_without_an_api_call(tmp_path, monkeypatch):
    """The whole re-runnability claim rests on this. A second identical sweep
    must cost zero quota, or the Checkpoint numbers are a thing someone saw
    once rather than a thing anyone can reproduce."""
    import src.clients.gemini as gemini

    monkeypatch.setattr(gemini, "cache_dir", lambda: tmp_path / "responses")
    gemini.write_cached("PROMPT", "the answer", "gemini-3.7-flash")

    assert gemini.read_cached("PROMPT") == ("the answer", "gemini-3.7-flash")
    assert gemini.read_cached("A DIFFERENT PROMPT") is None


def test_pool_returns_the_cached_answer_and_records_a_hit(tmp_path, monkeypatch):
    import src.clients.gemini as gemini

    monkeypatch.setattr(gemini, "cache_dir", lambda: tmp_path / "responses")
    monkeypatch.setattr(
        gemini, "get_settings", lambda: SimpleNamespace(google_api_key="test-key")
    )
    gemini.write_cached("hello", "cached text", "gemini-3.5-flash")

    pool = gemini.GeminiPool()
    text, model = pool.generate(["hello"])

    assert (text, model) == ("cached text", "gemini-3.5-flash")
    assert pool.usage.cache_hits == 1
    assert pool.usage.total_calls == 0, "a cache hit must not count as an API call"


def test_image_prompts_are_never_cached_here(tmp_path, monkeypatch):
    """OCR carries its own committed cache. Hashing image bytes into this one
    would duplicate it and bloat .cache/ for no gain."""
    import src.clients.gemini as gemini

    monkeypatch.setattr(gemini, "cache_dir", lambda: tmp_path / "responses")
    assert gemini._cacheable(["text", object()]) is None
    assert gemini._cacheable(["text", "more text"]) == "text\nmore text"


def test_a_truncated_cache_entry_is_refetched_not_fatal(tmp_path, monkeypatch):
    import src.clients.gemini as gemini

    monkeypatch.setattr(gemini, "cache_dir", lambda: tmp_path / "responses")
    path = gemini._cache_path(gemini._cache_key("PROMPT"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")

    assert gemini.read_cached("PROMPT") is None


# -- rotation under transient failure ------------------------------------


def _drive(monkeypatch, tmp_path, outcomes: list):
    """Return (gemini module, attempts-seen list) with the network replaced.

    `outcomes` is consumed one entry per model tried: an exception to raise or
    a string to return. This drives the rotation without touching the network.
    """
    import src.clients.gemini as gemini

    monkeypatch.setattr(gemini, "cache_dir", lambda: tmp_path / "responses")
    monkeypatch.setattr(
        gemini, "get_settings", lambda: SimpleNamespace(google_api_key="test-key")
    )
    seen: list[int] = []
    queue = list(outcomes)

    def fake_with_retry(operation, *, attempts=5, description="", **kwargs):
        seen.append(attempts)
        outcome = queue.pop(0) if queue else "fallthrough"
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(gemini, "with_retry", fake_with_retry)
    return gemini, seen


def test_transient_failure_rotates_to_the_next_model(monkeypatch, tmp_path):
    """A per-minute limit on one model says nothing about the next, which has
    its own quota bucket. Rotating beats sleeping - measured after an evaluation
    sweep stalled 19 minutes on a single hung request."""
    from src.clients.retry import RetriesExhausted

    gemini, seen = _drive(
        monkeypatch, tmp_path, [RetriesExhausted("429 rate limit"), "second model's answer"]
    )
    pool = gemini.GeminiPool()
    text, model = pool.generate(["hello"])

    assert text == "second model's answer"
    assert model == gemini.MODEL_ROTATION[1]
    assert len(seen) == 2, "should have tried exactly two models"


def test_daily_quota_retires_a_model_for_the_rest_of_the_process(monkeypatch, tmp_path):
    from src.clients.retry import DailyQuotaExhausted

    gemini, _ = _drive(
        monkeypatch, tmp_path, [DailyQuotaExhausted("perday"), "answer"]
    )
    pool = gemini.GeminiPool()
    _, model = pool.generate(["hello"])

    assert gemini.MODEL_ROTATION[0] in pool.usage.exhausted
    assert gemini.MODEL_ROTATION[0] not in pool.available
    assert model == gemini.MODEL_ROTATION[1]


def test_attempts_are_few_while_alternatives_remain_and_many_on_the_last(
    monkeypatch, tmp_path
):
    """While another model is untried, give up fast and rotate. On the last one,
    waiting is the only option left, so spend every attempt."""
    gemini, seen = _drive(monkeypatch, tmp_path, ["ok"])
    gemini.GeminiPool(models=("only-model",)).generate(["sole model prompt"])
    assert seen == [gemini.ATTEMPTS_ON_LAST_MODEL]

    # A distinct prompt: the same one would be served from the cache written
    # above, and no request would be attempted at all.
    gemini, seen = _drive(monkeypatch, tmp_path, ["ok"])
    gemini.GeminiPool(models=("first", "second")).generate(["two model prompt"])
    assert seen == [gemini.ATTEMPTS_WHILE_ALTERNATIVES_REMAIN]


def test_every_model_failing_transiently_still_raises_rather_than_hanging(
    monkeypatch, tmp_path
):
    from src.clients.retry import RetriesExhausted

    from src.clients.gemini import MODEL_ROTATION

    gemini, seen = _drive(
        monkeypatch, tmp_path, [RetriesExhausted("429")] * len(MODEL_ROTATION)
    )
    with pytest.raises(gemini.AllModelsExhausted):
        gemini.GeminiPool().generate(["every model fails"])
    assert len(seen) == len(MODEL_ROTATION), "every model should have been tried"


def test_a_request_timeout_is_configured():
    """The SDK defaults to no timeout, which is how a sweep hangs indefinitely
    with no error and no way to interrupt it."""
    import src.clients.gemini as gemini

    assert gemini.REQUEST_TIMEOUT_MS > 0
    assert gemini.REQUEST_TIMEOUT_MS <= 300_000, "a timeout this long is not a timeout"
