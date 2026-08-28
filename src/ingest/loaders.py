"""Format-specific text extraction, producing citable text blocks.

Every block carries a locator ("para 170", "page 3") because the whole system is
built on traceable evidence: a graph edge that cannot name the line it came from
is not usable as evidence. Extracting locators here, at read time, is far cheaper
than trying to recover them later by searching for a passage in the source file.

Format coverage:
    .md    read raw - the wiki markup ([[links]], pipe tables) is the graph
           source, so it must not be normalised away
    .txt   read raw, split on blank lines
    .docx  paragraphs *and* tables, in document order (the Annals interleaves
           prose with registry tables, and the tables carry the relations)
    .pdf   per-page text via pdfplumber

Scanned PDFs are not handled here. They have no text layer at all - verified: the
17 .scan.pdf files contain /Image and DCTDecode but no /Font - so they route
through src/ingest/ocr.py instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TextBlock:
    """One citable unit of text from a document.

    The locator is what appears in a citation, so it is written for a human
    reader rather than for machine round-tripping.
    """

    text: str
    #: Human-readable position, e.g. "para 170", "page 3", "table 2 row 5".
    locator: str
    #: paragraph | heading | table_row | page
    kind: str


class UnsupportedFormatError(ValueError):
    """Raised for a file extension no loader handles."""


#: Typographic characters the corpus uses, mapped to ASCII equivalents.
#:
#: This is not cosmetic. The codex and wiki use U+2019 for apostrophes
#: ("Gloamreach’s forged is 303 AS"), so a relation regex or entity lookup
#: written with a plain ASCII apostrophe silently fails to match. Normalising at
#: read time means every downstream component compares like with like.
_PUNCTUATION_NORMALISATION = {
    0x2018: "'",    # left single quote
    0x2019: "'",    # right single quote / apostrophe
    0x201C: '"',    # left double quote
    0x201D: '"',    # right double quote
    0x2013: "-",    # en dash
    0x2014: "-",    # em dash
    0x2026: "...",  # ellipsis
    0x00A0: " ",    # non-breaking space
}

_WHITESPACE_RE = re.compile(r"[ 	]+")


def _clean(text: str) -> str:
    """Normalise typographic punctuation, collapse whitespace runs, and strip.

    Markup characters are left alone - the wiki [[links]] and pipe tables the
    graph builder parses must survive intact.
    """
    return _WHITESPACE_RE.sub(" ", text.translate(_PUNCTUATION_NORMALISATION)).strip()


def load_markdown(path: Path) -> list[TextBlock]:
    """Read a wiki article, preserving markup verbatim.

    Markdown is returned unnormalised because the graph builder parses [[links]]
    and pipe tables out of it. Blocks are split on blank lines, and a heading is
    tagged as such so citations can say which section a fact came from.
    """
    raw = path.read_text(encoding="utf-8").translate(_PUNCTUATION_NORMALISATION)
    blocks: list[TextBlock] = []
    current_heading = "body"

    for index, chunk in enumerate(re.split(r"\n\s*\n", raw), start=1):
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.startswith("#"):
            current_heading = chunk.lstrip("#").strip()
            blocks.append(
                TextBlock(text=chunk, locator=f"heading: {current_heading}", kind="heading")
            )
        else:
            blocks.append(
                TextBlock(
                    text=chunk,
                    locator=f"section '{current_heading}', block {index}",
                    kind="paragraph",
                )
            )
    return blocks


def load_text(path: Path) -> list[TextBlock]:
    """Read a plain-text ephemeral document, split on blank lines."""
    # Encoding is not guaranteed for in-world documents; errors="replace" keeps a
    # single bad byte from dropping an entire piece of evidence.
    raw = path.read_text(encoding="utf-8", errors="replace")
    return [
        TextBlock(text=_clean(chunk), locator=f"block {index}", kind="paragraph")
        for index, chunk in enumerate(re.split(r"\n\s*\n", raw), start=1)
        if chunk.strip()
    ]


def load_docx(path: Path) -> list[TextBlock]:
    """Read a .docx, returning paragraphs and table rows in document order.

    Document order matters. The Annals of the Ashen Era alternates a registry
    heading with the table holding that registry's relations; reading all
    paragraphs and then all tables would sever every table from its subject.
    python-docx exposes paragraphs and tables as separate collections, so we walk
    the underlying XML body to recover the true ordering.
    """
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(str(path))
    body = document.element.body

    blocks: list[TextBlock] = []
    para_index = 0
    table_index = 0

    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]

        if tag == "p":
            para_index += 1
            text = _clean(Paragraph(child, document).text)
            if not text:
                continue
            blocks.append(
                TextBlock(text=text, locator=f"para {para_index}", kind="paragraph")
            )

        elif tag == "tbl":
            table_index += 1
            table = Table(child, document)
            for row_index, row in enumerate(table.rows, start=1):
                cells = [_clean(cell.text) for cell in row.cells]
                # Word repeats a merged cell's text across the cells it spans;
                # de-duplicating consecutive repeats keeps "Field | Value" rows
                # from becoming "Field | Field | Value".
                deduped: list[str] = []
                for cell in cells:
                    if not deduped or deduped[-1] != cell:
                        deduped.append(cell)
                text = " | ".join(c for c in deduped if c)
                if not text:
                    continue
                blocks.append(
                    TextBlock(
                        text=text,
                        locator=f"table {table_index} row {row_index}",
                        kind="table_row",
                    )
                )

    return blocks


def load_pdf(path: Path) -> list[TextBlock]:
    """Read a text-layer PDF, one block per page.

    Returns an empty list for a PDF with no extractable text - that is the
    signature of a scan, and the caller routes it to OCR rather than treating an
    empty document as a load failure.
    """
    import pdfplumber

    blocks: list[TextBlock] = []
    with pdfplumber.open(str(path)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = _clean(page.extract_text() or "")
            if text:
                blocks.append(
                    TextBlock(text=text, locator=f"page {page_number}", kind="page")
                )
    return blocks


#: Dispatch table. Keyed by lowercased extension.
LOADERS = {
    ".md": load_markdown,
    ".txt": load_text,
    ".docx": load_docx,
    ".pdf": load_pdf,
}


def load(path: Path) -> list[TextBlock]:
    """Read any supported document into citable text blocks.

    Raises:
        UnsupportedFormatError: If no loader handles the extension.
    """
    loader = LOADERS.get(path.suffix.lower())
    if loader is None:
        raise UnsupportedFormatError(
            f"No loader for {path.suffix!r} ({path.name}). "
            f"Supported: {', '.join(sorted(LOADERS))}"
        )
    return loader(path)
