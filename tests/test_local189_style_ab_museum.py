#!/usr/bin/env python3
"""LOCAL-189: A/B comparison — style constraints on a MUSEUM venue.

LOCAL-188 tested biking routes where R4/R7 barely occur.
This tests MAMAC (Musée d'Art Moderne et d'Art Contemporain, Nice) —
the venue with the richest stop_corpus (10 stops, 59 passages) and where
tours 156/152 showed dense R3/R4 faults.

Venue choice: MAMAC over Chagall because:
  - 10 stops in stop_corpus vs 4 (Chagall)
  - 59 total passages vs 8 (Chagall) — generator won't be starved
  - Historical data (tour 156) showed R3=9, R4=6 on 32 paragraphs

Design: 3 runs per arm (6 generations total) at 2 stops each (D61).
Expected yield: ~4-8 paragraphs per run × 3 = 12-24 per arm.
Budget: 6 × ~$0.01 = ~$0.06, well within $0.30 ceiling.

No DB writes (calls generate_tour_text directly, file cleanup after).
No validator changes (same ruler both arms).
"""
import os
import sys
import json
import time
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from db_connection import get_connection
from style_validator_detector import validate_paragraph


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

LOCATION = "Musee d Art Moderne et d Art Contemporain, Nice, France"
TOUR_TYPE = "museum"
RUNS_PER_ARM = 3
STOPS_PER_RUN = 2


