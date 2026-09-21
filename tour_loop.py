#!/usr/bin/env python3
"""The tour-quality loop: generate -> score -> diagnose -> fix -> regenerate.

Michael, 2026-09-21: *"at some point I will rely on your judgement and the
described 3 steps can be done by you automatically informing me but not continue
without my permission unless I stop you."*

**The rule this runs under already existed.** CLAUDE.md RULE ZERO: do not stop and
ask; ask only before something irreversible. Fixing a bug is `git revert`-able and
generating a tour inside an agreed ceiling is reversible. LEAD asked permission for
both anyway, repeatedly — that was the failure, not a missing mechanism. This file
exists so a future session inherits the loop instead of re-deriving it.

WHAT THE LOOP MAY DO WITHOUT ASKING
  * generate tours, up to the spend ceiling
  * score them (tour_quality.py) and diagnose a defect
  * fix code, commit, push a branch, re-run
  * dispatch a kiro-cli critic (see below)

WHAT IT MUST STOP FOR
  * spending past the ceiling
  * deploying anything, or writing to the production database
  * deleting files the user has not agreed to lose
  * a judgement about whether a tour is INTERESTING — see below

THE HONEST LIMIT. `tour_quality.py` measures defects with an objective signature:
missing stops, truncated fragments, repeated episodes, refuted claims, a named
death with no circumstances, zero named people. It cannot measure whether a tour is
worth listening to. Round 4 scored 3/3 clean while a Security Checkpoint stop read
"a carefully choreographed dance of safety and efficiency" — the glossary prose
Michael has objected to from the start. **So the loop drives the counters to zero
and then hands over.** That is not a compromise; it is the shape of the problem.

THE SECOND CRITIC (Michael's idea, 2026-09-21). He observed that several engines —
Claude, Meta AI, Amazon Q — critique tours well, "sometimes better than I can". The
machinery is already here: `kiro_dispatcher.py` forks headless `kiro-cli` (Amazon's
agentic CLI) per task file, and every LOCAL-* task this month ran through it. What
is new is pointing it at CRITIQUE rather than implementation, and pointing it at
the gap: **ask it whether the tour is dull, not whether it has defects** — we can
already count defects.

Two constraints on that, learned the hard way:
  * A critic's finding is a CLAIM, not a fact. D423: two instruments disagreed and
    LEAD nearly published the wrong one. Reproduce a finding before fixing it.
  * A critic must not write the rule. Gates built on unverified premises have cost
    whole rounds (D579, where LEAD blamed an innocent gate twice). The critic
    reports; a human-reviewed change follows.

Usage:
    python3 tour_loop.py --venue "..." --stops 4 --runs 3 --out DIR [--ceiling 5.00]
    python3 tour_loop.py --score-only DIR
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
PAUSE = os.path.join(REPO, '.continuous_dev', 'PAUSE')
DEFAULT_CEILING = 5.00


def paused():
    """Michael can stop the loop without talking to anyone: touch the file."""
    return os.path.exists(PAUSE)


def spend_from_log(path):
    try:
        txt = open(path, errors='ignore').read()
    except Exception:
        return 0.0
    hits = re.findall(r'Total API cost: \$([0-9.]+)', txt)
    return float(hits[-1]) if hits else 0.0


def generate(venue, stops, out_path, log_path, runner):
    env = dict(os.environ)
    env.update({'DISABLE_TOUR_CACHE': '1', 'STORIED_MODE': 'true'})
    env.setdefault('DATABASE_URL',
                   'postgresql://admin:password123@localhost:5433/audiotours')
    with open(log_path, 'w') as log:
        subprocess.run([sys.executable, '-u', runner, venue, '', str(stops), out_path],
                       stdout=log, stderr=subprocess.STDOUT, env=env, cwd=REPO)
    return spend_from_log(log_path)


def score(out_dir, stops, building):
    sys.path.insert(0, REPO)
    import tour_quality as tq
    paths = sorted(glob.glob(os.path.join(out_dir, '*.txt')))
    return tq.score_batch(paths, requested_stops=stops, is_building_tour=building)


def critic_task_file(tour_path, venue):
    """Write a task file the dispatcher will hand to kiro-cli.

    It asks the ONE question tour_quality.py cannot answer.
    """
    tid = 'CRITIC-' + re.sub(r'\W+', '-', os.path.basename(tour_path))[:40]
    body = f"""# {tid} — is this tour DULL?

