"""run_local805_container.py — LOCAL-805 live acceptance (ISOLATED container).

Proves the near-landmark routing fix end to end on the CHEAP arm
(NARRATION_MODEL=gpt-4.1-mini, RESEARCH_BACKEND=serper — Gemini credit depleted):

  0. b1  "Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City"  (3)
         — the ticket's exact field defect. Must route to the PLACES path (not
           WALKING) and deliver real spas within ~1.5 km of Ben Thanh Market.
  1.     "coffee near Boston Common"                                           (3)
         — business subject + landmark centre; 3 real cafés within ~1.5 km of
           Boston Common.

Each delivered stop is Serper-Places-checked for distance from the geocoded
landmark centre (verify step below). The landmark itself must NOT be a stop.

LEAD NOTE: Gemini prepaid credit is DEPLETED. Every tour runs RESEARCH_BACKEND=
serper, NO Gemini grounding. If a step still needs Gemini, report UNPROVEN.

Budget: HARD CAP $1.00 for the WHOLE task (combined across every provider),
enforced by tests/live_run_meter.py. At most 3 live tours. Each delivered tour is
stored as ONE additive is_test row in the ISOLATED DB. No DELETE. Live DB never
written.

Run inside an isolated container only (OWN project -p local805; never -p
audioura; never touch audioura-*):

    docker network create local805_net
    docker run -d --name local805-postgres --network local805_net \
        -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=password123 \
        -e POSTGRES_DB=audiotours postgres:15
    docker run --rm --name local805-tg --network local805_net \
        --env-file .env \
        -e DATABASE_URL=postgresql://admin:password123@local805-postgres:5432/audiotours \
        -e NARRATION_MODEL=gpt-4.1-mini -e RESEARCH_BACKEND=serper \
        -e STORIED_MODE=true -e DISABLE_TOUR_CACHE=1 -e DISABLE_STOP_POOL=1 \
        -e STOP_EXISTENCE_GATE_MODE=log_only \
        -e TEST_GEMINI_MAX_USD=1.00 -e COST_HARD_LIMIT_USD=1.00 \
        -v "$PWD":/app -w /app audioura-tour-generator:latest \
        python -u run_local805_container.py <0|1>
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
_os.environ.setdefault('NARRATION_MODEL', 'gpt-4.1-mini')
_os.environ.setdefault('RESEARCH_BACKEND', 'serper')
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.00')
_os.environ.setdefault('COST_HARD_LIMIT_USD', '1.00')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

HARD_CAP_USD = 1.00
HOST = socket.gethostname()

# (request, tour_type, n_stops, slug, landmark-for-distance-check)
TOURS = [
    ('Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City',
     '', 3, 'b1-BENTHANH-SPA', 'Ben Thanh Market, Ho Chi Minh City'),
    ('coffee near Boston Common',
     '', 3, 'coffee-BOSTON-COMMON', 'Boston Common, Boston, MA'),
]

if len(_sys.argv) > 1:
    try:
        _only = int(_sys.argv[1])
        TOURS = [TOURS[_only]]
        print(f"[LOCAL-805] single-tour mode: index {_only}", flush=True)
    except (ValueError, IndexError):
        print(f"[LOCAL-805] bad tour index {_sys.argv[1]!r}; running all", flush=True)

print("=== LOCAL-805 isolated live run (cheap arm: gpt-4.1-mini + serper) ===", flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  cache_off=1 pool_off=1  STORIED_MODE=true "
      f"RESEARCH_BACKEND={_os.environ.get('RESEARCH_BACKEND')}", flush=True)

try:
    from live_run_meter import LiveRunMeter
except Exception as _e:
    print(f"[LOCAL-805] live_run_meter unavailable ({_e}) — cannot cap; aborting", flush=True)
    _sys.exit(2)


def _conn():
    import psycopg2
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=_os.environ.get('DB_HOST', 'local805-postgres'),
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


def _haversine_km(a, b):
    if not a or not b:
        return float('inf')
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi = math.radians(b[0] - a[0]); dl = math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def _geocode(name):
    """Best-effort geocode of the landmark centre via places_search's geocoder."""
    try:
        import places_search as ps
        c = ps._geocode_scope_center(name) if hasattr(ps, '_geocode_scope_center') else None
        if c:
            return (float(c[0]), float(c[1]))
    except Exception:
        pass
    try:
        from stop_existence_gate import _geocode_scope_center as _g
        c = _g(name)
        if c:
            return (float(c[0]), float(c[1]))
    except Exception:
        pass
    return None


