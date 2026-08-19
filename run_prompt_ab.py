#!/usr/bin/env python3
"""run_prompt_ab.py — A/B two story-prompt variants over N runs each.

**Why this exists as a file rather than a shell loop.** D486's A/B of the story
pass was run ad hoc and lived in one session's context plus a stray log for an
hour; the decision record nearly inherited the recommendation without the
evidence. An A/B that cannot be re-run identically is not a measurement.

**What it does NOT do.** It does not decide anything, and it does not report a
winner on a difference it cannot resolve. D484 measured a single-run sd of 4.9
index points; at n runs per arm the standard error of the difference is
`sd * sqrt(2/n)`, so 5-per-arm resolves roughly 10 points and nothing finer.
This prints the CI and says "indistinguishable" whenever it straddles zero,
which is the sentence D486 had to be written to record.

**Arms are alternated, never blocked.** Serper results, model sampling and OpenAI
load all drift over a session; running all of arm A then all of arm B confounds
the arm with the clock.

Usage:
    python3 run_prompt_ab.py --runs 5 --var STORY_PROMPT_VARIANT --arms v2,v1
    python3 run_prompt_ab.py --runs 3 --var STORY_PASS_ENABLED --arms 1,0

Writes PROMPT_AB_<timestamp>.log with every run's full output preserved, because
a mean with no way back to the tours it came from is not evidence either.
"""
import argparse
import os
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime

RUNNER = 'run_full_tour_release_check.py'

# "[LOCAL-485] index mean 58.3 over 3 stop(s), range 46-76"
_INDEX = re.compile(r'\[LOCAL-485\]\s+index mean\s+([0-9.]+)\s+over\s+(\d+)\s+stop')
# "[D489] material kind: ... kind=inert volume=rich ..."
_KIND = re.compile(r'\[D489\] material kind:.*?kind=(\w+)\s+volume=(\w+)')


def one_run(env_var: str, value: str, log) -> dict:
    env = dict(os.environ)
    env[env_var] = value
    env.setdefault('DISABLE_TOUR_CACHE', '1')
    env.setdefault('STORIED_MODE', 'true')
    env.setdefault('DATABASE_URL',
                   'postgresql://admin:password123@localhost:5433/audiotours')
    started = time.time()
    proc = subprocess.run([sys.executable, RUNNER], env=env,
                          capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    log.write(f"\n{'=' * 78}\nARM {env_var}={value}  "
              f"{datetime.now():%H:%M:%S}  exit={proc.returncode}\n{'=' * 78}\n")
    log.write(out)
    log.flush()

    m = _INDEX.search(out)
    kinds = _KIND.findall(out)
    return {
        'arm': value,
        'index': float(m.group(1)) if m else None,
        'stops': int(m.group(2)) if m else 0,
        'seconds': round(time.time() - started, 1),
        'exit': proc.returncode,
        'disagreements': sum(1 for k, v in kinds
                             if k == 'inert' and v in ('rich', 'medium')),
        'kind_rows': kinds,
    }


def summarise(results, arms):
    print(f"\n{'=' * 70}\nRESULT\n{'=' * 70}")
    means = {}
    for arm in arms:
        vals = [r['index'] for r in results if r['arm'] == arm and r['index'] is not None]
        if not vals:
            print(f"  arm {arm!r}: no usable runs")
            continue
        means[arm] = statistics.mean(vals)
        sd = statistics.stdev(vals) if len(vals) > 1 else float('nan')
        print(f"  arm {arm!r}: n={len(vals)} mean={means[arm]:.1f} "
              f"sd={sd:.1f} runs={[round(v, 1) for v in vals]}")

    if len(means) != 2:
        print("\n  Cannot compare — one arm produced no usable runs.")
        return

    a, b = arms[0], arms[1]
    va = [r['index'] for r in results if r['arm'] == a and r['index'] is not None]
    vb = [r['index'] for r in results if r['arm'] == b and r['index'] is not None]
    diff = means[a] - means[b]
    # Pooled sd, then SE of the difference. Small n, so this is indicative only.
    try:
        pooled = statistics.stdev(va + vb)
        se = pooled * ((1 / len(va) + 1 / len(vb)) ** 0.5)
        lo, hi = diff - 1.96 * se, diff + 1.96 * se
        print(f"\n  difference ({a} - {b}) = {diff:+.1f}")
        print(f"  pooled sd {pooled:.1f}, SE {se:.1f}, 95% CI {lo:+.1f} to {hi:+.1f}")
        if lo <= 0 <= hi:
            print(f"\n  *** INDISTINGUISHABLE FROM ZERO. Do not report a winner. ***")
            print(f"      At n={len(va)}/{len(vb)} this design resolves about "
                  f"{1.96 * se:.0f} points.")
        else:
            print(f"\n  Difference excludes zero. Still one exhibition, one day — "
                  f"replicate before building on it.")
    except statistics.StatisticsError:
        print("\n  Too few runs to compute a CI.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', type=int, default=5, help='runs PER ARM')
    ap.add_argument('--var', default='STORY_PASS_ENABLED')
    ap.add_argument('--arms', default='1,0', help='comma-separated arm values')
    args = ap.parse_args()

    arms = [a.strip() for a in args.arms.split(',') if a.strip()]
    if len(arms) != 2:
        sys.exit('need exactly two arms')

    stamp = datetime.now().strftime('%Y%m%d_%H%M')
    path = f'PROMPT_AB_{stamp}.log'
    results = []
    print(f"A/B on {args.var}: {arms[0]} vs {arms[1]}, {args.runs} runs each, "
          f"alternating. Log -> {path}")

    with open(path, 'w') as log:
        for i in range(args.runs):
            for arm in arms:                      # alternate, never block
                r = one_run(args.var, arm, log)
                results.append(r)
                print(f"  run {len(results):2d}  arm={arm:>3}  "
                      f"index={r['index']}  {r['seconds']}s  "
                      f"disagreements={r['disagreements']}")

    summarise(results, arms)

    total_dis = sum(r['disagreements'] for r in results)
    total_rows = sum(len(r['kind_rows']) for r in results)
    if total_rows:
        print(f"\n  D489 kind-vs-volume: {total_dis}/{total_rows} stop-observations "
              f"had enough material of the wrong kind "
              f"({100 * total_dis / total_rows:.0f}%)")
    print(f"\n  Full output preserved in {path}")


if __name__ == '__main__':
    main()
