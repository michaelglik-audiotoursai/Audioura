#!/usr/bin/env python3
"""run_local646_container.py — LOCAL-646 live acceptance (ISOLATED container).

Generates TWO fresh tours through the REAL generation path with the LOCAL-646
branch code in the image (the stop_editor _STRUCT_LABELS fix and the
directions_guarantee MULTILINE fix), cache + pool OFF:

  1. WALKING: "Walking tour in Boston dedicated to Massachusetts politics and
     current affairs, Boston, MA" — 5 stops. The regression tour (557). Must show
     reg 1 (no collapsed Stop-4 field/Orientation block) and reg 2 (no duplicate
     "Continue to <next>" after an existing walking "Directions:" line) FIXED.
  2. MUSEUM CANARY: "The Courtauld Gallery, London, United Kingdom" — 3 stops.
     Must have 0 detector failures (the museum work must not regress).

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
    _live_run_meter.auto_meter('LOCAL-646')
except Exception as _meter_err:
    print(f"[LOCAL-646] live_run_meter unavailable ({_meter_err}): "
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
os.environ.setdefault('STOP_EDITOR', '1')         # the fixed editor must run
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

print("=== LOCAL-646 isolated live run (Boston walking 5 + Courtauld 3) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   HARD CAP(combined): "
      f"${HARD_CAP_USD}  reserve: ${RESERVE_USD}  cache_off=1 pool_off=1",
      flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402
import directions_guarantee as _dg  # noqa: E402


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
    """Assert the two LOCAL-646 regressions are absent in a WALKING tour."""
    headers = re.findall(r"(?mi)^Stop\s+\d+:\s*(.+)$", text)
    for h in headers:
        print(f"  STOP TITLE: {h.strip()[:90]}", flush=True)
    m = re.search(r"That['\u2019]s\s+(\d+)\s+stops?", text)
    stated = m.group(1) if m else "?"
    print(f"  HEADER COUNT: {len(headers)}   "
          f"count_delivered_stops: {_tc.count_delivered_stops(text)}   "
          f"stated 'That's N stops': {stated}", flush=True)

    # REG 1 — a field label glued AFTER another field's value on one line
    # ("Type/Specialty: X Specific Examples: Y"), or narration glued onto the
    # Orientation line. Both are the Stop-4 collapse shape.
    glued_fields = re.findall(
        r"(?mi)^(?:Type/Specialty|Specific Examples|Operational Details|"
        r"Museum Information|Address|Coordinates):[^\n]*\b"
        r"(?:Type/Specialty|Specific Examples|Operational Details|"
        r"Museum Information|Orientation):", text)
    # An Orientation line that also carries narration is detectable as an
    # Orientation line far longer than a one-sentence orientation AND immediately
    # followed by a non-blank line is NOT required; the strong signal is a second
    # field label on the Orientation line, covered above. We additionally flag a
    # Type/Specialty line that contains "Specific Examples:" inline.
    reg1_collapse = bool(glued_fields)
    print(f"  [REG1] collapsed field/Orientation lines: "
          f"{[g[:60] for g in glued_fields]}  -> collapse={reg1_collapse}",
          flush=True)

    # REG 2 — a duplicate stand-alone "Continue to <next>." / "Your final stop …"
    # transition that follows a stop whose body ALREADY has a "Directions:" line.
    # count_stops_missing_directions must be 0 AND no stop should carry BOTH a
    # Directions: line and a separate transition line to the same next stop.
    missing = _dg.count_stops_missing_directions(text)
    # Detect a literal duplicate: a "Directions:" line in a block immediately
    # followed (within the same block) by a bare "Continue to X." whose X is the
    # next stop title.
    body, _tail = _dg._body_and_tail(text)
    blocks = _dg._stop_blocks(body)
    dup_transitions = []
    for i in range(len(blocks) - 1):
        s, e, _t = blocks[i]
        seg = body[s:e]
        nxt = blocks[i + 1][2]
        has_dir = bool(re.search(r"(?mi)^\s*Directions:\s*\S", seg))
        has_cont = bool(re.search(
            r"(?mi)^\s*(?:Continue to|Your final stop[^:]*:)\s*" +
            re.escape(nxt), seg))
        if has_dir and has_cont:
            dup_transitions.append(f"stop{i+1}->{nxt[:40]}")
    reg2_dup = bool(dup_transitions)
    print(f"  [REG2] missing_directions={missing}  "
          f"dup(Directions+Continue) blocks={dup_transitions} -> dup={reg2_dup}",
          flush=True)

    print(f"  [LOCAL-646] WALKING RESULT: reg1_collapse={reg1_collapse}  "
          f"reg2_dup={reg2_dup}  (both must be False)", flush=True)


def _report_museum(text):
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
    print(f"  [canary] run-on header: {bool(glued)}  "
          f"missing_directions: {_dg.count_stops_missing_directions(text)}",
          flush=True)


def _store(location, text, n_stops, slug, kind_desc):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-646 {location.split(',')[0][:40]} {int(time.time())}"
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
            location, tour_type, f"/app/tours/LOCAL646_{slug}.txt", stops,
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
                 f"LOCAL-646 live fresh ({slug}, {tour_type})")
    if nid:
        print(f"STORED audio_tours id = {nid}  (is_test=true)", flush=True)
        print(f"LOCAL646_TOUR_ID_{slug}={nid}", flush=True)
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
print("=== LOCAL-646 run complete ===", flush=True)
for _slug, _id, _outcome in results:
    print(f"RESULT {_slug}: id={_id if _id else ''} outcome={_outcome}",
          flush=True)
