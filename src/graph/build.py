"""Build the graph from ingested evidence, one infobox row at a time.

The builder consumes `EvidenceUnit`s rather than re-reading the corpus, so the
document identity, authority tier and locator attached during ingestion carry
through onto every edge instead of being reconstructed here. That is the whole
reason ingestion attaches provenance once (see `src/ingest/pipeline.py`).

Three rules this module exists to enforce, each of them a measured finding:

- **Rows are a sequence, not a mapping.** Five pages repeat a field name and
  `the_ashen_vanguard.md` carries `Belligerent` three times. `fields[name] = value`
  keeps the last and drops the rest, silently (F-018). Rows keep their index.
- **The infobox is the first pipe table**, not the `## Infobox` section. Six
  pages have no such heading and one of them is hop 2 of `1b_003` (ADR-009).
- **An unmapped field name is reported, not ignored.** A relation the corpus
  expresses under a field nobody mapped is an edge that silently never exists,
  which is indistinguishable from the corpus not asserting it. `Graph.unmapped_fields`
  is printed by the CLI for exactly this reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from src.graph.cells import Reference, leading_verb, parse_cell
from src.graph.entities import canonical_key, display_name
from src.graph.schema import Edge, Graph, Node
from src.ingest.metadata import discover
from src.ingest.pipeline import IngestionResult, ingest
from src.settings import PROJECT_ROOT, get_settings

RELATIONS_PATH = PROJECT_ROOT / "config" / "relations.yaml"

#: A markdown table row: `| field | value |`.
_ROW_RE = re.compile(r"^\|\s*(?P<field>[^|]+?)\s*\|\s*(?P<value>.*?)\s*\|\s*$")

#: Fields that name the page's own subject rather than a relation.
_SELF_FIELDS = frozenset({"Name"})


@dataclass(frozen=True)
class RelationMap:
    """field name -> (relation, direction), plus the fields known to be attributes."""

    forward: dict[str, str]
    reverse: dict[str, str]
    inverses: dict[str, str]
    attributes: frozenset[str]
    #: Lowercased forward field name -> relation, so a verb written *inside* a
    #: cell can be checked against the direction the field name implies.
    verbs: dict[str, str]
    #: relation -> extra *question* vocabulary, from each relation's `cues:` key.
    #: Read only by the cue-based router; the builder never consults it, because
    #: these are not field names and no corpus row is keyed on them.
    question_cues: dict[str, list[str]]

    def lookup(self, field_name: str) -> tuple[str, str] | None:
        """Return (relation, "forward"|"reverse"), or None if not a relation."""
        if field_name in self.forward:
            return self.forward[field_name], "forward"
        if field_name in self.reverse:
            return self.reverse[field_name], "reverse"
        return None

    def states_forward(self, raw: str, relation: str) -> bool:
        """True when the cell's own leading verb asserts `relation` of the subject.

        MEASURED: three cells in the corpus are written `Mentor of [[X]]` under
        the field name `Mentor`, which config maps as *reverse*. The field name
        and the cell disagree, and the cell is the more specific statement -
        "Mentor of X" names the subject as the mentor, whichever way the row is
        labelled. Trusting the field name alone inverted all three edges, and
        `rb_044`'s gold path runs through one of them.

        Deliberately narrow: this fires only when the verb resolves to the *same*
        relation the field name mapped. A cell whose verb names a different
        relation is not a direction disagreement and is left alone.
        """
        verb = leading_verb(raw)
        return verb is not None and self.verbs.get(verb) == relation

    def is_known(self, field_name: str) -> bool:
        return (
            field_name in self.forward
            or field_name in self.reverse
            or field_name in self.attributes
        )


def load_relation_map(path: Path = RELATIONS_PATH) -> RelationMap:
    """Read config/relations.yaml.

    Lives in config rather than code for ADR-005's reason: it is a claim about
    the corpus, and a judge should be able to disagree with one line of it
    without touching Python.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    forward: dict[str, str] = {}
    reverse: dict[str, str] = {}
    inverses: dict[str, str] = {}

    question_cues: dict[str, list[str]] = {}

    for relation, spec in (raw.get("relations") or {}).items():
        inverses[relation] = spec.get("inverse", relation)
        cues = spec.get("cues") or []
        if cues:
            question_cues[relation] = list(cues)
        fields = spec.get("fields") or {}
        for name in fields.get("forward") or []:
            forward[name] = relation
        for name in fields.get("reverse") or []:
            reverse[name] = relation

    return RelationMap(
        forward=forward,
        reverse=reverse,
        inverses=inverses,
        attributes=frozenset(raw.get("attributes") or []),
        verbs={name.lower(): relation for name, relation in forward.items()},
        question_cues=question_cues,
    )


