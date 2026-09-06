"""Are there entities the corpus names that the graph has no node for?

    python -m eval.probes.entity_reachability

ADR-027 measured *edges*: 255 of 261 edges between existing nodes are named by a
non-wiki passage. It never measured the **node set**. `build.py` builds nodes
from wiki infobox rows, so an entity that only the codex, chronicles or ephemera
name has no node at all, and a question about it declines by construction rather
than on evidence. That boundary is real and was undocumented; this probe puts a
number on it. ADR-030 records the result.

Read-only. It imports the graph builder, the ingest pass and `route.py`'s
gazetteer so that the surface forms measured here are byte-identical to the ones
the shipped answer path recognises - a probe that invents its own third scanner
measures its own scanner, not the product (ADR-027 made the same call for the
same reason). Nothing here writes or mutates anything, and nothing under `src/`
imports it.

Two extractors, deliberately different in precision:

1. **The gazetteer** - `src/graph/corroborate.py`'s `scan_surfaces`, itself
   `route.py`'s. Every hit resolves by construction, because the gazetteer is
   built *from* the graph's nodes. It is here as the known-good half of the
   denominator, not as a discovery mechanism.
2. **Capitalised multi-word spans** - for names the gazetteer has never heard
   of. This is the noisy half and it is noisy on purpose: an extractor tuned
   until it only found real entities would be assuming the answer. In-world
   honorifics ("High Inquisitor"), document-type names ("Field Report") and
   short forms ("The Cartel") all survive it. ADR-030 hand-checks a fifteen-name
   sample and states the true rate; do not quote the raw unreachable count as an
   entity count.

Resolution is **exact only** - `EXACT`, `NORMALISED` and `ALIAS`, the three
tiers `resolve.py` reaches without guessing. `AMBIGUOUS` (a fuzzy near-miss) is
counted as unreachable, because ADR-011 forbids fuzzy resolution from picking a
winner and this probe may not quietly do what the product refuses to.

A third measurement needs no hand-check at all. Every `ephemera/` document is
named `<doctype>_concerning_<subject>.<ext>`, and `src/ingest/metadata.py`
already parses that into `EvidenceUnit.subject_slug`. The corpus is *declaring*
who each document is about, so those subjects are first-class by the archive's
own convention. Counting how many of them the graph cannot reach is a clean
number with no extraction noise in it at all.
"""

from __future__ import annotations

import collections
import random
import re

from src.graph.build import build_graph, load_relation_map
from src.graph.corroborate import CORROBORATING_COLLECTIONS, scan_surfaces
from src.ingest.pipeline import ingest
from src.query.resolve import EntityResolver, ResolutionStatus
from src.settings import get_settings

#: Seed for the hand-check sample. Fixed so the fifteen names ADR-030 checked
#: are the fifteen names this prints, forever.
SAMPLE_SEED = 20260906
SAMPLE_SIZE = 15

#: The three resolution tiers that reach a node without guessing. `AMBIGUOUS`
#: is excluded on purpose: it is `resolve.py` reporting near-misses, and
#: ADR-011 forbids promoting one of those to an answer.
EXACT_TIERS = frozenset(
    {ResolutionStatus.EXACT, ResolutionStatus.NORMALISED, ResolutionStatus.ALIAS}
)

#: One capitalised word, allowing internal apostrophes and hyphens so
#: "Iron-Ring" stays one token rather than two.
_TOKEN = r"[A-Z][a-z]+(?:['’-][A-Z]?[a-z]+)*"
#: Lowercase words a proper name may contain but not begin with.
_CONNECTIVE = r"(?:of|the|and|de|von|van|du|la|le)"
_SPAN_RE = re.compile(rf"\b{_TOKEN}(?:\s+(?:{_CONNECTIVE}\s+)?{_TOKEN})+")

_POSSESSIVE_RE = re.compile(r"[’']s$")

#: Function words a sentence can start with, which the span regex then sweeps
#: into the name ("And the Bleeding Crown", "Of Sabelle Blackspire"). Stripping
#: them is not noise-hiding: a possessive and a leading conjunction are
#: grammatical inflections of the same name, so leaving them in would *inflate*
#: the unreachable count with duplicates of names that do resolve. The set is
#: closed-class function words only - conjunctions, prepositions, determiners -
#: chosen by word class rather than by which ones happened to look untidy in a
#: sample. "The" is deliberately absent: it is part of several node names.
_LEADING_STOPWORDS = frozenset(
    """a an and but because in for yet so when while though although after before
    behind then thus if since as at by from on to with upon beneath beyond within
    without against among that which who whose where whether not nor or still even
    once until during of my our your his her its their this these those""".split()
)


