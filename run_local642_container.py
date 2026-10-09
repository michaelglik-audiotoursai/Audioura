#!/usr/bin/env python3
"""run_local642_container.py — LOCAL-642 live acceptance (ISOLATED container).

Generates ONE fresh museum tour through the REAL generation path with the
LOCAL-642 branch code in the image, cache + pool OFF:

  The National Gallery, London, United Kingdom — 3 stops. This is the venue whose
  stop "The Toilet of Venus ('The Rokeby Venus')" — a title with PARENTHESES and
  QUOTES — shipped FLATTENED (header+Address+Coordinates+Orientation on one line)
  and DUPLICATED under a "Continue to …" transition (Bench R9, R12, tour 495).

Acceptance (binding):
  * Every "Stop N:" header line carries ONLY the title — the ``run_on`` detector
    (^Stop N: … Address|Coordinates|Orientation|Directions:) is CLEAR.
  * No "Continue to <title> <field block>" duplicate line survives.
  * venue_as_stop detector PASSES (the venue is never itself a stop).
  * 3 narrated stop bodies == 3 "Stop N:" headers == stops_count == "That's 3
    stops".

HARD CAP $0.90 (ticket), enforced by tests/live_run_meter.py across ALL providers,
plus a RESERVE GATE before the tour. The delivered SPOKEN text is stored as ONE
additive is_test row for critique.sh / detectors.py. is_test rows are the ONLY
rows written. No DELETE. At most ONE tour is started.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-642')
except Exception as _meter_err:
    print(f"[LOCAL-642] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import socket
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tour (cache off)
os.environ['DISABLE_STOP_POOL'] = '1'             # pool off (ticket requirement)
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '0.90')
os.environ['COST_HARD_LIMIT_USD'] = '0.90'        # ticket HARD CAP
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
os.environ.setdefault('STOP_EDITOR_ENABLED', '1')

HARD_CAP_USD = 0.90
RESERVE_USD = 0.55          # start the tour only if spend + 0.55 <= cap
HOST = socket.gethostname()

VENUES = [
    ('National Gallery, London, United Kingdom', 3, 'NATGAL'),
]

print("=== LOCAL-642 isolated live run (National Gallery, 3 stops, ONE tour) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   HARD CAP: ${HARD_CAP_USD}  "
      f"reserve: ${RESERVE_USD}  cache_off=1 pool_off=1", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402


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


def _row_count():
    try:
        conn = _conn(); conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM audio_tours")
            n = cur.fetchone()[0]
        conn.close(); return n
    except Exception as e:
        print(f"  [db] row count failed: {e}", flush=True); return None


def _test_row_count():
    try:
        conn = _conn(); conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM audio_tours WHERE is_test = true")
            n = cur.fetchone()[0]
        conn.close(); return n
    except Exception as e:
        print(f"  [db] test row count failed: {e}", flush=True); return None


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


def _report(text):
    # Header integrity: narrated stop bodies vs headers vs the stated count.
    headers = re.findall(r"(?mi)^Stop\s+\d+:\s*(.+)$", text)
    for h in headers:
        print(f"  STOP TITLE: {h.strip()[:90]}", flush=True)
    m = re.search(r"That['\u2019]s\s+(\d+)\s+stops?", text)
    stated = m.group(1) if m else "?"
    print(f"  HEADER COUNT: {len(headers)}   "
          f"count_delivered_stops: {_tc.count_delivered_stops(text)}   "
          f"stated 'That's N stops': {stated}", flush=True)
    # [LOCAL-642] Flattened-header / duplicated-transition artifacts must be absent.
    glued_label = re.search(r"(?mi)^(?:Address|Directions|Coordinates|Orientation):\S*Stop\s+\d+:", text)
    run_on = re.search(r"(?mi)^Stop\s+\d+:.*\b(?:Address|Coordinates|Orientation|Directions):", text)
    # A transition line that carries a glued field block ("Continue to X Address: …").
    dup_block = re.search(
        r"(?im)^(?:Directions:\s*)?(?:Continue to|Continue through|Proceed to|Next:|"
        r"Head towards|Your final stop(?:\s+in\s+[^:]+)?:).*[ \t](?:Address|Coordinates|Orientation|Directions):",
        text)
    print(f"  [LOCAL-642] flatten/dup artifacts: label-glued={bool(glued_label)} "
          f"run-on={bool(run_on)} dup-transition-block={bool(dup_block)}", flush=True)
    # Any flattened header line (header carrying a field label) — must be [].
    flat = [h.strip()[:70] for h in headers
            if re.search(r"\b(?:Address|Coordinates|Orientation|Directions):", h)]
    print(f"  [LOCAL-642] flattened header lines: {flat}", flush=True)


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-642 {location.split(',')[0]} {int(time.time())}"
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
                 f"LOCAL-642 live fresh ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


def _run_one(location, stops, slug):
    spend = _spend_so_far()
    print(f"\n[reserve-gate] spend_so_far=${spend if spend is not None else '?'} "
          f"+ reserve ${RESERVE_USD} vs cap ${HARD_CAP_USD}", flush=True)
    if spend is not None and (spend + RESERVE_USD) > HARD_CAP_USD:
        print(f"[reserve-gate] SKIP {slug}: would exceed cap "
              f"(${spend:.4f}+${RESERVE_USD} > ${HARD_CAP_USD})", flush=True)
        return None, 'SKIPPED_CAP'
    print(f"=== generating: {location} ({stops} stops) ===", flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            location, 'museum', f"/app/tours/LOCAL642_{slug}.txt", stops, user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {location}: {e}", flush=True)
        return None, f'ERROR:{e}'
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME: NO TOUR TEXT (refused/empty) after {elapsed:.1f}s",
              flush=True)
        return None, 'NO_TEXT'
    delivered = _tc.count_delivered_stops(text)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    _report(text)
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        _tot = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
        print(f"[cost] tour_total=${_tot:.4f}", flush=True)
    except Exception:
        pass
    nid = _store(location, text, delivered, slug)
    if nid:
        print(f"STORED audio_tours id = {nid}  (is_test=true)", flush=True)
        print(f"LOCAL642_TOUR_ID_{slug}={nid}", flush=True)
    return nid, 'DELIVERED'


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}",
      flush=True)

results = []
for _loc, _stops, _slug in VENUES:
    _id, _outcome = _run_one(_loc, _stops, _slug)
    results.append((_slug, _id, _outcome))

print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}",
      flush=True)
print("=== LOCAL-642 run complete ===", flush=True)
for _slug, _id, _outcome in results:
    print(f"RESULT {_slug}: id={_id if _id else ''} outcome={_outcome}", flush=True)
