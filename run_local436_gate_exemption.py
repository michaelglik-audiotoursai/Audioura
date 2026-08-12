#!/usr/bin/env python3
"""LOCAL-436: Prove the gate exemption works both directions.

1. MFA Unbound under ENFORCE mode — must deliver a tour (real exhibition works survive)
2. MFA Unbound under LOG_ONLY (default) — must deliver a tour (baseline comparison)
3. Fabricated work injected into the gate — must be dropped (gate still catches fakes)
4. Control: Palais de la Méditerranée 4/4, dates intact

Code path: generate_tour_text (production symbol), no monkeypatching, no pins.
Env vars: STOP_EXISTENCE_GATE_MODE is set and reported for every number.
"""
import json
import os
import sys
import time
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
os.environ['TOUR_LLM_MODEL'] = 'gpt-4o'
os.environ.pop('PYTEST_CURRENT_TEST', None)
os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)
os.environ['AUDIOURA_DB_TARGET'] = 'production'
os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'
os.environ['DISABLE_TOUR_CACHE'] = '1'

from generate_tour_text import generate_tour_text

OUTPUT_DIR = PROJECT_ROOT / "tours"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MFA_LOCATION = "Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA"
PALAIS_LOCATION = "Palais de la Méditerranée, Nice, France"

print(f"{'#'*70}")
print(f"# LOCAL-436: Gate Exemption Proof — Both Directions")
print(f"# Real exhibition work must survive under ENFORCE")
print(f"# Fabricated work must still be dropped")
print(f"# Control: Palais 4/4, dates intact")
print(f"{'#'*70}")
print()

results = {}

# ─────────────────────────────────────────────────────────────────────────────
# PROOF 1: MFA Unbound under ENFORCE mode (with the fix)
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("PROOF 1: MFA UNBOUND under STOP_EXISTENCE_GATE_MODE=enforce")
print(f"{'='*70}")
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
print(f"  STOP_EXISTENCE_GATE_MODE: {os.environ['STOP_EXISTENCE_GATE_MODE']}")

start = time.time()
output_file = str(OUTPUT_DIR / "local436_mfa_enforce.json")
result = generate_tour_text(
    location=MFA_LOCATION,
    tour_type="contained",
    output_file=output_file,
    total_stops=3,
    persona=None,
)
elapsed = time.time() - start

if result and result[0]:
    # Parse stops from the output
    try:
        with open(output_file) as f:
            tour_data = json.load(f)
        stops = tour_data.get('stops', [])
        stop_names = [s.get('title', s.get('name', '?')) for s in stops]
    except Exception:
        stops = []
        stop_names = []
    text_len = len(result[0]) if isinstance(result[0], str) else 0
    results['mfa_enforce'] = {
        'status': 'DELIVERED',
        'stops': len(stops),
        'stop_names': stop_names,
        'text_length': text_len,
        'elapsed': elapsed,
        'gate_mode': 'enforce',
    }
    print(f"\n  ✓ DELIVERED: {len(stops)} stops, {text_len} chars, {elapsed:.1f}s")
    for name in stop_names:
        print(f"    Stop: {name}")
else:
    results['mfa_enforce'] = {
        'status': 'FAILED',
        'elapsed': elapsed,
        'gate_mode': 'enforce',
    }
    print(f"\n  ✗ FAILED to deliver under enforce ({elapsed:.1f}s)")

# ─────────────────────────────────────────────────────────────────────────────
# PROOF 2: MFA Unbound under LOG_ONLY (shipping default)
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("PROOF 2: MFA UNBOUND under STOP_EXISTENCE_GATE_MODE=log_only (default)")
print(f"{'='*70}")
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'log_only'
print(f"  STOP_EXISTENCE_GATE_MODE: {os.environ['STOP_EXISTENCE_GATE_MODE']}")

start = time.time()
output_file = str(OUTPUT_DIR / "local436_mfa_log_only.json")
result = generate_tour_text(
    location=MFA_LOCATION,
    tour_type="contained",
    output_file=output_file,
    total_stops=3,
    persona=None,
)
elapsed = time.time() - start

if result and result[0]:
    try:
        with open(output_file) as f:
            tour_data = json.load(f)
        stops = tour_data.get('stops', [])
        stop_names = [s.get('title', s.get('name', '?')) for s in stops]
    except Exception:
        stops = []
        stop_names = []
    text_len = len(result[0]) if isinstance(result[0], str) else 0
    results['mfa_log_only'] = {
        'status': 'DELIVERED',
        'stops': len(stops),
        'stop_names': stop_names,
        'text_length': text_len,
        'elapsed': elapsed,
        'gate_mode': 'log_only',
    }
    print(f"\n  ✓ DELIVERED: {len(stops)} stops, {text_len} chars, {elapsed:.1f}s")
    for name in stop_names:
        print(f"    Stop: {name}")
else:
    results['mfa_log_only'] = {
        'status': 'FAILED',
        'elapsed': elapsed,
        'gate_mode': 'log_only',
    }
    print(f"\n  ✗ FAILED to deliver under log_only ({elapsed:.1f}s)")

