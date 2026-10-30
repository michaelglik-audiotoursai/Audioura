#!/usr/bin/env python3
"""run_local577_palais_live.py — LOCAL-577 acceptance: Palais Lascaris, Nice,
museum, 4 stops, run twice, exactly as GCloud runs it (gpt-4o), under a $2.00
OpenAI hard cap, with the stop-existence gate ON (DATABASE_URL set, D261) and the
tour cache OFF (D262).

The field defect (job b5982123, tour 431) was 4 requested -> 3 delivered because
D1v2 dropped a real stop on a canonical-title mismatch and R4 could not refill.
This run proves the fix in the real generation path.

Usage:  python3 run_local577_palais_live.py <run_number>
Writes: LOCAL577_PALAIS_RUN<run>.txt  (the tour) and prints the stop count.
"""

# [LOCAL-678] Install the network paid-API meter for this HOST-run process. In a
# container sitecustomize (PYTHONPATH=/opt/meter) does this; on the host nothing
# does, so without this line every OpenAI/Gemini/Serper call this harness makes
# would be invisible to paid_api_calls. Must be the first thing we do, before any
# paid-call module is imported. Never breaks a run (install_meter fails open).
import os as _os678  # noqa: E402
import sys as _sys678  # noqa: E402
_sys678.path.insert(0, _os678.path.join(
    _os678.path.dirname(_os678.path.abspath(__file__)), "_meter"))
try:
    import meter_bootstrap as _meter_bootstrap  # noqa: F401,E402  (installs the meter)
except Exception as _meter_err:  # metering must never break a run
    print("[LOCAL-678] network meter unavailable (%s): "
          "paid calls from this host run will not be metered" % (_meter_err,))
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Load .env (carries OPENAI_API_KEY) without overriding anything already set.
for line in open(os.path.join(HERE, '.env')):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# D261 host env: existence gate ON. D262: cache OFF so this is a real generation.
os.environ.setdefault('DATABASE_URL',
                       'postgresql://admin:password123@localhost:5433/audiotours')
os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'
# GCloud runs gpt-4o; cap OpenAI spend at $2.00 (COST_HARD_LIMIT_USD).
os.environ['TOUR_LLM_MODEL'] = 'gpt-4o'
os.environ['COST_HARD_LIMIT_USD'] = '2.00'

RUN = sys.argv[1] if len(sys.argv) > 1 else '1'
LOCATION = 'Palais Lascaris, Nice, France'
STOPS = 4
OUT = os.path.join(HERE, f'LOCAL577_PALAIS_RUN{RUN}.txt')

print(f"=== LOCAL-577 live run {RUN} ===")
print(f"location : {LOCATION}")
print(f"stops    : {STOPS} (requested)")
print(f"model    : {os.environ['TOUR_LLM_MODEL']}")
print(f"cap      : ${os.environ['COST_HARD_LIMIT_USD']}")
print(f"cache    : OFF   existence-gate DB: {'set' if os.environ.get('DATABASE_URL') else 'UNSET'}")
print(f"out      : {os.path.basename(OUT)}\n")

from generate_tour_text import generate_tour_text  # noqa: E402

t0 = time.time()
text, out_file, _coords = generate_tour_text(LOCATION, 'museum', OUT, STOPS)
elapsed = time.time() - t0

if not text:
    print(f"\nRUN {RUN} FAILED: no text returned after {elapsed:.1f}s")
    sys.exit(1)

# Count delivered stops from the written tour (Stop N: markers).
import re
delivered = len(re.findall(r'(?mi)^\s*Stop\s+\d+\s*[:\-]', text))
print(f"\nRUN {RUN}: {len(text)} chars in {elapsed:.1f}s -> {os.path.basename(OUT)}")
print(f"RUN {RUN}: delivered stops (Stop N: markers) = {delivered} / requested {STOPS}")
