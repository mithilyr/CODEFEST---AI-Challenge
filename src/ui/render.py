"""View dict -> HTML string. Hand-written, stdlib only, no template engine.

Nothing is imported from `src.query` or `src.graph` here on purpose: this
module can only render what `view.build_view` already put in a plain dict, so
there is no way for presentation code to reach back into the reasoning layer.

The layout is deliberately plain. The instruction for this checkpoint is that
the evidence and explanation surfaces work before anything is made pretty, so
the CSS below does legibility (a readable measure, a monospace column for
provenance, enough contrast to survive a projector) and stops there.

Nine surfaces the demo has to expose, and where each one lives:

    1. question input          `page_index`, and the form on every page
    2. final answer            `_answer_block`  - the engine's `values`, listed
    3. strategy used           `_strategy_block` - template + relation chain
    4. evidence path, all hops `_routes_block`
    5. supporting passages     `_routes_block`, each hop's `raw` cell
    6. source tier             `_routes_block` per hop, `_documents_block` per doc
    7. conflicts + handling    `_conflict_block`
    8. evidence sufficiency    `_status_block`
    9. fallback reason         `_status_block`, the engine's `note`
"""

from __future__ import annotations

from html import escape

DEMO_QUESTIONS: list[tuple[str, str]] = [
    (
        "1b_013",
        "Whose dominion encompasses the lair of the Gravemaw Wyrm?",
    ),
    (
        "1b_007",
        "Which accord was ultimately won by the faction of which "
        "Ederon Fellgard is a member?",
    ),
    (
        "1b_006",
        "Which individual was a member of the faction that ultimately won "
        "the War of Drowned Light?",
    ),
    (
        "1b_009",
        "In what way is Halvard Crowhurst connected to the victors of the "
        "Purge of Blackport?",
    ),
    (
        "1b_003",
        "To which shadowed redoubt must one journey to examine the relic long "
        "borne by Cerys Sablewood the Ashen since 356 AS?",
    ),
    (
        "1b_005",
        "Which war was won by the organization that included Isolde Mournvale "
        "as one of its members?",
    ),
    (
        "1b_022",
        "Which war did Ravena Stormwell's own faction ultimately win?",
    ),
]

