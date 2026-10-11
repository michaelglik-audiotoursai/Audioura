#!/usr/bin/env python3
"""run_local669b_container.py — LOCAL-669B live acceptance (ISOLATED container).

Ticket: "Ho Chi Minh City Museum of Fine Arts, Vietnam", 5 stops, museum, FRESH,
NORMAL arm ONLY. ONE paid tour for the WHOLE 669B, HARD CAP $1.10.

Verifies the 669B fix end to end: the HCMC tour must deliver 5 DISTINCT works —
the National Treasure "North/Central/South Spring Garden" (Q109406846) appearing
ONCE, not three times, and NOT as a scraped citation line. Reports the delivered
stops + their sources, the LOCAL-669 highlights log, the LOCAL-669B identity-dedup
collapses, the grounded-request count, $ and seconds.

Rows: additive is_test only. No DELETE. Spend from paid_api_calls, tagged
user_id=TEST-LOCAL-669B.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-669B')
except Exception as _meter_err:
    print(f"[LOCAL-669B] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import io
import re
import socket
import time
import contextlib

_os.environ['STORIED_MODE'] = 'true'
_os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tour (cache off)
_os.environ['DISABLE_STOP_POOL'] = '1'             # pool off (fresh)
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.10')
_os.environ['COST_HARD_LIMIT_USD'] = '1.10'        # ticket HARD CAP (whole task)
_os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

HARD_CAP_USD = 1.10
HOST = socket.gethostname()
LOCATION = 'Ho Chi Minh City Museum of Fine Arts, Vietnam'
STOPS = 5

print("=== LOCAL-669B isolated live run (HCMC museum 5, NORMAL arm only) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  cache_off=1 pool_off=1", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402


def _conn():
    import psycopg2
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=_os.environ.get('DB_HOST', 'development-postgres-2-1'),
        port=_os.environ.get('DB_PORT', '5432'),
        dbname=_os.environ.get('DB_NAME', 'audiotours'),
        user=_os.environ.get('DB_USER', 'admin'),
        password=_os.environ.get('DB_PASSWORD', 'password123'))


def _scalar(sql, args=()):
    try:
        conn = _conn(); conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql, args)
            v = cur.fetchone()[0]
        conn.close(); return v
    except Exception as e:
        print(f"  [db] query failed: {e}", flush=True); return None


def _row_count():
    return _scalar("SELECT count(*) FROM audio_tours")


def _test_row_count():
    return _scalar("SELECT count(*) FROM audio_tours WHERE is_test = true")


def _spend_so_far():
    v = _scalar("SELECT COALESCE(SUM(usd),0) FROM paid_api_calls WHERE host = %s",
                (HOST,))
    return float(v) if v is not None else None


def _spend_breakdown():
    try:
        conn = _conn(); conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT provider, COUNT(*), COALESCE(SUM(usd),0) "
                "FROM paid_api_calls WHERE host = %s GROUP BY provider "
                "ORDER BY 3 DESC", (HOST,))
            rows = cur.fetchall()
        conn.close(); return rows
    except Exception as e:
        print(f"  [db] breakdown failed: {e}", flush=True); return []


# ───────────────────────── detectors ────────────────────────────────────────

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")
_ADDR_RE = re.compile(r"(?mi)^Address:\s*(.+)$")
_SOURCES_RE = re.compile(r"(?mi)^Sources?:\s*(.+)$")
_FOREIGN = re.compile(r"(?i)\b(saint\s+louis|honolulu|guston|holbein|pippin)\b")


def _norm_identity(s):
    """A crude order-ignored content-token set, to detect duplicate works in the
    DELIVERED stop titles (post-hoc verification that one work != three stops)."""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", (s or "").lower())
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    stripped = re.sub(r"[^\w\s]", " ", stripped)
    glue = {"the", "of", "and", "a", "an", "to", "in", "on", "with", "for"}
    toks = sorted(t for t in stripped.split() if t not in glue and len(t) >= 2)
    return " ".join(toks)


def _titles(text):
    return [t.strip() for t in _STOP_HEADER_RE.findall(text)]


def detect_delivered(text):
    n = _tc.count_delivered_stops(text)
    return (n >= 1), f"delivered_stops={n}"


def detect_no_citation_stop(text):
    """No stop title may be a scraped source/citation line (the 669 defect #2)."""
    bad = [t for t in _titles(text)
           if re.search(r"(?i)\b(source|references?|citation|portal|\[|\*\*|https?://)", t)]
    return (not bad), f"citation_titles={bad}"


def detect_distinct_works(text):
    """The 669B headline: no two delivered stops are the SAME work by a loose
    order-ignored content-token identity (so the three Spring Gardens -> one)."""
    titles = _titles(text)
    seen = {}
    dups = []
    for t in titles:
        k = _norm_identity(t)
        if not k:
            continue
        if k in seen:
            dups.append((seen[k], t))
        else:
            seen[k] = t
    return (not dups), f"duplicate_pairs={dups}"


def _report(text):
    titles = _titles(text)
    print("  --- STOP LIST ---", flush=True)
    for h in titles:
        print(f"  STOP TITLE: {h[:120]}", flush=True)
    print("  --- SOURCES LINES ---", flush=True)
    for s in _SOURCES_RE.findall(text)[:12]:
        print(f"  SOURCES: {s.strip()[:200]}", flush=True)
    print("  --- DETECTORS ---", flush=True)
    results = {}
    for name, fn in (("DELIVERED", detect_delivered),
                     ("NO_CITATION_STOP", detect_no_citation_stop),
                     ("DISTINCT_WORKS", detect_distinct_works)):
        try:
            ok, detail = fn(text)
        except Exception as e:
            ok, detail = False, f"detector error: {e}"
        results[name] = ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
    print(f"  [LOCAL-669B] ALL DETECTORS PASS = {all(results.values())}", flush=True)
    return results


def _store(location, text, n_stops):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-669B {location.split(',')[0][:40]} NORMAL {int(time.time())}"
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audio_tours
                    (tour_name, request_string, number_requested,
                     tour_content, stops_count, creator_type, storied_mode,
                     is_test, track, tour_kind, description)
                VALUES (%s, %s, %s, %s, %s, 'Test', true, true, 'beta', 'full', %s)
                RETURNING id
                """,
                (name, location, n_stops, text, n_stops,
                 "LOCAL-669B live fresh (NORMAL)"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


def _count_grounded(gen_log):
    """Count grounded requests from the generation log: the LOCAL-669 highlights
    line reports its own grounded request count; also count any other grounded
    research calls logged. Returns (highlights_grounded, serper_from_highlights,
    identity_collapses, raw_lines)."""
    hl_grounded = 0
    hl_serper = 0
    collapses = []
    for ln in gen_log.splitlines():
        m = re.search(r"highlights:\s*(\d+)\s*candidates,\s*(\d+)\s*verified,\s*cost\s*(\d+)\s*grounded request\s*\+\s*(\d+)\s*Serper", ln)
        if m:
            hl_grounded = int(m.group(3))
            hl_serper = int(m.group(4))
        if "[LOCAL-669B] IDENTITY DEDUP" in ln or "identity dedup:" in ln:
            collapses.append(ln.strip())
    return hl_grounded, hl_serper, collapses


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}",
      flush=True)

print(f"\n=== [NORMAL] generating: {LOCATION} ({STOPS} stops, museum) ===",
      flush=True)
t0 = time.time()
_buf = io.StringIO()


class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            s.write(data)
        return len(data)

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass


text = None
try:
    with contextlib.redirect_stdout(_Tee(_sys.__stdout__, _buf)):
        text, _p, _c = generate_tour_text(
            LOCATION, 'museum', "/app/tours/LOCAL669B_NORMAL.txt", STOPS,
            user_id=None)
except Exception as e:
    print(f"RUN ERROR: {e}", flush=True)

elapsed = time.time() - t0
gen_log = _buf.getvalue()

if not text:
    print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
else:
    delivered = _tc.count_delivered_stops(text)
    print(f"\nOUTCOME: DELIVERED — {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    _report(text)
    hl_grounded, hl_serper, collapses = _count_grounded(gen_log)
    print(f"\n[LOCAL-669B] grounded requests (highlights): {hl_grounded}  "
          f"serper 2nd-source: {hl_serper}", flush=True)
    print(f"[LOCAL-669B] identity-dedup collapse log lines:", flush=True)
    for c in collapses:
        print(f"    {c}", flush=True)
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        tc = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
        print(f"[cost] tour_total=${tc:.4f}", flush=True)
    except Exception:
        pass
    nid = _store(LOCATION, text, delivered)
    if nid:
        print(f"STORED audio_tours id = {nid}  (is_test=true)", flush=True)
        print(f"LOCAL669B_TOUR_ID={nid}", flush=True)
    try:
        with open("/app/tours/LOCAL669B_NORMAL_delivered.txt", "w",
                  encoding="utf-8") as _df:
            _df.write(text)
    except Exception:
        pass

print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}",
      flush=True)
print("[db] spend breakdown by provider:", flush=True)
for prov, cnt, usd in _spend_breakdown():
    print(f"    {prov}: {cnt} calls, ${float(usd):.4f}", flush=True)
print("=== LOCAL-669B run complete ===", flush=True)
