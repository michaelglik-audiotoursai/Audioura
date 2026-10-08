#!/usr/bin/env python3
"""run_local625_container.py — LOCAL-625 live acceptance (ISOLATED container).

Generates the TWO venues from the LOCAL-625 ticket through the REAL generation
path with the branch code in the image, metered + hard-capped at $1.00 COMBINED
(all providers, via tests/live_run_meter.py):

    1. Mauritshuis, The Hague, Netherlands   (2 stops)  — the wrong-entity venue
    2. Alte Pinakothek, Munich, Germany      (2 stops)  — the garbage-hours /
                                                           room-as-stop venue

Both are FRESH museum tours (tour cache OFF). For each delivered tour it prints
the HOURS line(s), the per-stop ADDRESS lines and the STOP TITLES, then stores
the SPOKEN text as an additive is_test row in audio_tours (creator_type='Test')
so critique.sh <id> scores the SAME text. The is_test rows are the ONLY rows
written. No DELETE.
"""
# [LOCAL-613] Meter + cap this isolated run (install BEFORE importing generators).
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-625')
except Exception as _meter_err:
    print(f"[LOCAL-613] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # force FRESH tours
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.00')
os.environ['COST_HARD_LIMIT_USD'] = '1.00'        # ticket cap (two venues)
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
os.environ.setdefault('STORY_PREFS', '1')

VENUES = [
    ('Mauritshuis, The Hague, Netherlands', 2, 'MAURITSHUIS'),
    ('Alte Pinakothek, Munich, Germany', 2, 'ALTE_PINAKOTHEK'),
]

print("=== LOCAL-625 isolated live run (two FRESH museums, 2 stops each) ===",
      flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   combined cap: "
      f"${os.environ['COST_HARD_LIMIT_USD']}", flush=True)

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
        conn = _conn()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM audio_tours")
            n = cur.fetchone()[0]
        conn.close()
        return n
    except Exception as e:
        print(f"  [db] row count failed: {e}", flush=True)
        return None


# ── Report the LOCAL-625 defect lines straight off the delivered SPOKEN text ──
def _report_facts(text):
    # Hours
    for m in re.finditer(r"(?mi)^Museum Information:\s*(.+)$", text):
        print(f"  HOURS/Museum Information: {m.group(1).strip()}", flush=True)
    # the spoken 'is open' sentence, when hours are woven into prose
    for m in re.finditer(r"(?mi)\b([A-Z][^.\n]*?\bis open\b[^.\n]*\.)", text):
        print(f"  HOURS(spoken): {m.group(1).strip()}", flush=True)
    # Per-stop addresses
    for m in re.finditer(r"(?mi)^Address:\s*(.*)$", text):
        print(f"  ADDRESS: {m.group(1).strip()!r}", flush=True)
    # Stop titles
    for m in re.finditer(r"(?mi)^Stop\s+\d+:\s*(.+)$", text):
        print(f"  STOP TITLE: {m.group(1).strip()}", flush=True)
    # Garbage-hours probe: the exact 471 defect is a bare "HH–HH" with NO
    # colon/dot minutes anywhere in the Museum Information value (midnight-start
    # fragments like "00–18; 00–20"). A correct "10.00–18.00" / "13:00–18:00" has
    # minutes and must NOT be flagged.
    bad = []
    for m in re.finditer(r"(?mi)^Museum Information:\s*(.+)$", text):
        val = m.group(1)
        for seg in re.split(r"[;,.]\s*", val):
            seg = seg.strip()
            # a bare "HH-HH" segment with no colon/dot minute marker
            if re.fullmatch(r"\d{1,2}\s*[–-]\s*\d{1,2}", seg):
                bad.append(seg)
    if bad:
        print(f"  !! GARBAGE-HOURS PROBE FOUND: {bad}", flush=True)
    else:
        print("  garbage-hours probe: CLEAN", flush=True)


def _store_tour(location, text, n_stops, slug):
    try:
        conn = _conn()
        conn.autocommit = True
        name = f"LOCAL-625 {location.split(',')[0]} {int(time.time())}"
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
                 f"LOCAL-625 live fresh ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close()
        return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True)
        return None


def _run_one(location, stops, out_file, slug):
    print(f"\n=== generating: {location} ({stops} stops) ===", flush=True)
    t0 = time.time()
    try:
        text, _out_path, _coords = generate_tour_text(
            location, 'museum', out_file, stops, user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {location}: {e}", flush=True)
        return None
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        return None
    delivered = _tc.count_delivered_stops(text)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    print(f"[LOCAL-625 facts on spoken text] — {location}", flush=True)
    _report_facts(text)
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _c = dict(_LAST_GENERATION_COST or {})
        _tot = float(_c.get('tour_total_cost', _c.get('total_cost', 0.0)) or 0.0)
        print(f"[cost] tour_total=${_tot:.4f}", flush=True)
    except Exception:
        pass
    new_id = _store_tour(location, text, delivered, slug)
    if new_id:
        print(f"STORED audio_tours id = {new_id}  (is_test=true)", flush=True)
        print(f"LOCAL625_TOUR_ID={new_id}", flush=True)
    return new_id


print(f"[db] audio_tours row count BEFORE: {_row_count()}", flush=True)

ids = []
for location, stops, slug in VENUES:
    tid = _run_one(location, stops, f"/app/tours/LOCAL625_{slug}.txt", slug)
    if tid:
        ids.append(tid)

print(f"\n[db] audio_tours row count AFTER: {_row_count()}", flush=True)
print("=== LOCAL-625 run complete ===", flush=True)
print(f"LOCAL625_TOUR_IDS={','.join(str(i) for i in ids)}", flush=True)
