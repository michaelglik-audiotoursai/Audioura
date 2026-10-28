"""run_local790_container.py — LOCAL-790 live acceptance (ISOLATED container).

Walking tours outside the US/Europe used to reject every real place and ship
"no stops could be generated". These three fresh paid tours run through the real
generation path and prove the fix end to end:

  0. "French colonial architecture and Vietnamese culture walk, District 1 and 3,
      Ho Chi Minh City"                         (5 stops)
  1. "Pagodas and temples of Ho Chi Minh City (Jade Emperor Pagoda, Thien Hau
      Temple)"                                  (5 stops)
  2. "Boston Freedom Trail walking tour, Boston, MA"  (4 stops)  — US canary,
      must stay unchanged.

For 0 and 1 we want 5 real HCMC places each (the pagodas request must INCLUDE
Jade Emperor Pagoda and Thien Hau Temple, and must not list the same place twice
under its Vietnamese + English name). For 2 we want 4 real Boston stops.

Budget: HARD CAP $2.00 for the WHOLE task, enforced by tests/live_run_meter.py
(combined across every provider). Each delivered tour is stored as ONE additive
is_test row. No DELETE.

Run inside an isolated container only (reuse the LOCAL-788B isolated postgres;
never -p audioura; never touch audioura-*):
    docker run --rm --name local790-tg \
        --network local788b_default \
        --env-file .env \
        -e DATABASE_URL=postgresql://admin:password123@local788b-postgres:5432/audiotours \
        -e STORIED_MODE=true -e DISABLE_TOUR_CACHE=1 -e DISABLE_STOP_POOL=1 \
        -e STOP_EXISTENCE_GATE_MODE=log_only \
        -e TEST_GEMINI_MAX_USD=2.00 -e COST_HARD_LIMIT_USD=2.00 \
        -v "$PWD":/app -w /app audioura-tour-generator:latest \
        python -u run_local790_container.py <0|1|2>
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
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '2.00')
_os.environ.setdefault('COST_HARD_LIMIT_USD', '2.00')
# Walking tours force ENFORCE regardless (LOCAL-662); the shared-stack default is
# log_only, matching the field stack.
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

HARD_CAP_USD = 2.00
HOST = socket.gethostname()

# tour_type "" for the two HCMC walks (as the app sends); "walking" for Boston so
# the US canary matches a classic Freedom Trail walking request.
TOURS = [
    ('French colonial architecture and Vietnamese culture walk, '
     'District 1 and 3, Ho Chi Minh City', '', 5, 'HCMC-ARCH'),
    ('Pagodas and temples of Ho Chi Minh City '
     '(Jade Emperor Pagoda, Thien Hau Temple)', '', 5, 'HCMC-PAGODAS'),
    ('Boston Freedom Trail walking tour, Boston, MA', 'walking', 4, 'BOSTON-FREEDOM'),
]

if len(_sys.argv) > 1:
    try:
        _only = int(_sys.argv[1])
        TOURS = [TOURS[_only]]
        print(f"[LOCAL-790] single-tour mode: index {_only}", flush=True)
    except (ValueError, IndexError):
        print(f"[LOCAL-790] bad tour index {_sys.argv[1]!r}; running all", flush=True)

print("=== LOCAL-790 isolated live run (walking gate intl) ===", flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  cache_off=1 pool_off=1  "
      f"gate=walking->ENFORCE  STORIED_MODE=true", flush=True)

try:
    from live_run_meter import LiveRunMeter
except Exception as _e:
    print(f"[LOCAL-790] live_run_meter unavailable ({_e}) — cannot cap; aborting", flush=True)
    _sys.exit(2)


def _conn():
    import psycopg2
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=_os.environ.get('DB_HOST', 'local788b-postgres'),
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
_ADDR_RE = re.compile(r"(?mi)^Address:\s*(.+)$")
_COORD_RE = re.compile(r"(?mi)^Coordinates:\s*(.+)$")


def _report_stops(text):
    print("  --- STOPS ---", flush=True)
    titles = _STOP_HEADER_RE.findall(text)
    addrs = _ADDR_RE.findall(text)
    coords = _COORD_RE.findall(text)
    for i, t in enumerate(titles):
        a = addrs[i].strip() if i < len(addrs) else '(no address line)'
        c = coords[i].strip() if i < len(coords) else '(no coord line)'
        print(f"  STOP {i+1}: {t.strip()[:80]}", flush=True)
        print(f"         addr: {a[:90]}", flush=True)
        print(f"         coords: {c[:40]}", flush=True)
    return titles


def _store(location, text, n_stops):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-790 {location.split(',')[0][:40]} {int(time.time())}"
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
                (name, location, n_stops, text, n_stops, 'LOCAL-790 walking gate intl live'))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [db] store failed: {e}", flush=True); return None


def main():
    before = _row_count()
    print(f"audio_tours rows BEFORE: {before}", flush=True)

    meter = LiveRunMeter('LOCAL-790')
    results = []
    try:
        import generate_tour_text as g
        import traceback as _tb
        for (location, ttype, stops, slug) in TOURS:
            print(f"\n=== TOUR [{slug}] {location!r} tour_type={ttype!r} "
                  f"({stops} stops) ===", flush=True)
            t0 = time.time()
            try:
                text, _out, coords = g.generate_tour_text(location, ttype, None, stops)
                dt = time.time() - t0
                if not text:
                    try:
                        _ev = dict(getattr(g, '_LAST_CLEAN_FAIL_EVIDENCE', {}) or {})
                    except Exception:
                        _ev = {}
                    print(f"  [LOCAL-790] generation returned NO text "
                          f"(clean-fail) in {dt:.0f}s; evidence={_ev}", flush=True)
                    try:
                        meter.add_generation(g)
                    except Exception:
                        pass
                    results.append((slug, 'NO_TEXT (clean-fail)', 0))
                    continue
                titles = _report_stops(text)
                n = len(titles)
                rid = _store(location, text, stops)
                try:
                    meter.add_generation(g)
                except Exception as _ae:
                    print(f"  [LOCAL-790] meter.add_generation failed (non-fatal): {_ae}", flush=True)
                print(f"  stored is_test row id={rid}; delivered {n} stop(s) in {dt:.0f}s",
                      flush=True)
                results.append((slug, f'{n} stops', n))
            except Exception as e:
                print(f"  [LOCAL-790] TOUR [{slug}] raised: {e}", flush=True)
                _tb.print_exc()
                try:
                    meter.add_generation(g)
                except Exception:
                    pass
                results.append((slug, f'ERROR: {e}', 0))
                continue
    finally:
        try:
            row_id = meter.record()
            print(f"\n[LOCAL-790] cost ledger row: {row_id}", flush=True)
        except Exception as _me:
            print(f"[LOCAL-790] meter.record failed (non-fatal): {_me}", flush=True)
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
    print("=== LOCAL-790 SUMMARY ===", flush=True)
    for slug, status, n in results:
        print(f"  [{slug}] {status}", flush=True)


if __name__ == '__main__':
    main()
