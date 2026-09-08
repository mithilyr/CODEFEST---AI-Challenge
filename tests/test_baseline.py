"""The Checkpoint 1 baseline's build path, exercised without spending quota.

WHY THIS MODULE EXISTS
----------------------
`eval/run_eval.py` tells a judge with no index to run
`python -m src.baseline.index`. Until 2026-09-08 that module had no `__main__`
block, so the command printed nothing and exited 0 (F-037): the one instruction
standing between a fresh clone and the Checkpoint 1 numbers did nothing, and no
test noticed because `src/baseline/` had no tests at all.

Nothing here touches the corpus or Voyage. `embed` is replaced with a
deterministic stand-in and the cache is redirected into `tmp_path`, so the whole
module runs on a clone with no data and no keys.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from src.baseline import index as index_module
from src.baseline.index import VectorIndex, build_and_save, main
from src.clients.embeddings import EmbeddingsUnavailableError
from src.ingest.pipeline import EvidenceUnit
from src.settings import PROJECT_ROOT, get_settings

#: Voyage's dimension. The real vectors are 1024-wide; keeping that here means
#: a shape assumption that only holds for toy widths cannot pass.
DIMENSIONS = 1024


def an_evidence_unit(n: int, doc: str = "wiki/ashfall_colossus.md") -> EvidenceUnit:
    return EvidenceUnit(
        evidence_id=f"{doc}#{n}",
        canonical_doc_id=doc,
        collection="wiki",
        locator=f"para {n}",
        kind="paragraph",
        # Long enough that the chunker's 1000-char budget flushes every unit or
        # two, so a handful of units produces more than one chunk.
        text=f"Block {n}. " + "The colossus walked. " * 40,
        tier=1,
        subtier=0,
        doctype="article",
        subject_slug="ashfall_colossus",
        display_asset=None,
    )


@pytest.fixture
def offline(monkeypatch, tmp_path: Path):
    """Redirect the cache into tmp_path and stub out the embedding call.

    Settings are patched rather than the environment: a developer with a real
    VOYAGE_API_KEY in .env would otherwise have these tests fall through to a
    live, billable API call.
    """
    sandboxed = dataclasses.replace(get_settings(), cache_dir=tmp_path / ".cache")
    monkeypatch.setattr(index_module, "get_settings", lambda: sandboxed)

    #: One entry per embed() call, as (input_type, texts). A build makes two -
    #: the chunks, then the shipped query vectors - so tests that count work
    #: done must say which they mean.
    calls: list[tuple[str, list[str]]] = []

    def fake_embed(texts, *, input_type="document", stats=None, progress=False):
        calls.append((input_type, list(texts)))
        # Distinct, non-parallel vectors, so a search that ignores the query
        # cannot accidentally rank correctly.
        vectors = []
        for i, _ in enumerate(texts):
            vector = np.zeros(DIMENSIONS, dtype=np.float32)
            vector[i % DIMENSIONS] = 1.0
            vectors.append(vector.tolist())
        return vectors

    monkeypatch.setattr(index_module, "embed", fake_embed)
    return calls


@pytest.fixture
def corpus_free(monkeypatch, offline):
    """`offline`, plus an ingestion pass that returns fixed evidence."""
    import src.ingest.pipeline as pipeline

    result = pipeline.IngestionResult(
        documents=[],
        evidence=[an_evidence_unit(n) for n in range(6)],
        dedup_report=pipeline.DedupReport(),
        failures=[],
        elapsed_seconds=0.0,
    )
    monkeypatch.setattr(pipeline, "ingest_cached", lambda force=False: result)
    return offline


# -- the regression itself ------------------------------------------------


def test_the_command_run_eval_names_is_actually_runnable():
    """`python -m src.baseline.index` must reach an entry point.

    This is the exact defect: the module was importable and did nothing. `-m`
    with `--help` needs neither corpus nor key, so it is safe to run here, and
    it fails loudly if the `__main__` block is ever removed again.
    """
    completed = subprocess.run(
        [sys.executable, "-m", "src.baseline.index", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--force" in completed.stdout


def test_run_eval_points_at_a_module_that_can_build():
    """The remedy in run_eval's error message must name a real entry point.

    Asserted against the message rather than a comment, so renaming the module
    without updating the message breaks a test instead of a judge's evening.
    """
    source = (PROJECT_ROOT / "eval" / "run_eval.py").read_text(encoding="utf-8")
    assert "python -m src.baseline.index" in source
    assert callable(index_module.main)
    assert hasattr(index_module, "build_and_save")


# -- the build path -------------------------------------------------------


def test_build_writes_vectors_and_chunks_that_load_back(corpus_free, tmp_path):
    built = build_and_save(progress=False)

    vectors_path, chunks_path = VectorIndex._paths()
    assert vectors_path.is_file() and chunks_path.is_file()
    assert vectors_path.parent == tmp_path / ".cache" / "index"

    reloaded = VectorIndex.load()
    assert reloaded is not None
    assert len(reloaded) == len(built) > 1
    assert reloaded.matrix.shape == (len(built), DIMENSIONS)
    # Chunk provenance must survive the JSON round trip, or citations break.
    assert reloaded.chunks[0].locators == built.chunks[0].locators
    assert isinstance(reloaded.chunks[0].locators, tuple)


def test_saved_vectors_are_normalised(corpus_free):
    """Search is a dot product, which is only cosine if the rows are unit-length."""
    index = build_and_save(progress=False)
    norms = np.linalg.norm(index.matrix, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-6)


def documents_embedded(calls) -> int:
    return sum(1 for input_type, _ in calls if input_type == "document")


def test_second_run_reuses_the_saved_index_and_re_embeds_nothing(corpus_free):
    calls = corpus_free
    build_and_save(progress=False)
    embedded_once = len(calls)

    again = build_and_save(progress=False)

    assert len(calls) == embedded_once, "a warm index must not re-embed"
    assert len(again) > 0


def test_force_rebuilds(corpus_free):
    calls = corpus_free
    build_and_save(progress=False)
    build_and_save(force=True, progress=False)
    assert documents_embedded(calls) == 2


def test_a_build_ships_query_vectors_for_the_supplied_questions(corpus_free, monkeypatch):
    """The bundle is only key-free if the dev questions' vectors travel with it."""
    monkeypatch.setattr(
        index_module, "sample_questions", lambda: ["Question one?", "Question two?"]
    )
    build_and_save(progress=False)

    shipped = index_module.load_query_vectors()
    assert sorted(shipped) == ["Question one?", "Question two?"]
    assert index_module.VectorIndex._queries_path().is_file()


