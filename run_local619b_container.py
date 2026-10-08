#!/usr/bin/env python3
"""run_local619b_container.py — LOCAL-619B live acceptance (ISOLATED container).

Runs TWO never-seen museums through the REAL generation path with the LOCAL-619B
branch code mounted over /app, 4 stops each, metered + hard-capped at $1.50
COMBINED (TEST_GEMINI_MAX_USD, all providers, via tests/live_run_meter.py):

    1. Städel Museum, Frankfurt, Germany            (4 stops)
    2. Musée des Beaux-Arts de Lille, Lille, France (4 stops)

For each museum it prints the DELIVERED THEMATIC CONCLUSION IN FULL (the one thing
this ticket is about) and checks the five D634 criteria on the delivered text:
  1. no stop list (at most one delivered title appears in the conclusion);
  2. no "From … to …";
  3. every factual noun in the conclusion appears in the stops (claim/G4);
  4. restaurant offer last;
  5. the stop count is correct when present.
It then stores the delivered tour_content in development-postgres-2-1
``audio_tours`` (is_test=true, creator_type='Test') so ``critique.sh <id>`` scores
the SAME spoken text. No DELETE; only additive is_test rows are written.

Usage (inside the isolated container):
    python3 run_local619b_container.py
"""
# [LOCAL-613] Meter + cap this isolated run (install BEFORE importing generators).
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-619B')
except Exception as _meter_err:
    print(f"[LOCAL-613] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # force FRESH tours
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.50')
os.environ['COST_HARD_LIMIT_USD'] = '1.50'        # ticket cap (combined)
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')

RUNS = [
    ('St\u00e4del Museum, Frankfurt, Germany', '/app/tours/LOCAL619B_STADEL.txt'),
    ('Mus\u00e9e des Beaux-Arts de Lille, Lille, France',
     '/app/tours/LOCAL619B_LILLE.txt'),
]
STOPS = 4

print("=== LOCAL-619B isolated live run (two museums, 4 stops each) ===",
      flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   combined cap: "
      f"${os.environ['COST_HARD_LIMIT_USD']}", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402
try:
    import claim_check as _cc  # noqa: E402
except Exception:
    _cc = None
try:
    import stop_pool_store as _sps  # noqa: E402
except Exception:
    _sps = None

_SPLICE_RE = re.compile(r"That['\u2019]s\s+\d+\s+stops?\s+[\u2014-]")
_COUNT_RE = re.compile(r"That['\u2019]s\s+(\d+)\s+stops?")
_THEMATIC_RE = re.compile(
    r"(?im)^(?:This tour|Across these stops|Across the stops|Taken together|"
    r"Together,? these|What connects|The works on this tour|"
    r"The stops on this tour|On this tour)\b")
_FROM_TO_RE = re.compile(r"\bFrom\s+.+?\s+to\s+.+?,", re.IGNORECASE)
_RESTAURANT_RE = re.compile(r"we can build you a restaurant tour", re.IGNORECASE)


def _delivered_titles(text):
    out = []
    for m in re.finditer(r'(?m)^Stop\s+\d+:\s*(.+?)\s*$', text):
        t = m.group(1).strip()
        t = re.sub(r',\s*\d{3,4}\s*$', '', t)
        t = re.sub(r'\s+by\s+.+$', '', t, flags=re.IGNORECASE)
        if t:
            out.append(t.strip())
    return out


def _conclusion_only(text):
    body = re.split(r'(?mi)^\s*Sources:', text)[0]
    m = _THEMATIC_RE.search(body)
    return body[m.start():].strip() if m else ""


def _store_tour(location, text, n_stops):
    try:
        import psycopg2
    except Exception as e:
        print(f"  [store] psycopg2 unavailable: {e}", flush=True)
        return None
    dburl = os.environ.get('DATABASE_URL')
    try:
        conn = psycopg2.connect(dburl) if dburl else psycopg2.connect(
            host=os.environ.get('DB_HOST', 'development-postgres-2-1'),
            port=os.environ.get('DB_PORT', '5432'),
            dbname=os.environ.get('DB_NAME', 'audiotours'),
            user=os.environ.get('DB_USER', 'admin'),
            password=os.environ.get('DB_PASSWORD', 'password123'))
        conn.autocommit = True
        name = f"LOCAL-619B {location.split(',')[0]} {int(time.time())}"
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
                (name, location, STOPS, text, n_stops,
                 'LOCAL-619B isolated live run (critique seed)'))
            new_id = cur.fetchone()[0]
        conn.close()
        return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True)
        return None


