#!/usr/bin/env python3
"""run_local651_ab_container.py — LOCAL-651 live A/B (ISOLATED container).

FOUR fresh tours through the REAL generation path, cache + pool OFF:

  1. Courtauld, 3 stops, FAST_PIPELINE OFF   (baseline)
  2. Courtauld, 3 stops, FAST_PIPELINE ON    (independent waits overlapped)
  3. Walters,   3 stops, FAST_PIPELINE OFF
  4. Walters,   3 stops, FAST_PIPELINE ON

Per tour we report: delivered stop count + titles, wall time, the pipeline's own
[TIMING] phase line, the per-tour [TIMING-SUB] aggregate (sub-timer reset before
each tour), the tour's own $ from _LAST_GENERATION_COST, and BOTH the $ and the
CALL COUNT recorded in paid_api_calls for this host during the tour (so the ±10%
call-count parity in the ticket can be checked ON vs OFF). Each delivered SPOKEN
text is stored as ONE additive is_test row for critique.sh / detectors.py. is_test
rows are the ONLY rows written. No DELETE.

HARD CAP $3.00 COMBINED (ticket), enforced by tests/live_run_meter.py across ALL
providers, plus a RESERVE GATE before each tour. Row counts printed before/after.
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

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['DISABLE_STOP_POOL'] = '1'
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '3.00')
os.environ['COST_HARD_LIMIT_USD'] = '3.00'
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
os.environ.setdefault('STOP_EDITOR', '1')
os.environ.setdefault('STOP_EDITOR_ENABLED', '1')

HARD_CAP_USD = 3.00
RESERVE_USD = 0.60        # start a tour only if spend + 0.60 <= cap
HOST = socket.gethostname()

TOURS = [
    ('The Courtauld Gallery, London, United Kingdom', 3, 'museum', 'COURTAULD_OFF', False),
    ('The Courtauld Gallery, London, United Kingdom', 3, 'museum', 'COURTAULD_ON',  True),
    ('The Walters Art Museum, Baltimore, Maryland',   3, 'museum', 'WALTERS_OFF',   False),
    ('The Walters Art Museum, Baltimore, Maryland',   3, 'museum', 'WALTERS_ON',    True),
]

print("=== LOCAL-651 isolated live A/B (Courtauld 3 + Walters 3, OFF vs ON) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}  HARD CAP(combined): "
      f"${HARD_CAP_USD}  reserve: ${RESERVE_USD}  cache_off=1 pool_off=1", flush=True)

import phase_timer as _pt
from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402
import fast_pipeline as _fp  # noqa: E402


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


def _calls_so_far():
    v = _scalar("SELECT count(*) FROM paid_api_calls WHERE host = %s", (HOST,))
    return int(v) if v is not None else None


def _calls_by_kind(since_calls_marker_ts):
    """Return {kind: count} for paid_api_calls on this host since a timestamp."""
    out = {}
    try:
        conn = _conn(); conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT kind, count(*) FROM paid_api_calls "
                "WHERE host = %s AND ts >= %s GROUP BY kind",
                (HOST, since_calls_marker_ts))
            for k, c in cur.fetchall():
                out[k] = int(c)
        conn.close()
    except Exception as e:
        print(f"  [db] by-kind query failed: {e}", flush=True)
    return out


def _detectors(text):
    headers = re.findall(r"(?mi)^Stop\s+\d+:\s*(.+)$", text)
    delivered = _tc.count_delivered_stops(text)
    m = re.search(r"That['\u2019]s\s+(\d+)\s+stops?", text)
    stated = m.group(1) if m else "?"
    runon = bool(re.search(r"(?mi)^Stop\s+\d+:.*\b(?:Address|Coordinates|"
                           r"Orientation|Directions):", text))
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
                 f"LOCAL-651 live A/B ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


def _now_ts():
    return _scalar("SELECT now()")


def _run_one(location, stops, tour_type, slug, fast_on):
    spend = _spend_so_far()
    print(f"\n[reserve-gate] spend_so_far=${spend if spend is not None else '?'} "
          f"+ reserve ${RESERVE_USD} vs cap ${HARD_CAP_USD}", flush=True)
    if spend is not None and (spend + RESERVE_USD) > HARD_CAP_USD:
        print(f"[reserve-gate] SKIP {slug}: would exceed cap", flush=True)
        return (slug, None, 'SKIPPED_CAP', None)

    if fast_on:
        os.environ['FAST_PIPELINE'] = '1'
    else:
        os.environ.pop('FAST_PIPELINE', None)
    assert _fp.is_enabled() is bool(fast_on), "flag not set as intended"

    # Reset the per-tour sub-timer so each tour's [TIMING-SUB] table is clean.
    _pt.reset_sub_timer()

    calls_before = _calls_so_far()
    spend_before = _spend_so_far()
    ts_before = _now_ts()

    print(f"=== generating: {location} ({stops} stops) "
          f"FAST_PIPELINE={'1' if fast_on else 'OFF'} [{slug}] ===", flush=True)
    t0 = time.time()
    text = None
    try:
        text, _p, _c = generate_tour_text(
            location, tour_type, f"/app/tours/LOCAL651_{slug}.txt", stops,
            user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {slug}: {e}", flush=True)
        os.environ.pop('FAST_PIPELINE', None)
        return (slug, None, f'ERROR:{e}', None)
    finally:
        os.environ.pop('FAST_PIPELINE', None)
    elapsed = time.time() - t0

    print(f"\n----- [TIMING-SUB] aggregate for {slug} -----", flush=True)
    try:
        _pt.get_sub_timer().summary()
    except Exception as _e:
        print(f"[TIMING-SUB] summary unavailable: {_e}", flush=True)

    if not text:
        print(f"OUTCOME {slug}: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        return (slug, None, 'NO_TEXT', None)

    d = _detectors(text)
    calls_after = _calls_so_far()
    spend_after = _spend_so_far()
    tour_calls = (calls_after - calls_before) if (calls_after is not None
                                                  and calls_before is not None) else None
    tour_spend = (spend_after - spend_before) if (spend_after is not None
                                                  and spend_before is not None) else None
    by_kind = _calls_by_kind(ts_before) if ts_before is not None else {}

    print(f"OUTCOME {slug}: DELIVERED {len(text)} chars, {d['delivered']} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    for h in d['headers']:
        print(f"  STOP TITLE: {h}", flush=True)
    print(f"  [detectors] delivered={d['delivered']} stated='{d['stated']}' "
          f"runon_header={d['runon_header']} callbacks_in_text={d['callbacks_in_text']} "
          f"(budget={d['callback_budget']})", flush=True)
    print(f"  [paid_api_calls] tour_calls={tour_calls} tour_spend=$"
          f"{tour_spend if tour_spend is None else round(tour_spend,4)} by_kind={by_kind}",
          flush=True)
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
        print(f"  STORED audio_tours id = {nid} (is_test=true)", flush=True)
        print(f"  LOCAL651_TOUR_ID_{slug}={nid}", flush=True)
    return (slug, nid, 'DELIVERED', {"wall_s": round(elapsed, 1),
                                     "tour_cost": tour_cost,
                                     "tour_calls": tour_calls,
                                     "by_kind": by_kind, **d})


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()} "
      f"(calls: {_calls_so_far()})", flush=True)

results = []
for _loc, _stops, _ttype, _slug, _fast in TOURS:
    results.append(_run_one(_loc, _stops, _ttype, _slug, _fast))

print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()} "
      f"(calls: {_calls_so_far()})", flush=True)
print("=== LOCAL-651 run complete ===", flush=True)
for _slug, _id, _outcome, _m in results:
    _extra = ""
    if _m:
        _extra = (f" wall={_m['wall_s']}s cost=${_m['tour_cost']} "
                  f"calls={_m['tour_calls']} stops={_m['delivered']} "
                  f"callbacks={_m['callbacks_in_text']}/{_m['callback_budget']}")
    print(f"RESULT {_slug}: id={_id if _id else ''} outcome={_outcome}{_extra}",
          flush=True)
