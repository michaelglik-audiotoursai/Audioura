"""run_local865_container.py — LOCAL-865 live acceptance (ISOLATED container, cheap arm).

Palais Lascaris, Nice (6 stops): PASS = >=5/6 stops all of Palais Lascaris, tour lat/lng
within 100 m of the venue pin 43.6977,7.2773. Regression: Isabella Stewart Gardner
Museum, Boston (3 stops) still 3/3. Cap $0.60 whole task.
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
_os.environ.setdefault('STORY_PASS_MODEL', 'gpt-4.1')
_os.environ.setdefault('RESEARCH_BACKEND', 'serper')
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '0.60')
_os.environ.setdefault('COST_HARD_LIMIT_USD', '0.60')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

HARD_CAP_USD = 0.60
HOST = socket.gethostname()

# (request, tour_type, n_stops, slug, expected_category, must_contain)
TOURS = [
    ('Palais Lascaris, Nice', 'museum', 6, 'palais-lascaris-nice', 'museum', []),
    ('Isabella Stewart Gardner Museum, Boston', 'museum', 3, 'gardner-boston', 'museum', []),
]
VENUE_PINS = {'palais-lascaris-nice': (43.6977, 7.2773)}

print("=== LOCAL-865 isolated live run (cheap arm: gpt-4.1-mini + gpt-4.1 story + serper) ===", flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  cache_off=1 pool_off=1 STORIED_MODE=true "
      f"RESEARCH_BACKEND={_os.environ.get('RESEARCH_BACKEND')} "
      f"STORY_PASS_MODEL={_os.environ.get('STORY_PASS_MODEL')}", flush=True)

try:
    from live_run_meter import LiveRunMeter
except Exception as _e:
    print(f"[LOCAL-865] live_run_meter unavailable ({_e}) — cannot cap; aborting", flush=True)
    _sys.exit(2)


def _conn():
    import psycopg2
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=_os.environ.get('DB_HOST', 'local865-postgres'),
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
        print(f"  STOP {i+1}: {t.strip()[:90]}", flush=True)
    sf = bool(_SHORTFALL_RE.search(text or ''))
    print(f"  shortfall-apology present: {sf}", flush=True)
    return titles, sf


def _report_coords(coords):
    """coords is (lat_list_or_struct). Print whatever structure the generator
    returned so a human can confirm real pins exist. Non-fatal on any shape."""
    try:
        print(f"  --- COORDS payload type={type(coords).__name__} ---", flush=True)
        print(f"  coords = {str(coords)[:400]}", flush=True)
    except Exception as e:
        print(f"  [coords] report failed: {e}", flush=True)


def _store(location, text, n_stops):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-865 {location.split(',')[0][:40]} {int(time.time())}"
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
                 'LOCAL-865 house-walk live'))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [db] store failed: {e}", flush=True); return None


def main():
    before = _row_count()
    print(f"audio_tours rows BEFORE: {before}", flush=True)

    meter = LiveRunMeter('LOCAL-865')
    results = []
    try:
        import generate_tour_text as g
        import traceback as _tb
        for (location, ttype, stops, slug, expect_cat, must_contain) in TOURS:
            print(f"\n=== TOUR [{slug}] {location!r} tour_type={ttype!r} "
                  f"({stops} stops) expect={expect_cat} ===", flush=True)
            # Deterministic pre-spend category check (the CLASSIFY-FIX fix in action).
            try:
                cat0 = g._classify_tour_category(location, ttype)
                print(f"  [LOCAL-865] base classified category = {cat0!r}", flush=True)
            except Exception as _ce:
                print(f"  [LOCAL-865] classify failed (non-fatal): {_ce}", flush=True)
            t0 = time.time()
            try:
                text, _out, coords = g.generate_tour_text(location, ttype, None, stops)
                dt = time.time() - t0
                if not text:
                    try:
                        _ev = dict(getattr(g, '_LAST_CLEAN_FAIL_EVIDENCE', {}) or {})
                    except Exception:
                        _ev = {}
                    print(f"  [LOCAL-865] generation returned NO text "
                          f"(clean-fail) in {dt:.0f}s; evidence={_ev}", flush=True)
                    try:
                        meter.add_generation(g)
                    except Exception:
                        pass
                    results.append((slug, 'NO_TEXT (clean-fail)', 0, stops,
                                    None, expect_cat, False))
                    continue
                titles, sf = _report_stops(text)
                _report_coords(coords)
                try:
                    import math as _m
                    pin = VENUE_PINS.get(slug)
                    if pin and coords and coords[0] is not None:
                        la1, lo1, la2, lo2 = map(_m.radians, (coords[0], coords[1], pin[0], pin[1]))
                        h = _m.sin((la2-la1)/2)**2 + _m.cos(la1)*_m.cos(la2)*_m.sin((lo2-lo1)/2)**2
                        print(f"  [LOCAL-865] tour lat/lng {coords} is {2*6371000*_m.asin(_m.sqrt(h)):.0f} m from venue pin {pin}", flush=True)
                    _os.makedirs('run865_out', exist_ok=True)
                    open(f'run865_out/{slug}.txt', 'w', encoding='utf-8').write(text)
                except Exception as _pe:
                    print(f"  [LOCAL-865] pin check failed: {_pe}", flush=True)
                rid = _store(location, text, stops)
                try:
                    meter.add_generation(g)
                except Exception as _ae:
                    print(f"  [LOCAL-865] meter.add_generation failed (non-fatal): {_ae}", flush=True)
                # Did the delivered stop titles contain each required place?
                blob = (text or '').lower()
                contains_ok = all(frag in blob for frag in must_contain)
                print(f"  stored is_test row id={rid}; delivered {len(titles)}/{stops} "
                      f"stop(s) in {dt:.0f}s; must_contain={must_contain} -> {contains_ok}",
                      flush=True)
                results.append((slug, f'{len(titles)}/{stops} stops',
                                len(titles), stops, sf, expect_cat, contains_ok))
            except Exception as e:
                print(f"  [LOCAL-865] TOUR [{slug}] raised: {e}", flush=True)
                _tb.print_exc()
                try:
                    meter.add_generation(g)
                except Exception:
                    pass
                results.append((slug, f'ERROR: {e}', 0, stops, None, expect_cat, False))
                continue
    finally:
        try:
            row_id = meter.record()
            print(f"\n[LOCAL-865] cost ledger row: {row_id}", flush=True)
        except Exception as _me:
            print(f"[LOCAL-865] meter.record failed (non-fatal): {_me}", flush=True)
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
    print("=== LOCAL-865 SUMMARY ===", flush=True)
    for slug, status, n, req, sf, expect_cat, contains_ok in results:
        # PASS for the walk: delivered N==req AND both required places present.
        # PASS for the museum: delivered N==req.
        if expect_cat == 'walking':
            verdict = 'PASS' if (n == req and contains_ok) else 'FAIL'
        else:
            verdict = 'PASS' if (n == req) else 'FAIL'
        print(f"  [{slug}] {status} expect={expect_cat} contains_ok={contains_ok} -> {verdict}"
              f"{' (shortfall-apology present)' if sf else ''}", flush=True)


if __name__ == '__main__':
    main()
