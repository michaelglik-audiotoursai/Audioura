#!/usr/bin/env python3
"""research_library_refresh.py — LOCAL-806 P6 research-library refresh job.

The P6 pilot pre-researches the most-requested destinations cheaply and keeps the
research in the stop pool with a `fresh_until` date (museums/landmarks 90 days,
businesses 30 days). The reader (stop_pool_store.get_pool_stops) already serves a
library row ONLY while `fresh_until` is in the future and IGNORES it once stale —
so a stale row is never delivered. THIS job keeps the library warm: it finds
library rows whose `fresh_until` is within a lead window of expiry (or already
past) and RE-RESEARCHES the place behind them, which re-stamps a new
`fresh_until = NOW() + N days` on the pooled stops. A customer request there then
keeps getting a fast, cheap library hit instead of falling back to full research.

This is the small script the ticket asks for, runnable by launchd later
(com.audioura.research-library-refresh.plist — a FILE ONLY, installed by LEAD).

Design
======
* A library row is any stop_pool row with `fresh_until IS NOT NULL` (the partial
  index idx_stop_pool_fresh_until makes this scan cheap). Ordinary delivered-tour
  stops have fresh_until = NULL and are never touched here.
* "Nearing expiry" = fresh_until <= NOW() + <lead-days>. Default lead is 7 days,
  so a row is re-researched in the week before it would go stale (and any already
  stale row is caught too).
* Each near-expiry row is grouped by (venue_identity, tour_type) and mapped back
  to a pilot place in build_research_library.PLACES by its venue identity. Only
  places that are IN that pilot set are re-researched — the refresher re-runs the
  exact builder path (generate the research half + the generator's own pool store
  with RESEARCH_LIBRARY_FRESH_DAYS set), so the refreshed row lands under the SAME
  (identity, tour_type) key the customer read uses and its fresh_until advances.
* DRY-RUN BY DEFAULT: it only reports what it WOULD refresh. Pass --apply to
  actually re-research (which makes capped paid-API calls, exactly like the
  builder). launchd would run it with --apply.

SAFETY
======
The scan is READ-ONLY. The re-research WRITE goes ONLY to the DATABASE_URL you
pass, which MUST be the isolated research-library DB — the same hard refusal as
build_research_library.py aborts if it looks like the live 5433 DB. Never
DELETE/DROP: a row is only ever UPDATEd in place (its fresh_until advanced).

Run (report only):
    DATABASE_URL=postgresql://admin:password123@local806-postgres:5432/audiotours \
        python3 research_library_refresh.py --lead-days 7

Run (actually refresh, capped like the builder):
    DATABASE_URL=... RESEARCH_BACKEND=serper NARRATION_MODEL=gpt-4.1-mini \
    TEST_GEMINI_MAX_USD=2.00 COST_HARD_LIMIT_USD=2.00 \
        python3 research_library_refresh.py --lead-days 7 --apply
"""
import argparse
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))

# Cheap arm, same as the builder. Only set on --apply does any of this matter.
_os.environ.setdefault('NARRATION_MODEL', 'gpt-4.1-mini')
_os.environ.setdefault('RESEARCH_BACKEND', 'serper')
_os.environ.setdefault('DISABLE_TOUR_CACHE', '1')
_os.environ.setdefault('DISABLE_STOP_POOL', '1')  # don't short-circuit on the pool we refill
_os.environ.setdefault('STORIED_MODE', 'true')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '2.00')
_os.environ.setdefault('COST_HARD_LIMIT_USD', '2.00')

DEFAULT_LEAD_DAYS = 7


def _refuse_if_live_db():
    """Hard refusal: never let a refresh WRITE touch the live 5433 DB."""
    url = (_os.environ.get('DATABASE_URL') or '').lower()
    host = (_os.environ.get('DB_HOST') or '').lower()
    port = (_os.environ.get('DB_PORT') or '')
    bad = []
    if 'development-postgres' in url or 'development-postgres' in host:
        bad.append('development-postgres')
    if ':5433/' in url or port == '5433':
        bad.append('port 5433')
    if not url and not host:
        bad.append('no DATABASE_URL / DB_HOST set')
    if bad:
        print(f"[LOCAL-806] REFUSING to refresh: DATABASE_URL/host looks like the "
              f"LIVE DB ({', '.join(bad)}). The research library is an isolated "
              f"throwaway DB. Aborting.", flush=True)
        _sys.exit(2)


