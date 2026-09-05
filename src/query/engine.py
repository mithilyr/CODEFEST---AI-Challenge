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
from src.query.diagnostics import (
    Diagnostics,
    for_no_path,
    for_relation_unavailable,
    for_template_miss,
    for_unresolved_mention,
)
from src.query.evidence import (
    EvidenceStatus,
    check_abstention,
    classify_traversal,
    filter_endpoints,
    mentioned_in_corpus,
    resolution_status,
)
from src.query.fallback import route_by_cues
from src.query.planner import plan_and_walk
from src.query.resolve import EntityResolver, Resolution, ResolutionStatus
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
    #: What the engine established before it declined - resolved entities and
    #: their records, near-miss candidates, the relations that DO exist, how
    #: far a traversal got. Always None on an answered result: it exists so a
    #: decline renders as reasoning rather than as a bare status string
    #: (ADR-026). Built in `src/query/diagnostics.py`, because collecting it
    #: reads the graph and the UI may not.
    diagnostics: Diagnostics | None = None

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
    use_fallback: bool = True,
    use_planner: bool = False,
    planner_pool: object | None = None,
) -> Answer:
    """Answer one question, or say precisely why not.

    Three routing tiers, tried in order, each running only if the previous one
    declined: four deterministic templates (ADR-017), deterministic cue
    matching (ADR-019), then an LLM that proposes a relation chain which is
    validated against the graph and walked deterministically (ADR-020).

    Args:
        use_fallback: Set False to run the four templates alone. Exists so
            ADR-019's templates-only column stays reproducible now that the
            fallback tier ships inside this function - an ADR that tells a
            reader to run a command must keep producing the number it quotes.
        use_planner: **Defaults to False.** The two deterministic tiers are the
            product; the LLM tier is opted into, never out of. That is
            CLAUDE.md's "deterministic-first, an LLM is a fallback" stated as a
            default rather than as a comment, and it has two concrete
            consequences: no test and no eval sweep can silently spend daily
            quota or depend on a model being reachable, and a measured number
            is reproducible by construction. `src/ui/server.py` and the CLI
            opt in; the harness does not.
        planner_pool: Injected client for tests; built from
            `OPENROUTER_API_KEY` when omitted, and skipped entirely if that key
            is absent.
    """
    resolver = resolver or EntityResolver(graph)
    gazetteer = gazetteer if gazetteer is not None else build_gazetteer(graph, resolver)
    corpus_path = corpus_path or get_settings().require_corpus()
    relation_map = relation_map or load_relation_map()

    routed = route(question, graph, resolver, gazetteer)

    if isinstance(routed, RouteMiss):
        # Tier 2: deterministic cue routing. Tier 3: an LLM plan, validated
        # then walked deterministically. Each runs only when the one before it
        # declined, and each declines rather than guessing - so a question none
        # of them can route still ends at the template stage's honest miss.
        if use_fallback:
            fallback = _fallback_answer(question, graph, relation_map)
            if fallback is not None:
                return fallback
        if use_planner:
            planned = _planned_answer(question, graph, relation_map, planner_pool)
            if planned is not None:
                return planned
        return _unrouted(
            question, routed, resolver, evidence_units,
            graph=graph, gazetteer=gazetteer, relation_map=relation_map,
        )

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
            diagnostics=(
                for_relation_unavailable(
                    graph, routed.start_key, routed.chain, relation_map
                )
                if base_status == EvidenceStatus.RELATION_UNAVAILABLE
                else for_no_path(
                    graph, routed.start_key, routed.chain, paths, None, relation_map
                )
            ),
        )

    if routed.goal_key is not None:
        reached_paths = paths
        paths = [p for p in paths if p.end == routed.goal_key]
        if not paths:
            return Answer(
                question=question, status=EvidenceStatus.NO_PATH,
                template=routed.template, chain=routed.chain, start_key=routed.start_key,
                goal_key=routed.goal_key,
                note="the chain reached other endpoints but never the named goal",
                # `reached_paths`, not `paths` - the endpoints the traversal
                # actually found are the whole point of this block, and `paths`
                # has just been filtered down to the empty set.
                diagnostics=for_no_path(
                    graph, routed.start_key, routed.chain, reached_paths,
                    routed.goal_key, relation_map,
                ),
            )
        filt_status = EvidenceStatus.SUFFICIENT
    else:
        unfiltered = paths
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
            # The candidates the type filter removed are exactly what makes
            # this decline legible - F-022 recorded that they were dropped and
            # unreachable. Here they are the content of the block.
            diagnostics=for_no_path(
                graph, routed.start_key, routed.chain, unfiltered, None, relation_map
            ),
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

    if route_result.profile:
        status = EvidenceStatus.PROFILE
    elif route_result.ambiguous:
        status = EvidenceStatus.FALLBACK_AMBIGUOUS
    else:
        status = EvidenceStatus.FALLBACK_SUFFICIENT
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
            (
                "This question names no relation, so there is no single chain "
                "to walk. Below is everything the graph records about "
                f"{graph.nodes[route_result.start.key].name}, each fact with "
                "the document it came from - the entity's record, not an "
                "answer to a narrower question."
            )
            if route_result.profile
            else (
                "No template matched. Answered by cue-based fallback routing on "
                f"relation(s) {', '.join(route_result.cued) or 'n/a'}. This tier is "
                "measured at lower precision than template routing (ADR-019) - "
                "check the evidence trail."
            )
        ),
    )


