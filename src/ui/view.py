"""`Answer` -> a plain dict a template can walk. No decisions are taken here.

WHERE THE LINE IS
-----------------
This module is allowed to *read, group, join and label* fields the engine
already produced. It is not allowed to *derive a new fact* from them.

Allowed, and used below:

- reading `EvidenceStatus.is_answerable` (the enum's own property);
- reading `ConflictReport.status` and `.must_surface` (the report's own
  properties) and printing them verbatim;
- grouping edges by the path they belong to, and collecting the distinct
  documents and tiers those edges already carry;
- looking a node's *display name* up by key, so a hop reads
  "Gravemaw Wyrm" rather than "gravemaw_wyrm";
- glossing a status code with one fixed line of English (`STATUS_GLOSS`),
  which is a caption on a name the engine chose, not a judgement about this
  answer.

Not allowed, and deliberately absent:

- comparing two tiers to decide which source wins (`conflict.py` did that;
  this module prints its verdict);
- re-running or extending a traversal to find more evidence;
- filtering candidates by type (`evidence.filter_endpoints` did that);
- composing `values`, `status` and `conflict` into a natural-language answer.
  `1b_009`'s expected answer is a sentence, and this module still does not
  write it: it shows the supported hop, the disputed hop and both sources,
  and leaves the reader to draw the conclusion the evidence supports.

The graph is accepted for one purpose only - `key -> display name`. It is
never traversed. `_display` is the whole of that access.
"""

from __future__ import annotations

from src.graph.schema import Edge, Graph
from src.query.engine import Answer
from src.query.evidence import EvidenceStatus

#: One fixed line per status, lifted from `evidence.py`'s own docstring so the
#: two cannot drift into saying different things. A caption on a name the
#: engine chose - not an assessment of any particular answer.
STATUS_GLOSS: dict[str, str] = {
    EvidenceStatus.NO_TEMPLATE_MATCH.value:
        "No deterministic template's trigger phrase matched this question. "
        "The engine logged the miss instead of guessing at a route.",
    EvidenceStatus.UNRESOLVED_ENTITY.value:
        "A name in the question does not appear anywhere in the corpus - "
        "most likely a typo or an invented name.",
    EvidenceStatus.AMBIGUOUS_ENTITY.value:
        "A name in the question did not match one entity exactly - either it "
        "resembles several, or it is a near-miss for one (a typo). The "
        "candidates and their similarities are listed below; resolution is "
        "exact-match only and never picks a winner (ADR-011), so retry with "
        "the exact name.",
    EvidenceStatus.OUTSIDE_STRUCTURED_COVERAGE.value:
        "The entity is real and named in the corpus text, but has no wiki "
        "infobox, so the graph - built only from structured cells - has no "
        "node for it (ADR-016).",
    EvidenceStatus.RELATION_UNAVAILABLE.value:
        "The first hop failed: this entity's page never records a fact of "
        "the kind the question asks for.",
    EvidenceStatus.NO_PATH.value:
        "The first hop worked, but the chain never completed to an endpoint.",
    EvidenceStatus.PATH_MISSING_ATTRIBUTE.value:
        "Candidates were found, but every one carried a recorded type that "
        "contradicts what the question asked for.",
    EvidenceStatus.SUFFICIENT.value:
        "Every hop the question needs was found, with its provenance.",
    EvidenceStatus.ABSTENTION.value:
        "The corpus itself declines to answer here. An abstaining cell is "
        "not the same as a missing one (F-014).",
    EvidenceStatus.CONFLICTING_EVIDENCE.value:
        "The evidence is complete but sources disagree, and the disagreement "
        "is not settled by authority tier. Both sides are shown below.",
    EvidenceStatus.FALLBACK_SUFFICIENT.value:
        "No template matched, so this was routed by matching the question's "
        "words against relation vocabulary - a second, weaker tier. Measured "
        "at 40% precision against template routing's 91% (ADR-019), and its "
        "usual error is stopping one hop short and returning the waypoint. "
        "Read the evidence trail before trusting this one.",
    EvidenceStatus.FALLBACK_AMBIGUOUS.value:
        "Fallback routing reached more than one endpoint and could not "
        "separate them from the question's wording. Every candidate is shown "
        "rather than one being picked.",
    EvidenceStatus.PLANNED_SUFFICIENT.value:
        "No deterministic tier matched, so a model proposed which relations to "
        "follow. Every name in that plan was checked against the graph before "
        "anything was traversed, and the evidence below is the graph's, not "
        "the model's - but the choice of route was not deterministic (ADR-020).",
    EvidenceStatus.PLANNED_AMBIGUOUS.value:
        "A model-proposed route reached more than one endpoint. All are shown; "
        "none was picked.",
    EvidenceStatus.PROFILE.value:
        "This question names an entity but no relation, so there is no single "
        "chain to walk. What follows is everything the graph records about "
        "that entity - each fact sourced - rather than an answer to a "
        "narrower question.",
}

