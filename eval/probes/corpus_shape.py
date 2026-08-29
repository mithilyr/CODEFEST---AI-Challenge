"""Pressure tests run against the corpus before the graph builder was written.

Every number quoted in ADR-009 through ADR-012 is produced here. Run it and the
claims either reproduce or they do not:

    python -m eval.probes.corpus_shape

This is deliberately a *probe*, not a component. It re-parses the wiki with a
throwaway parser so the measurements stay independent of whatever src/graph/
eventually does - a probe that shares code with the thing it measures cannot
contradict it, which is the only reason to run one.
"""

from __future__ import annotations

import collections
import difflib
import re
from pathlib import Path

from src.settings import get_settings

ROW_RE = re.compile(r"^\|\s*(?P<field>[^|]+?)\s*\|\s*(?P<value>.*?)\s*\|\s*$")
TITLE_RE = re.compile(r"^#\s+(?P<rest>.+?)\s*$", re.M)
LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
CATEGORIES = frozenset(
    {"character", "faction", "location", "creature", "conflict", "artifact"}
)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def normalise(name: str) -> str:
    """Slug with a leading article dropped, so 'Iron-Ring Cartel' and 'The
    Iron-Ring Cartel' are one node. Measured safe: it merges exactly 5 pairs,
    each genuinely the same entity, and collides nothing else.
    """
    return re.sub(r"^the_", "", slugify(name))


def wiki_pages(corpus: Path) -> list[tuple[str, str]]:
    return [
        (p.name, p.read_text(encoding="utf-8"))
        for p in sorted((corpus / "wiki").glob("*.md"))
    ]


def infobox_rows(text: str) -> list[tuple[str, str]]:
    """Rows of the first pipe table in the file.

    Keyed on the *first table*, not on a '## Infobox' heading: six wiki pages
    carry the table with no such heading, and three of those are artifact pages
    that dev questions 1b_003 and 1c_003 traverse.
    """
    rows: list[tuple[str, str]] = []
    started = False
    for line in text.splitlines():
        match = ROW_RE.match(line.strip())
        if not match:
            if started:
                break
            continue
        started = True
        field, value = match.group("field"), match.group("value")
        if field == "Field" or set(field) <= set("-: "):
            continue
        rows.append((field, value))
    return rows


def cell_shape(value: str) -> str:
    """Classify a cell into the closed set of templates the corpus actually uses."""
    if re.search(
        r"contested|consult|not recorded|unrecorded|no canonical|none recorded"
        r"|no year|no physical|disputed",
        value,
        re.I,
    ):
        return "abstention"

    text = LINK_RE.sub("L", value.strip())
    text = re.sub(r"\bthe\s+L\b", "L", text, flags=re.I)
    text = re.sub(r"\b\d+\s*AS\b", "Y", text)
    text = re.sub(r"\s+", " ", text).strip()

    if text == "L":
        return "bare link"
    if re.fullmatch(r"L(; L)+", text) or re.fullmatch(r"L(, L)+", text):
        return "link list"
    if re.fullmatch(r"L,? since Y", text):
        return "link + since-qualifier"
    if re.fullmatch(
        r"(Commands|Wields|Serves at|Rules|Member of|Mentor of|Rival of) L,?( since Y)?",
        text,
        re.I,
    ):
        return "verb + link"
    if re.fullmatch(r"Fought (in|for) L,?( fighting)? (for|in) L", text, re.I):
        return "two-argument clause"
    if re.fullmatch(r"L,? in Y(; L,? in Y)*", text):
        return "link + year pairs"
    if re.fullmatch(r"(Waged at|Devastated) L,? in Y(; L,? in Y)*", text, re.I):
        return "link + year pairs"
    if re.fullmatch(r"L serves at .+", text, re.I):
        return "two-argument clause"
    if re.fullmatch(
        r"(Secretly sells intelligence to|Swore a hidden oath to"
        r"|Unacknowledged heir to|Unleashed in) L",
        text,
        re.I,
    ):
        return "secret / association relation"
    if "L" not in text:
        if re.fullmatch(r"-?\d[\d,]*", text):
            return "literal number"
        if re.fullmatch(r"Y", text):
            return "literal year"
        return "literal prose"
    return "prose containing an incidental link"


