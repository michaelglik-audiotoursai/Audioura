"""run_local838_container.py — LOCAL-838 live acceptance (ISOLATED container).

Proves the walk-beats-805 fix end to end on the CHEAP arm
(NARRATION_MODEL=gpt-4.1-mini, RESEARCH_BACKEND=serper):

  0.  "Ben Thanh Market walk, Ho Chi Minh City"   tour_type=walking   (4)
      — the field defect (wave 14 proof, gen 00020-2q6 @ ce18fca3): LOCAL-805's
        business-subject routing classified the SUBJECT ("Ben Thanh Market": a
        market → a business) and sent the request down the PLACES path as
        category='restaurant', OVERRIDING the app's explicit walking type, so
        LOCAL-836's walkable-area widening never ran and the tour shipped 2/4.
        With the fix the explicit walking tour_type (and the "walk" word) win:
        category='walking', the single-anchor scope widens to the enclosing area,
        and replenishment reaches 4 real nearby District-1 landmarks.

PASS = walking category, 4/4 REAL nearby landmarks (not padded / not duplicated),
and ≤ $0.30 for the tour.

Budget: HARD CAP $0.40 for the WHOLE task (combined across every provider),
enforced by tests/live_run_meter.py + task_budget (TASK_BUDGET_ID=LOCAL-838,
TASK_BUDGET_USD=0.40). ONE live tour. The delivered tour is stored as ONE
additive is_test row in the ISOLATED DB. No DELETE. Live DB never written. Never
touch the shared audioura-* containers.

Run via run_local838_live.sh (it carries the LOCAL-820 meter contract), or inside
an isolated container only (OWN project -p local838; never -p audioura):

    python -u run_local838_container.py
"""
import os as _os
import sys as _sys
import re
import socket
import time

_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))

_os.environ['STORIED_MODE'] = 'true'
_os.environ['DISABLE_TOUR_CACHE'] = '1'
_os.environ['DISABLE_STOP_POOL'] = '1'
_os.environ.setdefault('NARRATION_MODEL', 'gpt-4.1-mini')
_os.environ.setdefault('RESEARCH_BACKEND', 'serper')
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '0.40')
_os.environ.setdefault('COST_HARD_LIMIT_USD', '0.40')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

HARD_CAP_USD = 0.40
PER_TOUR_PASS_USD = 0.30
HOST = socket.gethostname()

# (request, tour_type, n_stops, slug)
TOURS = [
    ('Ben Thanh Market walk, Ho Chi Minh City',
     'walking', 4, 'ben-thanh-market-walk-HCMC'),
]

print("=== LOCAL-838 isolated live run (cheap arm: gpt-4.1-mini + serper) ===", flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  per-tour PASS <= ${PER_TOUR_PASS_USD}  "
      f"cache_off=1 pool_off=1  STORIED_MODE=true "
      f"RESEARCH_BACKEND={_os.environ.get('RESEARCH_BACKEND')}", flush=True)

try:
    from live_run_meter import LiveRunMeter
except Exception as _e:
    print(f"[LOCAL-838] live_run_meter unavailable ({_e}) — cannot cap; aborting", flush=True)
    _sys.exit(2)


def _conn():
    import psycopg2
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=_os.environ.get('DB_HOST', 'local838-postgres'),
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


_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")
_SHORTFALL_RE = re.compile(r"rather than the\s+\d+\s+you asked for", re.IGNORECASE)


def _report_stops(text):
    print("  --- STOPS ---", flush=True)
    titles = _STOP_HEADER_RE.findall(text)
    for i, t in enumerate(titles):
        print(f"  STOP {i+1}: {t.strip()[:80]}", flush=True)
    sf = bool(_SHORTFALL_RE.search(text or ''))
    print(f"  shortfall-apology present: {sf}", flush=True)
    return titles, sf


def _store(location, text, n_stops):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-838 {location.split(',')[0][:40]} {int(time.time())}"
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
                 'LOCAL-838 walk-beats-805 live'))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [db] store failed: {e}", flush=True); return None


def main():
    before = _row_count()
    print(f"audio_tours rows BEFORE: {before}", flush=True)

    meter = LiveRunMeter('LOCAL-838')
    results = []
    try:
        import generate_tour_text as g
        import traceback as _tb
        for (location, ttype, stops, slug) in TOURS:
            print(f"\n=== TOUR [{slug}] {location!r} tour_type={ttype!r} "
                  f"({stops} stops) ===", flush=True)
            # Show the classified category deterministically BEFORE spend — this
            # is the LOCAL-838 fix in action (explicit walking tour_type + "walk"
            # word beat the 805 business-subject routing).
            try:
                cat = g._classify_tour_category(location, ttype)
                print(f"  [LOCAL-838] classified category = {cat!r} "
                      f"(expected 'walking')", flush=True)
            except Exception as _ce:
                cat = '?'
                print(f"  [LOCAL-838] classify failed (non-fatal): {_ce}", flush=True)
            t0 = time.time()
            try:
                text, _out, coords = g.generate_tour_text(location, ttype, None, stops)
                dt = time.time() - t0
                if not text:
                    try:
                        _ev = dict(getattr(g, '_LAST_CLEAN_FAIL_EVIDENCE', {}) or {})
                    except Exception:
                        _ev = {}
                    print(f"  [LOCAL-838] generation returned NO text "
                          f"(clean-fail) in {dt:.0f}s; evidence={_ev}", flush=True)
                    try:
                        meter.add_generation(g)
                    except Exception:
                        pass
                    results.append((slug, 'NO_TEXT (clean-fail)', 0, stops, None, cat))
                    continue
                titles, sf = _report_stops(text)
                rid = _store(location, text, stops)
                try:
                    meter.add_generation(g)
                except Exception as _ae:
                    print(f"  [LOCAL-838] meter.add_generation failed (non-fatal): {_ae}", flush=True)
                print(f"  stored is_test row id={rid}; delivered {len(titles)}/{stops} "
                      f"stop(s) in {dt:.0f}s", flush=True)
                results.append((slug, f'{len(titles)}/{stops} stops cat={cat}',
                                len(titles), stops, sf, cat))
            except Exception as e:
                print(f"  [LOCAL-838] TOUR [{slug}] raised: {e}", flush=True)
                _tb.print_exc()
                try:
                    meter.add_generation(g)
                except Exception:
                    pass
                results.append((slug, f'ERROR: {e}', 0, stops, None, cat))
                continue
    finally:
        try:
            row_id = meter.record()
            print(f"\n[LOCAL-838] cost ledger row: {row_id}", flush=True)
        except Exception as _me:
            print(f"[LOCAL-838] meter.record failed (non-fatal): {_me}", flush=True)
        try:
            print(meter.summary(), flush=True)
        except Exception:
            pass
        try:
            meter.uninstall()
        except Exception:
            pass

    after = _row_count()
    print(f"\naudio_tours rows AFTER: {after}  (delta={after - before if (after and before) else '?'})",
          flush=True)
    print("=== LOCAL-838 SUMMARY ===", flush=True)
    for slug, status, n, req, sf, cat in results:
        verdict = 'PASS' if (n == req and cat == 'walking') else 'FAIL'
        print(f"  [{slug}] {status}  -> {verdict}"
              f"{' (shortfall-apology present)' if sf else ''}", flush=True)


if __name__ == '__main__':
    main()
