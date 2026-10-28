"""run_local788b_container.py — LOCAL-788B live acceptance (ISOLATED container).

Three fresh paid tours through the real generation path, each with tour_type ""
(exactly as the app sends it), proving the PLACES-FIRST fix end to end: for a
place-type tour the candidates come from places_search (the map) FIRST, an
LLM-proposed name that the map does not carry in scope is dropped, and the
existence gate ENFORCES (never ships an unverified stop).

  0. "middle eastern restaurants near me, west Roxbury, MA"  (2 stops)
     — the exact field defect (shipped the fabricated Sultan's Kebab / Cafe Jaffa)
  1. "coffee shops in Jamaica Plain, Boston"                 (3 stops)
  2. "Kitesurfing schools in Mui Ne, Vietnam"                (3 stops)

For each tour it prints the stop names, addresses, coordinates and the $ spent,
and reports the audio_tours row count BEFORE and AFTER. Budget: HARD CAP $1.50
for the WHOLE task, enforced by tests/live_run_meter.py (combined across every
provider). Each delivered tour is stored as ONE additive is_test row. No DELETE.

Run inside an isolated container only (never -p audioura; never touch audioura-*):
    docker run --rm --name local788b-tg \
        --network local788b_default \
        --env-file .env \
        -e DATABASE_URL=postgresql://admin:password123@local788b-postgres:5432/audiotours \
        -e STORIED_MODE=true -e DISABLE_TOUR_CACHE=1 -e DISABLE_STOP_POOL=1 \
        -e STOP_EXISTENCE_GATE_MODE=log_only \
        -e TEST_GEMINI_MAX_USD=1.50 -e COST_HARD_LIMIT_USD=1.50 \
        -v "$PWD":/app -w /app audioura-tour-generator:latest \
        python -u run_local788b_container.py <0|1|2>
"""
import os as _os
import sys as _sys
import re
import socket
import time

_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))

# Fresh, isolated, storied. tour_type "" as the app sends → place-type detection
# must force ENFORCE from poi_type / request text, not from the app tour_type.
_os.environ['STORIED_MODE'] = 'true'
_os.environ['DISABLE_TOUR_CACHE'] = '1'
_os.environ['DISABLE_STOP_POOL'] = '1'
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.50')
_os.environ.setdefault('COST_HARD_LIMIT_USD', '1.50')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')  # place-type forces enforce

HARD_CAP_USD = 1.50
HOST = socket.gethostname()

# tour_type is "" for every tour — exactly what the app sends.
TOURS = [
    ('middle eastern restaurants near me, west Roxbury, MA', '', 2, 'ME-WROX'),
    ('coffee shops in Jamaica Plain, Boston', '', 3, 'COFFEE-JP'),
    ('Kitesurfing schools in Mui Ne, Vietnam', '', 3, 'KITE-MUINE'),
]

if len(_sys.argv) > 1:
    try:
        _only = int(_sys.argv[1])
        TOURS = [TOURS[_only]]
        print(f"[LOCAL-788B] single-tour mode: index {_only}", flush=True)
    except (ValueError, IndexError):
        print(f"[LOCAL-788B] bad tour index {_sys.argv[1]!r}; running all", flush=True)

print("=== LOCAL-788B isolated live run (places-first, tour_type='') ===", flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  cache_off=1 pool_off=1  "
      f"gate=place-type->ENFORCE  STORIED_MODE=true", flush=True)

try:
    from live_run_meter import LiveRunMeter
except Exception as _e:
    print(f"[LOCAL-788B] live_run_meter unavailable ({_e}) — cannot cap; aborting", flush=True)
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
        name = f"LOCAL-788B {location.split(',')[0][:40]} {int(time.time())}"
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
                (name, location, n_stops, text, n_stops, 'LOCAL-788B places-first live'))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [db] store failed: {e}", flush=True); return None


def main():
    before = _row_count()
    print(f"audio_tours rows BEFORE: {before}", flush=True)

    meter = LiveRunMeter('LOCAL-788B')
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
                    print(f"  [LOCAL-788B] generation returned NO text "
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
                    print(f"  [LOCAL-788B] meter.add_generation failed (non-fatal): {_ae}", flush=True)
                print(f"  stored is_test row id={rid}; delivered {n} stop(s) in {dt:.0f}s",
                      flush=True)
                results.append((slug, f'{n} stops', n))
            except Exception as e:
                print(f"  [LOCAL-788B] TOUR [{slug}] raised: {e}", flush=True)
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
            print(f"\n[LOCAL-788B] cost ledger row: {row_id}", flush=True)
        except Exception as _me:
            print(f"[LOCAL-788B] meter.record failed (non-fatal): {_me}", flush=True)
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
    print("=== LOCAL-788B SUMMARY ===", flush=True)
    for slug, status, n in results:
        print(f"  [{slug}] {status}", flush=True)


if __name__ == '__main__':
    main()
