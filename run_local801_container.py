#!/usr/bin/env python3
"""run_local801_container.py — LOCAL-801 live acceptance (ISOLATED container).

Regenerates the TWO P1-flagged requests through the REAL generation path on the
DEFAULT arm (no NARRATION_MODEL / TOUR_LLM_MODEL override — the gpt-4.1 cloud
setting that produced the P1 defects), cache + pool OFF (FRESH tours):

    1. Freedom Trail walking tour, Boston, MA   (5 stops, walking)
       P1 w1: Park Street Church delivered twice, "6 stops for 5".
    2. coffee shops in Jamaica Plain, Boston     (3 stops, restaurant)
       P1 d1: Stop 1 mid-clause collision ("J.P. Licks.P. Licks.P. Licks").

Gemini prepaid credit is DEPLETED (LEAD, 2026-10-28), so research runs on
RESEARCH_BACKEND=serper with no Gemini grounding. A step that still needs Gemini
is reported UNPROVEN rather than retried.

HARD CAP $1.50 combined, enforced with a RESERVE GATE read from paid_api_calls
for THIS container host. For each delivered tour it prints the stop titles, the
delivered stop count vs requested, the "That's N stops" sentence, and runs the
three LOCAL-801 acceptance checks:

  A. delivered stop count == requested (never more) and no duplicate title.
  B. no stray preview header ("Stop N: … — it is roughly … away.").
  C. no mid-clause collision ("<word>.P. <word>.P." weld; dangling "from J.P.").

is_test rows are the ONLY rows written. No DELETE. Never the live DB.
"""
import os
import re
import socket
import time

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-801')
except Exception as _meter_err:
    print(f"[LOCAL-801] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped by the meter")

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tours (cache off)
os.environ['DISABLE_STOP_POOL'] = '1'             # pool off (regenerate clean)
os.environ.setdefault('STOP_EDITOR', '1')
# DEFAULT ARM: do NOT set TOUR_LLM_MODEL / NARRATION_MODEL — use image defaults
# (gpt-4.1), the cloud setting that produced the P1 defects.
os.environ['RESEARCH_BACKEND'] = 'serper'         # LEAD: Gemini credit depleted
os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.50')
os.environ['COST_HARD_LIMIT_USD'] = '1.50'        # ticket HARD CAP

HARD_CAP_USD = 1.50
RESERVE_USD = 0.70            # start a tour only if spend + 0.70 <= cap
HOST = socket.gethostname()

# (request_string, stops, tour_category, slug)
REQUESTS = [
    ('Freedom Trail walking tour, Boston, MA', 5, 'walking', 'W1_FREEDOM_TRAIL'),
    ('coffee shops in Jamaica Plain, Boston', 3, 'restaurant', 'D1_JP_COFFEE'),
]

print("=== LOCAL-801 isolated live run (DEFAULT arm, RESEARCH_BACKEND=serper) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"arm   : DEFAULT (no NARRATION_MODEL/TOUR_LLM_MODEL override)  "
      f"HARD CAP ${HARD_CAP_USD}  reserve ${RESERVE_USD}  "
      f"cache={os.environ['DISABLE_TOUR_CACHE']} pool={os.environ['DISABLE_STOP_POOL']} "
      f"research={os.environ['RESEARCH_BACKEND']}", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402


def _conn():
    import psycopg2
    dburl = os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
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


# ── LOCAL-801 acceptance checks ───────────────────────────────────────────────
_STRAY_PREVIEW = re.compile(
    r'(?im)^Stop \d+:.*(?:\u2014|--|-)\s*it is (?:roughly|about|approximately)')
_WELD = re.compile(r'\b\w+\.(?:[A-Z]\.)\s+\w+\.(?:[A-Z]\.)')
_DANGLING = re.compile(r'(?i)\b(?:from|at|to|by)\s+[A-Z]\.(?:[A-Z]\.)?\s*[A-Z][a-z]+\s')


def _accept(text, requested):
    text = _tc.normalise_stop_headers(text)
    titles = [m.group(1).strip() for m in
              re.finditer(r"(?mi)^Stop\s+\d+:\s*(.+)$", text)]
    delivered = _tc.count_delivered_stops(text)
    norm = [re.sub(r'\s+', ' ', t.lower()).strip(' .,:;"\'') for t in titles]
    dup = len(norm) != len(set(norm))
    m_cnt = re.search(r"That['\u2019]s\s+(\d+)\s+stops?", text)
    stated = int(m_cnt.group(1)) if m_cnt else None
    checks = {
        'A_count_eq_requested': delivered == requested,
        'A_no_duplicate_title': not dup,
        'A_stated_matches': (stated is None) or (stated == delivered),
        'B_no_stray_preview': not bool(_STRAY_PREVIEW.search(text)),
        'C_no_weld': not bool(_WELD.search(text)),
        'C_no_dangling_abbrev': not bool(_DANGLING.search(text)),
    }
    print(f"  STOP TITLES ({delivered}/{requested}): {titles}", flush=True)
    if stated is not None:
        print(f"  CLOSING COUNT: \"That's {stated} stops\"", flush=True)
    for k, v in checks.items():
        print(f"  CHECK {k}: {'PASS' if v else 'FAIL'}", flush=True)
    return all(checks.values()), checks


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-801 {location.split(',')[0]} {int(time.time())}"
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
                 f"LOCAL-801 live fresh ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


def _run_one(location, stops, category, slug):
    spend = _spend_so_far()
    print(f"\n[reserve-gate] spend_so_far=${spend if spend is not None else '?'} "
          f"+ reserve ${RESERVE_USD} vs cap ${HARD_CAP_USD}", flush=True)
    if spend is not None and (spend + RESERVE_USD) > HARD_CAP_USD:
        print(f"[reserve-gate] SKIP {slug}: would exceed cap", flush=True)
        return None
    print(f"=== generating: {location} ({stops} stops, {category}) ===", flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            location, category, f"/app/tours/LOCAL801_{slug}.txt", stops,
            user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {location}: {e}", flush=True); return None
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        return None
    delivered = _tc.count_delivered_stops(text)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    ok, _checks = _accept(text, stops)
    print(f"  LOCAL-801 ACCEPTANCE: {'ALL PASS' if ok else 'HAS FAILURES'}",
          flush=True)
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
        print(f"LOCAL801_TOUR_ID={nid}", flush=True)
    return nid


print(f"[db] audio_tours row count BEFORE: {_row_count()}", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}",
      flush=True)

ids = []
for location, stops, category, slug in REQUESTS:
    tid = _run_one(location, stops, category, slug)
    if tid:
        ids.append(tid)

print(f"\n[db] audio_tours row count AFTER: {_row_count()}", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}",
      flush=True)
print("=== LOCAL-801 run complete ===", flush=True)
print(f"LOCAL801_TOUR_IDS={','.join(str(i) for i in ids)}", flush=True)
