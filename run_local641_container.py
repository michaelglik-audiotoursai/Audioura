#!/usr/bin/env python3
"""run_local641_container.py — LOCAL-641 live acceptance (ISOLATED container).

Generates the TWO ticket venues through the REAL generation path with the
LOCAL-641 branch code in the image, cache + pool OFF (FRESH tours):

    1. The Courtauld Gallery, London, United Kingdom  (3 stops) — R10 FRESH scored
       Kiro 4 because Stop 1 opened with STOP 2's orientation (Van Gogh carried
       Seurat's "tapestry of discrete points / pointillist" orientation) while
       Stop 2 lost its own. The SAME stops reused scored 8 and 8.5. Target: each
       stop opens with ITS OWN orientation; Kiro >= 7.5 fresh.
    2. The National Gallery, London, United Kingdom   (3 stops) — the same class
       appeared at the NG in R4 ("Stop 1's Orientation describes Stop 2's
       painting").

Root cause (fixed on this branch): stop_pool_orchestrator._overall_from_new
searched the WHOLE gen_text for the first "Orientation:" label; when Stop 1's own
orientation was folded into opening prose (no label), it returned a LATER stop's
orientation and injected it onto Stop 1. It is now scoped to the Stop-1 block.
fix_orientation_work_mismatch is neutralised to a logging-only detector.

HARD CAP $1.30 combined, enforced with the RESERVE GATE: a tour is started only
if (spend_so_far + reserve) <= $1.30. Each delivered tour's SPOKEN text is stored
as an additive is_test row for critique.sh / detectors.py. is_test rows are the
ONLY rows written. No DELETE.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-641')
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
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.30')
os.environ['COST_HARD_LIMIT_USD'] = '1.30'        # ticket HARD CAP
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')

HARD_CAP_USD = 1.30
RESERVE_USD = 0.80          # start a tour only if spend + 0.80 <= cap
HOST = socket.gethostname()

VENUES = [
    ('The Courtauld Gallery, London, United Kingdom', 3, 'COURTAULD'),
    ('The National Gallery, London, United Kingdom', 3, 'NATIONAL_GALLERY'),
]
_only = (os.environ.get('LOCAL641_ONLY') or '').strip().upper()
if _only:
    VENUES = [v for v in VENUES if v[2] == _only] or VENUES

print("=== LOCAL-641 isolated live run (Courtauld + National Gallery, 3 stops each) ===", flush=True)
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


def _per_stop_orientation(text):
    """[LOCAL-641] Print each stop's title and the FIRST sentence of its spoken
    body / Orientation — the exact field this ticket is about. A stop with no own
    orientation (shift) shows up as the previous stop carrying a foreign work."""
    headers = list(re.finditer(r"(?mi)^Stop\s+(\d+):\s*(.+)$", text))
    for i, h in enumerate(headers):
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        block = text[start:end]
        title = h.group(2).strip()
        om = re.search(r"(?im)^\s*Orientation:\s*(.+)$", block)
        if om:
            orient = om.group(1).strip()
            label = "Orientation"
        else:
            # No Orientation label: show the first non-empty spoken line (the body
            # opener that plays the role of orientation after field-line stripping).
            lines = [l.strip() for l in block.splitlines()
                     if l.strip() and not re.match(
                         r"^\s*(Address|Coordinates|Museum Information|Type/Specialty|"
                         r"Specific Examples|Operational Details|Directions)\s*:", l)]
            orient = lines[0] if lines else "<<< NONE >>>"
            label = "Opener"
        print(f"  STOP {i+1}: {title}", flush=True)
        print(f"    {label}: {orient[:220]}", flush=True)


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-641 {location.split(',')[0]} {int(time.time())}"
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
                 f"LOCAL-641 live fresh ({slug})"))
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
    print(f"=== generating: {location} ({stops} stops) ===", flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            location, 'museum', f"/app/tours/LOCAL641_{slug}.txt", stops, user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {location}: {e}", flush=True); return None
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True); return None
    delivered = _tc.count_delivered_stops(text)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    _per_stop_orientation(text)
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
        print(f"LOCAL641_TOUR_ID={nid}", flush=True)
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
print("=== LOCAL-641 run complete ===", flush=True)
print(f"LOCAL641_TOUR_IDS={','.join(str(i) for i in ids)}", flush=True)
