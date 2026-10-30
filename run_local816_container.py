"""run_local816_container.py — LOCAL-816 live acceptance (ISOLATED container).

Proves the named-anchor walking-tour stop-count fix end to end on the CHEAP arm
(NARRATION_MODEL=gpt-4.1-mini, RESEARCH_BACKEND=serper):

  0.  "Trevi Fountain, Pantheon and Piazza Navona walking tour, Rome"   (5)
      — the catalog defect (847): the three named anchors leak into the
        containment scope, rejecting every replenishment candidate, so the tour
        shipped 4 of 5. With the fix the scope widens to "Rome" and replenishment
        can reach 5.
  1.  "Westminster walking tour, London"                               (5)
      — catalog defect (849): shipped 4 of 5. A real-district scope; must deliver
        5 real places.

Each tour MUST deliver the requested 5 stops (the whole point of LOCAL-816).

Budget: HARD CAP $0.60 for the WHOLE task (combined across every provider),
enforced by tests/live_run_meter.py. At most 2 live tours. Each delivered tour is
stored as ONE additive is_test row in the ISOLATED DB. No DELETE. Live DB never
written.

Run inside an isolated container only (OWN project -p local816; never -p
audioura; never touch audioura-*):

    docker network create local816_net
    docker run -d --name local816-postgres --network local816_net \
        -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=password123 \
        -e POSTGRES_DB=audiotours postgres:15
    docker run --rm --name local816-tg --network local816_net \
        --env-file .env \
        -e DATABASE_URL=postgresql://admin:password123@local816-postgres:5432/audiotours \
        -e NARRATION_MODEL=gpt-4.1-mini -e RESEARCH_BACKEND=serper \
        -e STORIED_MODE=true -e DISABLE_TOUR_CACHE=1 -e DISABLE_STOP_POOL=1 \
        -e STOP_EXISTENCE_GATE_MODE=log_only \
        -e TEST_GEMINI_MAX_USD=0.60 -e COST_HARD_LIMIT_USD=0.60 \
        -v "$PWD":/app -w /app audioura-tour-generator:latest \
        python -u run_local816_container.py <0|1>
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
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '0.60')
_os.environ.setdefault('COST_HARD_LIMIT_USD', '0.60')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

HARD_CAP_USD = 0.60
HOST = socket.gethostname()

# (request, tour_type, n_stops, slug)
TOURS = [
    ('Trevi Fountain, Pantheon and Piazza Navona walking tour, Rome',
     'walking', 5, 'trevi-pantheon-navona-ROME'),
    ('Westminster walking tour, London',
     'walking', 5, 'westminster-LONDON'),
]

if len(_sys.argv) > 1:
    try:
        _only = int(_sys.argv[1])
        TOURS = [TOURS[_only]]
        print(f"[LOCAL-816] single-tour mode: index {_only}", flush=True)
    except (ValueError, IndexError):
        print(f"[LOCAL-816] bad tour index {_sys.argv[1]!r}; running all", flush=True)

print("=== LOCAL-816 isolated live run (cheap arm: gpt-4.1-mini + serper) ===", flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  cache_off=1 pool_off=1  STORIED_MODE=true "
      f"RESEARCH_BACKEND={_os.environ.get('RESEARCH_BACKEND')}", flush=True)

try:
    from live_run_meter import LiveRunMeter
except Exception as _e:
    print(f"[LOCAL-816] live_run_meter unavailable ({_e}) — cannot cap; aborting", flush=True)
    _sys.exit(2)


def _conn():
    import psycopg2
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=_os.environ.get('DB_HOST', 'local816-postgres'),
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
        name = f"LOCAL-816 {location.split(',')[0][:40]} {int(time.time())}"
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
                 'LOCAL-816 named-anchor walking count live'))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [db] store failed: {e}", flush=True); return None


def main():
    before = _row_count()
    print(f"audio_tours rows BEFORE: {before}", flush=True)

    meter = LiveRunMeter('LOCAL-816')
    results = []
    try:
        import generate_tour_text as g
        import traceback as _tb
        for (location, ttype, stops, slug) in TOURS:
            print(f"\n=== TOUR [{slug}] {location!r} tour_type={ttype!r} "
                  f"({stops} stops) ===", flush=True)
            # Show the resolved containment scope deterministically BEFORE spend —
            # this is the LOCAL-816 fix in action (anchor list -> enclosing area).
            try:
                from tour_type_detector import detect_intent as _di  # best effort
            except Exception:
                _di = None
            try:
                cat = g._classify_tour_category(location, ttype)
                print(f"  [LOCAL-816] classified category = {cat!r}", flush=True)
            except Exception as _ce:
                print(f"  [LOCAL-816] classify failed (non-fatal): {_ce}", flush=True)
            t0 = time.time()
            try:
                text, _out, coords = g.generate_tour_text(location, ttype, None, stops)
                dt = time.time() - t0
                if not text:
                    try:
                        _ev = dict(getattr(g, '_LAST_CLEAN_FAIL_EVIDENCE', {}) or {})
                    except Exception:
                        _ev = {}
                    print(f"  [LOCAL-816] generation returned NO text "
                          f"(clean-fail) in {dt:.0f}s; evidence={_ev}", flush=True)
                    try:
                        meter.add_generation(g)
                    except Exception:
                        pass
                    results.append((slug, 'NO_TEXT (clean-fail)', 0, stops, None))
                    continue
                titles, sf = _report_stops(text)
                rid = _store(location, text, stops)
                try:
                    meter.add_generation(g)
                except Exception as _ae:
                    print(f"  [LOCAL-816] meter.add_generation failed (non-fatal): {_ae}", flush=True)
                print(f"  stored is_test row id={rid}; delivered {len(titles)}/{stops} "
                      f"stop(s) in {dt:.0f}s", flush=True)
                results.append((slug, f'{len(titles)}/{stops} stops cat={cat}',
                                len(titles), stops, sf))
            except Exception as e:
                print(f"  [LOCAL-816] TOUR [{slug}] raised: {e}", flush=True)
                _tb.print_exc()
                try:
                    meter.add_generation(g)
                except Exception:
                    pass
                results.append((slug, f'ERROR: {e}', 0, stops, None))
                continue
    finally:
        try:
            row_id = meter.record()
            print(f"\n[LOCAL-816] cost ledger row: {row_id}", flush=True)
        except Exception as _me:
            print(f"[LOCAL-816] meter.record failed (non-fatal): {_me}", flush=True)
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
    print("=== LOCAL-816 SUMMARY ===", flush=True)
    for slug, status, n, req, sf in results:
        verdict = 'PASS' if n == req else 'SHORT'
        print(f"  [{slug}] {status}  -> {verdict}"
              f"{' (shortfall-apology present)' if sf else ''}", flush=True)


if __name__ == '__main__':
    main()