def _planned_answer(
    question: str, graph: Graph, relation_map: RelationMap, pool: object | None
) -> Answer | None:
    """Third tier: an LLM plan, validated, then walked deterministically.

    Returns None whenever the planner declines - no API key, an exhausted
    rotation, a rejected plan, or a valid plan that reaches nothing. All four
    leave the caller reporting the deterministic tiers' own result, because a
    model failing to help is not new information about the corpus.

    Nothing the model said reaches the answer. It chose which chain to walk;
    `walk_relations` walked it and the evidence is the graph's.
    """
    outcome = plan_and_walk(question, graph, relation_map, pool=pool)
    if not outcome.answered or outcome.plan is None:
        return None

    ends = {p.end for p in outcome.paths}
    status = (
        EvidenceStatus.PLANNED_AMBIGUOUS
        if len(ends) > 1
        else EvidenceStatus.PLANNED_SUFFICIENT
    )
    values = tuple(
        dict.fromkeys(
            graph.nodes[p.end].name if p.end in graph.nodes else p.end
            for p in outcome.paths
        )
    )
    return Answer(
        question=question,
        status=status,
        values=values,
        template="llm_plan",
        chain=outcome.plan.relations,
        start_key=outcome.plan.start_key,
        paths=outcome.paths,
        documents=tuple(dict.fromkeys(d for p in outcome.paths for d in p.documents)),
        note=(
            "No deterministic tier matched. A model proposed the chain "
            f"{' -> '.join(outcome.plan.relations)} from "
            f"{graph.nodes[outcome.plan.start_key].name}"
            f"{f' (model: {outcome.model})' if outcome.model else ''}; every name in it "
            "was checked against the graph before traversal, and the evidence "
            "below is the graph's, not the model's."
        ),
    )


#: Word tokens for near-miss scanning. Underscores are turned into spaces
#: before this runs, so `halvard_crowhurst` is scanned as two words - a user
#: pasting an entity key should be treated like a user typing the name.
_WORD_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")

#: Longest entity name in the corpus is four words ("Cerys Sablewood the
#: Ashen"), so scanning past four buys nothing and costs comparisons.
_MAX_SPAN_WORDS = 4

#: Reporting floor, deliberately far above the resolver's own FUZZY_FLOOR of
#: 0.72. MEASURED: real typos score 0.941 ("halward crowhurst"), 0.947
#: ("gloamreac"), 0.966 ("Ederon Fellgar") and 0.968 ("Raven Stormwell"),
#: while the worst noise - a window that swallows a *correctly* spelled name
#: plus a neighbouring word, "was Ederon Fellgard" - tops out at 0.882. 0.90
#: sits in that gap. This floor governs only what we SHOW; nothing is ever
#: resolved automatically at any similarity (ADR-011).
_SUGGESTION_FLOOR = 0.90

#: Single words shorter than this are skipped. Short strings score noisily
#: against a 117-key pool and would suggest a name for words like "lair".
_MIN_SINGLE_WORD = 5

