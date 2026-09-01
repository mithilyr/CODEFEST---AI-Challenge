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
"""

_STATUS_CLASS = {
    "sufficient": "ok",
    "conflicting_evidence": "warn",
    "abstention": "warn",
}


def _status_class(status: str) -> str:
    """Colour band for a status code. A lookup, not an assessment."""
    return _STATUS_CLASS.get(status, "bad")


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
        'autocomplete="off" autofocus>'
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
    return f"<section><h2>Answer</h2>{body}</section>"


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


def _status_block(view: dict) -> str:
    """Evidence sufficiency, and the fallback reason when there is one."""
    cls = _status_class(view["status"])
    parts = [
        f'<span class="status {cls}">{_e(view["status"])}</span>',
        f'<p class="gloss">{_e(view["status_gloss"])}</p>',
    ]
    parts.append(
        '<p class="gloss">Answerable: <strong>'
        f'{"yes" if view["answerable"] else "no"}</strong> '
        "&mdash; read from the status the engine returned, not decided here.</p>"
    )
    if view["note"]:
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


def page_index() -> str:
    return _shell(
        "Ashen Era Intelligence Assistant",
        _search_form() + _examples_block(),
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
        + _routes_block(view)
        + _documents_block(view)
        + _examples_block()
    )
    return _shell(f"{view['question'][:60]} - Ashen Era", body)


def page_error(message: str) -> str:
    return _shell(
        "Error - Ashen Era",
        _search_form()
        + f'<section><h2>Error</h2><p class="note">{_e(message)}</p></section>'
        + _examples_block(),
    )
