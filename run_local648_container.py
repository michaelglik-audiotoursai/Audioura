#!/usr/bin/env python3
"""run_local648_container.py — LOCAL-648 live acceptance (ISOLATED container).

Two phases, one combined spend cap ($2.50, ticket), metered via
tests/live_run_meter.py across ALL providers:

  PHASE 1 — OFFLINE A/B (per story-lead question): for 6 stored museums, answer
    the RECONSTRUCTED per-stop grounded question BOTH ways (Gemini grounded search
    vs serper_research) and record distinct facts, sources, $/question,
    seconds/question, and a cheap-model overlap judgement. Writes
    LOCAL648_overlap_measurement.json. (measure_local648_overlap.py does the work.)

  PHASE 2 — LIVE tours with RESEARCH_BACKEND=serper: generate the Courtauld (3)
    and the Walters (3) through the REAL generation path, cache + pool OFF. The
    per-stop grounded narrate is answered by Serper; the venue preflight stays on
    Gemini (so we expect ~1 Gemini grounding request per tour = the preflight).
    Each delivered SPOKEN tour is stored as ONE additive is_test row for
    critique.sh / detectors.py. is_test rows are the ONLY rows written. No DELETE.

Reports row counts before/after and the per-arm spend read from paid_api_calls.
A RESERVE GATE before each live tour prevents crossing the cap.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
except Exception as _e:
    _live_run_meter = None
    print(f"[LOCAL-648] live_run_meter unavailable ({_e})", flush=True)

import os
import re
import socket
import time

# ── global run config ─────────────────────────────────────────────────────────
os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['DISABLE_STOP_POOL'] = '1'
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '2.50')   # ticket combined cap
os.environ['COST_HARD_LIMIT_USD'] = '2.50'
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')

HARD_CAP_USD = 2.50
OFFLINE_BUDGET_USD = float(os.environ.get('LOCAL648_OFFLINE_BUDGET', '1.00'))
RESERVE_USD = 0.55          # start a live tour only if spend + 0.55 <= cap
HOST = socket.gethostname()

# PHASE 2 live tours (location, stops, tour_type, slug)
TOURS = [
    ('The Courtauld Gallery, London, United Kingdom', 3, 'museum', 'COURTAULD'),
    ('The Walters Art Museum, Baltimore, MD, United States', 3, 'museum', 'WALTERS'),
]

print("=== LOCAL-648 isolated live run (offline A/B + Serper live tours) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}  COMBINED CAP ${HARD_CAP_USD}  "
      f"offline budget ${OFFLINE_BUDGET_USD}  reserve ${RESERVE_USD}  "
      f"cache_off=1 pool_off=1", flush=True)


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


# ── PHASE 1: offline A/B ──────────────────────────────────────────────────────
def run_offline():
    print("\n" + "#" * 70, flush=True)
    print("# PHASE 1 — OFFLINE A/B (Gemini grounded vs Serper research)", flush=True)
    print("#" * 70, flush=True)
    os.environ['LOCAL648_MAX_USD'] = str(OFFLINE_BUDGET_USD)
    # Write the measurement JSON into the mounted /app/tours so it survives the
    # disposable container (which is --rm, so docker cp is too late).
    os.environ.setdefault('LOCAL648_OUT_JSON',
                          '/app/tours/LOCAL648_overlap_measurement.json')
    try:
        import measure_local648_overlap as mm
        import sys as _s
        _argv = _s.argv
        _s.argv = ['measure_local648_overlap.py']  # all 6 museums
        try:
            mm.main()
        finally:
            _s.argv = _argv
    except SystemExit:
        pass
    except Exception as e:
        print(f"[PHASE1] offline A/B error: {type(e).__name__}: {e}", flush=True)


# ── PHASE 2: live tours (RESEARCH_BACKEND=serper) ─────────────────────────────
def _store(location, text, n_stops, slug, kind_desc):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-648 {location.split(',')[0][:40]} {int(time.time())}"
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


def _report_museum(text):
    import tour_conclusion as _tc
    import directions_guarantee as _dg
    headers = re.findall(r"(?mi)^Stop\s+\d+:\s*(.+)$", text)
    for h in headers:
        print(f"  STOP TITLE: {h.strip()[:90]}", flush=True)
    print(f"  HEADER COUNT: {len(headers)}   "
          f"count_delivered_stops: {_tc.count_delivered_stops(text)}", flush=True)
    glued = re.search(r"(?mi)^Stop\s+\d+:.*\b(?:Address|Coordinates|Orientation|"
                      r"Directions):", text)
    print(f"  [canary] run-on header: {bool(glued)}  "
          f"missing_directions: {_dg.count_stops_missing_directions(text)}",
          flush=True)


def run_live():
    print("\n" + "#" * 70, flush=True)
    print("# PHASE 2 — LIVE tours, RESEARCH_BACKEND=serper", flush=True)
    print("#" * 70, flush=True)
    os.environ['RESEARCH_BACKEND'] = 'serper'     # the whole point
    import story_leads
    print(f"  research_backend() = {story_leads.research_backend()}", flush=True)

    from generate_tour_text import generate_tour_text
    import tour_conclusion as _tc
    results = []
    for location, stops, ttype, slug in TOURS:
        spend = _spend_so_far()
        print(f"\n[reserve-gate] spend_so_far="
              f"${spend if spend is not None else '?'} + reserve ${RESERVE_USD} "
              f"vs cap ${HARD_CAP_USD}", flush=True)
        if spend is not None and (spend + RESERVE_USD) > HARD_CAP_USD:
            print(f"[reserve-gate] SKIP {slug}: would exceed cap", flush=True)
            results.append((slug, None, 'SKIPPED_CAP'))
            continue
        # Reset grounding counters so we can report Gemini grounding requests/tour.
        try:
            story_leads.reset_grounding_requests()
        except Exception:
            pass
        print(f"=== generating: {location} ({stops} stops, {ttype}) ===",
              flush=True)
        t0 = time.time()
        try:
            text, _p, _c = generate_tour_text(
                location, ttype, f"/app/tours/LOCAL648_{slug}.txt", stops,
                user_id=None)
        except Exception as e:
            print(f"RUN ERROR for {location}: {e}", flush=True)
            results.append((slug, None, f'ERROR:{e}'))
            continue
        elapsed = time.time() - t0
        if not text:
            print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
            results.append((slug, None, 'NO_TEXT'))
            continue
        delivered = _tc.count_delivered_stops(text)
        print(f"OUTCOME: DELIVERED — {len(text)} chars, {delivered} stops, "
              f"wall {elapsed:.1f}s", flush=True)
        _report_museum(text)
        try:
            greq = story_leads.get_grounding_requests()
            gq = story_leads.get_grounding_queries()
            print(f"  [GROUNDING] Gemini grounding requests this tour: {greq} "
                  f"(queries {gq})  — expect ~1 (the preflight)", flush=True)
        except Exception:
            pass
        try:
            from generate_tour_text import _LAST_GENERATION_COST
            _cc = dict(_LAST_GENERATION_COST or {})
            _tot = float(_cc.get('tour_total_cost',
                                 _cc.get('total_cost', 0.0)) or 0.0)
            print(f"  [cost] tour_total=${_tot:.4f}", flush=True)
        except Exception:
            pass
        nid = _store(location, text, delivered, slug,
                     f"LOCAL-648 live Serper backend ({slug}, {ttype})")
        if nid:
            print(f"STORED audio_tours id = {nid}  (is_test=true)", flush=True)
            print(f"LOCAL648_TOUR_ID_{slug}={nid}", flush=True)
        results.append((slug, nid, 'DELIVERED'))
    return results


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    meter = None
    if _live_run_meter is not None:
        try:
            meter = _live_run_meter.LiveRunMeter('LOCAL-648')
        except Exception as e:
            print(f"[LOCAL-648] meter init failed ({e}); continuing uncapped-local",
                  flush=True)

    print(f"[db] audio_tours row count BEFORE: {_row_count()} "
          f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
    print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}",
          flush=True)

    run_offline()

    try:
        import story_leads as _sl
        _CapExc = getattr(_sl, 'TestRunCapExceeded', RuntimeError)
    except Exception:
        _CapExc = RuntimeError
    try:
        results = run_live()
    except _CapExc as e:
        print(f"[LOCAL-648] run stopped by combined cap: {e}", flush=True)
        results = []
    except Exception as e:
        print(f"[LOCAL-648] live phase error: {e}", flush=True)
        results = []

    if meter is not None:
        try:
            row_id = meter.record()
            print(f"[meter] cost_ledger row id = {row_id}", flush=True)
            print(meter.summary(), flush=True)
        except Exception as e:
            print(f"[meter] record failed: {e}", flush=True)
        finally:
            try:
                meter.uninstall()
            except Exception:
                pass

    print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
          f"(is_test rows AFTER: {_test_row_count()})", flush=True)
    print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}",
          flush=True)
    print("=== LOCAL-648 run complete ===", flush=True)
    for _slug, _id, _outcome in results:
        print(f"RESULT {_slug}: id={_id if _id else ''} outcome={_outcome}",
              flush=True)


if __name__ == '__main__':
    main()
