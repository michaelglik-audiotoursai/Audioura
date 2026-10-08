#!/usr/bin/env python3
"""run_local619_container.py — LOCAL-619 live acceptance (ISOLATED container).

Runs THREE never-seen museums through the REAL generation path with the LOCAL-619
branch code mounted over /app, 3 stops each, metered + hard-capped at $2.50
COMBINED (TEST_GEMINI_MAX_USD, all providers, via tests/live_run_meter.py):

    1. Museo Thyssen-Bornemisza, Madrid, Spain       (3 stops)
    2. Musee d'Orsay, Paris, France                  (3 stops)
    3. Hamburger Kunsthalle, Hamburg, Germany        (3 stops)

For each museum it prints the DELIVERED CONCLUSION IN FULL (the one thing this
ticket is about), checks that the conclusion count equals the delivered stop
count, that no "That's N stops —" splice survives, and that exactly one
conclusion is present, then stores the delivered tour_content in the
development-postgres-2-1 ``audio_tours`` table (is_test=true, creator_type='Test')
so ``critique.sh <id>`` scores the SAME spoken text. No DELETE; only additive
is_test rows are written.

Usage (inside the isolated container):
    python3 run_local619_container.py
"""
# [LOCAL-613] Meter + cap this isolated run (install BEFORE importing generators).
import os as _os619
import sys as _sys619
_sys619.path.insert(0, _os619.path.join(
    _os619.path.dirname(_os619.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-619')
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
    ('Museo Thyssen-Bornemisza, Madrid, Spain', '/app/tours/LOCAL619_THYSSEN.txt'),
    ("Mus\u00e9e d'Orsay, Paris, France", '/app/tours/LOCAL619_ORSAY.txt'),
    ('Hamburger Kunsthalle, Hamburg, Germany', '/app/tours/LOCAL619_KUNSTHALLE.txt'),
]
STOPS = 3

print("=== LOCAL-619 isolated live run (three museums, 3 stops each) ===", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   combined cap: "
      f"${os.environ['COST_HARD_LIMIT_USD']}", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402

_SPLICE_RE = re.compile(r"That['\u2019]s\s+\d+\s+stops?\s+[\u2014-]")
_COUNT_RE = re.compile(r"That['\u2019]s\s+(\d+)\s+stops?")
_THREAD_RE = re.compile(r"you have followed the thread", re.IGNORECASE)
_RESTAURANT_RE = re.compile(r"we can build you a restaurant tour", re.IGNORECASE)


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
        name = f"LOCAL-619 {location.split(',')[0]} {int(time.time())}"
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
                 'LOCAL-619 isolated live run (critique seed)'))
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
    delivered = _tc.count_delivered_stops(text)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {len(titles)} stops, "
          f"path={_path}, wall {elapsed:.1f}s", flush=True)
    for m in titles:
        print(f"   {m.strip()[:110]}", flush=True)

    # [LOCAL-619] conclusion acceptance checks (visible)
    m_count = _COUNT_RE.search(text)
    concl_count = int(m_count.group(1)) if m_count else None
    print(f"\n[LOCAL-619] delivered stops = {delivered}; "
          f"conclusion count = {concl_count}; "
          f"MATCH = {concl_count == delivered}", flush=True)
    print(f"[LOCAL-619] no 'That's N stops —' splice = "
          f"{_SPLICE_RE.search(text) is None}", flush=True)
    print(f"[LOCAL-619] one conclusion = "
          f"{len(_THREAD_RE.findall(text)) == 1}  "
          f"(thread sentences = {len(_THREAD_RE.findall(text))})", flush=True)

    _tour_total = float(_cost.get('tour_total_cost', 0.0) or 0.0)
    print(f"[cost] tour_total=${_tour_total:.4f}", flush=True)

    # Print the CONCLUSION in full (everything from the thread/count opener to the
    # end, minus any trailing Sources block).
    print(f"\n---------------- CONCLUSION (in full) — {location} ----------------", flush=True)
    _concl_start = None
    m_thread = re.search(r'(?mi)^(?:From\s+.+?\s+to\s+.+?,\s+you have followed the thread'
                         r'|On this tour you have followed the thread)', text)
    m_cnt = _COUNT_RE.search(text)
    cands = [m.start() for m in (m_thread, m_cnt) if m]
    if cands:
        _concl_start = min(cands)
        _concl = text[_concl_start:]
        _src = re.search(r'(?mi)^\s*Sources:', _concl)
        if _src:
            _concl = _concl[:_src.start()]
        print(_concl.strip(), flush=True)
    else:
        print("(no conclusion found)", flush=True)

    new_id = _store_tour(location, text, len(titles))
    print(f"\nOUT: {out_file}", flush=True)
    if new_id:
        print(f"STORED audio_tours id = {new_id}  (is_test=true)", flush=True)
        print(f"CRITIQUE: ~/Audioura/.continuous_dev/calib/critique.sh {new_id}", flush=True)
        print(f"LOCAL619_TOUR_ID={new_id}", flush=True)
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

print("\n=== LOCAL-619 run complete ===", flush=True)
print(f"LOCAL619_TOUR_IDS={','.join(str(i) for i in ids)}", flush=True)
