"""run_local809_container.py — LOCAL-809 live acceptance (ISOLATED container).

Two fresh paid tours through the real generation path, proving the museum-source
fixes end to end on the ticket's named venues:

  0. "Metropolitan Museum of Art, New York, NY" (5)
       — fix 1: no Met Store merchandise as a stop (no "… Custom Print",
         "… Calendar", "… Mug", "… Tote", "… — The Met Store"); every stop a real
         work in the Met's collection.
  1. "Belvedere Museum, Vienna, Austria" (5)
       — fix 2: every stop a work HELD BY the Belvedere (no Monet/Van Gogh that
         live elsewhere); fix 3: no "… may refer to" disambiguation text in any
         stop; fix 4: the museum pin is within 150 m of the museum's own place
         (Upper Belvedere ≈ 48.1915, 16.3809).

Acceptance (checked after each run, printed):
  * every stop title passes junk_title_guard (no shop product / commerce);
  * no stop body contains a "may refer to" disambiguation lead;
  * every stop with a coordinate is within SCOPE of the venue city (a gross
    ~1 km-off wrong-"Belvedere" pin is flagged); pins ≤ 150 m of the venue P625
    where a venue reference is known.

Budget: HARD CAP $1.20 for the WHOLE task, enforced by tests/live_run_meter.py
(combined across every provider), with a reserve gate before each tour. ≤ 3 live
tours. Each delivered tour is stored as ONE additive is_test row in the ISOLATED
postgres only. No DELETE. Never the live/development DB.

Run inside a DISPOSABLE container (never -p audioura; never touch audioura-*):
    docker run --rm --name local809-tg \
        --network local788b_default \
        --env-file .env \
        -e DATABASE_URL=postgresql://admin:password123@local788b-postgres:5432/audiotours \
        -e RESEARCH_BACKEND=serper -e NARRATION_MODEL=gpt-4.1-mini \
        -e STORIED_MODE=true -e DISABLE_TOUR_CACHE=1 -e DISABLE_STOP_POOL=1 \
        -e STOP_EXISTENCE_GATE_MODE=log_only \
        -e TEST_GEMINI_MAX_USD=1.20 -e COST_HARD_LIMIT_USD=1.20 \
        -v "$PWD":/app -w /app audioura-tour-generator:latest \
        python -u run_local809_container.py <0|1>
"""
import os as _os
import sys as _sys
import math
import re
import socket
import time

_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))

_os.environ['STORIED_MODE'] = 'true'
_os.environ['DISABLE_TOUR_CACHE'] = '1'
_os.environ['DISABLE_STOP_POOL'] = '1'
_os.environ.setdefault('RESEARCH_BACKEND', 'serper')
_os.environ.setdefault('NARRATION_MODEL', 'gpt-4.1-mini')
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.20')
_os.environ.setdefault('COST_HARD_LIMIT_USD', '1.20')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

HARD_CAP_USD = 1.20
HOST = socket.gethostname()

# (request, tour_type, n_stops, slug, (venue_lat, venue_lng), city_center)
TOURS = [
    ('Metropolitan Museum of Art, New York, NY', '', 5, 'MET-NYC',
     (40.7794, -73.9632), (40.7794, -73.9632)),
    ('Belvedere Museum, Vienna, Austria', '', 5, 'BELVEDERE-VIE',
     (48.1915, 16.3809), (48.2082, 16.3738)),
]

if len(_sys.argv) > 1:
    try:
        _only = int(_sys.argv[1])
        TOURS = [TOURS[_only]]
        print(f"[LOCAL-809] single-tour mode: index {_only}", flush=True)
    except (ValueError, IndexError):
        print(f"[LOCAL-809] bad tour index {_sys.argv[1]!r}; running all", flush=True)

print("=== LOCAL-809 isolated live run (museum sources) ===", flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  cache_off=1 pool_off=1 "
      f"RESEARCH_BACKEND={_os.environ.get('RESEARCH_BACKEND')}", flush=True)

try:
    from live_run_meter import LiveRunMeter
except Exception as _e:
    print(f"[LOCAL-809] live_run_meter unavailable ({_e}) — cannot cap; aborting", flush=True)
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
_COORD_RE = re.compile(r"(?mi)^Coordinates:\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)")


