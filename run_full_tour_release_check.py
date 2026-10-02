#!/usr/bin/env python3
"""run_full_tour_release_check.py — one full tour, every stop, scored.

Michael, 2026-08-18: *"generate the full tour including all the stories on all
stops to evaluate maybe we reached the acceptable point for Storied release."*

Run from the HOST, not the container: the container image is at code_sha 35cb1d4
and carries none of D466-D471. D261's env is mandatory —

  DISABLE_TOUR_CACHE=1   else a CACHED tour may be scored (D262)
  DATABASE_URL=...       else the stop-existence gate SILENTLY does not run (D261)

`SNIPPET_CAP_PER_STOP=20` is set here rather than changed in `snippet_ranker.py`:
the cap's default is a production cost decision and this run is the evidence for
making it, not the place to assume it.

Writes the tour, the full generation log, and a per-stop score table.
"""
import os
import sys
import time
import json

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

LOCATION = 'Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA'
STOPS = int(os.environ.get('RELEASE_CHECK_STOPS', '4'))
STAMP = time.strftime('%Y%m%d_%H%M')
OUT = os.path.join(HERE, f'TOUR_MFA_RELEASE_{STAMP}.txt')

print(f"location : {LOCATION}")
print(f"stops    : {STOPS}")
print(f"cap      : {os.environ['SNIPPET_CAP_PER_STOP']}")
print(f"out      : {os.path.basename(OUT)}\n", flush=True)

from generate_tour_text import generate_tour_text   # noqa: E402

t0 = time.time()
text, a, b = generate_tour_text(LOCATION, 'museum', OUT, STOPS)
elapsed = time.time() - t0

if not text:
    print("\nFAILED: no text returned")
    sys.exit(1)

open(OUT, 'w', encoding='utf-8').write(text)
print(f"\n{'=' * 70}")
print(f"GENERATED {len(text)} chars in {elapsed:.1f}s -> {os.path.basename(OUT)}")
print(f"{'=' * 70}\n", flush=True)

# ── score every stop with the same instrument the iteration chart used ──────
from gate_fp_probe import parse_tour            # noqa: E402
from evaluate_story import evaluate_story       # noqa: E402

corpus_path = os.path.join(HERE, 'story_lab_state', 'stop2_page_text.txt')
corpus = open(corpus_path, encoding='utf-8').read() if os.path.exists(corpus_path) else ''

stops = parse_tour(text)
rows = []
print(f"{'#':>2}  {'stop':<44} {'idx':>4} {'hist':>5} {'detl':>5} {'soc':>5}")
print('-' * 74)
for st in stops:
    ev = evaluate_story(st['description'], corpus=corpus)
    rows.append({'stop': st['name'], 'index': ev['valuation_index'],
                 'historic': ev['historic'], 'detail': ev['detail'],
                 'social': ev['social'], 'text': st['description'],
                 'orientation': st['orientation']})
    print(f"{st['n']:>2}  {st['name'][:44]:<44} {ev['valuation_index']:>4} "
          f"{ev['historic']:>5} {ev['detail']:>5} {ev['social']:>5}")

if rows:
    n = len(rows)
    print('-' * 74)
    print(f"{'':>2}  {'MEAN':<44} {sum(r['index'] for r in rows)/n:>4.0f} "
          f"{sum(r['historic'] for r in rows)/n:>5.0f} "
          f"{sum(r['detail'] for r in rows)/n:>5.0f} "
          f"{sum(r['social'] for r in rows)/n:>5.0f}")
    print(f"\n  stops with detail == 0 (no object named): "
          f"{sum(1 for r in rows if r['detail'] == 0)} of {n}")

json.dump({'location': LOCATION, 'stops_requested': STOPS, 'elapsed_s': elapsed,
           'chars': len(text), 'cap': os.environ['SNIPPET_CAP_PER_STOP'],
           'rows': rows},
          open(OUT.replace('.txt', '_SCORES.json'), 'w'), indent=2, ensure_ascii=False)
print(f"\n  scores -> {os.path.basename(OUT.replace('.txt', '_SCORES.json'))}")
