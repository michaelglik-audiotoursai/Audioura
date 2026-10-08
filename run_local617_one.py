#!/usr/bin/env python3
"""run_local617_one.py — generate ONE museum (env LOCAL617_VENUE) for LOCAL-617.

A thin, single-venue variant of run_local617_container.py so a flaky venue can be
re-run on its own without re-spending on the museums that already delivered.
Metered + capped the same way; stores an additive is_test row for critique.sh.
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _m
    _m.auto_meter('LOCAL-617')
except Exception as _e:
    print(f"[meter] unavailable: {_e}")

import os, re, time
os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '2.50')
os.environ['COST_HARD_LIMIT_USD'] = '2.50'
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')

VENUE = os.environ.get('LOCAL617_VENUE', 'Museo de Bellas Artes de Sevilla, Seville')
STOPS = 3
OUT = f"/app/tours/LOCAL617_ONE.txt"

from generate_tour_text import generate_tour_text
import work_first_evidence as wfe


def _store(location, text, n):
    import psycopg2
    conn = psycopg2.connect(
        host=os.environ.get('DB_HOST', 'development-postgres-2-1'),
        port=os.environ.get('DB_PORT', '5432'),
        dbname=os.environ.get('DB_NAME', 'audiotours'),
        user=os.environ.get('DB_USER', 'admin'),
        password=os.environ.get('DB_PASSWORD', 'password123'))
    conn.autocommit = True
    name = f"LOCAL-617 {location.split(',')[0]} {int(time.time())}"
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO audio_tours
               (tour_name, request_string, number_requested, tour_content,
                stops_count, creator_type, storied_mode, is_test, track,
                tour_kind, description)
               VALUES (%s,%s,%s,%s,%s,'Test',true,true,'beta','full',%s)
               RETURNING id""",
            (name, location, STOPS, text, n,
             'LOCAL-617 single-venue live run (critique seed)'))
        nid = cur.fetchone()[0]
    conn.close()
    return nid


print(f"=== LOCAL-617 single-venue run: {VENUE} ({STOPS} stops) ===", flush=True)
t0 = time.time()
try:
    text, out_file, _ = generate_tour_text(VENUE, 'museum', OUT, STOPS)
except Exception as e:
    print(f"RUN ERROR: {e}", flush=True)
    text = None
dt = time.time() - t0
if not text:
    print(f"OUTCOME: NO TOUR TEXT after {dt:.1f}s", flush=True)
    print("LOCAL617_TOUR_IDS=", flush=True)
else:
    titles = re.findall(r'(?mi)^\s*(Stop\s+\d+\s*[:\-].*)$', text)
    vtok = [w for w in re.split(r'[\s,\-]+', VENUE) if len(w) >= 3]
    share = wfe.institutional_share(text, venue_tokens=vtok)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {len(titles)} stops, "
          f"wall {dt:.1f}s", flush=True)
    print(f"[LOCAL-617] institutional sentence share (delivered): {100*share:.0f}%",
          flush=True)
    nid = _store(VENUE, text, len(titles))
    print(f"STORED audio_tours id = {nid}  (is_test=true)", flush=True)
    print(f"LOCAL617_TOUR_IDS={nid}", flush=True)
