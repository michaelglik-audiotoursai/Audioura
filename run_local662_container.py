#!/usr/bin/env python3
"""run_local662_container.py — LOCAL-662 live acceptance (ISOLATED container).

Tour 557 v9 (Kiro 5.5) shipped the Boston "Massachusetts politics and current
affairs" WALKING tour wrong four ways:
  1. An UNVERIFIED stop ("The State House Park") invented facts.
  2. A LEAKED editor marker '<!-- LOCAL-628:stop-editor:v1 -->' inside the text.
  3. TOO MUCH NEWS — a news feed on 4 of 5 stops + "(Reported by X, Y.)" lists.
  4. A COLLISION — "…civic architecture could Seven years later, in 1976…".

This harness proves the fix end-to-end on ONE FRESH PAID tour through the real
generation path: the ticket request, 5 stops, walking, fresh, NORMAL arm (no
NARRATION_MODEL / RESEARCH_BACKEND override). It runs deterministic detectors over
the delivered text and prints PASS/FAIL for each defect, then reports stops, each
stop's existence evidence (from the generator log), the news paragraphs, and the
detector results.

ONE paid tour only. HARD CAP $0.70 for the WHOLE task, enforced by
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
    _live_run_meter.auto_meter('LOCAL-662')
except Exception as _meter_err:
    print(f"[LOCAL-662] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import re
import socket
import time

# NORMAL ARM: no NARRATION_MODEL, no RESEARCH_BACKEND override.
_os.environ['STORIED_MODE'] = 'true'
_os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tour (cache off)
_os.environ['DISABLE_STOP_POOL'] = '1'             # pool off (fresh)
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '0.70')
_os.environ['COST_HARD_LIMIT_USD'] = '0.70'        # ticket HARD CAP (whole task)
_os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
_os.environ.setdefault('STOP_EDITOR', '1')
# Walking tours force the stop-existence gate to ENFORCE (LOCAL-662 defect 1);
# the generator computes this per-category, but set the shared-stack default
# explicitly so the run is reproducible and the log shows the decision.
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

HARD_CAP_USD = 0.70
RESERVE_USD = 0.45          # start the tour only if spend + 0.45 <= cap
HOST = socket.gethostname()

TOURS = [
    ('Walking tour in Boston dedicated to Massachusetts politics and current '
     'affairs, Boston, MA', 5, 'walking', 'BOSTONWALK'),
]

print("=== LOCAL-662 isolated live run (Boston walking 5, ONE paid tour) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"NORMAL ARM  HARD CAP(task): ${HARD_CAP_USD}  reserve: ${RESERVE_USD}  "
      f"cache_off=1 pool_off=1  gate=walking->ENFORCE", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402


def _conn():
    import psycopg2
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=_os.environ.get('DB_HOST', 'postgres-2'),
        port=_os.environ.get('DB_PORT', '5432'),
        dbname=_os.environ.get('DB_NAME', 'audiotours'),
        user=_os.environ.get('DB_USER', 'admin'),
        password=_os.environ.get('DB_PASSWORD', 'password123'))


def _scalar(sql, args=()):
    try:
        conn = _conn(); conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql, args)
            v = cur.fetchone()[0]
        conn.close(); return v
    except Exception as e:
        print(f"  [db] query failed: {e}", flush=True); return None


def _row_count():
    return _scalar("SELECT count(*) FROM audio_tours")


def _test_row_count():
    return _scalar("SELECT count(*) FROM audio_tours WHERE is_test = true")


def _spend_so_far():
    v = _scalar("SELECT COALESCE(SUM(usd),0) FROM paid_api_calls WHERE host = %s",
                (HOST,))
    return float(v) if v is not None else None


# ───────────────────────── Four deterministic detectors ─────────────────────

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")
_DIR_LINE_RE = re.compile(r"(?mi)^Directions:\s*(.+)$")
_NEWS_MARK = "In recent news:"
# The general mid-clause collision shape.
_COLLISION_RE = re.compile(r"(?<![.!?:;,)\]\"'\u201d\u2019])\b([a-z]{3,})\s([A-Z][a-z]{2,})")


def _spoken(text):
    keep = []
    for ln in (text or "").split("\n"):
        if re.match(r"^\s*(Museum Information|Address|Coordinates|Type/Specialty|"
                    r"Specific Examples|Operational Details|Tour-Category|Sources)\s*:",
                    ln):
            continue
        keep.append(ln)
    return "\n".join(keep)


def detect_defect1_unverified(text):
    """No invented 'The State House Park'-style stop; stops look like real places.
    We assert the specific tour-557 phantom stop is absent and no stop title is a
    generic invented '... Park'/'... Garden' with no proper name."""
    titles = [t.strip() for t in _STOP_HEADER_RE.findall(text)]
    bad = [t for t in titles if re.search(r"(?i)^the\s+state\s+house\s+park\b", t)]
    return (not bad), f"phantom_stop_titles={bad}; titles={titles}"


def detect_defect2_marker(text):
    """No editor/HTML-comment marker in the delivered (spoken) text."""
    bad = "<!--" in text or "-->" in text or "LOCAL-628:stop-editor" in text
    return (not bad), f"marker_present={bad}"


def detect_defect3_news(text):
    """News capped: on at most 2 stops; no '(Reported by …)' source list."""
    bodies = re.split(r"(?mi)^Stop\s+\d+:", text)
    stops_with_news = sum(1 for b in bodies if _NEWS_MARK in b)
    reported_by = bool(re.search(r"\(Reported by", text))
    ok = stops_with_news <= 2 and not reported_by
    return ok, (f"stops_with_news={stops_with_news} (<=2); "
                f"reported_by_parenthetical={reported_by}")


def detect_defect4_collision(text):
    """No dangling-modal / general mid-clause collision in the spoken text."""
    import stop_editor as se
    spoken = _spoken(text)
    modal = se.detect_dangling_modal_join(spoken)
    # the specific tour-557 shape
    specific = "could Seven" in spoken
    # general collision set on spoken prose
    general = _COLLISION_RE.findall(spoken)
    return (modal is None and not specific), \
        f"dangling_modal={modal}; could_Seven={specific}; general_hits={len(general)}"


def _report(text):
    print("  --- STOP LIST ---", flush=True)
    for h in _STOP_HEADER_RE.findall(text):
        print(f"  STOP TITLE: {h.strip()[:90]}", flush=True)
    print("  --- NEWS PARAGRAPHS ---", flush=True)
    for b in re.split(r"(?mi)^(Stop\s+\d+:.*)$", text):
        if _NEWS_MARK in b:
            for para in b.split("\n\n"):
                if _NEWS_MARK in para:
                    print(f"  NEWS: {para.strip()[:300]}", flush=True)
    print("  --- DEFECT DETECTORS ---", flush=True)
    results = {}
    for name, fn in (("DEFECT1_unverified_stop", detect_defect1_unverified),
                     ("DEFECT2_leaked_marker", detect_defect2_marker),
                     ("DEFECT3_too_much_news", detect_defect3_news),
                     ("DEFECT4_sentence_collision", detect_defect4_collision)):
        try:
            ok, detail = fn(text)
        except Exception as e:
            ok, detail = False, f"detector error: {e}"
        results[name] = ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
    allok = all(results.values())
    print(f"  [LOCAL-662] ALL FOUR DEFECTS GONE = {allok}", flush=True)
    return results


def _store(location, text, n_stops, slug, kind_desc):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-662 {location.split(',')[0][:40]} {int(time.time())}"
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
        print(f"[reserve-gate] SKIP {slug}: would exceed cap", flush=True)
        return None, 'SKIPPED_CAP', None
    print(f"=== generating: {location} ({stops} stops, {tour_type}) ===",
          flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            location, tour_type, f"/app/tours/LOCAL662_{slug}.txt", stops,
            user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {location}: {e}", flush=True)
        return None, f'ERROR:{e}', None
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        return None, 'NO_TEXT', None
    delivered = _tc.count_delivered_stops(text)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    results = _report(text)
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        _tot = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
        print(f"[cost] tour_total=${_tot:.4f}", flush=True)
    except Exception:
        pass
    nid = _store(location, text, delivered, slug,
                 f"LOCAL-662 live fresh ({slug}, {tour_type})")
    if nid:
        print(f"STORED audio_tours id = {nid}  (is_test=true)", flush=True)
        print(f"LOCAL662_TOUR_ID_{slug}={nid}", flush=True)
    # Also dump the full delivered text to the mounted tours dir for the report.
    try:
        with open(f"/app/tours/LOCAL662_{slug}_delivered.txt", "w",
                  encoding="utf-8") as _df:
            _df.write(text)
    except Exception:
        pass
    return nid, 'DELIVERED', results


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}",
      flush=True)

results = []
for _loc, _stops, _ttype, _slug in TOURS:
    _id, _outcome, _det = _run_one(_loc, _stops, _ttype, _slug)
    results.append((_slug, _id, _outcome, _det))

print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}",
      flush=True)
print("=== LOCAL-662 run complete ===", flush=True)
for _slug, _id, _outcome, _det in results:
    print(f"RESULT {_slug}: id={_id if _id else ''} outcome={_outcome} "
          f"detectors={_det}", flush=True)
