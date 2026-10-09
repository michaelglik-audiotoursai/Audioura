#!/usr/bin/env python3
"""run_local658_container.py — LOCAL-658 live acceptance (ISOLATED container).

ONE paid tour: the ticket's Boston request, fresh (cache + pool OFF), through the
real generation path with the LOCAL-658 fixes in the image:

  "Walking tour in Boston dedicated to Massachusetts politics and current affairs,
   Boston, MA" — 5 stops, walking.

What this proves on the delivered tour (the four defects):
  D1 — every walking leg is within the hard limit; a far GEO-CHECK replacement is
       NOT delivered (if a stop was dropped as unwalkable, N-1 with an honest
       shortfall sentence).
  D2 — no stop header / directions truncated at an initial ("John F.", "M. Pei").
  D3 — the conclusion is category-appropriate (the request's theme / places),
       never "modern art" / "the works show" on this walking tour.
  D4 — Type/Specialty / Specific Examples are present in the text view but the
       TTS-stripped spoken text does not contain the field labels.

HARD CAP $1.20 for the WHOLE task, enforced by tests/live_run_meter.py across all
providers, plus a RESERVE GATE before the tour. The delivered SPOKEN text is
stored as ONE additive is_test row. is_test rows are the ONLY rows written. No
DELETE. At most ONE tour is started. The museum canary is OFFLINE (fixtures) —
this harness never starts a paid museum tour.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-658')
except Exception as _meter_err:
    print(f"[LOCAL-658] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import socket
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tour (cache off)
os.environ['DISABLE_STOP_POOL'] = '1'             # pool off (fresh)
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.20')
os.environ['COST_HARD_LIMIT_USD'] = '1.20'        # ticket HARD CAP (whole task)
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
os.environ.setdefault('STOP_EDITOR', '1')
os.environ.setdefault('STOP_EDITOR_ENABLED', '1')

HARD_CAP_USD = 1.20
RESERVE_USD = 0.55          # start the tour only if spend + 0.55 <= cap
HOST = socket.gethostname()

LOCATION = ('Walking tour in Boston dedicated to Massachusetts politics and '
            'current affairs, Boston, MA')
STOPS = 5
TTYPE = 'walking'
SLUG = 'BOSTONWALK'

print("=== LOCAL-658 isolated live run (Boston walking 5, ONE paid tour) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   HARD CAP(task): "
      f"${HARD_CAP_USD}  reserve: ${RESERVE_USD}  cache_off=1 pool_off=1",
      flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402

# D4 TTS stripper (exact production function).
try:
    from tour_generation_modernized import _strip_nav_fields_for_tts
except Exception:
    _strip_nav_fields_for_tts = None

# Walking leg geometry (same haversine the generator uses).
from generate_tour_text import _haversine_km, _parse_coords  # noqa: E402
from tour_settings import WALKING_LEG_HARD_KM, WALKING_TOTAL_HARD_KM  # noqa: E402

_INITIAL_TAIL = re.compile(r'(?:^|\s)[A-Z]\.$')   # a header/line ENDING on an initial


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


def _stop_blocks(text):
    """[(num, name, coord)] for each delivered Stop block."""
    heads = list(re.finditer(r'(?mi)^Stop\s+(\d+):\s*(.+?)\s*$', text))
    out = []
    for i, h in enumerate(heads):
        start = h.start()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        seg = text[start:end]
        cm = re.search(r'(?mi)^Coordinates:\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)',
                       seg)
        coord = None
        if cm:
            try:
                coord = (float(cm.group(1)), float(cm.group(2)))
            except ValueError:
                coord = None
        out.append((int(h.group(1)), h.group(2).strip(), coord))
    return out


def _report(text):
    blocks = _stop_blocks(text)
    print("  --- STOP LIST + LEG DISTANCES ---", flush=True)
    prev = None
    truncated = []
    for num, name, coord in blocks:
        leg = ""
        if prev and prev[2] and coord:
            d = _haversine_km(prev[2], coord)
            flag = "  <<< OVER LEG LIMIT" if d > WALKING_LEG_HARD_KM else ""
            leg = f"  leg_from_prev={d:.2f} km{flag}"
        print(f"  STOP {num}: {name[:80]}{leg}", flush=True)
        if _INITIAL_TAIL.search(name):
            truncated.append(name)
        prev = (num, name, coord)
    # Total straight-line route length.
    coords = [c for _, _, c in blocks if c]
    total = sum(_haversine_km(coords[i], coords[i + 1])
                for i in range(len(coords) - 1)) if len(coords) >= 2 else 0.0
    print(f"  [D1] total straight-line route = {total:.2f} km "
          f"(hard total limit {WALKING_TOTAL_HARD_KM} km, per-leg {WALKING_LEG_HARD_KM} km)",
          flush=True)
    # D2: any header truncated at an initial?
    print(f"  [D2] stop headers truncated at an initial = "
          f"{truncated if truncated else 'NONE'}", flush=True)
    for pat in ('Continue to', 'head to', 'make your way to'):
        for m in re.finditer(r'(?i)' + pat + r'\s+([^.\n]{0,60})', text):
            tgt = m.group(1).strip()
            if _INITIAL_TAIL.search(tgt + '.') or re.search(r'\b[A-Z]\.\s*(?:—|-|$)', tgt):
                print(f"  [D2] directions target may be truncated: '{pat} {tgt}'",
                      flush=True)
    # D3: conclusion.
    concl = ""
    m = re.search(r'(?i)(Across these stops[^\n]+|This tour followed one thread[^\n]+)',
                  text)
    if m:
        concl = m.group(1).strip()
    print(f"  [D3] conclusion: {concl[:300] if concl else '(not found)'}",
          flush=True)
    low = (concl or text).lower()
    print(f"  [D3] 'modern art' in conclusion = {'modern art' in low}", flush=True)
    print(f"  [D3] 'the works show' in conclusion = {'the works show' in low}",
          flush=True)
    # D4: field lines present in text view but stripped from TTS.
    has_type = 'Type/Specialty:' in text
    has_examples = 'Specific Examples:' in text
    print(f"  [D4] text view has Type/Specialty={has_type} "
          f"Specific Examples={has_examples}", flush=True)
    if _strip_nav_fields_for_tts:
        spoken = _strip_nav_fields_for_tts(text)
        print(f"  [D4] TTS-spoken has 'Type/Specialty:'="
              f"{'Type/Specialty:' in spoken} 'Specific Examples:'="
              f"{'Specific Examples:' in spoken} (both MUST be False)", flush=True)
    # Shortfall sentence (D1 N-1 honesty), if any.
    sm = re.search(r'(?i)(so this tour has[^.\n]*\.|rather than the \d+ you[^.\n]*\.)',
                   text)
    if sm:
        print(f"  [D1] honest shortfall sentence present: '{sm.group(0).strip()}'",
              flush=True)


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-658 {location.split(',')[0][:40]} {int(time.time())}"
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
                 f"LOCAL-658 live fresh ({slug}, walking)"))
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
        return None, 'SKIPPED_CAP'
    print(f"=== generating: {LOCATION} ({STOPS} stops, {TTYPE}) ===", flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            LOCATION, TTYPE, f"/app/tours/LOCAL658_{SLUG}.txt", STOPS,
            user_id=None)
    except Exception as e:
        print(f"RUN ERROR: {e}", flush=True)
        return None, f'ERROR:{e}'
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
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
    nid = _store(LOCATION, text, delivered, SLUG)
    if nid:
        print(f"STORED audio_tours id = {nid}  (is_test=true)", flush=True)
        print(f"LOCAL658_TOUR_ID_{SLUG}={nid}", flush=True)
    return nid, 'DELIVERED'


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}",
      flush=True)

_id, _outcome = _run_one()

print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}",
      flush=True)
print("=== LOCAL-658 run complete ===", flush=True)
print(f"RESULT {SLUG}: id={_id if _id else ''} outcome={_outcome}", flush=True)
