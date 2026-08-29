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

The index persists to .cache/ so a judge who has run the build once - or who
receives the prebuilt cache - gets instant startup and needs no API key to query.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from src.baseline.chunker import Chunk
from src.clients.embeddings import EMBEDDING_MODEL, EmbeddingStats, embed, embed_query
from src.settings import get_settings


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
        """Return the k most similar chunks to the query."""
        vector = np.asarray(embed_query(query), dtype=np.float32)
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
