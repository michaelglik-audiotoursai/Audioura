#!/usr/bin/env python3
"""run_local637_container.py — LOCAL-637 live acceptance (ISOLATED container).

Two checks through the REAL code with the LOCAL-637 branch in the image, cache +
pool OFF (FRESH):

  1. PAID — The Wallace Collection, London, 3 stops. Bench R6 built this museum's
     corpus from a MUSIC BAND's Wikipedia article (resolved Q1516598, enwiki
     'Wallace Collection (band)') and refused the tour. With the LOCAL-637 fixes
     the venue must resolve to the MUSEUM (Q1327919) and generate. ONE paid tour
     only (ticket: "Start no second paid tour"). Delivered SPOKEN text is stored
     as an additive is_test row for critique.sh / detectors.py.

  2. FREE — resolver-only National Gallery x3 under an INJECTED 429. No paid
     calls: this calls venue_resolver.resolve_venue() with requests.get wrapped
     so the FIRST Wikidata search per resolve returns HTTP 429 (then the real
     endpoint). Bench R6 refused the National Gallery (Q180788, 389 works) when a
     429 tripped the dead-host breaker and city validation discarded the already-
     resolved museum. It must now resolve to Q180788 all three times.

HARD CAP $1.30, enforced with the RESERVE GATE: the paid tour starts only if
(spend_so_far + reserve) <= $1.30, spend_so_far read from paid_api_calls for THIS
container host. is_test rows are the ONLY rows written. No DELETE.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-637')
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
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.30')
os.environ['COST_HARD_LIMIT_USD'] = '1.30'        # ticket HARD CAP
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')

HARD_CAP_USD = 1.30
RESERVE_USD = 0.80          # start the paid tour only if spend + 0.80 <= cap
HOST = socket.gethostname()

WALLACE = ('The Wallace Collection, London, United Kingdom', 3, 'WALLACE')
NG_RESOLVER = 'The National Gallery'
NG_CITY = 'London'
NG_QID = 'Q180788'

print("=== LOCAL-637 isolated live run ===", flush=True)
print(f"host  : {HOST}", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   HARD CAP: ${HARD_CAP_USD}  "
      f"reserve: ${RESERVE_USD}  cache_off=1 pool_off=1", flush=True)

import requests  # noqa: E402
from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402
import venue_resolver as _vr  # noqa: E402


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
    for m in re.finditer(r"(?mi)^Stop\s+\d+:\s*(.+)$", text):
        print(f"  STOP TITLE: {m.group(1).strip()}", flush=True)


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-637 {location.split(',')[0]} {int(time.time())}"
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
                 f"LOCAL-637 live fresh ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


def _run_paid(location, stops, slug):
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
            location, 'museum', f"/app/tours/LOCAL637_{slug}.txt", stops, user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {location}: {e}", flush=True); return None
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True); return None
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
        print(f"LOCAL637_TOUR_ID={nid}", flush=True)
    return nid


def _resolver_only_ng_under_429(runs=3):
    """FREE check: resolve the National Gallery `runs` times with the FIRST
    Wikidata search per resolve forced to HTTP 429. No paid calls at all — this
    exercises only venue_resolver + dead_host_breaker.
    """
    import dead_host_breaker as _dhb

    class _Resp429:
        status_code = 429
        headers = {"Retry-After": "1"}

        def json(self):
            return {}

    print(f"\n=== resolver-only National Gallery x{runs} under injected 429 "
          f"(NO paid calls) ===", flush=True)
    results = []
    _orig_get = requests.get
    for i in range(runs):
        # Fresh tour scope per run so the dead-host cool-down starts clean.
        _tok = _dhb.begin_tour_scope()
        _state = {"injected": False}

        def _get(url, *a, **k):
            # Inject a single 429 on the FIRST Wikidata API GET of this resolve,
            # then fall through to the real endpoint for every subsequent call.
            if (not _state["injected"]) and 'wikidata.org/w/api.php' in str(url):
                _state["injected"] = True
                print(f"  [run {i+1}] injected HTTP 429 on first Wikidata search",
                      flush=True)
                return _Resp429()
            return _orig_get(url, *a, **k)

        requests.get = _get
        try:
            ent = _vr.resolve_venue(NG_RESOLVER, NG_CITY)
        except Exception as e:
            ent = None
            print(f"  [run {i+1}] resolve raised: {e}", flush=True)
        finally:
            requests.get = _orig_get
            _dhb.end_tour_scope(_tok)
        qid = getattr(ent, 'qid', None)
        name = getattr(ent, 'name', None)
        ok = (qid == NG_QID)
        results.append(ok)
        print(f"  [run {i+1}] resolved qid={qid} name={name!r} "
              f"{'OK' if ok else 'FAIL (expected ' + NG_QID + ')'}", flush=True)
    passed = sum(1 for r in results if r)
    print(f"=== resolver-only NG result: {passed}/{runs} resolved to {NG_QID} ===",
          flush=True)
    return passed, runs


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}", flush=True)

# 1) ONE paid tour: the Wallace Collection, 3 stops (gated).
_wid = _run_paid(*WALLACE)

# 2) FREE resolver-only National Gallery x3 under injected 429.
_ng_pass, _ng_runs = _resolver_only_ng_under_429(3)

print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}", flush=True)
print("=== LOCAL-637 run complete ===", flush=True)
print(f"LOCAL637_TOUR_IDS={_wid if _wid else ''}", flush=True)
print(f"LOCAL637_NG_RESOLVER={_ng_pass}/{_ng_runs}", flush=True)