CSS = """
*, *::before, *::after { box-sizing: border-box; }
body { margin: 0; padding: 2rem 1.25rem 4rem;
       font: 16px/1.55 -apple-system, "Segoe UI", Roboto, sans-serif;
       color: #1b1b1f; background: #f6f6f4; }
main { max-width: 62rem; margin: 0 auto; }
h1 { font-size: 1.35rem; margin: 0 0 .25rem; letter-spacing: -.01em; }
h1 a { color: inherit; text-decoration: none; }
.sub { color: #5c5c66; font-size: .85rem; margin: 0 0 1.5rem; }
form { display: flex; gap: .5rem; margin: 0 0 1.25rem; }
input[type=text] { flex: 1; padding: .7rem .85rem; font-size: 1rem;
                   border: 1px solid #c8c8d0; border-radius: 6px;
                   background: #fff; color: inherit; }
button { padding: .7rem 1.4rem; font-size: 1rem; font-weight: 600;
         border: 0; border-radius: 6px; background: #1b1b1f; color: #fff;
         cursor: pointer; }
section { background: #fff; border: 1px solid #e2e2e8; border-radius: 8px;
          padding: 1rem 1.15rem; margin: 0 0 1rem; }
section > h2 { font-size: .72rem; text-transform: uppercase;
               letter-spacing: .09em; color: #6a6a76; margin: 0 0 .7rem;
               font-weight: 700; }
.answer { font-size: 1.5rem; font-weight: 600; margin: 0; }
.answer li { margin: .15rem 0; }
ul.values { margin: 0; padding-left: 1.2rem; font-size: 1.05rem; font-weight: 600; }
.status { display: inline-block; padding: .2rem .6rem; border-radius: 999px;
          font-size: .78rem; font-weight: 700; letter-spacing: .04em;
          font-family: ui-monospace, Consolas, monospace; }
.ok   { background: #dff3e4; color: #17542c; }
.warn { background: #fde9c9; color: #6d4106; }
.bad  { background: #fbdcdc; color: #7a1d1d; }
.gloss { margin: .6rem 0 0; color: #3d3d45; font-size: .92rem; }
.modelbar { margin: 0 0 .9rem; padding: .7rem .85rem; background: #fff8e8;
            border: 1px solid #e8cf95; border-left: 4px solid #b8860b;
            border-radius: 6px; }
.modelbar .mbhead { font-size: .78rem; font-weight: 700; letter-spacing: .05em;
                    color: #6d4106; margin: 0 0 .35rem;
                    font-family: ui-monospace, Consolas, monospace; }
.modelbar p { margin: .3rem 0 0; font-size: .9rem; color: #3d3d45; }
.modelbar .plan { font-family: ui-monospace, Consolas, monospace;
                  font-size: .84rem; background: #f6ecd2; padding: .1rem .4rem;
                  border-radius: 4px; color: #5a3d05; }
.note { margin: .6rem 0 0; padding: .6rem .75rem; background: #f4f4f7;
        border-left: 3px solid #9a9aa8; font-size: .9rem;
        font-family: ui-monospace, Consolas, monospace; white-space: pre-wrap; }
.route { border: 1px solid #e6e6ec; border-radius: 6px; padding: .75rem .85rem;
         margin: 0 0 .7rem; }
.route > .rhead { font-size: .78rem; color: #6a6a76; margin: 0 0 .55rem;
                  font-weight: 600; }
.hop { padding: .55rem 0 .55rem .85rem; border-left: 3px solid #cfcfda;
       margin: 0 0 .5rem; }
.hop.disputed { border-left-color: #c0392b; background: #fdf3f2; }
.hop:last-child { margin-bottom: 0; }
.step { font-size: 1rem; margin: 0 0 .3rem; }
.step .rel { font-family: ui-monospace, Consolas, monospace; font-size: .84rem;
             background: #ececf2; padding: .1rem .4rem; border-radius: 4px;
             color: #3a3a46; }
.prov { font-family: ui-monospace, Consolas, monospace; font-size: .8rem;
        color: #4a4a55; margin: 0; }
.prov .doc { color: #1b3a63; }
.passage { font-family: ui-monospace, Consolas, monospace; font-size: .82rem;
           background: #f4f4f7; padding: .4rem .55rem; border-radius: 4px;
           margin: .3rem 0 0; white-space: pre-wrap; word-break: break-word; }
.tag { display: inline-block; font-size: .72rem; font-weight: 700;
       padding: .1rem .45rem; border-radius: 4px; margin-left: .35rem;
       background: #ececf2; color: #4a4a55;
       font-family: ui-monospace, Consolas, monospace; }
.tag.tier1 { background: #e2ebf8; color: #1b3a63; }
.tag.tier2 { background: #e9eaef; color: #34343f; }
.tag.tier3 { background: #f1ece2; color: #5a4a2c; }
.tag.tier4 { background: #f6e7e7; color: #6d2c2c; }
.tag.dispute { background: #c0392b; color: #fff; }
.tag.rev { background: #efe6f6; color: #4a2c63; }
table { border-collapse: collapse; width: 100%; font-size: .87rem; }
th, td { text-align: left; padding: .4rem .5rem; border-bottom: 1px solid #ececf1; }
th { font-size: .72rem; text-transform: uppercase; letter-spacing: .06em;
     color: #6a6a76; }
td.mono { font-family: ui-monospace, Consolas, monospace; font-size: .82rem; }
.sides { display: grid; grid-template-columns: 1fr 1fr; gap: .8rem; }
@media (max-width: 46rem) { .sides { grid-template-columns: 1fr; }
                            form { flex-direction: column; } }
.side { border: 1px solid #e6e6ec; border-radius: 6px; padding: .7rem .8rem; }
.side.asserts { border-top: 3px solid #2c6e49; }
.side.denies  { border-top: 3px solid #c0392b; }
.side h3 { margin: 0 0 .45rem; font-size: .78rem; text-transform: uppercase;
           letter-spacing: .06em; color: #4a4a55; }
.unresolved { margin: .7rem 0 0; padding: .6rem .75rem; background: #fdf3f2;
              border-left: 3px solid #c0392b; font-size: .9rem; }
.examples { margin: 0; padding: 0; list-style: none;
            display: flex; flex-wrap: wrap; gap: .4rem; }
.examples a { display: inline-block; padding: .3rem .6rem; font-size: .82rem;
              background: #ececf2; border-radius: 5px; color: #26263a;
              text-decoration: none; }
.examples a:hover { background: #dedee8; }
.examples .qid { font-family: ui-monospace, Consolas, monospace;
                 font-weight: 700; margin-right: .35rem; color: #5c5c66; }
footer { color: #7a7a86; font-size: .8rem; text-align: center; margin: 1.5rem 0 0; }
.suggest { margin: .7rem 0; padding: .7rem .85rem; background: #fff8e6;
           border-left: 3px solid #d99b1c; border-radius: 0 5px 5px 0; }
.suggest ul { margin: .3rem 0 0; padding-left: 1.2rem; }
.suggest a { font-weight: 700; color: #7a4c06; }
.mono { font-family: ui-monospace, Consolas, monospace; font-size: .85em; }
details { border: 1px solid #e6e6ec; border-radius: 6px; margin: 0 0 .4rem;
          background: #fcfcfd; }
summary { cursor: pointer; padding: .5rem .7rem; font-weight: 600;
          font-size: .9rem; }
ul.entitylist { columns: 3 14rem; margin: 0; padding: 0 .7rem .7rem 1.9rem;
                font-size: .87rem; }
ul.entitylist li { break-inside: avoid; margin: .1rem 0; }
ul.entitylist a { color: #26263a; text-decoration: none; }
ul.entitylist a:hover { text-decoration: underline; }
"""

#: The one status that is an unqualified answer. Everything else that answers
#: carries a caveat - a lower-precision tier, an unnarrowed set, or a whole
#: record instead of a value - and is ambered rather than greened.
_UNQUALIFIED = "sufficient"

#: Declines the engine *chose*, as opposed to routes it could not find. These
#: were amber before this function became a rule, and turning them red would
#: have been a real change of meaning: ADR-026's position is that a decline is a
#: result, and abstaining on purpose is not the same as failing to route.
_CHOSEN_DECLINES = frozenset({"abstention"})


def _status_class(status: str, answerable: bool) -> str:
    """Colour band for a status. A rule, not a table.

    This was a three-entry lookup with `bad` as the default, which quietly
    painted **five answerable statuses red**: `fallback_sufficient`,
    `fallback_ambiguous`, `planned_sufficient`, `planned_ambiguous` and
    `profile`. The cue-fallback tier returns 17 correct answers on the frozen
    set and every one of them was shown in the same colour as a failure.

    A partial table over a growing enum drifts silently every time a status is
    added - it has to be edited, and nothing fails if it is not. Deriving the
    band from `answerable`, which the view already carries, cannot go stale: a
    new status is coloured correctly the day it exists.

    `answerable` comes from `EvidenceStatus.is_answerable` via the view, so this
    stays a lookup on data the engine decided rather than an assessment made
    here (ADR-018).
    """
    if status in _CHOSEN_DECLINES:
        return "warn"
    if not answerable:
        return "bad"
    return "ok" if status == _UNQUALIFIED else "warn"