#: Ordinary English a corpus name is never made only of. A window composed
#: entirely of these cannot be a misspelt entity, so it is skipped before the
#: resolver runs - each skipped window saves 117 `difflib` comparisons, and a
#: typical question generates far more function-word windows than name-shaped
#: ones. MEASURED: 77ms -> 49ms per question on the miss path, with no change
#: to any suggestion the scan makes.
_NOT_A_NAME = frozenset(
    {
        "a", "about", "an", "and", "any", "are", "as", "at", "be", "been",
        "by", "can", "color", "colour", "did", "do", "does", "for", "from",
        "had", "has", "have", "how", "in", "is", "it", "its", "me", "must",
        "of", "on", "one", "or", "own", "recorded", "so", "tell", "that",
        "the", "their", "there", "they", "this", "to", "was", "were", "what",
        "when", "where", "which", "who", "whom", "whose", "why", "with",
        "ultimately", "also", "still", "some", "many", "much", "more", "most",
    }
)


def _best_near_miss(question: str, resolver: EntityResolver):
    """Find the likeliest misspelt entity in a question, or nothing.

    WHY THIS SCANS RATHER THAN PATTERN-MATCHES. The first version used
    `_CAPITALISED_SPAN_RE`, so it only ever saw capitalised phrases. Reported
    by a user: "halward crowhurst" (lowercase, and a v/w typo) returned a bare
    `no_template_match` with no suggestion, while "Halward Crowhurst" got the
    suggestion. The resolver had no difficulty with either - it scores both at
    0.941 against `Halvard Crowhurst` - but the lowercase spelling never
    reached it, because the regex demanded capitals. People typing into a
    search box do not capitalise, and they paste entity keys with underscores.

    Returns (span, resolution) or (None, None).
    """
    text = question.replace("_", " ")
    tokens = _WORD_TOKEN_RE.findall(text)
    best: tuple[float, str, object] | None = None

    for size in range(1, _MAX_SPAN_WORDS + 1):
        for start in range(len(tokens) - size + 1):
            window = tokens[start : start + size]
            if all(w.lower() in _NOT_A_NAME for w in window):
                continue
            span = _strip_possessive(" ".join(window))
            if size == 1 and len(span) < _MIN_SINGLE_WORD:
                continue
            resolution = resolver.resolve(span)

            # A span that resolves for real means the question DOES name a
            # known entity, so the miss is about routing or relations, not
            # spelling. Suggesting a typo here would be wrong and confusing:
            # "Who was Ederon Fellgard's mentor?" names the man correctly and
            # fails because the corpus records no mentor.
            if resolution.resolved:
                return None, None

            if resolution.status == ResolutionStatus.AMBIGUOUS and resolution.candidates:
                if _resolves_when_bare_s_dropped(span, resolver):
                    # F-026: "isolde mournvales" for "Isolde Mournvale's" -
                    # spelled correctly, just missing the apostrophe entirely.
                    # `_strip_possessive` only strips a marked possessive; this
                    # catches the unmarked one without a typo suggestion.
                    return None, None
                score = resolution.candidates[0].similarity
                if score >= _SUGGESTION_FLOOR and (best is None or score > best[0]):
                    best = (score, span, resolution)

    if best is None:
        return None, None
    return best[1], best[2]


def _strip_possessive(span: str) -> str:
    """Drop a trailing possessive so a correct name is not reported as a typo.

    `_CAPITALISED_SPAN_RE` captures "Ederon Fellgard's" whole. Resolved as-is
    that span is ambiguous at 0.938 against the real `Ederon Fellgard`, so the
    near-miss reporter below announced "'Ederon Fellgard's' is not a name in
    the corpus" for a question that spelled the name perfectly - suggesting a
    typo where there was none. The corpus uses U+2019 apostrophes as well as
    ASCII ones (CLAUDE.md corpus fact 6), so both are stripped.
    """
    for suffix in ("'s", "’s", "'", "’"):
        if span.endswith(suffix):
            return span[: -len(suffix)]
    return span


def _resolves_when_bare_s_dropped(span: str, resolver: EntityResolver) -> bool:
    """True if dropping an unmarked trailing "s" makes `span` resolve cleanly.

    F-026: `_strip_possessive` only catches a *marked* possessive - "Ederon
    Fellgard's". Three of 49 frozen questions omit the apostrophe entirely
    ("isolde mournvales", "ederon fellgards", "ravena stormwells"), spelled
    correctly apart from that, and the reporter announced each as a typo -
    a regression from the more specific `relation_unavailable` these
    questions got before the near-miss reporter existed.

    Deliberately narrow, per F-026's own caution that a bare `s`-strip "is not
    obviously safe against plurals and names ending in s": this function never
    widens what gets *suggested* as a typo, only suppresses a suggestion when
    the trimmed form resolves through `resolve()`'s exact/normalised/alias
    tiers - never fuzzy (ADR-011), so it can only fire when the trimmed span
    is byte-for-byte a real canonical key. MEASURED against the corpus's own
    risk case: 11 entity names themselves end in "s" ("Ashfall Colossus",
    "Embercrag Fortress", ...); none of their bare-s-stripped forms collide
    with a different entity, so a correctly-spelled mention of one of them
    never reaches this function in the first place - it already resolves
    before `_best_near_miss` considers it a candidate at all.
    """
    if len(span) < 2 or not span.endswith("s"):
        return False
    return resolver.resolve(span[:-1]).resolved


