#!/usr/bin/env python3
"""LOCAL-518: Profile the story_first phase — measure, don't guess.

Runs a single tour through the REAL generate_tour_text pipeline with the
story-first path FORCED ON (L440_STORY_FIRST=true), captures every
[SF-STEP] / [SF-BREAKDOWN] / [SF-AGG] / [TIMING] line the instrumentation
emits, and prints a clean summary at the end.

Usage:
    python3 run_local518_profile.py "<location>" <total_stops> [tour_type]

Required env (D261) is set below if not already present.
"""
import io
import os
import re
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# --- Load .env (keys) ---
_env_path = Path.home() / "Audioura" / ".env"
if _env_path.exists():
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v

# --- Required env (D261) ---
os.environ.setdefault('DISABLE_TOUR_CACHE', '1')
os.environ.setdefault('DATABASE_URL',
                      'postgresql://admin:password123@localhost:5433/audiotours')
os.environ.setdefault('STORIED_MODE', 'true')
# Force story-first ON (it is gated OFF by default; D400)
os.environ['L440_STORY_FIRST'] = 'true'
os.environ.setdefault('GENERATION_TIER', 'plus')
os.environ.pop('PYTEST_CURRENT_TEST', None)
os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)

LOCATION = sys.argv[1] if len(sys.argv) > 1 else "Museum of Fine Arts, Boston, MA"
TOTAL_STOPS = int(sys.argv[2]) if len(sys.argv) > 2 else 4
TOUR_TYPE = sys.argv[3] if len(sys.argv) > 3 else "contained"

from generate_tour_text import generate_tour_text  # noqa: E402

OUTPUT_DIR = PROJECT_ROOT / "tours"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
_slug = re.sub(r'[^a-z0-9]+', '_', LOCATION.lower())[:40]
output_file = str(OUTPUT_DIR / f"local518_{_slug}.json")

print(f"{'#'*72}")
print(f"# LOCAL-518 story_first profile")
print(f"# Location : {LOCATION}")
print(f"# Stops    : {TOTAL_STOPS}   Tour type: {TOUR_TYPE}")
print(f"# L440_STORY_FIRST=true  STORIED_MODE={os.environ.get('STORIED_MODE')}")
print(f"{'#'*72}", flush=True)

buf = io.StringIO()


class _Tee(io.TextIOBase):
    """Write to both the real stdout and a capture buffer."""
    def __init__(self, real, cap):
        self.real = real
        self.cap = cap

    def write(self, s):
        self.real.write(s)
        self.cap.write(s)
        return len(s)

    def flush(self):
        self.real.flush()


start = time.time()
_real = sys.stdout
sys.stdout = _Tee(_real, buf)
try:
    result = generate_tour_text(
        location=LOCATION,
        tour_type=TOUR_TYPE,
        output_file=output_file,
        total_stops=TOTAL_STOPS,
        persona=None,
    )
finally:
    sys.stdout = _real
elapsed = time.time() - start

captured = buf.getvalue()

# --- Extract the timing lines ---
sf_step = [l for l in captured.splitlines() if '[SF-STEP]' in l]
sf_breakdown = [l for l in captured.splitlines() if '[SF-BREAKDOWN]' in l]
sf_agg = [l for l in captured.splitlines() if '[SF-AGG]' in l]
timing = [l for l in captured.splitlines() if '[TIMING]' in l]
l445 = [l for l in captured.splitlines()
        if '[LOCAL-445]' in l or '[LOCAL-440]' in l]

print(f"\n{'='*72}")
print(f"# LOCAL-518 CAPTURED TIMING — {LOCATION}")
print(f"{'='*72}")
print(f"generate_tour_text returned: "
      f"{'OK' if result and result[0] else 'None/FAILED'}   "
      f"wall={elapsed:.1f}s")

print(f"\n--- [TIMING] phase lines ({len(timing)}) ---")
for l in timing:
    print(l.strip())

print(f"\n--- [SF-BREAKDOWN] per-stop ({len(sf_breakdown)}) ---")
for l in sf_breakdown:
    print(l.strip())

print(f"\n--- [SF-AGG] batch aggregate ({len(sf_agg)}) ---")
for l in sf_agg:
    print(l.strip())

print(f"\n--- [SF-STEP] raw per-step ({len(sf_step)}) ---")
for l in sf_step:
    print(l.strip())

if not sf_step and not sf_breakdown:
    print("\n!!! NO story_first STEP TIMING CAPTURED !!!")
    print("    story_first did not run (likely tour_category != 'museum').")
    print("    Relevant [LOCAL-440/445] lines:")
    for l in l445:
        print("    " + l.strip())

# Persist the raw capture for the record
log_path = PROJECT_ROOT / f"LOCAL518_{_slug}.log"
with open(log_path, 'w') as f:
    f.write(captured)
print(f"\nRaw log written: {log_path}")
