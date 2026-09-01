"""The orchestrator: one call, `answer_question`, wiring every stage together.

    question -> route() -> walk_relations() -> classify -> filter -> conflict
             -> Answer, with every hop's evidence attached

Nothing here is a fallback path in disguise. Each stage either succeeds
concretely or the function returns early with a named `EvidenceStatus`
explaining why, so a caller (a test, the eval harness, eventually a UI) never
has to guess what "no answer" meant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path as FsPath

from src.graph.build import RelationMap, load_relation_map
from src.graph.schema import Graph
from src.graph.traverse import Path, walk_relations
from src.query.conflict import ConflictReport, check_conflict
from src.query.evidence import (
    EvidenceStatus,
    check_abstention,
    classify_traversal,
    filter_endpoints,
    mentioned_in_corpus,
    resolution_status,
)
from src.query.fallback import route_by_cues
from src.query.resolve import EntityResolver, Resolution
from src.query.route import RouteMiss, build_gazetteer, route
from src.settings import get_settings

#: A capitalised multi-word span, used only as a last-resort guess at which
#: phrase in a routing-miss question was meant to be an entity - so a name the
#: gazetteer never heard of can still be classified as unresolved (or, if the
#: corpus does mention it, as outside structured coverage) instead of the
#: whole question just being logged as an opaque miss.
_CAPITALISED_SPAN_RE = re.compile(r"\b[A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+)+\b")


@dataclass(frozen=True)
class Answer:
    """Everything the engine determined about one question."""

    question: str
    status: EvidenceStatus
    values: tuple[str, ...] = ()
    template: str | None = None
    chain: tuple[str, ...] = ()
    start_key: str | None = None
    goal_key: str | None = None
    paths: tuple[Path, ...] = ()
    documents: tuple[str, ...] = ()
    conflict: ConflictReport | None = None
    resolutions: tuple[Resolution, ...] = ()
    note: str | None = None

    def explain(self) -> str:
        """Human-readable trace: every hop, with the evidence that produced it."""
        if not self.paths:
            return f"[{self.status.value}] {self.note or ''}".strip()
        lines = [f"status: {self.status.value}", f"template: {self.template}"]
        for path in self.paths:
            lines.append(path.explain())
        if self.conflict is not None:
            lines.append(f"conflict: {self.conflict.status}")
            if self.conflict.denial:
                lines.append(f"  denial ({self.conflict.denial.document}): {self.conflict.denial.quote}")
        return "\n".join(lines)


def answer_question(
    question: str,
    graph: Graph,
    *,
    resolver: EntityResolver | None = None,
    gazetteer: list[tuple[str, str]] | None = None,
    corpus_path: FsPath | None = None,
    relation_map: RelationMap | None = None,
    evidence_units: list | None = None,
) -> Answer:
    """Answer one question deterministically, or say precisely why not."""
    resolver = resolver or EntityResolver(graph)
    gazetteer = gazetteer if gazetteer is not None else build_gazetteer(graph, resolver)
    corpus_path = corpus_path or get_settings().require_corpus()
    relation_map = relation_map or load_relation_map()

    routed = route(question, graph, resolver, gazetteer)

    if isinstance(routed, RouteMiss):
        fallback = _fallback_answer(question, graph, relation_map)
        if fallback is not None:
            return fallback
        return _unrouted(question, routed, resolver, evidence_units)

    paths = walk_relations(graph, routed.start_key, list(routed.chain))
    base_status = classify_traversal(graph, routed.start_key, routed.chain, paths)

    if base_status != EvidenceStatus.SUFFICIENT:
        quote = check_abstention(graph, corpus_path, routed.start_key, routed.chain[0], relation_map)
        if quote is not None:
            return Answer(
                question=question, status=EvidenceStatus.ABSTENTION,
                template=routed.template, chain=routed.chain, start_key=routed.start_key,
                note=f"{routed.start_key}'s own record abstains: {quote!r}",
            )
        return Answer(
            question=question, status=base_status, template=routed.template,
            chain=routed.chain, start_key=routed.start_key,
        )

    if routed.goal_key is not None:
        paths = [p for p in paths if p.end == routed.goal_key]
        if not paths:
            return Answer(
                question=question, status=EvidenceStatus.NO_PATH,
                template=routed.template, chain=routed.chain, start_key=routed.start_key,
                goal_key=routed.goal_key,
                note="the chain reached other endpoints but never the named goal",
            )
        filt_status = EvidenceStatus.SUFFICIENT
    else:
        paths, filt_status = filter_endpoints(
            graph, paths,
            entity_type=routed.type_hint_entity_type,
            word=routed.type_hint_word,
        )

    if filt_status != EvidenceStatus.SUFFICIENT:
        return Answer(
            question=question, status=filt_status, template=routed.template,
            chain=routed.chain, start_key=routed.start_key,
            note=f"type hint {routed.type_hint_word!r} eliminated every candidate",
        )

    conflict = None
    status = EvidenceStatus.SUFFICIENT
    if routed.check_conflict:
        subject_key = paths[0].nodes[1]
        conflict = check_conflict(graph, corpus_path, subject_key, routed.chain[0], routed.start_key)
        if conflict.must_surface:
            status = EvidenceStatus.CONFLICTING_EVIDENCE

    values = tuple(sorted({graph.nodes[p.end].name for p in paths}))
    documents = tuple(sorted({doc for p in paths for doc in p.documents}))

    return Answer(
        question=question, status=status, values=values, template=routed.template,
        chain=routed.chain, start_key=routed.start_key, goal_key=routed.goal_key,
        paths=tuple(paths), documents=documents, conflict=conflict,
    )


def _fallback_answer(question: str, graph: Graph, relation_map: RelationMap) -> Answer | None:
    """Second routing tier: cue-based, run only after a template miss.

    Returns None whenever the fallback declines, so the caller reports the
    template stage's own miss rather than a weaker-looking failure invented
    here. Measured (ADR-019): this adds 7 correct answers and 13
    complete-evidence retrievals over templates alone, across 49 answerable
    questions, and regresses none of them - templates run first, so every
    answer they already produced is untouched.

    The status is deliberately not SUFFICIENT. See
    `EvidenceStatus.FALLBACK_SUFFICIENT` for why the two tiers must stay
    distinguishable to a reader.
    """
    route_result = route_by_cues(graph, question, relation_map)
    if not route_result.answered:
        return None

    status = (
        EvidenceStatus.FALLBACK_AMBIGUOUS
        if route_result.ambiguous
        else EvidenceStatus.FALLBACK_SUFFICIENT
    )
    values = tuple(
        dict.fromkeys(
            graph.nodes[p.end].name if p.end in graph.nodes else p.end
            for p in route_result.paths
        )
    )
    documents = tuple(
        dict.fromkeys(d for p in route_result.paths for d in p.documents)
    )
    first = route_result.paths[0]
    return Answer(
        question=question,
        status=status,
        values=values,
        template="cue_fallback",
        chain=tuple(e.relation for e in first.edges),
        start_key=route_result.start.key if route_result.start else None,
        paths=route_result.paths,
        documents=documents,
        note=(
            "No template matched. Answered by cue-based fallback routing on "
            f"relation(s) {', '.join(route_result.cued) or 'n/a'}. This tier is "
            "measured at lower precision than template routing (ADR-019) - "
            "check the evidence trail."
        ),
    )


def _unrouted(
    question: str, miss: RouteMiss, resolver: EntityResolver, evidence_units: list | None
) -> Answer:
    """Turn a template miss into the most specific status the evidence allows.

    A miss is not automatically UNRESOLVED_ENTITY - most questions with no
    matching trigger simply ask something these four templates don't cover,
    which the caller should read from `note`. Only when a trigger *did* fire
    but no entity in the question resolved (see `route.py`'s own miss
    reasons) is it worth guessing at the phrase and classifying why it
    failed, so "a name this system has never heard of" and "a real corpus
    entity the graph doesn't cover" are not both reported as the same thing.
    """
    if "no resolved entity" not in miss.reason and "did not find exactly one" not in miss.reason:
        return Answer(question=question, status=EvidenceStatus.NO_TEMPLATE_MATCH, note=miss.reason)

    for candidate in _CAPITALISED_SPAN_RE.findall(question):
        resolution = resolver.resolve(candidate)
        if resolution.resolved:
            continue  # a real entity resolved; the miss was about routing, not resolution.
        status = resolution_status(resolution) or EvidenceStatus.UNRESOLVED_ENTITY
        if status == EvidenceStatus.UNRESOLVED_ENTITY and evidence_units is not None:
            if mentioned_in_corpus(candidate, evidence_units):
                status = EvidenceStatus.OUTSIDE_STRUCTURED_COVERAGE
        return Answer(
            question=question, status=status, resolutions=(resolution,), note=miss.reason
        )

    return Answer(question=question, status=EvidenceStatus.RELATION_UNAVAILABLE, note=miss.reason)


def main(argv: list[str] | None = None) -> None:
    """CLI demo: answer one question, printing the full evidence trail.

    Defaults to the first vertical slice, `1b_013`, so `python -m
    src.query.engine` alone reproduces the smoke test with no arguments.
    """
    import sys

    from src.graph.build import build_graph

    question = " ".join(argv or sys.argv[1:]) or (
        "Whose dominion encompasses the lair of the Gravemaw Wyrm?"
    )
    graph = build_graph()
    answer = answer_question(question, graph)
    print(f"Q: {question}")
    print(f"A: {', '.join(answer.values) or '(none)'}")
    print(answer.explain())


if __name__ == "__main__":
    main()
