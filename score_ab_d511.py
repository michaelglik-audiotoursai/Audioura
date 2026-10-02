#!/usr/bin/env python3
"""score_ab_d511.py — score every tour of the D511 A/B with ONE instrument.

`run_full_tour_release_check.py` scores its own output and `run_loop_tour.py`
does not, so the two arms would otherwise be measured by different code paths.
This scores both from the .txt on disk, with the same `evaluate_story` call and
the same corpus, and prints per-arm means plus the per-stop table.

Usage:  python3 score_ab_d511.py TOUR_A.txt TOUR_B.txt ...
        (arm is inferred from the filename: TOUR_LOOP_* is ON, TOUR_MFA_* OFF)
"""
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from gate_fp_probe import parse_tour        # noqa: E402
from evaluate_story import evaluate_story   # noqa: E402

CORPUS_PATH = os.path.join(HERE, 'story_lab_state', 'stop2_page_text.txt')
CORPUS = open(CORPUS_PATH, encoding='utf-8').read() if os.path.exists(CORPUS_PATH) else ''


def arm_of(path):
    return 'ON' if os.path.basename(path).startswith('TOUR_LOOP') else 'OFF'


def main(paths):
    per_arm = {'OFF': [], 'ON': []}
    rows_out = []
    for p in paths:
        text = open(p, encoding='utf-8').read()
        arm = arm_of(p)
        stops = parse_tour(text)
        print(f"\n{os.path.basename(p)}   arm={arm}   {len(text)} chars   "
              f"{len(stops)} stops")
        print(f"{'#':>2}  {'stop':<44} {'idx':>4} {'hist':>5} {'detl':>5} "
              f"{'soc':>5} {'words':>6}")
        print('-' * 80)
        idxs = []
        for st in stops:
            ev = evaluate_story(st['description'], corpus=CORPUS)
            idxs.append(ev['valuation_index'])
            words = len((st['description'] or '').split())
            print(f"{st['n']:>2}  {st['name'][:44]:<44} {ev['valuation_index']:>4} "
                  f"{ev['historic']:>5} {ev['detail']:>5} {ev['social']:>5} "
                  f"{words:>6}")
            rows_out.append({'file': os.path.basename(p), 'arm': arm,
                             'stop': st['name'], 'index': ev['valuation_index'],
                             'historic': ev['historic'], 'detail': ev['detail'],
                             'social': ev['social'], 'words': words})
        if idxs:
            m = sum(idxs) / len(idxs)
            per_arm[arm].append(m)
            print('-' * 80)
            print(f"{'':>2}  {'TOUR MEAN':<44} {m:>4.1f}")

    print('\n' + '=' * 80)
    print('A/B SUMMARY — tour-mean valuation index')
    print('=' * 80)
    for arm in ('OFF', 'ON'):
        v = per_arm[arm]
        if not v:
            continue
        sd = statistics.stdev(v) if len(v) > 1 else float('nan')
        print(f"  loop {arm:<3} n={len(v)}  runs={[round(x, 1) for x in v]}  "
              f"mean={sum(v)/len(v):.2f}  sd={sd:.2f}")
    if per_arm['OFF'] and per_arm['ON']:
        off = sum(per_arm['OFF']) / len(per_arm['OFF'])
        on = sum(per_arm['ON']) / len(per_arm['ON'])
        print(f"\n  delta (ON - OFF) = {on - off:+.2f}")
        pooled = [x for a in per_arm.values() for x in a]
        if len(pooled) > 2:
            print(f"  pooled sd across all runs = {statistics.stdev(pooled):.2f}"
                  "   <- a delta smaller than this is noise (D484)")
    json.dump(rows_out, open(os.path.join(HERE, 'AB_D511_SCORES.json'), 'w'),
              indent=2, ensure_ascii=False)
    print(f"\n  rows -> AB_D511_SCORES.json")


if __name__ == '__main__':
    main(sys.argv[1:])
