#!/usr/bin/env python3
"""run_local667_container.py — LOCAL-667 live acceptance (ISOLATED container).

The ticket: "Ho Chi Minh City Museum of Fine Arts, Vietnam", 5 stops, museum.
Baseline (tour 662) delivered 1 of 5: the one SPARQL work "North Central South
Spring Garden" was atomised into North / Central / South / Spring Garden / Garden,
D1v2 verified only one fragment, R4's real Vietnamese works all failed the thin
canonical match, and the LOCAL-16 gate stripped the unverified fills → "1 stop
rather than the 5 you asked for".

This harness proves the fix end-to-end on ONE FRESH PAID museum tour through the
real generation path (NORMAL arm — no NARRATION_MODEL / RESEARCH_BACKEND
override). It reports the delivered stops, each stop's verification method /
source (from the generator's evidence log echoed to the log), the tier, and the
three LOCAL-667 detectors:
  * no split-title fragment survives as its own stop (North/Central/South/Garden);
  * the one real work "North Central South Spring Garden" survives whole;
  * stop count improved over the 1-of-5 baseline.

ONE paid tour only. HARD CAP $0.80 for the WHOLE task, enforced by
tests/live_run_meter.py plus a RESERVE GATE before the tour. The delivered SPOKEN
text is stored as ONE additive is_test row. is_test rows are the ONLY rows
written. No DELETE.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-667')
except Exception as _meter_err:
    print(f"[LOCAL-667] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import re
import socket
import time

# NORMAL ARM: no NARRATION_MODEL, no RESEARCH_BACKEND override.
_os.environ['STORIED_MODE'] = 'true'
_os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tour (cache off)
_os.environ['DISABLE_STOP_POOL'] = '1'             # pool off (fresh)
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '0.80')
_os.environ['COST_HARD_LIMIT_USD'] = '0.80'        # ticket HARD CAP (whole task)
_os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

HARD_CAP_USD = 0.80
RESERVE_USD = 0.55          # start the tour only if spend + 0.55 <= cap
HOST = socket.gethostname()

TOURS = [
    ('Ho Chi Minh City Museum of Fine Arts, Vietnam', 5, 'museum', 'HCMC'),
]

print("=== LOCAL-667 isolated live run (HCMC museum 5, ONE paid tour) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"NORMAL ARM  HARD CAP(task): ${HARD_CAP_USD}  reserve: ${RESERVE_USD}  "
      f"cache_off=1 pool_off=1", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402


def _conn():
    import psycopg2
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=_os.environ.get('DB_HOST', 'postgres-2'),
        port=_os.environ.get('DB_PORT', '5432'),
        dbname=_os.environ.get('DB_NAME', 'audiotours'),
        user=_os.environ.get('DB_USER', 'admin'),
        password=_os.environ.get('DB_PASSWORD', 'password123'))


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


# ───────────────────────── LOCAL-667 detectors ──────────────────────────────

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")
_SOURCES_RE = re.compile(r"(?mi)^Sources?:\s*(.+)$")

# The split-title fragments that must NEVER ship as their own stop.
_FRAGMENTS = {"north", "central", "south", "garden"}
_WHOLE_WORK = "north central south spring garden"


def _titles(text):
    return [t.strip() for t in _STOP_HEADER_RE.findall(text)]


def detect_no_bare_fragment_stop(text):
    """No stop title is a bare split-title fragment (North / Central / South /
    Garden) — the atomised pieces must not survive as separate stops."""
    bad = []
    for t in _titles(text):
        base = re.sub(r"\s+(collection|gallery)$", "", t.strip().lower())
        if base in _FRAGMENTS:
            bad.append(t)
    return (not bad), f"bare_fragment_stops={bad}"


def detect_whole_work_present(text):
    """The one real work survives whole somewhere in the tour (title or body)."""
    present = _WHOLE_WORK in re.sub(r"[^\w\s]", " ", text.lower())
    return present, f"whole_work_present={present}"


def detect_improved_count(text):
    """More than the 1-of-5 baseline (any improvement over 1 stop is the win;
    5 is the goal)."""
    delivered = _tc.count_delivered_stops(text)
    return (delivered > 1), f"delivered_stops={delivered} (baseline was 1)"


def _report(text):
    titles = _titles(text)
    print("  --- STOP LIST ---", flush=True)
    for h in titles:
        print(f"  STOP TITLE: {h[:100]}", flush=True)
    print("  --- SOURCES LINES ---", flush=True)
    for s in _SOURCES_RE.findall(text):
        print(f"  SOURCES: {s.strip()[:200]}", flush=True)
    print("  --- LOCAL-667 DETECTORS ---", flush=True)
    results = {}
    for name, fn in (("NO_BARE_FRAGMENT_STOP", detect_no_bare_fragment_stop),
                     ("WHOLE_WORK_PRESENT", detect_whole_work_present),
                     ("IMPROVED_STOP_COUNT", detect_improved_count)):
        try:
            ok, detail = fn(text)
        except Exception as e:
            ok, detail = False, f"detector error: {e}"
        results[name] = ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
    print(f"  [LOCAL-667] ALL DETECTORS PASS = {all(results.values())}", flush=True)
    return results


def _store(location, text, n_stops, slug, kind_desc):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-667 {location.split(',')[0][:40]} {int(time.time())}"
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
                (name, location, n_stops, text, n_stops, kind_desc))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


def _run_one(location, stops, tour_type, slug):
    spend = _spend_so_far()
    print(f"\n[reserve-gate] spend_so_far=${spend if spend is not None else '?'} "
          f"+ reserve ${RESERVE_USD} vs cap ${HARD_CAP_USD}", flush=True)
    if spend is not None and (spend + RESERVE_USD) > HARD_CAP_USD:
        print(f"[reserve-gate] SKIP {slug}: would exceed cap", flush=True)
        return None, 'SKIPPED_CAP', None
    print(f"=== generating: {location} ({stops} stops, {tour_type}) ===",
          flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            location, tour_type, f"/app/tours/LOCAL667_{slug}.txt", stops,
            user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {location}: {e}", flush=True)
        return None, f'ERROR:{e}', None
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        return None, 'NO_TEXT', None
    delivered = _tc.count_delivered_stops(text)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    results = _report(text)
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        _tot = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
        print(f"[cost] tour_total=${_tot:.4f}", flush=True)
    except Exception:
        pass
    nid = _store(location, text, delivered, slug,
                 f"LOCAL-667 live fresh ({slug}, {tour_type})")
    if nid:
        print(f"STORED audio_tours id = {nid}  (is_test=true)", flush=True)
        print(f"LOCAL667_TOUR_ID_{slug}={nid}", flush=True)
    try:
        with open(f"/app/tours/LOCAL667_{slug}_delivered.txt", "w",
                  encoding="utf-8") as _df:
            _df.write(text)
    except Exception:
        pass
    return nid, 'DELIVERED', results


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}",
      flush=True)

results = []
for _loc, _stops, _ttype, _slug in TOURS:
    _id, _outcome, _det = _run_one(_loc, _stops, _ttype, _slug)
    results.append((_slug, _id, _outcome, _det))

print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}",
      flush=True)
print("=== LOCAL-667 run complete ===", flush=True)
for _slug, _id, _outcome, _det in results:
    print(f"RESULT {_slug}: id={_id if _id else ''} outcome={_outcome} "
          f"detectors={_det}", flush=True)
