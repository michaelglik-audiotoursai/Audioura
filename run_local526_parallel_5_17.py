#!/usr/bin/env python3
"""run_local526_parallel_5_17.py — LOCAL-526 acceptance measurement.

Parallelise PHASE 5.17's per-stop retries. This runner generates the two tours
the ticket names — a 4-stop church tour and a 4-stop Logan tour — under two
regimes on the SAME refactored code path:

  * SERIAL:   STORY_RETRY_MAX_WORKERS=1  (the retry pool is forced to one worker,
              i.e. the old one-after-another behaviour)
  * PARALLEL: the default pool (min(len, 5))

For each run it captures wall time, the [TIMING] TOTAL story_first phase, the
PHASE 5.17 `retry summary` line and the [D534] repetition-scan lines, so that
stop count / accept-reject / retry counts can be compared serial-vs-parallel.

D261 env is mandatory and set below. Run preflight.py first.
"""
import io
import os
import re
import sys
import time
import json
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

for line in open(os.path.join(HERE, '.env')):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['STORIED_MODE'] = 'true'
os.environ.setdefault('DATABASE_URL',
                      'postgresql://admin:password123@localhost:5433/audiotours')
os.environ.setdefault('SNIPPET_CAP_PER_STOP', '20')

from generate_tour_text import generate_tour_text  # noqa: E402

TOURS = [
    ('church', 'Our Lady Help of Christians Catholic Church, Newton MA', 'museum', 4),
    ('logan',  'Walking tour around Logan Airport, Boston MA',          'walking', 4),
]

STAMP = time.strftime('%Y%m%d_%H%M')


def _extract(log):
    total = None
    story_first = None
    m = re.search(r'\[TIMING\] TOTAL wall=([\d.]+)s phases: (.*)', log)
    if m:
        total = float(m.group(1))
        sf = re.search(r'story_first=([\d.]+)s', m.group(2))
        if sf:
            story_first = float(sf.group(1))
    retry_summary = None
    rs = re.search(r'\[LOCAL-474\] retry summary: .*', log)
    if rs:
        retry_summary = rs.group(0).strip()
    triggers = None
    tg = re.search(r'\[LOCAL-487\] triggers: .*', log)
    if tg:
        triggers = tg.group(0).strip()
    d534 = re.findall(r'\[D534\] .*', log)
    # count stops in the produced tour text is done by the caller
    return {
        'wall_total_timing': total,
        'story_first_s': story_first,
        'retry_summary': retry_summary,
        'triggers': triggers,
        'd534_lines': d534,
    }


def _count_stops(text):
    return len(re.findall(r'^Stop\s+\d+:', text, flags=re.MULTILINE))


def run_one(name, location, tour_type, stops, mode):
    if mode == 'serial':
        os.environ['STORY_RETRY_MAX_WORKERS'] = '1'
    else:
        os.environ.pop('STORY_RETRY_MAX_WORKERS', None)

    out = os.path.join(HERE, f'LOCAL526_{name}_{mode}_{STAMP}.txt')
    print(f"\n{'='*74}\n  {name.upper()} — {mode.upper()} — {stops} stops\n"
          f"  {location}\n{'='*74}", flush=True)

    buf = io.StringIO()
    t0 = time.time()
    with contextlib.redirect_stdout(buf):
        text, _a, _b = generate_tour_text(location, tour_type, out, stops)
    elapsed = time.time() - t0
    log = buf.getvalue()
    # echo the captured log so it is visible in the run output
    sys.stdout.write(log)
    sys.stdout.flush()

    if not text:
        print(f"\n  FAILED: no text returned for {name}/{mode}", flush=True)
        return None

    open(out, 'w', encoding='utf-8').write(text)
    info = _extract(log)
    info.update({
        'name': name, 'mode': mode, 'location': location,
        'tour_type': tour_type, 'stops_requested': stops,
        'wall_wrapped_s': round(elapsed, 1),
        'chars': len(text), 'stop_count': _count_stops(text),
        'out_file': os.path.basename(out),
    })
    print(f"\n  [{name}/{mode}] wall={elapsed:.1f}s  "
          f"story_first={info['story_first_s']}s  stops={info['stop_count']}  "
          f"chars={len(text)}", flush=True)
    print(f"  [{name}/{mode}] {info['retry_summary']}", flush=True)
    return info


def main():
    results = []
    for name, location, tour_type, stops in TOURS:
        for mode in ('serial', 'parallel'):
            r = run_one(name, location, tour_type, stops, mode)
            if r is None:
                print("ABORT: a run failed", flush=True)
                sys.exit(1)
            results.append(r)

    out_json = os.path.join(HERE, f'LOCAL526_RESULTS_{STAMP}.json')
    json.dump(results, open(out_json, 'w'), indent=2, ensure_ascii=False)

    print(f"\n\n{'#'*74}\n#  SUMMARY\n{'#'*74}")
    print(f"{'tour':<8} {'mode':<9} {'wall':>7} {'story_first':>12} {'stops':>6}")
    for r in results:
        print(f"{r['name']:<8} {r['mode']:<9} {r['wall_wrapped_s']:>6.1f}s "
              f"{str(r['story_first_s']):>11}s {r['stop_count']:>6}")
    print(f"\nresults -> {os.path.basename(out_json)}")
    for r in results:
        print(f"\n[{r['name']}/{r['mode']}] {r['retry_summary']}")
        print(f"[{r['name']}/{r['mode']}] {r['triggers']}")


if __name__ == '__main__':
    main()