def _scan_near_expiry(db_url, lead_days):
    """READ-ONLY scan: library rows whose fresh_until <= NOW()+lead_days.

    Returns a list of dicts {venue_identity, tour_type, n_stops, min_fresh_until,
    stale} grouped by (venue_identity, tour_type).
    """
    import psycopg2
    conn = psycopg2.connect(db_url)
    try:
        conn.set_session(readonly=True, autocommit=True)
    except Exception:
        pass
    rows = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT venue_identity, tour_type,
                       COUNT(*) AS n_stops,
                       MIN(fresh_until) AS min_fresh_until,
                       BOOL_OR(fresh_until < NOW()) AS any_stale
                FROM stop_pool
                WHERE fresh_until IS NOT NULL
                  AND fresh_until <= NOW() + (%s || ' days')::interval
                GROUP BY venue_identity, tour_type
                ORDER BY MIN(fresh_until) ASC
                """,
                (int(lead_days),),
            )
            for r in cur.fetchall():
                rows.append({
                    'venue_identity': r[0],
                    'tour_type': r[1],
                    'n_stops': int(r[2]),
                    'min_fresh_until': r[3],
                    'stale': bool(r[4]),
                })
    finally:
        conn.close()
    return rows


def _pilot_place_for_identity(venue_identity):
    """Map a library row's venue_identity back to a pilot place + its fresh_days.

    Only pilot places (build_research_library.PLACES) are refreshable here: the
    refresher re-runs the builder path for the matching request string so the
    refreshed row lands under the identical (identity, tour_type) key. A library
    row whose identity is not in the pilot set is reported but skipped (it was not
    built by this pilot and has no known re-research request string).
    """
    import build_research_library as b
    import stop_pool_store as pool
    import generate_tour_text as g
    for (request, ttype, n_stops) in b.PLACES:
        ident = pool.venue_identity(request)
        if ident == venue_identity:
            cat = g._classify_tour_category(request, ttype)
            fresh_days = b.FRESH_DAYS_BY_CATEGORY.get(cat, b.DEFAULT_FRESH_DAYS)
            return {'request': request, 'tour_type': ttype,
                    'n_stops': n_stops, 'fresh_days': fresh_days, 'category': cat}
    return None


def _refresh_place(place, db_url):
    """Re-research one pilot place (the builder path) → advances its fresh_until."""
    import generate_tour_text as g
    _os.environ['RESEARCH_LIBRARY_FRESH_DAYS'] = str(place['fresh_days'])
    text, _out, _coords = g.generate_tour_text(
        place['request'], place['tour_type'], None, place['n_stops'])
    return bool(text)


def main():
    ap = argparse.ArgumentParser(description='LOCAL-806 research-library refresh')
    ap.add_argument('--lead-days', type=int, default=DEFAULT_LEAD_DAYS,
                    help='refresh rows whose fresh_until is within this many days '
                         '(or already past). Default 7.')
    ap.add_argument('--apply', action='store_true',
                    help='actually re-research (capped paid-API calls). Without '
                         'it, only report what would be refreshed (dry run).')
    args = ap.parse_args()

    db_url = _os.environ.get('DATABASE_URL')
    if not db_url:
        print('[LOCAL-806] no DATABASE_URL set — nothing to scan. Aborting.', flush=True)
        _sys.exit(2)
    # The scan is read-only; the WRITE (only under --apply) must be isolated.
    if args.apply:
        _refuse_if_live_db()

    due = _scan_near_expiry(db_url, args.lead_days)
    print(f"=== LOCAL-806 research-library refresh "
          f"({'APPLY' if args.apply else 'DRY-RUN'}; lead={args.lead_days}d) ===",
          flush=True)
    print(f"library (venue, tour_type) groups within/after fresh_until: {len(due)}",
          flush=True)
    if not due:
        print("nothing to refresh.", flush=True)
        return

    meter = None
    if args.apply:
        try:
            from live_run_meter import LiveRunMeter
            meter = LiveRunMeter('LOCAL-806-refresh')
        except Exception as e:
            print(f"[LOCAL-806] live_run_meter unavailable ({e}) — cannot cap a "
                  f"refresh WRITE; aborting.", flush=True)
            _sys.exit(2)

    import generate_tour_text as g  # noqa: F401 (import cost paid once)
    refreshed = skipped = 0
    try:
        for d in due:
            place = _pilot_place_for_identity(d['venue_identity'])
            tag = 'STALE' if d['stale'] else 'nearing'
            if not place:
                skipped += 1
                print(f"  SKIP  {tag:7s} identity={d['venue_identity'][:48]!r} "
                      f"tour_type={d['tour_type']!r} ({d['n_stops']} stop(s)) — not a "
                      f"pilot place, no re-research request string", flush=True)
                continue
            if not args.apply:
                print(f"  WOULD {tag:7s} {place['request'][:50]!r} "
                      f"cat={place['category']} +{place['fresh_days']}d "
                      f"({d['n_stops']} stop(s), min_fresh_until={d['min_fresh_until']})",
                      flush=True)
                continue
            print(f"  REFRESH {tag:7s} {place['request'][:50]!r} "
                  f"cat={place['category']} +{place['fresh_days']}d", flush=True)
            try:
                ok = _refresh_place(place, db_url)
                refreshed += 1 if ok else 0
                if not ok:
                    print(f"    (no text produced — row left as-is, not served stale)",
                          flush=True)
            except Exception as e:
                print(f"    [LOCAL-806] refresh raised: {e}", flush=True)
            finally:
                try:
                    meter.add_generation(g)
                except Exception:
                    pass
    finally:
        if meter is not None:
            try:
                meter.record()
                print(meter.summary(), flush=True)
            except Exception:
                pass
            try:
                meter.uninstall()
            except Exception:
                pass

    if args.apply:
        print(f"\n[LOCAL-806] refreshed {refreshed} place(s); skipped {skipped} "
              f"non-pilot group(s).", flush=True)
    else:
        print(f"\n[LOCAL-806] dry run: {len(due)-skipped} pilot place(s) would be "
              f"refreshed, {skipped} non-pilot group(s) skipped. Re-run with --apply "
              f"to re-research.", flush=True)


if __name__ == '__main__':
    main()
