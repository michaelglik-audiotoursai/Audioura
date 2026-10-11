#!/usr/bin/env python3
"""run_local668_container.py — LOCAL-668 live acceptance (ISOLATED container).

Ticket: "Ho Chi Minh City Museum of Fine Arts, Vietnam", 5 stops, museum, FRESH.
Two arms, side by side, in ONE disposable container:

  * NORMAL arm — no NARRATION_MODEL / RESEARCH_BACKEND override. The LOCAL-668
    fix must stop BLOCKER4b from rejecting the contained tour: a tour is
    DELIVERED (not "no tour"), with ONE venue address across the stops.
  * CHEAP arm — NARRATION_MODEL=gpt-4.1-mini, RESEARCH_BACKEND=serper. The
    area-stop research must not pull in another museum: NO "Saint Louis" /
    "Honolulu" in the delivered text; the lacquer-layering technique told once.

Reports, per arm: delivered stops, Sources lines, the LOCAL-668 detectors, the
thin-verify verification-query count (cost cap), $ and seconds.

HARD CAP $1.40 for the WHOLE TASK (both arms), enforced by tests/live_run_meter
plus a RESERVE GATE before each arm. Rows: additive is_test only. No DELETE.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-668')
except Exception as _meter_err:
    print(f"[LOCAL-668] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import re
import socket
import time

_os.environ['STORIED_MODE'] = 'true'
_os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tour (cache off)
_os.environ['DISABLE_STOP_POOL'] = '1'             # pool off (fresh)
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.40')
_os.environ['COST_HARD_LIMIT_USD'] = '1.40'        # ticket HARD CAP (whole task)
_os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

HARD_CAP_USD = 1.40
RESERVE_USD = 0.60          # start an arm only if spend + 0.60 <= cap
HOST = socket.gethostname()

LOCATION = 'Ho Chi Minh City Museum of Fine Arts, Vietnam'
STOPS = 5

print("=== LOCAL-668 isolated live run (HCMC museum 5, normal + cheap) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  reserve: ${RESERVE_USD}  "
      f"cache_off=1 pool_off=1", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402


def _conn():
    import psycopg2
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=_os.environ.get('DB_HOST', 'development-postgres-2-1'),
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


# ───────────────────────── LOCAL-668 detectors ──────────────────────────────

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")
_ADDR_RE = re.compile(r"(?mi)^Address:\s*(.+)$")
_SOURCES_RE = re.compile(r"(?mi)^Sources?:\s*(.+)$")
_FOREIGN = re.compile(r"(?i)\b(saint\s+louis|honolulu|guston|holbein|pippin)\b")


def _titles(text):
    return [t.strip() for t in _STOP_HEADER_RE.findall(text)]


def detect_delivered(text):
    n = _tc.count_delivered_stops(text)
    return (n >= 1), f"delivered_stops={n}"


def detect_single_address(text):
    """BLOCKER4b target: a contained tour has 1-2 addresses."""
    addrs = [a.strip().lower()[:30] for a in _ADDR_RE.findall(text) if a.strip()]
    uniq = set(addrs)
    return (len(uniq) <= 2), f"unique_addresses={len(uniq)} :: {sorted(uniq)[:3]}"


def detect_no_foreign_museum(text):
    """LOCAL-668 #3: no other museum / its artists leaked into the text."""
    hits = sorted(set(m.group(0) for m in _FOREIGN.finditer(text)))
    return (not hits), f"foreign_mentions={hits}"


def detect_lacquer_told_once(text):
    """LOCAL-668 #4: the lacquer-layering technique is explained at most once."""
    sents = re.split(r"(?<=[.!?])\s+", text)
    tech = [s for s in sents
            if re.search(r"(?i)lacquer", s)
            and re.search(r"(?i)\b(layer|layered|layers|coat|coats|sanded|polished|burnish)\b", s)]
    return (len(tech) <= 1), f"lacquer_technique_sentences={len(tech)}"