def infobox_rows(text: str) -> list[tuple[str, str]]:
    """Rows of the first pipe table in `text`, in document order.

    Returns a list, never a dict: repeated field names are real (F-018) and the
    row index is provenance. Header and separator rows are dropped.
    """
    rows: list[tuple[str, str]] = []
    started = False
    for line in text.splitlines():
        match = _ROW_RE.match(line.strip())
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


def entity_types(corpus: Path) -> dict[str, str]:
    """Canonical key -> entity type, from the image filename taxonomy.

    Node type is not on the wiki title - only 26 of 95 titles state a category
    (ADR-009). It is on the plate and atmo filenames, which `metadata.py` already
    parses, so it is read from there and never guessed from the page.
    """
    return {
        canonical_key(record.subject_slug): record.category
        for record in discover(corpus)
        if record.subject_slug and record.category
    }


def _first_table_block(units: list) -> tuple[object, str] | None:
    """The first evidence unit whose text contains a pipe table."""
    for unit in units:
        if _has_table(unit.text):
            return unit, unit.text
    return None


def _has_table(text: str) -> bool:
    return any(_ROW_RE.match(line.strip()) for line in text.splitlines())


def build_graph(
    result: IngestionResult | None = None,
    relations: RelationMap | None = None,
) -> Graph:
    """Construct the graph from ingested wiki evidence.

    Args:
        result: Ingestion output. Ingested fresh (from cache) when omitted.
        relations: Field-to-relation map. Loaded from config when omitted.

    Returns:
        A `Graph` whose every edge carries the row it was read from.
    """
    result = result or ingest()
    relations = relations or load_relation_map()
    types = entity_types(get_settings().require_corpus())

    by_doc: dict[str, list] = {}
    for unit in result.evidence:
        if unit.collection == "wiki":
            by_doc.setdefault(unit.canonical_doc_id, []).append(unit)

    # Pass 1: every entity that owns a page, so pass 2 can resolve a plain-text
    # cell against a known name. `the_ashen_vanguard.md` writes its three
    # `Belligerent` rows as unlinked text - "The War of Drowned Light", no
    # brackets - so a link-driven parser reads the page as having no conflicts
    # at all. Resolution is exact match on the canonical key (ADR-011): a name
    # that does not match a known entity produces no edge rather than a guess.
    known: dict[str, str] = {}
    for doc_id, units in sorted(by_doc.items()):
        found = _first_table_block(units)
        if found is None:
            continue
        name = _subject_name(infobox_rows(found[1]), doc_id, units)
        known[canonical_key(name)] = name

    graph = Graph()
    unmapped: dict[str, int] = {}

    for doc_id, units in sorted(by_doc.items()):
        found = _first_table_block(units)
        if found is None:
            continue
        unit, text = found
        rows = infobox_rows(text)

        subject_name = _subject_name(rows, doc_id, units)
        subject_key = canonical_key(subject_name)
        graph.add_node(
            Node(
                key=subject_key,
                name=subject_name,
                entity_type=types.get(subject_key),
                page=doc_id,
            )
        )

        for index, (field_name, value) in enumerate(rows):
            if field_name in _SELF_FIELDS:
                continue

            mapping = relations.lookup(field_name)
            if mapping is None:
                if not relations.is_known(field_name):
                    unmapped[field_name] = unmapped.get(field_name, 0) + 1
                continue

            relation, direction = mapping
            cell = parse_cell(value, link_types=types)

            # The cell's own verb outranks the field name when the two
            # disagree, and the disagreement is counted rather than absorbed
            # (ADR-023). Silently preferring either one is how three mentor_of
            # edges pointed backwards for a week.
            if direction == "reverse" and relations.states_forward(value, relation):
                direction = "forward"
                key = f"{field_name} -> {relation}"
                graph.direction_overrides[key] = (
                    graph.direction_overrides.get(key, 0) + 1
                )

            references = cell.references
            extraction = "link"

            if not references:
                named = _resolve_unlinked(cell, known)
                if not named:
                    continue
                references, extraction = named, "exact_name_match"

            for reference in references:
                target_key = canonical_key(reference.target)
                graph.add_node(
                    Node(
                        key=target_key,
                        name=display_name(reference.target),
                        entity_type=types.get(target_key),
                    )
                )
                source, target = (
                    (subject_key, target_key)
                    if direction == "forward"
                    else (target_key, subject_key)
                )
                graph.add_edge(
                    Edge(
                        source=source,
                        relation=relation,
                        target=target,
                        document=doc_id,
                        field_name=field_name,
                        row=index,
                        raw=value,
                        template=cell.template,
                        tier=unit.tier,
                        assertion="secret" if cell.is_secret else "asserts",
                        year=reference.year,
                        year_kind=reference.year_kind,
                        qualifier=reference.qualifier,
                        inferred_inverse=direction == "reverse",
                        extraction=extraction,
                    )
                )

    graph.unmapped_fields = unmapped
    return graph