def normalise_span(span: str) -> str:
    """Strip the possessive and any leading function words from a matched span.

    Returns "" when nothing multi-word survives, which is the signal to discard
    the span - this probe measures multi-word names, and a bare surname left
    behind by the strip is not one.
    """
    parts = _POSSESSIVE_RE.sub("", span).strip().split()
    while parts and parts[0].lower() in _LEADING_STOPWORDS:
        parts.pop(0)
    return " ".join(parts) if len(parts) >= 2 else ""


class Candidates:
    """Candidate names found outside the wiki, and where each one was found."""

    def __init__(self) -> None:
        #: casefolded name -> the form to display
        self.display: dict[str, str] = {}
        #: casefolded name -> {(collection, canonical document id)}
        self.sources: dict[str, set[tuple[str, str]]] = collections.defaultdict(set)
        #: casefolded name -> occurrences
        self.mentions: collections.Counter = collections.Counter()

    def add(self, name: str, unit) -> None:
        key = name.casefold()
        self.display.setdefault(key, name)
        self.sources[key].add((unit.collection, unit.canonical_doc_id))
        self.mentions[key] += 1


def collect(result, graph) -> tuple[Candidates, dict[str, str]]:
    """One pass over the non-wiki evidence, running both extractors."""
    resolver = EntityResolver(graph)
    pattern, surface_to_key, _ = scan_surfaces(graph, resolver)

    found = Candidates()
    for unit in result.evidence:
        if unit.collection not in CORROBORATING_COLLECTIONS:
            continue
        if unit.kind not in ("paragraph", "page"):
            continue
        for match in pattern.finditer(unit.text):
            found.add(match.group(1), unit)
        for match in _SPAN_RE.finditer(unit.text):
            name = normalise_span(match.group(0))
            if name:
                found.add(name, unit)
    return found, surface_to_key


def partition(
    found: Candidates, graph, surface_to_key: dict[str, str]
) -> tuple[dict[str, str], list[str]]:
    """Split candidates into those that reach a graph node and those that do not."""
    resolver = EntityResolver(graph)
    reachable: dict[str, str] = {}
    unreachable: list[str] = []
    for key, name in found.display.items():
        if key in surface_to_key:
            reachable[key] = surface_to_key[key]
            continue
        outcome = resolver.resolve(name)
        if outcome.status in EXACT_TIERS and outcome.key:
            reachable[key] = outcome.key
        else:
            unreachable.append(key)
    return reachable, sorted(unreachable)