def test_a_shipped_vector_is_used_instead_of_calling_the_api(corpus_free, monkeypatch):
    """The point of the sidecar: a shipped query must spend nothing."""
    monkeypatch.setattr(index_module, "sample_questions", lambda: ["Known question?"])
    index = build_and_save(progress=False)

    def must_not_be_called(text):  # pragma: no cover - the assertion is that it isn't
        raise AssertionError("search called the embedding API for a shipped query")

    monkeypatch.setattr(index_module, "embed_query", must_not_be_called)

    hits = index.search("Known question?", k=1)
    assert len(hits) == 1

    with pytest.raises(AssertionError):
        index.search("A question nobody shipped", k=1)


def test_main_returns_zero_and_builds(corpus_free):
    assert main([]) == 0
    assert VectorIndex.load() is not None


def test_missing_key_exits_one_and_prints_the_remedy(corpus_free, monkeypatch, capsys):
    """A judge with no VOYAGE_API_KEY gets the remedy, not a traceback."""

    def unavailable(*args, **kwargs):
        raise EmbeddingsUnavailableError(
            "3392 text(s) are not in the embedding cache and "
            "VOYAGE_API_KEY is not set."
        )

    monkeypatch.setattr(index_module, "embed", unavailable)

    assert main([]) == 1
    assert "VOYAGE_API_KEY" in capsys.readouterr().err


def test_run_eval_fails_loudly_when_the_index_is_missing(monkeypatch):
    """A missing index must not read as success to a script wrapping this.

    `raise SystemExit("message")` prints to stderr and exits 1 - the message is
    not an exit code. Pinned because the alternative, `print` then `return 0`,
    looks almost identical at the call site and would make a CI wrapper green
    on the one failure a fresh clone actually hits.
    """
    import eval.run_eval as run_eval

    monkeypatch.setattr(VectorIndex, "load", classmethod(lambda cls: None))

    with pytest.raises(SystemExit) as raised:
        run_eval.main(["--checkpoint", "baseline"])

    # A str code means "print me and exit 1". 0 and None both mean success.
    assert raised.value.code not in (0, None)
    assert "python -m src.baseline.index" in str(raised.value.code)


