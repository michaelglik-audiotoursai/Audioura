#!/usr/bin/env python3
"""run_local618_container.py — LOCAL-618 live acceptance (ISOLATED container).

Runs the THREE ticket museums through the REAL generation path with the
LOCAL-618 branch code mounted over /app, 3 stops each, metered + hard-capped at
$2.50 COMBINED (TEST_GEMINI_MAX_USD, all providers, via tests/live_run_meter.py):

    1. Museum Boijmans Van Beuningen, Rotterdam, Netherlands  (3 stops)  — #3 venue resolution
    2. Museo de Bellas Artes de Sevilla, Seville, Spain        (3 stops)  — #1/#2/#4
    3. Musee des Beaux-Arts de Rouen, Rouen, France            (3 stops)

For each museum it prints STOP 1 IN FULL (so the orientation pre-tell #1, the
grammar/splice lint #2 and the honest unpublished-hours line #4 are visible),
measures institutional share, and stores the delivered tour_content in the
development-postgres-2-1 ``audio_tours`` table (is_test=true, creator_type='Test')
so ``critique.sh <id>`` scores the SAME spoken text. No DELETE; only additive
is_test rows are written.

Usage (inside the isolated container):
    python3 run_local618_container.py
"""
# [LOCAL-613] Meter + cap this isolated run (install BEFORE importing generators).
import os as _os618
import sys as _sys618
_sys618.path.insert(0, _os618.path.join(
    _os618.path.dirname(_os618.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-618')
except Exception as _meter_err:
    print(f"[LOCAL-613] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # force FRESH tours
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '2.50')
os.environ['COST_HARD_LIMIT_USD'] = '2.50'        # ticket cap (combined)
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')

RUNS = [
    ('Museum Boijmans Van Beuningen, Rotterdam, Netherlands', '/app/tours/LOCAL618_BOIJMANS.txt'),
    ('Museo de Bellas Artes de Sevilla, Seville, Spain', '/app/tours/LOCAL618_SEVILLA.txt'),
    ('Mus\u00e9e des Beaux-Arts de Rouen, Rouen, France', '/app/tours/LOCAL618_ROUEN.txt'),
]
STOPS = 3

print("=== LOCAL-618 isolated live run (three museums, 3 stops each) ===", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   combined cap: "
      f"${os.environ['COST_HARD_LIMIT_USD']}", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
try:
    import work_first_evidence as wfe  # noqa: E402
except Exception:
    wfe = None


def _store_tour(location, text, n_stops):
    """Store the delivered tour so critique.sh can score it. Returns new id or None."""
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
        name = f"LOCAL-618 {location.split(',')[0]} {int(time.time())}"
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
                 'LOCAL-618 isolated live run (critique seed)'))
            new_id = cur.fetchone()[0]
        conn.close()
        return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True)
        return None


def _report(location, out_file, text, elapsed):
    print(f"\n################ {location} ################", flush=True)
    try:
        from generate_tour_text import (_LAST_GENERATION_COST, _LAST_DELIVERY_PATH)
        _cost = dict(_LAST_GENERATION_COST or {})
        _path = _LAST_DELIVERY_PATH
    except Exception:
        _cost, _path = {}, '?'

    if not text:
        print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s (path={_path})", flush=True)
        return None

    titles = re.findall(r'(?mi)^\s*(Stop\s+\d+\s*[:\-].*)$', text)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {len(titles)} stops, "
          f"path={_path}, wall {elapsed:.1f}s", flush=True)
    for m in titles:
        print(f"   {m.strip()[:110]}", flush=True)

    if wfe is not None:
        try:
            _vtok = [w for w in re.split(r'[\s,\-]+', location) if len(w) >= 3]
            share = wfe.institutional_share(text, venue_tokens=_vtok)
            print(f"\n[LOCAL-617] institutional sentence share (delivered): "
                  f"{100*share:.0f}%", flush=True)
        except Exception:
            pass

    # [LOCAL-618 #4] honesty line / no 'check <domain>' pointer check (visible)
    _honest = text.count("Opening hours weren't published where we could read them")
    _check_ptr = len(re.findall(r"(?i)check[^.?!]*before you go", text))
    print(f"[LOCAL-618 #4] unpublished-hours line count={_honest}  "
          f"'check…before you go' count={_check_ptr}", flush=True)

    _tour_total = float(_cost.get('tour_total_cost', 0.0) or 0.0)
    print(f"[cost] tour_total=${_tour_total:.4f}", flush=True)

    print(f"\n---------------- STOP 1 (in full) — {location} ----------------", flush=True)
    _s1 = re.search(r'(Stop\s+1:.*?)(?=\nStop\s+2:|\Z)', text, re.DOTALL)
    print((_s1.group(1).strip() if _s1 else '(Stop 1 not found)'), flush=True)

    new_id = _store_tour(location, text, len(titles))
    print(f"\nOUT: {out_file}", flush=True)
    if new_id:
        print(f"STORED audio_tours id = {new_id}  (is_test=true)", flush=True)
        print(f"CRITIQUE: ~/Audioura/.continuous_dev/calib/critique.sh {new_id}", flush=True)
        print(f"LOCAL618_TOUR_ID={new_id}", flush=True)
    return new_id


ids = []
for location, out in RUNS:
    print(f"\n=== generating: {location} ({STOPS} stops) ===", flush=True)
    t0 = time.time()
    try:
        text, out_file, _coords = generate_tour_text(location, 'museum', out, STOPS)
    except Exception as _run_err:
        print(f"RUN ERROR for {location}: {_run_err}", flush=True)
        text, out_file = None, out
    _id = _report(location, out_file, text, time.time() - t0)
    if _id:
        ids.append(_id)

print("\n=== LOCAL-618 run complete ===", flush=True)
print(f"LOCAL618_TOUR_IDS={','.join(str(i) for i in ids)}", flush=True)
