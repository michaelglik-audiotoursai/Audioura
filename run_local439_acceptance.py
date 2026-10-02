#!/usr/bin/env python3
"""LOCAL-439: Live acceptance runs — MFA Unbound + Palais Lascaris control.

Gate mode: STORIED_MODE=true, L421_GATE_BLOCKS=false (informational)
Reports: per-stop story-unit counts (not sentence tallies), classification cost,
         Palais control (4/4 stops, dates 1780/1652/1581/1696).
"""
import json
import os
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# --- Environment ---
_env_path = PROJECT_ROOT / '.env'
if not _env_path.exists():
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
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['L421_GATE_BLOCKS'] = 'false'
os.environ.pop('PYTEST_CURRENT_TEST', None)
os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)

print("=" * 72)
print("  LOCAL-439 LIVE ACCEPTANCE")
print(f"  Gate mode: STORIED_MODE=true, L421_GATE_BLOCKS=false (informational)")
print(f"  DISABLE_TOUR_CACHE=1")
print(f"  TOUR_LLM_MODEL={os.environ.get('TOUR_LLM_MODEL', '(default gpt-3.5-turbo)')}")
print(f"  TOUR_STORY_MODEL={os.environ.get('TOUR_STORY_MODEL', '(default gpt-4o)')}")
print("=" * 72)

from generate_tour_text import generate_tour_text as gen_tour
from story_gate import (
    verify_stop_story,
    classify_story_unit,
    extract_candidate_story_units,
    get_classification_cost,
    reset_classification_cost,
)

results = {}


def run_tour(label, location, stops, output_path):
    """Run a single tour and report per-stop story-unit metrics."""
    print(f"\n{'─' * 72}")
    print(f"  {label}")
    print(f"  location: {location}")
    print(f"  stops:    {stops}")
    print(f"{'─' * 72}\n")

    reset_classification_cost()
    start = time.time()
    tour_text, out_file, coords = gen_tour(
        location, "contained", output_path,
        total_stops=stops, persona=None,
        user_id=f"local439_{label.lower().replace(' ', '_')}",
        job_id=f"local439_{label.lower().replace(' ', '_')}",
    )
    elapsed = time.time() - start

    if not tour_text:
        print(f"\n  *** FAILED: no text generated for {label} ***")
        results[label] = {'status': 'FAILED', 'elapsed': elapsed}
        return

    # Parse stops
    stop_blocks = re.split(r'(?=^Stop\s+\d+:)', tour_text, flags=re.MULTILINE)
    stop_blocks = [b for b in stop_blocks if b.strip() and re.match(r'Stop\s+\d+:', b.strip())]

    print(f"\n  {'=' * 60}")
    print(f"  {label} RESULTS ({elapsed:.1f}s)")
    print(f"  {'=' * 60}")
    print(f"  Total stops: {len(stop_blocks)}")
    print(f"  Total words: {len(tour_text.split())}")

    # Per-stop story-unit analysis
    stop_results = []
    for block in stop_blocks:
        header_match = re.match(r'Stop\s+\d+:\s*(.+?)(?:\s+by\s+|\s*,\s*\d|\n)', block)
        stop_name = header_match.group(1).strip() if header_match else 'Unknown'

        # Extract description
        desc_match = re.search(
            r'(?:Orientation:.*?\n\n)(.+?)(?:\n\s*Directions:|\n\s*Sources:|\n\s*Closing:|\Z)',
            block, re.DOTALL
        )
        description = desc_match.group(1).strip() if desc_match else block

        word_count = len(description.split())

        # Classify with the new story-unit gate
        gate_result = verify_stop_story(description=description, framing_case='exhibition')

        # Extract dates from stop
        dates = re.findall(r'\b(1[0-9]{3})\b', block)

        stop_results.append({
            'name': stop_name,
            'word_count': word_count,
            'story_units': gate_result['story_unit_count'],
            'passed': gate_result['passed'],
            'dates': dates,
            'interest_scores': gate_result.get('interest_scores', []),
        })

        status = "✓" if gate_result['passed'] else "✗"
        print(f"  {status} {stop_name}: story_units={gate_result['story_unit_count']}, "
              f"words={word_count}")
        if gate_result.get('interest_scores'):
            for iscr in gate_result['interest_scores']:
                print(f"      interest: emotional={iscr['emotional_content']}, "
                      f"new_info={iscr['new_information']}, "
                      f"deduction={iscr['deduction']}, "
                      f"total={iscr['interest_score']}")
        if not gate_result['passed']:
            for f in gate_result['failures']:
                print(f"      → {f}")

    cost = get_classification_cost()
    print(f"\n  Classification cost: ${cost['total_cost_usd']:.6f} "
          f"(input={cost['input_tokens']}tok, output={cost['output_tokens']}tok)")

    passed_count = sum(1 for r in stop_results if r['passed'])
    print(f"  Story gate: {passed_count}/{len(stop_results)} stops passed")

    results[label] = {
        'status': 'OK',
        'elapsed': elapsed,
        'stops': stop_results,
        'classification_cost': cost,
        'gate_passed': f"{passed_count}/{len(stop_results)}",
    }

    return tour_text


# --- MFA Unbound ---
output_path = str(PROJECT_ROOT / "tours" / "local439_mfa_unbound")
os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
mfa_text = run_tour(
    "MFA Unbound",
    "Museum of Fine Arts, Boston - Unbound: Contemporary Art After Frida Kahlo",
    3,
    output_path,
)

# --- Palais Lascaris Control ---
output_path = str(PROJECT_ROOT / "tours" / "local439_palais_control")
palais_text = run_tour(
    "Palais Lascaris",
    "Palais Lascaris, Nice, France",
    4,
    output_path,
)

# --- Control check: Palais dates ---
print(f"\n{'═' * 72}")
print("  PALAIS CONTROL (D302/D326)")
print(f"{'═' * 72}")
if 'Palais Lascaris' in results and results['Palais Lascaris']['status'] == 'OK':
    palais_stops = results['Palais Lascaris']['stops']
    print(f"  Stops: {len(palais_stops)}/4")
    all_dates = []
    for s in palais_stops:
        all_dates.extend(s['dates'])
    expected_dates = {'1780', '1652', '1581', '1696'}
    found_dates = set(all_dates)
    present = expected_dates & found_dates
    missing = expected_dates - found_dates
    print(f"  Expected dates: {sorted(expected_dates)}")
    print(f"  Found dates: {sorted(found_dates)}")
    print(f"  Present: {sorted(present)} ({len(present)}/4)")
    if missing:
        print(f"  Missing: {sorted(missing)}")
    else:
        print(f"  ALL DATES INTACT ✓")
else:
    print("  Palais run FAILED — cannot verify control")

# --- Summary ---
print(f"\n{'═' * 72}")
print("  SUMMARY")
print(f"{'═' * 72}")
for label, data in results.items():
    if data['status'] == 'OK':
        print(f"  {label}: {data['gate_passed']} stops, "
              f"cost=${data['classification_cost']['total_cost_usd']:.6f}, "
              f"elapsed={data['elapsed']:.1f}s")
    else:
        print(f"  {label}: {data['status']}")

print(f"\n  Gate mode: informational (L421_GATE_BLOCKS=false)")
print("  Done.")
