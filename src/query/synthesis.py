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
    "two plain sentences that state the answer and cite the source document "
    "for each hop inline.\n"
    "Rules you must not break:\n"
    "- Do not add any fact that is not in the chain below.\n"
    "- Do not infer a connection between two facts unless the chain states it.\n"
    "- Do not soften or resolve a disagreement; if one is listed, say plainly "
    "that the sources disagree.\n"
    "- If the chain does not support a confident answer, say so."
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


def template_sentence(answer: Answer, graph: Graph) -> str:
    """A deterministic sentence built from the verified chain.

    Deliberately plain. It states the answer, the route, and the sources, and
    claims nothing else - a template that tried to read well would be a
    template that could be wrong in a way nobody checked.
    """
    if not answer.paths:
        return "No answer: " + (answer.note or answer.status.value)

    values = ", ".join(answer.values) or "no endpoint"
    chains = []
    for path in answer.paths:
        hops = _hops(path, graph)
        if not hops:
            continue
        chains.append(" -> ".join([hops[0]["from"]] + [h["to"] for h in hops]))
    documents = ", ".join(answer.documents)

    lead = values
    if answer.status == EvidenceStatus.CONFLICTING_EVIDENCE:
        lead = f"{values} - but the sources disagree, and the disagreement is not settled by authority tier"
    elif answer.status in (
        EvidenceStatus.FALLBACK_AMBIGUOUS,
        EvidenceStatus.PLANNED_AMBIGUOUS,
    ):
        lead = f"any of: {values}"

    route = "; ".join(dict.fromkeys(chains))
    return f"{lead}. Route: {route}. Sources: {documents}."


def _prompt(answer: Answer, graph: Graph) -> str:
    lines = [_INSTRUCTIONS, "", f"Question: {answer.question}", "", "Verified chain:"]
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