def _unrouted(
    question: str,
    miss: RouteMiss,
    resolver: EntityResolver,
    evidence_units: list | None,
    *,
    graph: Graph,
    gazetteer: list[tuple[str, str]],
    relation_map: RelationMap,
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
    # A near-miss spelling must be *reported*, not swallowed. Asked
    # "Who is Raven Stormwell?" the resolver finds `Ravena Stormwell` at 0.968
    # and correctly refuses to pick it (ADR-011: `caedmon_fellgard` and
    # `ederon_fellgard` sit at 0.839, so any threshold loose enough to accept
    # 0.968 eventually merges two real people). But refusing to guess is not a
    # reason to withhold what we found - the old behaviour returned a bare
    # NO_TEMPLATE_MATCH and never mentioned the candidate, leaving a user with
    # a typo no way to discover it.
    #
    # Reporting is safe where guessing is not: `AMBIGUOUS_ENTITY` carries the
    # candidates and their similarities for the caller to show, and the system
    # still resolves nothing on its own. Only a span the resolver itself
    # classified AMBIGUOUS qualifies - one it found nothing for at all (e.g.
    # "Ashen Era") stays an ordinary template miss.
    span, resolution = _best_near_miss(question, resolver)
    if resolution is not None:
        suggestions = ", ".join(
            f"{c.name} ({c.similarity:.3f})" for c in resolution.candidates[:3]
        )
        return Answer(
            question=question,
            status=EvidenceStatus.AMBIGUOUS_ENTITY,
            resolutions=(resolution,),
            diagnostics=for_unresolved_mention(
                graph, resolution, relation_map, evidence_units
            ),
            note=(
                f"{span!r} is not a name in the corpus. Closest: "
                f"{suggestions}. Resolution is exact-match only and never "
                f"picks a winner (ADR-011) - retry with the exact name."
            ),
        )

    if "no resolved entity" not in miss.reason and "did not find exactly one" not in miss.reason:
        # The dominant decline: 18 of 23 on the frozen robustness set. It used
        # to carry `miss.reason` and nothing else, which on screen is a red
        # word where an answer should be. It now carries whichever entities the
        # question named that the graph does know, each with its record, plus
        # the closed relation vocabulary that bounds what could have been
        # asked (ADR-026).
        return Answer(
            question=question,
            status=EvidenceStatus.NO_TEMPLATE_MATCH,
            note=miss.reason,
            diagnostics=for_template_miss(
                question, graph, resolver, gazetteer, relation_map
            ),
        )

    for candidate in _CAPITALISED_SPAN_RE.findall(question):
        resolution = resolver.resolve(candidate)
        if resolution.resolved:
            continue  # a real entity resolved; the miss was about routing, not resolution.
        status = resolution_status(resolution) or EvidenceStatus.UNRESOLVED_ENTITY
        if status == EvidenceStatus.UNRESOLVED_ENTITY and evidence_units is not None:
            if mentioned_in_corpus(candidate, evidence_units):
                status = EvidenceStatus.OUTSIDE_STRUCTURED_COVERAGE
        return Answer(
            question=question, status=status, resolutions=(resolution,),
            note=miss.reason,
            diagnostics=for_unresolved_mention(
                graph, resolution, relation_map, evidence_units
            ),
        )

    # No start entity is known on this branch - a trigger fired but nothing in
    # the question resolved - so `for_relation_unavailable` has nothing to
    # describe. The template-miss block is the honest one here: it reports what
    # (if anything) was recognised, and says so plainly when that is nothing.
    return Answer(
        question=question,
        status=EvidenceStatus.RELATION_UNAVAILABLE,
        note=miss.reason,
        diagnostics=for_template_miss(
            question, graph, resolver, gazetteer, relation_map
        ),
    )


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