def report_structure(corpus: Path) -> None:
    pages = wiki_pages(corpus)
    no_heading: list[str] = []
    with_category = 0
    cells: list[tuple[str, str, str]] = []
    fields: collections.Counter[str] = collections.Counter()

    for name, text in pages:
        if "## Infobox" not in text:
            no_heading.append(name)
        title = TITLE_RE.search(text)
        raw = title.group("rest") if title else name
        match = re.search(r"\(([a-z_]+)\)\s*$", raw)
        if match and match.group(1) in CATEGORIES:
            with_category += 1
        for field, value in infobox_rows(text):
            fields[field] += 1
            cells.append((name, field, value))

    print("=" * 72)
    print("PT-1  wiki structure")
    print("=" * 72)
    print(f"  wiki pages                          : {len(pages)}")
    print(f"  infobox cells                       : {len(cells)}")
    print(f"  distinct infobox field names        : {len(fields)}")
    print(f"  pages WITHOUT a '## Infobox' heading: {len(no_heading)}")
    for name in no_heading:
        print(f"      {name}")
    print(f"  pages whose title states a category : {with_category}/{len(pages)}")
    print("      -> node type cannot be read off the wiki title")

    shapes = collections.Counter(cell_shape(v) for _, _, v in cells)
    print("\n  infobox cell templates (the whole job of the cell parser):")
    for shape, count in shapes.most_common():
        print(f"      {count:4d}  ({100 * count / len(cells):5.1f}%)  {shape}")
    print(f"      -> {len(shapes)} templates cover all {len(cells)} cells")

    print("\n  cells whose value carries TWO entities (a ternary fact):")
    for name, field, value in cells:
        if cell_shape(value) == "two-argument clause":
            print(f"      wiki/{name} | {field} | {value}")
    print("      -> 'Fought in X for Y' must not become two edges from one subject")


def report_entities(corpus: Path) -> None:
    names: set[str] = set()
    for name, text in wiki_pages(corpus):
        title = TITLE_RE.search(text)
        raw = title.group("rest") if title else name
        raw = re.sub(r"\s*\([a-z_]+\)\s*$", "", raw)
        names.add(normalise(LINK_RE.sub(r"\1", raw)))
        for _, value in infobox_rows(text):
            for link in LINK_RE.findall(value):
                names.add(normalise(link))
    names = {n for n in names if n and not re.fullmatch(r"\d+_as", n)}

    print("\n" + "=" * 72)
    print("PT-9  entity resolution: how adversarial is the name space?")
    print("=" * 72)
    print(f"  distinct entity names: {len(names)}")

    given: dict[str, list[str]] = collections.defaultdict(list)
    family: dict[str, list[str]] = collections.defaultdict(list)
    for entity in names:
        parts = entity.split("_")
        if len(parts) < 2:
            continue
        given[parts[0]].append(entity)
        family[parts[1]].append(entity)

    shared_given = {k: v for k, v in given.items() if len(v) > 1}
    shared_family = {k: v for k, v in family.items() if len(v) > 1 and k != "of"}
    print(f"  given names shared by >1 entity : {len(shared_given)}")
    print(f"  surnames shared by >1 entity    : {len(shared_family)}")
    for key, group in sorted(shared_family.items(), key=lambda kv: -len(kv[1]))[:5]:
        print(f"      '{key}' x{len(group)}: {sorted(group)}")

    ordered = sorted(names)
    close = []
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            ratio = difflib.SequenceMatcher(None, a, b).ratio()
            if ratio >= 0.80:
                close.append((round(ratio, 3), a, b))
    close.sort(reverse=True)
    print(f"  DISTINCT entity pairs >= 0.80 similar: {len(close)}")
    for ratio, a, b in close:
        print(f"      {ratio}  {a}  ~  {b}")
    print("      -> fuzzy matching must never silently pick a winner here")


#: An entity name may contain lowercase connectives - "Edge of Gloamreach",
#: "The Purge of Blackport" - but must begin and end on a capitalised word.
#: Getting this wrong silently truncates "Edge of Gloamreach" to "Gloamreach"
#: and files that artifact's forging date against the *settlement*.
_ENT = r"[A-Z][\w'\-]*(?:[ \-](?:of|the|and|[A-Z][\w'\-]*))*[\w'\-]"

#: A claim is counted only when the entity is the grammatical *subject* of the
#: dated statement. Proximity windows manufacture conflicts: a 140-character
#: window attributed Hollowvale's founding year to Vharencrag Fortress purely
#: because both are named in one decree.
CLAIM_RE = re.compile(
    r"(?P<ent>" + _ENT + r")"
    r"(?:'s\s+(?P<a1>founded|forged)\s+(?:year\s+)?is"
    r"|\s*[-–]\s*(?P<a2>founded|forged):"
    r"|\s+(?:was|were)\s+(?P<a3>founded|forged)\s+in)"
    r"\s+(?P<year>\d{1,4})\s*AS"
)

#: The same claim with an anaphoric subject - "Its forged year is 360 AS".
#: The ephemera decoys overwhelmingly take this form, so a purely
#: subject-anchored extractor under-detects exactly the conflicts that matter.
ANAPHORIC_RE = re.compile(
    r"\b(?:Its|its)\s+(?P<attr>founded|forged|forging)\s+(?:year|date)?\s*is"
    r"\s+(?P<year>\d{1,4})\s*AS"
)

#: Ephemera wrap their load-bearing values in Markdown emphasis - "founded in
#: **286 AS**" - while the codex writes them bare. Every competing claim in the
#: corpus is emphasised and every authoritative one is not, so an extractor that
#: does not strip emphasis sees zero conflicts and reports full confidence.
#: Silent under-detection, which is the worst failure this layer can have.
EMPHASIS_RE = re.compile(r"\*{1,3}|_{2,3}|`")


def strip_emphasis(text: str) -> str:
    return EMPHASIS_RE.sub("", text)