def _report_stops(text):
    print("  --- STOPS ---", flush=True)
    titles = _STOP_HEADER_RE.findall(text)
    coords = _COORD_RE.findall(text)
    addrs = _ADDR_RE.findall(text)
    parsed = []
    for i, t in enumerate(titles):
        c = coords[i].strip() if i < len(coords) else ''
        a = addrs[i].strip() if i < len(addrs) else ''
        latlng = None
        m = re.search(r'(-?\d+\.\d+)[,\s]+(-?\d+\.\d+)', c)
        if m:
            latlng = (float(m.group(1)), float(m.group(2)))
        parsed.append((t.strip(), a, latlng))
        print(f"  STOP {i+1}: {t.strip()[:80]}", flush=True)
        print(f"         addr: {a[:90]}", flush=True)
        print(f"         coords: {c[:40]}", flush=True)
    return parsed


def _check_distance(parsed, landmark):
    centre = _geocode(landmark)
    if not centre:
        print(f"  [LOCAL-805] could not geocode landmark {landmark!r} — distance UNPROVEN", flush=True)
        return
    print(f"  [LOCAL-805] landmark centre {landmark!r} = {centre}", flush=True)
    lm_fold = re.sub(r'[^a-z]', '', landmark.split(',')[0].lower())
    for title, _addr, latlng in parsed:
        tfold = re.sub(r'[^a-z]', '', title.lower())
        if lm_fold and lm_fold in tfold:
            print(f"  [LOCAL-805] !! landmark itself appears as a STOP: {title!r}", flush=True)
        if latlng:
            km = _haversine_km(centre, latlng)
            flag = 'OK' if km <= 1.5 else ('wide' if km <= 3.0 else 'FAR')
            print(f"  [LOCAL-805] {flag}  {km:.2f} km  {title[:50]}", flush=True)
        else:
            print(f"  [LOCAL-805] (no coords) {title[:50]}", flush=True)


def _store(location, text, n_stops):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-805 {location.split(',')[0][:40]} {int(time.time())}"
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
                (name, location, n_stops, text, n_stops, 'LOCAL-805 near-landmark live'))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [db] store failed: {e}", flush=True); return None


def main():
    before = _row_count()
    print(f"audio_tours rows BEFORE: {before}", flush=True)

    meter = LiveRunMeter('LOCAL-805')
    results = []
    try:
        import generate_tour_text as g
        import traceback as _tb
        for (location, ttype, stops, slug, landmark) in TOURS:
            print(f"\n=== TOUR [{slug}] {location!r} tour_type={ttype!r} "
                  f"({stops} stops) ===", flush=True)
            # Prove the routing deterministically BEFORE spending anything.
            cat = g._classify_tour_category(location, ttype)
            print(f"  [LOCAL-805] classified category = {cat!r} "
                  f"(expect 'restaurant' = places path)", flush=True)
            t0 = time.time()
            try:
                text, _out, coords = g.generate_tour_text(location, ttype, None, stops)
                dt = time.time() - t0
                if not text:
                    try:
                        _ev = dict(getattr(g, '_LAST_CLEAN_FAIL_EVIDENCE', {}) or {})
                    except Exception:
                        _ev = {}
                    print(f"  [LOCAL-805] generation returned NO text "
                          f"(clean-fail) in {dt:.0f}s; evidence={_ev}", flush=True)
                    try:
                        meter.add_generation(g)
                    except Exception:
                        pass
                    results.append((slug, 'NO_TEXT (clean-fail)', 0))
                    continue
                parsed = _report_stops(text)
                _check_distance(parsed, landmark)
                rid = _store(location, text, stops)
                try:
                    meter.add_generation(g)
                except Exception as _ae:
                    print(f"  [LOCAL-805] meter.add_generation failed (non-fatal): {_ae}", flush=True)
                print(f"  stored is_test row id={rid}; delivered {len(parsed)}/{stops} "
                      f"stop(s) in {dt:.0f}s", flush=True)
                results.append((slug, f'{len(parsed)}/{stops} stops cat={cat}', len(parsed)))
            except Exception as e:
                print(f"  [LOCAL-805] TOUR [{slug}] raised: {e}", flush=True)
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
            print(f"\n[LOCAL-805] cost ledger row: {row_id}", flush=True)
        except Exception as _me:
            print(f"[LOCAL-805] meter.record failed (non-fatal): {_me}", flush=True)
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
    print("=== LOCAL-805 SUMMARY ===", flush=True)
    for slug, status, n in results:
        print(f"  [{slug}] {status}", flush=True)


if __name__ == '__main__':
    main()
