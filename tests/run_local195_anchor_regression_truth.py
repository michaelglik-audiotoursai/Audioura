#!/usr/bin/env python3
"""LOCAL-195: Hand-check whether gpt-4o-mini's anchor regression is real.

Method:
  1. Generate MAMAC tours with each model (1 run each, 2 stops)
  2. Run anchor detector on both
  3. Collect NO_ANCHOR and UNLINKED_ENTITY paragraphs
  4. Output them for manual fact-checking against corpus

$0.35 ceiling. No DB writes. No detector modification. No container rebuild.
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from db_connection import get_connection
from stop_anchor_detector_v2 import (
    parse_tour_stops,
    build_corpus_anchors,
    build_sibling_corpus_texts,
    classify_paragraph,
    is_navigation_paragraph,
    _normalize_for_match,
)
from stop_anchor_detector_v2_with_stop_corpus import (
    get_stop_corpus_passages,
    get_stop_corpus_venue_name,
    enrich_venue_corpus_with_stop_passages,
    get_venue_corpus_for_tour,
)

LOCATION = "Musee d Art Moderne et d Art Contemporain, Nice, France"
TOUR_TYPE = "museum"
STOPS_PER_RUN = 2


def _ensure_env():
    """Ensure OPENAI_API_KEY is set."""
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


def generate_one_tour(model_name: str):
    """Generate a 2-stop MAMAC tour. Returns (tour_text, tokens, elapsed)."""
    _ensure_env()
    os.environ['TOUR_LLM_MODEL'] = model_name
    os.environ['STORIED_MODE'] = 'true'
    _saved_db_url = os.environ.pop('DATABASE_URL', None)

    if 'generate_tour_text' in sys.modules:
        del sys.modules['generate_tour_text']

    from generate_tour_text import generate_tour_text

    t0 = time.time()
    try:
        tour_text, output_file, coords = generate_tour_text(
            location=LOCATION,
            tour_type=TOUR_TYPE,
            total_stops=STOPS_PER_RUN,
        )
    except Exception as e:
        print(f"  GENERATION ERROR ({model_name}): {e}")
        import traceback; traceback.print_exc()
        tour_text = None
        output_file = None
    elapsed = time.time() - t0

    from generate_tour_text import _LAST_GENERATION_COST as cost_info
    total_tokens = cost_info.get('total_tokens', 0)

    if _saved_db_url:
        os.environ['DATABASE_URL'] = _saved_db_url
    os.environ.pop('TOUR_LLM_MODEL', None)

    # Clean up file
    if output_file and os.path.exists(output_file):
        os.remove(output_file)

    return tour_text, total_tokens, elapsed


def run_detector_detailed(tour_text):
    """Run anchor detector and return per-paragraph results with full text."""
    stops = parse_tour_stops(tour_text)
    if not stops:
        return []

    conn = get_connection()
    try:
        import psycopg2.extras
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        tour_name = "MAMAC, Nice - Museum Tour"

        # Get venue_corpus
        cur.execute("""
            SELECT * FROM venue_corpus
            WHERE venue_name ILIKE %s OR venue_name ILIKE %s LIMIT 1
        """, ('%MAMAC%', '%Moderne%Contemporain%'))
        vc_row = cur.fetchone()
        venue_corpus = None
        if vc_row:
            venue_corpus = dict(vc_row)
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

        # Build enriched per-stop corpus (same as LOCAL-194 detector)
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

        # Classify each paragraph
        results = []
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
                results.append({
                    'stop_title': stop['title'],
                    'full_text': para,
                    'classification': result['classification'],
                    'anchor': result.get('anchor'),
                    'all_anchors': result.get('all_anchors', []),
                })

        return results
    finally:
        conn.close()


def main():
    _ensure_env()

    print("=" * 80)
    print("LOCAL-195: Anchor Regression Truth Check")
    print("  Venue: MAMAC, Nice (2 stops)")
    print("  Arms: gpt-3.5-turbo vs gpt-4o-mini")
    print("=" * 80)

    all_results = {}
    total_spend = 0.0

    for model in ['gpt-3.5-turbo', 'gpt-4o-mini']:
        print(f"\n{'─'*80}")
        print(f"Generating with {model}...")
        tour_text, tokens, elapsed = generate_one_tour(model)

        if not tour_text:
            print(f"  FAILED")
            continue

        # Cost
        rate = 0.002 if model == 'gpt-3.5-turbo' else 0.000285
        cost = tokens / 1000 * rate
        total_spend += cost
        print(f"  Tokens: {tokens}, Cost: ${cost:.4f}, Time: {elapsed:.1f}s")

        # Run detector
        para_results = run_detector_detailed(tour_text)

        # Collect stops
        stops = parse_tour_stops(tour_text)
        stop_titles = [s['title'] for s in stops]
        print(f"  Stops: {stop_titles}")

        # Summary
        classes = {}
        for r in para_results:
            c = r['classification']
            classes[c] = classes.get(c, 0) + 1
        print(f"  Classifications: {classes}")

        all_results[model] = {
            'tour_text': tour_text,
            'tokens': tokens,
            'cost': cost,
            'elapsed': elapsed,
            'stop_titles': stop_titles,
            'para_results': para_results,
            'classifications': classes,
        }

    print(f"\n{'='*80}")
    print(f"TOTAL SPEND: ${total_spend:.4f} (ceiling: $0.35)")
    print(f"{'='*80}")

    # Output the NO_ANCHOR and UNLINKED_ENTITY paragraphs for manual checking
    print(f"\n\n{'='*80}")
    print("NO_ANCHOR AND UNLINKED_ENTITY PARAGRAPHS — FOR MANUAL FACT CHECK")
    print("=" * 80)

    for model, data in all_results.items():
        print(f"\n\n{'━'*80}")
        print(f"MODEL: {model}")
        print(f"Stops: {data['stop_titles']}")
        print(f"{'━'*80}")

        flagged = [r for r in data['para_results']
                   if r['classification'] in ('NO_ANCHOR', 'UNLINKED_ENTITY')]

        print(f"\nFlagged paragraphs: {len(flagged)} "
              f"(NO_ANCHOR: {sum(1 for r in flagged if r['classification']=='NO_ANCHOR')}, "
              f"UNLINKED_ENTITY: {sum(1 for r in flagged if r['classification']=='UNLINKED_ENTITY')})")

        for i, r in enumerate(flagged, 1):
            print(f"\n{'─'*60}")
            print(f"[{i}] Stop: {r['stop_title']}")
            print(f"    Classification: {r['classification']}")
            print(f"    Full text:")
            print(f"    {r['full_text']}")
            print()

    # DB safety
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    print(f"\naudio_tours rows: {cur.fetchone()[0]}")
    cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,21,24,27,28,29,152) ORDER BY id")
    print(f"Nice list: {[r[0] for r in cur.fetchall()]}")
    conn.close()


if __name__ == '__main__':
    main()