def declared_subjects(result, graph) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Per-document `subject_slug`: does the graph hold the entity it names?

    The filename convention (`contract_concerning_halvard_cindervale.pdf`) is
    the archive declaring what a document is about, so this measurement needs no
    extractor and carries no extraction noise.
    """
    subjects: dict[str, str] = {}
    for unit in result.evidence:
        if unit.collection in CORROBORATING_COLLECTIONS and unit.subject_slug:
            subjects.setdefault(unit.subject_slug, unit.canonical_doc_id)

    resolver = EntityResolver(graph)
    reached: list[tuple[str, str]] = []
    missing: list[tuple[str, str]] = []
    for slug, document in sorted(subjects.items()):
        outcome = resolver.resolve(slug.replace("_", " "))
        found_node = slug in graph.nodes or outcome.status in EXACT_TIERS
        (reached if found_node else missing).append((slug, document))
    return reached, missing


_TABLE_ROW_RE = re.compile(r"^\|\s*(?P<field>[^|]+?)\s*\|\s*(?P<value>.*?)\s*\|\s*$")


def _first_table(text: str) -> list[tuple[str, str]]:
    """Rows of the first pipe table, re-parsed independently of `build.py`.

    Deliberately a throwaway parser, the same choice `corpus_shape.py` made and
    for the same reason: a probe that shares a parser with the thing it measures
    cannot contradict it. Only the *field-to-relation map* is shared, because
    which fields are relations is configuration, not behaviour.
    """
    rows: list[tuple[str, str]] = []
    started = False
    for line in text.splitlines():
        match = _TABLE_ROW_RE.match(line.strip())
        if not match:
            if started:
                break
            continue
        started = True
        field_name, value = match.group("field"), match.group("value")
        if field_name == "Field" or set(field_name) <= set("-: "):
            continue
        rows.append((field_name, value))
    return rows


def silent_relation_rows(graph) -> list[tuple[str, str, str, list[str]]]:
    """Infobox rows on a mapped relation field that produced no edge at all.

    A row can legitimately produce nothing - a `Secret` whose prose names no
    entity, a `Core location | No` - so this is a list to read, not a defect
    count. What it exists to catch is the third case: a cell that plainly names
    entities and still yields no edge. The last element of each tuple is the
    `;`-separated names in the cell that are not graph nodes.

    Read entirely from the graph's own public output (`Edge.document` and
    `Edge.row`) against an independent re-parse of the page, so it cannot
    disagree with the builder about what the builder did.
    """
    relations = load_relation_map()
    corpus = get_settings().require_corpus()

    produced = {(edge.document, edge.row) for edge in graph.edges}
    resolver = EntityResolver(graph)

    silent: list[tuple[str, str, str, list[str]]] = []
    for page in sorted((corpus / "wiki").glob("*.md")):
        doc_id = f"wiki/{page.name}"
        text = page.read_text(encoding="utf-8")
        for index, (field_name, value) in enumerate(_first_table(text)):
            if relations.lookup(field_name) is None:
                continue
            if (doc_id, index) in produced:
                continue
            # A `;`-part that is *entirely* a capitalised multi-word span is a
            # bare name, not a sentence - the same test the corpus-wide scan
            # above uses, so the two halves of this probe agree on what a name
            # looks like.
            lost = [
                part
                for part in (p.strip() for p in value.split(";"))
                if part
                and "[[" not in part
                and _SPAN_RE.fullmatch(part)
                and resolver.resolve(part).status not in EXACT_TIERS
            ]
            silent.append((doc_id, field_name, value, lost))
    return silent


def report(result, graph) -> str:
    scanned = sum(
        1
        for u in result.evidence
        if u.collection in CORROBORATING_COLLECTIONS and u.kind in ("paragraph", "page")
    )
    found, surface_to_key = collect(result, graph)
    reachable, unreachable = partition(found, graph, surface_to_key)

    by_collection: collections.Counter = collections.Counter()
    exclusive: collections.Counter = collections.Counter()
    for key in unreachable:
        named_in = {c for c, _ in found.sources[key]}
        for collection in named_in:
            by_collection[collection] += 1
        if len(named_in) == 1:
            exclusive[next(iter(named_in))] += 1

    total = len(found.display)
    lines = [
        "Cross-collection entity reachability (ADR-030)",
        "",
        f"non-wiki units scanned        : {scanned}",
        f"graph nodes                   : {len(graph.nodes)}",
        f"graph edges                   : {len(graph.edges)}",
        "",
        f"distinct candidate names      : {total}",
        f"  reach one of the {len(graph.nodes)} nodes   : "
        f"{len(reachable)}  ({100 * len(reachable) / total:.1f}%)",
        f"  reach no node               : "
        f"{len(unreachable)}  ({100 * len(unreachable) / total:.1f}%)",
        "",
        "unreachable names by collection (a name in two collections counts in both):",
    ]
    for collection in sorted(by_collection, key=lambda c: -by_collection[c]):
        lines.append(
            f"    {collection:12} {by_collection[collection]:4}"
            f"   ({exclusive[collection]} named in this collection only)"
        )

    lines += [
        "",
        f"Sample of {SAMPLE_SIZE} unreachable names (seed {SAMPLE_SEED}), "
        "hand-checked in ADR-030:",
    ]
    sample = random.Random(SAMPLE_SEED).sample(
        unreachable, min(SAMPLE_SIZE, len(unreachable))
    )
    for key in sorted(sample):
        _, document = sorted(found.sources[key])[0]
        lines.append(
            f"    {found.display[key]!r:42} x{found.mentions[key]:<4} {document}"
        )

    reached, missing = declared_subjects(result, graph)
    subject_total = len(reached) + len(missing)
    lines += [
        "",
        "Documents that declare their own subject in the filename",
        "(`<doctype>_concerning_<subject>`) - no extractor, so no extraction noise:",
        f"    declared subjects         : {subject_total}",
        f"    reach a graph node        : "
        f"{len(reached)}  ({100 * len(reached) / subject_total:.1f}%)",
        f"    reach no node             : "
        f"{len(missing)}  ({100 * len(missing) / subject_total:.1f}%)",
    ]
    for slug, document in missing:
        lines.append(f"        {slug:40} {document}")
    lines.append(
        "    (ADR-030 adjudicates these two by hand; one is a truncated filename.)"
    )

    silent = silent_relation_rows(graph)
    with_names = [row for row in silent if row[3]]
    lines += [
        "",
        "Infobox rows on a mapped relation field that produced no edge:",
        f"    silent rows               : {len(silent)}",
        f"    of those, naming an entity the graph does not hold : {len(with_names)}",
    ]
    for doc_id, field_name, value, lost in with_names:
        lines.append(f"        {doc_id} | {field_name} | {value}")
        lines.append(f"            unreachable names: {lost}")

    return "\n".join(lines)


def main() -> None:
    result = ingest()
    graph = build_graph(result)
    print(report(result, graph))


if __name__ == "__main__":
    main()
