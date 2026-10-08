#!/usr/bin/env python3
"""run_local623_one.py — one replacement venue for the LOCAL-623 live set.

Mauritshuis failed venue resolution (wrong Wikidata entity, 0 works) — a
resolver issue unrelated to the LOCAL-623 fixes. This runs ONE fresh,
never-generated replacement so the live set is three delivered tours. Metered +
hard-capped (the harness-level cap still applies via the container env).
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _lrm
    _lrm.auto_meter('LOCAL-623')
except Exception as _e:
    print(f"[meter] unavailable ({_e})")

import os
import re
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ['COST_HARD_LIMIT_USD'] = os.environ.get('COST_HARD_LIMIT_USD', '1.50')
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
os.environ.setdefault('STORY_PREFS', '1')

LOCATION = os.environ.get('L623_VENUE', 'Alte Pinakothek, Munich, Germany')
STOPS = int(os.environ.get('L623_STOPS', '2'))
SLUG = os.environ.get('L623_SLUG', 'ALTEPIN')

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402


def _conn():
    import psycopg2
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', 'development-postgres-2-1'),
        port=os.environ.get('DB_PORT', '5432'),
        dbname=os.environ.get('DB_NAME', 'audiotours'),
        user=os.environ.get('DB_USER', 'admin'),
        password=os.environ.get('DB_PASSWORD', 'password123'))


def _row_count():
    try:
        c = _conn(); c.autocommit = True
        with c.cursor() as cur:
            cur.execute("SELECT count(*) FROM audio_tours"); n = cur.fetchone()[0]
        c.close(); return n
    except Exception as e:
        print(f"[db] count failed: {e}"); return None


print(f"[db] row count BEFORE: {_row_count()}", flush=True)
print(f"=== generating: {LOCATION} ({STOPS} stops) ===", flush=True)
t0 = time.time()
text, _p, _c = generate_tour_text(LOCATION, 'museum',
                                  f"/app/tours/LOCAL623_{SLUG}.txt", STOPS,
                                  user_id=None)
el = time.time() - t0
if not text:
    print(f"OUTCOME: NO TOUR TEXT after {el:.1f}s", flush=True)
    _sys.exit(0)
delivered = _tc.count_delivered_stops(text)
print(f"OUTCOME: DELIVERED — {len(text)} chars, {delivered} stops, wall {el:.1f}s",
      flush=True)
checks = [
    ("#3 garbage address", re.findall(r"(?mi)^Address:\s*(\d{4}\b[^\n]*)", text)),
    ("#4 citation leftover", re.findall(r"as (?:published|listed|stated) by the museum", text, re.I)),
    ("#5 dropped-possessive probe", re.findall(r"\b[A-Z][a-z]+ (?:scene|celebration)\b", text)),
    ("#2 museum motif", re.findall(r"museum(?:['\u2019]s)? story of preservation and renewal", text, re.I)),
]
for label, hits in checks:
    print(f"  {label}: {'CLEAN' if not hits else 'FOUND '+str(hits)}", flush=True)
try:
    c = _conn(); c.autocommit = True
    with c.cursor() as cur:
        cur.execute(
            """INSERT INTO audio_tours
               (tour_name, request_string, number_requested, tour_content,
                stops_count, creator_type, storied_mode, is_test, track,
                tour_kind, description)
               VALUES (%s,%s,%s,%s,%s,'Test',true,true,'beta','full',%s)
               RETURNING id""",
            (f"LOCAL-623 {LOCATION.split(',')[0]} {int(time.time())}", LOCATION,
             delivered, text, delivered, f"LOCAL-623 live fresh ({SLUG})"))
        nid = cur.fetchone()[0]
    c.close()
    print(f"STORED audio_tours id = {nid}  (is_test=true)", flush=True)
    print(f"LOCAL623_TOUR_ID={nid}", flush=True)
except Exception as e:
    print(f"[store] failed: {e}", flush=True)
print(f"[db] row count AFTER: {_row_count()}", flush=True)
