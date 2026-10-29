#!/usr/bin/env python3
"""build_research_library.py - LOCAL-806 P6 research-library builder.

Pre-research the most-requested destinations cheaply and KEEP the research in the
stop pool with a `fresh_until` date, so a later customer request there is built
from stored research instead of researched from scratch (the P6 idea, Michael
2026-10-27).

What it does
============
For each (place, tour_type, n_stops) in the pilot set it runs the RESEARCH HALF
of the pipeline - generate_tour_text(), which does candidate discovery
(places_search / Wikidata), existence evidence, pins, fact snippets and the
narration TEXT, but NO voice/TTS (voice is the expensive on-demand half and is
never produced here) - then stores the delivered stops into stop_pool with
`fresh_days` set:

    museums / landmarks (museum, walking, facility, specialized)  -> 90 days
    businesses          (restaurant / places)                     -> 30 days

The row's `fresh_until` is NOW()+fresh_days. get_pool_stops serves it only while
fresh; research_library_refresh.py re-researches it as it nears expiry.

Research backend is Serper (RESEARCH_BACKEND=serper) - Gemini credit is depleted.

SAFETY
======
Writes ONLY to the DATABASE_URL you pass, which MUST be an isolated throwaway DB
seeded from the schema dump - NEVER the live 5433 DB. A hard refusal below aborts
if DATABASE_URL points at the known live host/port. Cost is meted and HARD-capped
by tests/live_run_meter.py (TEST_GEMINI_MAX_USD / COST_HARD_LIMIT_USD).

Run (inside the LOCAL-806 isolated container; see SUBMISSION_LOCAL-806.md):

    docker run --rm --network local806_net --env-file .env \
        -e DATABASE_URL=postgresql://admin:password123@local806-postgres:5432/audiotours \
        -e NARRATION_MODEL=gpt-4.1-mini -e RESEARCH_BACKEND=serper \
        -e DISABLE_TOUR_CACHE=1 -e DISABLE_STOP_POOL=1 \
        -e STOP_EXISTENCE_GATE_MODE=log_only \
        -e TEST_GEMINI_MAX_USD=2.00 -e COST_HARD_LIMIT_USD=2.00 \
        -v "$PWD":/app -w /app audioura-tour-generator:latest \
        python -u build_research_library.py            # all places
        python -u build_research_library.py 0 1 2      # only these indices

DISABLE_STOP_POOL=1 keeps the generation itself from reading/short-circuiting on
the pool it is FILLING; the explicit store below (with fresh_days) is what writes
the library rows. Each place is researched once per tour_type.
"""
import os as _os
import sys as _sys
import time

_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))

# Cheap arm; never touch the whole-tour cache or read the pool we are filling.
_os.environ.setdefault('NARRATION_MODEL', 'gpt-4.1-mini')
_os.environ.setdefault('RESEARCH_BACKEND', 'serper')
_os.environ.setdefault('DISABLE_TOUR_CACHE', '1')
_os.environ.setdefault('DISABLE_STOP_POOL', '1')
# STORIED_MODE must be on: the generator's own post-generation pool store (the
# single, correct write point) only fires under storied mode, and it is that
# store — not a second one here — that writes the library row under the exact
# (venue identity, tour_type) key a later customer read uses.
_os.environ.setdefault('STORIED_MODE', 'true')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '2.00')
_os.environ.setdefault('COST_HARD_LIMIT_USD', '2.00')

# Freshness windows (days) by tour category.
FRESH_DAYS_BY_CATEGORY = {
    'museum': 90,
    'walking': 90,
    'facility': 90,
    'specialized': 90,
    'restaurant': 30,   # the maps-first/places category dining + businesses share
}
DEFAULT_FRESH_DAYS = 90


# The 10 pilot places (most-requested non-test on the Mac DB + HCMC + Mui Ne).
# (request_string, tour_type_hint, n_stops). An empty tour_type lets the
# classifier decide from the request wording (the production path).
PLACES = [
    # 1. Boston politics / current affairs walking tour (114 requested, EN/RU/ES/FR)
    ('Walking tour in Boston dedicated to Massachusetts politics and current affairs, Boston, MA', '', 5),
    # 2. Asian Arts Museum, Nice (93 requested + 11 tour_requests)
    ('Asian arts museum, Nice, France', '', 5),
    # 3. Palais Lascaris, Nice (21 requested)
    ('Palais Lascaris, Nice, France', '', 5),
    # 4. Salem Witch Museum, Salem MA (21 + 3)
    ('The Salem Witch Museum, Salem, MA', '', 5),
    # 5. McMullen Museum of Art, Boston College (6 + 2)
    ('McMullen Museum of Art, Boston College, Boston, MA', '', 5),
    # 6. Boston Common (29 tour_requests + 5 audio_tours - top by request count)
    ('Please generate a walking tour of Boston Common', '', 5),
    # 7. Faneuil Hall Marketplace, Boston (4 + 1)
    ('Faneuil Hall Marketplace, Boston, MA', '', 5),
    # 8. Museum of Fine Arts, Boston (5 tour_requests)
    ('Museum of Fine Arts, Boston, MA', '', 5),
    # 9. (REQUIRED - Michael's trip) Ho Chi Minh City pagodas & temples
    ('Pagodas and temples of Ho Chi Minh City (Jade Emperor Pagoda, Thien Hau Temple)', '', 5),
    # 10. (REQUIRED - Michael's trip) Mui Ne kitesurfing (places/business)
    ('Kitesurfing schools in Mui Ne, Vietnam', '', 4),
]


