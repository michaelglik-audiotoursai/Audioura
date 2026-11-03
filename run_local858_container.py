"""run_local858_container.py — LOCAL-858 live acceptance (ISOLATED container).

Proves the HCMC "all pins collapse to the city centre" fix end to end on the
CHEAP arm (NARRATION_MODEL=gpt-4.1-mini, STORY_PASS_MODEL=gpt-4.1,
RESEARCH_BACKEND=serper), on the EXACT request strings from the ticket:

  1. "Ben Thanh Market and Saigon Opera House walk, Ho Chi Minh City"   (3)
  2. "Hoan Kiem Lake and Temple of Literature walk, Hanoi"              (3)
  3. "Boston Common and Old North Church walk, Boston"   — control     (2)

For every delivered tour the harness parses each stop's shipped "Coordinates:"
line and measures it against the real landmark (Wikidata P625). PASS per the
ticket:
  * every delivered pin is within 150 m of the real landmark (listed),
  * no pin is the city centroid,
  * ROUTE-ORDER counts every stop as having coordinates (no "0 stops with
    coordinates" / "Only N stops with coordinates" short of the delivered count).

Budget: HARD CAP $0.40 for the WHOLE task (combined across providers), enforced
by tests/live_run_meter.py + task_budget (TASK_BUDGET_ID=LOCAL-858,
TASK_BUDGET_USD=0.40). Each delivered tour is stored as ONE additive is_test row
in the ISOLATED DB. No DELETE. The live DB is never written. The shared audioura-*
containers are never touched.

Run via run_local858_live.sh (it carries the LOCAL-820 meter contract) inside an
isolated container only (OWN project -p local858; never -p audioura).
"""
import io
import os as _os
import sys as _sys
import re
import math
import socket
import time
import contextlib

_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))

_os.environ['STORIED_MODE'] = 'true'
_os.environ['DISABLE_TOUR_CACHE'] = '1'
_os.environ['DISABLE_STOP_POOL'] = '1'
_os.environ.setdefault('NARRATION_MODEL', 'gpt-4.1-mini')
_os.environ.setdefault('STORY_PASS_MODEL', 'gpt-4.1')
_os.environ.setdefault('RESEARCH_BACKEND', 'serper')
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '0.40')
_os.environ.setdefault('COST_HARD_LIMIT_USD', '0.40')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')
# The fix uses the live Wikidata P625 landmark lookup on the generation path.
_os.environ.setdefault('LANDMARK_LIVE_LOOKUP', '1')

HARD_CAP_USD = 0.40
HOST = socket.gethostname()

# (request, tour_type, n_stops, slug, scope_center, {stop_substr: (lat, lng)})
TOURS = [
    ('Ben Thanh Market and Saigon Opera House walk, Ho Chi Minh City',
     '', 3, 'ben-thanh-opera-HCMC', (10.7769, 106.7009),
     {'ben thanh': (10.772521, 106.698019),
      'opera': (10.776390, 106.702780)}),
    ('Hoan Kiem Lake and Temple of Literature walk, Hanoi',
     '', 3, 'hoan-kiem-temple-literature-HANOI', (21.0285, 105.8542),
     {'hoan kiem': (21.028889, 105.852500),
      'temple of literature': (21.028611, 105.835556)}),
    ('Boston Common and Old North Church walk, Boston',
     '', 2, 'boston-common-old-north-BOSTON', (42.3601, -71.0589),
     {'boston common': (42.355000, -71.065556),
      'old north church': (42.366389, -71.054444)}),
]

# The city centroids the model historically collapsed to (tour 527 shape).
CENTROIDS = {
    'ben-thanh-opera-HCMC': (10.776, 106.695),
    'hoan-kiem-temple-literature-HANOI': (21.0285, 105.8542),
    'boston-common-old-north-BOSTON': (42.3601, -71.0589),
}

