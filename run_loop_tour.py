#!/usr/bin/env python3
"""run_loop_tour.py — D511: full tour with the credit_line loop ON.

`STORY_LOOP_ENABLED=1` is the only difference from
`run_full_tour_release_check.py`. Everything else — D261's mandatory env,
DISABLE_TOUR_CACHE, the stop count — is identical, so the two runs are
comparable and the loop is the single variable.
"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
for line in open(os.path.join(HERE, '.env')):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['STORIED_MODE'] = 'true'
os.environ['STORY_LOOP_ENABLED'] = '1'
os.environ.setdefault('DATABASE_URL',
                      'postgresql://admin:password123@localhost:5433/audiotours')
os.environ.setdefault('SNIPPET_CAP_PER_STOP', '20')

# [D523] Overridable so a second subject can be run without editing the file.
LOCATION = os.environ.get('LOOP_TOUR_LOCATION',
                          'Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA')
STOPS = int(os.environ.get('LOOP_TOUR_STOPS', '3'))
OUT = os.path.join(HERE, os.environ.get("LOOP_TOUR_OUT",
                   f"TOUR_LOOP_{time.strftime('%Y%m%d_%H%M')}.txt"))
print(f"location: {LOCATION}\nstops   : {STOPS}\nloop    : ON\nout     : {os.path.basename(OUT)}\n")

from generate_tour_text import generate_tour_text  # noqa: E402
t0 = time.time()
text, out_file, _ = generate_tour_text(LOCATION, 'museum', OUT, STOPS)
if not text:
    print("\nFAILED: no text returned"); sys.exit(1)
print(f"\nOK {len(text)} chars in {time.time()-t0:.0f}s -> {os.path.basename(OUT)}")
