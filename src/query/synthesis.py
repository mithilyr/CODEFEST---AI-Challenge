"""Turn a verified answer into a sentence. Phrasing only - never retrieval.

THE BOUNDARY, AND WHY IT IS ABSOLUTE
--------------------------------------
By the time this module runs, the reasoning is finished. A routing tier found
the chain, traversal walked it, the type filter ran, and any same-tier conflict
was detected. This module's entire job is to render that into English.

    graph -> query engine -> verified evidence package -> [here] -> prose

The model is handed the chain and forbidden from adding to it. It cannot query
the graph, cannot see the corpus, and cannot reach any tool. Its input is a
list of hops that were already checked; anything it says beyond them is
hallucination with no path into the evidence trail, which is why the trail is
always rendered alongside the prose and never replaced by it.

PROVENANCE IS A FIELD, NOT A FOOTNOTE
---------------------------------------
`Synthesis.phrasing` records which path produced the text:

    "model"     an LLM phrased it from the verified chain
    "template"  a deterministic sentence built from the same chain
    "none"      nothing was found to phrase

CLAUDE.md requires every LLM fallback to be counted, and this is how the report
can say what fraction of demo answers actually needed a model. It is also the
honest answer to a judge asking "did the AI write this": for a keyless run the
answer is no, and the field proves it.

The template path is not a degraded mode bolted on for CI. It is the default
whenever no key is configured, it uses the identical evidence, and it is what
the demo runs on if the network is down - which is the scenario CLAUDE.md's
"never record the demo against a cold cache" rule exists to survive.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.graph.schema import Graph
from src.graph.traverse import Path
from src.query.engine import Answer
from src.query.evidence import EvidenceStatus

_INSTRUCTIONS = (
    "You are phrasing an answer that has ALREADY been verified. Write one or "
    "two plain sentences that state the answer.\n"
    "Do NOT cite sources, file names or field names. Every hop's document is "
    "displayed beneath your sentence with its exact row, so repeating it makes "
    "the sentence unreadable without making it more checkable.\n"
    "Rules you must not break:\n"
    "- Do not add any fact that is not in the chain below.\n"
    "- Do not infer a connection between two facts unless the chain states it.\n"
    "- Do not soften or resolve a disagreement; if one is listed, say plainly "
    "that the sources disagree.\n"
    "- If the chain does not support a confident answer, say so.\n"
    "- If several endpoints are listed as answers, name EVERY one of them. "
    "Naming a few and stopping presents one answer as the answer."
)

#: Statuses whose *whole point* is that the sources disagree. The prompt gets
#: an explicit instruction for these, because a model asked to write a clean
#: sentence will otherwise pick a side - which is the one thing `1b_009` exists
#: to stop us doing.
_CONFLICT_STATUSES = frozenset({EvidenceStatus.CONFLICTING_EVIDENCE})


@dataclass(frozen=True)
class Synthesis:
    """A phrased answer, with the provenance of the phrasing itself."""

    text: str
    #: "model" | "template" | "none"
    phrasing: str
    model: str | None = None

    @property
    def used_a_model(self) -> bool:
        return self.phrasing == "model"


def _hops(path: Path, graph: Graph) -> list[dict]:
    current = path.start
    out = []
    for edge in path.edges:
        nxt = edge.target if edge.source == current else edge.source
        out.append(
            {
                "from": graph.nodes[current].name if current in graph.nodes else current,
                "relation": edge.relation,
                "to": graph.nodes[nxt].name if nxt in graph.nodes else nxt,
                "document": edge.document,
                "field": edge.field_name,
            }
        )
        current = nxt
    return out


#: How each relation reads in a sentence, in the direction the chain walks it.
#:
#: `(forward, reverse)`. Forward phrases an edge `A --[r]--> B` as "A <p> B";
#: reverse phrases the same edge walked from B as "B <p> A". Both are needed
#: because traversal is bidirectional by necessity - the corpus is asymmetric,
#: and `1b_006` walks `victor_of` backwards from the war to the faction that
#: won it (ADR-016).
#:
#: This is phrasing vocabulary and nothing else. It cannot affect what is
#: retrieved, which relation is walked, or which endpoint is returned - by the
#: time this module runs all of that is decided. It is kept here rather than in
#: `config/relations.yaml` for exactly that reason: `cues:` in config change
#: what gets *answered* (ADR-024) and deserve a judge's eye, whereas these
#: change only how a finished answer is worded. Completeness against the live
#: graph is pinned by `test_every_relation_in_the_graph_has_a_phrase`.
_PHRASES: dict[str, tuple[str, str]] = {
    "belligerent_in": ("fought in", "had as a belligerent"),
    "concealed_tie_to": ("has a concealed tie to", "is the concealed tie of"),
    "devastated": ("devastated", "was devastated by"),
    "forged_at": ("was forged at", "is the forging place of"),
    "housed_in": ("is housed in", "houses"),
    "in_region": ("lies in", "contains"),
    "lair_in": ("has its lair in", "is the lair of"),
    "member_of": ("is a member of", "counts among its members"),
    "mentor_of": ("is a mentor of", "was mentored by"),
    "rival_of": ("is a rival of", "is a rival of"),
    "ruled_by": ("is ruled by", "rules"),
    "serves_at": ("serves at", "is served by"),
    "victor_of": ("is named victor of", "was won by"),
    "waged_at": ("was waged at", "was the site of"),
    "wields": ("wields", "is wielded by"),
}

#: Above this many endpoints, the explanation says "those N" instead of
#: repeating the list it just gave. `1b_006` has fourteen, and naming them
#: twice in one sentence is how the old template became unreadable.
_RELIST_LIMIT = 3


def phrase_for(relation: str, forward: bool) -> str:
    """The wording for one hop, or a plain fallback for an unmapped relation.

    The fallback names the relation rather than guessing at English for it. A
    new relation added to config should read awkwardly here until someone gives
    it a phrase - not silently read as something it is not.
    """
    pair = _PHRASES.get(relation)
    if pair is None:
        return f"is linked by {relation} to" if forward else f"is linked by {relation} from"
    return pair[0] if forward else pair[1]


def _steps(path: Path, graph: Graph) -> list[tuple[str, str, str]]:
    """One `(subject, phrase, object)` per hop, in the order walked."""
    current = path.start
    out = []
    for edge in path.edges:
        forward = edge.source == current
        nxt = edge.target if forward else edge.source
        out.append(
            (
                graph.nodes[current].name if current in graph.nodes else current,
                phrase_for(edge.relation, forward),
                graph.nodes[nxt].name if nxt in graph.nodes else nxt,
            )
        )
        current = nxt
    return out


def _join(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _explain(steps: list[tuple[str, str, str]], endpoints: list[str]) -> str:
    """One route, as a clause chain: "A does X to B, which does Y to C"."""
    parts = []
    for index, (subject, phrase, obj) in enumerate(steps):
        last = index == len(steps) - 1
        if last:
            target = (
                f"those {len(endpoints)}"
                if len(endpoints) > _RELIST_LIMIT
                else _join(endpoints)
            )
        else:
            target = obj
        parts.append(
            f"{subject} {phrase} {target}" if index == 0 else f"which {phrase} {target}"
        )
    return ", ".join(parts)


def _profile_sentence(answer: Answer, graph: Graph) -> str:
    """`EvidenceStatus.PROFILE`: an entity's record, not an answer to a question.

    "Who is Ravena Stormwell?" names no relation, so `fallback.profile_of`
    returns every fact the graph holds about her. Those endpoints are not
    candidate answers and must not be worded as if they were - the generic lead
    called them "2 answers: The Silent Choir and Vharenford", which invites a
    reader to pick one, and neither is an answer to anything. Her record is the
    answer.

    Facts about one subject are joined into a single statement rather than
    repeated as "X is ...; X serves ...", because a profile is a description of
    one thing and reads like one.
    """
    by_subject: dict[str, list[str]] = {}
    for path in answer.paths:
        steps = _steps(path, graph)
        if not steps:
            continue
        subject = steps[0][0]
        clauses = by_subject.setdefault(subject, [])
        for index, (_, phrase, obj) in enumerate(steps):
            clause = f"{phrase} {obj}" if index == 0 else f"which {phrase} {obj}"
            if clause not in clauses:
                clauses.append(clause)

    described = ". ".join(
        f"{subject} {_join(clauses)}" for subject, clauses in by_subject.items()
    )
    return (
        f"{described}. That is the entity's whole recorded profile, not an "
        "answer to a narrower question."
    )


def template_sentence(answer: Answer, graph: Graph) -> str:
    """A deterministic statement built from the verified chain.

    WHY THIS IS NOT A DATA DUMP ANY MORE
    ------------------------------------
    The first version rendered `"<values>. Route: A -> B -> C. Sources: ..."`.
    It was honest and nearly unreadable: `1b_006` produced fourteen arrow
    chains that differ only in their last node, in one sentence, and a reader
    had to reconstruct what "->" meant for each relation. The demo's whole
    claim is that a joined answer can be understood and checked, and prose that
    has to be decoded works against that.

    So each hop is now worded, in the direction the chain actually walked it,
    and routes sharing a prefix are stated once.

    The sentence carries **no citation tail**. An earlier version ended in
    `Sources: wiki/a.md, wiki/b.md.` on the reasoning that a sentence without
    its sources is not checkable - true of a sentence read alone, and not true
    here: every hop's document, field and row is rendered directly beneath it,
    and the source-documents table lists them again with their tiers. Repeating
    them inside the sentence made it unreadable without making it more
    checkable (ADR-042). What is unchanged is the part that mattered - the
    sentence still says nothing the chain does not contain.

    A conflict sentence is the one exception, and it is not a citation: naming
    *which* record asserts a disputed claim and which declines to is the
    content of the disagreement, not a footnote for it.

    This path needs no API key. It is what a keyless clone runs, what the test
    suite measures, and what the demo falls back to on a cold network -
    CLAUDE.md's "never record the demo against a cold cache" rule applies to
    the prose as much as to the answer.
    """
    if not answer.paths:
        return "No answer: " + (answer.note or answer.status.value)

    if answer.status == EvidenceStatus.PROFILE:
        return _profile_sentence(answer, graph)

    # Routes sharing every hop but their endpoint are one statement with a list
    # at the end, not N statements. Keyed on the wording, so two routes that
    # read identically collapse even if they came from different edges.
    groups: dict[tuple, tuple[list, list[str]]] = {}
    for path in answer.paths:
        steps = _steps(path, graph)
        if not steps:
            continue
        key = tuple((subject, phrase) for subject, phrase, _ in steps)
        if key not in groups:
            groups[key] = (steps, [])
        endpoints = groups[key][1]
        if steps[-1][2] not in endpoints:
            endpoints.append(steps[-1][2])

    values = list(answer.values)
    if not values:
        lead = "no endpoint"
    elif len(values) == 1:
        lead = values[0]
    else:
        lead = f"{len(values)} answers: {_join(values)}"

    if answer.status == EvidenceStatus.CONFLICTING_EVIDENCE:
        lead = (
            f"{lead} - but the sources disagree, and the disagreement is not "
            "settled by authority tier"
        )
    elif answer.status in (
        EvidenceStatus.FALLBACK_AMBIGUOUS,
        EvidenceStatus.PLANNED_AMBIGUOUS,
    ):
        lead = f"any of: {_join(values)}" if values else lead

    explanation = "; ".join(
        _explain(steps, endpoints) for steps, endpoints in groups.values()
    )

    # Name the disputed hop. Without this the explanation states the contested
    # claim as flatly as the uncontested one and leaves the caveat stranded in
    # the lead - a reader would have to work out for themselves which of the
    # two hops the disagreement is even about. Every value here comes off the
    # report `conflict.py` already produced; nothing is decided a second time,
    # and no side is preferred.
    dispute = ""
    if answer.status == EvidenceStatus.CONFLICTING_EVIDENCE and answer.conflict:
        report = answer.conflict
        subject = graph.nodes[report.subject_key].name if report.subject_key in graph.nodes else report.subject_key
        obj = graph.nodes[report.object_key].name if report.object_key in graph.nodes else report.object_key
        asserting = ", ".join(dict.fromkeys(e.document for e in report.asserting_edges))
        dispute = (
            f" The disagreement is over whether {subject} "
            f"{phrase_for(report.relation, True)} {obj}"
        )
        if asserting:
            dispute += f": {asserting} asserts it"
            if report.denial:
                dispute += f", and {report.denial.document} declines to"
        dispute += "."

    return f"{lead}. {explanation}.{dispute}"


def _prompt(answer: Answer, graph: Graph) -> str:
    lines = [_INSTRUCTIONS, "", f"Question: {answer.question}", ""]

    # MEASURED: asked `1b_006`, which has fourteen equally valid answers, the
    # model wrote "Corvus Hollowmere the Pale was a member of The Silent
    # Choir..." and stopped - 1 of 14, phrased as though it were the answer.
    # The hops were all in the prompt; what was missing was any statement that
    # the endpoints are a *set*. Listing them separately, above the chain,
    # says it in the one place a reader of the prompt cannot miss.
    if len(answer.values) > 1:
        lines += [
            f"This question has {len(answer.values)} answers, ALL equally valid. "
            "Your sentence must name every one:",
            ", ".join(answer.values),
            "",
        ]

    lines.append("Verified chain:")
    for path in answer.paths:
        for hop in _hops(path, graph):
            lines.append(
                f"- {hop['from']} --[{hop['relation']}]--> {hop['to']} "
                f"(source: {hop['document']}, field {hop['field']!r})"
            )
    if answer.status in _CONFLICT_STATUSES and answer.conflict is not None:
        lines += ["", "The sources disagree here. State that plainly; do not pick a side."]
        if answer.conflict.denial:
            lines.append(
                f'- {answer.conflict.denial.document} denies it: '
                f'"{answer.conflict.denial.quote}"'
            )
    if answer.status.routing_tier in ("cue_fallback", "llm_plan"):
        lines += [
            "",
            "This route came from a lower-precision tier. Do not overstate "
            "confidence in the phrasing.",
        ]
    return "\n".join(lines)


def synthesise(
    answer: Answer, graph: Graph, *, pool: object | None = None, use_model: bool = True
) -> Synthesis:
    """Phrase a verified `Answer`.

    Falls back to `template_sentence` for a missing key, an exhausted rotation,
    or any provider failure. Never raises: a phrasing failure must not lose an
    answer that was already found and verified.

    Args:
        use_model: False forces the deterministic path - what tests and any
            reproducible measurement should use.
    """
    if not answer.paths:
        return Synthesis(
            text=answer.note or f"No answer: {answer.status.value}",
            phrasing="none",
        )

    if not use_model:
        return Synthesis(template_sentence(answer, graph), "template")

    try:
        if pool is None:
            from src.clients.openrouter import OpenRouterPool

            pool = OpenRouterPool()
        text, model = pool.generate([_prompt(answer, graph)], description="answer phrasing")
        if not text.strip():
            raise RuntimeError("empty phrasing")
        return Synthesis(text.strip(), "model", model)
    except Exception:  # noqa: BLE001
        # Any provider failure at all. The evidence is already verified, so
        # degrading to the template loses only the prose - never the answer.
        return Synthesis(template_sentence(answer, graph), "template")
