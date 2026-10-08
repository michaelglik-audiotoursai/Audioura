#!/usr/bin/env python3
"""run_local631_container.py — LOCAL-631 live concurrency acceptance (ISOLATED).

Reproduces the bench-R0 condition that leaked the Rijksmuseum's hours/admission
into the Musée Rodin: TWO tours generated AT THE SAME TIME in one process, one
thread each, through the REAL generation path with this branch's code in the
image. Cache + pool OFF (fresh). 2 stops each.

    Thread A: Musée Rodin, Paris, France        (2 stops)
    Thread B: Rijksmuseum, Amsterdam, Netherlands (2 stops)

Each delivered tour's practical-facts sentence (spoken hours + admission) is
printed; the acceptance is that each is the tour's OWN venue's facts — Rodin
never speaks Amsterdam hours, Rijksmuseum never speaks Paris admission.

HARD CAP $1.20 COMBINED, enforced with the RESERVE GATE (LOCAL-626/627): the
pair is started only if (spend_so_far + reserve) <= cap, spend read from
paid_api_calls for THIS container host. is_test rows are the ONLY rows written.
No DELETE. Reports audio_tours row count before and after.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-631')
except Exception as _meter_err:
    print(f"[LOCAL-613] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import socket
import threading
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tours (cache off)
os.environ['DISABLE_STOP_POOL'] = '1'             # pool off (ticket requirement)
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.20')
os.environ['COST_HARD_LIMIT_USD'] = '1.20'        # ticket HARD CAP
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')

HARD_CAP_USD = 1.20
# Two 2-stop tours run concurrently; reserve the whole pair's expected spend
# before launching EITHER, so we never start a pair that could cross the cap.
RESERVE_USD = 1.00
HOST = socket.gethostname()

VENUES = [
    ('Musée Rodin, Paris, France', 2, 'RODIN'),
    ('Rijksmuseum, Amsterdam, Netherlands', 2, 'RIJKS'),
]

print("=== LOCAL-631 isolated CONCURRENT live run (Rodin + Rijksmuseum, 2 stops each) ===", flush=True)
print(f"host  : {HOST}", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   HARD CAP: ${HARD_CAP_USD}  "
      f"reserve: ${RESERVE_USD}  cache=OFF pool=OFF", flush=True)

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
        conn = _conn(); conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM audio_tours")
            n = cur.fetchone()[0]
        conn.close(); return n
    except Exception as e:
        print(f"  [db] row count failed: {e}", flush=True); return None


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


# Practical-facts extraction: the spoken opening hours and admission sentences.
_HOURS_RE = re.compile(
    r"(?mi)((?:Open\b|The museum is open\b|The [A-Z][\w' ]*is open\b|Hours\b)[^.\n]*\.)")
_ADMISSION_RE = re.compile(
    r"(?mi)((?:Adult admission\b|Admission\b|A ticket\b|Standard admission\b|"
    r"Entry\b|Entrance\b)[^.\n]*\.)")


def _practical_facts(text):
    hours = [m.group(1).strip() for m in _HOURS_RE.finditer(text)]
    adm = [m.group(1).strip() for m in _ADMISSION_RE.finditer(text)]
    return hours, adm


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-631 {location.split(',')[0]} {int(time.time())}"
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
                 f"LOCAL-631 concurrent fresh ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


_results = {}
_lock = threading.Lock()


def _run_one(location, stops, slug, start_barrier):
    # Both threads block here, then are released together => true concurrency.
    try:
        start_barrier.wait(timeout=30)
    except Exception:
        pass
    t0 = time.time()
    print(f"[{slug}] START generate: {location} ({stops} stops) @ {t0:.1f}", flush=True)
    try:
        text, _p, _c = generate_tour_text(
            location, 'museum', f"/app/tours/LOCAL631_{slug}.txt", stops, user_id=None)
    except Exception as e:
        print(f"[{slug}] RUN ERROR: {e}", flush=True)
        with _lock:
            _results[slug] = {'error': str(e)}
        return
    elapsed = time.time() - t0
    if not text:
        print(f"[{slug}] OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        with _lock:
            _results[slug] = {'error': 'no_text'}
        return
    delivered = _tc.count_delivered_stops(text)
    hours, adm = _practical_facts(text)
    # Read this job's cost from the (now per-job) holder.
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        _tot = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
    except Exception:
        _tot = -1.0
    nid = _store(location, text, delivered, slug)
    with _lock:
        _results[slug] = {
            'location': location, 'chars': len(text), 'stops': delivered,
            'wall': elapsed, 'hours': hours, 'admission': adm,
            'cost': _tot, 'id': nid, 'text': text,
        }
    print(f"[{slug}] OUTCOME: DELIVERED {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s, cost ${_tot:.4f}, id={nid}", flush=True)


# ---- reserve gate (combined, before launching either thread) ----------------
_before = _row_count()
_spend_before = _spend_so_far()
print(f"[db] audio_tours row count BEFORE: {_before}", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_before}", flush=True)
print(f"[reserve-gate] spend_so_far=${_spend_before if _spend_before is not None else '?'} "
      f"+ reserve ${RESERVE_USD} vs cap ${HARD_CAP_USD}", flush=True)

if _spend_before is not None and (_spend_before + RESERVE_USD) > HARD_CAP_USD:
    print(f"[reserve-gate] SKIP pair: would exceed cap "
          f"(${_spend_before:.4f}+${RESERVE_USD} > ${HARD_CAP_USD}) — not generating", flush=True)
    print(f"[db] audio_tours row count AFTER: {_row_count()}", flush=True)
    print("=== LOCAL-631 run complete (gated) ===", flush=True)
    _sys.exit(0)

barrier = threading.Barrier(len(VENUES))
threads = [
    threading.Thread(target=_run_one, args=(loc, stops, slug, barrier))
    for (loc, stops, slug) in VENUES
]
for t in threads:
    t.start()
for t in threads:
    t.join()

# ---- report -----------------------------------------------------------------
print("\n================= PRACTICAL-FACTS (per concurrent tour) =================", flush=True)
for _loc, _stops, slug in VENUES:
    r = _results.get(slug, {})
    if r.get('error'):
        print(f"[{slug}] ERROR: {r['error']}", flush=True)
        continue
    print(f"[{slug}] {r['location']}  (id={r['id']}, {r['stops']} stops, ${r['cost']:.4f})", flush=True)
    for h in r['hours']:
        print(f"    HOURS(spoken):     {h}", flush=True)
    for a in r['admission']:
        print(f"    ADMISSION(spoken): {a}", flush=True)
    if not r['hours'] and not r['admission']:
        print("    (no practical-facts sentence detected in spoken text)", flush=True)

# ---- cross-contamination assertion -----------------------------------------
print("\n================= CROSS-CONTAMINATION CHECK =================", flush=True)
rodin = _results.get('RODIN', {})
rijks = _results.get('RIJKS', {})
_leak = False
if rodin.get('text') and rijks.get('text'):
    # Each tour's practical facts must not appear in the other's text.
    for a in rijks.get('admission', []) + rijks.get('hours', []):
        if a and a in rodin['text']:
            print(f"  LEAK: Rijksmuseum fact appears in Rodin tour: {a!r}", flush=True)
            _leak = True
    for a in rodin.get('admission', []) + rodin.get('hours', []):
        if a and a in rijks['text']:
            print(f"  LEAK: Rodin fact appears in Rijksmuseum tour: {a!r}", flush=True)
            _leak = True
    if not _leak:
        print("  PASS: no venue's hours/admission appear in the other's tour.", flush=True)
else:
    print("  (one or both tours did not deliver; see errors above)", flush=True)

print(f"\n[db] audio_tours row count AFTER: {_row_count()}", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}", flush=True)
_ids = [str(_results[s]['id']) for _, _, s in VENUES
        if _results.get(s, {}).get('id')]
print(f"LOCAL631_TOUR_IDS={','.join(_ids)}", flush=True)
print("=== LOCAL-631 run complete ===", flush=True)
