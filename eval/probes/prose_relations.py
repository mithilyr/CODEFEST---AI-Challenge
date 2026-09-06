"""Do the non-wiki collections assert relations no infobox row expresses?

THE QUESTION THIS EXISTS TO ANSWER
------------------------------------
Three measurements bracket this and none of them answers it:

- **ADR-027** measured *existing edges*: 255 of 261 are named by a codex,
  chronicle or ephemera passage. That is about edges the wiki already built.
- **ADR-030/032** measured the *node set*: 78 of 79 declared document subjects
  reach a graph node, the 79th a corpus filename truncation, so **0 genuine
  unreachable entities**. That is about nodes, not about the relations between
  them.
- ADR-027 also cited a 2 Sep argument that "the 4 wrong answers name only wiki
  pages in `required_evidence`" - and ADR-030 recorded that this is partly
  circular, because `required_evidence` was itself derived from the wiki-built
  graph.

So the question left open is the one in between: **a relation asserted in
codex, chronicle or ephemera prose, for which no infobox row produced an edge.**
If a population of those exists, the graph is missing facts the corpus states
plainly, and sub-track 1B's "connect related information across the whole
document set" is not fully served. If it does not, the wiki bounds the relation
set the way ADR-030 showed it bounds the node set.

This probe measures that population. It is READ ONLY: it builds nothing, and it
modifies neither the graph nor any evidence unit.

METHOD, AND WHAT IT DELIBERATELY REFUSES TO DO
------------------------------------------------
For each non-wiki evidence unit, split into sentences, find every gazetteer
surface form in each sentence, and look for one of the verb patterns below
between two resolved entities. Emit a candidate `(subject, relation, object)`
with the sentence and its provenance.

Three constraints, inherited rather than invented:

- **Exact resolution only.** The scan reuses `corroborate.scan_surfaces`, which
  is `route.py`'s gazetteer, so the surface forms are byte-identical to the ones
  the answer path recognises. ADR-011 forbids fuzzy resolution from picking a
  winner and a probe may not quietly do what the product refuses to.
- **An ambiguous surface is dropped, not guessed.** Same rule, same reason as
  ADR-027.
- **A verb pattern is a claim about the corpus, so it is listed, not inferred.**
  Every pattern below maps to a relation `config/relations.yaml` already
  defines. The probe never invents a relation name, because an edge under a
  relation nothing else uses is an edge no template can traverse.

The output classifies every candidate against the built graph:

    CONFIRMS      the edge already exists - prose restating an infobox row
    NEW           no such edge - the population this probe exists to count
    INVERTED      the reverse edge exists (subject/object swapped)

`NEW` is the only interesting bucket, and it is reported with its sentences so
that a human can hand-check it. **A candidate is not a fact.** Regular
expressions over narrative prose produce false positives; ADR-030's hand-check
found 0 of 15 sampled spans were genuine, and the same discipline applies here.
The headline number of this probe is the *hand-checked* one, not the raw count.

    python -m eval.probes.prose_relations
    python -m eval.probes.prose_relations --sample 20
"""

from __future__ import annotations

import argparse
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from src.graph.build import build_graph
from src.graph.corroborate import CORROBORATING_COLLECTIONS, scan_surfaces
from src.graph.schema import Graph
from src.ingest.pipeline import EvidenceUnit, ingest

#: Sentence boundaries. Deliberately crude: the corpus writes plain declarative
#: prose, and a full sentence splitter would be a dependency for no measured
#: gain. A missed boundary costs a candidate, never a wrong one, because both
#: entities must still be found inside whatever span results.
_SENTENCE_RE = re.compile(r"(?<=[.;:!?])\s+|\n+")

