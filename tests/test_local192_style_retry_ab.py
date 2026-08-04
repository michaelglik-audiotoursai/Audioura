#!/usr/bin/env python3
"""LOCAL-192: A/B comparison — style retry (validate + re-ask) vs no retry.

D63 established that prompt instruction alone does not fix R4
(prescribed feeling). LOCAL-192 adds a validate-and-regenerate step:
after generating each stop's narration, run the deterministic validator
on each paragraph, and for any paragraph with an error-severity violation,
re-request just that paragraph telling the model exactly which rule it broke.

This test measures whether the retry reduces violation rates.

Design (same as LOCAL-189 for comparability):
  - Venue: MAMAC (same as LOCAL-189)
  - 2 stops per run, 3 runs per arm = 6 generations total
  - ARM A: DISABLE_STYLE_RETRY=1 (retry off — same as LOCAL-189 constrained arm)
  - ARM B: Style retry ON (validate-and-regenerate active)
  - Both arms have style constraints in the prompt (LOCAL-188 active)
  - DATABASE_URL removed to bypass S20 tour cache (D63 trap)
  - STORIED_MODE=true (required for multi-paragraph descriptions)

Budget: ~$0.12 base + ~$0.02 retries = ~$0.14, ceiling $0.40.
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


def generate_museum_2_stops(retry_enabled=True, run_idx=0):
    """Generate a 2-stop museum tour with or without style retry.

    Both arms have style constraints in the prompt (LOCAL-188 active).
    The variable under test is DISABLE_STYLE_RETRY.
    """
    _ensure_env()

    # Style constraints always ON (both arms have the prompt rules)
    os.environ.pop('DISABLE_STYLE_CONSTRAINTS', None)

    # The A/B variable: retry on or off
    if retry_enabled:
        os.environ.pop('DISABLE_STYLE_RETRY', None)
    else:
        os.environ['DISABLE_STYLE_RETRY'] = '1'

    # STORIED_MODE=true for multi-paragraph museum descriptions
    os.environ['STORIED_MODE'] = 'true'

    # Remove DATABASE_URL to bypass the S20 tour cache (D63 — cache key
    # doesn't include DISABLE_STYLE_RETRY; would return identical text).
    _saved_db_url = os.environ.pop('DATABASE_URL', None)

    # Force reimport to pick up env var changes
    if 'generate_tour_text' in sys.modules:
        del sys.modules['generate_tour_text']

    from generate_tour_text import generate_tour_text

    tour_text, output_file, coords = generate_tour_text(
        location=LOCATION,
        tour_type=TOUR_TYPE,
        total_stops=STOPS_PER_RUN,
    )

    # Restore env
    os.environ.pop('DISABLE_STYLE_RETRY', None)
    if _saved_db_url:
        os.environ['DATABASE_URL'] = _saved_db_url

    return tour_text, output_file


def extract_stops_and_paragraphs(tour_text):
    """Parse tour text into stops with title and narration paragraphs."""
    if not tour_text:
        return []

    stops = []
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

    for stop in stops:
        paragraphs = []
        lines = stop['content'].split('\n\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
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
            if len(line) > 30:
                paragraphs.append(line)
        stop['paragraphs'] = paragraphs

    return stops


def validate_stops(stops):
    """Run the style validator on extracted stops and return per-rule counts + details."""
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

    details = []

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
                    'severities': [f['severity'] for f in result['findings']],
                })

    return totals, details


def main():
    print("=" * 78)
    print("LOCAL-192: A/B COMPARISON — Style Retry (validate + re-ask) vs No Retry")
    print("=" * 78)
    print(f"Venue: MAMAC (Musée d'Art Moderne et d'Art Contemporain, Nice)")
    print(f"  Same venue as LOCAL-189 for comparability.")
    print(f"  Both arms have style constraints in prompt (LOCAL-188 active).")
    print(f"  Variable under test: DISABLE_STYLE_RETRY")
    print(f"Request: {LOCATION} / {TOUR_TYPE} / {STOPS_PER_RUN} stops × {RUNS_PER_ARM} runs")
    print(f"Budget ceiling: $0.40")
    print()

    arm_a_all_stops = []
    arm_b_all_stops = []
    arm_a_files = []
    arm_b_files = []
    total_time = 0

    # ── ARM A: Retry DISABLED (3 runs) ──
    print("━" * 78)
    print("ARM A: DISABLE_STYLE_RETRY=1 (no retry — same output as LOCAL-189 ARM B)")
    print("━" * 78)
    for run_i in range(RUNS_PER_ARM):
        print(f"\n  ── Run A{run_i+1} ──")
        t0 = time.time()
        text_a, file_a = generate_museum_2_stops(retry_enabled=False, run_idx=run_i)
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

    # ── ARM B: Retry ENABLED (3 runs) ──
    print()
    print("━" * 78)
    print("ARM B: Style retry ACTIVE (validate + re-ask failing paragraphs)")
    print("━" * 78)
    for run_i in range(RUNS_PER_ARM):
        print(f"\n  ── Run B{run_i+1} ──")
        t0 = time.time()
        text_b, file_b = generate_museum_2_stops(retry_enabled=True, run_idx=run_i)
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

    print(f"\n  ARM A (retry OFF — prompt constraints only):")
    print(f"    Total paragraphs:     {results_a['total_paragraphs']}")
    print(f"    Navigation (exempt):  {results_a['navigation_paragraphs']}")
    print(f"    Content paragraphs:   {content_a}")
    print(f"    Clean (no violations):{results_a['clean_paragraphs']}")
    print(f"    R1 imperatives:       {results_a['R1_IMPERATIVE']}")
    print(f"    R3 suggestive expl:   {results_a['R3_SUGGESTIVE_EXPLORATION']}")
    print(f"    R4 prescribed feeling:{results_a['R4_PRESCRIBED_FEELING']}")
    print(f"    R7 halluc sensory:    {results_a['R7_HALLUCINATED_SENSORY']}")

    print(f"\n  ARM B (retry ON — validate + re-ask):")
    print(f"    Total paragraphs:     {results_b['total_paragraphs']}")
    print(f"    Navigation (exempt):  {results_b['navigation_paragraphs']}")
    print(f"    Content paragraphs:   {content_b}")
    print(f"    Clean (no violations):{results_b['clean_paragraphs']}")
    print(f"    R1 imperatives:       {results_b['R1_IMPERATIVE']}")
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

    # Overall failure rate (error-severity only, to match the retry trigger)
    failed_a = content_a - results_a['clean_paragraphs']
    failed_b = content_b - results_b['clean_paragraphs']
    rate_a = failed_a / content_a if content_a > 0 else 0
    rate_b = failed_b / content_b if content_b > 0 else 0
    print(f"\n  Overall failure rate:     ARM A = {100*rate_a:.1f}% ({failed_a}/{content_a})    ARM B = {100*rate_b:.1f}% ({failed_b}/{content_b})")
    print(f"  Delta: {100*(rate_b - rate_a):.1f} percentage points")

    # ── ERROR-SEVERITY ONLY RATE (what the retry actually targets) ──
    print()
    print("─" * 78)
    print("ERROR-SEVERITY VIOLATIONS ONLY (what retry targets — excludes R7 warnings)")
    print("─" * 78)
    error_a = results_a['R1_IMPERATIVE'] + results_a['R3_SUGGESTIVE_EXPLORATION'] + results_a['R4_PRESCRIBED_FEELING']
    error_b = results_b['R1_IMPERATIVE'] + results_b['R3_SUGGESTIVE_EXPLORATION'] + results_b['R4_PRESCRIBED_FEELING']
    error_rate_a = error_a / content_a if content_a > 0 else 0
    error_rate_b = error_b / content_b if content_b > 0 else 0
    print(f"  ARM A: {error_a} error-severity violations in {content_a} paragraphs ({100*error_rate_a:.1f}%)")
    print(f"  ARM B: {error_b} error-severity violations in {content_b} paragraphs ({100*error_rate_b:.1f}%)")
    print(f"  Delta: {100*(error_rate_b - error_rate_a):.1f} percentage points")

    # ── SAMPLE VIOLATIONS (both arms) ──
    if details_a:
        print()
        print("─" * 78)
        print(f"SAMPLE VIOLATIONS — ARM A (first 5 of {len(details_a)})")
        print("─" * 78)
        for d in details_a[:5]:
            print(f"  [{', '.join(d['findings'])}] {d['stop']}")
            print(f"    \"{d['para_preview']}...\"")

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

    set_a = set(t.split(':', 1)[-1].strip().lower() for t in titles_a)
    set_b = set(t.split(':', 1)[-1].strip().lower() for t in titles_b)
    if set_a == set_b:
        print(f"  SAME stops — direct comparison valid")
    elif set_a & set_b:
        print(f"  PARTIAL OVERLAP: {len(set_a & set_b)} shared — rates are per-paragraph, comparable")
    else:
        print(f"  DIFFERENT stops — rates are per-paragraph, not matched-pair")

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
    else:
        print(f"  ⚠ Thin sample — directional only")

    # ── COST ──
    print()
    print("─" * 78)
    print("COST")
    print("─" * 78)
    # Base: 6 × ~$0.02 = ~$0.12 (from LOCAL-189 actuals)
    # Retry overhead: logged during generation (ARM B runs)
    print(f"  Base generation cost (both arms): 6 × ~$0.02 = ~$0.12")
    print(f"  Retry overhead: see [LOCAL-192] log lines in ARM B runs above")
    print(f"  Ceiling: $0.40")
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
    target_nice = [1, 12, 14, 17, 21, 24, 27, 28, 29]
    cur.execute(
        "SELECT id FROM audio_tours WHERE id = ANY(%s) AND NOT is_test ORDER BY id",
        (target_nice,)
    )
    found_ids = [r[0] for r in cur.fetchall()]
    nice_check = found_ids == target_nice
    # Check test tours
    cur.execute("SELECT COUNT(*) FROM audio_tours WHERE is_test = true")
    test_count = cur.fetchone()[0]
    conn.close()
    print(f"  audio_tours total rows: {count}")
    print(f"  Nice list {target_nice}: {'✓ ALL PRESENT (is_test=false)' if nice_check else f'✗ MISSING — found only {found_ids}'}")
    print(f"  Test tours (is_test=true): {test_count}")
    print(f"  NOTE: generate_tour_text writes to file only — no DB rows created by this test")

    # ── CLEANUP ──
    print()
    print("─" * 78)
    print("CLEANUP")
    print("─" * 78)
    for f in arm_a_files + arm_b_files:
        if f and os.path.exists(f):
            os.remove(f)
            print(f"  Removed: {os.path.basename(f)}")
    import glob as _glob
    test_files = _glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tours', '*MAMAC*'))
    test_files += _glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tours', '*Moderne*'))
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
