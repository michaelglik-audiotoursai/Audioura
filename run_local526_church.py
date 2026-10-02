#!/usr/bin/env python3
"""run_local526_church.py — LOCAL-526 church before/after (2nd pair) + scoring.

Church (Our Lady Help of Christians, Newton MA) is the tour the field notes say
"works" and it reliably delivers 4 stops with heavy PHASE 5.17 activity. Serial
vs parallel on the same refactored code path; each output is scored with
tour_quality.score_tour (is_building_tour=True) so the `repeated` defect — the
one most likely to break under concurrency — is checked directly.
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
import tour_quality as tq  # noqa: E402

NAME = 'church'
LOCATION = 'Our Lady Help of Christians Catholic Church, Newton MA'
TOUR_TYPE = 'museum'
STOPS = 4
STAMP = time.strftime('%Y%m%d_%H%M')


def _extract(log):
    out = {'story_first_s': None, 'wall_total_timing': None,
           'retry_summary': None, 'triggers': None, 'workers': None,
           'd534_lines': []}
    m = re.search(r'\[TIMING\] TOTAL wall=([\d.]+)s phases: (.*)', log)
    if m:
        out['wall_total_timing'] = float(m.group(1))
        sf = re.search(r'story_first=([\d.]+)s', m.group(2))
        if sf:
            out['story_first_s'] = float(sf.group(1))
    for key, pat in (('retry_summary', r'\[LOCAL-474\] retry summary: .*'),
                     ('triggers', r'\[LOCAL-487\] triggers: .*')):
        mm = re.search(pat, log)
        if mm:
            out[key] = mm.group(0).strip()
    w = re.search(r'regenerating \d+ eligible stop\(s\) concurrently '
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
    out = os.path.join(HERE, f'LOCAL526_{NAME}2_{mode}_{STAMP}.txt')
    print(f"\n{'='*74}\n  {NAME.upper()} — {mode.upper()} — {STOPS} stops\n{'='*74}", flush=True)
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
    score = tq.score_tour(text, requested_stops=STOPS, is_building_tour=True)
    info.update({'mode': mode, 'wall_wrapped_s': round(elapsed, 1),
                 'chars': len(text),
                 'stop_count': len(re.findall(r'^Stop\s+\d+:', text, re.M)),
                 'clean': score['clean'], 'defects': score['defects'],
                 'metrics': score['metrics'], 'out_file': os.path.basename(out)})
    print(f"\n  [{NAME}/{mode}] wall={elapsed:.1f}s story_first={info['story_first_s']}s "
          f"workers={info['workers']} stops={info['stop_count']} clean={score['clean']}", flush=True)
    print(f"  [{NAME}/{mode}] {info['retry_summary']}", flush=True)
    print(f"  [{NAME}/{mode}] defects={json.dumps(score['defects'])}", flush=True)
    return info


def main():
    results = [run_one('serial'), run_one('parallel')]
    if any(r is None for r in results):
        print("ABORT: a run failed", flush=True)
        sys.exit(1)
    out_json = os.path.join(HERE, f'LOCAL526_CHURCH2_RESULTS_{STAMP}.json')
    json.dump(results, open(out_json, 'w'), indent=2, ensure_ascii=False)
    print(f"\n{'#'*74}\n#  CHURCH SUMMARY (pair 2)\n{'#'*74}")
    for r in results:
        print(f"{r['mode']:<9} wall={r['wall_wrapped_s']:>6.1f}s "
              f"story_first={str(r['story_first_s']):>7}s workers={r['workers']} "
              f"stops={r['stop_count']} clean={r['clean']} repeated={'repeated' in r['defects']}")
        print(f"    {r['retry_summary']}")
    print(f"\nresults -> {os.path.basename(out_json)}")


if __name__ == '__main__':
    main()