#: Shown beside a hop so a reader knows what the number means without
#: opening config/authority.yaml.
TIER_LABEL: dict[int, str] = {
    1: "tier 1 - codex",
    2: "tier 2 - wiki",
    3: "tier 3 - chronicles",
    4: "tier 4 - ephemera",
}


def tier_label(tier: int) -> str:
    return TIER_LABEL.get(tier, f"tier {tier}")


def _display(graph: Graph, key: str) -> str:
    """A node's display name, or the key itself when the graph has no node.

    The only use this module makes of the graph. It reads `graph.nodes` and
    nothing else - no `neighbours`, no `out_edges`, no traversal.
    """
    node = graph.nodes.get(key)
    return node.name if node is not None else key


def _is_disputed(edge: Edge, answer: Answer) -> bool:
    """Is this the exact hop the engine's conflict report is about?

    A join, not a judgement. `check_conflict` already decided *that* something
    is disputed, and *which* relation between which two entities; this locates
    that hop among the ones being drawn so the page can mark it. It invents no
    dispute of its own: with no conflict report, or one the engine did not
    flag `must_surface`, nothing is ever marked.
    """
    conflict = answer.conflict
    if conflict is None or not conflict.must_surface:
        return False
    return (
        edge.relation == conflict.relation
        and {edge.source, edge.target} == {conflict.subject_key, conflict.object_key}
    )


def _attestations(corroboration, edge: Edge) -> list[dict]:
    """Non-wiki passages naming both ends of `edge`, as plain data.

    `corroboration` is duck-typed on purpose: the import allowlist in
    `tests/test_ui.py` pins exactly which modules this file may import, and the
    corroboration index is not one of them (it reaches the gazetteer, which
    reaches the resolver). The view asks it for data and renders what it gets;
    it decides nothing.
    """
    if corroboration is None:
        return []
    return [
        {
            "document": a.document,
            "collection": a.collection,
            "locator": a.locator,
            "tier": a.tier,
            "tier_label": tier_label(a.tier),
            "quote": a.quote,
        }
        for a in corroboration.for_edge(edge)
    ]


def _hop(
    graph: Graph,
    edge: Edge,
    from_key: str,
    position: int,
    answer: Answer,
    corroboration=None,
) -> dict:
    forward = edge.source == from_key
    to_key = edge.target if forward else edge.source
    return {
        "position": position,
        "from_key": from_key,
        "from_name": _display(graph, from_key),
        "to_key": to_key,
        "to_name": _display(graph, to_key),
        "relation": edge.relation,
        # How the corpus wrote the edge, not how we walked it. An edge read off
        # the *other* page is still evidence, and hiding the direction would
        # hide the asymmetry ADR-016 measured.
        "direction": "forward" if forward else "reverse",
        "document": edge.document,
        "tier": edge.tier,
        "tier_label": tier_label(edge.tier),
        "field_name": edge.field_name,
        "row": edge.row,
        "raw": edge.raw,
        "cell_template": edge.template,
        "assertion": edge.assertion,
        "extraction": edge.extraction,
        "year": edge.year,
        "year_kind": edge.year_kind,
        "qualifier": edge.qualifier,
        "inferred_inverse": edge.inferred_inverse,
        "disputed": _is_disputed(edge, answer),
        # Cross-collection attestation (ADR-027). Co-mention, not proof: these
        # passages name both ends, which is why the page says "also attested
        # in" rather than claiming they assert the relation.
        "attestations": _attestations(corroboration, edge),
    }


def _route(graph: Graph, path, index: int, answer: Answer, corroboration=None) -> dict:
    hops = []
    current = path.start
    for position, edge in enumerate(path.edges, start=1):
        hop = _hop(graph, edge, current, position, answer, corroboration)
        hops.append(hop)
        current = hop["to_key"]
    return {
        "index": index,
        "start_key": path.start,
        "start_name": _display(graph, path.start),
        "endpoint_key": current,
        "endpoint_name": _display(graph, current),
        "hops": hops,
        "documents": list(path.documents),
    }


def _conflict(graph: Graph, answer: Answer) -> dict | None:
    """The engine's conflict report, transcribed. Nothing is resolved here."""
    report = answer.conflict
    if report is None:
        return None
    return {
        # `status` and `must_surface` are the report's own properties, printed
        # as they came. This module does not compare the two tiers below to
        # reach a verdict of its own - that comparison already happened in
        # conflict.py, and repeating it here would let the two disagree.
        "status": report.status,
        "must_surface": report.must_surface,
        "subject_key": report.subject_key,
        "subject_name": _display(graph, report.subject_key),
        "relation": report.relation,
        "object_key": report.object_key,
        "object_name": _display(graph, report.object_key),
        "asserted_by": [
            {
                "document": e.document,
                "tier": e.tier,
                "tier_label": tier_label(e.tier),
                "field_name": e.field_name,
                "row": e.row,
                "raw": e.raw,
            }
            for e in report.asserting_edges
        ],
        "denied_by": None
        if report.denial is None
        else {
            "document": report.denial.document,
            "tier": report.denial.tier,
            "tier_label": tier_label(report.denial.tier),
            "quote": report.denial.quote,
        },
    }


