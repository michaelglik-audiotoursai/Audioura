#!/usr/bin/env python3
"""run_local638_container.py — LOCAL-638 live acceptance (ISOLATED container).

Generates ONE fresh Frick Collection tour (3 stops) through the REAL generation
path with the LOCAL-638 branch code in the image, cache + pool OFF. This is the
live check for Michael's four Frick-523 listening notes (D640):

  1. practical facts (hours/price) live in the Stop-1 opening general description,
     never inside a stop's Orientation/narration;
  2. no stop ends on an unpaid teaser;
  3. a stop that narrates a pivotal decision/event states its consequence and
     links it back to the work (the Thomas More case);
  4. every stop except the last ends with directions to the next stop.

HARD CAP $1.00 (ticket), enforced by tests/live_run_meter.py (TEST_GEMINI_MAX_USD)
across ALL providers, plus a RESERVE GATE before the single tour. The delivered
SPOKEN text is stored as ONE additive is_test row for critique.sh / detectors.py.
is_test rows are the ONLY rows written. No DELETE. Only ONE tour is started.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-638')
except Exception as _meter_err:
    print(f"[LOCAL-613] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import socket
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tour (cache off)
os.environ['DISABLE_STOP_POOL'] = '1'             # pool off (ticket requirement)
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.00')
os.environ['COST_HARD_LIMIT_USD'] = '1.00'        # ticket HARD CAP
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
os.environ.setdefault('STOP_EDITOR_ENABLED', '1')  # Note 2 editor on

HARD_CAP_USD = 1.00
RESERVE_USD = 0.80          # start the tour only if spend + 0.80 <= cap
HOST = socket.gethostname()

VENUE = 'The Frick Collection, New York, NY'
STOPS = 3
SLUG = 'FRICK'

print("=== LOCAL-638 isolated live run (The Frick Collection, 3 stops) ===", flush=True)
print(f"host  : {HOST}", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   HARD CAP: ${HARD_CAP_USD}  "
      f"reserve: ${RESERVE_USD}  cache_off=1 pool_off=1 editor_on=1", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402


def _conn():
    import psycopg2
    dburl = os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', 'postgres-2'),
        port=os.environ.get('DB_PORT', '5432'),
        dbname=os.environ.get('DB_NAME', 'audiotours'),
        user=os.environ.get('DB_USER', 'admin'),
        password=os.environ.get('DB_PASSWORD', 'password123'))


def _row_count():
    try:
        conn = _conn(); conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM audio_tours")
            n = cur.fetchone()[0]
        conn.close(); return n
    except Exception as e:
        print(f"  [db] row count failed: {e}", flush=True); return None


def _test_row_count():
    try:
        conn = _conn(); conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM audio_tours WHERE is_test = true")
            n = cur.fetchone()[0]
        conn.close(); return n
    except Exception as e:
        print(f"  [db] test row count failed: {e}", flush=True); return None


def _spend_so_far():
    try:
        conn = _conn(); conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(usd),0) FROM paid_api_calls WHERE host = %s",
                (HOST,))
            v = float(cur.fetchone()[0] or 0.0)
        conn.close(); return v
    except Exception as e:
        print(f"  [db] spend read failed: {e}", flush=True); return None


def _report(text):
    for m in re.finditer(r"(?mi)^Stop\s+\d+:\s*(.+)$", text):
        print(f"  STOP TITLE: {m.group(1).strip()}", flush=True)
    for m in re.finditer(r"(?mi)\b([A-Z][^.\n]*?\bis open\b[^.\n]*\.)", text):
        print(f"  HOURS(spoken): {m.group(1).strip()}", flush=True)
    for m in re.finditer(r"(?mi)\b((?:Admission is|Standard admission is|admission is)[^.\n]*\.)", text):
        print(f"  ADMISSION(spoken): {m.group(1).strip()}", flush=True)


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-638 {location.split(',')[0]} {int(time.time())}"
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
                 f"LOCAL-638 live fresh ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


def _run_one(location, stops, slug):
    spend = _spend_so_far()
    print(f"\n[reserve-gate] spend_so_far=${spend if spend is not None else '?'} "
          f"+ reserve ${RESERVE_USD} vs cap ${HARD_CAP_USD}", flush=True)
    if spend is not None and (spend + RESERVE_USD) > HARD_CAP_USD:
        print(f"[reserve-gate] SKIP {slug}: would exceed cap "
              f"(${spend:.4f}+${RESERVE_USD} > ${HARD_CAP_USD})", flush=True)
        return None
    print(f"=== generating: {location} ({stops} stops) ===", flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            location, 'museum', f"/app/tours/LOCAL638_{slug}.txt", stops, user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {location}: {e}", flush=True); return None
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True); return None
    delivered = _tc.count_delivered_stops(text)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    _report(text)
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        _tot = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
        print(f"[cost] tour_total=${_tot:.4f}", flush=True)
    except Exception:
        pass
    nid = _store(location, text, delivered, slug)
    if nid:
        print(f"STORED audio_tours id = {nid}  (is_test=true)", flush=True)
        print(f"LOCAL638_TOUR_ID={nid}", flush=True)
    return nid


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}", flush=True)

tid = _run_one(VENUE, STOPS, SLUG)

print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}", flush=True)
print("=== LOCAL-638 run complete ===", flush=True)
print(f"LOCAL638_TOUR_ID={tid if tid else ''}", flush=True)
