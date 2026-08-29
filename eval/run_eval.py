"""Run an evaluation checkpoint and write reproducible results.

    python -m eval.run_eval --checkpoint baseline

One command reproduces the Checkpoint 1 numbers. The first sweep spends one
Gemini request per scoreable question; every sweep after that is served from
``.cache/responses/`` and spends nothing, which is what makes the number
re-derivable rather than a thing someone once saw.

Questions come from the corpus's own ``sample_questions.json`` so the harness
scores the supplied set, not a set we wrote. Ground truth comes from
``eval/answer_key.json``. Where the key has no traced answer - the eleven 1A
questions, which are read off figure plates - the question is recorded as
``not_scored`` rather than dropped, so the denominator stays honest.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from eval.harness import QuestionResult, RetrievedItem, new_run, write_results
from eval.scoring import failure_category, score_answer, score_evidence
from src.settings import get_settings

ANSWER_KEY_PATH = Path(__file__).resolve().parent / "answer_key.json"

#: Marks a citation in a baseline answer. The baseline prompt asks the model to
#: "cite the source numbers you used", so a bare [3] is the expected form.
CITATION_PATTERNS = ("[1]", "[2]", "[3]", "[4]", "[5]", "wiki/", "codex/", "ephemera/", "chronicles/")


def load_questions() -> list[dict]:
    """The competition's own dev questions, read from the corpus."""
    path = get_settings().require_corpus() / "sample_questions.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_key() -> dict[str, dict]:
    raw = json.loads(ANSWER_KEY_PATH.read_text(encoding="utf-8"))
    return {entry["qid"]: entry for entry in raw["questions"]}


def expected_docs(entry: dict) -> list[str]:
    """Documents a correct traversal must reach, from the traced path.

    Conflict questions also require the sources that carry the *rejected*
    claims: a system that never retrieves the sermon cannot know there was a
    disagreement to resolve, so those documents are part of the evidence the
    answer needs, not a distractor to be avoided.
    """
    docs = [hop["source"] for hop in entry.get("expected_path", []) if hop.get("source")]
    conflict = entry.get("conflict") or {}
    for record in conflict.get("rejected", []) + conflict.get("abstains", []):
        if record.get("source"):
            docs.append(record["source"])
    authoritative = conflict.get("authoritative") or {}
    if authoritative.get("source"):
        docs.append(authoritative["source"])
    return list(dict.fromkeys(docs))


def has_citations(answer: str) -> bool:
    return any(pattern in answer for pattern in CITATION_PATTERNS)


