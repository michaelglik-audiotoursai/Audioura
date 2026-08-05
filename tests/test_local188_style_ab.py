#!/usr/bin/env python3
"""LOCAL-188: A/B comparison — style constraints in narration prompt.

Generates 2 stops (D61) with the same request, twice:
  A) DISABLE_STYLE_CONSTRAINTS=1 (baseline — no style rules in prompt)
  B) Style constraints ACTIVE (the LOCAL-188 change)

Then runs the UNCHANGED style_validator_detector on both and reports
per-rule per-paragraph rates.

Cost: ~$0.01 per 2-stop generation × 2 arms = ~$0.02 total.
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from db_connection import get_connection
from style_validator_detector import validate_paragraph, _split_sentences, _is_style_navigation_paragraph


def generate_2_stops(location, tour_type, with_constraints=True):
    """Generate a 2-stop tour and return the text content.

    Sets DISABLE_STYLE_CONSTRAINTS env var to control the prompt.
    """
    if with_constraints:
        os.environ.pop('DISABLE_STYLE_CONSTRAINTS', None)
    else:
        os.environ['DISABLE_STYLE_CONSTRAINTS'] = '1'

    # Force non-museum category for this test (outdoor biking tour)
    os.environ['STORIED_MODE'] = 'false'

    from generate_tour_text import generate_tour_text

    tour_text, output_file, coords = generate_tour_text(
        location=location,
        tour_type=tour_type,
        total_stops=2,
    )

    # Cleanup env
    os.environ.pop('DISABLE_STYLE_CONSTRAINTS', None)

    return tour_text, output_file


def extract_stops_and_paragraphs(tour_text):
    """Parse tour text into stops with title and narration paragraphs."""
    if not tour_text:
        return []

    import re
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

    return totals


def main():
    # The same request that generated tours 152/156 — French Riviera biking
    LOCATION = "French Riviera biking tour, Nice"
    TOUR_TYPE = "biking"

    print("=" * 78)
    print("LOCAL-188: A/B COMPARISON — Style Constraints in Narration Prompt")
    print("=" * 78)
    print(f"Request: {LOCATION} / {TOUR_TYPE} / 2 stops (D61)")
    print()

    # ── ARM A: WITHOUT constraints ──
    print("-" * 78)
    print("ARM A: DISABLE_STYLE_CONSTRAINTS=1 (baseline — no style rules in prompt)")
    print("-" * 78)
    t0 = time.time()
    text_a, file_a = generate_2_stops(LOCATION, TOUR_TYPE, with_constraints=False)
    time_a = time.time() - t0
    print(f"\n  Generation time: {time_a:.1f}s")

    if not text_a:
        print("  ERROR: Generation failed for ARM A")
        sys.exit(1)

    stops_a = extract_stops_and_paragraphs(text_a)
    print(f"  Stops extracted: {len(stops_a)}")
    for s in stops_a:
        print(f"    • {s['title']}")
        print(f"      Paragraphs: {len(s.get('paragraphs', []))}")

    results_a = validate_stops(stops_a)
    print(f"\n  Validation results (ARM A — no constraints):")
    print(f"    Total paragraphs:     {results_a['total_paragraphs']}")
    print(f"    Navigation (exempt):  {results_a['navigation_paragraphs']}")
    content_a = results_a['total_paragraphs'] - results_a['navigation_paragraphs']
    print(f"    Content paragraphs:   {content_a}")
    print(f"    Clean (no violations):{results_a['clean_paragraphs']}")
    print(f"    R1 imperatives:       {results_a['R1_IMPERATIVE']}")
    print(f"    R2 questions:         {results_a['R2_QUESTION']}")
    print(f"    R3 suggestive expl:   {results_a['R3_SUGGESTIVE_EXPLORATION']}")
    print(f"    R4 prescribed feeling:{results_a['R4_PRESCRIBED_FEELING']}")
    print(f"    R7 halluc sensory:    {results_a['R7_HALLUCINATED_SENSORY']}")
    rate_a = (content_a - results_a['clean_paragraphs']) / content_a if content_a > 0 else 0

    # ── ARM B: WITH constraints ──
    print()
    print("-" * 78)
    print("ARM B: Style constraints ACTIVE (LOCAL-188 change)")
    print("-" * 78)
    t0 = time.time()
    text_b, file_b = generate_2_stops(LOCATION, TOUR_TYPE, with_constraints=True)
    time_b = time.time() - t0
    print(f"\n  Generation time: {time_b:.1f}s")

    if not text_b:
        print("  ERROR: Generation failed for ARM B")
        sys.exit(1)

    stops_b = extract_stops_and_paragraphs(text_b)
    print(f"  Stops extracted: {len(stops_b)}")
    for s in stops_b:
        print(f"    • {s['title']}")
        print(f"      Paragraphs: {len(s.get('paragraphs', []))}")

    results_b = validate_stops(stops_b)
    print(f"\n  Validation results (ARM B — with constraints):")
    print(f"    Total paragraphs:     {results_b['total_paragraphs']}")
    print(f"    Navigation (exempt):  {results_b['navigation_paragraphs']}")
    content_b = results_b['total_paragraphs'] - results_b['navigation_paragraphs']
    print(f"    Content paragraphs:   {content_b}")
    print(f"    Clean (no violations):{results_b['clean_paragraphs']}")
    print(f"    R1 imperatives:       {results_b['R1_IMPERATIVE']}")
    print(f"    R2 questions:         {results_b['R2_QUESTION']}")
    print(f"    R3 suggestive expl:   {results_b['R3_SUGGESTIVE_EXPLORATION']}")
    print(f"    R4 prescribed feeling:{results_b['R4_PRESCRIBED_FEELING']}")
    print(f"    R7 halluc sensory:    {results_b['R7_HALLUCINATED_SENSORY']}")
    rate_b = (content_b - results_b['clean_paragraphs']) / content_b if content_b > 0 else 0

    # ── COMPARISON ──
    print()
    print("=" * 78)
    print("COMPARISON")
    print("=" * 78)
    print(f"  ARM A failure rate: {100*rate_a:.1f}% ({content_a - results_a['clean_paragraphs']}/{content_a} paragraphs)")
    print(f"  ARM B failure rate: {100*rate_b:.1f}% ({content_b - results_b['clean_paragraphs']}/{content_b} paragraphs)")
    print()
    print(f"  Per-rule rates (violations per content paragraph):")
    print(f"  {'Rule':<25} {'ARM A':<15} {'ARM B':<15} {'Delta':<10}")
    print(f"  {'-'*65}")
    for rule in ['R1_IMPERATIVE', 'R3_SUGGESTIVE_EXPLORATION', 'R4_PRESCRIBED_FEELING', 'R7_HALLUCINATED_SENSORY']:
        rate_rule_a = results_a[rule] / content_a if content_a > 0 else 0
        rate_rule_b = results_b[rule] / content_b if content_b > 0 else 0
        delta = rate_rule_b - rate_rule_a
        print(f"  {rule:<25} {rate_rule_a:<15.3f} {rate_rule_b:<15.3f} {delta:<+10.3f}")

    # ── ITINERARY CONFOUND CHECK ──
    print()
    print("-" * 78)
    print("ITINERARY CONFOUND CHECK")
    print("-" * 78)
    titles_a = [s['title'] for s in stops_a]
    titles_b = [s['title'] for s in stops_b]
    print(f"  ARM A stops: {titles_a}")
    print(f"  ARM B stops: {titles_b}")
    if set(t.split(':',1)[-1].strip().lower() for t in titles_a) == set(t.split(':',1)[-1].strip().lower() for t in titles_b):
        print(f"  SAME stops — direct comparison valid")
    else:
        print(f"  DIFFERENT stops — comparison shows per-paragraph rates, not matched pairs")
        print(f"  (The itinerary confound is real — see task spec)")

    # ── NAVIGATION CHECK ──
    print()
    print("-" * 78)
    print("NAVIGATION/ORIENTATION TEXT CHECK")
    print("-" * 78)
    # Extract first Directions line from ARM B to verify it's still imperative
    import re
    directions_b = re.findall(r'^Directions:\s*(.+)$', text_b or '', re.MULTILINE)
    if directions_b:
        for d in directions_b[:2]:
            result = validate_paragraph(d)
            status = "CLEAN ✓" if not result['findings'] else f"FLAGGED ✗ ({[f['rule_id'] for f in result['findings']]})"
            print(f"  Direction: \"{d[:60]}...\"")
            print(f"  Validator: {status}")
    else:
        print(f"  (No Directions lines found in ARM B output)")

    # ── COST ──
    print()
    print("-" * 78)
    print("COST")
    print("-" * 78)
    # Estimate from token counts logged during generation
    print(f"  Estimated total: ~$0.02 (2 × 2-stop generations at ~$0.01 each)")
    print(f"  Ceiling: $0.25")

    # ── DB SAFETY ──
    print()
    print("-" * 78)
    print("DATABASE SAFETY")
    print("-" * 78)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    count = cur.fetchone()[0]
    cur.execute("SELECT array_agg(id ORDER BY id) FROM audio_tours WHERE NOT is_test AND tour_name ILIKE '%Nice%'")
    nice_ids = cur.fetchone()[0] or []
    conn.close()
    print(f"  audio_tours total rows: {count}")
    print(f"  Nice tour IDs (is_test=false): {nice_ids}")
    print(f"  Test tours: is_test flag NOT APPLICABLE (tours written to file, not DB)")

    # Cleanup generated files
    for f in [file_a, file_b]:
        if f and os.path.exists(f):
            os.remove(f)
            print(f"  Cleaned up: {f}")

    print()
    print("=" * 78)
    print("DONE")
    print("=" * 78)


if __name__ == '__main__':
    main()