def _report(text):
    titles = _titles(text)
    print("  --- STOP LIST ---", flush=True)
    for h in titles:
        print(f"  STOP TITLE: {h[:100]}", flush=True)
    print("  --- ADDRESS LINES ---", flush=True)
    for a in _ADDR_RE.findall(text):
        print(f"  ADDRESS: {a.strip()[:120]}", flush=True)
    print("  --- SOURCES LINES ---", flush=True)
    for s in _SOURCES_RE.findall(text)[:12]:
        print(f"  SOURCES: {s.strip()[:200]}", flush=True)
    print("  --- LOCAL-668 DETECTORS ---", flush=True)
    results = {}
    for name, fn in (("DELIVERED", detect_delivered),
                     ("SINGLE_ADDRESS", detect_single_address),
                     ("NO_FOREIGN_MUSEUM", detect_no_foreign_museum),
                     ("LACQUER_TOLD_ONCE", detect_lacquer_told_once)):
        try:
            ok, detail = fn(text)
        except Exception as e:
            ok, detail = False, f"detector error: {e}"
        results[name] = ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
    print(f"  [LOCAL-668] ALL DETECTORS PASS = {all(results.values())}", flush=True)
    return results


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-668 {location.split(',')[0][:40]} {slug} {int(time.time())}"
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
                 f"LOCAL-668 live fresh ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


def _run_arm(slug, env_overrides):
    for k, v in env_overrides.items():
        if v is None:
            _os.environ.pop(k, None)
        else:
            _os.environ[k] = v
    spend = _spend_so_far()
    print(f"\n[reserve-gate] arm={slug} spend_so_far="
          f"${spend if spend is not None else '?'} + reserve ${RESERVE_USD} "
          f"vs cap ${HARD_CAP_USD}", flush=True)
    if spend is not None and (spend + RESERVE_USD) > HARD_CAP_USD:
        print(f"[reserve-gate] SKIP {slug}: would exceed cap", flush=True)
        return (slug, None, 'SKIPPED_CAP', None, 0.0, 0.0)
    print(f"=== [{slug}] generating: {LOCATION} ({STOPS} stops, museum) "
          f"overrides={ {k:v for k,v in env_overrides.items()} } ===", flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            LOCATION, 'museum', f"/app/tours/LOCAL668_{slug}.txt", STOPS,
            user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {slug}: {e}", flush=True)
        return (slug, None, f'ERROR:{e}', None, 0.0, time.time() - t0)
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME [{slug}]: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        return (slug, None, 'NO_TEXT', None, 0.0, elapsed)
    delivered = _tc.count_delivered_stops(text)
    print(f"OUTCOME [{slug}]: DELIVERED — {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    results = _report(text)
    tour_cost = 0.0
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        tour_cost = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
        print(f"[cost] {slug} tour_total=${tour_cost:.4f}", flush=True)
    except Exception:
        pass
    nid = _store(LOCATION, text, delivered, slug)
    if nid:
        print(f"STORED audio_tours id = {nid}  (is_test=true)", flush=True)
        print(f"LOCAL668_TOUR_ID_{slug}={nid}", flush=True)
    try:
        with open(f"/app/tours/LOCAL668_{slug}_delivered.txt", "w",
                  encoding="utf-8") as _df:
            _df.write(text)
    except Exception:
        pass
    return (slug, nid, 'DELIVERED', results, tour_cost, elapsed)


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}",
      flush=True)

ARMS = [
    ("NORMAL", {"NARRATION_MODEL": None, "RESEARCH_BACKEND": None}),
    ("CHEAP", {"NARRATION_MODEL": "gpt-4.1-mini", "RESEARCH_BACKEND": "serper"}),
]

results = []
for _slug, _env in ARMS:
    results.append(_run_arm(_slug, _env))

print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}",
      flush=True)
print("=== LOCAL-668 run complete ===", flush=True)
for _slug, _id, _outcome, _det, _cost, _secs in results:
    print(f"RESULT {_slug}: id={_id if _id else ''} outcome={_outcome} "
          f"cost=${_cost:.4f} secs={_secs:.1f} detectors={_det}", flush=True)
