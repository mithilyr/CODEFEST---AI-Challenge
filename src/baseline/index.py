"""In-memory vector index over the corpus chunks.

WHY NOT A VECTOR DATABASE
-------------------------
The corpus produces roughly 30,000 chunks. At 1024 dimensions in float32 that is
about 120 MB, and an exhaustive cosine search is a single matrix multiply that
completes in low milliseconds. FAISS, Chroma and Pinecone all solve approximate
search at a scale we do not have; adopting one would add an install step, a
service to explain, and an approximation error, in exchange for nothing
measurable.

Vectors are L2-normalised once at build time, which turns cosine similarity into
a plain dot product and removes per-query normalisation entirely.

The index persists to .cache/index/, which is committed (ADR-047), so a fresh
clone gets instant startup and needs no API key to reproduce the Checkpoint 1
numbers.

Build it with::

    python -m src.baseline.index

which is the command ``eval/run_eval.py`` names when it finds no index. That
command was a no-op until 2026-09-08: this module had no ``__main__`` block, so
a judge following the error message saw nothing happen (F-037).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from src.baseline.chunker import Chunk
from src.clients.embeddings import (
    EMBEDDING_MODEL,
    EmbeddingsUnavailableError,
    EmbeddingStats,
    embed,
    embed_query,
)
from src.settings import MissingCorpusError, get_settings


@dataclass(frozen=True)
class SearchHit:
    """One retrieved chunk and its similarity to the query."""

    chunk: Chunk
    score: float


class VectorIndex:
    """Exhaustive cosine-similarity search over chunk embeddings."""

    def __init__(self, chunks: list[Chunk], matrix: np.ndarray) -> None:
        if len(chunks) != matrix.shape[0]:
            raise ValueError(
                f"chunk/vector mismatch: {len(chunks)} chunks, {matrix.shape[0]} vectors"
            )
        self.chunks = chunks
        self.matrix = matrix

    # -- construction ----------------------------------------------------

    @classmethod
    def build(cls, chunks: list[Chunk], *, progress: bool = True) -> "VectorIndex":
        """Embed every chunk and assemble the index."""
        stats = EmbeddingStats()
        vectors = embed(
            [chunk.text for chunk in chunks],
            input_type="document",
            stats=stats,
            progress=progress,
        )
        if progress:
            print(f"  embeddings: {stats.summary()}")

        matrix = np.asarray(vectors, dtype=np.float32)
        # Normalise once so querying is a dot product, not a cosine computation.
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return cls(chunks, matrix / norms)

    # -- persistence -----------------------------------------------------

    @staticmethod
    def _paths() -> tuple[Path, Path]:
        base = get_settings().cache_dir / "index"
        return base / f"{EMBEDDING_MODEL}.vectors.npy", base / f"{EMBEDDING_MODEL}.chunks.json"

    def save(self) -> None:
        """Persist vectors and chunk metadata side by side."""
        vectors_path, chunks_path = self._paths()
        vectors_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(vectors_path, self.matrix)
        chunks_path.write_text(
            json.dumps([asdict(c) for c in self.chunks]), encoding="utf-8"
        )

    @staticmethod
    def _queries_path() -> Path:
        return get_settings().cache_dir / "index" / f"{EMBEDDING_MODEL}.queries.json"

    @classmethod
    def load(cls) -> "VectorIndex | None":
        """Load a persisted index, or None if it has not been built."""
        vectors_path, chunks_path = cls._paths()
        if not (vectors_path.is_file() and chunks_path.is_file()):
            return None
        matrix = np.load(vectors_path)
        raw = json.loads(chunks_path.read_text(encoding="utf-8"))
        chunks = [Chunk(**{**c, "locators": tuple(c["locators"])}) for c in raw]
        return cls(chunks, matrix)

    # -- search ----------------------------------------------------------

    def search(self, query: str, k: int = 5) -> list[SearchHit]:
        """Return the k most similar chunks to the query.

        Query vectors shipped alongside the index are used in preference to
        calling Voyage, so the committed bundle reproduces the Checkpoint 1
        numbers with no key (ADR-047). A question outside that set still needs
        one - the bundle covers the supplied dev questions, not every question.
        """
        shipped = load_query_vectors().get(query)
        vector = np.asarray(
            shipped if shipped is not None else embed_query(query), dtype=np.float32
        )
        norm = np.linalg.norm(vector)
        if norm:
            vector = vector / norm

        scores = self.matrix @ vector
        # argpartition finds the top k without sorting all 30,000 scores.
        top = np.argpartition(-scores, min(k, len(scores) - 1))[:k]
        top = top[np.argsort(-scores[top])]

        return [SearchHit(chunk=self.chunks[i], score=float(scores[i])) for i in top]

    def __len__(self) -> int:
        return len(self.chunks)


# -- shipped query vectors -----------------------------------------------


def load_query_vectors() -> dict[str, list[float]]:
    """Query embeddings shipped with the index, keyed by question text.

    WHY THESE ARE SEPARATE FROM THE EMBEDDING CACHE (ADR-047)
    ---------------------------------------------------------
    `.cache/embeddings/` is 82 MB of per-chunk vectors and stays gitignored.
    The baseline only ever embeds twenty *queries* - the corpus's own
    `sample_questions.json` - and those are a few KB. Keeping them beside the
    index makes the committed bundle exactly one directory, rather than twenty
    negation rules in `.gitignore` pointing at content-addressed shard names.

    Read fresh each call rather than cached: `search` is called once per
    question over a twenty-question run, so the file is read twenty times, and
    a module-level cache would go stale the moment a rebuild rewrote it.
    """
    path = VectorIndex._queries_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A truncated sidecar should fall through to the API, not crash a run.
        return {}


def save_query_vectors(questions: list[str], *, progress: bool = True) -> int:
    """Embed the supplied questions and save them beside the index.

    Returns:
        How many query vectors were written. Zero when the corpus is absent -
        the questions come from it, and a build without one is still a valid
        index, just not a self-contained bundle.
    """
    if not questions:
        return 0
    vectors = embed(questions, input_type="query", progress=False)
    path = VectorIndex._queries_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(zip(questions, vectors))), encoding="utf-8"
    )
    if progress:
        print(f"  queries: {len(vectors)} shipped vectors -> {path.name}")
    return len(vectors)


def sample_questions() -> list[str]:
    """The corpus's own dev questions, or [] when the corpus is absent."""
    from src.settings import MissingCorpusError as _Missing

    try:
        path = get_settings().require_corpus() / "sample_questions.json"
        return [item["question"] for item in json.loads(path.read_text(encoding="utf-8"))]
    except (_Missing, OSError, KeyError, json.JSONDecodeError):
        return []

