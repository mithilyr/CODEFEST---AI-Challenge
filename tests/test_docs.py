"""Graph counts asserted in prose, re-derived from the live graph.

WHY THIS FILE EXISTS
--------------------
The edge count has now drifted from the documentation twice.

ADR-028 skipped six self-reference rows and took the count 267 -> 261. Code and
tests followed immediately - `graphview.py`, `conftest.py` and five assertions
across `test_corroborate`, `test_declines` and `test_diagram` all say 261. Three
prose documents did not, and nothing noticed until someone ran the demo, saw the
server print "117 entities, 261 edges", and went looking for why the docs
disagreed.

That is the same failure mode as F-026 and as the one `test_diagram.py` exists
to prevent: a number in a document nobody re-runs. `README.md` and
`ai-usage-disclosure.md` are submitted deliverables, and `CLAUDE.md` is what
every future session reads as ground truth, so a stale figure there propagates
into the report and the video rather than sitting harmlessly in a file.

WHAT IS AND IS NOT SCANNED
--------------------------
ADR-028 set the policy this test enforces: **historical ADRs keep the figures
they measured.** ADR-016 recording "117 nodes and 267 edges" is not a stale
claim, it is what the graph was when ADR-016 was written, and rewriting it would
erase what the measurement said. So `docs/decisions.md` is deliberately out of
scope, and `ai_usage/session-*.txt` are exported chat logs and a mandatory
submission artefact - editing one to tidy a number would falsify the record.

`docs/failures.md` needs no exemption at all: it carries superseded counts only
as fractions, which this regex does not match. See HISTORICAL_DOCS.

Only documents that describe the system **as it is now** are scanned.

WHAT SHAPE IS MATCHED, AND WHAT IS DELIBERATELY MISSED
------------------------------------------------------
Only the pairing shapes - "117 entities and 261 edges", "117 entities, 261
edges" - because they are unambiguously present-tense assertions of graph size,
and they are where both drifts actually happened.

Fractions like "255 of 261 edges (97.7%)" are **not** checked. That shape is
indistinguishable by regex from the historical "three of 267 edges pointed
backwards" in `README.md`, and a test that guessed between them would either
fail on a correct historical sentence or pass on a stale live one. Being narrow
and honest about it beats being clever and wrong; `test_corroborate.py` already
pins the 255/261 figure at its source.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Documents that describe the system as it is now. A graph count in any of
#: these is a claim a judge will read as current.
LIVE_DOCS = (
    "CLAUDE.md",
    "README.md",
    "docs/architecture.md",
    "ai_usage/ai-usage-disclosure.md",
    # Was README.md until 8 Sep, when the README became a plain-English
    # introduction and the evidence moved here. It still describes the system as
    # it is now, so it is scanned - a document does not stop needing a guard
    # because it was renamed.
    "docs/engineering-notes.md",
    # The number sheet exists so the report can be checked against one file.
    # A stale sheet is worse than no sheet - it would launder a wrong figure
    # into every document that trusts it - so it is scanned like the rest.
    "docs/numbers.md",
    # The recording script quotes the server's own boot-time banner - a live
    # claim read aloud on camera is exactly the kind of number this test
    # exists to keep honest, more so than one that only sits in a file.
    "docs/video-script.md",
)

#: Documents whose figures are historical by design. Listed rather than merely
#: omitted, so the exemption is a stated policy instead of an oversight.
#:
#: `docs/failures.md` is *not* here, and that is not an oversight either. It
#: carries superseded counts, but only ever as fractions - "three of 267 edges
#: pointed backwards", "241 -> 267 edges" - which the pairing regex does not
#: match. It needs no exemption because it is never scanned. This test learned
#: that the hard way: listing it here failed, because the exemption test asserts
#: a doc actually contains a superseded pairing, and it contains none.
HISTORICAL_DOCS = ("docs/decisions.md",)

#: "117 entities and 261 edges" / "117 entities, 261 edges" / "117 nodes and ...".
#: Thousands separators are allowed because prose elsewhere writes "3,392".
_PAIR = re.compile(
    r"(?P<entities>[\d,]+)\s+(?:entities|nodes)\s*(?:,|and|,\s*and)\s*(?P<edges>[\d,]+)\s+edges",
    re.IGNORECASE,
)


def _claims(document: str) -> list[tuple[int, int, str]]:
    """Every (entities, edges, line) pair asserted in one document."""
    text = (REPO_ROOT / document).read_text(encoding="utf-8")
    found = []
    for match in _PAIR.finditer(text):
        entities = int(match["entities"].replace(",", ""))
        edges = int(match["edges"].replace(",", ""))
        line = text[: match.start()].count("\n") + 1
        found.append((entities, edges, f"{document}:{line}"))
    return found


@pytest.mark.parametrize("document", LIVE_DOCS)
def test_live_documents_state_the_current_graph_size(document: str, graph):
    """A prose graph count must match the graph that actually builds.

    This is the assertion that would have caught the 267/261 drift on the commit
    that introduced it, rather than three ADRs later.
    """
    wrong = [
        (entities, edges, where)
        for entities, edges, where in _claims(document)
        if (entities, edges) != (len(graph.nodes), len(graph.edges))
    ]
    assert not wrong, (
        f"stale graph count in {document}; the graph builds "
        f"{len(graph.nodes)} entities / {len(graph.edges)} edges, but: "
        + "; ".join(f"{where} says {e} entities / {d} edges" for e, d, where in wrong)
    )


@pytest.mark.parametrize("document", LIVE_DOCS)
def test_live_documents_still_state_a_graph_size(document: str):
    """Guard against the test passing because the sentence was deleted.

    A check that only fires on a *wrong* number is silently satisfied by a
    document that stopped making the claim at all. Each of these four makes the
    no-graph-database argument, and that argument rests on the size being small.
    """
    assert _claims(document), (
        f"{document} no longer states a graph size. If that is deliberate, "
        f"remove it from LIVE_DOCS and say why; otherwise the "
        f"no-graph-database argument has lost its evidence."
    )


@pytest.mark.parametrize("document", HISTORICAL_DOCS)
def test_historical_documents_are_exempt_by_policy(document: str, graph):
    """The exemption is real, and this test documents why it has to be.

    `docs/decisions.md` genuinely contains "117 nodes and 267 edges" (ADR-016).
    That is correct as written - it is what ADR-016 measured. If a future change
    makes every historical figure coincidentally current, this test fails and
    tells whoever is reading that the exemption may no longer be earned.
    """
    stale = [
        where
        for entities, edges, where in _claims(document)
        if (entities, edges) != (len(graph.nodes), len(graph.edges))
    ]
    assert stale, (
        f"{document} no longer contains any superseded graph count. The "
        f"historical-figures exemption exists because it did; re-check whether "
        f"it still needs to be exempt."
    )
