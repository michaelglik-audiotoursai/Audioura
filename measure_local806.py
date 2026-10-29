#!/usr/bin/env python3
"""measure_local806.py - LOCAL-806 library OFF vs ON measurement (one run).

Runs ONE request through generate_tour_text and reports wall seconds + metered
cost (tests/live_run_meter), and writes the delivered tour text to a file for
BLIND scoring (the measured text carries no OFF/ON label).

Two arms, each in its OWN container DB (set by DATABASE_URL + DB_* envs):
  OFF  - DISABLE_STOP_POOL=1, an EMPTY DB  -> full fresh research+generation.
  ON   - pool enabled, the BUILT library DB -> library hit (pre-researched stops
         reused; little or nothing researched).

STORIED_MODE=true on both arms (the reuse path is the storied pool path).

Usage (inside the LOCAL-806 container):
    python -u measure_local806.py <off|on> <place_index> <out_text_path>
"""
import os as _os
import sys as _sys
import time

_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))

_os.environ.setdefault('NARRATION_MODEL', 'gpt-4.1-mini')
_os.environ.setdefault('RESEARCH_BACKEND', 'serper')
_os.environ.setdefault('DISABLE_TOUR_CACHE', '1')   # isolate the stop-pool effect
_os.environ.setdefault('STORIED_MODE', 'true')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

# The 4 measured places (same list/order as build_research_library.PLACES, a
# subset chosen to fit the paid-API budget: cheaper walking/places requests).
MEASURE = [
    ('Please generate a walking tour of Boston Common', '', 5),
    ('Walking tour in Boston dedicated to Massachusetts politics and current affairs, Boston, MA', '', 5),
    ('Pagodas and temples of Ho Chi Minh City (Jade Emperor Pagoda, Thien Hau Temple)', '', 4),
    ('Kitesurfing schools in Mui Ne, Vietnam', '', 4),
]


def main():
    if len(_sys.argv) < 4:
        print("usage: measure_local806.py <off|on> <place_index> <out_text_path>", flush=True)
        _sys.exit(2)
    arm = _sys.argv[1].strip().lower()
    idx = int(_sys.argv[2])
    out_path = _sys.argv[3]

    if arm == 'off':
        _os.environ['DISABLE_STOP_POOL'] = '1'
    else:
        _os.environ.pop('DISABLE_STOP_POOL', None)

    request, ttype, n_stops = MEASURE[idx]
    print(f"=== LOCAL-806 MEASURE arm={arm} idx={idx} n={n_stops} ===", flush=True)
    print(f"request: {request!r}", flush=True)
    print(f"DISABLE_STOP_POOL={_os.environ.get('DISABLE_STOP_POOL')!r} "
          f"RESEARCH_BACKEND={_os.environ.get('RESEARCH_BACKEND')} "
          f"DB set={bool(_os.environ.get('DATABASE_URL'))}", flush=True)

    from live_run_meter import LiveRunMeter
    import generate_tour_text as g

    meter = LiveRunMeter(f'LOCAL-806-{arm}')
    t0 = time.time()
    text = None
    try:
        text, _out, _coords = g.generate_tour_text(request, ttype, None, n_stops)
    finally:
        dt = time.time() - t0
        try:
            meter.add_generation(g)
        except Exception:
            pass
        try:
            meter.record()
        except Exception:
            pass
        try:
            meter.uninstall()
        except Exception:
            pass

    n_delivered = 0
    if text:
        import re
        n_delivered = len(re.findall(r'(?mi)^Stop\s+\d+:', text))
        with open(out_path, 'w') as f:
            f.write(text)

    b = meter.breakdown()
    total = meter.total_usd()
    print(f"\n=== RESULT arm={arm} idx={idx} ===", flush=True)
    print(f"  wall_seconds   : {dt:.1f}", flush=True)
    print(f"  cost_usd_total : {total:.4f}", flush=True)
    print(f"  openai         : {b['openai']:.4f}", flush=True)
    print(f"  serper         : {b['serper']:.4f}", flush=True)
    print(f"  gemini_grounding: {b['gemini_grounding']['usd']:.4f} "
          f"(queries={b['gemini_grounding']['queries']})", flush=True)
    print(f"  stops_delivered: {n_delivered}", flush=True)
    print(f"  text_saved     : {out_path if text else '(none)'}", flush=True)
    # One-line machine-readable result for the driver to parse.
    print(f"MEASURE_RESULT arm={arm} idx={idx} wall_s={dt:.1f} "
          f"cost_usd={total:.4f} stops={n_delivered}", flush=True)


if __name__ == '__main__':
    main()
