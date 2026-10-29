"""run_local810_container.py — LOCAL-810 live acceptance (ISOLATED container).

A slow Wikidata (WDQS SPARQL ReadTimeout / 429) must NOT fail a whole museum
tour. Evidence (LOCAL-809 live run): "Metropolitan Museum of Art, New York" —
the model's candidates were all real Met works, but fetch_venue_works(Q160236)
hit WDQS ReadTimeout ×4 → 0 canonical titles → the tour cleanly FAILED.

This harness proves the LOCAL-810 fix end to end: WDQS is BLACK-HOLED
(WDQS_ENDPOINT points at an unroutable host so every SPARQL call ReadTimeouts),
and the Met tour MUST still deliver real Met works through the fallback chain
(per-candidate P195/P276 checks → museum site → Wikipedia highlights), logging
`[LOCAL-810] venue works fallback <qid> <source> <n>`.

Acceptance (printed after the run):
  * the tour produces text (NOT a clean fail);
  * >= 5 stops, each a plausible real Met work title (not shop/junk);
  * the fallback log line appears;
  * cost under the $1.00 hard cap; <= 3 live tours.

Budget: HARD CAP $1.00 (tests/live_run_meter.py), reserve gate before each tour.
Each delivered tour is stored as ONE additive is_test row in the ISOLATED
postgres only. No DELETE. Never the live/development DB.

Run inside a DISPOSABLE container (project local810; never -p audioura):
    docker run --rm --name local810-tg \
        --network local810_default \
        --env-file .env \
        -e DATABASE_URL=postgresql://admin:password123@local810-postgres:5432/audiotours \
        -e VENUE_CACHE_DB_URL=postgresql://admin:password123@local810-postgres:5432/audiotours \
        -e WDQS_ENDPOINT=http://240.0.0.1:9/sparql \
        -e VENUE_WORKS_TIMEOUT=5 \
        -e RESEARCH_BACKEND=serper -e NARRATION_MODEL=gpt-4.1-mini \
        -e STORIED_MODE=true -e DISABLE_TOUR_CACHE=1 -e DISABLE_STOP_POOL=1 \
        -e STOP_EXISTENCE_GATE_MODE=log_only \
        -e TEST_GEMINI_MAX_USD=1.00 -e COST_HARD_LIMIT_USD=1.00 \
        -v "$PWD":/app -w /app audioura-tour-generator:latest \
        python -u run_local810_container.py
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
_os.environ.setdefault('RESEARCH_BACKEND', 'serper')
_os.environ.setdefault('NARRATION_MODEL', 'gpt-4.1-mini')
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.00')
_os.environ.setdefault('COST_HARD_LIMIT_USD', '1.00')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')
# [LOCAL-810] Black-hole WDQS so the bounded venue-works query ReadTimeouts and
# the fallback chain must carry the tour. An unroutable TEST-NET-3 host.
_os.environ.setdefault('WDQS_ENDPOINT', 'http://240.0.0.1:9/sparql')
_os.environ.setdefault('VENUE_WORKS_TIMEOUT', '5')

HARD_CAP_USD = 1.00
HOST = socket.gethostname()

# (request, tour_type, n_stops, slug)
TOURS = [
    ('Metropolitan Museum of Art, New York, NY', '', 5, 'MET-NYC'),
]

print("=== LOCAL-810 isolated live run (WDQS blocked → fallback) ===", flush=True)
print(f"host  : {HOST}", flush=True)
print(f"WDQS_ENDPOINT (black-holed): {_os.environ.get('WDQS_ENDPOINT')}", flush=True)
print(f"VENUE_WORKS_TIMEOUT: {_os.environ.get('VENUE_WORKS_TIMEOUT')}s", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  cache_off=1 pool_off=1 "
      f"RESEARCH_BACKEND={_os.environ.get('RESEARCH_BACKEND')}", flush=True)

try:
    from live_run_meter import LiveRunMeter
except Exception as _e:
    print(f"[LOCAL-810] live_run_meter unavailable ({_e}) — cannot cap; aborting", flush=True)
    _sys.exit(2)


def _conn():
    import psycopg2
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=_os.environ.get('DB_HOST', 'local810-postgres'),
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


def _check(text, slug):
    """Print acceptance checks for the delivered tour; return a problems list."""
    problems = []
    try:
        import junk_title_guard as jtg
    except Exception:
        jtg = None

    titles = _STOP_HEADER_RE.findall(text)
    print("  --- STOPS ---", flush=True)
    for i, t in enumerate(titles):
        t = t.strip()
        print(f"  STOP {i+1}: {t[:80]}", flush=True)
        if jtg is not None and jtg.is_junk_page_title(t, slug):
            problems.append(f"shop/junk stop title: {t!r}")
        if jtg is not None and jtg.is_shop_product_title(t):
            problems.append(f"shop product stop title: {t!r}")
    if len(titles) < 5:
        problems.append(f"only {len(titles)} stops parsed (expected >= 5)")
    return problems, titles


def _store(location, text, n_stops):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-810 {location.split(',')[0][:40]} {int(time.time())}"
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
                 'LOCAL-810 WDQS-blocked fallback live'))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [db] store failed (non-fatal): {e}", flush=True); return None


def main():
    before = _row_count()
    print(f"audio_tours rows BEFORE: {before}", flush=True)

    meter = LiveRunMeter('LOCAL-810')
    results = []
    # Capture the generator's stdout so we can assert the fallback log line fired.
    import io
    import contextlib
    try:
        import generate_tour_text as g
        import traceback as _tb
        for (location, ttype, stops, slug) in TOURS:
            try:
                spent = meter.total_usd()
            except Exception:
                spent = 0.0
            if spent >= HARD_CAP_USD:
                print(f"\n[LOCAL-810] reserve gate: ${spent:.3f} >= ${HARD_CAP_USD} "
                      f"— skipping remaining tours", flush=True)
                break
            print(f"\n=== TOUR [{slug}] {location!r} ({stops} stops) "
                  f"spent=${spent:.3f} ===", flush=True)
            t0 = time.time()
            _cap = io.StringIO()

            class _Tee:
                def __init__(self, *streams): self._s = streams
                def write(self, d):
                    for s in self._s:
                        s.write(d)
                def flush(self):
                    for s in self._s:
                        try: s.flush()
                        except Exception: pass

            try:
                with contextlib.redirect_stdout(_Tee(_sys.stdout, _cap)):
                    text, _out, _coords = g.generate_tour_text(location, ttype, None, stops)
                dt = time.time() - t0
                captured = _cap.getvalue()
                fallback_logged = bool(re.search(
                    r"\[LOCAL-810\] venue works fallback \S+ \w+ \d+", captured))
                print(f"  fallback log line present: {fallback_logged}", flush=True)
                if not text:
                    print(f"  [LOCAL-810] generation returned NO text in {dt:.0f}s "
                          f"(CLEAN FAIL — the bug is NOT fixed)", flush=True)
                    try: meter.add_generation(g)
                    except Exception: pass
                    results.append((slug, 'NO_TEXT', ['clean fail with WDQS blocked']))
                    continue
                problems, titles = _check(text, slug)
                if not fallback_logged:
                    problems.append("fallback log line '[LOCAL-810] venue works "
                                    "fallback …' did NOT appear")
                rid = _store(location, text, stops)
                try: meter.add_generation(g)
                except Exception as _ae:
                    print(f"  [LOCAL-810] meter.add_generation failed (non-fatal): {_ae}", flush=True)
                verdict = 'PASS' if not problems else 'FAIL'
                print(f"  stored is_test row id={rid} in {dt:.0f}s — {verdict}", flush=True)
                for p in problems:
                    print(f"    PROBLEM: {p}", flush=True)
                results.append((slug, verdict, problems))
            except Exception as e:
                print(f"  [LOCAL-810] TOUR [{slug}] raised: {e}", flush=True)
                _tb.print_exc()
                try: meter.add_generation(g)
                except Exception: pass
                results.append((slug, f'ERROR: {e}', []))
                continue
    finally:
        try:
            row_id = meter.record()
            print(f"\n[LOCAL-810] cost ledger row: {row_id}", flush=True)
        except Exception as _me:
            print(f"[LOCAL-810] meter.record failed (non-fatal): {_me}", flush=True)
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
          f"(delta={after - before if (after is not None and before is not None) else '?'})",
          flush=True)
    print("=== LOCAL-810 SUMMARY ===", flush=True)
    for slug, verdict, problems in results:
        print(f"  [{slug}] {verdict}" + (f" ({len(problems)} problems)" if problems else ""),
              flush=True)


if __name__ == '__main__':
    main()
