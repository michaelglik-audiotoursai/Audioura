#!/usr/bin/env python3
"""run_local622_container.py — LOCAL-622 live acceptance (ISOLATED container).

Runs ONE fresh museum tour through the REAL generation path with the LOCAL-622
branch code in the image, metered + hard-capped at $1.00 (TEST_GEMINI_MAX_USD,
all providers combined, via tests/live_run_meter.py):

    Kunsthaus Zürich, Zurich, Switzerland   (5 stops)   — the D635 venue

Deliverables proven here:
  * The [TIMING] TOTAL line, so `external_lookups` is auditable and visibly at
    or under ~150s (D635 measured 663.4s on the same venue, pre-budget).
  * The LOCAL-622 OSM lookup-budget summary line.
  * The paid_api_calls totals for THIS container host (printed from the DB by
    the live shell wrapper via SELECT ... WHERE host = '<container hostname>').

No DELETE. The delivered tour is stored as an additive is_test row for critique.
"""
# [LOCAL-613] Meter + cap this isolated run (install BEFORE importing generators).
import os as _os622
import sys as _sys622
_sys622.path.insert(0, _os622.path.join(
    _os622.path.dirname(_os622.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-622')
except Exception as _meter_err:
    print(f"[LOCAL-613] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import socket
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # force a FRESH tour
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.00')
os.environ['COST_HARD_LIMIT_USD'] = '1.00'        # ticket cap
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')

LOCATION = 'Kunsthaus Zürich, Zurich, Switzerland'
OUT_FILE = '/app/tours/LOCAL622_KUNSTHAUS.txt'
STOPS = 5

print("=== LOCAL-622 isolated live run (Kunsthaus Zürich, 5 stops) ===", flush=True)
print(f"host  : {socket.gethostname()}", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   cap: ${os.environ['COST_HARD_LIMIT_USD']}", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402


def _store_tour(location, text, n_stops):
    try:
        import psycopg2
    except Exception as e:
        print(f"  [store] psycopg2 unavailable: {e}", flush=True)
        return None
    dburl = os.environ.get('DATABASE_URL')
    try:
        conn = psycopg2.connect(dburl) if dburl else psycopg2.connect(
            host=os.environ.get('DB_HOST', 'development-postgres-2-1'),
            port=os.environ.get('DB_PORT', '5432'),
            dbname=os.environ.get('DB_NAME', 'audiotours'),
            user=os.environ.get('DB_USER', 'admin'),
            password=os.environ.get('DB_PASSWORD', 'password123'))
        conn.autocommit = True
        name = f"LOCAL-622 {location.split(',')[0]} {int(time.time())}"
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
                (name, location, STOPS, text, n_stops,
                 'LOCAL-622 isolated live run (budget + poll fix)'))
            new_id = cur.fetchone()[0]
        conn.close()
        return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True)
        return None


print(f"\n=== generating: {LOCATION} ({STOPS} stops) ===", flush=True)
t0 = time.time()
try:
    text, out_file, _coords = generate_tour_text(LOCATION, 'museum', OUT_FILE, STOPS)
except Exception as _run_err:
    print(f"RUN ERROR for {LOCATION}: {_run_err}", flush=True)
    text, out_file = None, OUT_FILE
elapsed = time.time() - t0

print(f"\n################ {LOCATION} ################", flush=True)
try:
    from generate_tour_text import (_LAST_GENERATION_COST, _LAST_DELIVERY_PATH)
    _cost = dict(_LAST_GENERATION_COST or {})
    _path = _LAST_DELIVERY_PATH
except Exception:
    _cost, _path = {}, '?'

if not text:
    print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s (path={_path})", flush=True)
else:
    titles = re.findall(r'(?mi)^\s*(Stop\s+\d+\s*[:\-].*)$', text)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {len(titles)} stops, "
          f"path={_path}, wall {elapsed:.1f}s", flush=True)
    for m in titles:
        print(f"   {m.strip()[:110]}", flush=True)
    _tour_total = float(_cost.get('tour_total_cost', 0.0) or 0.0)
    print(f"[cost] tour_total=${_tour_total:.4f}", flush=True)
    new_id = _store_tour(LOCATION, text, len(titles))
    if new_id:
        print(f"STORED audio_tours id = {new_id}  (is_test=true)", flush=True)
        print(f"LOCAL622_TOUR_ID={new_id}", flush=True)

print(f"\nhost  : {socket.gethostname()}", flush=True)
print("=== LOCAL-622 run complete ===", flush=True)
