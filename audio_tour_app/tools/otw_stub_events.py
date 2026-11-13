#!/usr/bin/env python3
"""LOCAL-908 proof stub: accepts POST /listening-events and logs each body.

Runs on its OWN port (default 15003); never touches the shared audioura-* stack.
    python3 tools/otw_stub_events.py 15003 /tmp/otw/events.log
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 15003
LOG = sys.argv[2] if len(sys.argv) > 2 else "/tmp/otw/events.log"


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n).decode() or "{}"
        if self.path.rstrip("/") != "/listening-events":
            return self._send(404, {"error": "not_found"})
        try:
            ev = json.loads(raw)
        except Exception:
            return self._send(400, {"error": "bad json"})
        with open(LOG, "a") as f:
            f.write(json.dumps({"t": time.strftime("%H:%M:%S"), **ev}) + "\n")
        self._send(201, {"id": 1, "weight_delta": 0})

    def log_message(self, *a):
        pass


HTTPServer(("127.0.0.1", PORT), H).serve_forever()
