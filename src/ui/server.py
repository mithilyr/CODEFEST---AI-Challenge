"""A stdlib `http.server` in front of `answer_question`. No framework.

WHY NOT A FRAMEWORK
-------------------
CLAUDE.md's binding constraint is that every team member must be able to
explain and modify any part of this submission on demand. A request handler
with two routes and one call into the query layer is about eighty lines any
Python programmer can read top to bottom. Streamlit would add a dependency
whose rerun model and session state a teammate would have to defend to a
judge, in exchange for nothing this page needs: there is no client-side state
here, only a GET with a query string.

The graph is built once, at startup (~5.5s measured), and reused for every
request. Rebuilding per request would make the demo feel broken and prove
nothing.

    python -m src.ui.server            # http://127.0.0.1:8000
    python -m src.ui.server --port 9000
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from src.graph.build import build_graph, load_relation_map
from src.graph.schema import Graph
from src.ingest.pipeline import ingest
from src.query.catalogue import build_catalogue
from src.query.engine import answer_question
from src.query.resolve import EntityResolver
from src.query.route import build_gazetteer
from src.query.synthesis import synthesise
from src.ui.graphview import layout, legend_html, render_svg
from src.ui.render import page_answer, page_error, page_graph, page_index
from src.ui.view import build_view


class Engine:
    """Everything expensive, built once and held.

    A thin holder, not a second engine: `ask` forwards to
    `query.engine.answer_question` and adds nothing. The resolver and
    gazetteer are cached here only because rebuilding them per request costs
    seconds and changes no result - `answer_question` builds exactly these
    itself when they are not passed.
    """

    def __init__(
        self,
        graph: Graph | None = None,
        *,
        use_planner: bool = False,
        use_model_phrasing: bool = False,
        evidence_units: list | None = None,
    ) -> None:
        self.graph = graph if graph is not None else build_graph()
        self.resolver = EntityResolver(self.graph)
        self.gazetteer = build_gazetteer(self.graph, self.resolver)
        self.relation_map = load_relation_map()
        #: MEASURED DEFECT, fixed here: without evidence units,
        #: `answer_question` cannot tell `OUTSIDE_STRUCTURED_COVERAGE` from
        #: `UNRESOLVED_ENTITY`, and the UI never passed them. The demo
        #: therefore told a judge that Halvard Cindervale - a person with 21
        #: passages across tier-1 codex, tier-2 wiki and tier-4 ephemera - was
        #: a name the corpus does not contain. Ingest is ~5s at startup and
        #: cached thereafter. Pass `[]` in tests that do not need it.
        self.evidence_units = (
            evidence_units if evidence_units is not None else ingest().evidence
        )
        self._catalogue: dict | None = None
        #: Both default OFF, matching `answer_question`'s own default. The demo
        #: is deterministic unless someone asks for otherwise, so an unattended
        #: run cannot spend daily quota and a cold network cannot break it.
        #: `--with-model` turns both on.
        self.use_planner = use_planner
        self.use_model_phrasing = use_model_phrasing
        self._svg: str | None = None

    def catalogue(self) -> dict:
        """Entity list and relation vocabulary for the front page, built once."""
        if self._catalogue is None:
            self._catalogue = build_catalogue(self.graph, self.relation_map)
        return self._catalogue

    def graph_svg(self) -> str:
        """Render the graph once and hold it.

        The layout costs ~0.8s and is deterministic, so recomputing it per
        request would spend time to produce a byte-identical result.
        """
        if self._svg is None:
            self._svg = render_svg(self.graph, layout(self.graph))
        return self._svg

    def ask(self, question: str) -> dict:
        answer = answer_question(
            question,
            self.graph,
            resolver=self.resolver,
            gazetteer=self.gazetteer,
            use_planner=self.use_planner,
            evidence_units=self.evidence_units,
        )
        # Phrasing is additive and never replaces the evidence trail - the page
        # renders both, so a viewer can always check the sentence against the
        # hops that produced it.
        synthesis = synthesise(
            answer, self.graph, use_model=self.use_model_phrasing
        )
        view = build_view(answer, self.graph)
        view["prose"] = synthesis.text
        view["phrasing"] = synthesis.phrasing
        view["phrasing_model"] = synthesis.model
        return view


def make_handler(engine: Engine) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "AshenEraUI/1.0"

        def _send(self, body: str, status: int = 200) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's name
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send(page_index(engine.catalogue()))
                return
            if parsed.path == "/graph":
                self._send(
                    page_graph(
                        engine.graph_svg(),
                        legend_html(),
                        len(engine.graph.nodes),
                        len(engine.graph.edges),
                    )
                )
                return
            if parsed.path != "/ask":
                self._send(page_error(f"No such page: {parsed.path}"), status=404)
                return

            question = (parse_qs(parsed.query).get("q") or [""])[0].strip()
            if not question:
                self._send(page_index(engine.catalogue()))
                return
            try:
                view = engine.ask(question)
            except Exception as exc:  # noqa: BLE001 - the page must say what broke
                # Surfaced, not swallowed. A blank page during the live demo
                # would be worse than an ugly one, and a caught exception is a
                # bug report the audience can read.
                self._send(page_error(f"{type(exc).__name__}: {exc}"), status=500)
                return
            self._send(page_answer(view))

        def log_message(self, fmt: str, *args) -> None:
            print(f"  {self.address_string()} {fmt % args}")

    return Handler


def serve(
    host: str = "127.0.0.1", port: int = 8000, *, with_model: bool = False
) -> None:
    print("building the graph ...")
    engine = Engine(use_planner=with_model, use_model_phrasing=with_model)
    print(
        f"  {len(engine.graph.nodes)} entities, {len(engine.graph.edges)} edges, "
        f"{len(engine.evidence_units)} evidence units"
    )
    print(
        "  model tiers: ON (planner + phrasing)"
        if with_model
        else "  model tiers: off - fully deterministic (pass --with-model to enable)"
    )
    httpd = ThreadingHTTPServer((host, port), make_handler(engine))
    print(f"\n  Ashen Era assistant on http://{host}:{port}\n  Ctrl-C to stop\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve the Ashen Era demo UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--with-model",
        action="store_true",
        help=(
            "enable the LLM planner tier and model phrasing. Off by default so "
            "an unattended demo cannot spend daily quota or break on a cold "
            "network; needs OPENROUTER_API_KEY."
        ),
    )
    args = parser.parse_args(argv)
    serve(args.host, args.port, with_model=args.with_model)


if __name__ == "__main__":
    main()