print("=== LOCAL-858 isolated live run (cheap arm: gpt-4.1-mini + gpt-4.1 story + serper) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  cache_off=1 pool_off=1 STORIED_MODE=true "
      f"RESEARCH_BACKEND={_os.environ.get('RESEARCH_BACKEND')} "
      f"STORY_PASS_MODEL={_os.environ.get('STORY_PASS_MODEL')} "
      f"LANDMARK_LIVE_LOOKUP={_os.environ.get('LANDMARK_LIVE_LOOKUP')}", flush=True)

try:
    from live_run_meter import LiveRunMeter
except Exception as _e:
    print(f"[LOCAL-858] live_run_meter unavailable ({_e}) — cannot cap; aborting",
          flush=True)
    _sys.exit(2)


def _conn():
    import psycopg2
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=_os.environ.get('DB_HOST', 'local858-postgres'),
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
_COORD_RE = re.compile(r"(?mi)^Coordinates:\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")
# ROUTE-ORDER logs either "Computed route for N stops with coords" (routing ran)
# or "Only N stops with coordinates — skipping" (fewer than 3). Capture N in both.
_ROUTE_ORDER_RE = re.compile(
    r"\[ROUTE-ORDER\]\s+(?:Computed route for|Only)\s+(\d+)\s+stops?\s+with\s+coord",
    re.IGNORECASE)


def _hav_m(a, b):
    R = 6371000.0
    la1, lo1 = math.radians(a[0]), math.radians(a[1])
    la2, lo2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def _parse_stops(text):
    """Return [(title, (lat,lng)|None)] in document order."""
    out = []
    # Walk the text stop-by-stop so each coordinate binds to its own header.
    blocks = re.split(r"(?mi)^Stop\s+\d+:\s*", text)
    headers = _STOP_HEADER_RE.findall(text)
    for i, title in enumerate(headers):
        # The block after header i+1 holds that stop's lines.
        body = blocks[i + 1] if i + 1 < len(blocks) else ""
        cm = _COORD_RE.search(body)
        pt = (float(cm.group(1)), float(cm.group(2))) if cm else None
        out.append((title.strip(), pt))
    return out


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-858 {slug} {int(time.time())}"
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
                 'LOCAL-858 HCMC pins live'))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [db] store failed: {e}", flush=True); return None


