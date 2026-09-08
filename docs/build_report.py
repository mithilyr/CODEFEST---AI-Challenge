"""Render `docs/report.md` to a single self-contained HTML file for printing.

WHY NOT A PDF LIBRARY. The submission needs a PDF, and every Python route to one
on Windows (weasyprint, wkhtmltopdf, pandoc) drags in a native toolchain that
nobody on this team installed or can defend. A browser already has a
print-to-PDF engine, so the shortest defensible path is one HTML file with A4
print CSS, printed from the browser.

The architecture SVG is inlined rather than linked, so the HTML is one file and
the print engine cannot silently drop a missing image.

    python docs/build_report.py
    # then open docs/report.html and print to PDF (A4, margins default,
    # background graphics ON)

`markdown` is a dev-time convenience for this script only. It is deliberately
NOT in requirements.txt: nothing the graded system runs imports it, and a judge
following the README must not be made to install it.
"""

from __future__ import annotations

import re
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent
CSS = """
@page { size: A4; margin: 14mm 15mm; }
* { box-sizing: border-box; }
body { font: 9.6pt/1.42 "Segoe UI", -apple-system, Roboto, sans-serif;
       color: #16161a; margin: 0; }
h1 { font-size: 17pt; margin: 0 0 .15em; letter-spacing: -.01em; }
h2 { font-size: 11.5pt; margin: 1.1em 0 .35em; padding-bottom: .18em;
     border-bottom: 1.5px solid #16161a; page-break-after: avoid; }
h3 { font-size: 10pt; margin: .85em 0 .3em; color: #33333c;
     page-break-after: avoid; }
p, li { margin: .38em 0; }
ul { margin: .35em 0; padding-left: 1.1em; }
strong { color: #000; }
em { color: #33333c; }
code { font-family: Consolas, ui-monospace, monospace; font-size: .87em;
       background: #f1f1f4; padding: .05em .28em; border-radius: 3px; }
table { border-collapse: collapse; width: 100%; margin: .5em 0;
        font-size: 8.9pt; page-break-inside: avoid; }
th, td { text-align: left; padding: .26em .5em; border: 1px solid #d6d6de;
         vertical-align: top; }
th { background: #f1f1f4; font-weight: 600; }
hr { border: 0; border-top: 1px solid #d6d6de; margin: .9em 0; }
blockquote { margin: .5em 0; padding-left: .8em; border-left: 3px solid #c8c8d2;
             color: #33333c; }
.diagram { text-align: center; margin: .5em 0; page-break-inside: avoid; }
.diagram svg { max-width: 100%; height: auto; max-height: 132mm; }
a { color: #16161a; }
"""


def inline_svg(html: str) -> str:
    """Replace the diagram <img> with the SVG's own markup."""

    def repl(match: re.Match[str]) -> str:
        src = match.group(1)
        path = (ROOT / src).resolve()
        if not path.is_file():
            raise SystemExit(f"diagram not found: {path}")
        svg = path.read_text(encoding="utf-8")
        svg = re.sub(r"<\?xml[^>]*\?>", "", svg).strip()
        return f'<div class="diagram">{svg}</div>'

    return re.sub(r'<p><img[^>]*src="([^"]+)"[^>]*/?></p>', repl, html)


def main() -> None:
    source = (ROOT / "report.md").read_text(encoding="utf-8")
    body = markdown.markdown(source, extensions=["tables", "attr_list"])
    body = inline_svg(body)

    out = ROOT / "report.html"
    out.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Ashen Era Intelligence Assistant - Submission Report</title>"
        f"<style>{CSS}</style></head><body>{body}</body></html>",
        encoding="utf-8",
    )
    print(f"wrote {out}")
    print(f"  {len(source.split())} words")
    print("  open it and print to PDF: A4, background graphics ON")


if __name__ == "__main__":
    main()
