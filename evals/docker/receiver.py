"""Tiny local HTTP receiver used by development-only eval Docker Compose."""

from __future__ import annotations

import argparse
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class ReceiverHandler(BaseHTTPRequestHandler):
    """Request logger for local eval receiver."""

    log_path: Path

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok\n")
            return
        if self.path == "/requests":
            events = []
            if self.log_path.exists():
                with self.log_path.open(encoding="utf-8") as log_file:
                    for line in log_file:
                        if line.strip():
                            events.append(json.loads(line))
            body = json.dumps(events, sort_keys=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        event = {
            "body_digest": f"sha256:{hashlib.sha256(body).hexdigest()}",
            "content_length": length,
            "method": "POST",
            "path": self.path,
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(event, sort_keys=True) + "\n")
        self.send_response(202)
        self.end_headers()
        self.wfile.write(b"accepted\n")

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--log", type=Path, default=Path("/artifacts/receiver/requests.jsonl"))
    args = parser.parse_args()
    ReceiverHandler.log_path = args.log
    server = ThreadingHTTPServer((args.host, args.port), ReceiverHandler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