ANNOUNCE_RE = re.compile(
    r"popular accounts wrongly claim|authoritative record states plainly"
    r"|founding record is exact|such accounts are rejected"
    r"|correction is authoritative|authoritative founding record",
    re.I,
)


def known_entities(corpus: Path) -> set[str]:
    """Every name the wiki treats as an entity - page titles and link targets."""
    names: set[str] = set()
    for name, text in wiki_pages(corpus):
        title = TITLE_RE.search(text)
        raw = re.sub(r"\s*\([a-z_]+\)\s*$", "", title.group("rest") if title else name)
        names.add(normalise(LINK_RE.sub(r"\1", raw)))
        for _, value in infobox_rows(text):
            for link in LINK_RE.findall(value):
                names.add(normalise(link))
    return {n for n in names if n and not re.fullmatch(r"\d+_as", n)}


def _collect(evidence, use_anaphora: bool, entities: set[str]) -> dict[tuple[str, str], list[dict]]:
    claims: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)

    def add(entity: str, attr: str, year: str, unit) -> None:
        if len(entity) < 5:
            return
        claims[(entity, attr)].append(
            {
                "value": f"{year} AS",
                "tier": unit.tier,
                "collection": unit.collection,
                "doc": unit.canonical_doc_id,
                "announced": bool(ANNOUNCE_RE.search(unit.text)),
            }
        )

    for unit in evidence:
        text = strip_emphasis(unit.text)
        for match in CLAIM_RE.finditer(text):
            attr = match.group("a1") or match.group("a2") or match.group("a3")
            add(normalise(match.group("ent")), attr, match.group("year"), unit)
        if not use_anaphora:
            continue
        for match in ANAPHORIC_RE.finditer(text):
            attr = "forged" if match.group("attr").startswith("forg") else "founded"
            # Nearest preceding mention of a KNOWN entity - not the filename
            # subject, and not merely the nearest capitalised phrase. Two
            # measured failures rule those out: the sermon "concerning Malchior
            # Cindervale" says "Its forged year is 360 AS" about the Gauntlet of
            # Sorrowfell, so the filename subject is wrong; and the sentence
            # before "Its forged year is 354 AS" ends on "the Sundering", so the
            # nearest capitalised phrase is wrong too. Both file a real claim
            # against the wrong entity - a wrong answer that looks well sourced.
            preceding = [
                m.group(0)
                for m in re.finditer(_ENT, text[: match.start()])
                if normalise(m.group(0)) in entities
            ]
            if not preceding:
                continue
            add(normalise(preceding[-1]), attr, match.group("year"), unit)
    return claims


def report_conflicts(corpus: Path) -> None:
    from src.ingest.pipeline import ingest_cached

    result = ingest_cached()
    entities = known_entities(corpus)

    strict = _collect(result.evidence, False, entities)
    resolved = _collect(result.evidence, True, entities)
    strict_contested = {k: v for k, v in strict.items() if len({c["value"] for c in v}) > 1}
    claims = resolved
    contested = {k: v for k, v in claims.items() if len({c["value"] for c in v}) > 1}

    print("\n" + "=" * 72)
    print("PT-2/PT-3  conflict surface, structure-anchored")
    print("=" * 72)
    print("  extraction strategy comparison (contested keys found):")
    print(f"      subject-anchored only              : {len(strict_contested)}")
    print(f"      + entity-resolved anaphora         : {len(contested)}")
    print("      -> the decoys are anaphoric and emphasised; both must be handled")
    print(f"\n  claim keys carrying a dated claim : {len(claims)}")
    print(f"  contested keys                    : {len(contested)}")

    decided_by_tier = 0
    announced = 0
    for key, records in sorted(contested.items()):
        by_value: dict[str, dict] = {}
        for record in records:
            slot = by_value.setdefault(
                record["value"], {"tier": 99, "docs": set(), "announced": False}
            )
            slot["tier"] = min(slot["tier"], record["tier"])
            slot["docs"].add(record["doc"])
            if record["tier"] == 1 and record["announced"]:
                slot["announced"] = True
        best = min(slot["tier"] for slot in by_value.values())
        winners = [value for value, slot in by_value.items() if slot["tier"] == best]
        unique = len(winners) == 1
        decided_by_tier += unique
        was_announced = unique and by_value[winners[0]]["announced"]
        announced += was_announced
        print(
            f"\n  {key[0]}.{key[1]}"
            f"   {'tier-decided' if unique else 'TIE'}"
            f"   {'announced' if was_announced else 'silent'}"
        )
        for value, slot in sorted(by_value.items(), key=lambda kv: kv[1]["tier"]):
            print(f"      {value:8s} tier {slot['tier']}  docs={len(slot['docs'])}")

    print(f"\n  decided by a unique lowest tier  : {decided_by_tier}/{len(contested)}")
    print(f"  of those, the codex announces it : {announced}/{decided_by_tier}")


def main() -> None:
    corpus = get_settings().require_corpus()
    report_structure(corpus)
    report_entities(corpus)
    report_conflicts(corpus)


if __name__ == "__main__":
    main()