def _entity_ref(ref) -> dict | None:
    """Transcribe one `diagnostics.EntityRef`. Plain data out, nothing derived."""
    if ref is None:
        return None
    return {
        "key": ref.key,
        "name": ref.name,
        "type": ref.entity_type,
        "page": ref.page,
        "similarity": ref.similarity,
    }


def _diagnostics(answer: Answer) -> dict | None:
    """Transcribe what the engine established before it declined.

    Every value below was computed in `src/query/diagnostics.py`. This function
    renames nothing into a claim and computes nothing new - it flattens
    dataclasses into dicts so `render.py` can walk them without importing the
    engine. That is the whole of the UI's involvement in a decline (ADR-026).
    """
    diag = answer.diagnostics
    if diag is None:
        return None
    return {
        "span": diag.span,
        "asked_relation": diag.asked_relation,
        "relation_vocabulary": list(diag.relation_vocabulary),
        "suggestions": [_entity_ref(c) for c in diag.suggestions],
        "candidates": [_entity_ref(c) for c in diag.candidates],
        "start": _entity_ref(diag.start),
        "goal": _entity_ref(diag.goal),
        "reached": [_entity_ref(e) for e in diag.reached],
        "reached_count": diag.reached_count,
        "hops_completed": diag.hops_completed,
        "established": [
            {
                "entity": _entity_ref(n.entity),
                "relations_present": list(n.relations_present),
                "fact_count": n.fact_count,
                "facts": [
                    {
                        "relation": f.relation,
                        "direction": f.direction,
                        "other": _entity_ref(f.other),
                        "document": f.document,
                        "field_name": f.field_name,
                        "row": f.row,
                        "raw": f.raw,
                        "tier": f.tier,
                        "tier_label": tier_label(f.tier),
                    }
                    for f in n.facts
                ],
            }
            for n in diag.established
        ],
        "presence": [
            {
                "collection": pr.collection,
                "tier": pr.tier,
                "tier_label": tier_label(pr.tier),
                "documents": list(pr.documents),
                "unit_count": pr.unit_count,
                "evidence_id": pr.evidence_id,
                "locator": pr.locator,
                "quote": pr.quote,
            }
            for pr in diag.presence
        ],
    }


def build_view(answer: Answer, graph: Graph, corroboration=None) -> dict:
    """Everything the page needs, read off one `Answer`.

    The returned dict is plain data - no engine objects leak into the
    template, so `render.py` cannot call back into the query layer even if
    someone later tries to make it.
    """
    routes = [
        _route(graph, p, i, answer, corroboration)
        for i, p in enumerate(answer.paths, start=1)
    ]

    # Tier per document, collected from the edges that already carry it. The
    # engine's `answer.documents` stays the authority on *which* documents were
    # used; this only attaches the tier each edge recorded for one.
    tiers: dict[str, int] = {}
    for route in routes:
        for hop in route["hops"]:
            tiers.setdefault(hop["document"], hop["tier"])

    return {
        "question": answer.question,
        "status": answer.status.value,
        "status_gloss": STATUS_GLOSS.get(answer.status.value, ""),
        # The enum's own property. The UI does not decide what counts as an
        # answer; it asks the status it was handed.
        "answerable": answer.status.is_answerable,
        "values": list(answer.values),
        "template": answer.template,
        # Presentation needs to know a model chose this route, and the tier
        # identity is the engine's word for it - `llm_plan` is set only by
        # `engine._planned_answer`. Derived here rather than in render.py so the
        # renderer keeps branching on view data instead of knowing tier names,
        # and so the string lives in one place if a fourth tier is ever added.
        "routed_by_model": answer.template == "llm_plan",
        "chain": list(answer.chain),
        "start_key": answer.start_key,
        "start_name": None if answer.start_key is None else _display(graph, answer.start_key),
        "goal_key": answer.goal_key,
        "goal_name": None if answer.goal_key is None else _display(graph, answer.goal_key),
        "routes": routes,
        "documents": [
            {
                "document": d,
                "tier": tiers.get(d),
                "tier_label": tier_label(tiers[d]) if d in tiers else "",
            }
            for d in answer.documents
        ],
        "conflict": _conflict(graph, answer),
        # The engine's own words for why it stopped, passed through unedited.
        # This is the fallback-reason surface; when it is None there was no
        # fallback to explain.
        "note": answer.note,
        # Partial evidence for a decline. None on an answered result.
        "diagnostics": _diagnostics(answer),
        "resolutions": [
            {
                "mention": r.mention,
                "status": r.status.value,
                "key": r.key,
                # Flattened to plain data like everything else. The similarity
                # is shown because ADR-011's whole point is that a 0.839 match
                # is still not a winner - a reader should see the number the
                # resolver refused to act on.
                "candidates": [
                    {"key": c.key, "name": c.name, "similarity": c.similarity}
                    for c in r.candidates
                ],
            }
            for r in answer.resolutions
        ],
    }
