"""Is the answer key narrower than the corpus?

This checker exists because of F-015. A careful human reviewer read `1b_006`,
reported `confidence: high`, and listed **two** valid answers. The corpus
documents **fourteen**. The reviewer was not careless - membership in that faction
is recorded in two disjoint places, 6 names on the faction page's `Members` row
and 8 more on individual character pages with zero overlap, and a human reading
from one direction sees one half. A second human reading the same direction
inherits the same blind spot.

So the mitigation is not another reviewer. It is enumeration that reads **both
directions by construction**, which is what this module does.

INDEPENDENCE - WHY THIS FILE IMPORTS NOTHING FROM src/graph/
-------------------------------------------------------------
Ground truth validated by the system under test is not ground truth. If the graph
generated or confirmed the answer key, the graph would score 100% by
construction and every Checkpoint 2 number would measure nothing.

This module therefore:

- imports no graph module, and uses no graph output, entity set or relation map;
- does not reuse the graph's cell parser, its `relations.yaml`, or its
  canonicalisation;
- reads raw document text through `src/ingest`, which predates the graph and
  supplies document identity and locators for citation.

The field-name families below were written by reading raw corpus field names, not
by consulting `config/relations.yaml`. The two will overlap - they describe the
same corpus - but neither is derived from the other, so agreement between them is
evidence rather than tautology.

WHAT THIS PROVES, AND WHAT IT DOES NOT
---------------------------------------
Enumeration is strong evidence of **recall** failure: if the corpus asserts an
answer the key omits, the key is too narrow and scoring will mark correct answers
wrong. That is the F-015 class and this checker is built for it.

Enumeration is weak evidence of **precision**. It cannot confirm that a key answer
is *right*, only that text supporting it can or cannot be located. A key entry
this checker cannot corroborate is surfaced for a human, never rejected.

Semantic disputes are surfaced, never resolved. Where two documents assert
different values, both are reported with their sources. Enumeration does not
prove truth.

    python -m eval.completeness
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from src.ingest.pipeline import EvidenceUnit, ingest
from src.settings import PROJECT_ROOT

REPORT_PATH = PROJECT_ROOT / "eval" / "verification" / "completeness_report.md"
ANSWER_KEY_PATH = PROJECT_ROOT / "eval" / "answer_key.json"

#: Field-name families, keyed by the relation word an answer-key hop uses.
#: Written by reading the corpus's own field names - deliberately NOT imported
#: from config/relations.yaml, so that agreement between the two is corroboration
#: rather than a tautology. Matching is substring, case-insensitive, so
#: "member" also catches "Members", "Membership" and "Known members".
FIELD_STEMS: dict[str, tuple[str, ...]] = {
    "member_of": ("member", "membership", "affiliat", "allegian", "personnel"),
    "has_member": ("member", "membership", "affiliat", "allegian", "personnel"),
    "victor": ("victor",),
    "victor_of": ("victor",),
    "wields": ("wield", "weapon", "relic"),
    "housed_in": ("hous",),
    "lair_in": ("lair",),
    "ruled_by": ("rule", "ruler", "ruling"),
    "founded": ("found", "establish", "began"),
    "forged": ("forge", "forging"),
}

#: Prose verbs for the same relations, used when the assertion is a sentence
#: rather than an infobox row. 1C answers are years stated in paragraphs.
PROSE_STEMS: dict[str, tuple[str, ...]] = {
    "founded": ("founded", "founding", "established"),
    "forged": ("forged", "forging"),
}

_ROW_RE = re.compile(r"\|\s*(?P<field>[^|\n]+?)\s*\|\s*(?P<value>[^|\n]*?)\s*\|")
_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_YEAR_RE = re.compile(r"\b(\d{2,4})\s*AS\b")
_SPLIT_RE = re.compile(r"\s*[;,]\s*")
_EMPHASIS_RE = re.compile(r"\*+")
#: Sentence boundary, plus the `|` of an infobox row - a table row is its
#: own assertion and must not bleed into the next.
_SENTENCE_RE = re.compile(r"(?<=[.;!?])\s+|\s*\|\s*|\n+")


#: The wiki appends a bracketed category to 26 of its 95 H1 headings -
#: `# The Silent Choir (faction)`. It is part of the heading, not of the name.
#:
#: Leaving it in was the checker's own first bug, and it failed in exactly the
#: direction this module exists to catch. `the_silent_choir.md` normalised to
#: `silent_choir_faction`, which did not match the pivot `silent_choir`, so the
#: faction page was never recognised as the pivot's own page and **Direction A
#: never ran**. Enumeration returned only the 8 character-page members and
#: missed the `Members` row entirely - the same half of the corpus the human
#: reviewer in F-015 missed, for a different reason.
_TYPE_SUFFIX = re.compile(
    r"\s*\((?:character|faction|location|creature|conflict|artifact)\)\s*$", re.I
)


def normalise(name: str) -> str:
    """Loose key for comparing two surface names.

    Deliberately its own implementation rather than the graph's `canonical_key`.
    They will agree on most inputs; that is the point of an independent check.
    """
    text = _EMPHASIS_RE.sub("", _LINK_RE.sub(r"\1", name)).replace("’", "'")
    text = _TYPE_SUFFIX.sub("", text.strip())
    text = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return re.sub(r"^the_", "", text)


@dataclass
class Support:
    """One raw passage backing a candidate answer."""

    document: str
    locator: str
    field_name: str | None
    text: str
    #: "faction_page" (found on the pivot's own page) or "subject_page"
    #: (found on another entity's page, naming the pivot). The distinction is
    #: F-015's entire lesson.
    direction: str

    def cite(self) -> str:
        where = f"{self.document} ({self.locator})"
        if self.field_name:
            where += f" | {self.field_name}"
        return where


@dataclass
class Finding:
    """What enumeration found for one question."""

    qid: str
    question: str
    pivot: str
    relation: str
    key_answers: list[str] = field(default_factory=list)
    discovered: dict[str, list[Support]] = field(default_factory=dict)
    #: Corpus-supported, absent from the key, on a question whose key claims to
    #: enumerate a complete set. The F-015 class.
    missing_from_key: list[str] = field(default_factory=list)
    #: Corpus-supported siblings on a single-answer question. Expected, not a
    #: defect: the question selects one of several true facts by a semantic
    #: constraint the enumerator cannot apply. Surfaced for a human.
    semantic_siblings: list[str] = field(default_factory=list)
    #: Values the key already records as competing claims. Not missing answers.
    known_conflicts: list[str] = field(default_factory=list)
    #: In the key, no supporting passage located. Needs a human, not a verdict.
    unlocated: list[str] = field(default_factory=list)
    #: Competing values for the same slot. Surfaced, never resolved.
    disputes: list[tuple[str, list[Support]]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if self.missing_from_key:
            return "RECALL RISK"
        if self.unlocated:
            return "PRECISION - needs human"
        if self.semantic_siblings or self.disputes:
            return "needs human"
        return "consistent"


def wiki_units(evidence: list[EvidenceUnit]) -> dict[str, list[EvidenceUnit]]:
    by_doc: dict[str, list[EvidenceUnit]] = defaultdict(list)
    for unit in evidence:
        by_doc[unit.canonical_doc_id].append(unit)
    return by_doc


def _rows(text: str) -> list[tuple[str, str]]:
    """Every `| field | value |` pair in a block, in order."""
    out = []
    for match in _ROW_RE.finditer(text):
        field_name, value = match.group("field"), match.group("value")
        if field_name.lower() == "field" or set(field_name) <= set("-: "):
            continue
        out.append((field_name, value))
    return out


def _names_in(value: str, vocabulary: set[str]) -> list[str]:
    """Entity names in a cell: every link, plus plain text matching a known name."""
    names = [n.strip() for n in _LINK_RE.findall(value)]
    if not names:
        for part in _SPLIT_RE.split(_EMPHASIS_RE.sub("", value)):
            part = part.strip()
            if part and normalise(part) in vocabulary:
                names.append(part)
    return names


def build_vocabulary(by_doc: dict[str, list[EvidenceUnit]]) -> dict[str, str]:
    """Known entity names, from wiki page titles and every link target.

    Raw-text derived. No graph involvement: a page's `# Heading` and the
    `[[targets]]` written anywhere in the corpus are both in the source files.
    """
    vocabulary: dict[str, str] = {}
    for doc_id, units in by_doc.items():
        if doc_id.startswith("wiki/"):
            stem = Path(doc_id).stem.replace("_", " ")
            vocabulary.setdefault(normalise(stem), stem)
        for unit in units:
            if unit.kind == "heading" and unit.text.startswith("# "):
                title = unit.text[2:].strip()
                vocabulary.setdefault(normalise(title), title)
            for target in _LINK_RE.findall(unit.text):
                vocabulary.setdefault(normalise(target), target.strip())
    return vocabulary


def enumerate_entity_answers(
    pivot: str,
    relation: str,
    by_doc: dict[str, list[EvidenceUnit]],
    vocabulary: dict[str, str],
) -> dict[str, list[Support]]:
    """Every entity the corpus links to `pivot` under `relation`, both directions.

    Direction A reads the pivot's own page. Direction B reads every other page
    for a row naming the pivot. Running both unconditionally is the whole point:
    F-015 happened because a human ran only one.
    """
    stems = FIELD_STEMS.get(relation, (relation.split("_")[0],))
    pivot_key = normalise(pivot)
    found: dict[str, list[Support]] = defaultdict(list)

    for doc_id, units in sorted(by_doc.items()):
        if not doc_id.startswith("wiki/"):
            continue
        subject = _subject_of(doc_id, units)
        is_pivot_page = normalise(subject) == pivot_key

        for unit in units:
            for field_name, value in _rows(unit.text):
                if not any(s in field_name.lower() for s in stems):
                    continue
                names = _names_in(value, set(vocabulary))

                if is_pivot_page:
                    # Direction A: the pivot's page lists them.
                    for name in names:
                        found[normalise(name)].append(
                            Support(doc_id, unit.locator, field_name, value,
                                    "pivot_page")
                        )
                elif any(normalise(n) == pivot_key for n in names):
                    # Direction B: another page names the pivot, so that page's
                    # own subject is a candidate.
                    found[normalise(subject)].append(
                        Support(doc_id, unit.locator, field_name, value,
                                "subject_page")
                    )
    return dict(found)


def enumerate_value_answers(
    pivot: str,
    relation: str,
    evidence: list[EvidenceUnit],
) -> dict[str, list[Support]]:
    """Every year the corpus asserts for `pivot` under `relation`, any collection.

    1C answers are years stated in prose across chronicles, codex and ephemera,
    and the competing values are the question. Every assertion is collected with
    its source so a human can weigh them; none is chosen here.
    """
    stems = PROSE_STEMS.get(relation, (relation,))
    pivot_words = [w for w in re.split(r"\W+", pivot.lower()) if len(w) > 3]
    found: dict[str, list[Support]] = defaultdict(list)

    for unit in evidence:
        text = _EMPHASIS_RE.sub("", unit.text)
        # Scope to the SENTENCE, not the block. Block scope collected every year
        # in any passage that merely mentioned the entity - a character's `Born`
        # and `Died` rows became candidate founding years for a settlement,
        # because the same infobox happened to name `Edge of Gloamreach`.
        # 12 candidates where 3 were real. A report that noisy gets ignored,
        # which would defeat the point of having one.
        for sentence in _SENTENCE_RE.split(text):
            low = sentence.lower()
            if not all(w in low for w in pivot_words):
                continue
            if not any(s in low for s in stems):
                continue
            for year in _YEAR_RE.findall(sentence):
                found[normalise(f"{year} AS")].append(
                    Support(unit.canonical_doc_id, unit.locator, None,
                            re.sub(r"\s+", " ", sentence).strip()[:200], "prose")
                )
    return dict(found)


def _excerpt(text: str, needle: str, width: int = 150) -> str:
    index = text.find(needle)
    start = max(0, index - width // 2)
    return re.sub(r"\s+", " ", text[start:start + width]).strip()


def _subject_of(doc_id: str, units: list[EvidenceUnit]) -> str:
    for unit in units:
        if unit.kind == "heading" and unit.text.startswith("# "):
            return _LINK_RE.sub(r"\1", unit.text[2:]).strip()
    return Path(doc_id).stem.replace("_", " ")


def check(key: dict, evidence: list[EvidenceUnit]) -> list[Finding]:
    """Run enumeration for every scoreable question."""
    by_doc = wiki_units(evidence)
    vocabulary = build_vocabulary(by_doc)
    findings: list[Finding] = []

    for entry in key["questions"]:
        paths = entry.get("acceptable_paths") or []
        if not paths:
            continue
        last = paths[0]["hops"][-1]
        pivot, relation = last["from"], last["relation"]
        key_answers = [a["answer"] for a in entry["accepted_answers"]]

        finding = Finding(
            qid=entry["qid"],
            question=entry["question"],
            pivot=pivot,
            relation=relation,
            key_answers=key_answers,
        )

        if relation in PROSE_STEMS:
            discovered = enumerate_value_answers(pivot, relation, evidence)
        else:
            discovered = enumerate_entity_answers(pivot, relation, by_doc, vocabulary)

        finding.discovered = discovered

        # A prose answer is a sentence, not an entity - enumeration cannot be
        # compared against it, and pretending otherwise would manufacture a
        # finding. Report what was found and leave the judgement to a human.
        if entry["answer_cardinality"] == "single" and len(key_answers[0].split()) > 8:
            finding.notes.append(
                "Key answer is prose, not an entity. Enumeration lists what the "
                "corpus asserts for this relation; a human must judge the phrasing."
            )
        else:
            key_keys = {normalise(a) for a in key_answers}
            for alias in (al for a in entry["accepted_answers"] for al in a["aliases"]):
                key_keys.add(normalise(alias))

            # Values the key already documents as competing claims are not
            # omissions - the key knows about them and records their stance.
            conflict_keys = {
                normalise(str(claim.get("value")))
                for conflict in entry.get("conflicts", [])
                for claim in conflict.get("claims", [])
                if claim.get("value")
            }

            extras = sorted(k for k in discovered if k not in key_keys)
            finding.known_conflicts = [k for k in extras if k in conflict_keys]
            remaining = [k for k in extras if k not in conflict_keys]

            # The split that stops this checker crying wolf.
            #
            # `any_of` means the key claims to enumerate every valid answer, so
            # anything the corpus supports and the key omits is a real recall
            # defect - 1b_006's shape exactly.
            #
            # `single` means the question selects ONE fact from several that are
            # all true, using a constraint enumeration cannot apply. 1b_007 asks
            # for an *accord*; the Cartel also won The Winter Reckoning and is
            # named victor of The Purge of Blackport. Both are correct facts and
            # neither belongs in the key. Calling those "missing answers" would
            # train the team to ignore this report.
            if entry["answer_cardinality"] == "any_of":
                finding.missing_from_key = remaining
            else:
                finding.semantic_siblings = remaining

            finding.unlocated = sorted(
                a for a in key_answers if normalise(a) not in discovered
            )

        if relation in PROSE_STEMS and len(discovered) > 1:
            finding.disputes = sorted(discovered.items())

        findings.append(finding)

    return findings


def render(findings: list[Finding]) -> str:
    lines = [
        "# Answer-key completeness report",
        "",
        "Generated by `python -m eval.completeness`. Independent of `src/graph/`:",
        "no graph module, entity set or relation map is imported, and the field-name",
        "families are written from raw corpus field names rather than from",
        "`config/relations.yaml`.",
        "",
        "**Enumeration proves recall, not truth.** A `RECALL RISK` means the corpus",
        "appears to support an answer the key omits - the F-015 class, where scoring",
        "would mark correct answers wrong. A `PRECISION` or `DISPUTE` row is a",
        "question for a human, not a verdict.",
        "",
        "| qid | verdict | key | found | missing from key | unlocated |",
        "|---|---|---|---|---|---|",
    ]
    for f in findings:
        lines.append(
            f"| `{f.qid}` | {f.verdict} | {len(f.key_answers)} | {len(f.discovered)} "
            f"| {len(f.missing_from_key)} | {len(f.unlocated)} |"
        )

    for f in findings:
        lines += ["", "---", "", f"## `{f.qid}` - {f.verdict}", "",
                  f"**Question.** {f.question}", "",
                  f"**Enumerated.** `{f.pivot}` --[{f.relation}]-->", ""]
        for note in f.notes:
            lines += [f"> {note}", ""]

        lines.append(f"**Key lists {len(f.key_answers)}:** "
                     + ", ".join(f"`{a}`" for a in f.key_answers[:20]))
        lines.append("")

        if f.discovered:
            lines += [f"**Corpus enumeration found {len(f.discovered)}:**", ""]
            for name, supports in sorted(f.discovered.items()):
                directions = sorted({s.direction for s in supports})
                mark = " **<- NOT IN KEY**" if name in f.missing_from_key else ""
                lines.append(f"- `{name}` ({', '.join(directions)}){mark}")
                for support in supports[:3]:
                    lines.append(f"    - {support.cite()}")
                    lines.append(f"      > {support.text[:160]}")
            lines.append("")

        if f.missing_from_key:
            lines += ["**RECALL RISK - corpus supports, key omits:**", "",
                      "The key declares `any_of`, so it claims to list every valid",
                      "answer. These would be scored wrong today.", ""]
            lines += [f"- `{n}`" for n in f.missing_from_key] + [""]

        if f.semantic_siblings:
            lines += ["**Semantic siblings - true facts the question excludes:**", "",
                      "Single-answer question. These are correct statements the",
                      "question's own wording rules out; enumeration cannot apply that",
                      "filter and does not try. Confirm the key picked the right one.", ""]
            lines += [f"- `{n}`" for n in f.semantic_siblings] + [""]

        if f.known_conflicts:
            lines += ["**Already recorded as competing claims in the key:**", ""]
            lines += [f"- `{n}`" for n in f.known_conflicts] + [""]

        if f.unlocated:
            lines += ["**PRECISION - key asserts, enumeration could not locate:**", "",
                      "Not a rejection. Enumeration reads infobox rows and named prose;",
                      "an answer stated only in narrative will not be found here.", ""]
            lines += [f"- `{a}`" for a in f.unlocated] + [""]

        if f.disputes:
            lines += ["**DISPUTE - competing values, for human adjudication:**", ""]
            for value, supports in f.disputes:
                lines.append(f"- `{value}` - {len(supports)} source(s)")
                for support in supports[:4]:
                    lines.append(f"    - {support.cite()}")
            lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    key = json.loads(ANSWER_KEY_PATH.read_text(encoding="utf-8"))
    findings = check(key, ingest().evidence)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render(findings), encoding="utf-8")

    recall = [f for f in findings if f.missing_from_key]
    precision = [f for f in findings if f.unlocated]
    disputes = [f for f in findings if f.disputes]

    print(f"questions checked     : {len(findings)}")
    print(f"RECALL RISK           : {len(recall)}  {[f.qid for f in recall]}")
    print(f"PRECISION, needs human: {len(precision)}  {[f.qid for f in precision]}")
    print(f"DISPUTES, needs human : {len(disputes)}  {[f.qid for f in disputes]}")
    print(f"\nreport: {REPORT_PATH}")
    return 1 if recall else 0


if __name__ == "__main__":
    raise SystemExit(main())
