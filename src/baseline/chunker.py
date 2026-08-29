"""Fixed-window chunking for the baseline retriever.

This is deliberately the textbook approach: walk each document's blocks in order,
accumulate until a size budget is reached, emit a chunk, and start the next one
with a block of overlap so a fact spanning a boundary survives.

We are not trying to make the baseline clever. Its job is to represent what a
competent team would build in an afternoon, so that any advantage the knowledge
graph shows is attributable to the retrieval strategy rather than to us having
tuned one side and not the other. What the baseline *does* get is the same
high-quality embeddings and the same clean, deduplicated, provenance-carrying
evidence units as the real system.

The one thing chunks keep that a typical naive pipeline discards is provenance:
each chunk records the document it came from and the locators it spans, so the
baseline can cite its sources and be scored on evidence precision like anything
else.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.ingest.pipeline import EvidenceUnit

#: Target characters per chunk. Roughly 250 tokens - large enough to hold a full
#: infobox or paragraph, small enough that a top-5 retrieval stays inside a
#: modest prompt budget.
TARGET_CHARS = 1000

#: Blocks of overlap carried into the next chunk, so a fact split across a
#: boundary appears whole in at least one chunk.
OVERLAP_BLOCKS = 1


@dataclass(frozen=True)
class Chunk:
    """One retrievable window of text, with the provenance to cite it."""

    chunk_id: str
    canonical_doc_id: str
    collection: str
    text: str
    #: Locators of every block this chunk spans, e.g. ("para 68", "para 69").
    locators: tuple[str, ...]
    tier: int
    subtier: int
    doctype: str | None
    display_asset: str | None

    @property
    def citation(self) -> str:
        """Human-readable source reference for the answer."""
        if not self.locators:
            return self.canonical_doc_id
        if len(self.locators) == 1:
            return f"{self.canonical_doc_id} ({self.locators[0]})"
        return f"{self.canonical_doc_id} ({self.locators[0]}-{self.locators[-1]})"


def chunk_documents(evidence: list[EvidenceUnit]) -> list[Chunk]:
    """Group evidence units into fixed-size windows, per document.

    Chunks never span documents. Mixing two sources into one retrieval unit
    would make the tier of the result ambiguous, and the whole conflict model
    depends on knowing which source a claim came from.

    Args:
        evidence: Evidence units from the ingestion pipeline, in document order.

    Returns:
        Chunks in stable order, so an index rebuild is reproducible.
    """
    by_document: dict[str, list[EvidenceUnit]] = {}
    for unit in evidence:
        by_document.setdefault(unit.canonical_doc_id, []).append(unit)

    chunks: list[Chunk] = []

    for doc_id, units in by_document.items():
        window: list[EvidenceUnit] = []
        size = 0

        def flush(window: list[EvidenceUnit]) -> None:
            if not window:
                return
            first = window[0]
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}::c{len(chunks)}",
                    canonical_doc_id=doc_id,
                    collection=first.collection,
                    text="\n".join(u.text for u in window),
                    locators=tuple(u.locator for u in window),
                    tier=first.tier,
                    subtier=first.subtier,
                    doctype=first.doctype,
                    display_asset=first.display_asset,
                )
            )

        for unit in units:
            window.append(unit)
            size += len(unit.text)

            if size >= TARGET_CHARS:
                flush(window)
                window = window[-OVERLAP_BLOCKS:] if OVERLAP_BLOCKS else []
                size = sum(len(u.text) for u in window)

        # Emit the tail, unless it is only the overlap already covered above.
        if window and len(window) > (OVERLAP_BLOCKS if chunks else 0):
            flush(window)

    return chunks
