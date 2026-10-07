#!/usr/bin/env python3
"""run_local583_container.py — LOCAL-583 D4 live acceptance (IN CONTAINER, D608).

Runs the Griffin request through the REAL generation path inside the shipping
tour-generator container. Prints the delivered stop list and the engine's
`[TIMING] TOTAL` line so the text-phase wall time is auditable. Run twice in a
row: the first run writes a fresh (chrome-free) venue_corpus row at
CORPUS_VERSION=5; the second must HIT that fresh cache and still deliver the
same exhibition stops.

Env (inside the container): DATABASE_URL already points at postgres-2, keys are
injected by compose. We only add the acceptance switches here.

Usage (via docker exec):
    python3 run_local583_container.py 1   # first run (cache miss, writes fresh)
    python3 run_local583_container.py 2   # second run (cache hit, same stops)
"""

# [LOCAL-613] Meter + cap this isolated run. auto_meter installs the per-task
# TEST_GEMINI_MAX_USD cap (default $1.00, ALL providers combined) at the grounding
# counter and writes ONE cost_ledger row (user_id='LOCAL-583', description='test run')
# at process exit — even if the cap or any error stops the run. One line; every
# future harness should do the same.
import os as _os613  # noqa: E402
import sys as _sys613  # noqa: E402
_sys613.path.insert(0, _os613.path.join(
    _os613.path.dirname(_os613.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter  # noqa: E402
    _live_run_meter.auto_meter('LOCAL-583')
except Exception as _meter_err:  # metering must never break a run
    print(f"[LOCAL-613] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")
import os
import re
import sys
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'          # tour-output cache off; venue_corpus cache stays ON
os.environ['TOUR_LLM_MODEL'] = 'gpt-4o'
os.environ['COST_HARD_LIMIT_USD'] = '3.00'      # OpenAI hard cap $3 (ticket)

LOCATION = 'Griffin museum of photography, Winchester, MA'
STOPS = 5
run_tag = (sys.argv[1] if len(sys.argv) > 1 else '1')
OUT = f'/app/tours/LOCAL583_GRIFFIN_RUN{run_tag}.txt'

print(f"=== LOCAL-583 D4 container run {run_tag} ===")
print(f"location : {LOCATION}")
print(f"stops    : {STOPS} (requested)")
print(f"model    : {os.environ['TOUR_LLM_MODEL']}   cap: ${os.environ['COST_HARD_LIMIT_USD']}")

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