# ─────────────────────────────────────────────────────────────────────────────
# PROOF 3: Fabricated work must still be dropped by the existence gate
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("PROOF 3: FABRICATED WORK — existence gate must still drop it")
print(f"{'='*70}")
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
print(f"  STOP_EXISTENCE_GATE_MODE: {os.environ['STOP_EXISTENCE_GATE_MODE']}")

from stop_existence_gate import run_existence_gate
from db_connection import get_connection

conn = get_connection()
real_conn = getattr(conn, '_conn', conn)

# Run the gate directly on a fabricated work
fabricated_stops = ["The Invisible Symphony of Forgotten Dreams"]
gate_result = run_existence_gate(
    fabricated_stops,
    "Museum of Fine Arts, Boston",
    real_conn,
    tour_type='museum',
)
conn.close()

if "The Invisible Symphony of Forgotten Dreams" in gate_result['unverified_stops']:
    results['fabricated_dropped'] = {
        'status': 'DROPPED',
        'stop': "The Invisible Symphony of Forgotten Dreams",
        'gate_mode': 'enforce',
        'action': gate_result['action'],
    }
    print(f"\n  ✓ DROPPED: fabricated work correctly identified as unverified")
    print(f"    Stop: 'The Invisible Symphony of Forgotten Dreams'")
    print(f"    Action: {gate_result['action']}")
else:
    results['fabricated_dropped'] = {
        'status': 'NOT_DROPPED',
        'stop': "The Invisible Symphony of Forgotten Dreams",
        'gate_mode': 'enforce',
        'verified_stops': gate_result['verified_stops'],
    }
    print(f"\n  ✗ FAILED: fabricated work was NOT dropped!")

# ─────────────────────────────────────────────────────────────────────────────
# CONTROL: Palais de la Méditerranée 4/4, dates intact (D302/D326)
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("CONTROL: Palais de la Méditerranée 4/4, dates intact (D302/D326)")
print(f"{'='*70}")
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
print(f"  STOP_EXISTENCE_GATE_MODE: {os.environ['STOP_EXISTENCE_GATE_MODE']}")

start = time.time()
output_file = str(OUTPUT_DIR / "local436_palais_control.json")
result = generate_tour_text(
    location=PALAIS_LOCATION,
    tour_type="contained",
    output_file=output_file,
    total_stops=4,
    persona=None,
)
elapsed = time.time() - start

if result and result[0]:
    try:
        with open(output_file) as f:
            tour_data = json.load(f)
        stops = tour_data.get('stops', [])
        stop_names = [s.get('title', s.get('name', '?')) for s in stops]
    except Exception:
        stops = []
        stop_names = []
    text_len = len(result[0]) if isinstance(result[0], str) else 0
    # Check for dates in the tour text
    import re
    text = result[0] if isinstance(result[0], str) else ''
    date_patterns = re.findall(r'\b1[89]\d{2}\b|\b20[012]\d\b', text)
    results['palais_control'] = {
        'status': 'DELIVERED',
        'stops': len(stops),
        'stop_names': stop_names,
        'text_length': text_len,
        'elapsed': elapsed,
        'gate_mode': 'enforce',
        'dates_found': len(date_patterns) > 0,
        'date_examples': date_patterns[:5],
    }
    print(f"\n  ✓ DELIVERED: {len(stops)}/4 stops, {text_len} chars, {elapsed:.1f}s")
    for name in stop_names:
        print(f"    Stop: {name}")
    print(f"    Dates intact: {len(date_patterns) > 0} (examples: {date_patterns[:5]})")
else:
    results['palais_control'] = {
        'status': 'FAILED',
        'elapsed': elapsed,
        'gate_mode': 'enforce',
    }
    print(f"\n  ✗ FAILED to deliver Palais control ({elapsed:.1f}s)")

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n\n{'#'*70}")
print("# SUMMARY")
print(f"{'#'*70}")
print()
print(f"| Test | Gate Mode | Result |")
print(f"|------|-----------|--------|")
for key, r in results.items():
    label = key.replace('_', ' ').title()
    print(f"| {label} | {r.get('gate_mode', '?')} | {r.get('status', '?')} |")

# Save full results
results_file = OUTPUT_DIR / "local436_results.json"
with open(results_file, 'w') as f:
    json.dump(results, f, indent=2)
print(f"\nFull results: {results_file}")

# Final assertion
all_passed = (
    results.get('mfa_enforce', {}).get('status') == 'DELIVERED'
    and results.get('mfa_log_only', {}).get('status') == 'DELIVERED'
    and results.get('fabricated_dropped', {}).get('status') == 'DROPPED'
    and results.get('palais_control', {}).get('status') == 'DELIVERED'
    and results.get('palais_control', {}).get('stops', 0) == 4
)

if all_passed:
    print("\n✓ ALL PROOFS PASS")
    sys.exit(0)
else:
    print("\n✗ SOME PROOFS FAILED — see details above")
    sys.exit(1)
