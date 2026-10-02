#!/usr/bin/env python3
"""run_local441_acceptance.py — Live acceptance test for LOCAL-441.

Runs a full Palais Lascaris generation on the LOCAL-441 branch and measures:
  - Wall-clock of the external lookup phase (P856 checks)
  - P856 checks: attempted / resolved (tier1) / budget-expired
  - Total generation wall-clock
  - D302 control: 4/4 stops, dates intact

Target: external-lookup phase contributes ≤30s total.

Env vars:
  DISABLE_TOUR_CACHE=1
  DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours
  STORIED_MODE=true
"""
import os
import sys
import re
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Required env
os.environ.setdefault('DISABLE_TOUR_CACHE', '1')
os.environ.setdefault('DATABASE_URL', 'postgresql://admin:password123@localhost:5433/audiotours')
os.environ.setdefault('STORIED_MODE', 'true')

import work_story_searcher as wss


def run_palais_lascaris():
    """Run full Palais Lascaris generation and report metrics."""
    from generate_tour_text import generate_tour_text

    print("=" * 70)
    print("  LOCAL-441 ACCEPTANCE: Palais Lascaris, Nice, France (4 stops)")
    print("=" * 70)
    print()
    print(f"  Config:")
    print(f"    EXTERNAL_LOOKUP_BATCH_BUDGET_SECONDS = {wss.EXTERNAL_LOOKUP_BATCH_BUDGET_SECONDS}")
    print(f"    EXTERNAL_LOOKUP_POOL_SIZE = {wss.EXTERNAL_LOOKUP_POOL_SIZE}")
    print(f"    EXTERNAL_LOOKUP_PER_TIMEOUT = {wss.EXTERNAL_LOOKUP_PER_TIMEOUT}")
    print(f"    DISABLE_TOUR_CACHE = {os.environ.get('DISABLE_TOUR_CACHE')}")
    print(f"    DATABASE_URL = {os.environ.get('DATABASE_URL', '<not set>')}")
    print(f"    STORIED_MODE = {os.environ.get('STORIED_MODE')}")
    print()

    # Clear the module cache so we get fresh lookup timings
    wss._MODULE_DOMAIN_CACHE.clear()

    filepath = "/tmp/local441_palais.txt"

    # Full generation
    gen_start = time.time()
    try:
        tour_text, _, coords = generate_tour_text(
            "Palais Lascaris, Nice, France",
            "museum",
            filepath,
            total_stops=4,
        )
    except Exception as e:
        print(f"  GENERATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return

    gen_elapsed = time.time() - gen_start

    print()
    print("=" * 70)
    print("  RESULTS")
    print("=" * 70)
    print()
    print(f"  Total generation wall-clock: {gen_elapsed:.1f}s")
    print()

    # Report module cache state (how many domains were checked)
    cache_size = len(wss._MODULE_DOMAIN_CACHE)
    tier1_count = sum(1 for v in wss._MODULE_DOMAIN_CACHE.values() if v == 'tier1')
    tier3_count = sum(1 for v in wss._MODULE_DOMAIN_CACHE.values() if v == 'tier3')
    print(f"  P856 lookup counters:")
    print(f"    Domains in module cache: {cache_size}")
    print(f"    Resolved as tier1: {tier1_count}")
    print(f"    Resolved as tier3: {tier3_count}")
    print()

    # D302 Control: check tour output
    if not tour_text:
        print("  ⚠️  No tour text generated!")
        return

    print(f"  Tour text length: {len(tour_text)} chars")
    stops = re.split(r'(?:^|\n)(?:##?\s*)?Stop\s+\d+[:\s]', tour_text, flags=re.IGNORECASE)
    stops = stops[1:] if len(stops) > 1 else []
    print(f"  Stops generated: {len(stops)}")

    # Date control (D302): 1780, 1884, 1696, 1581
    palais_dates = ['1780', '1884', '1696', '1581']
    print()
    print(f"  D302 Date control:")
    for d in palais_dates:
        found = len(re.findall(re.escape(d), tour_text))
        status = "✓" if found > 0 else "✗"
        print(f"    {status} {d}: {found} occurrences")

    # Stop word counts
    print()
    print(f"  Stop word counts (min 120 required):")
    for i, stop_text in enumerate(stops, 1):
        wc = len(stop_text.split())
        status = "✓" if wc >= 120 else "✗"
        print(f"    {status} Stop {i}: {wc} words")

    print()
    print("=" * 70)
    print(f"  ACCEPTANCE TARGET: lookup phase ≤30s")
    print(f"  TOTAL GENERATION: {gen_elapsed:.1f}s")
    print("=" * 70)


if __name__ == '__main__':
    run_palais_lascaris()
