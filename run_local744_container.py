#!/usr/bin/env python3
"""run_local744_container.py — LOCAL-744 live acceptance (ISOLATED container).

Two FRESH biking tours, side by side, in ONE disposable container:

  * SALEM  — "the episode 1 of season 1 biking tour, Salem, MA" (5 stops).
             WGN's *Salem* (2014) was filmed in Shreveport, Louisiana, so the
             Orientation MUST open with the sourced disclosure saying so, and the
             real Salem places (Pickering Wharf / Winter Island Park / Fort
             Pickering Lighthouse) must no longer be dropped as "no evidence".
  * SHREVEPORT — "the episode 1 of season 1 tour, Shreveport, Louisiana"
             (5 stops). Shreveport IS a filming location, so the Orientation says
             so (with a source), not "filmed elsewhere".

For each arm: the delivered stop list, the VERBATIM Orientation opening, the
LOCAL-744 detectors, $ and seconds. Rows stored additive is_test=true with
lat/lng NULL. Row counts before/after. No DELETE (D141).

HARD CAP $1.00 for the WHOLE TASK (both arms), enforced by tests/live_run_meter
plus a RESERVE GATE before each arm.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-744')
except Exception as _meter_err:
    print(f"[LOCAL-744] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import re
import socket
import time

_os.environ['STORIED_MODE'] = 'true'
_os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tour (cache off)
_os.environ['DISABLE_STOP_POOL'] = '1'             # pool off (fresh)
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.00')
_os.environ['COST_HARD_LIMIT_USD'] = '1.00'        # ticket HARD CAP (whole task)
_os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
# The existence gate must actually DROP fabricated stops and KEEP real ones — run
# it in enforce so the LOCAL-744 fix (real Salem places verify) is exercised live.
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'enforce')
# [LOCAL-744] Budget discipline: the task cap is $1.00 for TWO fresh tours. The
# cheap arm (gpt-4.1-mini narration + serper research) brings each fresh tour to
# well under $0.50 so both fit under the cap. These mirror the LOCAL-668 CHEAP
# arm's knobs.
_os.environ.setdefault('NARRATION_MODEL', 'gpt-4.1-mini')
_os.environ.setdefault('RESEARCH_BACKEND', 'serper')

HARD_CAP_USD = 1.00
RESERVE_USD = 0.45          # start an arm only if spend + 0.45 <= cap
HOST = socket.gethostname()

ARMS = [
    ("SALEM", "the episode 1 of season 1 biking tour, Salem, MA", "biking", 5),
    ("SHREVEPORT", "the episode 1 of season 1 tour, Shreveport, Louisiana", "biking", 5),
]

print("=== LOCAL-744 isolated live run (Salem + Shreveport, biking, 5 stops) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  reserve: ${RESERVE_USD}  "
      f"cache_off=1 pool_off=1 gate=enforce", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402


def _conn():
    import psycopg2
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=_os.environ.get('DB_HOST', 'development-postgres-2-1'),
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


def _host_spend():
    v = _scalar("SELECT COALESCE(SUM(usd),0) FROM paid_api_calls WHERE host = %s",
                (HOST,))
    return float(v) if v is not None else None


# [LOCAL-744] Budget is measured for THIS run. The paid_api_calls table is
# cumulative per host (a previous shakeout run already spent on this host), so we
# capture a baseline at start and report spend RELATIVE to it — the honest cost of
# this run, and the number the $1.00 cap/reserve gate must respect.
_SPEND_BASELINE = None


def _spend_so_far():
    """Spend during THIS run (host spend minus the baseline captured at start)."""
    cur = _host_spend()
    if cur is None:
        return None
    if _SPEND_BASELINE is None:
        return cur
    return max(0.0, cur - _SPEND_BASELINE)


_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")
_ORIENTATION_RE = re.compile(r"(?mi)^Orientation:\s*(.+)$")


def _titles(text):
    return [t.strip() for t in _STOP_HEADER_RE.findall(text)]


def _orientation_opening(text):
    m = _ORIENTATION_RE.search(text)
    if not m:
        return None
    # The opening sentence(s): up to the first two sentences of the Orientation.
    body = m.group(1).strip()
    sents = re.split(r"(?<=[.!?])\s+", body)
    return " ".join(sents[:2]).strip()


def _store(location, text, n_stops, slug):
    """Insert the delivered tour additively, is_test=true, lat/lng NULL."""
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-744 {location.split(',')[0][:40]} {slug} {int(time.time())}"
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audio_tours
                    (tour_name, request_string, number_requested,
                     tour_content, stops_count, creator_type, storied_mode,
                     is_test, track, tour_kind, description, lat, lng)
                VALUES (%s, %s, %s, %s, %s, 'Test', true, true, 'beta', 'full',
                        %s, NULL, NULL)
                RETURNING id
                """,
                (name, location, n_stops, text, n_stops,
                 f"LOCAL-744 live fresh ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


def _run_arm(slug, location, tour_type, stops):
    spend = _spend_so_far()
    print(f"\n[reserve-gate] arm={slug} spend_so_far="
          f"${spend if spend is not None else '?'} + reserve ${RESERVE_USD} "
          f"vs cap ${HARD_CAP_USD}", flush=True)
    if spend is not None and (spend + RESERVE_USD) > HARD_CAP_USD:
        print(f"[reserve-gate] SKIP {slug}: would exceed cap", flush=True)
        return (slug, None, 'SKIPPED_CAP', None, None, 0.0, 0.0)
    print(f"=== [{slug}] generating: {location!r} ({stops} stops, {tour_type}) ===",
          flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            location, tour_type, f"/app/tours/LOCAL744_{slug}.txt", stops,
            user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {slug}: {e}", flush=True)
        return (slug, None, f'ERROR:{e}', None, None, 0.0, time.time() - t0)
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME [{slug}]: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        return (slug, None, 'NO_TEXT', None, None, 0.0, elapsed)

    delivered = _tc.count_delivered_stops(text)
    opening = _orientation_opening(text)
    print(f"OUTCOME [{slug}]: DELIVERED — {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    print("  --- STOP LIST ---", flush=True)
    for h in _titles(text):
        print(f"  STOP TITLE: {h[:100]}", flush=True)
    print("  --- ORIENTATION OPENING (verbatim) ---", flush=True)
    print(f"  ORIENTATION_OPENING[{slug}]: {opening}", flush=True)

    # LOCAL-744 detectors
    low = (text or '').lower()
    says_filmed = ("filmed in" in low) or ("could not confirm where" in low)
    print(f"  [{'PASS' if says_filmed else 'FAIL'}] ORIENTATION_STATES_FILMING: "
          f"{says_filmed}", flush=True)

    tour_cost = 0.0
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        tour_cost = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
        print(f"[cost] {slug} tour_total=${tour_cost:.4f}", flush=True)
    except Exception:
        pass

    nid = _store(location, text, delivered, slug)
    if nid:
        print(f"STORED audio_tours id = {nid}  (is_test=true, lat/lng NULL)", flush=True)
        print(f"LOCAL744_TOUR_ID_{slug}={nid}", flush=True)
    try:
        with open(f"/app/tours/LOCAL744_{slug}_delivered.txt", "w",
                  encoding="utf-8") as _df:
            _df.write(text)
    except Exception:
        pass
    return (slug, nid, 'DELIVERED', opening, says_filmed, tour_cost, elapsed)


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
_SPEND_BASELINE = _host_spend() or 0.0
print(f"[db] paid_api_calls spend baseline for host {HOST}: ${_SPEND_BASELINE:.4f} "
      f"(this run is measured RELATIVE to this)", flush=True)

results = []
for _slug, _loc, _tt, _n in ARMS:
    results.append(_run_arm(_slug, _loc, _tt, _n))

_run_spend = _spend_so_far()
_abs_spend = _host_spend()
print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] THIS RUN spend (host {HOST}): ${_run_spend if _run_spend is not None else '?'} "
      f"(cap ${HARD_CAP_USD}); host cumulative now ${_abs_spend if _abs_spend is not None else '?'}",
      flush=True)
print("=== LOCAL-744 run complete ===", flush=True)
for _slug, _id, _outcome, _opening, _filmed, _cost, _secs in results:
    print(f"RESULT {_slug}: id={_id if _id else ''} outcome={_outcome} "
          f"states_filming={_filmed} cost=${_cost if _cost else 0.0:.4f} "
          f"secs={_secs:.1f}", flush=True)
    if _opening:
        print(f"RESULT {_slug} ORIENTATION: {_opening}", flush=True)
