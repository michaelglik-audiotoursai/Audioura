#!/usr/bin/env python3
"""LOCAL-437: MFA Unbound live run under enforce mode.

Proves:
1. The exemption fires (output: "[LOCAL-437] EXISTENCE-GATE: EXEMPT")
2. Stops are delivered (not dropped by the existence gate)
3. The LOCAL-372 page-grounding still operates (stops are on the venue page)

Gate mode: enforce. Without the exemption, all stops would be dropped (D389).
With the exemption, checklist/prose_llm-sourced stops bypass the gate and are
instead grounded by LOCAL-372's title_appears_in_page check.
"""
import json
import os
import re
import sys
import time
from io import StringIO
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# --- Environment ---
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

os.environ['STORIED_MODE'] = 'true'
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
os.environ['TOUR_LLM_MODEL'] = 'gpt-4o'
os.environ.pop('PYTEST_CURRENT_TEST', None)
os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)
os.environ['AUDIOURA_DB_TARGET'] = 'production'
os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'
os.environ['DISABLE_TOUR_CACHE'] = '1'

from generate_tour_text import generate_tour_text
from variance_harness import extract_per_stop_counts

LOCATION = "Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA"
TOUR_TYPE = "contained"
TOTAL_STOPS = 3
OUTPUT_FILE = str(PROJECT_ROOT / "tours" / "local437_mfa_unbound.json")

print(f"{'#'*70}")
print(f"# LOCAL-437: MFA Unbound — enforce mode with exemption")
print(f"# Location: {LOCATION}")
print(f"# Tour type: {TOUR_TYPE}")
print(f"# Stops: {TOTAL_STOPS}")
print(f"# Gate mode: enforce (STOP_EXISTENCE_GATE_MODE=enforce)")
print(f"# Expect: exemption fires, stops delivered")
print(f"{'#'*70}")

# Capture stdout to check for exemption log
import contextlib

captured = StringIO()

start = time.time()
with contextlib.redirect_stdout(captured):
    result = generate_tour_text(
        location=LOCATION,
        tour_type=TOUR_TYPE,
        output_file=OUTPUT_FILE,
        total_stops=TOTAL_STOPS,
        persona=None,
    )
elapsed = time.time() - start

output_log = captured.getvalue()
# Print the captured output
print(output_log)

print(f"\n{'='*70}")
print(f"MFA UNBOUND RESULTS")
print(f"{'='*70}")
print(f"Elapsed: {elapsed:.1f}s")
print(f"Gate mode: enforce (STOP_EXISTENCE_GATE_MODE=enforce)")

checks_passed = 0
checks_total = 3

# Check 1: Tour generated
if not result or not result[0]:
    print("FAIL: No tour generated")
    # Check if exemption was at least attempted
    if '[LOCAL-437] EXISTENCE-GATE: EXEMPT' in output_log:
        print("  (Exemption DID fire, but tour failed for another reason)")
    sys.exit(1)

tour_text = result[0]
counts = extract_per_stop_counts(tour_text)
num_stops = len(counts)
if num_stops >= 3:
    print(f"✓ Stops delivered: {num_stops}/{TOTAL_STOPS}")
    checks_passed += 1
else:
    print(f"✗ Stops: {num_stops}/{TOTAL_STOPS}")

# Check 2: Exemption fired
if '[LOCAL-437] EXISTENCE-GATE: EXEMPT' in output_log:
    print(f"✓ Exemption fired (checklist/prose_llm path)")
    # Extract the source
    match = re.search(r'EXEMPT — stops sourced from exhibition (\w+)', output_log)
    if match:
        print(f"  Source: {match.group(1)}")
    checks_passed += 1
else:
    print(f"✗ Exemption did NOT fire — check _exhibition_stops_source")
    # Look for what DID happen
    if 'EXISTENCE-GATE ENFORCE' in output_log:
        print(f"  Gate ran and may have dropped stops")
    if 'EXISTENCE-GATE: OFF' in output_log:
        print(f"  Gate was OFF")

# Check 3: LOCAL-372 grounding operated
if '[D1/LOCAL-372]' in output_log:
    print(f"✓ LOCAL-372 page-grounding operated")
    # Extract grounding result
    grounding_match = re.search(r'(\d+) exhibition stop\(s\) grounded', output_log)
    if grounding_match:
        print(f"  {grounding_match.group(1)} stops grounded against venue page")
    dropped_match = re.search(r'DROPPED (\d+) stop\(s\) absent from', output_log)
    if dropped_match:
        print(f"  {dropped_match.group(1)} stops dropped (not on page)")
    checks_passed += 1
else:
    print(f"✗ LOCAL-372 page-grounding did not operate")

# Per-stop detail
print(f"\nPer-stop detail:")
for stop_name, count in counts.items():
    status = "✓" if count >= 3 else "✗"
    print(f"  {status} {stop_name[:55]:55s} story_count={count}")

print(f"\n{'='*70}")
print(f"VERDICT: {'PASS' if checks_passed == checks_total else 'PARTIAL'} "
      f"({checks_passed}/{checks_total} checks)")
print(f"Gate mode: enforce")
print(f"{'='*70}")
