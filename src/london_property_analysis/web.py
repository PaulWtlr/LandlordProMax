from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:
    from .listings import fetch_foxtons_prime, write_csv, write_js, write_json
except ImportError:  # Allows `python src/london_property_analysis/web.py`.
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from london_property_analysis.listings import fetch_foxtons_prime, write_csv, write_js, write_json


class PropertyAppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory or str(PROJECT_ROOT), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", ""}:
            self.path = "/app/index.html"
        if parsed.path == "/healthz":
            self._write_json({"status": "ok", "app": "london-property-analysis"})
            return
        if parsed.path == "/api/listings":
            params = parse_qs(parsed.query)
            refresh = params.get("refresh", ["0"])[0] in {"1", "true", "yes"}
            self._write_dataset(refresh=refresh)
            return
        super().do_GET()

    def _write_dataset(self, refresh: bool = False) -> None:
        path = PROJECT_ROOT / "data" / "live_properties.json"
        if refresh or not path.exists():
            rows = fetch_foxtons_prime(limit=1000)
            write_csv(rows, str(PROJECT_ROOT / "data" / "processed" / "chelsea-south-kensington-listings.csv"))
            write_json(
                rows,
                str(path),
                {
                    "mode": "chelsea_south_kensington",
                    "requestedLimit": 1000,
                    "areas": ["Chelsea", "South Kensington"],
                    "refresh": refresh,
                },
            )
            write_js(rows, str(PROJECT_ROOT / "data" / "live_properties.js"))
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            payload = {"meta": {"count": 0, "source": "none"}, "listings": []}
        self._write_json(payload)

    def _write_json(self, payload: dict[str, object]) -> None:
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


def main() -> int:
    parser = argparse.ArgumentParser(prog="property-web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=4173, type=int)
    args = parser.parse_args()
    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