def _report(location, out_file, text, elapsed):
    print(f"\n################ {location} ################", flush=True)
    try:
        from generate_tour_text import (_LAST_GENERATION_COST, _LAST_DELIVERY_PATH)
        _cost = dict(_LAST_GENERATION_COST or {})
        _path = _LAST_DELIVERY_PATH
    except Exception:
        _cost, _path = {}, '?'

    if not text:
        print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s (path={_path})",
              flush=True)
        return None

    titles = _delivered_titles(text)
    delivered = _tc.count_delivered_stops(text)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {len(titles)} stops, "
          f"path={_path}, wall {elapsed:.1f}s", flush=True)
    for t in titles:
        print(f"   Stop: {t[:100]}", flush=True)

    concl = _conclusion_only(text)

    # Criterion 1 — no stop list (<=1 title in the conclusion).
    named = sum(1 for t in titles if len(t) >= 4
                and re.search(r'\b' + re.escape(t) + r'\b', concl, re.IGNORECASE))
    # Criterion 2 — no From…to.
    no_from_to = _FROM_TO_RE.search(concl) is None
    # Criterion 3 — every factual noun grounded (claim/G4).
    bad_claims = None
    if _cc is not None and _sps is not None:
        try:
            stops = _sps.parse_delivered_stops(_tc.normalise_stop_headers(text))
            passages = [(s.get('narration') or '').strip() for s in stops
                        if (s.get('narration') or '').strip()]
            checkable = _COUNT_RE.sub("", _RESTAURANT_RE.sub("", concl))
            res = _cc.check_paragraph(checkable, stop_title="",
                                      venue_name=location.split(',')[0],
                                      passages=passages, other_stop_passages=None)
            vc = res.get('verdict_counts', {}) or {}
            bad_claims = int(vc.get('unsupported', 0)) + int(vc.get('contradicted', 0))
        except Exception as e:
            print(f"  [claim/G4] check skipped: {e}", flush=True)
    # Criterion 4 — restaurant last.
    body = re.split(r'(?mi)^\s*Sources:', text)[0].strip()
    last_line = [ln for ln in body.splitlines() if ln.strip()]
    rest_last = bool(last_line and _RESTAURANT_RE.search(last_line[-1]))
    # Criterion 5 — count correct when present.
    m_cnt = _COUNT_RE.search(text)
    count_ok = (m_cnt is None) or (int(m_cnt.group(1)) == delivered)

    print(f"\n[LOCAL-619B D634 criteria]", flush=True)
    print(f"  1 no stop list (<=1 title)   : {named <= 1}  (titles named={named})",
          flush=True)
    print(f"  2 no 'From … to …'           : {no_from_to}", flush=True)
    print(f"  3 factual nouns grounded     : "
          f"{'PASS' if bad_claims == 0 else ('n/a' if bad_claims is None else 'FAIL')}"
          f"  (unsupported/contradicted={bad_claims})", flush=True)
    print(f"  4 restaurant offer last      : {rest_last}", flush=True)
    print(f"  5 count correct when present : {count_ok}  "
          f"(stated={m_cnt.group(1) if m_cnt else 'none'}, delivered={delivered})",
          flush=True)
    print(f"  (no legacy splice            : {_SPLICE_RE.search(text) is None})",
          flush=True)
    print(f"  (one conclusion              : {len(_THEMATIC_RE.findall(text)) == 1})",
          flush=True)

    _tour_total = float(_cost.get('tour_total_cost',
                                  _cost.get('total_cost', 0.0)) or 0.0)
    print(f"[cost] tour_total=${_tour_total:.4f}", flush=True)

    print(f"\n---------------- CONCLUSION (in full) — {location} ----------------",
          flush=True)
    print(concl if concl else "(no conclusion found)", flush=True)

    new_id = _store_tour(location, text, len(titles))
    print(f"\nOUT: {out_file}", flush=True)
    if new_id:
        print(f"STORED audio_tours id = {new_id}  (is_test=true)", flush=True)
        print(f"LOCAL619B_TOUR_ID={new_id}", flush=True)
    return new_id


ids = []
for location, out in RUNS:
    print(f"\n=== generating: {location} ({STOPS} stops) ===", flush=True)
    t0 = time.time()
    try:
        text, out_file, _coords = generate_tour_text(location, 'museum', out, STOPS)
    except Exception as _run_err:
        print(f"RUN ERROR for {location}: {_run_err}", flush=True)
        text, out_file = None, out
    _id = _report(location, out_file, text, time.time() - t0)
    if _id:
        ids.append(_id)

print("\n=== LOCAL-619B run complete ===", flush=True)
print(f"LOCAL619B_TOUR_IDS={','.join(str(i) for i in ids)}", flush=True)
