#!/usr/bin/env python3
import argparse
import base64
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from fangdi_ocr_lib import ocr_png_bytes


def parse_png_bytes(payload):
    if "image_base64" in payload:
        return base64.b64decode(payload["image_base64"])
    if "image_data_url" in payload:
        _, encoded = payload["image_data_url"].split(",", 1)
        return base64.b64decode(encoded)
    raise ValueError("expected image_base64 or image_data_url")


class Handler(BaseHTTPRequestHandler):
    results_path = None

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(200, {"ok": True})

    def do_GET(self):
        if self.path == "/healthz":
            self._send(200, {"ok": True})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception as exc:
            self._send(400, {"error": f"invalid json: {exc}"})
            return

        if parsed.path == "/ocr":
            try:
                result = ocr_png_bytes(parse_png_bytes(payload))
                self._send(200, result)
            except Exception as exc:
                self._send(400, {"error": str(exc)})
            return

        if parsed.path == "/append-result":
            item = {"received_at": datetime.now().isoformat(), **payload}
            self.results_path.parent.mkdir(parents=True, exist_ok=True)
            with self.results_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            self._send(200, {"ok": True, "path": str(self.results_path)})
            return

        self._send(404, {"error": "not found"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--results-file",
        default="/root/fangdi-data/var/fangdi-count-results.jsonl",
        help="jsonl file for browser runner results",
    )
    args = parser.parse_args()

    Handler.results_path = Path(args.results_file)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        json.dumps(
            {
                "host": args.host,
                "port": args.port,
                "results_file": str(Handler.results_path),
            },
            ensure_ascii=False,
        )
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
