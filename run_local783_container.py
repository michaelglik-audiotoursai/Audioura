"""run_local783_container.py — LOCAL-783 live acceptance (ISOLATED container).

Three fresh paid tours through the real generation path, proving the Serper
Places provider powers the business/restaurant bulk search + refill (the
LOCAL-779B "Known limitation": the free Nominatim bulk search returned 0 for
West Roxbury and the North End, so the refill was empty):

  1. "middle eastern restaurants near me, west Roxbury, MA"   (2 stops) — DINING
     ACCEPTANCE: delivers 2 of {Al Wadi, Stardust, Bread Thyme}. LOCAL-779B
     refused this; that refusal only reflected the free OSM data.
  2. "coffee shops in Jamaica Plain, Boston"                  (3 stops) — BUSINESS
  3. "gyms in Brookline, MA"                                  (2 stops) — BUSINESS

For each tour it prints the stop names, addresses, coordinates, the Serper Places
calls made, and the $ spent. It reports the audio_tours row count BEFORE and AFTER.
Budget: HARD CAP $1.20 for the whole task (combined across all providers). Each
delivered tour is stored as ONE additive is_test row. No DELETE of any kind.

Run inside an isolated container only (never -p audioura; never touch audioura-*):
    docker run --rm --name local783-tg \
        --network development_default \
        -e DATABASE_URL=... -e OPENAI_API_KEY=... -e GEMINI_API_KEY=... \
        -e SERP_API_KEY=... -e SERP_PROVIDER=serper -e STORIED_MODE=true \
        -e TEST_GEMINI_MAX_USD=1.20 -e COST_HARD_LIMIT_USD=1.20 \
        -v "$PWD":/app -w /app audioura-tour-generator \
        python -u run_local783_container.py <0|1|2>
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
_os.environ.setdefault('SERP_PROVIDER', 'serper')
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.20')
_os.environ.setdefault('COST_HARD_LIMIT_USD', '1.20')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

HARD_CAP_USD = 1.20
HOST = socket.gethostname()

TOURS = [
    ('middle eastern restaurants near me, west Roxbury, MA', 2, 'dining', 'ME-WROX'),
    ('coffee shops in Jamaica Plain, Boston', 3, 'walking', 'COFFEE-JP'),
    ('gyms in Brookline, MA', 2, 'walking', 'GYMS-BROOKLINE'),
]

if len(_sys.argv) > 1:
    try:
        _only = int(_sys.argv[1])
        TOURS = [TOURS[_only]]
        print(f"[LOCAL-783] single-tour mode: index {_only}", flush=True)
    except (ValueError, IndexError):
        print(f"[LOCAL-783] bad tour index {_sys.argv[1]!r}; running all", flush=True)

print("=== LOCAL-783 isolated live run (Serper Places bulk search + refill) ===", flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  cache_off=1 pool_off=1  "
      f"SERP_PROVIDER={_os.environ.get('SERP_PROVIDER')}  STORIED_MODE=true", flush=True)
print(f"serper key present: {bool(_os.environ.get('SERP_API_KEY') or _os.environ.get('SERPER_API_KEY'))}",
      flush=True)

try:
    from live_run_meter import LiveRunMeter
except Exception as _e:
    print(f"[LOCAL-783] live_run_meter unavailable ({_e}) — cannot cap; aborting", flush=True)
    _sys.exit(2)


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


def _places_call_count():
    """Serper Places calls recorded in paid_api_calls (url ending /places)."""
    return _scalar("SELECT count(*) FROM paid_api_calls WHERE url LIKE %s",
                   ('%/places%',))


def _places_usd():
    return _scalar("SELECT COALESCE(SUM(usd),0) FROM paid_api_calls WHERE url LIKE %s",
                   ('%/places%',))


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
        name = f"LOCAL-783 {location.split(',')[0][:40]} {int(time.time())}"
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
                (name, location, n_stops, text, n_stops, 'LOCAL-783 serper places live'))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [db] store failed: {e}", flush=True); return None


def main():
    before = _row_count()
    places_before = _places_call_count()
    print(f"audio_tours rows BEFORE: {before}", flush=True)
    print(f"serper /places calls BEFORE: {places_before}", flush=True)

    meter = LiveRunMeter('LOCAL-783')
    results = []
    try:
        import generate_tour_text as g
        import traceback as _tb
        for (location, stops, kind, slug) in TOURS:
            print(f"\n=== TOUR [{slug}] {location!r} ({stops} stops) ===", flush=True)
            _pc0 = _places_call_count()
            t0 = time.time()
            try:
                text, _out, coords = g.generate_tour_text(location, kind, None, stops)
                dt = time.time() - t0
                _pc1 = _places_call_count()
                _pdelta = (_pc1 - _pc0) if (_pc1 is not None and _pc0 is not None) else '?'
                if not text:
                    try:
                        _ev = dict(getattr(g, '_LAST_CLEAN_FAIL_EVIDENCE', {}) or {})
                    except Exception:
                        _ev = {}
                    print(f"  [LOCAL-783] generation returned NO text "
                          f"(clean-fail) in {dt:.0f}s; evidence={_ev}", flush=True)
                    print(f"  [LOCAL-783] serper /places calls this tour: {_pdelta}", flush=True)
                    try:
                        meter.add_generation(g)
                    except Exception:
                        pass
                    results.append((slug, 'NO_TEXT (clean-fail)', 0, _pdelta))
                    continue
                titles = _report_stops(text)
                n = len(titles)
                rid = _store(location, text, stops)
                try:
                    meter.add_generation(g)
                except Exception as _ae:
                    print(f"  [LOCAL-783] meter.add_generation failed: {_ae}", flush=True)
                print(f"  stored is_test row id={rid}; delivered {n} stop(s) in {dt:.0f}s",
                      flush=True)
                print(f"  serper /places calls this tour: {_pdelta}", flush=True)
                results.append((slug, f'{n} stops', n, _pdelta))
            except Exception as e:
                print(f"  [LOCAL-783] TOUR [{slug}] raised: {e}", flush=True)
                _tb.print_exc()
                try:
                    meter.add_generation(g)
                except Exception:
                    pass
                results.append((slug, f'ERROR: {e}', 0, '?'))
                continue
    finally:
        try:
            row_id = meter.record()
            print(f"\n[LOCAL-783] cost ledger row: {row_id}", flush=True)
        except Exception as _me:
            print(f"[LOCAL-783] meter.record failed: {_me}", flush=True)
        try:
            print(meter.summary(), flush=True)
        except Exception:
            pass
        try:
            meter.uninstall()
        except Exception:
            pass

    after = _row_count()
    places_after = _places_call_count()
    places_usd = _places_usd()
    print(f"\naudio_tours rows AFTER: {after}  (delta={after - before if (after and before) else '?'})",
          flush=True)
    print(f"serper /places calls AFTER: {places_after}  "
          f"(delta={places_after - places_before if (places_after is not None and places_before is not None) else '?'})",
          flush=True)
    print(f"serper /places cumulative $ in ledger: {places_usd}", flush=True)
    print("=== LOCAL-783 SUMMARY ===", flush=True)
    for slug, status, n, pc in results:
        print(f"  [{slug}] {status}  (places_calls={pc})", flush=True)


if __name__ == '__main__':
    main()
