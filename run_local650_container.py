#!/usr/bin/env python3
"""run_local650_container.py — LOCAL-650 live acceptance (ISOLATED container).

Generates TWO fresh tours through the REAL generation path with the LOCAL-650
branch code in the image (theme_stop_guard, walking_directions_guard,
current_affairs_coverage + the directions_generator target guard + the PHASE 3A
theme constraint), cache + pool OFF:

  1. WALKING: "Walking tour in Boston dedicated to Massachusetts politics and
     current affairs, Boston, MA" — 5 stops. The evidence tour (557). Must show:
       • NO stop whose name is the request theme phrase / a topic
         (theme_stop_guard.find_theme_phrase_stops == []);
       • EVERY non-last stop's Directions names the NEXT stop with a distance
         (walking_directions_guard.count_wrong_target_directions == 0, and no
         stop missing a hand-off);
       • current-affairs honesty: a recent (<=5y) item OR the honest note.
  2. MUSEUM CANARY: "The Courtauld Gallery, London, United Kingdom" — 3 stops.
     The museum path MUST NOT change: 0 directions missing, no run-on header,
     and every LOCAL-650 guard is a no-op (museum headers are works).

HARD CAP $1.20 COMBINED (ticket), enforced by tests/live_run_meter.py across ALL
providers, plus a RESERVE GATE before each tour. The delivered SPOKEN text of
each tour is stored as ONE additive is_test row for critique.sh / detectors.py.
is_test rows are the ONLY rows written. No DELETE. At most TWO tours are started.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-650')
except Exception as _meter_err:
    print(f"[LOCAL-650] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import socket
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tour (cache off)
os.environ['DISABLE_STOP_POOL'] = '1'             # pool off (ticket requirement)
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.20')
os.environ['COST_HARD_LIMIT_USD'] = '1.20'        # ticket HARD CAP (combined)
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
os.environ.setdefault('STOP_EDITOR', '1')
os.environ.setdefault('STOP_EDITOR_ENABLED', '1')

HARD_CAP_USD = 1.20
RESERVE_USD = 0.55          # start a tour only if spend + 0.55 <= cap
HOST = socket.gethostname()

# (location, stops, tour_type, slug)
TOURS = [
    ('Walking tour in Boston dedicated to Massachusetts politics and current '
     'affairs, Boston, MA', 5, 'walking', 'BOSTONWALK'),
    ('The Courtauld Gallery, London, United Kingdom', 3, 'museum', 'COURTAULD'),
]

print("=== LOCAL-650 isolated live run (Boston walking 5 + Courtauld 3) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   HARD CAP(combined): "
      f"${HARD_CAP_USD}  reserve: ${RESERVE_USD}  cache_off=1 pool_off=1",
      flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402
import directions_guarantee as _dg  # noqa: E402
import theme_stop_guard as _tsg  # noqa: E402
import walking_directions_guard as _wdg  # noqa: E402
import current_affairs_coverage as _cac  # noqa: E402


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


def _report_walking(text):
    """Assert the three LOCAL-650 fixes hold on a WALKING tour."""
    headers = re.findall(r"(?mi)^Stop\s+\d+:\s*(.+)$", text)
    for h in headers:
        print(f"  STOP TITLE: {h.strip()[:90]}", flush=True)
    m = re.search(r"That['\u2019]s\s+(\d+)\s+stops?", text)
    stated = m.group(1) if m else "?"
    print(f"  HEADER COUNT: {len(headers)}   "
          f"count_delivered_stops: {_tc.count_delivered_stops(text)}   "
          f"stated 'That's N stops': {stated}", flush=True)

    # FIX 1 — no stop is the request theme phrase / a topic.
    theme = _tsg.extract_request_theme(text)
    theme_stops = _tsg.find_theme_phrase_stops(text)
    fix1_ok = (len(theme_stops) == 0)
    print(f"  [FIX1] request theme: {theme!r}  theme/topic stops: {theme_stops} "
          f"-> ok={fix1_ok}", flush=True)

    # FIX 2 — each non-last stop's Directions leads to the next stop + distance.
    wrong = _wdg.count_wrong_target_directions(text)
    missing = _dg.count_stops_missing_directions(text)
    analysis = _wdg.analyze(text)
    dist_present = sum(1 for r in analysis if r['has_distance'])
    fix2_ok = (wrong == 0 and missing == 0)
    print(f"  [FIX2] wrong_target={wrong}  missing_directions={missing}  "
          f"legs_with_distance={dist_present}/{max(len(analysis),0)} "
          f"-> ok={fix2_ok}", flush=True)
    for r in analysis:
        print(f"         stop {r['num']} -> {r['next'][:40]!r}: "
              f"has_dir={r['has_directions']} wrong={r['wrong_target']} "
              f"dist={r['has_distance']}", flush=True)

    # FIX 3 — current-affairs honesty: a recent item OR the honest note.
    wants = _cac.request_wants_current_affairs(text)
    recent = _cac.has_recent_item(text)
    note = _cac._HONEST_NOTE_MARK in text
    fix3_ok = (not wants) or recent or note
    print(f"  [FIX3] wants_current_affairs={wants}  has_recent_<=5y={recent}  "
          f"honest_note={note}  most_recent_year={_cac.most_recent_year(text)} "
          f"-> ok={fix3_ok}", flush=True)

    print(f"  [LOCAL-650] WALKING RESULT: fix1={fix1_ok} fix2={fix2_ok} "
          f"fix3={fix3_ok}  (all must be True)", flush=True)


def _report_museum(text):
    """Museum canary — the museum path must not change."""
    headers = re.findall(r"(?mi)^Stop\s+\d+:\s*(.+)$", text)
    for h in headers:
        print(f"  STOP TITLE: {h.strip()[:90]}", flush=True)
    m = re.search(r"That['\u2019]s\s+(\d+)\s+stops?", text)
    stated = m.group(1) if m else "?"
    print(f"  HEADER COUNT: {len(headers)}   "
          f"count_delivered_stops: {_tc.count_delivered_stops(text)}   "
          f"stated 'That's N stops': {stated}", flush=True)
    glued = re.search(r"(?mi)^Stop\s+\d+:.*\b(?:Address|Coordinates|Orientation|"
                      r"Directions):", text)
    missing = _dg.count_stops_missing_directions(text)
    # The LOCAL-650 guards must be no-ops on a museum tour.
    t1, ch1 = _tsg.rename_theme_phrase_stops(text)
    t2, rep2 = _wdg.ensure_walking_directions_lead_to_next(text)
    t3, ch3 = _cac.ensure_current_affairs_coverage(text)
    noop = (ch1 == [] and rep2['corrected'] == 0 and not ch3
            and t1 == text and t2 == text and t3 == text)
    print(f"  [canary] run-on header: {bool(glued)}  missing_directions: {missing}  "
          f"LOCAL-650 guards no-op: {noop}", flush=True)
    print(f"  [LOCAL-650] MUSEUM RESULT: run_on={bool(glued)} "
          f"missing_directions={missing} guards_noop={noop} "
          f"(run_on False, missing 0, noop True)", flush=True)


def _store(location, text, n_stops, slug, kind_desc):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-650 {location.split(',')[0][:40]} {int(time.time())}"
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
        print(f"[reserve-gate] SKIP {slug}: would exceed cap "
              f"(${spend:.4f}+${RESERVE_USD} > ${HARD_CAP_USD})", flush=True)
        return None, 'SKIPPED_CAP'
    print(f"=== generating: {location} ({stops} stops, {tour_type}) ===",
          flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            location, tour_type, f"/app/tours/LOCAL650_{slug}.txt", stops,
            user_id=None)
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
    if tour_type == 'walking':
        _report_walking(text)
    else:
        _report_museum(text)
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        _tot = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
        print(f"[cost] tour_total=${_tot:.4f}", flush=True)
    except Exception:
        pass
    nid = _store(location, text, delivered, slug,
                 f"LOCAL-650 live fresh ({slug}, {tour_type})")
    if nid:
        print(f"STORED audio_tours id = {nid}  (is_test=true)", flush=True)
        print(f"LOCAL650_TOUR_ID_{slug}={nid}", flush=True)
    return nid, 'DELIVERED'


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}",
      flush=True)

results = []
for _loc, _stops, _ttype, _slug in TOURS:
    _id, _outcome = _run_one(_loc, _stops, _ttype, _slug)
    results.append((_slug, _id, _outcome))

print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}",
      flush=True)
print("=== LOCAL-650 run complete ===", flush=True)
for _slug, _id, _outcome in results:
    print(f"RESULT {_slug}: id={_id if _id else ''} outcome={_outcome}",
          flush=True)
