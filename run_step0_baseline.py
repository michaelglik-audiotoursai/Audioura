#!/usr/bin/env python3
"""run_step0_baseline.py — the tour BEFORE any of the 7 steps engages.

Michael, 2026-08-20: *"generate 3 stop tour ... this is prior to any step
required for 7-step matrix engaged, then identify which stops require stories,
and then produce the matrix the first query should be based on and stop there."*

This is step 0. Everything the 7-step system does is switched OFF, so what comes
out is the tour the story machinery starts FROM. Read it as the baseline against
which every later step has to justify its cost.

WHAT IS OFF, and which step each flag corresponds to:

  GENERATION_TIER=free      steps 3b/3c/3d/4 — the free tier issues ZERO SERP
                            queries by construction (work_story_searcher R6), so
                            no query is built, nothing is retrieved, nothing is
                            ranked and no second model is asked. This is the
                            cleanest single switch for "before retrieval",
                            and it is the reason the tour below is written from
                            parametric memory plus the exhibition checklist only.
  DISABLE_STORY_WORTHINESS  step 2 — do not decide which stops deserve a story.
  DISABLE_STORY_REPLENISH   step 3d — no "learn more" round.
  DISABLE_STORY_LEADS       step 4 — no second model.
  DISABLE_STORY_INDEX       step 5 — no valuation index.
  STORY_PASS_ENABLED=0      D474 — no separate story pass.
  DISABLE_STORY_RETRY=1     steps 7a/7b/7c — the WHOLE of PHASE 5.17. [D499]
                            NOT covered by STORY_PASS_ENABLED=0: the retry block
                            is gated only on storied mode, so the first attempt
                            at this baseline had 7a firing on 3 stops and 7b
                            rotating on 3 — in a run whose entire purpose was to
                            show the tour before step 7 touches it. Verified by
                            grepping the log for the step markers rather than by
                            assuming the flags did what their names suggest.
  DISABLE_STORY_TOP_SIZE    step 7c belt-and-braces.

WHAT IS STILL ON, deliberately: the exhibition checklist (that is how we know
which three works are in the show at all), the stop-existence gate, and the
validation gates of step 6. Turning those off would produce a tour that could not
be compared with anything — ungrounded claims are not a baseline, they are noise.

D261's env is mandatory and unchanged: DISABLE_TOUR_CACHE=1 or a CACHED tour may
be scored (D262); DATABASE_URL or the stop-existence gate SILENTLY does not run.
"""
import os
import sys
import time

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

# ─── the 7 steps, all off ────────────────────────────────────────────────────
os.environ['GENERATION_TIER'] = 'free'
os.environ['DISABLE_STORY_WORTHINESS'] = '1'
os.environ['DISABLE_STORY_REPLENISH'] = '1'
os.environ['DISABLE_STORY_LEADS'] = '1'
os.environ['DISABLE_STORY_INDEX'] = '1'
os.environ['STORY_PASS_ENABLED'] = '0'
os.environ['DISABLE_STORY_RETRY'] = '1'
os.environ['DISABLE_STORY_TOP_SIZE'] = '1'

LOCATION = 'Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA'
STOPS = 3
STAMP = time.strftime('%Y%m%d_%H%M')
OUT = os.path.join(HERE, f'STEP0_BASELINE_{STAMP}.txt')

print(f"location : {LOCATION}")
print(f"stops    : {STOPS}")
print(f"out      : {os.path.basename(OUT)}")
print("7-step system: ALL OFF (see module docstring)\n")

from generate_tour_text import generate_tour_text  # noqa: E402

t0 = time.time()
text, out_file, _coords = generate_tour_text(LOCATION, 'museum', OUT, STOPS)
elapsed = time.time() - t0

if not text:
    print("\nFAILED: no text returned")
    sys.exit(1)

print(f"\nOK  {len(text)} chars in {elapsed:.1f}s -> {os.path.basename(OUT)}")
