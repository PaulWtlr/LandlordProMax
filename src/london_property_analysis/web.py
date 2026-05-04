from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class PropertyAppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory or str(PROJECT_ROOT), **kwargs)

    def do_GET(self) -> None:
        if self.path in {"/", ""}:
            self.path = "/app/index.html"
        if self.path == "/healthz":
            self._write_json({"status": "ok", "app": "london-property-analysis"})
            return
        super().do_GET()

    def _write_json(self, payload: dict[str, str]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        print(f"[web] {self.address_string()} - {format % args}")


def serve(host: str = "127.0.0.1", port: int = 4173) -> None:
    server = ThreadingHTTPServer((host, port), PropertyAppHandler)
    print(f"London property app running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


def add_serve_parser(subparsers: argparse._SubParsersAction) -> None:
    serve_parser = subparsers.add_parser("serve", help="Run the local HTML app")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", default=4173, type=int)