def _resolve_unlinked(cell, known: dict[str, str]) -> tuple[Reference, ...]:
    """Resolve a plain-text cell on a relation field against known entity names.

    Only exact matches on the canonical key count, and only for cells that are
    plain literals - never for prose or abstentions, where a matching substring
    would be a coincidence rather than a reference. A value that matches nothing
    yields no edge, which is the honest outcome: the corpus named something we
    do not have a page for.
    """
    if cell.template not in {"literal prose", "literal year", "literal number"}:
        return ()
    if cell.is_abstention:
        return ()

    parts = [p.strip() for p in re.split(r"\s*;\s*", cell.raw) if p.strip()]
    resolved = [p for p in parts if canonical_key(p) in known]
    if len(resolved) != len(parts):
        return ()
    return tuple(Reference(known[canonical_key(p)]) for p in resolved)


def _subject_name(rows: list[tuple[str, str]], doc_id: str, units: list | None = None) -> str:
    """The page's own entity name, in the corpus's own spelling.

    Three sources, in decreasing fidelity:

    1. **The H1 heading.** Present on all 95 wiki pages, and the only source that
       preserves spelling the other two lose - `the_iron_ring_cartel.md` has no
       `Name` row at all, so it previously fell through to the filename and
       became "the iron ring cartel", dropping both the capitals and the hyphen
       the corpus actually writes.
    2. **A `Name`-like infobox row**, for the pages that carry one.
    3. **The filename**, de-slugged. Lossy and last: slugification is one-way, so
       "The Thrice-Bound Edge" cannot be recovered from `the_thrice_bound_edge`.

    The result is passed through `display_name`, which strips `[[ ]]`, `**` and a
    trailing `(type)` disambiguator. That ordering matters: the key is derived
    from this return value, and `canonical_key("Ashfall Colossus (creature)")`
    would otherwise be `ashfall_colossus_creature` - a second node for an entity
    every link calls `[[Ashfall Colossus]]`.
    """
    if units:
        for unit in units:
            if unit.kind == "heading" and unit.text.startswith("# "):
                heading = display_name(unit.text[2:])
                if heading:
                    return heading

    for field_name, value in rows:
        if field_name in _SELF_FIELDS and value.strip():
            return display_name(value)

    return display_name(Path(doc_id).stem.replace("_", " "))


def main() -> None:
    graph = build_graph()
    print(graph.summary())


if __name__ == "__main__":
    main()
