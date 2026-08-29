"""Checkpoint 1: the naive RAG baseline.

Deliberately the obvious pipeline, with no advantages the real system will have:

    embed query -> top-k cosine -> concatenate chunks -> ask an LLM

What it specifically does NOT get, because these are the things under test:

  * No source authority. Chunks are presented in similarity order with no tier,
    so the model cannot know a codex outranks a sermon.
  * No graph traversal, so no way to join two documents that share no vocabulary.
  * No conflict detection. Contradictory claims arrive side by side, unmarked.
  * No abstention. It is asked to answer, as a naive pipeline would be.

It does get the same embeddings, the same clean deduplicated corpus, and the
same provenance-carrying evidence units as the real system. Handicapping the
baseline would make any later win meaningless.

The prompt is intentionally ordinary - what a competent team writes on day one.
Tuning it would blur what we are measuring, which is the retrieval strategy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.baseline.index import SearchHit, VectorIndex
from src.clients.gemini import GeminiPool

#: Chunks passed to the model. Five is the common default and fits the free-tier
#: context comfortably.
TOP_K = 5

BASELINE_PROMPT = """Answer the question using only the source passages below.

{context}

Question: {question}

Answer concisely. Cite the source numbers you used."""


@dataclass
class BaselineAnswer:
    """One baseline response, with everything needed to score it."""

    question: str
    answer: str
    hits: list[SearchHit]
    model: str
    #: Documents cited by the retriever, for evidence-precision scoring.
    retrieved_docs: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"Q: {self.question}", f"A: {self.answer}", "", "retrieved:"]
        lines += [
            f"  {i}. {h.score:.3f} tier {h.chunk.tier}.{h.chunk.subtier} "
            f"{h.chunk.canonical_doc_id}"
            for i, h in enumerate(self.hits, start=1)
        ]
        return "\n".join(lines)


def build_context(hits: list[SearchHit]) -> str:
    """Format retrieved chunks for the prompt.

    Sources are numbered and named, because even a naive pipeline cites its
    sources - but no tier or authority is included. That omission is the point:
    it is what the conflict layer will later add.
    """
    return "\n\n".join(
        f"[{i}] {hit.chunk.canonical_doc_id}\n{hit.chunk.text}"
        for i, hit in enumerate(hits, start=1)
    )


def answer(
    question: str,
    index: VectorIndex,
    pool: GeminiPool | None = None,
    *,
    k: int = TOP_K,
) -> BaselineAnswer:
    """Run the baseline pipeline for one question."""
    pool = pool or GeminiPool()
    hits = index.search(question, k=k)

    text, model = pool.generate(
        [BASELINE_PROMPT.format(context=build_context(hits), question=question)],
        description="baseline synthesis",
    )

    return BaselineAnswer(
        question=question,
        answer=text,
        hits=hits,
        model=model,
        retrieved_docs=[h.chunk.canonical_doc_id for h in hits],
    )