#: Verb patterns -> (relation, direction).
#:
#: `forward` means the entity BEFORE the verb is the edge's source:
#:     "Blackford is ruled by The Bleeding Crown"  -> blackford ruled_by crown
#: `reverse` means the entity before the verb is the edge's TARGET:
#:     "The Winter Reckoning was won by The Silent Choir" -> choir victor_of reckoning
#:
#: Every relation named here is defined in config/relations.yaml. Twelve
#: patterns, covering the ten relations the corpus states in prose at all - the
#: remaining three (concealed_tie_to, rival_of, devastated) are recorded only in
#: infobox rows and are deliberately absent rather than guessed at.
_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\bis (?:currently )?ruled by\b|\bwas ruled by\b|\bruled by\b", re.I), "ruled_by", "forward"),
    (re.compile(r"\blairs? (?:in|within|beneath)\b|\bmakes its lair in\b", re.I), "lair_in", "forward"),
    (re.compile(r"\bis housed (?:in|at)\b|\bwas housed (?:in|at)\b|\bhoused (?:in|at)\b", re.I), "housed_in", "forward"),
    (re.compile(r"\bwas forged (?:at|in)\b|\bis forged (?:at|in)\b|\bforged (?:at|in)\b", re.I), "forged_at", "forward"),
    (re.compile(r"\bserves at\b|\bserved at\b|\bis stationed at\b", re.I), "serves_at", "forward"),
    (re.compile(r"\bis a member of\b|\bwas a member of\b|\bbelongs to\b|\bbelonged to\b", re.I), "member_of", "forward"),
    (re.compile(r"\bis (?:the )?victor of\b|\bwas (?:the )?victor of\b|\bvictor of\b", re.I), "victor_of", "forward"),
    (re.compile(r"\bwas won by\b|\bwere won by\b|\bwas ultimately won by\b", re.I), "victor_of", "reverse"),
    (re.compile(r"\bis a core location of\b|\blies (?:in|within)\b|\bis situated (?:in|within)\b", re.I), "in_region", "forward"),
    (re.compile(r"\bwas mentor to\b|\bis mentor to\b|\bmentored\b", re.I), "mentor_of", "forward"),
    # NOT `bore|bears|carried`. Measured: "Gloamreach bears the pallid, bleak
    # character of the Pale Coast" is not a wielding, and the v1 pass emitted it
    # as `gloamreach wields pale_coast` with a tier-4 citation attached. A
    # polysemous verb produces a confident wrong edge, which is worse than no
    # edge - the same trade ADR-011 makes for fuzzy names.
    (re.compile(r"\bwields\b", re.I), "wields", "forward"),
    (re.compile(r"\bfought (?:in|at)\b|\bfought for\b", re.I), "belligerent_in", "forward"),
]

#: A pronoun between the candidate subject and the verb means the clause's real
#: subject is an anaphor this probe cannot resolve. MEASURED: "He is a member of
#: House Morvain and serves at Marrowwatch" yielded `house_morvain serves_at
#: marrowwatch` - the nearest entity to the left of the verb is not the subject
#: of it. That is F-009's lesson (resolving anaphora by proximity) in a new
#: place, and the honest response is to decline the candidate.
_PRONOUN_RE = re.compile(r"\b(?:he|she|it|they|him|her|them|his|hers|their|who|which|that|whose)\b", re.I)

#: A coordinating conjunction between the candidate subject and the verb means
#: the verb heads a second predicate whose subject is earlier in the sentence.
#: MEASURED: "Halvard Cindervale is a member of The Ashen Vanguard and serves at
#: Fenthrone" yielded `ashen_vanguard serves_at fenthrone`. The subject of
#: "serves at" is Halvard; the nearest-left entity is the object of the *first*
#: predicate. Twelve of the corpus's conjoined clauses take this shape.
_CONJUNCTION_RE = re.compile(r"\b(?:and|but|while|though|whereas)\b|,", re.I)

#: How far after the verb the object may sit. MEASURED: "The Psalter of Seven
#: Sorrows had been forged in 119 AS, long before the present court, long before
#: the liege whose death Maelis had arranged, long before Maelis Harrowick the
#: Pale had learned..." put a person 120 characters past the verb and yielded
#: `psalter forged_at maelis_harrowick_the_pale`. The real object is a year,
#: which is not an entity, so the correct behaviour is to find nothing.
_OBJECT_WINDOW = 40


@dataclass(frozen=True)
class Candidate:
    """One prose sentence asserting a relation between two resolved entities."""

    subject_key: str
    relation: str
    object_key: str
    document: str
    collection: str
    locator: str
    tier: int
    sentence: str
    verdict: str = ""


def _mentions(sentence: str, pattern: re.Pattern[str], surface_to_key: dict[str, str]):
    """[(start, end, node key)] for every gazetteer surface form in `sentence`."""
    found = []
    for match in pattern.finditer(sentence):
        key = surface_to_key.get(match.group(0).lower())
        if key is not None:
            found.append((match.start(), match.end(), key))
    return found