**Agent:** Mac Mini Kiro
**Read:** `{tour_path}`

Do NOT look for defects. They are already measured by `tour_quality.py` — missing
stops, truncated sentences, repeated episodes, refuted claims. This tour passes all
of those. The question is the one no counter answers:

**Would a listener standing at each stop want to keep listening, and why not?**

For EACH stop, answer:
  1. What is the single most interesting thing said here? Quote it.
  2. If nothing is interesting, say so plainly and say what the stop offers instead
     (a description of what the thing IS, atmosphere, a list of features).
  3. What could have been said, given this is "{venue}"? Name a person, an event or
     a dispute that belongs at this stop and is missing.

Then: rank the stops worst-first and say which ONE change would improve the tour most.

## PROCESS
Write your answer to `CRITIQUE_{tid}.md` at the repo root. Do not change any code.
Do not edit DECISIONS.md, CLAUDE.md, BACKLOG.md or .continuous_dev/STATUS.md.
Your findings are CLAIMS for LEAD to reproduce, not conclusions — say plainly when
you are inferring rather than reading.
"""
    path = os.path.join(REPO, f'new_kiro_session_is_required_{tid}.md')
    with open(path, 'w') as fh:
        fh.write(body)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--venue')
    ap.add_argument('--stops', type=int, default=4)
    ap.add_argument('--runs', type=int, default=3)
    ap.add_argument('--out')
    ap.add_argument('--ceiling', type=float, default=DEFAULT_CEILING)
    ap.add_argument('--building', action='store_true')
    ap.add_argument('--runner', default=os.path.join(REPO, 'scripts', 'run_tour.py'))
    ap.add_argument('--critic', action='store_true',
                    help='file a kiro-cli critique task when the batch is clean')
    ap.add_argument('--score-only')
    args = ap.parse_args()

    if args.score_only:
        print(json.dumps(score(args.score_only, args.stops, args.building), indent=2))
        return

    if paused():
        print('PAUSED — .continuous_dev/PAUSE exists; doing nothing.')
        return

    os.makedirs(args.out, exist_ok=True)
    spent = 0.0
    for i in range(1, args.runs + 1):
        if paused():
            print(f'PAUSED after {i - 1} run(s).')
            break
        if spent >= args.ceiling:
            print(f'CEILING reached (${spent:.2f} of ${args.ceiling:.2f}) — stopping.')
            break
        out = os.path.join(args.out, f'TOUR_{i}.txt')
        log = os.path.join(args.out, f'run_{i}.log')
        spent += generate(args.venue, args.stops, out, log, args.runner)
        print(f'  run {i}: ${spent:.2f} spent')

    result = score(args.out, args.stops, args.building)
    print(json.dumps(result, indent=2))
    print(f'\nSPEND ${spent:.2f} of ${args.ceiling:.2f}')

    if result.get('consistent'):
        print('CLEAN AND CONSISTENT — the counters can say no more.')
        if args.critic:
            best = max(result['rows'],
                       key=lambda r: r['metrics']['named_people'])['path']
            t = critic_task_file(os.path.join(args.out, best), args.venue)
            print(f'  critic task filed: {os.path.basename(t)}')
        print('HAND TO MICHAEL: is it interesting?')
    else:
        print('NOT CLEAN — diagnose, fix, re-run. Do not ask permission (RULE ZERO).')


if __name__ == '__main__':
    main()
