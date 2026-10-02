#!/usr/bin/env python3
"""LOCAL-438: Live acceptance runs — MFA Unbound + Palais Lascaris control.

Gate mode: STORIED_MODE=true, STOP_EXISTENCE_GATE_MODE=log_only (default)
Reports: per-stop word counts, which stories were packed, gate results (informational).
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
os.environ.pop('PYTEST_CURRENT_TEST', None)
os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)

print("=" * 72)
print("  LOCAL-438 LIVE ACCEPTANCE")
print(f"  Gate mode: STORIED_MODE=true, STOP_EXISTENCE_GATE_MODE={os.environ.get('STOP_EXISTENCE_GATE_MODE', 'log_only')}")
print(f"  DISABLE_TOUR_CACHE=1")
print(f"  TOUR_LLM_MODEL={os.environ.get('TOUR_LLM_MODEL', '(default gpt-3.5-turbo)')}")
print(f"  TOUR_STORY_MODEL={os.environ.get('TOUR_STORY_MODEL', '(default gpt-4o)')}")
print("=" * 72)

from generate_tour_text import generate_tour_text as gen_tour
from story_gate import extract_story_sentences

results = {}


def run_tour(label, location, stops, output_path):
    """Run a single tour and report per-stop metrics."""
    print(f"\n{'─' * 72}")
    print(f"  {label}")
    print(f"  location: {location}")
    print(f"  stops:    {stops}")
    print(f"{'─' * 72}\n")

    start = time.time()
    tour_text, out_file, coords = gen_tour(
        location, "contained", output_path,
        total_stops=stops, persona=None,
        user_id=f"local438_{label.lower().replace(' ', '_')}",
        job_id=f"local438_{label.lower().replace(' ', '_')}",
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
    print(f"  Total chars: {len(tour_text)}")
    print(f"  Total words: {len(tour_text.split())}")
    print(f"  Stops delivered: {len(stop_blocks)}/{stops}")

    stop_data = []
    for i, block in enumerate(stop_blocks):
        header = re.match(r'Stop\s+\d+:\s*(.+?)(?:\n|$)', block)
        name = header.group(1).strip() if header else f'Stop {i+1}'
        words = len(block.split())
        story_sents = extract_story_sentences(block)
        stop_data.append({
            'name': name[:60],
            'word_count': words,
            'story_sentences': len(story_sents),
        })
        status = '✓' if len(story_sents) >= 3 else '✗'
        print(f"  {status} Stop {i+1}: {name[:55]:55s} words={words:4d} story_count={len(story_sents)}")

    results[label] = {
        'status': 'OK',
        'elapsed': elapsed,
        'total_words': len(tour_text.split()),
        'stops_delivered': len(stop_blocks),
        'stops_requested': stops,
        'stop_data': stop_data,
    }

    # Save output
    with open(output_path, 'w') as f:
        f.write(tour_text)
    print(f"\n  Saved: {output_path}")


# --- Run 1: MFA Unbound ---
run_tour(
    "MFA Unbound",
    "Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA",
    3,
    str(PROJECT_ROOT / "TOUR_LOCAL438_MFA_UNBOUND.txt"),
)

# --- Run 2: Palais Lascaris control ---
run_tour(
    "Palais Lascaris",
    "Palais Lascaris, Nice, France",
    4,
    str(PROJECT_ROOT / "TOUR_LOCAL438_PALAIS_CONTROL.txt"),
)

# --- Summary ---
print(f"\n{'=' * 72}")
print("  LOCAL-438 ACCEPTANCE SUMMARY")
print(f"{'=' * 72}")
for label, data in results.items():
    if data['status'] == 'OK':
        stops = data['stop_data']
        words = [s['word_count'] for s in stops]
        print(f"\n  {label}:")
        print(f"    Stops: {data['stops_delivered']}/{data['stops_requested']}")
        print(f"    Per-stop words: {words}")
        print(f"    Total words: {data['total_words']}")
        for s in stops:
            print(f"      {s['name'][:50]:50s} {s['word_count']:4d}w  story_count={s['story_sentences']}")
    else:
        print(f"\n  {label}: FAILED")

# Check Palais control dates
if 'Palais Lascaris' in results and results['Palais Lascaris']['status'] == 'OK':
    palais_path = PROJECT_ROOT / "TOUR_LOCAL438_PALAIS_CONTROL.txt"
    palais_text = palais_path.read_text()
    required_dates = ['1780', '1652', '1581', '1696']
    found_dates = [d for d in required_dates if d in palais_text]
    missing_dates = [d for d in required_dates if d not in palais_text]
    print(f"\n  Palais dates: {len(found_dates)}/{len(required_dates)} intact")
    if missing_dates:
        print(f"    *** MISSING: {missing_dates} ***")
    else:
        print(f"    ✓ All dates present: {found_dates}")

print(f"\n{'=' * 72}")
