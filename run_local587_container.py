#!/usr/bin/env python3
"""run_local587_container.py — LOCAL-587 live timing (IN MY OWN CONTAINER).

Mirrors run_local583_container.py, but keeps the container's OWN env (the
subscribed switches STORY_RETRY_KEEP_BEST / STORY_RETRY_EARLY_STOP /
TOUR_STORY_MODEL=gpt-4.1 injected via --env-file) so the measurement matches the
LEAD baseline for this ticket. Prints the engine's `[TIMING] TOTAL` line and the
delivered stop list so the text-phase wall time and story counts are auditable.

OpenAI hard cap $3 (ticket).

Usage inside the container:
    python3 run_local587_container.py 1
    python3 run_local587_container.py 2
"""
import os
import re
import sys
import time

os.environ.setdefault('STORIED_MODE', 'true')
os.environ['DISABLE_TOUR_CACHE'] = '1'          # tour-output cache off; venue_corpus cache stays ON
os.environ['COST_HARD_LIMIT_USD'] = '3.00'      # OpenAI hard cap $3 (ticket)

LOCATION = 'Griffin museum of photography, Winchester, MA'
STOPS = 5
run_tag = (sys.argv[1] if len(sys.argv) > 1 else '1')
OUT = f'/app/tours/LOCAL587_GRIFFIN_RUN{run_tag}.txt'

print(f"=== LOCAL-587 live container run {run_tag} ===")
print(f"location    : {LOCATION}")
print(f"stops       : {STOPS} (requested)")
print(f"story model : {os.environ.get('TOUR_STORY_MODEL', '(default)')}")
print(f"keep_best   : {os.environ.get('STORY_RETRY_KEEP_BEST', '(unset)')}  "
      f"early_stop : {os.environ.get('STORY_RETRY_EARLY_STOP', '(unset)')}")
print(f"cost cap    : ${os.environ['COST_HARD_LIMIT_USD']}")

from generate_tour_text import generate_tour_text  # noqa: E402

t0 = time.time()
text, out_file, _coords = generate_tour_text(LOCATION, 'museum', OUT, STOPS)
elapsed = time.time() - t0

if not text:
    try:
        from generate_tour_text import _LAST_CLEAN_FAIL_EVIDENCE
        print(f"\nRUN {run_tag}: CLEAN FAIL after {elapsed:.1f}s")
        print(f"  evidence: {_LAST_CLEAN_FAIL_EVIDENCE}")
    except Exception as e:
        print(f"\nRUN {run_tag}: no text, evidence unavailable ({e})")
    sys.exit(1)

delivered = len(re.findall(r'(?mi)^\s*Stop\s+\d+\s*[:\-]', text))
print(f"\nRUN {run_tag}: {len(text)} chars in {elapsed:.1f}s -> {os.path.basename(OUT)}")
print(f"RUN {run_tag}: delivered stops = {delivered} / requested {STOPS}")
print(f"RUN {run_tag}: STOP LIST:")
for m in re.finditer(r'(?mi)^\s*(Stop\s+\d+\s*[:\-].*)$', text):
    print(f"   {m.group(1).strip()[:110]}")