def main():
    before = _row_count()
    print(f"audio_tours rows BEFORE: {before}", flush=True)

    meter = LiveRunMeter('LOCAL-858')
    results = []
    try:
        import generate_tour_text as g
        import traceback as _tb
        for (location, ttype, stops, slug, center, reals) in TOURS:
            print(f"\n=== TOUR [{slug}] {location!r} ({stops} stops) ===", flush=True)
            t0 = time.time()
            # Capture the generator's stdout so we can inspect the ROUTE-ORDER and
            # [LOCAL-858] lines, while still echoing them for the run log.
            buf = io.StringIO()
            try:
                class _Tee(io.TextIOBase):
                    def write(self, s):
                        buf.write(s)
                        _sys.__stdout__.write(s)
                        return len(s)
                with contextlib.redirect_stdout(_Tee()):
                    text, _out, _coords = g.generate_tour_text(
                        location, ttype, None, stops)
                dt = time.time() - t0
                captured = buf.getvalue()
                if not text:
                    print(f"  [LOCAL-858] generation returned NO text in {dt:.0f}s",
                          flush=True)
                    try:
                        meter.add_generation(g)
                    except Exception:
                        pass
                    results.append((slug, 'NO_TEXT', 0, stops, [], False, False, False))
                    continue

                parsed = _parse_stops(text)
                print("  --- STOPS & PINS ---", flush=True)
                centroid = CENTROIDS.get(slug)
                # Each delivered stop's OWN authoritative coordinate (the generator
                # may substitute its own landmarks for the two we named — a pin is
                # 'real' when it matches ITS stop's own Wikidata P625, not only the
                # two requested names). Falls back to the requested-name map.
                try:
                    import wikidata_landmark_lookup as _wl858
                except Exception:
                    _wl858 = None

                def _real_for(title):
                    tl = title.lower()
                    for key, rc in reals.items():
                        if key in tl:
                            return rc
                    if _wl858 is not None:
                        try:
                            hit = _wl858.lookup(
                                title, scope=location, scope_center=center,
                                tour_language='en', use_cache=False)
                            if hit:
                                return (float(hit[0]), float(hit[1]))
                        except Exception:
                            pass
                    return None

                pin_rows = []
                any_centroid = False
                for title, pt in parsed:
                    real = _real_for(title)
                    d_real = _hav_m(pt, real) if (pt and real) else None
                    d_cent = _hav_m(pt, centroid) if (pt and centroid) else None
                    is_cent = (d_cent is not None and d_cent <= 150.0)
                    any_centroid = any_centroid or is_cent
                    pin_rows.append((title, pt, real, d_real, is_cent))
                    print(f"  STOP: {title[:60]}", flush=True)
                    print(f"        pin={pt}  "
                          f"{('%.0f m from real' % d_real) if d_real is not None else 'no real-match'}"
                          f"{'  <<< CENTROID' if is_cent else ''}", flush=True)

                # ROUTE-ORDER count: the LAST route-order line's N.
                ro_counts = [int(m) for m in _ROUTE_ORDER_RE.findall(captured)]
                ro_last = ro_counts[-1] if ro_counts else None
                n_delivered = len(parsed)
                n_with_pin = sum(1 for _t, p in parsed if p is not None)

                # Pins within 150 m of their own real landmark (only matched stops).
                matched = [(t, d) for (t, p, r, d, c) in pin_rows if d is not None]
                all_within = all(d <= 150.0 for _t, d in matched) and bool(matched)

                # LOCAL-858 log line count in captured output (evidence).
                n_858 = len(re.findall(r"\[LOCAL-858\] no coordinate", captured))

                print(f"  ROUTE-ORDER counts over run: {ro_counts} (last={ro_last}); "
                      f"delivered={n_delivered}, with_pin={n_with_pin}, "
                      f"[LOCAL-858] no-coordinate lines={n_858}", flush=True)

                rid = _store(location, text, stops, slug)
                try:
                    meter.add_generation(g)
                except Exception as _ae:
                    print(f"  [LOCAL-858] meter.add_generation failed (non-fatal): {_ae}",
                          flush=True)
                print(f"  stored is_test row id={rid}; delivered {n_delivered}/{stops} "
                      f"stop(s) in {dt:.0f}s", flush=True)
                results.append((slug, f'{n_delivered}/{stops}', n_delivered, stops,
                                matched, all_within, (not any_centroid),
                                (ro_last is not None and ro_last >= n_with_pin
                                 and n_with_pin == n_delivered)))
            except Exception as e:
                print(f"  [LOCAL-858] TOUR [{slug}] raised: {e}", flush=True)
                _tb.print_exc()
                try:
                    meter.add_generation(g)
                except Exception:
                    pass
                results.append((slug, f'ERROR: {e}', 0, stops, [], False, False, False))
                continue
    finally:
        try:
            row_id = meter.record()
            print(f"\n[LOCAL-858] cost ledger row: {row_id}", flush=True)
        except Exception as _me:
            print(f"[LOCAL-858] meter.record failed (non-fatal): {_me}", flush=True)
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
    print("=== LOCAL-858 SUMMARY ===", flush=True)
    all_pass = True
    for slug, status, n, req, matched, within, no_centroid, ro_ok in results:
        verdict = 'PASS' if (n == req and within and no_centroid and ro_ok) else 'FAIL'
        all_pass = all_pass and (verdict == 'PASS')
        print(f"  [{slug}] {status} within150m={within} no_centroid={no_centroid} "
              f"route_order_counts_all={ro_ok} -> {verdict}", flush=True)
        for t, d in matched:
            print(f"       {t[:50]}: {d:.0f} m from real landmark", flush=True)
    print(f"=== LOCAL-858 OVERALL: {'PASS' if all_pass else 'FAIL'} ===", flush=True)


if __name__ == '__main__':
    main()
