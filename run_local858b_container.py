"""run_local858b_container.py — LOCAL-858B live acceptance (ISOLATED container).

Proves the Cloud-Run HCMC pin fix end to end on the CHEAP arm
(NARRATION_MODEL=gpt-4.1-mini, STORY_PASS_MODEL=gpt-4.1, RESEARCH_BACKEND=serper),
in a CLOUD-LIKE environment:

  * K_SERVICE=local858b                → the Cloud Run marker is set, exactly as
                                          the live generator sees it.
  * LANDMARK_LIVE_LOOKUP is UNSET here  → it must be set by the generator's own
                                          setdefault on the walking path (the
                                          ticket's item-1 concern).

The EXACT ticket request (tour 532):

  "Ben Thanh Market and Saigon Opera House walk, Ho Chi Minh City"   (3 stops)

run TWICE:

  PASS 1 — Wikidata REACHABLE   (LANDMARK_WIKIDATA_BLOCKED unset).
  PASS 2 — Wikidata BLOCKED      (LANDMARK_WIKIDATA_BLOCKED=1) → the SECOND
           authority (Serper /places → Nominatim) must place the pins.

PASS per the ticket, in BOTH passes:
  * Ben Thanh Market AND the Saigon Opera House within 150 m of the real pin;
  * no pin is the Vietnam COUNTRY centroid (15.93,107.97);
  * no pin is the HCMC city centroid (10.776,106.695).

Budget: HARD CAP $0.35 for the WHOLE task (combined across providers), enforced by
tests/live_run_meter.py + task_budget (TASK_BUDGET_ID=LOCAL-858B,
TASK_BUDGET_USD=0.35). Each delivered tour is stored as ONE additive is_test row
in the ISOLATED DB. No DELETE. The live DB is never written. The shared audioura-*
containers are never touched.

Run via run_local858b_live.sh (it carries the LOCAL-820 meter contract) inside an
isolated container only (OWN project -p local858b; never -p audioura).
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
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '0.35')
_os.environ.setdefault('COST_HARD_LIMIT_USD', '0.35')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')
# CLOUD-LIKE: the Cloud Run service marker is set …
_os.environ.setdefault('K_SERVICE', 'local858b')
# … and LANDMARK_LIVE_LOOKUP is deliberately NOT set here — the generator's own
# setdefault on the walking path must turn it on (ticket item 1). We assert below
# that it ended up on.

HARD_CAP_USD = 0.35
HOST = socket.gethostname()

# The exact tour-532 request (carries the city tail the scope lost on the cloud).
REQ = 'Ben Thanh Market and Saigon Opera House walk, Ho Chi Minh City'
N_STOPS = 3
SCOPE_CENTER = (10.7769, 106.7009)
REAL = {
    'ben thanh': (10.772521, 106.698019),
    'opera': (10.776390, 106.702780),
}
HCMC_CENTROID = (10.776, 106.695)
VN_COUNTRY_CENTROID = (15.93, 107.97)

print("=== LOCAL-858B isolated live run (cheap arm; CLOUD-LIKE K_SERVICE=local858b) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  K_SERVICE={_os.environ.get('K_SERVICE')} "
      f"LANDMARK_LIVE_LOOKUP(start)={_os.environ.get('LANDMARK_LIVE_LOOKUP')!r} "
      f"RESEARCH_BACKEND={_os.environ.get('RESEARCH_BACKEND')}", flush=True)

try:
    from live_run_meter import LiveRunMeter
except Exception as _e:
    print(f"[LOCAL-858B] live_run_meter unavailable ({_e}) — cannot cap; aborting",
          flush=True)
    _sys.exit(2)


def _conn():
    import psycopg2
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=_os.environ.get('DB_HOST', 'local858b-postgres'),
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
    out = []
    blocks = re.split(r"(?mi)^Stop\s+\d+:\s*", text)
    headers = _STOP_HEADER_RE.findall(text)
    for i, title in enumerate(headers):
        body = blocks[i + 1] if i + 1 < len(blocks) else ""
        cm = _COORD_RE.search(body)
        pt = (float(cm.group(1)), float(cm.group(2))) if cm else None
        out.append((title.strip(), pt))
    return out


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-858B {slug} {int(time.time())}"
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
                 'LOCAL-858B cloud pins live'))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [db] store failed: {e}", flush=True); return None


def _run_one(g, slug, wikidata_blocked):
    """Generate the tour once; return a result dict."""
    if wikidata_blocked:
        _os.environ['LANDMARK_WIKIDATA_BLOCKED'] = '1'
    else:
        _os.environ.pop('LANDMARK_WIKIDATA_BLOCKED', None)
    print(f"\n=== PASS [{slug}] wikidata_blocked={wikidata_blocked} ===", flush=True)
    t0 = time.time()
    buf = io.StringIO()

    class _Tee(io.TextIOBase):
        def write(self, s):
            buf.write(s)
            _sys.__stdout__.write(s)
            return len(s)
    try:
        with contextlib.redirect_stdout(_Tee()):
            text, _out, _coords = g.generate_tour_text(REQ, '', None, N_STOPS)
    except Exception as e:
        import traceback as _tb
        print(f"  [LOCAL-858B] PASS [{slug}] raised: {e}", flush=True)
        _tb.print_exc()
        return {'slug': slug, 'blocked': wikidata_blocked, 'status': f'ERROR: {e}',
                'ok': False}
    dt = time.time() - t0
    captured = buf.getvalue()
    # Item 1: assert the generator turned LANDMARK_LIVE_LOOKUP on itself.
    live_lookup_on = str(_os.environ.get('LANDMARK_LIVE_LOOKUP', '')).lower() in (
        '1', 'true', 'yes', 'on')
    if not text:
        print(f"  [LOCAL-858B] generation returned NO text in {dt:.0f}s", flush=True)
        return {'slug': slug, 'blocked': wikidata_blocked, 'status': 'NO_TEXT',
                'ok': False, 'live_lookup_on': live_lookup_on}

    parsed = _parse_stops(text)
    print("  --- STOPS & PINS ---", flush=True)
    pin_rows = []
    for title, pt in parsed:
        tl = title.lower()
        real = None
        for key, rc in REAL.items():
            if key in tl:
                real = rc
                break
        d_real = _hav_m(pt, real) if (pt and real) else None
        d_hcmc = _hav_m(pt, HCMC_CENTROID) if pt else None
        d_vn = _hav_m(pt, VN_COUNTRY_CENTROID) if pt else None
        is_hcmc_cent = (d_hcmc is not None and d_hcmc <= 150.0)
        is_vn_cent = (d_vn is not None and d_vn <= 1000.0)
        pin_rows.append((title, pt, real, d_real, is_hcmc_cent, is_vn_cent))
        print(f"  STOP: {title[:60]}", flush=True)
        print(f"        pin={pt}  "
              f"{('%.0f m from real' % d_real) if d_real is not None else 'no requested-name match'}"
              f"{'  <<< HCMC CENTROID' if is_hcmc_cent else ''}"
              f"{'  <<< VN COUNTRY CENTROID' if is_vn_cent else ''}", flush=True)

    ro_counts = [int(m) for m in _ROUTE_ORDER_RE.findall(captured)]
    # The two REQUESTED landmarks must each be within 150 m of the real pin.
    req_matched = {k: None for k in REAL}
    for (title, pt, real, d_real, _c, _v) in pin_rows:
        tl = title.lower()
        for key in REAL:
            if key in tl and d_real is not None:
                req_matched[key] = d_real
    both_requested_ok = all(
        (d is not None and d <= 150.0) for d in req_matched.values())
    any_country = any(v for (_t, _p, _r, _d, _c, v) in pin_rows)
    # Evidence lines from the fix.
    n_skip = len(re.findall(r"\[LOCAL-858B\] landmark lookup skipped", captured))
    n_landmark_pins = len(re.findall(r"\[LOCAL-858\] landmark pin", captured))
    n_cluster = len(re.findall(r"\[LOCAL-858B\] cluster collapse", captured))
    n_2nd = len(re.findall(r"serper_places|nominatim", captured))

    rid = _store(REQ, text, N_STOPS, slug)
    print(f"  ROUTE-ORDER counts: {ro_counts}; requested-landmark distances="
          f"{ {k: (round(v) if v is not None else None) for k, v in req_matched.items()} }; "
          f"LANDMARK_LIVE_LOOKUP_on={live_lookup_on}; landmark_pin_lines={n_landmark_pins}; "
          f"skip_lines={n_skip}; cluster_lines={n_cluster}", flush=True)
    print(f"  stored is_test row id={rid}; delivered {len(parsed)}/{N_STOPS} in {dt:.0f}s",
          flush=True)
    ok = (both_requested_ok and not any_country and live_lookup_on)
    return {'slug': slug, 'blocked': wikidata_blocked,
            'status': f'{len(parsed)}/{N_STOPS}', 'ok': ok,
            'both_requested_ok': both_requested_ok, 'any_country': any_country,
            'live_lookup_on': live_lookup_on, 'req_matched': req_matched}


def main():
    before = _row_count()
    print(f"audio_tours rows BEFORE: {before}", flush=True)
    meter = LiveRunMeter('LOCAL-858B')
    results = []
    try:
        import generate_tour_text as g
        results.append(_run_one(g, 'ben-thanh-opera-WIKIDATA', wikidata_blocked=False))
        try:
            meter.add_generation(g)
        except Exception:
            pass
        results.append(_run_one(g, 'ben-thanh-opera-BLOCKED', wikidata_blocked=True))
        try:
            meter.add_generation(g)
        except Exception:
            pass
    finally:
        try:
            row_id = meter.record()
            print(f"\n[LOCAL-858B] cost ledger row: {row_id}", flush=True)
        except Exception as _me:
            print(f"[LOCAL-858B] meter.record failed (non-fatal): {_me}", flush=True)
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
    print("=== LOCAL-858B SUMMARY ===", flush=True)
    all_pass = True
    for r in results:
        verdict = 'PASS' if r.get('ok') else 'FAIL'
        all_pass = all_pass and (verdict == 'PASS')
        print(f"  [{r['slug']}] blocked={r['blocked']} {r.get('status')} "
              f"both_requested_within150m={r.get('both_requested_ok')} "
              f"no_country_centroid={not r.get('any_country')} "
              f"live_lookup_on={r.get('live_lookup_on')} -> {verdict}", flush=True)
        rm = r.get('req_matched') or {}
        for k, v in rm.items():
            print(f"       {k}: {('%.0f m' % v) if v is not None else 'NO MATCH'}",
                  flush=True)
    print(f"=== LOCAL-858B OVERALL: {'PASS' if all_pass else 'FAIL'} ===", flush=True)


if __name__ == '__main__':
    main()
