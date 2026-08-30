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

from src.graph.build import build_graph
from src.graph.schema import Graph
from src.query.engine import answer_question
from src.query.resolve import EntityResolver
from src.query.route import build_gazetteer
from src.ui.render import page_answer, page_error, page_index
from src.ui.view import build_view


class Engine:
    """Everything expensive, built once and held.

    A thin holder, not a second engine: `ask` forwards to
    `query.engine.answer_question` and adds nothing. The resolver and
    gazetteer are cached here only because rebuilding them per request costs
    seconds and changes no result - `answer_question` builds exactly these
    itself when they are not passed.
    """

    def __init__(self, graph: Graph | None = None) -> None:
        self.graph = graph if graph is not None else build_graph()
        self.resolver = EntityResolver(self.graph)
        self.gazetteer = build_gazetteer(self.graph, self.resolver)

    def ask(self, question: str) -> dict:
        answer = answer_question(
            question,
            self.graph,
            resolver=self.resolver,
            gazetteer=self.gazetteer,
        )
        return build_view(answer, self.graph)


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
                self._send(page_index())
                return
            if parsed.path != "/ask":
                self._send(page_error(f"No such page: {parsed.path}"), status=404)
                return

            question = (parse_qs(parsed.query).get("q") or [""])[0].strip()
            if not question:
                self._send(page_index())
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


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    print("building the graph ...")
    engine = Engine()
    print(f"  {len(engine.graph.nodes)} entities, {len(engine.graph.edges)} edges")
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
    args = parser.parse_args(argv)
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
