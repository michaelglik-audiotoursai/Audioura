#!/usr/bin/env python3
"""run_local643_container.py — LOCAL-643 live acceptance (ISOLATED container).

Generates the TWO ticket venues through the REAL generation path with the
LOCAL-643 branch code in the image and STRUCTURED_STOPS=1, cache + pool OFF
(FRESH tours):

    1. The National Gallery, London, United Kingdom   (3 stops)
    2. The Courtauld Gallery, London, United Kingdom   (3 stops)

STRUCTURED_STOPS=1 makes the delivered text come from Stop/Opening/Closing
records (headers + field lines rendered ONCE) with narration-only passes run per
stop — the Strategy A cause-class replacement. Expected: 0 structural detector
failures (no header glued to a field, no orientation migrated between stops, no
lost/duplicated stop header, no split "9.00").

HARD CAP $1.50 combined, enforced with the RESERVE GATE: a tour is started only
if (spend_so_far + reserve) <= $1.50. Each delivered tour's SPOKEN text is stored
as an additive is_test row for critique.sh / detectors.py. is_test rows are the
ONLY rows written. No DELETE.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-643')
except Exception as _meter_err:
    print(f"[LOCAL-613] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import socket
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tours (cache off)
os.environ['DISABLE_STOP_POOL'] = '1'             # pool off (ticket requirement)
os.environ['STRUCTURED_STOPS'] = '1'              # LOCAL-643 flag ON for this run
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.50')
os.environ['COST_HARD_LIMIT_USD'] = '1.50'        # ticket HARD CAP
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')

HARD_CAP_USD = float(os.environ.get('LOCAL643_CAP_USD', '1.50'))
RESERVE_USD = float(os.environ.get('LOCAL643_RESERVE_USD', '0.80'))  # start a tour only if spend + reserve <= cap
HOST = socket.gethostname()

VENUES = [
    ('The National Gallery, London, United Kingdom', 3, 'NATIONAL_GALLERY'),
    ('The Courtauld Gallery, London, United Kingdom', 3, 'COURTAULD'),
]
_only = (os.environ.get('LOCAL643_ONLY') or '').strip().upper()
if _only:
    VENUES = [v for v in VENUES if v[2] == _only] or VENUES

print("=== LOCAL-643 isolated live run (National Gallery + Courtauld, 3 stops each) ===", flush=True)
print(f"host  : {HOST}", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   HARD CAP: ${HARD_CAP_USD}  "
      f"reserve: ${RESERVE_USD}  cache_off=1 pool_off=1 STRUCTURED_STOPS=1", flush=True)

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
    """Reserve-gate input: USD spent by THIS container host (paid_api_calls)."""
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


# ── Structural detectors (LOCAL-643): 0 failures expected ─────────────────────
_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
_FIELD_LABELS = (r"Address|Coordinates|Type/Specialty|Specific Examples|"
                 r"Operational Details|Museum Information|Orientation|Directions")


def _detectors(text):
    """Run the structure detectors this ticket targets. Returns a list of
    (name, detail) failures — empty list means a clean, well-formed tour."""
    fails = []
    headers = list(_STOP_HEADER_RE.finditer(text))

    # 1. No field label glued onto a 'Stop N:' header line.
    for h in headers:
        line = h.group(0)
        if re.search(rf"\b({_FIELD_LABELS}):", line):
            fails.append(("header_glued_to_field", line[:120]))

    # 2. Every stop header on its own line (no two headers on one line).
    for h in headers:
        if len(re.findall(r"(?i)\bStop\s+\d+:", h.group(0))) > 1:
            fails.append(("two_headers_one_line", h.group(0)[:120]))

    # 3. No empty bare field labels.
    for m in re.finditer(rf"(?mi)^\s*({_FIELD_LABELS}):\s*$", text):
        fails.append(("empty_bare_label", m.group(0).strip()))

    # 4. At most one Orientation per stop block (no duplication/migration doubling).
    blocks = re.split(r"(?m)(?=^Stop\s+\d+:)", text)
    for b in blocks:
        if not b.strip().startswith("Stop "):
            continue
        if len(re.findall(r"(?mi)^Orientation:", b)) > 1:
            fails.append(("two_orientations_in_stop", b.split(chr(10))[0][:80]))

    # 4b. No doubled 'Orientation: Orientation:' label on any line.
    if re.search(r"(?mi)^Orientation:\s*Orientation:", text):
        fails.append(("doubled_orientation_label", "Orientation: Orientation:"))

    # 5. No split decimal price ("9.\n\n00" / "Admission is 9." then "00 pounds").
    if re.search(r"(?i)\b\d+\.\s*(?:\n|$)\s*0{2}\b", text) or \
       re.search(r"(?i)is\s+\d+\.\s*$.*?^0{2}\b", text, re.MULTILINE | re.DOTALL):
        fails.append(("split_decimal_price", "a price decimal was split"))

    # 6. Delivered stop count matches the headers (no lost header).
    delivered = _tc.count_delivered_stops(text)
    if delivered != len(headers):
        fails.append(("stop_count_mismatch",
                      f"count_delivered={delivered} headers={len(headers)}"))

    return fails


def _per_stop_orientation(text):
    headers = list(_STOP_HEADER_RE.finditer(text))
    for i, h in enumerate(headers):
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        block = text[start:end]
        title = h.group(2).strip()
        om = re.search(r"(?im)^\s*Orientation:\s*(.+)$", block)
        if om:
            print(f"  STOP {i+1}: {title}", flush=True)
            print(f"    Orientation: {om.group(1).strip()[:200]}", flush=True)
        else:
            print(f"  STOP {i+1}: {title}", flush=True)
            print(f"    Orientation: <<< none >>>", flush=True)


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-643 {location.split(',')[0]} {int(time.time())}"
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
                 f"LOCAL-643 live fresh STRUCTURED_STOPS=1 ({slug})"))
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
        return None
    print(f"=== generating: {location} ({stops} stops) STRUCTURED_STOPS=1 ===", flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            location, 'museum', f"/app/tours/LOCAL643_{slug}.txt", stops, user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {location}: {e}", flush=True); return None
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True); return None
    delivered = _tc.count_delivered_stops(text)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    try:
        from generate_tour_text import _J as _gj
        print(f"[delivery] path = {getattr(_gj, '_LAST_DELIVERY_PATH', '?')}", flush=True)
    except Exception:
        pass
    _per_stop_orientation(text)
    fails = _detectors(text)
    if fails:
        print(f"  [detectors] {len(fails)} STRUCTURAL FAILURE(S):", flush=True)
        for name, detail in fails:
            print(f"    FAIL {name}: {detail}", flush=True)
    else:
        print(f"  [detectors] 0 structural failures — clean", flush=True)
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
        print(f"LOCAL643_TOUR_ID={nid}", flush=True)
    return nid


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}", flush=True)

ids = []
for location, stops, slug in VENUES:
    tid = _run_one(location, stops, slug)
    if tid:
        ids.append(tid)

print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}", flush=True)
print("=== LOCAL-643 run complete ===", flush=True)
print(f"LOCAL643_TOUR_IDS={','.join(str(i) for i in ids)}", flush=True)
