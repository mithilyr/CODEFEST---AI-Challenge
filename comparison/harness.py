"""Run both routers over one frozen question set and measure the difference.

ARM A  our four-template router      `src/query/route.py` via `answer_question`
ARM B  sister cue-based router       `comparison/cue_router.py`

Everything except routing is held constant: same graph, same `find_paths`,
same `src/query/conflict.py`, same corpus. See `cue_router`'s module docstring
for the three departures from the sister implementation and why each one
exists.

METRIC DEFINITIONS
-------------------
Stated here rather than left implicit, because every one of them is a claim a
judge can dispute, and a number whose definition is buried is not a
measurement. Group C (expected-unanswerable) is scored inverted throughout:
there, abstaining IS the correct behaviour.

route_success
    A route was produced at all. Arm A: `route()` returned a RouteResult
    rather than a RouteMiss. Arm B: status in {answered, any_of}.

entity_resolution_success
    The router resolved a start entity whose own wiki page is one of the
    question's `required_evidence` documents. Mechanical, and fair to both
    arms - it does not require the question set to name a gold start entity,
    which the independent author was deliberately not asked to supply.

answer_correctness
    Produced values match `gold_answers`, honouring `answer_cardinality`:
    `exactly_one` needs one correct value and no others; `any_of` needs at
    least one produced value to be in the gold set; `all_of` needs the
    produced set to equal the gold set. Alias-tolerant via the answer key's
    own alias lists for group A.

complete_evidence
    set(required_evidence) is a subset of the documents the surviving paths
    actually cite. This is the number Checkpoint 1 scored 0/9 on and the
    number that matters most - an answer reached without its evidence is
    right by the wrong route.

ambiguous_resolution
    The router could not narrow to one answer. Arm A: AMBIGUOUS_ENTITY, or a
    single-cardinality question returning >1 value. Arm B: status any_of.
    Not automatically a failure - `1b_006` genuinely has fourteen answers -
    so it is reported, not penalised.

no_route_shape
    The generalisation of NO_TEMPLATE_MATCH, so both arms are comparable.
    Arm A: EvidenceStatus.NO_TEMPLATE_MATCH. Arm B: status `profile` (an
    entity resolved but no relation was cued) - the same failure wearing a
    different name.

wrong_route
    The answer is correct but the relation sequence used is not one the gold
    route accepts, or the evidence is incomplete. This is the failure mode
    F-019 and `walk_relations`' docstring both exist for: fighting in a war
    is not winning it, and a selector reading only the endpoint scores it
    correct anyway.

unnecessary_depth
    Hops used exceeds the minimum hop count of any accepted gold route.

GOLD ROUTE DERIVATION
----------------------
Metrics `wrong_route` and `unnecessary_depth` need to know what the correct
relation sequence is. That is derived AFTER the question set is frozen, and
never by the question author, so it cannot influence question wording:

  group A  taken from `eval/answer_key.json`'s own `acceptable_paths` for the
           source question - authored before either router existed.
  group B  derived mechanically from the graph: every path (<= 3 hops) from a
           resolved question entity to the gold answer node whose documents
           cover `required_evidence`. If none exists, the question is marked
           `gold_route_underivable` and excluded from metrics 7 and 8 only.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path as FsPath

from src.graph.build import build_graph, load_relation_map
from src.graph.schema import Graph
from src.graph.traverse import Path, find_paths
from src.query.engine import answer_question
from src.query.evidence import EvidenceStatus
from src.query.resolve import EntityResolver
from src.query.route import build_gazetteer
from src.settings import get_settings

from eval.scoring import score_answer, score_evidence

from comparison.cue_router import relation_cues, route_question
from comparison.sister_conflicts import excluded_pairs as sister_excluded_pairs

MAX_HOPS = 3


# --------------------------------------------------------------------------
# One arm's outcome on one question, in a shape both arms can produce.
# --------------------------------------------------------------------------


@dataclass
class Outcome:
    status: str
    values: tuple[str, ...] = ()
    documents: tuple[str, ...] = ()
    relation_routes: tuple[tuple[str, ...], ...] = ()
    hops: int | None = None
    start_key: str | None = None
    would_escalate: str | None = None
    note: str | None = None


def _paths_to_outcome(
    graph: Graph, status: str, paths: tuple[Path, ...], start_key: str | None, **kw
) -> Outcome:
    values = tuple(
        dict.fromkeys(
            graph.nodes[p.end].name if p.end in graph.nodes else p.end for p in paths
        )
    )
    documents = tuple(dict.fromkeys(d for p in paths for d in p.documents))
    routes = tuple(dict.fromkeys(tuple(e.relation for e in p.edges) for p in paths))
    hops = min((len(p.edges) for p in paths), default=None)
    return Outcome(status, values, documents, routes, hops, start_key, **kw)


# --------------------------------------------------------------------------
# Arm A - our engine, unchanged.
# --------------------------------------------------------------------------


def run_arm_a(question: str, ctx: "Context", *, use_fallback: bool = False) -> Outcome:
    answer = answer_question(
        question,
        ctx.graph,
        resolver=ctx.resolver,
        gazetteer=ctx.gazetteer,
        corpus_path=ctx.corpus,
        relation_map=ctx.relation_map,
        use_fallback=use_fallback,
        # Deterministic only. A comparison number that silently depends on a
        # model being reachable is not reproducible, and this harness exists to
        # produce reproducible numbers.
        use_planner=False,
    )
    routes = tuple(
        dict.fromkeys(tuple(e.relation for e in p.edges) for p in answer.paths)
    )
    hops = min((len(p.edges) for p in answer.paths), default=None)
    return Outcome(
        status=answer.status.value,
        values=answer.values,
        documents=answer.documents,
        relation_routes=routes,
        hops=hops,
        start_key=answer.start_key,
        note=answer.note,
    )


# --------------------------------------------------------------------------
# Arm B - sister cue router, then our conflict module, then the same shape.
# --------------------------------------------------------------------------


def run_arm_b(question: str, ctx: "Context", **guards) -> Outcome:
    result = route_question(
        ctx.graph, question, ctx.relation_map, cues=ctx.cues, **guards
    )
    if result.status in ("unresolved_entity", "profile", "not_found"):
        return Outcome(
            status=result.status,
            start_key=result.start.key if result.start else None,
            would_escalate=result.would_escalate,
        )

    surviving = tuple(p for p in result.paths if not _denied(p, ctx))
    if not surviving:
        return Outcome(
            status="not_found",
            start_key=result.start.key if result.start else None,
            note="every candidate path excluded as a same-tier denial",
        )

    status = result.status
    if status == "answered" and len({p.end for p in surviving}) > 1:
        status = "any_of"
    return _paths_to_outcome(
        ctx.graph,
        status,
        surviving,
        result.start.key if result.start else None,
        would_escalate=result.would_escalate,
    )


def _denied(path: Path, ctx: "Context") -> bool:
    """Exclude a path routed through a structurally excluded (source, target).

    Uses the sister prototype's own structural rule
    (`comparison/sister_conflicts.py`), NOT our `src/query/conflict.py`. See
    that module's docstring for the measured reason: our paragraph-scoped
    `find_denial`, applied per edge, wrongly excluded the Cartel's
    uncontested Leaden Accord edge and turned 1b_007 and 1b_022 into
    `not_found` - harness artifacts that would have been reported as arm B
    routing failures.
    """
    return any(
        (edge.source, edge.target) in ctx.excluded_pairs for edge in path.edges
    )


# --------------------------------------------------------------------------
# Shared context, built once.
# --------------------------------------------------------------------------


@dataclass
class Context:
    graph: Graph
    relation_map: object
    resolver: EntityResolver
    gazetteer: list
    corpus: FsPath
    cues: dict
    answer_key: dict
    excluded_pairs: set = field(default_factory=set)


def build_context() -> Context:
    graph = build_graph()
    relation_map = load_relation_map()
    resolver = EntityResolver(graph)
    key = {
        q["qid"]: q
        for q in json.loads(
            FsPath("eval/answer_key.json").read_text(encoding="utf-8")
        )["questions"]
    }
    return Context(
        graph=graph,
        relation_map=relation_map,
        resolver=resolver,
        gazetteer=build_gazetteer(graph, resolver),
        corpus=get_settings().require_corpus(),
        cues=relation_cues(relation_map),
        answer_key=key,
        excluded_pairs=sister_excluded_pairs(graph),
    )


# --------------------------------------------------------------------------
# Gold routes, derived post-freeze.
# --------------------------------------------------------------------------


#: The answer key and config/relations.yaml disagree on four relation names.
#: This is the unreconciled vocabulary gap the README already reports rather
#: than hides ("the answer key names the relation `victor` where
#: config/relations.yaml calls it `victor_of`"). Left unnormalised it makes
#: every correct `victor_of` route look like a wrong route: arm A was flagged
#: wrong_route on 1b_006 and 1b_009 while holding correct answers and
#: complete evidence. Reconciling the two vocabularies for real is open work
#: in the main repo; normalising here keeps that open question from
#: contaminating this measurement.
RELATION_ALIASES = {"victor": "victor_of", "forged": "forged_at"}


def _canonical_relation(name: str, ctx: Context) -> str:
    rm = ctx.relation_map
    if name in rm.inverses:
        return name
    for canonical, inverse in rm.inverses.items():
        if inverse == name:
            return canonical
    return RELATION_ALIASES.get(name, name)


def gold_routes(q: dict, ctx: Context) -> tuple[tuple[tuple[str, ...], ...], int | None]:
    """Accepted relation sequences and the minimum accepted hop count."""
    if q.get("source"):
        entry = ctx.answer_key.get(q["source"])
        if entry:
            routes = tuple(
                dict.fromkeys(
                    tuple(_canonical_relation(h["relation"], ctx) for h in path["hops"])
                    for path in entry.get("acceptable_paths", [])
                )
            )
            if routes:
                return routes, min(len(r) for r in routes)

    gold_keys = _gold_answer_keys(q, ctx)
    required = set(q.get("required_evidence") or [])
    if not gold_keys or not required:
        return (), None

    from comparison.cue_router import find_entity_mentions

    routes: set[tuple[str, ...]] = set()
    for mention in find_entity_mentions(ctx.graph, q["question"]):
        for goal in gold_keys:
            for p in find_paths(ctx.graph, mention.key, goal, max_hops=MAX_HOPS):
                if required <= set(p.documents):
                    routes.add(tuple(e.relation for e in p.edges))
    if not routes:
        return (), None
    return tuple(sorted(routes)), min(len(r) for r in routes)


def _gold_answer_keys(q: dict, ctx: Context) -> set[str]:
    by_name = {n.name: k for k, n in ctx.graph.nodes.items()}
    return {by_name[a] for a in q.get("gold_answers", []) if a in by_name}


# --------------------------------------------------------------------------
# Scoring.
# --------------------------------------------------------------------------


def _accepted_answer_strings(q: dict, ctx: Context) -> list[str]:
    """Gold answers plus any aliases the answer key records for them."""
    accepted = list(q.get("gold_answers", []))
    lowered = {a.lower() for a in accepted}
    entry = ctx.answer_key.get(q.get("source") or "")
    if entry:
        for acc in entry.get("accepted_answers", []):
            if acc["answer"].lower() in lowered:
                accepted.extend(acc.get("aliases", []))
    return list(dict.fromkeys(accepted))


def score(q: dict, outcome: Outcome, ctx: Context) -> dict:
    answerable = q.get("expected_answerable", True)
    accepted = _accepted_answer_strings(q, ctx)
    produced = list(outcome.values)
    routes, min_gold_hops = gold_routes(q, ctx)

    routed = outcome.status in (
        "answered", "any_of", EvidenceStatus.SUFFICIENT.value,
        EvidenceStatus.CONFLICTING_EVIDENCE.value,
        EvidenceStatus.FALLBACK_SUFFICIENT.value,
        EvidenceStatus.FALLBACK_AMBIGUOUS.value,
    )

    # Scored with the project's own `eval/scoring.py`, not a bespoke
    # comparison. It carries the negation guard that answer_key.json's
    # preamble warns about and that ADR-014 was written around: a naive
    # `gold in predicted` credits "there is no mention of who the victors
    # were" as correct. Reusing it also means the comparison cannot quietly
    # grade on a kinder curve than our own eval harness does.
    verdict = score_answer(", ".join(produced), accepted) if produced else None
    correct = bool(verdict and verdict.correct)
    cardinality = q.get("answer_cardinality", "exactly_one")
    if correct and cardinality == "exactly_one" and len(produced) > 1:
        # One right value among several offered is not a resolved answer to a
        # question that has exactly one. Reported as ambiguous below.
        correct = False

    # A conflict question's correct behaviour is to SURFACE the dispute, not
    # to emit a matching string - `1b_009`'s gold answer in answer_key.json is
    # a prose sentence describing the disagreement, which no entity-valued
    # router can string-match. Crediting the conflict status is what makes the
    # two arms comparable on that question at all.
    entry = ctx.answer_key.get(q.get("source") or "")
    conflict_expected = bool(entry and entry.get("expected_conflict_status"))
    surfaced_conflict = outcome.status == EvidenceStatus.CONFLICTING_EVIDENCE.value
    if conflict_expected and surfaced_conflict:
        correct = True

    required = list(q.get("required_evidence") or [])
    ev = score_evidence(required, list(outcome.documents))
    complete = bool(required) and ev.recall == 1.0

    start_page = None
    if outcome.start_key and outcome.start_key in ctx.graph.nodes:
        start_page = ctx.graph.nodes[outcome.start_key].page
    entity_ok = bool(start_page and start_page in required)

    ambiguous = outcome.status in ("any_of", EvidenceStatus.AMBIGUOUS_ENTITY.value) or (
        cardinality == "exactly_one" and len(produced) > 1
    )
    no_shape = outcome.status in (
        EvidenceStatus.NO_TEMPLATE_MATCH.value, "profile"
    )
    # Route comparison is direction-insensitive. `walk_relations`' docstring
    # is explicit that direction is deliberately not specified - the graph is
    # asymmetric, and a faction's victory may be recorded only on the
    # conflict's page. answer_key.json documents one direction per path; the
    # reverse of an accepted route is the same claim read from the other end,
    # so both count. Without this, arm A was flagged wrong_route on 1b_006
    # and 1b_009 while holding complete, correct evidence.
    accepted_routes = set(routes) | {tuple(reversed(r)) for r in routes}
    wrong_route = bool(
        correct
        and accepted_routes
        and (
            not complete
            or not any(r in accepted_routes for r in outcome.relation_routes)
        )
    )
    deep = bool(
        min_gold_hops is not None
        and outcome.hops is not None
        and outcome.hops > min_gold_hops
    )

    return {
        "rid": q["rid"],
        "group": q["group"],
        "status": outcome.status,
        "route_success": routed if answerable else (not routed),
        "entity_resolution_success": entity_ok if answerable else (not outcome.start_key),
        "answer_correct": correct if answerable else (not produced),
        "complete_evidence": complete if answerable else True,
        "ambiguous": ambiguous,
        "no_route_shape": no_shape,
        "wrong_route": wrong_route,
        "unnecessary_depth": deep,
        "would_escalate": outcome.would_escalate,
        "gold_route_underivable": not routes,
        "values": list(outcome.values),
        "documents": list(outcome.documents),
        "relation_routes": [list(r) for r in outcome.relation_routes],
        "hops": outcome.hops,
        "note": outcome.note,
    }


METRICS = (
    "route_success",
    "entity_resolution_success",
    "answer_correct",
    "complete_evidence",
    "ambiguous",
    "no_route_shape",
    "wrong_route",
    "unnecessary_depth",
)


def summarise(rows: list[dict]) -> dict:
    out = {"n": len(rows)}
    for m in METRICS:
        out[m] = sum(1 for r in rows if r[m])
    out["would_escalate"] = sum(1 for r in rows if r["would_escalate"])
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", default="eval/robustness/routing_robustness_v1.json")
    ap.add_argument("--out", default="comparison/results")
    args = ap.parse_args(argv)

    ctx = build_context()
    questions = json.loads(FsPath(args.set).read_text(encoding="utf-8"))["questions"]

    # Three arms, not two. Arm A is the four templates ALONE - the fallback
    # tier now ships inside `answer_question`, so reproducing ADR-019's
    # templates-only column requires switching it off explicitly. Arm C is the
    # system as it actually ships.
    rows_a, rows_b, rows_c = [], [], []
    for q in questions:
        rows_a.append(score(q, run_arm_a(q["question"], ctx, use_fallback=False), ctx))
        rows_b.append(score(q, run_arm_b(q["question"], ctx), ctx))
        rows_c.append(score(q, run_arm_a(q["question"], ctx, use_fallback=True), ctx))

    outdir = FsPath(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "set": args.set,
        "arm_a": {"per_question": rows_a, "summary": summarise(rows_a)},
        "arm_b": {"per_question": rows_b, "summary": summarise(rows_b)},
        "arm_c_integrated": {"per_question": rows_c, "summary": summarise(rows_c)},
        "by_group": {
            g: {
                "arm_a": summarise([r for r in rows_a if r["group"] == g]),
                "arm_b": summarise([r for r in rows_b if r["group"] == g]),
            }
            for g in sorted({r["group"] for r in rows_a})
        },
    }
    (outdir / "router_comparison.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    answerable = [q["rid"] for q in questions if q.get("expected_answerable", True)]

    def only(rows):
        return [r for r in rows if r["rid"] in answerable]

    print(f"Answerable questions: {len(answerable)} of {len(questions)}\n")
    print(f"{'metric':<28}{'A templates':>13}{'B cues':>9}{'C shipped':>12}")
    print("-" * 62)
    for metric in METRICS:
        a = sum(1 for r in only(rows_a) if r[metric])
        b = sum(1 for r in only(rows_b) if r[metric])
        c = sum(1 for r in only(rows_c) if r[metric])
        print(f"{metric:<28}{a:>13}{b:>9}{c:>12}")

    def refusals(rows):
        return sum(
            1 for r in rows if r["rid"] not in answerable and r["answer_correct"]
        )

    print(
        f"\n{'honest refusal (of 6)':<28}"
        f"{refusals(rows_a):>13}{refusals(rows_b):>9}{refusals(rows_c):>12}"
    )
    print(f"\nwrote {outdir / 'router_comparison.json'}")


if __name__ == "__main__":
    main()
