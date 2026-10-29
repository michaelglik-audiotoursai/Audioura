"""local810_wdqs_proxy.py — a faithful WDQS-throttling proxy for the live run.

The LOCAL-809 evidence: the HEAVY "all works in collection" SPARQL query for a
big museum (the Met) ReadTimeouts on WDQS, while a TRIVIAL query from the same
container returns 200 in ~8.7 s. The LOCAL-810 fallback (a) per-candidate
P195/P276 checks are exactly those small, fast queries.

This proxy reproduces that precise condition so the live run exercises the
per-candidate path end to end:
  * a HEAVY venue-works query (the big GROUP_CONCAT collection pull, i.e. a query
    WITHOUT a single-title `FILTER(LCASE(STR(?lbl))` clause) → STALL: the proxy
    sleeps past the client's VENUE_WORKS_TIMEOUT so the client sees a ReadTimeout;
  * every OTHER query (the small per-candidate membership check, the
    related-holders query, …) → FORWARDED to the real WDQS and returned verbatim.

Point the generator at this proxy with WDQS_ENDPOINT=http://<host>:8899/sparql.
No external deps beyond the stdlib + requests. Bind host/port via env.
"""
import os
import sys
import urllib.parse
import http.server
import socketserver
import threading
import time

import requests

REAL_WDQS = os.environ.get("REAL_WDQS_ENDPOINT", "https://query.wikidata.org/sparql")
PORT = int(os.environ.get("PROXY_PORT", "8899"))
# Sleep this long on a heavy query so the client's (short) timeout trips first.
STALL_SECONDS = float(os.environ.get("PROXY_STALL_SECONDS", "90"))
_UA = "Audioura-LOCAL810-proxy/1.0 (field test; contact: dev@audioura.local)"


def _is_heavy_collection_query(q: str) -> bool:
    """Heavy = the big venue-works pull. It GROUP_CONCATs collections/creators and
    has NO single-title label FILTER (that marker identifies a small per-candidate
    query). Matches the LOCAL-810 bounded query and the legacy one."""
    if not q:
        return False
    if "FILTER(LCASE(STR(?lbl))" in q:
        return False  # small per-candidate membership check → fast path
    # The heavy query selects works by P195/P276 and GROUP_CONCATs collections.
    return ("wdt:P195" in q or "wdt:P276" in q) and "GROUP_CONCAT" in q


class _Handler(http.server.BaseHTTPRequestHandler):
    def _query(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        if "query" in qs:
            return qs["query"][0], qs
        if self.command == "POST":
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
            form = urllib.parse.parse_qs(body)
            if "query" in form:
                return form["query"][0], form
        return "", qs

    def _handle(self):
        query, _qs = self._query()
        if _is_heavy_collection_query(query):
            sys.stderr.write(f"[PROXY] HEAVY query → STALL {STALL_SECONDS}s "
                             f"(client should ReadTimeout)\n")
            sys.stderr.flush()
            time.sleep(STALL_SECONDS)  # client times out well before this returns
            try:
                self.send_response(504)
                self.end_headers()
            except Exception:
                pass
            return
        # Small / per-candidate / other query → forward to the real WDQS.
        sys.stderr.write(f"[PROXY] small query → forward to real WDQS "
                         f"({query[:70]!r}…)\n")
        sys.stderr.flush()
        try:
            resp = requests.get(
                REAL_WDQS,
                params={"query": query, "format": "json"},
                headers={"User-Agent": _UA,
                         "Accept": "application/sparql-results+json"},
                timeout=30)
            self.send_response(resp.status_code)
            self.send_header("Content-Type",
                             resp.headers.get("Content-Type", "application/json"))
            body = resp.content
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            sys.stderr.write(f"[PROXY] forward error: {e}\n")
            try:
                self.send_response(502)
                self.end_headers()
            except Exception:
                pass

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def log_message(self, *a):
        pass  # quiet


class _ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    srv = _ThreadingServer(("0.0.0.0", PORT), _Handler)
    sys.stderr.write(f"[PROXY] LOCAL-810 WDQS throttle proxy on :{PORT} "
                     f"→ real {REAL_WDQS} (heavy stall {STALL_SECONDS}s)\n")
    sys.stderr.flush()
    srv.serve_forever()


if __name__ == "__main__":
    main()