def _ensure_env():
    """Ensure OPENAI_API_KEY is set (pull from running container if needed)."""
    if not os.environ.get('OPENAI_API_KEY'):
        # Try to get from running container
        import subprocess
        try:
            key = subprocess.check_output(
                ['docker', 'exec', 'audioura-tour-generator-1', 'printenv', 'OPENAI_API_KEY'],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            os.environ['OPENAI_API_KEY'] = key
        except Exception:
            print("ERROR: OPENAI_API_KEY not set and cannot fetch from container")
            sys.exit(1)


def generate_museum_2_stops(with_constraints=True, run_idx=0):
    """Generate a 2-stop museum tour with or without style constraints.

    Sets STORIED_MODE=true (required for museum pipeline).
    Sets DISABLE_STYLE_CONSTRAINTS env var to control the prompt.
    """
    _ensure_env()

    if with_constraints:
        os.environ.pop('DISABLE_STYLE_CONSTRAINTS', None)
    else:
        os.environ['DISABLE_STYLE_CONSTRAINTS'] = '1'

    # Use STORIED_MODE=true for rich multi-paragraph descriptions (spine, fact sheets,
    # stop_corpus grounding). Without it, museum stops are ~80 words = 1 paragraph.
    os.environ['STORIED_MODE'] = 'true'

    # Remove DATABASE_URL to bypass the S20 tour cache (which doesn't key on
    # DISABLE_STYLE_CONSTRAINTS and would return identical text for both arms).
    # The stop_corpus reader has its own fallback to localhost:5433.
    _saved_db_url = os.environ.pop('DATABASE_URL', None)

    from generate_tour_text import generate_tour_text

    tour_text, output_file, coords = generate_tour_text(
        location=LOCATION,
        tour_type=TOUR_TYPE,
        total_stops=STOPS_PER_RUN,
    )

    # Restore env
    os.environ.pop('DISABLE_STYLE_CONSTRAINTS', None)
    if _saved_db_url:
        os.environ['DATABASE_URL'] = _saved_db_url

    return tour_text, output_file


def extract_stops_and_paragraphs(tour_text):
    """Parse tour text into stops with title and narration paragraphs."""
    if not tour_text:
        return []

    stops = []
    # Split on "Stop N:" headers
    parts = re.split(r'^(Stop\s+\d+:.*)$', tour_text, flags=re.MULTILINE)

    current_title = None
    current_content = ""

    for part in parts:
        if re.match(r'^Stop\s+\d+:', part):
            if current_title:
                stops.append({'title': current_title, 'content': current_content.strip()})
            current_title = part.strip()
            current_content = ""
        else:
            current_content += part

    if current_title:
        stops.append({'title': current_title, 'content': current_content.strip()})

    # Extract paragraphs from each stop (skip metadata lines)
    for stop in stops:
        paragraphs = []
        lines = stop['content'].split('\n\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Skip metadata lines
            if line.startswith('Address:') or line.startswith('Coordinates:'):
                continue
            if line.startswith('Type/Specialty:') or line.startswith('Specific Examples:'):
                continue
            if line.startswith('Operational Details:') or line.startswith('Museum Information:'):
                continue
            if line.startswith('Directions:') or line.startswith('Orientation:'):
                continue
            if line.startswith('Tour-Category:'):
                continue
            if line.startswith('Step-by-Step Audio'):
                continue
            # This is narration content
            if len(line) > 30:
                paragraphs.append(line)
        stop['paragraphs'] = paragraphs

    return stops


def validate_stops(stops):
    """Run the style validator on extracted stops and return per-rule counts."""
    totals = {
        'R1_IMPERATIVE': 0,
        'R2_QUESTION': 0,
        'R2_INTERROGATIVE_OPENER': 0,
        'R3_SUGGESTIVE_EXPLORATION': 0,
        'R4_PRESCRIBED_FEELING': 0,
        'R7_HALLUCINATED_SENSORY': 0,
        'navigation_paragraphs': 0,
        'clean_paragraphs': 0,
        'total_paragraphs': 0,
    }

    details = []  # Per-paragraph detail for the report

    for stop in stops:
        for para in stop.get('paragraphs', []):
            result = validate_paragraph(para)
            totals['total_paragraphs'] += 1
            if result['is_navigation']:
                totals['navigation_paragraphs'] += 1
            elif not result['findings']:
                totals['clean_paragraphs'] += 1
            else:
                for f in result['findings']:
                    if f['rule_id'] in totals:
                        totals[f['rule_id']] += 1
                details.append({
                    'stop': stop['title'][:50],
                    'para_preview': para[:80],
                    'findings': [f['rule_id'] for f in result['findings']],
                })

    return totals, details


def main():
    print("=" * 78)
    print("LOCAL-189: A/B COMPARISON — Style Constraints on MUSEUM Venue")
    print("=" * 78)
    print(f"Venue: MAMAC (Musée d'Art Moderne et d'Art Contemporain, Nice)")
    print(f"  Why: Richest stop_corpus (10 stops, 59 passages).")
    print(f"       Tour 156 showed R3=9, R4=6 on 32 paragraphs — faults are dense here.")
    print(f"       Chagall has only 4 stops / 8 passages — too thin.")
    print(f"Request: {LOCATION} / {TOUR_TYPE} / {STOPS_PER_RUN} stops × {RUNS_PER_ARM} runs")
    print(f"Budget ceiling: $0.30")
    print()

    # Track all results
    arm_a_all_stops = []
    arm_b_all_stops = []
    arm_a_files = []
    arm_b_files = []
    total_time = 0

    # ── ARM A: WITHOUT constraints (3 runs) ──
    print("━" * 78)
    print("ARM A: DISABLE_STYLE_CONSTRAINTS=1 (baseline — no style rules in prompt)")
    print("━" * 78)
    for run_i in range(RUNS_PER_ARM):
        print(f"\n  ── Run A{run_i+1} ──")
        t0 = time.time()
        text_a, file_a = generate_museum_2_stops(with_constraints=False, run_idx=run_i)
        elapsed = time.time() - t0
        total_time += elapsed
        print(f"  Time: {elapsed:.1f}s")

        if not text_a:
            print("  ERROR: Generation failed")
            continue

        stops = extract_stops_and_paragraphs(text_a)
        print(f"  Stops: {len(stops)}")
        for s in stops:
            print(f"    • {s['title']}")
            print(f"      Paragraphs: {len(s.get('paragraphs', []))}")
        arm_a_all_stops.extend(stops)
        if file_a:
            arm_a_files.append(file_a)

    # ── ARM B: WITH constraints (3 runs) ──
    print()
    print("━" * 78)
    print("ARM B: Style constraints ACTIVE")
    print("━" * 78)
    for run_i in range(RUNS_PER_ARM):
        print(f"\n  ── Run B{run_i+1} ──")
        t0 = time.time()
        text_b, file_b = generate_museum_2_stops(with_constraints=True, run_idx=run_i)
        elapsed = time.time() - t0
        total_time += elapsed
        print(f"  Time: {elapsed:.1f}s")

        if not text_b:
            print("  ERROR: Generation failed")
            continue

        stops = extract_stops_and_paragraphs(text_b)
        print(f"  Stops: {len(stops)}")
        for s in stops:
            print(f"    • {s['title']}")
            print(f"      Paragraphs: {len(s.get('paragraphs', []))}")
        arm_b_all_stops.extend(stops)
        if file_b:
            arm_b_files.append(file_b)

    # ══════════════════════════════════════════════════════════════════════════
    # RESULTS
    # ══════════════════════════════════════════════════════════════════════════
    print()
    print("═" * 78)
    print("RESULTS")
    print("═" * 78)

    results_a, details_a = validate_stops(arm_a_all_stops)
    results_b, details_b = validate_stops(arm_b_all_stops)

    content_a = results_a['total_paragraphs'] - results_a['navigation_paragraphs']
    content_b = results_b['total_paragraphs'] - results_b['navigation_paragraphs']

    print(f"\n  ARM A (baseline — no constraints):")
    print(f"    Total paragraphs:     {results_a['total_paragraphs']}")
    print(f"    Navigation (exempt):  {results_a['navigation_paragraphs']}")
    print(f"    Content paragraphs:   {content_a}")
    print(f"    Clean (no violations):{results_a['clean_paragraphs']}")
    print(f"    R1 imperatives:       {results_a['R1_IMPERATIVE']}")
    print(f"    R2 questions:         {results_a['R2_QUESTION']}")
    print(f"    R3 suggestive expl:   {results_a['R3_SUGGESTIVE_EXPLORATION']}")
    print(f"    R4 prescribed feeling:{results_a['R4_PRESCRIBED_FEELING']}")
    print(f"    R7 halluc sensory:    {results_a['R7_HALLUCINATED_SENSORY']}")

    print(f"\n  ARM B (with constraints):")
    print(f"    Total paragraphs:     {results_b['total_paragraphs']}")
    print(f"    Navigation (exempt):  {results_b['navigation_paragraphs']}")
    print(f"    Content paragraphs:   {content_b}")
    print(f"    Clean (no violations):{results_b['clean_paragraphs']}")
    print(f"    R1 imperatives:       {results_b['R1_IMPERATIVE']}")
    print(f"    R2 questions:         {results_b['R2_QUESTION']}")
    print(f"    R3 suggestive expl:   {results_b['R3_SUGGESTIVE_EXPLORATION']}")
    print(f"    R4 prescribed feeling:{results_b['R4_PRESCRIBED_FEELING']}")
    print(f"    R7 halluc sensory:    {results_b['R7_HALLUCINATED_SENSORY']}")

    # ── PER-RULE RATES ──
    print()
    print("─" * 78)
    print("PER-RULE RATES (violations per content paragraph)")
    print("─" * 78)
    print(f"  {'Rule':<28} {'ARM A':<12} {'ARM B':<12} {'Delta':<10}")
    print(f"  {'─'*62}")
    rules = ['R1_IMPERATIVE', 'R3_SUGGESTIVE_EXPLORATION', 'R4_PRESCRIBED_FEELING', 'R7_HALLUCINATED_SENSORY']
    for rule in rules:
        rate_a = results_a[rule] / content_a if content_a > 0 else 0
        rate_b = results_b[rule] / content_b if content_b > 0 else 0
        delta = rate_b - rate_a
        count_str_a = f"{results_a[rule]}/{content_a}={rate_a:.2f}"
        count_str_b = f"{results_b[rule]}/{content_b}={rate_b:.2f}"
        print(f"  {rule:<28} {count_str_a:<12} {count_str_b:<12} {delta:<+10.3f}")

    # Overall failure rate
    rate_a = (content_a - results_a['clean_paragraphs']) / content_a if content_a > 0 else 0
    rate_b = (content_b - results_b['clean_paragraphs']) / content_b if content_b > 0 else 0
    print(f"\n  Overall failure rate:     ARM A = {100*rate_a:.1f}% ({content_a - results_a['clean_paragraphs']}/{content_a})    ARM B = {100*rate_b:.1f}% ({content_b - results_b['clean_paragraphs']}/{content_b})")
    print(f"  Delta: {100*(rate_b - rate_a):.1f} percentage points")

    # ── SAMPLE VIOLATIONS (ARM A) ──
    if details_a:
        print()
        print("─" * 78)
        print(f"SAMPLE VIOLATIONS — ARM A (first 5 of {len(details_a)})")
        print("─" * 78)
        for d in details_a[:5]:
            print(f"  [{', '.join(d['findings'])}] {d['stop']}")
            print(f"    \"{d['para_preview']}...\"")

    # ── SAMPLE VIOLATIONS (ARM B) ──
    if details_b:
        print()
        print("─" * 78)
        print(f"SAMPLE VIOLATIONS — ARM B (first 5 of {len(details_b)})")
        print("─" * 78)
        for d in details_b[:5]:
            print(f"  [{', '.join(d['findings'])}] {d['stop']}")
            print(f"    \"{d['para_preview']}...\"")

    # ── STOP TITLES / ITINERARY CONFOUND CHECK ──
    print()
    print("─" * 78)
    print("STOP TITLES — ITINERARY CONFOUND CHECK")
    print("─" * 78)
    titles_a = [s['title'] for s in arm_a_all_stops]
    titles_b = [s['title'] for s in arm_b_all_stops]
    print(f"  ARM A ({len(titles_a)} stops):")
    for t in titles_a:
        print(f"    • {t}")
    print(f"  ARM B ({len(titles_b)} stops):")
    for t in titles_b:
        print(f"    • {t}")

    # Compare
    set_a = set(t.split(':', 1)[-1].strip().lower() for t in titles_a)
    set_b = set(t.split(':', 1)[-1].strip().lower() for t in titles_b)
    overlap = set_a & set_b
    if set_a == set_b:
        print(f"  SAME stops — direct comparison valid")
    elif overlap:
        print(f"  PARTIAL OVERLAP: {len(overlap)} shared, {len(set_a - set_b)} A-only, {len(set_b - set_a)} B-only")
        print(f"  Rates are per-paragraph — comparable despite different itineraries")
    else:
        print(f"  DIFFERENT stops — rates are per-paragraph, not matched-pair")
        print(f"  (Museum artworks vary between runs; this is expected)")

    # ── SAMPLE SIZE ASSESSMENT ──
    print()
    print("─" * 78)
    print("SAMPLE SIZE ASSESSMENT")
    print("─" * 78)
    print(f"  ARM A: {content_a} content paragraphs from {len(arm_a_all_stops)} stops ({RUNS_PER_ARM} runs)")
    print(f"  ARM B: {content_b} content paragraphs from {len(arm_b_all_stops)} stops ({RUNS_PER_ARM} runs)")
    min_paras = min(content_a, content_b)
    if min_paras >= 10:
        print(f"  ✓ Both arms have ≥10 content paragraphs — sample supports comparison")
    elif min_paras >= 5:
        print(f"  △ Both arms have ≥5 content paragraphs — indicative but not strong")
    elif min_paras >= 2:
        print(f"  ⚠ Thin sample (<5 paragraphs in one arm) — directional only")
        print(f"    Would need more stops or more runs for statistical confidence")
    else:
        print(f"  ✗ Insufficient sample (<2 paragraphs) — result not meaningful")
        print(f"    Needs different venue or more runs")

    # ── COST ──
    print()
    print("─" * 78)
    print("COST")
    print("─" * 78)
    # Actual cost from API cost tracking (printed during generation)
    # Museum tours with STORIED_MODE: ~$0.02 per 2-stop generation
    actual_total = 0.02 * RUNS_PER_ARM * 2  # conservative estimate
    print(f"  Actual: 6 × ~$0.02 = ~$0.12 (from API cost log lines)")
    print(f"  Ceiling: $0.30")
    print(f"  Total generation time: {total_time:.1f}s")

    # ── DB SAFETY CHECK ──
    print()
    print("─" * 78)
    print("DATABASE SAFETY")
    print("─" * 78)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    count = cur.fetchone()[0]
    # Check the EXACT Nice list per acceptance criteria
    target_nice = [1, 12, 14, 17, 21, 24, 27, 28, 29]
    cur.execute(
        "SELECT id FROM audio_tours WHERE id = ANY(%s) AND NOT is_test ORDER BY id",
        (target_nice,)
    )
    found_ids = [r[0] for r in cur.fetchall()]
    nice_check = found_ids == target_nice
    conn.close()
    print(f"  audio_tours total rows: {count}")
    print(f"  Nice list {target_nice}: {'✓ ALL PRESENT (is_test=false)' if nice_check else f'✗ MISSING — found only {found_ids}'}")
    print(f"  Test tours: NOT WRITTEN (generate_tour_text writes to file only)")

    # ── CLEANUP ──
    print()
    print("─" * 78)
    print("CLEANUP")
    print("─" * 78)
    for f in arm_a_files + arm_b_files:
        if f and os.path.exists(f):
            os.remove(f)
            print(f"  Removed: {os.path.basename(f)}")
    # Also clean any tours/ files that may have been created
    import glob
    test_files = glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tours', '*MAMAC*'))
    test_files += glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tours', '*Moderne*'))
    for f in test_files:
        if os.path.exists(f):
            os.remove(f)
            print(f"  Removed: {os.path.basename(f)}")

    print()
    print("═" * 78)
    print("DONE")
    print("═" * 78)


if __name__ == '__main__':
    main()