# -- the committed bundle (ADR-047) ---------------------------------------
#
# These run against the real `.cache/index/`, not a tmp_path, because what they
# assert is a property of the *shipped* files: a fresh clone must reproduce
# 1B 2/7 and 1C 2/2 with no API key. Nothing here calls an API.


def committed_bundle_present() -> bool:
    return (PROJECT_ROOT / ".cache" / "index").is_dir()


needs_bundle = pytest.mark.skipif(
    not committed_bundle_present(),
    reason="No .cache/index/; run `python -m src.baseline.index`.",
)


@needs_bundle
def test_the_bundle_is_not_ignored_by_git():
    """The exception in .gitignore must actually reach all three files.

    `.cache/` was ignored wholesale until ADR-047, and `*.npy` is *still*
    ignored globally - the vectors survive on one negation line. Asked of git
    itself rather than by reading the file, because the precedence rules here
    are exactly the part that is easy to get wrong.
    """
    for name in (
        "voyage-4-lite.vectors.npy",
        "voyage-4-lite.chunks.json",
        "voyage-4-lite.queries.json",
    ):
        path = f".cache/index/{name}"
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", path], cwd=PROJECT_ROOT
        ).returncode == 0
        assert not ignored, f"{path} is gitignored; the bundle would not ship"

    # And the 82 MB of chunk embeddings must stay out.
    assert (
        subprocess.run(
            ["git", "check-ignore", "-q", ".cache/embeddings"], cwd=PROJECT_ROOT
        ).returncode
        == 0
    ), ".cache/embeddings/ is 82 MB and must stay ignored"


@needs_bundle
def test_every_supplied_question_has_a_shipped_query_vector(corpus_root):
    """Without these the baseline calls Voyage, which is the whole gap ADR-047 closes."""
    from src.baseline.index import load_query_vectors, sample_questions

    shipped = load_query_vectors()
    missing = [q for q in sample_questions() if q not in shipped]
    assert not missing, f"{len(missing)} question(s) would need a live embedding"
    assert all(len(v) == DIMENSIONS for v in shipped.values())


@needs_bundle
def test_the_committed_index_matches_what_the_chunker_produces_now(corpus_root):
    """A committed artefact can drift from the code that made it. This is the guard.

    The chunker is deterministic and the corpus is read-only, so a mismatch
    means the shipped vectors describe text that no longer exists - and the
    baseline numbers would be measured against a corpus nobody has.
    """
    from src.baseline.chunker import chunk_documents
    from src.ingest.pipeline import ingest_cached

    expected = chunk_documents(ingest_cached().evidence)
    shipped = VectorIndex.load()

    assert shipped is not None
    assert len(shipped) == len(expected), (
        f"committed index has {len(shipped)} chunks, the chunker now produces "
        f"{len(expected)} - rebuild with `python -m src.baseline.index --force`"
    )
    assert [c.chunk_id for c in shipped.chunks] == [c.chunk_id for c in expected]


def test_a_pool_with_no_key_still_serves_the_cache(monkeypatch):
    """Constructing a GeminiPool must not need a key (ADR-047).

    It did until 8 Sep, and that alone made a keyless replay impossible: the
    constructor raised before a single cached response was read.
    """
    import dataclasses

    import src.clients.gemini as gemini

    keyless = dataclasses.replace(get_settings(), google_api_key=None)
    monkeypatch.setattr(gemini, "get_settings", lambda: keyless)

    pool = gemini.GeminiPool()  # must not raise
    monkeypatch.setattr(gemini, "read_cached", lambda prompt: ("cached text", "m"))

    text, model = pool.generate(["a prompt"])
    assert (text, model) == ("cached text", "m")
    assert pool.usage.cache_hits == 1


def test_a_pool_with_no_key_refuses_a_real_request(monkeypatch):
    """Deferring the check must not lose it - a cache miss still says what to do."""
    import dataclasses

    import src.clients.gemini as gemini

    keyless = dataclasses.replace(get_settings(), google_api_key=None)
    monkeypatch.setattr(gemini, "get_settings", lambda: keyless)
    monkeypatch.setattr(gemini, "read_cached", lambda prompt: None)

    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY is not set"):
        gemini.GeminiPool().generate(["an uncached prompt"])