def _refuse_if_live_db():
    """Hard refusal: never let this builder write to the live 5433 DB."""
    url = (_os.environ.get('DATABASE_URL') or '').lower()
    host = (_os.environ.get('DB_HOST') or '').lower()
    port = (_os.environ.get('DB_PORT') or '')
    bad = []
    # The live dev DB container / host:port.
    if 'development-postgres' in url or 'development-postgres' in host:
        bad.append('development-postgres')
    if ':5433/' in url or port == '5433':
        bad.append('port 5433')
    if not url and not host:
        bad.append('no DATABASE_URL / DB_HOST set')
    if bad:
        print(f"[LOCAL-806] REFUSING to run: DATABASE_URL/host looks like the LIVE "
              f"DB ({', '.join(bad)}). The library must be built in an isolated "
              f"throwaway DB. Aborting.", flush=True)
        _sys.exit(2)


def main():
    _refuse_if_live_db()

    sel = []
    for a in _sys.argv[1:]:
        try:
            sel.append(int(a))
        except ValueError:
            pass
    places = [PLACES[i] for i in sel] if sel else PLACES

    print("=== LOCAL-806 research-library build (cheap arm: gpt-4.1-mini + serper) ===",
          flush=True)
    print(f"DATABASE_URL set: {bool(_os.environ.get('DATABASE_URL'))}  "
          f"RESEARCH_BACKEND={_os.environ.get('RESEARCH_BACKEND')}  "
          f"cap=${_os.environ.get('TEST_GEMINI_MAX_USD')}", flush=True)
    print(f"places to build: {len(places)}", flush=True)

    db_url = _os.environ.get('DATABASE_URL')

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-806] live_run_meter unavailable ({e}) - cannot cap; aborting",
              flush=True)
        _sys.exit(2)

    import generate_tour_text as g
    import stop_pool_store as pool
    import traceback as _tb

    meter = LiveRunMeter('LOCAL-806')
    results = []
    try:
        for idx, (request, ttype, n_stops) in enumerate(places):
            cat = g._classify_tour_category(request, ttype)
            fresh_days = FRESH_DAYS_BY_CATEGORY.get(cat, DEFAULT_FRESH_DAYS)
            # The generator's own post-generation pool store reads this env and
            # stamps fresh_until = NOW()+fresh_days on every pooled stop. Set it
            # per place (museums/landmarks 90, businesses 30).
            _os.environ['RESEARCH_LIBRARY_FRESH_DAYS'] = str(fresh_days)
            print(f"\n=== [{idx}] {request!r}  type={ttype!r} cat={cat} "
                  f"fresh_days={fresh_days} n={n_stops} ===", flush=True)
            t0 = time.time()
            try:
                text, _out, _coords = g.generate_tour_text(request, ttype, None, n_stops)
                dt = time.time() - t0
                try:
                    meter.add_generation(g)
                except Exception:
                    pass
                if not text:
                    print(f"  [LOCAL-806] NO text (clean-fail) in {dt:.0f}s - not stored",
                          flush=True)
                    results.append((idx, request, cat, 0, 0, dt, 'NO_TEXT'))
                    continue
                # The generator stored the library rows itself (under the raw
                # tour_type the customer read uses) with fresh_until stamped.
                # Confirm what the reader will now serve for this place — this is
                # the LIBRARY HIT a later customer request gets.
                served = pool.get_pool_stops(request, ttype, db_url)
                fresh_set = sum(1 for s in served if s.get('fresh_until'))
                print(f"  researched in {dt:.0f}s; reader serves {len(served)} stop(s) "
                      f"for tour_type={ttype!r}, {fresh_set} with fresh_until "
                      f"(+{fresh_days}d)", flush=True)
                results.append((idx, request, cat, fresh_set, len(served), dt, 'OK'))
            except Exception as e:
                print(f"  [LOCAL-806] [{idx}] raised: {e}", flush=True)
                _tb.print_exc()
                try:
                    meter.add_generation(g)
                except Exception:
                    pass
                results.append((idx, request, cat, 0, 0, time.time() - t0, f'ERROR: {e}'))
                continue
    finally:
        try:
            row_id = meter.record()
            print(f"\n[LOCAL-806] cost ledger row: {row_id}", flush=True)
        except Exception as _me:
            print(f"[LOCAL-806] meter.record failed (non-fatal): {_me}", flush=True)
        try:
            print(meter.summary(), flush=True)
        except Exception:
            pass
        try:
            meter.uninstall()
        except Exception:
            pass

    print("\n=== LOCAL-806 library build SUMMARY ===", flush=True)
    total_written = 0
    for idx, request, cat, written, served, dt, status in results:
        total_written += written
        print(f"  [{idx}] {status:10s} cat={cat:11s} stored={written} served={served} "
              f"{dt:.0f}s  {request[:60]}", flush=True)
    print(f"  TOTAL library stops written: {total_written}", flush=True)


if __name__ == '__main__':
    main()