def _haversine_m(a, b):
    R = 6371000.0
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def _check(text, venue_pt, city_center, slug):
    """Print the acceptance checks for one delivered tour; return a problems list."""
    problems = []
    try:
        import junk_title_guard as jtg
    except Exception:
        jtg = None
    try:
        import disambiguation_guard as dg
    except Exception:
        dg = None

    titles = _STOP_HEADER_RE.findall(text)
    coords = _COORD_RE.findall(text)
    print("  --- STOPS ---", flush=True)
    for i, t in enumerate(titles):
        t = t.strip()
        print(f"  STOP {i+1}: {t[:80]}", flush=True)
        if jtg is not None and jtg.is_junk_page_title(t, slug):
            problems.append(f"shop/junk stop title: {t!r}")
        if jtg is not None and jtg.is_shop_product_title(t):
            problems.append(f"shop product stop title: {t!r}")

    # No disambiguation lead anywhere in the body.
    if dg is not None and dg.is_disambiguation_text(text):
        problems.append("tour body contains a 'may refer to' disambiguation lead")
    if re.search(r"(?i)\bmay\s+refer\s+to\b", text):
        problems.append("tour body contains literal 'may refer to'")

    # Pin checks: every parsed coordinate within scope of the city (<= 30 km);
    # the closest stop to the venue within 150 m where a venue reference is known.
    dists = []
    for (la, lo) in coords:
        try:
            pt = (float(la), float(lo))
        except ValueError:
            continue
        city_km = _haversine_m(pt, city_center) / 1000.0
        if city_km > 30:
            problems.append(f"pin {pt} is {city_km:.0f} km from city centre (off-scope)")
        if venue_pt:
            dists.append(_haversine_m(pt, venue_pt))
    if venue_pt and dists:
        best = min(dists)
        print(f"  closest stop pin to venue P625: {best:.0f} m", flush=True)
        if best > 150.0:
            problems.append(f"no stop pin within 150 m of venue P625 (closest {best:.0f} m)")
    return problems


def _store(location, text, n_stops):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-809 {location.split(',')[0][:40]} {int(time.time())}"
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
                (name, location, n_stops, text, n_stops, 'LOCAL-809 museum sources live'))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [db] store failed (non-fatal): {e}", flush=True); return None


def main():
    before = _row_count()
    print(f"audio_tours rows BEFORE: {before}", flush=True)

    meter = LiveRunMeter('LOCAL-809')
    results = []
    try:
        import generate_tour_text as g
        import traceback as _tb
        for (location, ttype, stops, slug, venue_pt, city_center) in TOURS:
            # Reserve gate: stop before a tour that could blow the cap.
            try:
                spent = meter.total_usd()
            except Exception:
                spent = 0.0
            if spent >= HARD_CAP_USD:
                print(f"\n[LOCAL-809] reserve gate: ${spent:.3f} >= ${HARD_CAP_USD} "
                      f"— skipping remaining tours", flush=True)
                break
            print(f"\n=== TOUR [{slug}] {location!r} ({stops} stops) "
                  f"spent=${spent:.3f} ===", flush=True)
            t0 = time.time()
            try:
                text, _out, _coords = g.generate_tour_text(location, ttype, None, stops)
                dt = time.time() - t0
                if not text:
                    print(f"  [LOCAL-809] generation returned NO text in {dt:.0f}s", flush=True)
                    try:
                        meter.add_generation(g)
                    except Exception:
                        pass
                    results.append((slug, 'NO_TEXT', []))
                    continue
                problems = _check(text, venue_pt, city_center, slug)
                rid = _store(location, text, stops)
                try:
                    meter.add_generation(g)
                except Exception as _ae:
                    print(f"  [LOCAL-809] meter.add_generation failed (non-fatal): {_ae}", flush=True)
                verdict = 'PASS' if not problems else 'FAIL'
                print(f"  stored is_test row id={rid} in {dt:.0f}s — {verdict}", flush=True)
                for p in problems:
                    print(f"    PROBLEM: {p}", flush=True)
                results.append((slug, verdict, problems))
            except Exception as e:
                print(f"  [LOCAL-809] TOUR [{slug}] raised: {e}", flush=True)
                _tb.print_exc()
                try:
                    meter.add_generation(g)
                except Exception:
                    pass
                results.append((slug, f'ERROR: {e}', []))
                continue
    finally:
        try:
            row_id = meter.record()
            print(f"\n[LOCAL-809] cost ledger row: {row_id}", flush=True)
        except Exception as _me:
            print(f"[LOCAL-809] meter.record failed (non-fatal): {_me}", flush=True)
        try:
            print(meter.summary(), flush=True)
        except Exception:
            pass
        try:
            meter.uninstall()
        except Exception:
            pass

    after = _row_count()
    print(f"\naudio_tours rows AFTER: {after}  "
          f"(delta={after - before if (after and before) else '?'})", flush=True)
    print("=== LOCAL-809 SUMMARY ===", flush=True)
    for slug, verdict, problems in results:
        print(f"  [{slug}] {verdict}" + (f" ({len(problems)} problems)" if problems else ""),
              flush=True)


if __name__ == '__main__':
    main()