def extract(graph: Graph, evidence: list[EvidenceUnit]) -> list[Candidate]:
    """Every prose-asserted relation candidate in the non-wiki collections."""
    surface_pattern, surface_to_key, _ambiguous = scan_surfaces(graph)
    candidates: list[Candidate] = []

    for unit in evidence:
        if unit.collection not in CORROBORATING_COLLECTIONS:
            continue
        text = unit.text or ""
        if not text:
            continue
        for sentence in _SENTENCE_RE.split(text):
            sentence = " ".join(sentence.split())
            if len(sentence) < 12:
                continue
            found = _mentions(sentence, surface_pattern, surface_to_key)
            if len(found) < 2:
                continue
            for verb_re, relation, direction in _PATTERNS:
                for verb in verb_re.finditer(sentence):
                    before = [m for m in found if m[1] <= verb.start()]
                    after = [m for m in found if m[0] >= verb.end()]
                    if not before or not after:
                        continue

                    # Three guards, each one a measured v1 failure mode. Every
                    # one of them DECLINES a candidate rather than repairing it,
                    # which is the same rule the answer path follows: a repaired
                    # guess is a guess wearing a fact's clothes.
                    gap = sentence[before[-1][1] : verb.start()]
                    if _PRONOUN_RE.search(gap):
                        continue          # anaphoric subject - cannot resolve
                    if _CONJUNCTION_RE.search(gap):
                        continue          # verb heads a second predicate
                    if after[0][0] - verb.end() > _OBJECT_WINDOW:
                        continue          # object too distant to be the object

                    left = before[-1][2]   # nearest entity to the left
                    right = after[0][2]    # nearest entity to the right
                    if left == right:
                        continue
                    subject, obj = (left, right) if direction == "forward" else (right, left)
                    candidates.append(
                        Candidate(
                            subject_key=subject,
                            relation=relation,
                            object_key=obj,
                            document=unit.canonical_doc_id,
                            collection=unit.collection,
                            locator=unit.locator,
                            tier=unit.tier,
                            sentence=sentence[:300],
                        )
                    )
    return candidates


def classify(graph: Graph, candidates: list[Candidate]) -> list[Candidate]:
    """Label each candidate CONFIRMS / INVERTED / NEW against the built graph."""
    existing = {(e.source, e.relation, e.target) for e in graph.edges}
    out = []
    for c in candidates:
        if (c.subject_key, c.relation, c.object_key) in existing:
            verdict = "CONFIRMS"
        elif (c.object_key, c.relation, c.subject_key) in existing:
            verdict = "INVERTED"
        else:
            verdict = "NEW"
        out.append(Candidate(**{**c.__dict__, "verdict": verdict}))
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", type=int, default=15,
                        help="how many NEW candidates to print for hand-checking")
    parser.add_argument("--seed", type=int, default=20260906,
                        help="fixed so the sample is the same one forever")
    args = parser.parse_args(argv)

    print("building graph and ingesting corpus ...")
    graph = build_graph()
    result = ingest()
    print(f"  {len(graph.nodes)} entities, {len(graph.edges)} edges")

    candidates = classify(graph, extract(graph, result.evidence))

    verdicts = Counter(c.verdict for c in candidates)
    print("\nprose relation candidates in codex / chronicles / ephemera")
    print(f"  total raw candidates : {len(candidates)}")
    for verdict in ("CONFIRMS", "INVERTED", "NEW"):
        print(f"    {verdict:9} : {verdicts.get(verdict, 0)}")

    new = [c for c in candidates if c.verdict == "NEW"]
    distinct = {(c.subject_key, c.relation, c.object_key) for c in new}
    print(f"\n  distinct NEW triples : {len(distinct)}")

    by_collection = Counter(c.collection for c in new)
    by_relation = Counter(c.relation for c in new)
    print(f"  by collection        : {dict(by_collection)}")
    print(f"  by relation          : {dict(by_relation)}")

    print(f"\nsample of {args.sample} distinct NEW triples, for hand-checking")
    print("(a candidate is not a fact - regexes over narrative produce false")
    print(" positives, and the headline number is the hand-checked one)\n")
    seen: dict[tuple[str, str, str], Candidate] = {}
    for c in new:
        seen.setdefault((c.subject_key, c.relation, c.object_key), c)
    rows = sorted(seen.values(), key=lambda c: (c.subject_key, c.relation, c.object_key))
    random.Random(args.seed).shuffle(rows)
    for c in rows[: args.sample]:
        print(f"  {c.subject_key} --{c.relation}--> {c.object_key}")
        print(f"     tier {c.tier}  {c.collection}/{c.document}  {c.locator}")
        print(f"     \"{c.sentence[:190]}\"")
        print()


if __name__ == "__main__":
    main()
