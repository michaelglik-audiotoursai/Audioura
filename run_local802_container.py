"""run_local802_container.py — LOCAL-802 live acceptance (ISOLATED container).

The three P1-flagged requests, re-run on the CHEAP arm (NARRATION_MODEL=
gpt-4.1-mini, RESEARCH_BACKEND=serper), to prove the LOCAL-802 fixes end to end:

  0. b1  "Massage and spa near Ben Thanh Market, Ho Chi Minh City"            (3)
         — off-topic reality-TV ("The Race") passage must be gone; the places
           path should widen once before delivering fewer than 3 stops.
  1. d3  "Seafood restaurants in Mui Ne, Vietnam"                             (3)
         — the Permian–Triassic extinction passage must be gone; the seafood
           stops stay.
  2. r2  "Arnold Arboretum, Boston"                                          (4)
         — the Visitor Center and the Hunnewell Building must NOT both ship as
           stops (same building); the Rose Garden stop must be about the
           Arboretum, not the White House.

LEAD NOTE (Oct 28): Gemini prepaid credit is DEPLETED. Every tour runs with
RESEARCH_BACKEND=serper and NO Gemini grounding. If a step still needs Gemini,
report UNPROVEN instead of retrying.

Budget: HARD CAP $1.20 for the WHOLE task (combined across every provider),
enforced by tests/live_run_meter.py. At most 4 live tours. Each delivered tour
is stored as ONE additive is_test row. No DELETE.

Run inside an isolated container only (OWN project -p local802; never -p
audioura; never touch audioura-*):
    docker run --rm --name local802-tg \
        --network local802_default \
        --env-file .env \
        -e DATABASE_URL=postgresql://admin:password123@local802-postgres:5432/audiotours \
        -e NARRATION_MODEL=gpt-4.1-mini -e RESEARCH_BACKEND=serper \
        -e STORIED_MODE=true -e DISABLE_TOUR_CACHE=1 -e DISABLE_STOP_POOL=1 \
        -e STOP_EXISTENCE_GATE_MODE=log_only \
        -e TEST_GEMINI_MAX_USD=1.20 -e COST_HARD_LIMIT_USD=1.20 \
        -v "$PWD":/app -w /app audioura-tour-generator:latest \
        python -u run_local802_container.py <0|1|2>
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
# Cheap arm (LEAD: serper only, Gemini depleted).
_os.environ.setdefault('NARRATION_MODEL', 'gpt-4.1-mini')
_os.environ.setdefault('RESEARCH_BACKEND', 'serper')
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.20')
_os.environ.setdefault('COST_HARD_LIMIT_USD', '1.20')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

HARD_CAP_USD = 1.20
HOST = socket.gethostname()

TOURS = [
    ('Massage and spa near Ben Thanh Market, Ho Chi Minh City', '', 3, 'b1-BENTHANH-SPA'),
    ('Seafood restaurants in Mui Ne, Vietnam', '', 3, 'd3-MUINE-SEAFOOD'),
    ('Arnold Arboretum, Boston', '', 4, 'r2-ARBORETUM'),
]

if len(_sys.argv) > 1:
    try:
        _only = int(_sys.argv[1])
        TOURS = [TOURS[_only]]
        print(f"[LOCAL-802] single-tour mode: index {_only}", flush=True)
    except (ValueError, IndexError):
        print(f"[LOCAL-802] bad tour index {_sys.argv[1]!r}; running all", flush=True)

print("=== LOCAL-802 isolated live run (cheap arm: gpt-4.1-mini + serper) ===", flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  cache_off=1 pool_off=1  STORIED_MODE=true "
      f"RESEARCH_BACKEND={_os.environ.get('RESEARCH_BACKEND')}", flush=True)

try:
    from live_run_meter import LiveRunMeter
except Exception as _e:
    print(f"[LOCAL-802] live_run_meter unavailable ({_e}) — cannot cap; aborting", flush=True)
    _sys.exit(2)


def _conn():
    import psycopg2
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=_os.environ.get('DB_HOST', 'local802-postgres'),
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

# [LOCAL-802] Off-topic markers the P1 run shipped — must NOT appear now.
_OFFTOPIC_MARKERS = [
    "Permian", "Triassic", "extinction", "marine species",
    "The Race", "42,000", "three continents",
    "Ellen Wilson", "White House", "Woodrow Wilson",
]


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


def _check_offtopic(text):
    hits = [m for m in _OFFTOPIC_MARKERS if m.lower() in text.lower()]
    if hits:
        print(f"  [LOCAL-802] !! OFF-TOPIC MARKERS STILL PRESENT: {hits}", flush=True)
    else:
        print("  [LOCAL-802] OK — no off-topic P1 markers in delivered text", flush=True)
    return hits


def _check_same_building(titles):
    folded = [re.sub(r'[^a-z]', '', t.lower()) for t in titles]
    vc = any('visitorcenter' in f for f in folded)
    hb = any('hunnewellbuilding' in f for f in folded)
    if vc and hb:
        print("  [LOCAL-802] !! BOTH Visitor Center AND Hunnewell Building present "
              "(same building shipped twice)", flush=True)
        return False
    print("  [LOCAL-802] OK — Visitor Center / Hunnewell not both present", flush=True)
    return True


def _store(location, text, n_stops):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-802 {location.split(',')[0][:40]} {int(time.time())}"
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
                (name, location, n_stops, text, n_stops, 'LOCAL-802 cheap-arm live'))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [db] store failed: {e}", flush=True); return None


def main():
    before = _row_count()
    print(f"audio_tours rows BEFORE: {before}", flush=True)

    meter = LiveRunMeter('LOCAL-802')
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
                    print(f"  [LOCAL-802] generation returned NO text "
                          f"(clean-fail) in {dt:.0f}s; evidence={_ev}", flush=True)
                    try:
                        meter.add_generation(g)
                    except Exception:
                        pass
                    results.append((slug, 'NO_TEXT (clean-fail)', 0))
                    continue
                titles = _report_stops(text)
                n = len(titles)
                offtopic = _check_offtopic(text)
                if slug.startswith('r2'):
                    _check_same_building(titles)
                rid = _store(location, text, stops)
                try:
                    meter.add_generation(g)
                except Exception as _ae:
                    print(f"  [LOCAL-802] meter.add_generation failed (non-fatal): {_ae}", flush=True)
                print(f"  stored is_test row id={rid}; delivered {n}/{stops} stop(s) "
                      f"in {dt:.0f}s; offtopic={offtopic}", flush=True)
                results.append((slug, f'{n}/{stops} stops offtopic={len(offtopic)}', n))
            except Exception as e:
                print(f"  [LOCAL-802] TOUR [{slug}] raised: {e}", flush=True)
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
            print(f"\n[LOCAL-802] cost ledger row: {row_id}", flush=True)
        except Exception as _me:
            print(f"[LOCAL-802] meter.record failed (non-fatal): {_me}", flush=True)
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
    print("=== LOCAL-802 SUMMARY ===", flush=True)
    for slug, status, n in results:
        print(f"  [{slug}] {status}", flush=True)


if __name__ == '__main__':
    main()
