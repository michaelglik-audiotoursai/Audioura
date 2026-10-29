"""run_local800_container.py — LOCAL-800 live acceptance (ISOLATED container).

Prove the LOCAL-800 "What people say" customer-voice paragraph end to end through
the real generation path, for the two business/place requests the ticket names:

  0. "Massage and spa near Ben Thanh Market, Ho Chi Minh City"   (3 stops)
  1. "coffee shops in Jamaica Plain, Boston"                     (3 stops)

For every delivered tour the harness prints, PER STOP:
  * the stop title + the delivered narration;
  * the SERPER DATA the paragraph came from (rating, review count, price band,
    website, signature items, praise, complaint — read off the stop's stored
    _customer_voice facts);
  * the composed "What people say" paragraph;
so the paragraph can be read directly against the sourced numbers it used. Each
[LOCAL-800] customer-voice log line is also surfaced.

LEAD NOTE (Oct 28): Gemini prepaid credit is DEPLETED (402 RESOURCE_EXHAUSTED).
Run every live tour with RESEARCH_BACKEND=serper and no Gemini grounding. If a
step still needs Gemini, report it UNPROVEN instead of retrying.

Budget: HARD CAP $1.50 for the WHOLE task (ticket), enforced by
tests/live_run_meter.py (combined across providers). Each delivered tour is stored
as ONE additive is_test row in the ISOLATED container DB. No DELETE. Never the
live DB.

Run inside an OWN isolated container (reuse the LOCAL-788B isolated postgres, or
bring up OWN `-p local800`; never -p audioura; never touch audioura-*):
    docker run --rm --name local800-tg \
        --network local788b_default \
        --env-file .env \
        -e DATABASE_URL=postgresql://admin:password123@local788b-postgres:5432/audiotours \
        -e STORIED_MODE=true -e DISABLE_TOUR_CACHE=1 -e DISABLE_STOP_POOL=1 \
        -e STOP_EXISTENCE_GATE_MODE=log_only \
        -e RESEARCH_BACKEND=serper -e SERP_PROVIDER=serper \
        -e TEST_GEMINI_MAX_USD=1.50 -e COST_HARD_LIMIT_USD=1.50 \
        -v "$PWD":/app -w /app audioura-tour-generator:latest \
        python -u run_local800_container.py <0|1>
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
_os.environ.setdefault('SERP_PROVIDER', 'serper')
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.50')
_os.environ.setdefault('COST_HARD_LIMIT_USD', '1.50')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

HARD_CAP_USD = 1.50
HOST = socket.gethostname()

# tour_type "" for every request (as the app sends an empty type).
TOURS = [
    ('Massage and spa near Ben Thanh Market, Ho Chi Minh City', '', 3,
     'BENTHANH-SPA', 'Ben Thanh Market, Ho Chi Minh City, Vietnam'),
    ('coffee shops in Jamaica Plain, Boston', '', 3,
     'JP-COFFEE', 'Jamaica Plain, Boston, MA'),
]

if len(_sys.argv) > 1:
    try:
        _only = int(_sys.argv[1])
        TOURS = [TOURS[_only]]
        print(f"[LOCAL-800] single-tour mode: index {_only}", flush=True)
    except (ValueError, IndexError):
        print(f"[LOCAL-800] bad tour index {_sys.argv[1]!r}; running all", flush=True)

print("=== LOCAL-800 isolated live run (customer-voice 'What people say') ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  cache_off=1 pool_off=1  "
      f"RESEARCH_BACKEND=serper  STORIED_MODE=true", flush=True)

try:
    from live_run_meter import LiveRunMeter
except Exception as _e:
    print(f"[LOCAL-800] live_run_meter unavailable ({_e}) — cannot cap; aborting",
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


def _print_customer_voice(g, titles):
    """Show each place stop's customer-voice facts (the Serper data it came from)
    and the composed paragraph, read off the final poi list the generator kept."""
    try:
        pois = list(getattr(g, '_LAST_POI_LIST', []) or [])
    except Exception:
        pois = []
    import customer_voice as _cv
    print("  --- CUSTOMER VOICE (LOCAL-800) ---", flush=True)
    shown = 0
    for p in pois:
        facts = p.get('_customer_voice') if isinstance(p, dict) else None
        if not facts or not facts.get('usable'):
            continue
        name = (p.get('name') or facts.get('name') or '')[:60]
        print(f"  STOP: {name}", flush=True)
        print(f"    SERPER DATA: rating={facts.get('rating')} "
              f"count={facts.get('rating_count')} price={facts.get('price_band')!r} "
              f"website={facts.get('website')!r}", flush=True)
        print(f"    FROM SNIPPETS: items={facts.get('items')} "
              f"praise={facts.get('top_praise')!r} "
              f"complaint={facts.get('top_complaint')!r} "
              f"since={facts.get('since_year')} "
              f"(snippets_used={facts.get('snippets_used')}, "
              f"searched={facts.get('searched')})", flush=True)
        print(f"    PARAGRAPH: {_cv.build_paragraph(facts)}", flush=True)
        print(f"    {_cv.log_line(facts)}", flush=True)
        shown += 1
    if not shown:
        print("  (no customer-voice paragraphs attached — see the [LOCAL-800] "
              "log lines above for why, e.g. rating/count missing)", flush=True)
    return shown


def _report_stops(text):
    print("  --- STOPS (delivered narration) ---", flush=True)
    titles = _STOP_HEADER_RE.findall(text)
    # Split the text on stop headers so each stop's body can be shown.
    chunks = re.split(r"(?mi)^Stop\s+\d+:\s*", text)
    bodies = chunks[1:] if len(chunks) > 1 else []
    for i, t in enumerate(titles):
        print(f"\n  STOP {i+1}: {t.strip()[:80]}", flush=True)
        if i < len(bodies):
            body = bodies[i].strip()
            # Trim at the next section marker for a clean per-stop print.
            body = re.split(r"(?mi)^(Address:|Coordinates:|Stop\s+\d+:)", body)[0]
            print("  " + body.strip()[:1400], flush=True)
    return [t.strip() for t in titles]


def _store(location, text, n_stops):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-800 {location.split(',')[0][:40]} {int(time.time())}"
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
                 'LOCAL-800 customer-voice live'))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [db] store failed: {e}", flush=True); return None


def _looks_like_spend_limit(evidence, exc_text):
    blob = f"{evidence} {exc_text}".lower()
    return ('project_spend_limit_exceeded' in blob
            or 'spend limit' in blob
            or 'insufficient_quota' in blob
            or 'resource_exhausted' in blob)


def main():
    before = _row_count()
    print(f"audio_tours rows BEFORE: {before}", flush=True)

    meter = LiveRunMeter('LOCAL-800')
    results = []
    spend_limit_hit = False
    try:
        import generate_tour_text as g
        import traceback as _tb
        for (location, ttype, stops, slug, scope) in TOURS:
            if spend_limit_hit:
                print(f"\n=== TOUR [{slug}] SKIPPED (spend limit already hit) ===",
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
                        print(f"  [LOCAL-800] spend limit — live UNPROVEN; not "
                              f"retrying (ticket).", flush=True)
                        results.append((slug, 'UNPROVEN (spend limit)', 0))
                        try:
                            meter.add_generation(g)
                        except Exception:
                            pass
                        continue
                    print(f"  [LOCAL-800] generation returned NO text "
                          f"(clean-fail) in {dt:.0f}s; evidence={_ev}", flush=True)
                    try:
                        meter.add_generation(g)
                    except Exception:
                        pass
                    results.append((slug, 'NO_TEXT (clean-fail)', 0))
                    continue
                titles = _report_stops(text)
                _cv_n = _print_customer_voice(g, titles)
                n = len(titles)
                rid = _store(location, text, stops)
                try:
                    meter.add_generation(g)
                except Exception as _ae:
                    print(f"  [LOCAL-800] meter.add_generation failed "
                          f"(non-fatal): {_ae}", flush=True)
                print(f"  stored is_test row id={rid}; delivered {n} stop(s), "
                      f"{_cv_n} with customer-voice, in {dt:.0f}s", flush=True)
                results.append((slug, f'{n} stops, {_cv_n} customer-voice', n))
            except Exception as e:
                print(f"  [LOCAL-800] TOUR [{slug}] raised: {e}", flush=True)
                _tb.print_exc()
                if _looks_like_spend_limit('', str(e)):
                    spend_limit_hit = True
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
            print(f"\n[LOCAL-800] cost ledger row: {row_id}", flush=True)
        except Exception as _me:
            print(f"[LOCAL-800] meter.record failed (non-fatal): {_me}", flush=True)
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
    print("=== LOCAL-800 SUMMARY ===", flush=True)
    for slug, status, n in results:
        print(f"  [{slug}] {status}", flush=True)
    if spend_limit_hit:
        print("  NOTE: provider spend limit hit — live part UNPROVEN "
              "(reported, not retried).", flush=True)


if __name__ == '__main__':
    main()