# -- operator entry point ------------------------------------------------


def build_and_save(*, force: bool = False, progress: bool = True) -> "VectorIndex":
    """Ingest, chunk, embed and persist the baseline index.

    Args:
        force: Rebuild even when a saved index is already present. A rebuild
            costs nothing in quota if the embedding cache is warm, but the
            cache is under .cache/ too, so on a fresh clone it is a full spend.
        progress: Print per-stage progress. Off in tests.

    Returns:
        The index that was built, or the one already on disk when it was
        present and `force` was not set.
    """
    if not force:
        existing = VectorIndex.load()
        if existing is not None:
            if progress:
                vectors_path, _ = VectorIndex._paths()
                print(
                    f"index already built: {len(existing)} chunks at "
                    f"{vectors_path.parent}\npass --force to rebuild."
                )
            return existing

    from src.baseline.chunker import chunk_documents
    from src.ingest.pipeline import ingest_cached

    evidence = ingest_cached().evidence
    chunks = chunk_documents(evidence)
    if progress:
        print(f"  chunks: {len(chunks)} from {len(evidence)} evidence units")

    index = VectorIndex.build(chunks, progress=progress)
    index.save()
    save_query_vectors(sample_questions(), progress=progress)

    if progress:
        vectors_path, chunks_path = VectorIndex._paths()
        print(f"  saved: {vectors_path}")
        print(f"         {chunks_path}")
    return index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild even if a saved index is present.",
    )
    args = parser.parse_args(argv)

    # A judge reaches this command from run_eval's error message, so both
    # failures it can hit - no corpus, no key - print their own remedy rather
    # than a traceback.
    try:
        build_and_save(force=args.force)
    except MissingCorpusError as error:
        print(error, file=sys.stderr)
        return 1
    except EmbeddingsUnavailableError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