def run_baseline(limit: int | None = None, no_cache: bool = False):
    """Run the Checkpoint 1 naive-RAG baseline over the supplied questions."""
    from src.baseline.index import VectorIndex
    from src.baseline.rag import TOP_K, answer as baseline_answer
    from src.clients.gemini import GeminiPool

    index = VectorIndex.load()
    if index is None:
        raise SystemExit(
            "No vector index found. Build it first:\n"
            "    python -m src.baseline.index\n"
            "The build embeds ~3,400 chunks and is cached afterwards."
        )

    questions = load_questions()
    key = load_key()
    if limit:
        questions = questions[:limit]

    run = new_run("baseline")
    pool = GeminiPool()
    started = time.time()

    for position, item in enumerate(questions, start=1):
        qid, question = item["qid"], item["question"]
        track = item["track"].split(":")[0].strip()
        entry = key.get(qid)
        scoreable = entry is not None

        print(f"[{position:2d}/{len(questions)}] {qid} ... ", end="", flush=True)

        before_calls = pool.usage.total_calls
        before_hits = pool.usage.cache_hits
        question_started = time.time()
        error: str | None = None
        predicted: str | None = None
        retrieved: list[RetrievedItem] = []
        retrieved_docs: list[str] = []
        model: str | None = None

        try:
            result = baseline_answer(
                question, index, pool, k=TOP_K, use_cache=not no_cache
            )
            predicted = result.answer
            model = result.model
            retrieved = [
                RetrievedItem(
                    rank=rank,
                    score=round(hit.score, 6),
                    chunk_id=hit.chunk.chunk_id,
                    canonical_doc_id=hit.chunk.canonical_doc_id,
                    collection=hit.chunk.collection,
                    locators=list(hit.chunk.locators),
                    tier=hit.chunk.tier,
                    subtier=hit.chunk.subtier,
                    text=hit.chunk.text,
                )
                for rank, hit in enumerate(result.hits, start=1)
            ]
            retrieved_docs = list(dict.fromkeys(result.retrieved_docs))
        except Exception as exc:  # noqa: BLE001 - a failed question must not end the sweep
            error = f"{type(exc).__name__}: {exc}"

        latency_ms = int((time.time() - question_started) * 1000)
        required = expected_docs(entry) if entry else []
        evidence = score_evidence(required, retrieved_docs)

        if error is not None:
            verdict = None
            category = "error"
        elif not scoreable:
            verdict = None
            category = "not_scored"
        else:
            verdict = score_answer(predicted or "", entry.get("acceptable", []))
            category = failure_category(verdict, evidence)

        verified_by = entry.get("verified_by") if entry else None
        verified_list = (
            [verified_by] if isinstance(verified_by, str) else list(verified_by or [])
        )

        run.questions.append(
            QuestionResult(
                qid=qid,
                track=track,
                question=question,
                expected_answer=entry.get("answer") if entry else None,
                acceptable=entry.get("acceptable", []) if entry else [],
                expected_evidence=required,
                expected_path=entry.get("expected_path", []) if entry else [],
                key_verified=len(verified_list) >= 2,
                key_verified_by=verified_list,
                predicted_answer=predicted,
                retrieved=retrieved,
                retrieved_docs=retrieved_docs,
                scored=scoreable and error is None,
                correct=verdict.correct if verdict else None,
                matched_string=verdict.matched if verdict else None,
                negated_match=verdict.negated_match if verdict else None,
                abstained=verdict.abstained if verdict else False,
                failure_category=category,
                evidence_precision=evidence.precision,
                evidence_recall=evidence.recall,
                evidence_hit=evidence.hit,
                latency_ms=latency_ms,
                llm_calls=pool.usage.total_calls - before_calls,
                cache_hits=pool.usage.cache_hits - before_hits,
                prompt_tokens=None,
                response_tokens=None,
                model=model,
                has_citations=has_citations(predicted or ""),
                answerable=bool(entry.get("answer")) if entry else None,
                error=error,
            )
        )
        print(category)

    run.elapsed_seconds = time.time() - started
    run.key_fully_verified = all(q.key_verified for q in run.scored)
    return run, pool


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--checkpoint",
        default="baseline",
        choices=["baseline"],
        help="Which system to evaluate. Only the Checkpoint 1 baseline exists so far.",
    )
    parser.add_argument("--limit", type=int, help="Run only the first N questions.")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Force fresh API requests. Costs quota - roughly one request per question.",
    )
    args = parser.parse_args(argv)

    run, pool = run_baseline(limit=args.limit, no_cache=args.no_cache)
    json_path, md_path = write_results(run)

    scored = run.scored
    correct = sum(1 for q in scored if q.correct)
    print()
    for track, (hits, total) in run.by_track().items():
        print(f"  {track}: {hits}/{total}")
    print(f"  all scored : {correct}/{len(scored)}")
    print(f"  not scored : {len(run.not_scored)}")
    print(f"  quota      : {pool.usage.summary()}")
    if not run.key_fully_verified:
        unverified = sum(1 for q in scored if not q.key_verified)
        print(
            f"\n  PROVISIONAL: {unverified}/{len(scored)} key entries are unverified. "
            "Do not quote these numbers."
        )
    print(f"\n  {json_path}\n  {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
