#!/usr/bin/env python3
"""run_local649_container.py — LOCAL-649 live A/B (ISOLATED container).

Four FRESH tours through the REAL generation path, cache + pool OFF:

  1. Courtauld, 3 stops, PARALLEL_STOPS OFF   (baseline)
  2. Courtauld, 3 stops, PARALLEL_STOPS ON    (plan → parallel write → stitch)
  3. Walters,   3 stops, PARALLEL_STOPS OFF   (baseline)
  4. Walters,   3 stops, PARALLEL_STOPS ON

For each tour we report: delivered stop count, wall time, the [TIMING] phases the
pipeline prints (narration phase is where the parallel write lands), the tour's
own cost from _LAST_GENERATION_COST, and spend from paid_api_calls for this host.
Each delivered SPOKEN text is stored as ONE additive is_test row for
critique.sh / detectors.py. is_test rows are the ONLY rows written. No DELETE.

HARD CAP $2.50 COMBINED (ticket), enforced by tests/live_run_meter.py across ALL
providers, plus a RESERVE GATE before each tour. Row counts are printed before
and after. At most FOUR tours are started.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-649')
except Exception as _meter_err:
    print(f"[LOCAL-649] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import socket
import time

# Fresh tours, storied mode, cache + pool off (ticket requirement).
os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['DISABLE_STOP_POOL'] = '1'
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '2.50')
os.environ['COST_HARD_LIMIT_USD'] = '2.50'
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
os.environ.setdefault('STOP_EDITOR', '1')
os.environ.setdefault('STOP_EDITOR_ENABLED', '1')

HARD_CAP_USD = 2.50
RESERVE_USD = 0.55        # start a tour only if spend + 0.55 <= cap
HOST = socket.gethostname()

# (location, stops, tour_type, slug, parallel_on)
TOURS = [
    ('The Courtauld Gallery, London, United Kingdom', 3, 'museum', 'COURTAULD_OFF', False),
    ('The Courtauld Gallery, London, United Kingdom', 3, 'museum', 'COURTAULD_ON',  True),
    ('The Walters Art Museum, Baltimore, Maryland',   3, 'museum', 'WALTERS_OFF',   False),
    ('The Walters Art Museum, Baltimore, Maryland',   3, 'museum', 'WALTERS_ON',    True),
]

print("=== LOCAL-649 isolated live A/B (Courtauld 3 + Walters 3, OFF vs ON) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   HARD CAP(combined): "
      f"${HARD_CAP_USD}  reserve: ${RESERVE_USD}  cache_off=1 pool_off=1",
      flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402
import parallel_stops as _ps  # noqa: E402


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


def _test_row_count():
    return _scalar("SELECT count(*) FROM audio_tours WHERE is_test = true")


def _spend_so_far():
    v = _scalar("SELECT COALESCE(SUM(usd),0) FROM paid_api_calls WHERE host = %s",
                (HOST,))
    return float(v) if v is not None else None


def _detectors(text):
    """Lightweight structural detectors on the delivered text, mirroring the
    checks the live runners print (full scoring is critique.sh/detectors.py on
    the stored is_test row)."""
    headers = re.findall(r"(?mi)^Stop\s+\d+:\s*(.+)$", text)
    delivered = _tc.count_delivered_stops(text)
    m = re.search(r"That['\u2019]s\s+(\d+)\s+stops?", text)
    stated = m.group(1) if m else "?"
    runon = bool(re.search(r"(?mi)^Stop\s+\d+:.*\b(?:Address|Coordinates|"
                           r"Orientation|Directions):", text))
    # D636 callbacks still present after stitch (should be <= budget)
    try:
        from cross_stop_reference_guard import (
            _PREV_STOP_RECAP_RE, _THEMATIC_BRIDGE_RE, callback_budget)
        cb = len(_PREV_STOP_RECAP_RE.findall(text)) + len(_THEMATIC_BRIDGE_RE.findall(text))
        budget = callback_budget(delivered)
    except Exception:
        cb, budget = -1, -1
    return {"headers": [h.strip()[:70] for h in headers],
            "delivered": delivered, "stated": stated,
            "runon_header": runon, "callbacks_in_text": cb, "callback_budget": budget}


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-649 {location.split(',')[0][:40]} {slug} {int(time.time())}"
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
                 f"LOCAL-649 live A/B ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


def _run_one(location, stops, tour_type, slug, parallel_on):
    spend = _spend_so_far()
    print(f"\n[reserve-gate] spend_so_far=${spend if spend is not None else '?'} "
          f"+ reserve ${RESERVE_USD} vs cap ${HARD_CAP_USD}", flush=True)
    if spend is not None and (spend + RESERVE_USD) > HARD_CAP_USD:
        print(f"[reserve-gate] SKIP {slug}: would exceed cap "
              f"(${spend:.4f}+${RESERVE_USD} > ${HARD_CAP_USD})", flush=True)
        return (slug, None, 'SKIPPED_CAP', None)

    # Set the flag for THIS tour only.
    if parallel_on:
        os.environ['PARALLEL_STOPS'] = '1'
    else:
        os.environ.pop('PARALLEL_STOPS', None)
    assert _ps.is_enabled() is bool(parallel_on), "flag not set as intended"

    print(f"=== generating: {location} ({stops} stops, {tour_type}) "
          f"PARALLEL_STOPS={'1' if parallel_on else 'OFF'} [{slug}] ===", flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            location, tour_type, f"/app/tours/LOCAL649_{slug}.txt", stops,
            user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {slug}: {e}", flush=True)
        return (slug, None, f'ERROR:{e}', None)
    finally:
        os.environ.pop('PARALLEL_STOPS', None)
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME {slug}: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        return (slug, None, 'NO_TEXT', None)

    d = _detectors(text)
    print(f"OUTCOME {slug}: DELIVERED {len(text)} chars, {d['delivered']} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    for h in d['headers']:
        print(f"  STOP TITLE: {h}", flush=True)
    print(f"  [detectors] delivered={d['delivered']} stated='{d['stated']}' "
          f"runon_header={d['runon_header']} callbacks_in_text={d['callbacks_in_text']} "
          f"(budget={d['callback_budget']})", flush=True)
    tour_cost = None
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        tour_cost = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
        print(f"  [cost] tour_total=${tour_cost:.4f}", flush=True)
    except Exception:
        pass
    nid = _store(location, text, d['delivered'], slug)
    if nid:
        print(f"  STORED audio_tours id = {nid}  (is_test=true)", flush=True)
        print(f"  LOCAL649_TOUR_ID_{slug}={nid}", flush=True)
    return (slug, nid, 'DELIVERED', {"wall_s": round(elapsed, 1),
                                     "tour_cost": tour_cost, **d})


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}",
      flush=True)

results = []
for _loc, _stops, _ttype, _slug, _par in TOURS:
    results.append(_run_one(_loc, _stops, _ttype, _slug, _par))

print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}",
      flush=True)
print("=== LOCAL-649 run complete ===", flush=True)
for _slug, _id, _outcome, _m in results:
    _extra = ""
    if _m:
        _extra = (f" wall={_m['wall_s']}s cost=${_m['tour_cost']} "
                  f"stops={_m['delivered']} callbacks={_m['callbacks_in_text']}/"
                  f"{_m['callback_budget']}")
    print(f"RESULT {_slug}: id={_id if _id else ''} outcome={_outcome}{_extra}",
          flush=True)
