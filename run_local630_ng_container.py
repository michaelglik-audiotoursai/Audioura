#!/usr/bin/env python3
"""run_local630_container.py — LOCAL-630 live acceptance (ISOLATED container).

Generates the TWO ticket venues through the REAL generation path with the
LOCAL-630 branch code in the image, cache + pool OFF (FRESH tours), STOP_EDITOR
on:

    1. The National Gallery, London, UK         (3 stops)  — the ticket venue
                                                             (every item 1–8).
    2. Art Institute of Chicago, Chicago, USA   (3 stops)  — never-generated
                                                             famous museum.

HARD CAP $1.50 combined, enforced with the RESERVE GATE: a tour is started only
if (spend_so_far + $0.90) <= $1.50, where spend_so_far is read from
paid_api_calls summed for THIS container host. For each delivered tour it prints
the stop titles (collection check), the single practical-facts sentence (spoken
hours + admission), the About section, and the conclusion, then stores the
SPOKEN text as an additive is_test row for critique.sh. is_test rows are the ONLY
rows written. No DELETE.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-630')
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
os.environ['STOP_EDITOR'] = '1'                   # ticket: STOP_EDITOR=1
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.50')
os.environ['COST_HARD_LIMIT_USD'] = '1.50'        # ticket HARD CAP
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
os.environ.setdefault('STORY_PREFS', '1')

HARD_CAP_USD = 0.90          # remaining budget after the first run ($1.50 total)
RESERVE_USD = 0.60           # start a tour only if spend + 0.60 <= cap
HOST = socket.gethostname()

VENUES = [
    ('The National Gallery, London, UK', 3, 'NATIONAL_GALLERY'),
]

print("=== LOCAL-630 isolated live run (National Gallery + Art Institute of "
      "Chicago, 3 stops each) ===", flush=True)
print(f"host  : {HOST}", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   HARD CAP: ${HARD_CAP_USD}  "
      f"reserve: ${RESERVE_USD}  STOP_EDITOR={os.environ['STOP_EDITOR']}  "
      f"cache={os.environ['DISABLE_TOUR_CACHE']} pool={os.environ['DISABLE_STOP_POOL']}",
      flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402


def _conn():
    import psycopg2
    dburl = os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', 'development-postgres-2-1'),
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


def _report(text):
    """Print the stop titles (collection check), the single practical-facts
    sentence, the About section and the conclusion for critique."""
    # Stop titles — the collection check reads these against the venue.
    for m in re.finditer(r"(?mi)^Stop\s+\d+:\s*(.+)$", text):
        print(f"  STOP TITLE: {m.group(1).strip()}", flush=True)
    # Single practical-facts sentence: spoken hours + admission.
    for m in re.finditer(r"(?mi)\b([A-Z][^.\n]*?\bis open\b[^.\n]*\.)", text):
        print(f"  HOURS(spoken): {m.group(1).strip()}", flush=True)
    for m in re.finditer(
            r"(?mi)\b((?:A ticket is|Admission is|Standard admission is|"
            r"admission is|free admission|The .* is free)[^.\n]*\.)", text):
        print(f"  ADMISSION(spoken): {m.group(1).strip()}", flush=True)
    # About section (Stop 1's opening paragraph) — print its first lines.
    _s1 = text.split("Stop 2:")[0]
    _about = re.search(r"(?is)Orientation:\s*(.+)", _s1)
    if _about:
        snippet = " ".join(_about.group(1).split())[:600]
        print(f"  ABOUT/OPENING: {snippet}", flush=True)
    # Conclusion tail.
    _m = re.search(r"(?ims)^(This tour|Across these stops|Across the stops|"
                   r"Together,? these|What connects|The works on this tour|"
                   r"The stops on this tour|On this tour)\b.*", text)
    if _m:
        print("  --- CONCLUSION ---", flush=True)
        for line in _m.group(0).splitlines():
            if line.strip():
                print(f"    {line.strip()}", flush=True)
        print("  --- end conclusion ---", flush=True)
    # Marker leak check (item 7).
    if "LOCAL-628:stop-editor" in text:
        print("  [item 7] WARNING: editor marker present in delivered text!",
              flush=True)
    else:
        print("  [item 7] editor marker absent from delivered text — OK",
              flush=True)


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-630 {location.split(',')[0]} {int(time.time())}"
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
                 f"LOCAL-630 live fresh ({slug})"))
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
            location, 'museum', f"/app/tours/LOCAL630_{slug}.txt", stops,
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
        print(f"LOCAL630_TOUR_ID={nid}", flush=True)
    return nid


print(f"[db] audio_tours row count BEFORE: {_row_count()}", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}",
      flush=True)

ids = []
for location, stops, slug in VENUES:
    tid = _run_one(location, stops, slug)
    if tid:
        ids.append(tid)

print(f"\n[db] audio_tours row count AFTER: {_row_count()}", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}",
      flush=True)
print("=== LOCAL-630 run complete ===", flush=True)
print(f"LOCAL630_TOUR_IDS={','.join(str(i) for i in ids)}", flush=True)
