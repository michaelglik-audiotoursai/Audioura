#!/usr/bin/env python3
"""run_local624_container.py — LOCAL-624 live acceptance (ISOLATED container).

Runs TWO venues that have NEVER been generated before (verified against
``audio_tours`` by name) through the REAL generation path with the LOCAL-624
branch code baked into the image, metered + hard-capped at $1.00 COMBINED (all
providers, via tests/live_run_meter.py):

    1. Wallraf-Richartz Museum, Cologne, Germany   (2 stops)
    2. Nationalmuseum, Stockholm, Sweden           (2 stops)

Each is a FRESH museum tour (tour cache OFF). For every delivered tour it checks
the LOCAL-624 defect classes on the SPOKEN text:
    A. appositive type-mismatch — a PERSON apposed with a WORK description
    B. truncated clause / dangling relative ("that characterized.")
    C. empty interpolated field ("(État / )", ", ,")
and stores it as an additive is_test row in ``audio_tours`` (creator_type=
'Test') so ``critique.sh <id>`` scores the SAME spoken text. The is_test rows
are the ONLY rows written. No DELETE.

Usage (inside the isolated container):
    python3 run_local624_container.py
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-624')
except Exception as _meter_err:
    print(f"[meter] live_run_meter unavailable ({_meter_err}): "
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
    ('Wallraf-Richartz Museum, Cologne, Germany', 2, 'WALLRAF'),
    ('Nationalmuseum, Stockholm, Sweden', 2, 'NATIONALMUSEUM'),
]

print("=== LOCAL-624 isolated live run (two FRESH museums, 2 stops each) ===",
      flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   combined cap: "
      f"${os.environ['COST_HARD_LIMIT_USD']}", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402
import unglossed_reference_gate as _urg  # noqa: E402


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


# ── the LOCAL-624 splice-class checks, run on the delivered SPOKEN text ───────
_WORK_NOUN = (r'(?:painting|canvas|oil[- ]on[- ]canvas|sculpture|statue|bronze|'
              r'engraving|etching|lithograph|woodcut|fresco|watercolou?r|'
              r'altarpiece|triptych|diptych|portrait|version\s+of|copy\s+of)')
_NAME = r'(?:[A-Z][a-zà-ÿ]+\.?)(?:\s+[A-Z][a-zà-ÿ.]+){0,3}'
_APPOS = re.compile(r'\b(' + _NAME + r'),\s+((?:a|an|the)\s+[\w\s\'’-]{0,60})(?=[,.])')
_EMPTY_FIELD = re.compile(r'\(\s*[^)]*/\s*\)|,\s*,|,\s*\.')
_FINITE = re.compile(r'\b(?:is|are|was|were|has|have|had|found|moved|remains?|'
                     r'stands?|became|came|went|hangs?|underwent|measures?|'
                     r'dates?|features?|includes?|portrays?)\b', re.I)
_NOT_PERSON = {'throughout', 'during', 'in', 'on', 'at', 'with', 'from', 'by',
               'after', 'before', 'since', 'around', 'the', 'this', 'that',
               'interestingly', 'notably', 'however', 'as', 'over', 'while',
               'when', 'where', 'standing', 'painted', 'created', 'originally',
               'eventually', 'ultimately'}


def _defect_report(text):
    out = {'A_appositive_type_mismatch': [], 'B_truncated_clause': [],
           'C_empty_field': []}
    for s in _urg._split_sentences(text):
        s = s.strip()
        if not s:
            continue
        for m in _APPOS.finditer(s):
            name, apps = m.group(1), m.group(2)
            if name.split()[0].lower().rstrip('.') in _NOT_PERSON:
                continue
            if not _urg._gloss_describes_a_work(apps):
                continue
            if _FINITE.search(apps):
                continue
            out['A_appositive_type_mismatch'].append(s[:140])
            break
        if _urg._ends_in_transitive_verb_without_object(s):
            out['B_truncated_clause'].append(s[:140])
        if _EMPTY_FIELD.search(s):
            out['C_empty_field'].append(s[:140])
    return out


def _store_tour(location, text, n_stops, slug):
    try:
        conn = _conn()
        conn.autocommit = True
        name = f"LOCAL-624 {location.split(',')[0]} {int(time.time())}"
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
                 f"LOCAL-624 live fresh ({slug})"))
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
    print(f"[LOCAL-624 splice checks on spoken text] — {location}", flush=True)
    rep = _defect_report(text)
    for label, hits in rep.items():
        status = "CLEAN" if not hits else f"FOUND {hits}"
        print(f"  {label}: {status}", flush=True)
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
        print(f"LOCAL624_TOUR_ID={new_id}", flush=True)
    return new_id


print(f"[db] audio_tours row count BEFORE: {_row_count()}", flush=True)

ids = []
for location, stops, slug in VENUES:
    tid = _run_one(location, stops, f"/app/tours/LOCAL624_{slug}.txt", slug)
    if tid:
        ids.append(tid)

print(f"\n[db] audio_tours row count AFTER: {_row_count()}", flush=True)
print("=== LOCAL-624 run complete ===", flush=True)
print(f"LOCAL624_TOUR_IDS={','.join(str(i) for i in ids)}", flush=True)
