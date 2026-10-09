#!/usr/bin/env python3
"""run_local659_container.py — LOCAL-659 live acceptance (ISOLATED container).

LOCAL-659 round 3. Tour 557 v5 shipped news with three/four wrongs: invented
precision ("On September 9, 2026 … led a 9/11 ceremony" from a Serper "1 month
ago"), month-old items beating this week's news, a theme query that returned 0,
and an off-theme cultural event (Athenaeum open house). This harness proves the
fix end-to-end on ONE FRESH PAID tour through the real generation path:

  WALKING (the ticket tour): "Walking tour in Boston dedicated to Massachusetts
  politics and current affairs, Boston, MA" — 5 stops. The [LOCAL-655] log must
  show:
    * SHORT theme queries issued ("Massachusetts politics", "Massachusetts
      governor", … "Boston city council"), each returning items (Defect 3);
    * each ACCEPT with its stop + reason + the DATE PRECISION/SOURCE: exact (from
      article meta) vs approximate (relative Serper date) (Defects 1 & 2);
    * cultural events (open house / festival / concert) in the REJECT list
      (Defect 4);
    * the delivered "In recent news:" paragraphs — a relative-only item stated
      APPROXIMATELY ("last month", no invented day), an exact item with its day;
    * newest news leading (this week's items ahead of month-old ones).

ONE paid tour only. HARD CAP $1.00 for the WHOLE task, enforced by
tests/live_run_meter.py plus a RESERVE GATE before the tour. The delivered SPOKEN
text is stored as ONE additive is_test row. is_test rows are the ONLY rows
written. No DELETE.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-659')
except Exception as _meter_err:
    print(f"[LOCAL-659] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import socket
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tour (cache off)
os.environ['DISABLE_STOP_POOL'] = '1'             # pool off (fresh news)
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.00')
os.environ['COST_HARD_LIMIT_USD'] = '1.00'        # ticket HARD CAP (whole task)
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
os.environ.setdefault('STOP_EDITOR', '1')
os.environ.setdefault('STOP_EDITOR_ENABLED', '1')

HARD_CAP_USD = 1.00
RESERVE_USD = 0.55          # start the tour only if spend + 0.55 <= cap
HOST = socket.gethostname()

# (location, stops, tour_type, slug) — ONE paid tour.
TOURS = [
    ('Walking tour in Boston dedicated to Massachusetts politics and current '
     'affairs, Boston, MA', 5, 'walking', 'BOSTONWALK'),
]

print("=== LOCAL-659 isolated live run (Boston current-affairs 5, ONE paid tour) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   HARD CAP(task): "
      f"${HARD_CAP_USD}  reserve: ${RESERVE_USD}  cache_off=1 pool_off=1",
      flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402
import current_affairs_news as _ca  # noqa: E402


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
    print("  --- STOP LIST ---", flush=True)
    headers = re.findall(r"(?mi)^Stop\s+\d+:\s*(.+)$", text)
    for h in headers:
        print(f"  STOP TITLE: {h.strip()[:90]}", flush=True)
    n_news = text.count(_ca._NEWS_MARK)
    has_note = _ca.HONEST_NOTE in text
    print(f"  [LOCAL-659] stops with 'In recent news:' = {n_news}", flush=True)
    print(f"  [LOCAL-659] honest note present = {has_note}", flush=True)
    print(f"  [LOCAL-659] '(Reported by' parenthetical count = "
          f"{text.count('(Reported by')}", flush=True)
    # Show each injected news paragraph verbatim.
    for m in re.finditer(re.escape(_ca._NEWS_MARK) + r"(.+?)(?:\n\n|\Z)", text, re.S):
        print(f"  [LOCAL-659] NEWS ITEM: {m.group(0).strip()[:600]}", flush=True)
    # Defect 1 guard: a bare "September 9, 2026"-style day that originated from a
    # relative Serper date would be a regression. We can only flag day-precise
    # strings here for the human to cross-check against the ACCEPT date sources.
    days = re.findall(r"(?:January|February|March|April|May|June|July|August|"
                      r"September|October|November|December)\s+\d{1,2},\s+20\d{2}",
                      " ".join(re.findall(re.escape(_ca._NEWS_MARK) + r".+?(?:\n\n|\Z)",
                                          text, re.S)))
    print(f"  [LOCAL-659] explicit day-dates inside news paragraphs: {days}",
          flush=True)
    print(f"  [LOCAL-659] WALKING RESULT: news_items={n_news} honest_note={has_note} "
          f"(at least one of the two MUST be present — the search DID run)",
          flush=True)


def _store(location, text, n_stops, slug, kind_desc):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-659 {location.split(',')[0][:40]} {int(time.time())}"
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
    print(f"[LOCAL-659] wants_current_affairs(request)="
          f"{_ca.wants_current_affairs(location)}", flush=True)
    print(f"[LOCAL-659] theme queries={_ca.derive_theme_queries(location)}",
          flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            location, tour_type, f"/app/tours/LOCAL659_{slug}.txt", stops,
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
    _report_walking(text)
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        _tot = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
        print(f"[cost] tour_total=${_tot:.4f}", flush=True)
    except Exception:
        pass
    nid = _store(location, text, delivered, slug,
                 f"LOCAL-659 live fresh ({slug}, {tour_type})")
    if nid:
        print(f"STORED audio_tours id = {nid}  (is_test=true)", flush=True)
        print(f"LOCAL659_TOUR_ID_{slug}={nid}", flush=True)
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
print("=== LOCAL-659 run complete ===", flush=True)
for _slug, _id, _outcome in results:
    print(f"RESULT {_slug}: id={_id if _id else ''} outcome={_outcome}",
          flush=True)
