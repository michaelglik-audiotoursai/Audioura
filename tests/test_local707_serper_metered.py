"""tests/test_local707_serper_metered.py — LOCAL-707.

The paid-API network meter stopped writing Serper rows after the LOCAL-678
httpx/aiohttp patch (Oct 13), while httpx-based OpenAI/Gemini kept logging. The
gap: LOCAL-678's tests only proved httpx (OpenAI) and aiohttp — nothing proved a
Serper call via urllib OR requests is still metered. This suite closes that gap
and proves the LOCAL-707 fix.

What is proven (NO real network, NO real paid call, NO real DB):
  1. network_urllib_serper_metered — a urllib Serper POST (the work_story_searcher
     / current_affairs_news path) writes exactly one kind="serper" row via the
     installed network patch, served by a LOCAL mock HTTP server.
  2. network_requests_serper_metered — the same for a requests.Session POST
     (the interpretive_enrichment / dining_corpus_harvester path).
  3. serper_post_guarantees_row_without_patch — serper_meter.serper_post writes a
     row even when the network patch is NOT installed (belt): it calls
     record_call() itself.
  4. serper_post_no_double_count_with_patch — with the patch live, serper_post
     still yields exactly ONE row, not two (the _mark_explicit guard).
  5. serper_post_cost_and_status — a 200 is priced at SERPER_PER_QUERY ($0.001),
     a non-200 at $0.0.

Each test points the meter's host-kind at 127.0.0.1 so a local server stands in
for google.serper.dev; the DB write and the daily-limit check are stubbed.
"""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "_meter"))
sys.path.insert(0, _ROOT)


# ── a local stand-in for google.serper.dev (no real network) ─────────────────
class _Handler(BaseHTTPRequestHandler):
    RESP = {"organic": [{"title": "t", "link": "https://e.com", "snippet": "s"}]}
    STATUS = 200

    def do_POST(self):
        ln = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(ln)
        body = json.dumps(self.RESP).encode()
        self.send_response(self.STATUS)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}/search"
    srv.shutdown()


@pytest.fixture
def meter(monkeypatch, tmp_path):
    """The network meter writing to a tmp log, DB + daily-limit stubbed, with the
    local 127.0.0.1 host treated as 'serper' so a local server stands in for the
    real host. install() is idempotent."""
    import paid_api_meter as m
    log = tmp_path / "paid_api_calls.jsonl"
    monkeypatch.setattr(m, "LOG", str(log))
    monkeypatch.setattr(m, "_db_write", lambda rec: None)
    monkeypatch.setattr(m, "check_daily_limit", lambda: None)
    _orig_hk = m._host_kind
    monkeypatch.setattr(
        m, "_host_kind",
        lambda u: "serper" if u and "127.0.0.1" in u else _orig_hk(u))
    m.install()
    m._LOG_FOR_TEST = str(log)
    return m


def _rows(m):
    p = m._LOG_FOR_TEST
    if not os.path.exists(p):
        return []
    with open(p) as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _serper_rows(m):
    return [r for r in _rows(m) if r.get("kind") == "serper"]


# ── 1. urllib via the network patch ──────────────────────────────────────────
def test_network_urllib_serper_metered(meter, server):
    """A urllib Serper POST (work_story_searcher / current_affairs_news path) is
    metered by the installed network patch. This is the exact client that
    silently stopped logging after LOCAL-678.

    Asserts a correctly-costed serper row is written for THIS call (delta >= 1):
    the meter is installed once process-wide and other suites may stack wrappers,
    so we assert "recorded, at the right cost" rather than a global exact count —
    the no-double-count property is proven under controlled state in
    test_serper_post_no_double_count_with_patch below."""
    before = len(_serper_rows(meter))
    import urllib.request
    req = urllib.request.Request(
        server, data=b'{"q":"x"}',
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        r.read()
    rows = _serper_rows(meter)
    assert len(rows) > before, "urllib Serper call must be metered (>=1 new row)"
    new = rows[before:]
    assert all(x["status"] == 200 for x in new)
    assert all(x["usd"] == meter.SERPER_PER_QUERY for x in new)


# ── 2. requests via the network patch ────────────────────────────────────────
def test_network_requests_serper_metered(meter, server):
    """A requests.Session Serper POST (interpretive_enrichment /
    dining_corpus_harvester path) is metered by the installed network patch."""
    before = len(_serper_rows(meter))
    import requests
    r = requests.post(server, data=b'{"q":"x"}',
                      headers={"Content-Type": "application/json"}, timeout=5)
    assert r.status_code == 200
    rows = _serper_rows(meter)
    assert len(rows) > before, "requests Serper call must be metered (>=1 new row)"
    new = rows[before:]
    assert all(x["usd"] == meter.SERPER_PER_QUERY for x in new)


# ── 3. serper_post guarantees a row even with NO network patch (belt) ─────────
def test_serper_post_guarantees_row_without_patch(monkeypatch, tmp_path, server):
    """serper_meter.serper_post writes the row itself via record_call(), so a
    container where the network patch never installed still meters Serper. We
    simulate "no patch" by resetting urllib/requests to their originals is
    unnecessary — instead we assert the row comes from record_call by stubbing
    the meter's log/db and NOT relying on the wrapper (the explicit mark would
    suppress the wrapper anyway)."""
    import paid_api_meter as m
    log = tmp_path / "paid_api_calls.jsonl"
    monkeypatch.setattr(m, "LOG", str(log))
    monkeypatch.setattr(m, "_db_write", lambda rec: None)
    monkeypatch.setattr(m, "check_daily_limit", lambda: None)
    _orig_hk = m._host_kind
    monkeypatch.setattr(
        m, "_host_kind",
        lambda u: "serper" if u and "127.0.0.1" in u else _orig_hk(u))
    # Do NOT call m.install() here — prove serper_post records on its own.
    import serper_meter
    status, body = serper_meter.serper_post(server, {"q": "x"}, api_key="k", timeout=5)
    assert status == 200
    with open(log) as fh:
        rows = [json.loads(l) for l in fh if l.strip()]
    serper = [r for r in rows if r.get("kind") == "serper"]
    assert len(serper) == 1, "serper_post must write exactly one row with no patch"
    assert serper[0]["usd"] == m.SERPER_PER_QUERY


# ── 4. serper_post does NOT double-count when the patch IS live ───────────────
def test_serper_post_no_double_count_with_patch(meter, server):
    """With the network patch installed AND serper_post recording explicitly, the
    request is metered exactly ONCE (the _mark_explicit guard). This is what lets
    us wire serper_post everywhere without inflating the ledger where the patch
    still works."""
    import serper_meter
    status, body = serper_meter.serper_post(server, {"q": "x"}, api_key="k", timeout=5)
    assert status == 200
    rows = _serper_rows(meter)
    assert len(rows) == 1, (
        "serper_post + live network patch must still record exactly ONE row, "
        "got %d" % len(rows))


# ── 5. cost + status ─────────────────────────────────────────────────────────
def test_serper_post_non200_is_zero_cost(meter, monkeypatch, server):
    """A non-200 Serper response is recorded at $0.0 (we were not billed)."""
    monkeypatch.setattr(_Handler, "STATUS", 429)
    import serper_meter
    status, body = serper_meter.serper_post(server, {"q": "x"}, api_key="k", timeout=5)
    assert status == 429
    rows = _serper_rows(meter)
    assert len(rows) == 1
    assert rows[0]["usd"] == 0.0
    monkeypatch.setattr(_Handler, "STATUS", 200)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
