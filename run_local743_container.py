#!/usr/bin/env python3
"""run_local743_container.py — LOCAL-743 live acceptance (ISOLATED container).

ONE paid tour: the ticket's request, fresh (cache + pool OFF), through the real
generation path with the LOCAL-743 fixes in the image:

  "the episode 1 of season 1 biking tour, Salem, MA" — 5 stops, biking.

What this proves on the delivered tour:
  * Every stop heading is the house "Stop N:" form — in particular Stop 1 is NOT
    a sentence ("Stop 1 is the X."), so the modernized splitter produces 5 audio
    files and stops_count=5 (the live defect delivered 4, stop 1 silent).
  * count_delivered_stops(text) == 5 and the modernized splitter (the exact live
    packer) yields 5 text_content blocks.
  * No structural field label (Coordinates:/Type/Specialty:/Specific Examples:)
    leaks into the spoken text.

HARD CAP $0.60 for the WHOLE task, enforced by tests/live_run_meter.py across all
providers, plus a RESERVE GATE before the tour. The delivered SPOKEN text is
stored as ONE additive is_test row. is_test rows are the ONLY rows written. No
DELETE. At most ONE tour is started.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-743')
except Exception as _meter_err:
    print(f"[LOCAL-743] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import socket
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tour (cache off)
os.environ['DISABLE_STOP_POOL'] = '1'             # pool off (fresh)
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '0.60')
os.environ['COST_HARD_LIMIT_USD'] = '0.60'        # ticket HARD CAP (whole task)
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
os.environ.setdefault('STOP_EDITOR', '1')
os.environ.setdefault('STOP_EDITOR_ENABLED', '1')

HARD_CAP_USD = 0.60
RESERVE_USD = 0.55          # start the tour only if spend + 0.55 <= cap
HOST = socket.gethostname()

LOCATION = 'the episode 1 of season 1 biking tour, Salem, MA'
STOPS = 5
TTYPE = 'biking'
SLUG = 'SALEMBIKE'

print("=== LOCAL-743 isolated live run (Salem biking 5, ONE paid tour) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   HARD CAP(task): "
      f"${HARD_CAP_USD}  reserve: ${RESERVE_USD}  cache_off=1 pool_off=1",
      flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402
import tour_generation_modernized as _tgm  # noqa: E402

try:
    from tour_generation_modernized import _strip_nav_fields_for_tts
except Exception:
    _strip_nav_fields_for_tts = None


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
    # The headline LOCAL-743 proof: the live splitter's view == the counter's view.
    delivered = _tc.count_delivered_stops(text)
    parsed = _tgm.parse_tour_content_to_modernized(text)
    n_split = len(parsed["text_content"])
    heads = re.findall(r'(?mi)^Stop\s+(\d+):\s*(.+?)\s*$', text)
    print("  --- STOP HEADERS (rendered) ---", flush=True)
    for num, name in heads:
        print(f"  Stop {num}: {name[:80]}", flush=True)
    print(f"  [LOCAL-743] count_delivered_stops = {delivered}", flush=True)
    print(f"  [LOCAL-743] modernized splitter blocks = {n_split} "
          f"(== number of audio_N files the live packer will write)", flush=True)
    # Sentence-form header must be gone.
    sentence_form = re.findall(r'(?mi)^Stop\s+\d+\s+(?:is\b|[-\u2013\u2014])', text)
    print(f"  [LOCAL-743] sentence-form stop headers remaining = "
          f"{sentence_form if sentence_form else 'NONE'}", flush=True)
    # Label leak into spoken text.
    leaks = _tc.find_leaked_field_labels(text)
    print(f"  [LOCAL-743] field-label leaks in text = "
          f"{leaks if leaks else 'NONE'}", flush=True)
    if _strip_nav_fields_for_tts:
        spoken = "\n".join(_strip_nav_fields_for_tts(b) for b in parsed["text_content"])
        for lbl in ("Coordinates:", "Type/Specialty:", "Specific Examples:"):
            print(f"  [LOCAL-743] TTS-spoken contains '{lbl}' = {lbl in spoken} "
                  f"(MUST be False)", flush=True)
    return delivered, n_split


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-743 {location.split(',')[0][:40]} {int(time.time())}"
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
                 f"LOCAL-743 live fresh ({slug}, biking)"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


def _run_one():
    spend = _spend_so_far()
    print(f"\n[reserve-gate] spend_so_far=${spend if spend is not None else '?'} "
          f"+ reserve ${RESERVE_USD} vs cap ${HARD_CAP_USD}", flush=True)
    if spend is not None and (spend + RESERVE_USD) > HARD_CAP_USD:
        print(f"[reserve-gate] SKIP {SLUG}: would exceed cap", flush=True)
        return None, 'SKIPPED_CAP', 0, 0
    print(f"=== generating: {LOCATION} ({STOPS} stops, {TTYPE}) ===", flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            LOCATION, TTYPE, f"/app/tours/LOCAL743_{SLUG}.txt", STOPS,
            user_id=None)
    except Exception as e:
        print(f"RUN ERROR: {e}", flush=True)
        return None, f'ERROR:{e}', 0, 0
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        return None, 'NO_TEXT', 0, 0
    delivered, n_split = _report(text)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        _tot = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
        print(f"[cost] tour_total=${_tot:.4f}", flush=True)
    except Exception:
        pass
    nid = _store(LOCATION, text, delivered, SLUG)
    if nid:
        print(f"STORED audio_tours id = {nid}  (is_test=true)", flush=True)
        print(f"LOCAL743_TOUR_ID_{SLUG}={nid}", flush=True)
    return nid, 'DELIVERED', delivered, n_split


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}",
      flush=True)

_id, _outcome, _delivered, _nsplit = _run_one()

print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}",
      flush=True)
print("=== LOCAL-743 run complete ===", flush=True)
print(f"RESULT {SLUG}: id={_id if _id else ''} outcome={_outcome} "
      f"delivered_stops={_delivered} splitter_blocks={_nsplit}", flush=True)
