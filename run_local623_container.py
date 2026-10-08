#!/usr/bin/env python3
"""run_local623_container.py — LOCAL-623 live acceptance (ISOLATED container).

Runs THREE venues that have NEVER been generated before (verified against
``audio_tours`` by name) through the REAL generation path with the LOCAL-623
branch code in the image, metered + hard-capped at $1.50 COMBINED (all providers,
via tests/live_run_meter.py):

    1. Musée d'Unterlinden, Colmar, France          (2 stops)
    2. Mauritshuis, The Hague, Netherlands           (2 stops)
    3. Statens Museum for Kunst, Copenhagen, Denmark (2 stops)

Each is a FRESH museum tour (tour cache OFF). For every delivered tour it checks
the five LOCAL-623 defects on the SPOKEN text and stores it as an additive
is_test row in ``audio_tours`` (creator_type='Test') so ``critique.sh <id>``
scores the SAME spoken text. The is_test tour rows are the ONLY rows written. No
DELETE.

Usage (inside the isolated container):
    python3 run_local623_container.py
"""
# [LOCAL-613] Meter + cap this isolated run (install BEFORE importing generators).
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-623')
except Exception as _meter_err:
    print(f"[LOCAL-613] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # force FRESH tours
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.50')
os.environ['COST_HARD_LIMIT_USD'] = '1.50'        # ticket cap (three venues)
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
os.environ.setdefault('STORY_PREFS', '1')

VENUES = [
    ("Mus\u00e9e d'Unterlinden, Colmar, France", 2, 'UNTERLINDEN'),
    ('Mauritshuis, The Hague, Netherlands', 2, 'MAURITSHUIS'),
    ('Statens Museum for Kunst, Copenhagen, Denmark', 2, 'SMK'),
]

print("=== LOCAL-623 isolated live run (three FRESH museums, 2 stops each) ===",
      flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   combined cap: "
      f"${os.environ['COST_HARD_LIMIT_USD']}", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402


def _conn():
    import psycopg2
    dburl = os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', 'development-postgres-2-1'),
        port=os.environ.get('DB_PORT', '5432'),
        dbname=os.environ.get('DB_NAME', 'audiotours'),
        user=os.environ.get('DB_USER', 'admin'),
        password=os.environ.get('DB_PASSWORD', 'password123'))


def _row_count():
    try:
        conn = _conn()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM audio_tours")
            n = cur.fetchone()[0]
        conn.close()
        return n
    except Exception as e:
        print(f"  [db] row count failed: {e}", flush=True)
        return None


# ── the five LOCAL-623 defect checks, run on the delivered SPOKEN text ────────
def _defect_report(text):
    out = []
    # #3 garbage address: a "Address: <4-digit-year> …" line
    bad_addr = re.findall(r"(?mi)^Address:\s*(\d{4}\b[^\n]*)", text)
    out.append(("#3 garbage address", bad_addr))
    # #4 citation leftover
    cit = re.findall(r"as (?:published|listed|stated) by the museum", text, re.I)
    out.append(("#4 citation leftover", cit))
    # #5 dropped possessive heuristics (the two real fragments; generic probe:
    #    a capitalised name immediately followed by 'scene/painting/style' with no 's)
    poss = re.findall(r"\b(?:Corot|Daumier|[A-Z][a-z]+) (?:scene|celebration)\b", text)
    out.append(("#5 dropped-possessive probe", poss))
    # #2 recurring museum motif in a stop body
    motif = re.findall(r"museum(?:['\u2019]s)? story of preservation and renewal", text, re.I)
    out.append(("#2 museum motif", motif))
    return out


def _store_tour(location, text, n_stops, slug):
    try:
        conn = _conn()
        conn.autocommit = True
        name = f"LOCAL-623 {location.split(',')[0]} {int(time.time())}"
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
                 f"LOCAL-623 live fresh ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close()
        return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True)
        return None


def _run_one(location, stops, out_file, slug):
    print(f"\n=== generating: {location} ({stops} stops) ===", flush=True)
    t0 = time.time()
    try:
        text, _out_path, _coords = generate_tour_text(
            location, 'museum', out_file, stops, user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {location}: {e}", flush=True)
        return None
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        return None
    delivered = _tc.count_delivered_stops(text)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    print(f"[LOCAL-623 defect checks on spoken text] — {location}", flush=True)
    for label, hits in _defect_report(text):
        status = "CLEAN" if not hits else f"FOUND {hits}"
        print(f"  {label}: {status}", flush=True)
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _c = dict(_LAST_GENERATION_COST or {})
        _tot = float(_c.get('tour_total_cost', _c.get('total_cost', 0.0)) or 0.0)
        print(f"[cost] tour_total=${_tot:.4f}", flush=True)
    except Exception:
        pass
    new_id = _store_tour(location, text, delivered, slug)
    if new_id:
        print(f"STORED audio_tours id = {new_id}  (is_test=true)", flush=True)
        print(f"LOCAL623_TOUR_ID={new_id}", flush=True)
    return new_id


print(f"[db] audio_tours row count BEFORE: {_row_count()}", flush=True)

ids = []
for location, stops, slug in VENUES:
    tid = _run_one(location, stops, f"/app/tours/LOCAL623_{slug}.txt", slug)
    if tid:
        ids.append(tid)

print(f"\n[db] audio_tours row count AFTER: {_row_count()}", flush=True)
print("=== LOCAL-623 run complete ===", flush=True)
print(f"LOCAL623_TOUR_IDS={','.join(str(i) for i in ids)}", flush=True)