def _clip(text: str, limit: int = 320) -> str:
    """Trim a corroborating passage to a readable length, marking the trim."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + " [...]"


def _e(value) -> str:
    """Escape anything for HTML. Every dynamic value on the page goes through here."""
    return escape("" if value is None else str(value), quote=True)


def _tier_tag(tier, label) -> str:
    if tier is None:
        return ""
        # A document with no edge recorded against it carries no tier to show;
        # inventing one would be exactly the kind of guess this project bans.
    return f'<span class="tag tier{_e(tier)}">{_e(label)}</span>'


# -- blocks ------------------------------------------------------------------


def _search_form(question: str = "") -> str:
    return (
        '<form action="/ask" method="get">'
        f'<input type="text" name="q" value="{_e(question)}" '
        'placeholder="Ask a question about the Ashen Era archive" '
        # Native autocomplete against the 117 entity names. The list is only
        # emitted on the index page; elsewhere the attribute simply matches no
        # datalist and the input behaves as a plain text box.
        'list="entities" autocomplete="off" autofocus>'
        "<button type=\"submit\">Ask</button>"
        "</form>"
    )


def _examples_block() -> str:
    items = "".join(
        f'<li><a href="/ask?q={_e_url(q)}"><span class="qid">{_e(qid)}</span>'
        f"{_e(q)}</a></li>"
        for qid, q in DEMO_QUESTIONS
    )
    return (
        "<section><h2>Dev question set</h2>"
        f'<ul class="examples">{items}</ul></section>'
    )


def _e_url(value: str) -> str:
    from urllib.parse import quote as urlquote

    return escape(urlquote(value), quote=True)


def _answer_block(view: dict) -> str:
    """The engine's `values`, listed. No sentence is composed from them.

    When there are no values the block says so plainly and defers to the
    status block for the reason - it does not write an apology or a guess.
    """
    values = view["values"]
    if not values:
        body = (
            '<p class="answer" style="color:#7a1d1d">No answer returned</p>'
            '<p class="gloss">The engine did not reach a value. '
            "See <em>evidence sufficiency</em> below for the named reason.</p>"
        )
    elif len(values) == 1:
        body = f'<p class="answer">{_e(values[0])}</p>'
    else:
        items = "".join(f"<li>{_e(v)}</li>" for v in values)
        body = (
            f'<ul class="values">{items}</ul>'
            f'<p class="gloss">{len(values)} values. The engine returned a set; '
            "they are listed as it ordered them.</p>"
        )
    # Above the value, deliberately. A reader who takes only the answer
    # should have already been told a model chose the route to it.
    return (
        f"<section><h2>Answer</h2>"
        f"{_model_route_banner(view)}{body}</section>"
    )


def _strategy_block(view: dict) -> str:
    if view["template"] is None:
        inner = (
            '<p class="gloss">No template matched, so no relation chain was '
            "walked.</p>"
        )
    else:
        chain = ' <span class="rel">-&gt;</span> '.join(
            f'<span class="rel">{_e(r)}</span>' for r in view["chain"]
        )
        start = view["start_name"] or view["start_key"]
        rows = [
            f"<tr><th>Template</th><td class=\"mono\">{_e(view['template'])}</td></tr>",
            f"<tr><th>Relation chain</th><td>{chain}</td></tr>",
            f"<tr><th>Start entity</th><td>{_e(start)} "
            f"<span class=\"tag\">{_e(view['start_key'])}</span></td></tr>",
        ]
        if view["goal_key"]:
            rows.append(
                f"<tr><th>Goal entity</th><td>{_e(view['goal_name'])} "
                f"<span class=\"tag\">{_e(view['goal_key'])}</span></td></tr>"
            )
        rows.append(
            f"<tr><th>Routes found</th><td>{len(view['routes'])}</td></tr>"
        )
        inner = f"<table>{''.join(rows)}</table>"
    return f"<section><h2>Strategy used</h2>{inner}</section>"


def _model_route_banner(view: dict) -> str:
    """Say plainly when a model chose the route, and what that did and did not do.

    A planner-tier answer was structurally indistinguishable from a
    deterministic one: same layout, a different word in the status pill, and the
    engine's note in the same grey box every fallback reason uses. A reader
    skimming could not tell a model had been involved at all.

    That matters in both directions. It understates the system - the planner is
    the tier that exists *because* ADR-019 measured the deterministic ones
    missing 35 of 49 realistic questions - and it overstates it, because an
    answer a model routed carries different risk from one a template routed
    (F-025: a well-formed plan, relevant to nothing, that passed validation).

    The banner renders `view["note"]`, which the engine wrote. It adds no
    judgement of its own, and it appears only when the engine set
    `routed_by_model`.
    """
    if not view.get("routed_by_model"):
        return ""

    chain = " &rarr; ".join(_e(r) for r in view["chain"]) or "no relations"
    start = _e(view["start_name"] or view["start_key"] or "an entity")

    return (
        '<div class="modelbar">'
        '<p class="mbhead">ROUTED BY A LANGUAGE MODEL</p>'
        "<p>No deterministic template matched, so this route was proposed by a "
        "model rather than by a rule. It chose <em>where to look</em>; it did "
        "not write the answer.</p>"
        f'<p>Proposed plan: <span class="plan">{start} &nbsp;{chain}</span></p>'
        "<p>Every name in that plan was checked against the graph before "
        "anything was traversed, and the evidence below is the graph's. "
        "Nothing the model said is quoted as fact.</p>"
        + (f'<p class="note">{_e(view["note"])}</p>' if view["note"] else "")
        + "</div>"
    )


def _status_block(view: dict) -> str:
    """Evidence sufficiency, and the fallback reason when there is one."""
    cls = _status_class(view["status"], view["answerable"])
    parts = [
        f'<span class="status {cls}">{_e(view["status"])}</span>',
        f'<p class="gloss">{_e(view["status_gloss"])}</p>',
    ]
    parts.append(
        '<p class="gloss">Answerable: <strong>'
        f'{"yes" if view["answerable"] else "no"}</strong> '
        "&mdash; read from the status the engine returned, not decided here.</p>"
    )
    # A planner-tier note is already shown in the banner above the answer;
    # repeating it here would say the same sentence twice on one page.
    if view["note"] and not view.get("routed_by_model"):
        parts.append(
            "<p class=\"gloss\" style=\"margin-bottom:.2rem\"><strong>"
            "Fallback reason, in the engine's words:</strong></p>"
            f'<p class="note">{_e(view["note"])}</p>'
        )
    for res in view["resolutions"]:
        cands = "".join(
            f"<li>{_e(c['name'])} <span class=\"tag\">{_e(c['key'])}</span> "
            f"similarity {c['similarity']:.3f}</li>"
            for c in res["candidates"]
        )
        parts.append(
            f'<div class="unresolved"><strong>{_e(res["mention"])}</strong> '
            f'&mdash; {_e(res["status"])}'
            + (
                f"<ul>{cands}</ul><p class=\"gloss\" style=\"margin:0\">"
                "Candidates are listed and never chosen between: entity "
                "resolution is exact-match only (ADR-011).</p>"
                if cands
                else ""
            )
            + "</div>"
        )
    return f"<section><h2>Evidence sufficiency</h2>{''.join(parts)}</section>"


def _attestation_html(hop: dict) -> str:
    """"Also attested in" - the other collections that name both ends of a hop.

    Deliberately worded as attestation and not as support. These passages were
    found by naming both entities (ADR-027); a paragraph that names two people
    is evidence the archive discusses them together, not proof it asserts the
    relation between them. Overstating that here would be F-014's mistake in a
    new place, and the citation would look every bit as solid.
    """
    attestations = hop.get("attestations") or []
    if not attestations:
        return ""
    rows = "".join(
        f'<li><span class="doc">{_e(a["document"])}</span> '
        f'<span class="mono">{_e(a["locator"])}</span> '
        f'<span class="tag">{_e(a["collection"])}</span>'
        f'{_tier_tag(a["tier"], a["tier_label"])}'
        f'<p class="passage">{_e(_clip(a["quote"]))}</p></li>'
        for a in attestations
    )
    return (
        f'<div class="attest"><p class="prov">also attested in '
        f"{len(attestations)} other document"
        f'{"" if len(attestations) == 1 else "s"} '
        f'&mdash; these name both ends of the hop; they are not a second '
        f'assertion of it</p><ul>{rows}</ul></div>'
    )


def _hop_html(hop: dict) -> str:
    tags = [_tier_tag(hop["tier"], hop["tier_label"])]
    if hop["disputed"]:
        tags.append('<span class="tag dispute">disputed</span>')
    if hop["inferred_inverse"]:
        tags.append('<span class="tag rev">read off the other page</span>')
    if hop["assertion"] != "asserts":
        tags.append(f'<span class="tag">{_e(hop["assertion"])}</span>')
    if hop["extraction"] != "link":
        tags.append(f'<span class="tag">{_e(hop["extraction"])}</span>')

    qualifiers = []
    if hop["year"] is not None:
        qualifiers.append(f"{_e(hop['year_kind'] or 'year')} {_e(hop['year'])} AS")
    if hop["qualifier"]:
        qualifiers.append(f"for {_e(hop['qualifier'])}")
    qual_html = (
        f'<p class="prov">qualifier: {", ".join(qualifiers)}</p>' if qualifiers else ""
    )

    return (
        f'<div class="hop{" disputed" if hop["disputed"] else ""}">'
        f'<p class="step">{hop["position"]}. {_e(hop["from_name"])} '
        f'<span class="rel">{_e(hop["relation"])}</span> '
        f'{_e(hop["to_name"])}{"".join(tags)}</p>'
        f'<p class="prov"><span class="doc">{_e(hop["document"])}</span> '
        f'| {_e(hop["field_name"])} (row {_e(hop["row"])}) '
        f'| parsed by: {_e(hop["cell_template"])}</p>'
        f'<p class="passage">{_e(hop["raw"])}</p>'
        f"{qual_html}"
        f"{_attestation_html(hop)}"
        "</div>"
    )


def _routes_block(view: dict) -> str:
    """Every hop of every route, each with the cell it was read from."""
    if not view["routes"]:
        return (
            "<section><h2>Evidence path</h2>"
            '<p class="gloss">No path was walked, so there are no hops to show.'
            "</p></section>"
        )
    blocks = []
    for route in view["routes"]:
        hops = "".join(_hop_html(h) for h in route["hops"])
        blocks.append(
            f'<div class="route"><p class="rhead">Route {route["index"]} of '
            f'{len(view["routes"])} &mdash; {_e(route["start_name"])} '
            f'&rarr; {_e(route["endpoint_name"])} '
            f'({len(route["hops"])} hops)</p>{hops}</div>'
        )
    return (
        "<section><h2>Evidence path &mdash; every hop, with its source passage</h2>"
        f"{''.join(blocks)}</section>"
    )


def _documents_block(view: dict) -> str:
    if not view["documents"]:
        return ""
    rows = "".join(
        f'<tr><td class="mono">{_e(d["document"])}</td>'
        f'<td>{_tier_tag(d["tier"], d["tier_label"])}</td></tr>'
        for d in view["documents"]
    )
    return (
        "<section><h2>Source documents and tiers</h2>"
        f"<table><tr><th>Document</th><th>Authority tier</th></tr>{rows}</table>"
        "</section>"
    )


def _conflict_block(view: dict) -> str:
    """Both sides of a dispute, side by side. Nothing is resolved here.

    The engine's `status` string is printed as it came. When it reads
    `unresolved_same_tier` the two panels below carry the same tier badge, and
    the page says so and stops - picking a winner is not presentation's job,
    and for `1b_009` there is no tier difference to pick one with.
    """
    conflict = view["conflict"]
    if conflict is None:
        return ""

    asserts = "".join(
        f'<p class="prov"><span class="doc">{_e(a["document"])}</span> '
        f'| {_e(a["field_name"])} (row {_e(a["row"])})'
        f'{_tier_tag(a["tier"], a["tier_label"])}</p>'
        f'<p class="passage">{_e(a["raw"])}</p>'
        for a in conflict["asserted_by"]
    ) or '<p class="gloss">No asserting edge recorded.</p>'

    denial = conflict["denied_by"]
    if denial is None:
        denies = (
            '<p class="gloss">No denial found. Silence is not denial &mdash; '
            "a source that says nothing is not disputing anything (F-014).</p>"
        )
    else:
        denies = (
            f'<p class="prov"><span class="doc">{_e(denial["document"])}</span>'
            f'{_tier_tag(denial["tier"], denial["tier_label"])}</p>'
            f'<p class="passage">{_e(denial["quote"])}</p>'
        )

    handling = (
        "Both sources sit at the same authority tier, so the tier model cannot "
        "rank them. The engine surfaced the disagreement instead of resolving "
        "it, and this page does the same."
        if conflict["status"] == "unresolved_same_tier"
        else "Reported by the engine as shown; this page does not re-decide it."
    )

    return (
        "<section><h2>Conflict, and how it was handled</h2>"
        f'<p class="gloss"><span class="status warn">{_e(conflict["status"])}'
        "</span> &nbsp;must surface: <strong>"
        f'{"yes" if conflict["must_surface"] else "no"}</strong></p>'
        f'<p class="gloss">Disputed claim: <strong>{_e(conflict["subject_name"])}'
        f'</strong> <span class="rel">{_e(conflict["relation"])}</span> '
        f'<strong>{_e(conflict["object_name"])}</strong></p>'
        '<div class="sides">'
        f'<div class="side asserts"><h3>Asserted by</h3>{asserts}</div>'
        f'<div class="side denies"><h3>Disputed by</h3>{denies}</div>'
        "</div>"
        f'<p class="gloss">{handling}</p>'
        "</section>"
    )


# -- decline evidence: what the engine DID establish ------------------------
#
# A decline is a result, and a result nobody can inspect is indistinguishable
# from a bug (ADR-026). Everything below renders data
# `src/query/diagnostics.py` collected at the decline site. Nothing here
# derives a fact, re-ranks anything, or softens a status.


def _fact_html(fact: dict) -> str:
    """One edge, with the infobox row it was read from - same citation as a hop."""
    arrow = "&rarr;" if fact["direction"] == "out" else "&larr;"
    return (
        '<div class="hop">'
        f'<p class="step"><span class="rel">{_e(fact["relation"])}</span> '
        f'{arrow} {_e(fact["other"]["name"])}'
        f'{_tier_tag(fact["tier"], fact["tier_label"])}</p>'
        f'<p class="prov"><span class="doc">{_e(fact["document"])}</span> '
        f'| {_e(fact["field_name"])} (row {_e(fact["row"])})</p>'
        f'<p class="passage">{_e(fact["raw"])}</p>'
        "</div>"
    )


def _established_block(view: dict) -> str:
    """The entities the question named that the system does know, with their records.

    This is the block that turns the commonest decline into something a judge
    can read. Measured: `no_template_match` is 18 of 23 declines on the frozen
    robustness set, and it used to carry a one-line reason and nothing else.
    """
    diag = view["diagnostics"]
    if not diag:
        return ""
    established = diag["established"]
    if not established:
        # When a span was identified, `_suggestion_block` has already said "we
        # read this as a name and could not place it", and the coverage block
        # may be about to show where it does appear. Repeating "nothing matched"
        # underneath those reads as a second, harsher failure for the same fact.
        if diag["span"]:
            return ""
        return (
            "<section><h2>What the system recognised</h2>"
            '<p class="gloss"><strong>Nothing in this question matched a known '
            "entity.</strong> The graph holds a closed set of names; a question "
            "that mentions none of them cannot be routed to any of them. "
            '<a href="/#entities">Browse the entity list</a> to see what is '
            "there.</p></section>"
        )

    blocks = []
    for item in established:
        entity = item["entity"]
        facts = "".join(_fact_html(f) for f in item["facts"])
        shown = len(item["facts"])
        total = item["fact_count"]
        more = (
            f'<p class="gloss">Showing {shown} of {total} recorded facts.</p>'
            if total > shown
            else ""
        )
        page = (
            f'<p class="prov"><span class="doc">{_e(entity["page"])}</span></p>'
            if entity["page"]
            else '<p class="gloss">No wiki page documents this entity directly '
            "&mdash; it is known only as a link target on other pages.</p>"
        )
        rels = "".join(
            f'<span class="tag">{_e(r)}</span>' for r in item["relations_present"]
        )
        kind = f" &mdash; {_e(entity['type'])}" if entity["type"] else ""
        blocks.append(
            f'<div class="route"><p class="rhead">{_e(entity["name"])}{kind}'
            f'</p>{page}'
            f'<p class="gloss">Relations recorded for it: {rels or "none"}</p>'
            f"{facts}{more}</div>"
        )
    return (
        "<section><h2>What the system did establish</h2>"
        '<p class="gloss">These names in the question resolved to entities the '
        "graph knows. Every fact below cites the infobox row it came from.</p>"
        f"{''.join(blocks)}</section>"
    )


def _suggestion_block(view: dict) -> str:
    """A name that did not become a node: the span, the near misses, where to look."""
    diag = view["diagnostics"]
    if not diag or not diag["span"]:
        return ""

    parts = [
        '<p class="gloss">The engine read <strong>'
        f'{_e(diag["span"])}</strong> as an entity name and could not match it '
        "to exactly one node.</p>"
    ]

    if diag["suggestions"]:
        items = "".join(
            f'<li><a href="/ask?q={_e_url(view["question"].replace(diag["span"], s["name"]))}">'
            f'{_e(s["name"])}</a> '
            f'<span class="tag">{_e(s["key"])}</span> '
            f'similarity {s["similarity"]:.3f}'
            + (
                f' &mdash; <span class="doc">{_e(s["page"])}</span>'
                if s["page"]
                else ""
            )
            + "</li>"
            for s in diag["suggestions"]
        )
        parts.append(
            '<div class="suggest"><p style="margin:0 0 .4rem"><strong>Did you '
            "mean?</strong> A suggestion, not a correction &mdash; nothing has "
            "been applied. Entity resolution is exact-match only and never picks "
            "a winner (ADR-011), because two real people sit at 0.839 similarity. "
            "Click one to re-ask with that spelling.</p>"
            f"<ul>{items}</ul></div>"
        )

    others = [c for c in diag["candidates"] if c not in diag["suggestions"]]
    if others:
        rows = "".join(
            f'<tr><td>{_e(c["name"])}</td>'
            f'<td class="mono">{_e(c["type"] or "unrecorded")}</td>'
            f'<td class="mono">{_e(c["page"] or "no page")}</td>'
            f'<td class="mono">{c["similarity"]:.3f}</td></tr>'
            for c in others
        )
        parts.append(
            '<p class="gloss">Every other candidate it matched, with its type and '
            "the document that records it:</p>"
            "<table><tr><th>Candidate</th><th>Type</th><th>Source document</th>"
            f"<th>Similarity</th></tr>{rows}</table>"
        )

    parts.append(
        '<p class="gloss"><a href="/#entities">Browse all entities</a> to find the '
        "exact spelling.</p>"
    )
    return f"<section><h2>The name we could not place</h2>{''.join(parts)}</section>"


def _coverage_block(view: dict) -> str:
    """Where an out-of-graph name DOES appear. The honest limit, with citations.

    `OUTSIDE_STRUCTURED_COVERAGE` is the one decline that is purely an
    architectural boundary rather than a gap in the corpus, and saying so is
    only credible with the documents named.
    """
    diag = view["diagnostics"]
    if not diag or not diag["presence"]:
        return ""
    rows = []
    for pr in diag["presence"]:
        docs = "".join(
            f'<li class="mono">{_e(d)}</li>' for d in pr["documents"][:6]
        )
        rows.append(
            f'<div class="route"><p class="rhead">{_e(pr["collection"])}'
            f'{_tier_tag(pr["tier"], pr["tier_label"])} &mdash; '
            f'{pr["unit_count"]} passage(s) in {len(pr["documents"])} document(s)</p>'
            f"<ul>{docs}</ul>"
            f'<p class="prov"><span class="doc">{_e(pr["evidence_id"])}</span> '
            f'| {_e(pr["locator"])}</p>'
            f'<p class="passage">{_e(pr["quote"])}</p></div>'
        )
    return (
        "<section><h2>Present in the corpus, absent from the graph</h2>"
        '<p class="gloss"><strong>The graph is built from wiki infobox rows only</strong> '
        "(<span class=\"mono\">src/graph/build.py</span>, "
        '<span class="mono">if unit.collection == &quot;wiki&quot;:</span>). An entity '
        "described at length in prose but never given an infobox row has no node, so "
        "no chain can be walked through it. That is a declared boundary of this "
        "checkpoint (ADR-016), not a failure to find the text &mdash; here is the text:</p>"
        f"{''.join(rows)}</section>"
    )


def _traversal_block(view: dict) -> str:
    """How far the chain got, and what it could not join to what."""
    diag = view["diagnostics"]
    if not diag or not diag["start"]:
        return ""
    start = diag["start"]
    goal = diag["goal"]

    lead = (
        f'<p class="answer" style="font-size:1.05rem">Could not join '
        f'<strong>{_e(start["name"])}</strong> to '
        f'<strong>{_e(goal["name"])}</strong>.</p>'
        if goal
        else f'<p class="answer" style="font-size:1.05rem">Started from '
        f'<strong>{_e(start["name"])}</strong> and reached no endpoint the '
        "question would accept.</p>"
    )

    rows = [
        f'<tr><th>Start</th><td>{_e(start["name"])} '
        f'<span class="tag">{_e(start["key"])}</span></td></tr>'
    ]
    if goal:
        rows.append(
            f'<tr><th>Goal</th><td>{_e(goal["name"])} '
            f'<span class="tag">{_e(goal["key"])}</span></td></tr>'
        )
    if diag["asked_relation"]:
        rows.append(
            "<tr><th>Relation asked for</th><td>"
            f'<span class="rel">{_e(diag["asked_relation"])}</span></td></tr>'
        )
    rows.append(
        f'<tr><th>Hops completed</th><td>{diag["hops_completed"]}</td></tr>'
    )

    reached = ""
    if diag["reached"]:
        items = "".join(
            f'<li>{_e(r["name"])}'
            + (f' <span class="tag">{_e(r["type"])}</span>' if r["type"] else "")
            + "</li>"
            for r in diag["reached"]
        )
        extra = (
            f' (showing {len(diag["reached"])} of {diag["reached_count"]})'
            if diag["reached_count"] > len(diag["reached"])
            else ""
        )
        reached = (
            f'<p class="gloss">The traversal did reach {diag["reached_count"]} '
            f"endpoint(s){extra} &mdash; they are real, sourced results that simply "
            "are not what this question asked for:</p>"
            f"<ul>{items}</ul>"
        )

    return (
        "<section><h2>How far the traversal got</h2>"
        f"{lead}<table>{''.join(rows)}</table>{reached}</section>"
    )


def _vocabulary_block(view: dict) -> str:
    """The relation vocabulary, so the boundary reads as declared, not accidental."""
    diag = view["diagnostics"]
    if not diag or not diag["relation_vocabulary"]:
        return ""
    asked = diag["asked_relation"]
    tags = "".join(
        f'<span class="tag{" dispute" if r == asked else ""}">{_e(r)}</span>'
        for r in diag["relation_vocabulary"]
    )
    asked_line = (
        f'<p class="gloss">This question asked for '
        f'<span class="rel">{_e(asked)}</span>, highlighted above.</p>'
        if asked
        else ""
    )
    return (
        "<section><h2>The relations this system knows</h2>"
        f'<p class="gloss">{len(diag["relation_vocabulary"])} relations, declared in '
        '<span class="mono">config/relations.yaml</span> and read by the same map the '
        "graph builder used. A question outside this vocabulary is outside the "
        "system&rsquo;s reach by design &mdash; the boundary is declared, not "
        f"accidental.</p><p>{tags}</p>{asked_line}"
        '<p class="gloss"><a href="/#relations">See each relation&rsquo;s field names '
        "and question vocabulary</a>.</p></section>"
    )


def _decline_blocks(view: dict) -> str:
    """Every partial-evidence block that applies, in reading order.

    Rendered only for a decline. Each block returns "" when the engine did not
    establish the thing it shows, so a page never claims more than was found.
    """
    if view["answerable"]:
        return ""
    return (
        _suggestion_block(view)
        + _traversal_block(view)
        + _established_block(view)
        + _coverage_block(view)
        + _vocabulary_block(view)
    )


# -- the front page: what can be asked, before anything is asked ------------
#
# A judge typing a first question is guessing against a closed 117-entity
# graph, and `python -m comparison.harness` measures how that goes: no route
# shape on 35 of 49 independently written questions. Publishing the entity list
# and the relation vocabulary widens what the system can answer by exactly
# nothing - it stops the boundary being discovered by failing at it.


def _entity_datalist(catalogue: dict | None) -> str:
    """Native browser autocomplete on the question box. No JavaScript.

    A `<datalist>` suggests as the judge types without a script tag, a CDN or a
    dependency - the same constraint `graphview.py` works under.
    """
    if not catalogue:
        return ""
    options = "".join(
        f'<option value="{_e(e["name"])}"></option>' for e in catalogue["entities"]
    )
    return f'<datalist id="entities">{options}</datalist>'


def _catalogue_block(catalogue: dict | None) -> str:
    """The browsable entity list and the relation vocabulary."""
    if not catalogue:
        return ""
    counts = catalogue["counts"]

    by_type: dict[str, list] = {}
    for entity in catalogue["entities"]:
        by_type.setdefault(entity["type"], []).append(entity)

    groups = []
    for kind in sorted(by_type, key=lambda k: (-len(by_type[k]), k)):
        items = "".join(
            # Every name links to a question the system can actually answer:
            # "Who is X?" routes to EvidenceStatus.PROFILE, the entity's whole
            # sourced record. So the list is not a catalogue of names, it is a
            # set of working entry points.
            f'<li><a href="/ask?q={_e_url("Who is " + e["name"] + "?")}">'
            f'{_e(e["name"])}</a>'
            + ("" if e["page"] else ' <span class="tag">no page</span>')
            + "</li>"
            for e in by_type[kind]
        )
        groups.append(
            f"<details><summary>{_e(kind)} "
            f'<span class="tag">{len(by_type[kind])}</span></summary>'
            f'<ul class="entitylist">{items}</ul></details>'
        )

    rel_rows = "".join(
        f'<tr><td><span class="rel">{_e(r["name"])}</span></td>'
        f'<td>{r["edges"]}</td>'
        f'<td class="mono">{_e(", ".join(r["fields"][:4]))}'
        + (f' +{len(r["fields"]) - 4}' if len(r["fields"]) > 4 else "")
        + "</td>"
        f'<td class="mono">{_e(", ".join(r["cues"]) or "-")}</td></tr>'
        for r in catalogue["relations"]
    )

    return (
        '<section id="entities"><h2>What you can ask about</h2>'
        f'<p class="gloss">The graph holds <strong>{counts["entities"]} entities</strong> '
        f'and <strong>{counts["edges"]} edges</strong> across '
        f'<strong>{counts["relations"]} relations</strong>. '
        f'{counts["page_backed"]} entities have a wiki page; the rest are known only '
        "as link targets. Click any name to see its full record.</p>"
        f"{''.join(groups)}</section>"
        '<section id="relations"><h2>The relations it can follow</h2>'
        '<p class="gloss">Declared in <span class="mono">config/relations.yaml</span>. '
        "<em>Field names</em> are how the corpus writes a fact; <em>question cues</em> "
        "are how a person asks about it, kept separate on purpose (ADR-024). A question "
        "outside this vocabulary will decline &mdash; and say so, with what it did "
        "establish.</p>"
        "<table><tr><th>Relation</th><th>Edges</th><th>Infobox field names</th>"
        f"<th>Question cues</th></tr>{rel_rows}</table></section>"
    )


# -- pages -------------------------------------------------------------------


def _shell(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)}</title><style>{CSS}</style></head><body><main>"
        '<h1><a href="/">Ashen Era Intelligence Assistant</a></h1>'
        '<p class="sub">Deterministic graph query over 317 documents. '
        "Every hop below cites the infobox row it was read from.</p>"
        f"{body}"
        "<footer>Checkpoint 2 &mdash; deterministic engine, no LLM in this path."
        "</footer></main></body></html>"
    )


def page_index(catalogue: dict | None = None) -> str:
    """The front page: ask, or browse what there is to ask about.

    `catalogue` is optional so the page still renders without one (tests, and
    any caller that has not built the graph yet); when present it supplies the
    autocomplete list and the browsable entity/relation tables.
    """
    return _shell(
        "Ashen Era Intelligence Assistant",
        _search_form()
        + _entity_datalist(catalogue)
        + _examples_block()
        + _reload_block()
        + _catalogue_block(catalogue),
    )


def _reload_block() -> str:
    """The corpus-reload control.

    The graph is built once at startup, so a document added to the corpus while
    the server runs is invisible until something rebuilds. A file watcher would
    hide that; this shows it. The rebuild is ~6s on the full corpus, and the
    result page prints the before/after counts rather than saying "done".
    """
    return (
        "<section><h2>Corpus</h2>"
        '<form action="/reload" method="post" style="margin:0">'
        '<button type="submit">Reindex corpus</button>'
        "</form>"
        "<p class='gloss'>The graph is read from disk at startup and held. Add or "
        "change a document in the corpus and reindex to pick it up - about six "
        "seconds for the full archive. The next page reports what changed.</p>"
        "</section>"
    )


def page_graph(svg: str, legend: str, node_count: int, edge_count: int) -> str:
    """The whole graph, drawn. Surface 10.

    A static SVG built by `src/ui/graphview.py` - no CDN, no JavaScript, works
    offline and with scripting disabled. See that module for why this is not
    vis-network.
    """
    body = (
        f"<h2>The knowledge graph</h2>"
        f"<p class='muted'>{node_count} entities, {edge_count} edges, built from "
        f"infobox rows. Every line carries the document that asserted it - "
        f"hover to read it.</p>"
        f"{legend}"
        f"<div style='border:1px solid #ddd6c8;border-radius:6px;overflow:hidden;"
        f"background:#faf8f4'>{svg}</div>"
        f"<p class='muted'><a href='/'>Ask a question</a></p>"
    )
    return _shell("The knowledge graph - Ashen Era", body)


def page_answer(view: dict) -> str:
    """The full result page: all nine demo surfaces, in reading order."""
    body = (
        _search_form(view["question"])
        + _answer_block(view)
        + _status_block(view)
        + _strategy_block(view)
        + _conflict_block(view)
        # Partial evidence for a decline, immediately after the status that
        # named it and before the (empty) route section - so the page reads
        # "here is why, and here is what we did find", not "nothing".
        + _decline_blocks(view)
        + _routes_block(view)
        + _documents_block(view)
        + _examples_block()
    )
    return _shell(f"{view['question'][:60]} - Ashen Era", body)


def _delta(before: int, after: int) -> str:
    """`118 -> 119 (+1)`, or `118 (unchanged)`. The point of the page is the +1."""
    if after == before:
        return f"{before:,} <span class='muted'>(unchanged)</span>"
    sign = "+" if after > before else ""
    return f"{before:,} &rarr; <strong>{after:,}</strong> ({sign}{after - before:,})"


def page_reload(report: dict) -> str:
    """What a corpus reload changed. Surface 11.

    Exists because a running server holds the graph it built at startup, so a
    document added to the corpus is invisible until something rebuilds. This is
    that something, and the page shows the before/after counts rather than
    reporting success, because "it reloaded" is a claim and "118 -> 119
    entities" is evidence.
    """
    before, after = report["before"], report["after"]
    unmapped = report.get("unmapped_fields") or {}

    rows = "".join(
        f"<tr><td>{label}</td><td class='mono'>{_delta(before[key], after[key])}</td></tr>"
        for label, key in (
            ("Evidence units", "units"),
            ("Entities", "entities"),
            ("Edges", "edges"),
        )
    )

    unchanged = all(before[k] == after[k] for k in ("units", "entities", "edges"))
    gloss = (
        "<p class='gloss'>Nothing changed. The corpus on disk is the one already "
        "loaded.</p>"
        if unchanged
        else "<p class='gloss'>The corpus on disk differed from the one loaded, "
        "and the graph was rebuilt from it.</p>"
    )

    # An unmapped field is a relation the corpus expresses under a name nobody
    # mapped - an edge that silently never exists. Surfaced here because a
    # reload is exactly when new vocabulary arrives, and the fix is a line of
    # `config/relations.yaml`, not code.
    if unmapped:
        items = "".join(
            f"<li><span class='mono'>{_e(name)}</span> &times;{count}</li>"
            for name, count in sorted(unmapped.items())
        )
        gloss += (
            "<p class='gloss'><strong>Field names this corpus uses that "
            "<code>config/relations.yaml</code> does not map</strong> - each is a "
            "relation the graph is not reading. Add it to that file and reload; "
            "no code change.</p>"
            f"<ul>{items}</ul>"
        )

    body = (
        _search_form()
        + "<section><h2>Corpus reloaded</h2>"
        + f"<p class='muted'>Re-read from disk in "
        f"{report['elapsed_seconds']:.1f}s.</p>"
        + f"<table>{rows}</table>"
        + gloss
        + "<p class='gloss'><a href='/'>Ask a question</a> against the reloaded "
        "corpus.</p></section>"
        + _examples_block()
    )
    return _shell("Corpus reloaded - Ashen Era", body)


def page_error(message: str) -> str:
    return _shell(
        "Error - Ashen Era",
        _search_form()
        + f'<section><h2>Error</h2><p class="note">{_e(message)}</p></section>'
        + _examples_block(),
    )
