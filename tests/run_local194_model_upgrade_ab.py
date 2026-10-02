#!/usr/bin/env python3
"""LOCAL-194: A/B measurement — gpt-3.5-turbo vs gpt-4o-mini on MAMAC.

The ONLY variable is TOUR_LLM_MODEL. Everything else (prompt, pipeline,
stop_corpus, style constraints) is identical between arms.

Arms:
  A: TOUR_LLM_MODEL=gpt-3.5-turbo (today's behaviour)
  B: TOUR_LLM_MODEL=gpt-4o-mini

Venue: MAMAC (Musée d'Art Moderne et d'Art Contemporain, Nice, France)
  - Same as LOCAL-189: richest stop_corpus, historical R3/R4 faults.

Design: 3 runs × 2 stops × 2 arms = 12 generations total.
Ceiling: $0.60.

Measures per arm:
  1. Style validator (R1/R3/R4/R7 per-rule rates + paragraph failure rate)
  2. Anchor rate (stop_corpus detector, unmodified)
  3. Cost per tour (token counts × per-model rate)
  4. Latency per tour (wall clock)

No DB writes. generate_tour_text writes to file only.
No container rebuilds (D48). No detector modifications (D55).
"""
import os
import sys
import json
import time
import re
import importlib
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from db_connection import get_connection
from style_validator_detector import validate_paragraph
from stop_anchor_detector_v2 import (
    parse_tour_stops,
    build_corpus_anchors,
    build_sibling_corpus_texts,
    classify_paragraph,
    is_navigation_paragraph,
    extract_entities,
    _normalize_for_match,
)
from stop_anchor_detector_v2_with_stop_corpus import (
    get_stop_corpus_passages,
    get_stop_corpus_venue_name,
    enrich_venue_corpus_with_stop_passages,
    get_venue_corpus_for_tour,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

LOCATION = "Musee d Art Moderne et d Art Contemporain, Nice, France"
TOUR_TYPE = "museum"
RUNS_PER_ARM = 3
STOPS_PER_RUN = 2

# Pricing per 1K tokens (input + output combined estimate)
# Source: https://openai.com/api/pricing (as of 2025-07)
# gpt-3.5-turbo: $0.002/1K (blended, documented in generate_tour_text.py)
# gpt-4o-mini: input $0.15/1M = $0.00015/1K, output $0.60/1M = $0.0006/1K
#   blended estimate at ~30% output: $0.00015*0.7 + $0.0006*0.3 ≈ $0.000285/1K
PRICING = {
    'gpt-3.5-turbo': 0.002,       # $/1K tokens (legacy blended rate used in codebase)
    'gpt-4o-mini': 0.000285,      # $/1K tokens (blended input/output)
    'gpt-4.1-mini': 0.000285,     # same tier as 4o-mini (fallback)
    'gpt-4o': 0.0075,             # $/1K tokens (blended)
}


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


def generate_tour(model_name: str, run_idx: int):
    """Generate a 2-stop MAMAC tour with the specified model.

    Returns (tour_text, output_file, total_tokens, elapsed_seconds, actual_model).
    """
    _ensure_env()

    # Set model
    os.environ['TOUR_LLM_MODEL'] = model_name
    os.environ['STORIED_MODE'] = 'true'

    # Bypass S20 cache (key doesn't include TOUR_LLM_MODEL)
    _saved_db_url = os.environ.pop('DATABASE_URL', None)

    # Force reimport to pick up env changes
    if 'generate_tour_text' in sys.modules:
        del sys.modules['generate_tour_text']

    from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST

    t0 = time.time()
    try:
        tour_text, output_file, coords = generate_tour_text(
            location=LOCATION,
            tour_type=TOUR_TYPE,
            total_stops=STOPS_PER_RUN,
        )
    except Exception as e:
        print(f"  GENERATION ERROR ({model_name}, run {run_idx}): {e}")
        tour_text = None
        output_file = None
    elapsed = time.time() - t0

    # Read cost info
    from generate_tour_text import _LAST_GENERATION_COST as cost_info
    total_tokens = cost_info.get('total_tokens', 0)

    # Restore env
    if _saved_db_url:
        os.environ['DATABASE_URL'] = _saved_db_url
    os.environ.pop('TOUR_LLM_MODEL', None)

    return tour_text, output_file, total_tokens, elapsed, model_name


def extract_stops_and_paragraphs(tour_text):
    """Parse tour text into stops [{title, paragraphs}]."""
    if not tour_text:
        return []
    stops = parse_tour_stops(tour_text)
    return stops


def run_style_validator(tour_text) -> Dict:
    """Run style validator on generated text. Returns rule counts."""
    stops = extract_stops_and_paragraphs(tour_text)
    totals = {
        'R1_IMPERATIVE': 0,
        'R3_SUGGESTIVE_EXPLORATION': 0,
        'R4_PRESCRIBED_FEELING': 0,
        'R7_HALLUCINATED_SENSORY': 0,
        'navigation_paragraphs': 0,
        'clean_paragraphs': 0,
        'total_content_paragraphs': 0,
        'failing_paragraphs': 0,
    }
    for stop in stops:
        for para in stop['paragraphs']:
            result = validate_paragraph(para)
            if result['is_navigation']:
                totals['navigation_paragraphs'] += 1
                continue
            totals['total_content_paragraphs'] += 1
            if not result['findings']:
                totals['clean_paragraphs'] += 1
            else:
                totals['failing_paragraphs'] += 1
                for f in result['findings']:
                    rule = f['rule_id']
                    if rule in totals:
                        totals[rule] += 1
    return totals


def run_anchor_detector(tour_text) -> Dict:
    """Run stop_corpus anchor detector on generated text. Returns classification counts."""
    stops = extract_stops_and_paragraphs(tour_text)
    if not stops:
        return {'ANCHORED': 0, 'NO_ANCHOR': 0, 'UNLINKED_ENTITY': 0, 'NAVIGATION': 0, 'total': 0}

    conn = get_connection()
    try:
        # Get venue_corpus from DB (same as the detector would)
        # Use a fake tour_id=0; build from tour_name
        tour_name = f"MAMAC, Nice - Museum Tour"
        venue_corpus = None

        # Try to get venue_corpus
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT vc.* FROM venue_corpus vc
            WHERE vc.venue_name ILIKE %s OR vc.venue_name ILIKE %s
            LIMIT 1
        """, ('%MAMAC%', '%Moderne%Contemporain%'))
        vc_row = cur.fetchone()
        if vc_row:
            venue_corpus = vc_row
            # Parse JSON fields
            for jf in ('story_elements_json', 'canonical_titles_json', 'pages_json'):
                val = venue_corpus.get(jf)
                if isinstance(val, str):
                    venue_corpus[jf] = json.loads(val)

        # Get stop_corpus venue name
        sc_venue_name = None
        cur.execute("SELECT DISTINCT venue_name FROM stop_corpus WHERE venue_name ILIKE %s", ('%MAMAC%',))
        row = cur.fetchone()
        if row:
            sc_venue_name = row['venue_name']
        if not sc_venue_name:
            cur.execute("SELECT DISTINCT venue_name FROM stop_corpus WHERE venue_name ILIKE %s", ('%Moderne%Contemporain%',))
            row = cur.fetchone()
            if row:
                sc_venue_name = row['venue_name']

        # Analyze each stop
        all_stop_titles = [s['title'] for s in stops]
        enriched_per_stop = {}
        for title in all_stop_titles:
            if sc_venue_name:
                passages = get_stop_corpus_passages(sc_venue_name, title, conn)
            else:
                passages = None
            if passages:
                enriched_per_stop[title] = enrich_venue_corpus_with_stop_passages(
                    venue_corpus, title, passages
                )
            else:
                enriched_per_stop[title] = venue_corpus

        # Build sibling corpus texts
        sibling_corpus_texts = {}
        for title in all_stop_titles:
            vc = enriched_per_stop[title]
            if vc:
                anchors = build_corpus_anchors(vc, title, tour_name)
                specific_text = ' '.join(anchors['facts'])
                for p in anchors['people']:
                    specific_text += ' ' + p
                for d in anchors['dates']:
                    specific_text += ' ' + d
                for t in anchors['titles']:
                    specific_text += ' ' + t
                sibling_corpus_texts[title] = _normalize_for_match(specific_text)
            else:
                sibling_corpus_texts[title] = ''

        totals = {'ANCHORED': 0, 'NO_ANCHOR': 0, 'UNLINKED_ENTITY': 0, 'NAVIGATION': 0, 'total': 0}
        for stop in stops:
            vc = enriched_per_stop.get(stop['title'], venue_corpus)
            corpus_anchors = build_corpus_anchors(
                vc, stop['title'], tour_name
            ) if vc else {
                'people': set(), 'dates': set(), 'titles': set(),
                'facts': [], 'all_corpus_people': set(), 'all_corpus_text': '',
            }
            for para in stop['paragraphs']:
                result = classify_paragraph(
                    para, corpus_anchors, stop['title'], tour_name,
                    sibling_corpus_texts=sibling_corpus_texts
                )
                totals[result['classification']] += 1
                totals['total'] += 1

        return totals
    finally:
        conn.close()


def main():
    """Run the A/B measurement."""
    _ensure_env()

    # Determine model B: try gpt-4o-mini first
    model_a = 'gpt-3.5-turbo'
    model_b = 'gpt-4o-mini'  # Will report error verbatim if unavailable

    results = {'A': [], 'B': []}

    print(f"\n{'='*70}")
    print(f"LOCAL-194: Model Upgrade A/B Measurement")
    print(f"  ARM A: {model_a}")
    print(f"  ARM B: {model_b}")
    print(f"  Venue: MAMAC, Nice")
    print(f"  Runs: {RUNS_PER_ARM} per arm × {STOPS_PER_RUN} stops")
    print(f"{'='*70}\n")

    for arm_label, model in [('A', model_a), ('B', model_b)]:
        print(f"\n--- ARM {arm_label}: {model} ---")
        for run_idx in range(RUNS_PER_ARM):
            print(f"\n  Run {arm_label}{run_idx+1}...")
            tour_text, output_file, total_tokens, elapsed, actual_model = generate_tour(model, run_idx)

            if not tour_text:
                print(f"  FAILED — no tour text generated")
                results[arm_label].append({
                    'run': run_idx + 1,
                    'model': model,
                    'error': 'generation_failed',
                    'elapsed': elapsed,
                })
                continue

            # Extract stop titles
            stops = extract_stops_and_paragraphs(tour_text)
            stop_titles = [s['title'] for s in stops]

            # Run detectors
            style_result = run_style_validator(tour_text)
            anchor_result = run_anchor_detector(tour_text)

            # Compute cost
            price_per_1k = PRICING.get(model, PRICING['gpt-3.5-turbo'])
            cost = total_tokens / 1000 * price_per_1k

            # Extract first full narration paragraph from first stop for sample
            sample_paragraph = ""
            if stops and stops[0]['paragraphs']:
                # Take the first non-trivial paragraph
                for p in stops[0]['paragraphs']:
                    if len(p) > 100:
                        sample_paragraph = p[:500]
                        break

            run_result = {
                'run': run_idx + 1,
                'model': model,
                'stop_titles': stop_titles,
                'style': style_result,
                'anchor': anchor_result,
                'tokens': total_tokens,
                'cost': cost,
                'elapsed': elapsed,
                'sample_paragraph': sample_paragraph,
            }
            results[arm_label].append(run_result)

            print(f"    Stops: {stop_titles}")
            print(f"    Tokens: {total_tokens}, Cost: ${cost:.4f}, Latency: {elapsed:.1f}s")
            print(f"    Style: {style_result['failing_paragraphs']}/{style_result['total_content_paragraphs']} failing")
            print(f"    Anchor: {anchor_result['ANCHORED']}/{anchor_result['total']} anchored")

            # Clean up output file
            if output_file and os.path.exists(output_file):
                os.remove(output_file)

    # ═══════════════════════════════════════════════════════════════════════════
    # REPORT
    # ═══════════════════════════════════════════════════════════════════════════
    print(f"\n\n{'='*70}")
    print(f"RESULTS")
    print(f"{'='*70}\n")

    for arm_label in ['A', 'B']:
        arm = results[arm_label]
        model = model_a if arm_label == 'A' else model_b
        valid_runs = [r for r in arm if 'error' not in r]

        if not valid_runs:
            print(f"\nARM {arm_label} ({model}): ALL RUNS FAILED")
            for r in arm:
                if 'error' in r:
                    print(f"  Run {r['run']}: {r.get('error', 'unknown')}")
            continue

        # Aggregate style
        total_content = sum(r['style']['total_content_paragraphs'] for r in valid_runs)
        total_failing = sum(r['style']['failing_paragraphs'] for r in valid_runs)
        total_r1 = sum(r['style']['R1_IMPERATIVE'] for r in valid_runs)
        total_r3 = sum(r['style']['R3_SUGGESTIVE_EXPLORATION'] for r in valid_runs)
        total_r4 = sum(r['style']['R4_PRESCRIBED_FEELING'] for r in valid_runs)
        total_r7 = sum(r['style']['R7_HALLUCINATED_SENSORY'] for r in valid_runs)

        # Aggregate anchor
        total_anchor_paras = sum(r['anchor']['total'] for r in valid_runs)
        total_anchored = sum(r['anchor']['ANCHORED'] for r in valid_runs)
        total_nav = sum(r['anchor']['NAVIGATION'] for r in valid_runs)

        # Aggregate cost/latency
        total_tokens_arm = sum(r['tokens'] for r in valid_runs)
        total_cost_arm = sum(r['cost'] for r in valid_runs)
        avg_cost_per_tour = total_cost_arm / len(valid_runs)
        avg_latency = sum(r['elapsed'] for r in valid_runs) / len(valid_runs)

        # Stop titles
        all_titles = set()
        for r in valid_runs:
            all_titles.update(r['stop_titles'])

        print(f"\nARM {arm_label}: {model}")
        print(f"  Runs: {len(valid_runs)} successful")
        print(f"  Stop titles: {sorted(all_titles)}")
        print(f"\n  STYLE VALIDATOR:")
        print(f"    Content paragraphs: {total_content}")
        print(f"    R1 (imperative):  {total_r1}/{total_content} = {total_r1/total_content:.3f}" if total_content else "    (no data)")
        print(f"    R3 (suggestive):  {total_r3}/{total_content} = {total_r3/total_content:.3f}" if total_content else "")
        print(f"    R4 (prescribed):  {total_r4}/{total_content} = {total_r4/total_content:.3f}" if total_content else "")
        print(f"    R7 (hallucinated):{total_r7}/{total_content} = {total_r7/total_content:.3f}" if total_content else "")
        print(f"    Overall failure:  {total_failing}/{total_content} = {total_failing/total_content:.3f}" if total_content else "")
        print(f"\n  ANCHOR DETECTOR:")
        print(f"    Total paragraphs: {total_anchor_paras}")
        print(f"    ANCHORED: {total_anchored}/{total_anchor_paras} = {total_anchored/total_anchor_paras:.3f}" if total_anchor_paras else "    (no data)")
        print(f"\n  COST & LATENCY:")
        print(f"    Total tokens: {total_tokens_arm}")
        print(f"    Total spend: ${total_cost_arm:.4f}")
        print(f"    Avg cost/tour: ${avg_cost_per_tour:.4f}")
        print(f"    Avg latency/tour: {avg_latency:.1f}s")
        print(f"    Pricing rate used: ${PRICING.get(model, 0)}/1K tokens")

    # Sample paragraphs (same stop if possible)
    print(f"\n\n{'='*70}")
    print(f"SAMPLE PARAGRAPHS (first stop, first run)")
    print(f"{'='*70}\n")
    for arm_label in ['A', 'B']:
        arm = results[arm_label]
        valid = [r for r in arm if 'error' not in r]
        if valid and valid[0].get('sample_paragraph'):
            model = model_a if arm_label == 'A' else model_b
            print(f"--- ARM {arm_label} ({model}) ---")
            print(valid[0]['sample_paragraph'])
            print()

    # Per-arm spend
    print(f"\n{'='*70}")
    print(f"PER-ARM SPEND (separately reported)")
    print(f"{'='*70}")
    for arm_label in ['A', 'B']:
        arm = results[arm_label]
        valid = [r for r in arm if 'error' not in r]
        model = model_a if arm_label == 'A' else model_b
        if valid:
            arm_spend = sum(r['cost'] for r in valid)
            print(f"  ARM {arm_label} ({model}): ${arm_spend:.4f} ({sum(r['tokens'] for r in valid)} tokens)")
        else:
            print(f"  ARM {arm_label} ({model}): $0 (all runs failed)")
    total_spend = sum(r['cost'] for arm in results.values() for r in arm if 'error' not in r)
    print(f"  TOTAL: ${total_spend:.4f}")
    print(f"  Ceiling: $0.60")

    # DB safety check
    print(f"\n{'='*70}")
    print(f"DATABASE SAFETY CHECK")
    print(f"{'='*70}")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    row_count = cur.fetchone()[0]
    cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,21,24,27,28,29,152) ORDER BY id")
    nice_ids = [r[0] for r in cur.fetchall()]
    conn.close()
    print(f"  audio_tours rows: {row_count}")
    print(f"  Nice list check: {nice_ids}")
    print(f"  Expected: [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]")


if __name__ == '__main__':
    main()
