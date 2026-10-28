"""run_local791b_container.py — LOCAL-791B live acceptance (ISOLATED container).

Three fresh paid tours through the real generation path, proving the LOCAL-791B
leftovers end to end, with the PIN-PROOF table item 3 asked for:

  0. "Pagodas and temples of HCMC (Jade Emperor Pagoda, Thien Hau Temple)" (5)
       — item 1: English titles with the local name in parentheses;
         item 2: NO off-category stop (no Tao Dan Park);
         item 3: every pin within 100 m of the real place.
  1. "Old Saigon walking tour, District 1, Ho Chi Minh City
       (Notre-Dame Cathedral, Central Post Office, Opera House, City Hall)" (6)
       — item 3: the pin table; the four named landmarks present.
  2. "Kitesurfing schools in Mui Ne, Vietnam" (3)
       — the stops named (business/activity places path).

For every delivered tour the harness prints the STOPS, then the PIN-PROOF TABLE
(pin_proof.pin_report + format_pin_table): each stop's shipped coordinate, the
independent Serper-Places/Nominatim reference for that name, and the distance.
Target ≤ 100 m.

Budget: HARD CAP $2.00 for the WHOLE task (ticket), enforced by
tests/live_run_meter.py (combined across providers). Each delivered tour is stored
as ONE additive is_test row. No DELETE.

OpenAI note (ticket): on Oct 28 the Mac key hit OpenAI's project spend limit
(project_spend_limit_exceeded). If generation fails for that reason, the harness
reports the live part UNPROVEN and stops — it does NOT retry in a loop.

Run inside an isolated container only (reuse the LOCAL-788B isolated postgres, or
bring up OWN `-p local791b`; never -p audioura; never touch audioura-*):
    docker run --rm --name local791b-tg \
        --network local788b_default \
        --env-file .env \
        -e DATABASE_URL=postgresql://admin:password123@local788b-postgres:5432/audiotours \
        -e STORIED_MODE=true -e DISABLE_TOUR_CACHE=1 -e DISABLE_STOP_POOL=1 \
        -e STOP_EXISTENCE_GATE_MODE=log_only \
        -e TEST_GEMINI_MAX_USD=2.00 -e COST_HARD_LIMIT_USD=2.00 \
        -v "$PWD":/app -w /app audioura-tour-generator:latest \
        python -u run_local791b_container.py <0|1|2>
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
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

HARD_CAP_USD = 2.00
HOST = socket.gethostname()

# tour_type "" for every request (as the app sends an empty type).
TOURS = [
    ('Pagodas and temples of HCMC '
     '(Jade Emperor Pagoda, Thien Hau Temple)', '', 5, 'PAGODAS-HCMC',
     'Ho Chi Minh City, Vietnam'),
    ('Old Saigon walking tour, District 1, Ho Chi Minh City '
     '(Notre-Dame Cathedral, Central Post Office, Opera House, City Hall)',
     '', 6, 'OLD-SAIGON', 'District 1, Ho Chi Minh City, Vietnam'),
    ('Kitesurfing schools in Mui Ne, Vietnam', '', 3, 'MUINE-KITE',
     'Mui Ne, Vietnam'),
]

if len(_sys.argv) > 1:
    try:
        _only = int(_sys.argv[1])
        TOURS = [TOURS[_only]]
        print(f"[LOCAL-791B] single-tour mode: index {_only}", flush=True)
    except (ValueError, IndexError):
        print(f"[LOCAL-791B] bad tour index {_sys.argv[1]!r}; running all", flush=True)

print("=== LOCAL-791B isolated live run (names / category / pins) ===", flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  cache_off=1 pool_off=1  STORIED_MODE=true",
      flush=True)

try:
    from live_run_meter import LiveRunMeter
except Exception as _e:
    print(f"[LOCAL-791B] live_run_meter unavailable ({_e}) — cannot cap; aborting",
          flush=True)
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


def _report_pins(text, scope):
    """[LOCAL-791B item 3] Pin-proof table for the delivered tour."""
    try:
        import pin_proof as _pp
    except Exception as e:
        print(f"  [LOCAL-791B] pin_proof unavailable ({e})", flush=True)
        return
    stops = _pp.parse_tour_stops(text)
    if not stops:
        print("  [LOCAL-791B] no stops parsed for pin proof", flush=True)
        return
    # Geocode the scope centre once so Serper Places binds to the right city.
    center = None
    try:
        import geocode_stops as _gs
        center = _gs.geocode(scope)
    except Exception:
        center = None
    print("  --- PIN PROOF (item 3) ---", flush=True)
    report = _pp.pin_report(stops, scope=scope, scope_center=center)
    print(_pp.format_pin_table(report), flush=True)
    return report


def _store(location, text, n_stops):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-791B {location.split(',')[0][:40]} {int(time.time())}"
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
                 'LOCAL-791B names/category/pins live'))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [db] store failed: {e}", flush=True); return None


def _looks_like_spend_limit(evidence, exc_text):
    blob = f"{evidence} {exc_text}".lower()
    return ('project_spend_limit_exceeded' in blob
            or 'spend limit' in blob
            or 'insufficient_quota' in blob)


def main():
    before = _row_count()
    print(f"audio_tours rows BEFORE: {before}", flush=True)

    meter = LiveRunMeter('LOCAL-791B')
    results = []
    spend_limit_hit = False
    try:
        import generate_tour_text as g
        import traceback as _tb
        for (location, ttype, stops, slug, scope) in TOURS:
            if spend_limit_hit:
                print(f"\n=== TOUR [{slug}] SKIPPED (OpenAI spend limit already hit) ===",
                      flush=True)
                results.append((slug, 'UNPROVEN (spend limit)', 0))
                continue
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
                    if _looks_like_spend_limit(_ev, ''):
                        spend_limit_hit = True
                        print(f"  [LOCAL-791B] OpenAI spend limit — live UNPROVEN; "
                              f"not retrying (ticket).", flush=True)
                        results.append((slug, 'UNPROVEN (spend limit)', 0))
                        try:
                            meter.add_generation(g)
                        except Exception:
                            pass
                        continue
                    print(f"  [LOCAL-791B] generation returned NO text "
                          f"(clean-fail) in {dt:.0f}s; evidence={_ev}", flush=True)
                    try:
                        meter.add_generation(g)
                    except Exception:
                        pass
                    results.append((slug, 'NO_TEXT (clean-fail)', 0))
                    continue
                titles = _report_stops(text)
                _report_pins(text, scope)
                n = len(titles)
                rid = _store(location, text, stops)
                try:
                    meter.add_generation(g)
                except Exception as _ae:
                    print(f"  [LOCAL-791B] meter.add_generation failed (non-fatal): {_ae}",
                          flush=True)
                print(f"  stored is_test row id={rid}; delivered {n} stop(s) in {dt:.0f}s",
                      flush=True)
                results.append((slug, f'{n} stops', n))
            except Exception as e:
                print(f"  [LOCAL-791B] TOUR [{slug}] raised: {e}", flush=True)
                _tb.print_exc()
                if _looks_like_spend_limit('', str(e)):
                    spend_limit_hit = True
                    print(f"  [LOCAL-791B] OpenAI spend limit — live UNPROVEN; "
                          f"not retrying (ticket).", flush=True)
                    results.append((slug, 'UNPROVEN (spend limit)', 0))
                else:
                    results.append((slug, f'ERROR: {e}', 0))
                try:
                    meter.add_generation(g)
                except Exception:
                    pass
                continue
    finally:
        try:
            row_id = meter.record()
            print(f"\n[LOCAL-791B] cost ledger row: {row_id}", flush=True)
        except Exception as _me:
            print(f"[LOCAL-791B] meter.record failed (non-fatal): {_me}", flush=True)
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
    print("=== LOCAL-791B SUMMARY ===", flush=True)
    for slug, status, n in results:
        print(f"  [{slug}] {status}", flush=True)
    if spend_limit_hit:
        print("  NOTE: OpenAI project spend limit hit — live part UNPROVEN "
              "(reported, not retried).", flush=True)


if __name__ == '__main__':
    main()
