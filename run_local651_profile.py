#!/usr/bin/env python3
"""run_local651_profile.py — LOCAL-651 Step 1 PROFILE run (isolated container).

ONE fresh Courtauld 3-stop tour through the REAL generation path, cache + pool
OFF, FAST_PIPELINE OFF (profiling the current serial pipeline). It prints the
pipeline's own [TIMING] phase line and then the aggregated [TIMING-SUB] table
(every network/LLM wait, summed across calls, with call counts and the worst
single call ~= critical path).

The delivered spoken text is stored as ONE additive is_test row (so the same run
can later be scored). is_test rows are the ONLY rows written. No DELETE.

Metered + capped by tests/live_run_meter.py (single tour; cap kept well under
the ticket's $3.00). Row counts printed before/after; spend read from
paid_api_calls for this host.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-651')
except Exception as _meter_err:
    print(f"[LOCAL-651] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import socket
import time

# Fresh tour, storied mode, cache + pool off. FAST_PIPELINE OFF (profile the
# current serial pipeline — this run produces the baseline [TIMING-SUB] table).
os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['DISABLE_STOP_POOL'] = '1'
os.environ.pop('FAST_PIPELINE', None)
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('COST_HARD_LIMIT_USD', '1.50')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.50')
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
os.environ.setdefault('STOP_EDITOR', '1')
os.environ.setdefault('STOP_EDITOR_ENABLED', '1')

HOST = socket.gethostname()
LOCATION = 'The Courtauld Gallery, London, United Kingdom'
STOPS = 3

print("=== LOCAL-651 PROFILE: Courtauld 3-stop, FAST_PIPELINE OFF ===", flush=True)
print(f"host  : {HOST}", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}  cache_off=1 pool_off=1 "
      f"FAST_PIPELINE=OFF", flush=True)

import phase_timer as _pt
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


def _spend_so_far():
    v = _scalar("SELECT COALESCE(SUM(usd),0) FROM paid_api_calls WHERE host = %s",
                (HOST,))
    return float(v) if v is not None else None


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-651 {location.split(',')[0][:40]} {slug} {int(time.time())}"
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
                 f"LOCAL-651 profile ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


print(f"[db] audio_tours row count BEFORE: {_row_count()}", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}",
      flush=True)

t0 = time.time()
text = None
try:
    text, _p, _c = generate_tour_text(
        LOCATION, 'museum', f"/app/tours/LOCAL651_PROFILE.txt", STOPS,
        user_id=None)
except Exception as e:
    print(f"RUN ERROR: {e}", flush=True)
elapsed = time.time() - t0

# The [TIMING-SUB] aggregate table — the deliverable of Step 1.
print("\n================= LOCAL-651 [TIMING-SUB] AGGREGATE =================",
      flush=True)
try:
    _pt.get_sub_timer().summary()
except Exception as _e:
    print(f"[TIMING-SUB] summary unavailable: {_e}", flush=True)

if text:
    headers = re.findall(r"(?mi)^Stop\s+\d+:\s*(.+)$", text)
    delivered = _tc.count_delivered_stops(text)
    print(f"\nOUTCOME: DELIVERED {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    for h in headers:
        print(f"  STOP TITLE: {h.strip()[:70]}", flush=True)
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        print(f"  [cost] tour_total=$"
              f"{float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0):.4f}",
              flush=True)
    except Exception:
        pass
    nid = _store(LOCATION, text, delivered, 'PROFILE')
    if nid:
        print(f"  STORED audio_tours id = {nid} (is_test=true)", flush=True)
        print(f"  LOCAL651_PROFILE_TOUR_ID={nid}", flush=True)
else:
    print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True)

print(f"\n[db] audio_tours row count AFTER: {_row_count()}", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}",
      flush=True)
print("=== LOCAL-651 profile run complete ===", flush=True)
