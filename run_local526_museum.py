#!/usr/bin/env python3
"""run_local526_museum.py — LOCAL-526 second before/after tour (MFA museum).

The ticket names a Logan tour as the second acceptance tour, but on base
9839cf4 a 4-stop Logan tour cannot be generated at all: the facility need-spine
drops every stop on LOW geocode confidence (LOCAL-480/471 safety gate) and the
sightseeing fallback yields 1–2 stops after the existence gate — both upstream
of PHASE 5.17, which never executes. Evidence is in the submission.

This runs the MFA museum tour instead — the proven release-check tour that
reliably delivers 4 stops and exercises PHASE 5.17 heavily — serial vs parallel
on the same refactored code path, to give a real second before/after.
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

NAME = 'museum'
LOCATION = 'Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA'
TOUR_TYPE = 'museum'
STOPS = 4
STAMP = time.strftime('%Y%m%d_%H%M')


def _extract(log):
    out = {'wall_total_timing': None, 'story_first_s': None,
           'retry_summary': None, 'triggers': None, 'd534_lines': [],
           'workers': None}
    m = re.search(r'\[TIMING\] TOTAL wall=([\d.]+)s phases: (.*)', log)
    if m:
        out['wall_total_timing'] = float(m.group(1))
        sf = re.search(r'story_first=([\d.]+)s', m.group(2))
        if sf:
            out['story_first_s'] = float(sf.group(1))
    rs = re.search(r'\[LOCAL-474\] retry summary: .*', log)
    if rs:
        out['retry_summary'] = rs.group(0).strip()
    tg = re.search(r'\[LOCAL-487\] triggers: .*', log)
    if tg:
        out['triggers'] = tg.group(0).strip()
    w = re.search(r'PHASE 5\.17: regenerating \d+ eligible stop\(s\) concurrently '
                  r'\(max_workers=(\d+)\)', log)
    if w:
        out['workers'] = int(w.group(1))
    out['d534_lines'] = re.findall(r'\[D534\] .*', log)
    return out


def run_one(mode):
    if mode == 'serial':
        os.environ['STORY_RETRY_MAX_WORKERS'] = '1'
    else:
        os.environ.pop('STORY_RETRY_MAX_WORKERS', None)
    out = os.path.join(HERE, f'LOCAL526_{NAME}_{mode}_{STAMP}.txt')
    print(f"\n{'='*74}\n  {NAME.upper()} — {mode.upper()} — {STOPS} stops\n"
          f"  {LOCATION}\n{'='*74}", flush=True)
    buf = io.StringIO()
    t0 = time.time()
    with contextlib.redirect_stdout(buf):
        text, _a, _b = generate_tour_text(LOCATION, TOUR_TYPE, out, STOPS)
    elapsed = time.time() - t0
    log = buf.getvalue()
    sys.stdout.write(log)
    sys.stdout.flush()
    if not text:
        print(f"\n  FAILED: no text for {NAME}/{mode}", flush=True)
        return None
    open(out, 'w', encoding='utf-8').write(text)
    info = _extract(log)
    info.update({'name': NAME, 'mode': mode, 'wall_wrapped_s': round(elapsed, 1),
                 'chars': len(text),
                 'stop_count': len(re.findall(r'^Stop\s+\d+:', text, re.M)),
                 'out_file': os.path.basename(out)})
    print(f"\n  [{NAME}/{mode}] wall={elapsed:.1f}s story_first={info['story_first_s']}s "
          f"workers={info['workers']} stops={info['stop_count']} chars={len(text)}", flush=True)
    print(f"  [{NAME}/{mode}] {info['retry_summary']}", flush=True)
    return info


def main():
    results = [run_one('serial'), run_one('parallel')]
    if any(r is None for r in results):
        print("ABORT: a run failed", flush=True)
        sys.exit(1)
    out_json = os.path.join(HERE, f'LOCAL526_MUSEUM_RESULTS_{STAMP}.json')
    json.dump(results, open(out_json, 'w'), indent=2, ensure_ascii=False)
    print(f"\n{'#'*74}\n#  MUSEUM SUMMARY\n{'#'*74}")
    for r in results:
        print(f"{r['mode']:<9} wall={r['wall_wrapped_s']:>6.1f}s "
              f"story_first={str(r['story_first_s']):>7}s workers={r['workers']} "
              f"stops={r['stop_count']}")
        print(f"    {r['retry_summary']}")
        print(f"    {r['triggers']}")
    print(f"\nresults -> {os.path.basename(out_json)}")


if __name__ == '__main__':
    main()
