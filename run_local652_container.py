#!/usr/bin/env python3
"""run_local652_container.py — LOCAL-652 live test (ISOLATED container).

Two FRESH tours through the REAL generation path, cache + pool OFF:

  1. The National Gallery, London — 3 stops  (the ticket's defect venue)
  2. The Courtauld Gallery, London — 3 stops  (a valid-thread control)

For each tour we report: delivered stop count, wall time, the THREAD the
discoverer chose (SQ-S6b mode + thread names, from the captured log), the
LOCAL-652 phantom-thread detectors (no foreign work/artist in the conclusion;
no cross-stop callback to a work not on the tour; no later-stop work title in
the Stop-1 opening), the tour's own cost, and spend from paid_api_calls.

Each delivered SPOKEN text is stored as ONE additive is_test row for
critique.sh / detectors.py. is_test rows are the ONLY rows written. No DELETE.

HARD CAP $2.00 (ticket), enforced by tests/live_run_meter.py across ALL
providers, plus a RESERVE GATE before each tour. Row counts are printed before
and after.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-652')
except Exception as _meter_err:
    print(f"[LOCAL-652] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import io
import os
import re
import socket
import time
import contextlib

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['DISABLE_STOP_POOL'] = '1'
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '2.00')
os.environ['COST_HARD_LIMIT_USD'] = '2.00'
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')

HARD_CAP_USD = 2.00
RESERVE_USD = 0.60
HOST = socket.gethostname()

TOURS = [
    ('The National Gallery, London, United Kingdom', 3, 'museum', 'NG_LONDON'),
    ('The Courtauld Gallery, London, United Kingdom', 3, 'museum', 'COURTAULD'),
]

print("=== LOCAL-652 isolated live test (NG London 3 + Courtauld 3, fresh) ===",
      flush=True)
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
        host=os.environ.get('DB_HOST', 'development-postgres-2-1'),
        port=os.environ.get('DB_PORT', '5432'),
        dbname=os.environ.get('DB_NAME', 'audiotours'),
        user=os.environ.get('DB_USER', 'admin'),
        password=os.environ.get('DB_PASSWORD', 'password123'))


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


def _thread_from_log(log_text):
    """Extract the SQ-S6b thread discovery outcome + any LOCAL-652 rejections."""
    mode = "?"
    threads = []
    rejected = []
    for line in log_text.splitlines():
        m = re.search(r"\[SQ-S6b\] Thread discovery: mode=(\w+), threads=(\d+)", line)
        if m:
            mode = f"{m.group(1)} (threads={m.group(2)})"
        m = re.search(r"\[LOCAL-652\] Theme '([^']+)' rejected", line)
        if m:
            rejected.append(m.group(1))
        m = re.search(r"\[SQ-S6b\] Thread discovery:.*", line)
    for line in log_text.splitlines():
        m = re.match(r"\s*→ '([^']+)': coverage=\d+%", line)
        if m:
            threads.append(m.group(1))
    return {"mode": mode, "threads": threads, "rejected": rejected}


def _foreign_entity_check(text):
    """LOCAL-652 phantom-thread detectors on the delivered text.

    Builds the delivered grounding from the Stop headers (title + 'by Artist')
    and flags any named work/artist entity in the CONCLUSION that is on no
    delivered stop, plus any cross-stop callback / opening-leak signatures."""
    import tour_conclusion as tcm
    # Parse delivered stop titles+artists for grounding.
    stops = []
    for m in re.finditer(r"(?mi)^Stop\s+\d+:\s*(.+)$", text):
        raw = m.group(1).strip()
        artist = ""
        am = re.search(r"\bby\s+(.+?)(?:,\s*\d{3,4})?\s*$", raw, re.IGNORECASE)
        if am:
            artist = am.group(1)
        title = re.sub(r"\s+by\s+.+$", "", raw, flags=re.IGNORECASE)
        title = re.sub(r",\s*\d{3,4}\s*$", "", title)
        stops.append({"title": title, "artist": artist})
    grounding = tcm._delivered_conclusion_grounding(stops)

    # Conclusion region: after the last Stop header, before Sources.
    headers = list(re.finditer(r"(?mi)^Stop\s+\d+:", text))
    tail = text[headers[-1].end():] if headers else text
    tail = re.split(r"(?mi)^Sources", tail)[0]
    foreign_concl = tcm._conclusion_names_foreign_entity(tail, grounding)

    # Opening region: before the second Stop header (Stop-1 opening + Museum Info).
    opening = text[:headers[1].start()] if len(headers) >= 2 else text
    # A later stop's title appearing in the Stop-1 opening is a leak.
    later_titles = [s["title"] for s in stops[1:] if s["title"]]
    opening_leak = [t for t in later_titles
                    if len(t) >= 5 and re.search(r"\b" + re.escape(t) + r"\b", opening, re.I)]

    return {"delivered_grounding_sample": sorted(grounding)[:12],
            "conclusion_foreign_entities": foreign_concl,
            "opening_leak_titles": opening_leak}


def _detectors(text):
    headers = re.findall(r"(?mi)^Stop\s+\d+:\s*(.+)$", text)
    delivered = _tc.count_delivered_stops(text)
    m = re.search(r"That['\u2019]s\s+(\d+)\s+stops?", text)
    stated = m.group(1) if m else "?"
    fe = _foreign_entity_check(text)
    return {"headers": [h.strip()[:70] for h in headers],
            "delivered": delivered, "stated": stated, **fe}


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-652 {location.split(',')[0][:40]} {slug} {int(time.time())}"
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
                 f"LOCAL-652 live test ({slug})"))
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
        return (slug, None, 'SKIPPED_CAP', None)

    print(f"=== generating: {location} ({stops} stops) [{slug}] ===", flush=True)
    t0 = time.time()
    _buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(_buf):
            text, _p, _c = generate_tour_text(
                location, tour_type, f"/app/tours/LOCAL652_{slug}.txt", stops,
                user_id=None)
    except Exception as e:
        _log = _buf.getvalue()
        print(_log, flush=True)
        print(f"RUN ERROR for {slug}: {e}", flush=True)
        return (slug, None, f'ERROR:{e}', None)
    _log = _buf.getvalue()
    # Echo the captured generation log so the thread/detector lines are visible.
    print(_log, flush=True)
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME {slug}: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        return (slug, None, 'NO_TEXT', None)

    thread = _thread_from_log(_log)
    d = _detectors(text)
    print(f"\nOUTCOME {slug}: DELIVERED {len(text)} chars, {d['delivered']} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    for h in d['headers']:
        print(f"  STOP TITLE: {h}", flush=True)
    print(f"  [SQ-S6b thread] mode={thread['mode']} threads={thread['threads']}",
          flush=True)
    print(f"  [LOCAL-652] rejected phantom threads: {thread['rejected']}", flush=True)
    print(f"  [LOCAL-652 detector] conclusion_foreign_entities="
          f"{d['conclusion_foreign_entities']}", flush=True)
    print(f"  [LOCAL-652 detector] opening_leak_titles={d['opening_leak_titles']}",
          flush=True)
    print(f"  [LOCAL-652 detector] delivered_grounding_sample="
          f"{d['delivered_grounding_sample']}", flush=True)
    _verdict = ("PASS" if not d['conclusion_foreign_entities']
                and not d['opening_leak_titles'] else "FAIL")
    print(f"  [LOCAL-652 VERDICT] {slug}: {_verdict}", flush=True)
    tour_cost = None
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        tour_cost = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
        print(f"  [cost] tour_total=${tour_cost:.4f}", flush=True)
    except Exception:
        pass
    nid = _store(location, text, d['delivered'], slug)
    if nid:
        print(f"  STORED audio_tours id = {nid}  (is_test=true)", flush=True)
        print(f"  LOCAL652_TOUR_ID_{slug}={nid}", flush=True)
    return (slug, nid, 'DELIVERED', {"wall_s": round(elapsed, 1),
                                     "tour_cost": tour_cost,
                                     "verdict": _verdict, **d})


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}",
      flush=True)

results = []
for _loc, _stops, _ttype, _slug in TOURS:
    results.append(_run_one(_loc, _stops, _ttype, _slug))

print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}",
      flush=True)
print("=== LOCAL-652 run complete ===", flush=True)
for _slug, _id, _outcome, _m in results:
    _extra = ""
    if _m:
        _extra = (f" wall={_m['wall_s']}s cost=${_m['tour_cost']} "
                  f"stops={_m['delivered']} verdict={_m['verdict']} "
                  f"concl_foreign={_m['conclusion_foreign_entities']} "
                  f"opening_leak={_m['opening_leak_titles']}")
    print(f"RESULT {_slug}: id={_id if _id else ''} outcome={_outcome}{_extra}",
          flush=True)
