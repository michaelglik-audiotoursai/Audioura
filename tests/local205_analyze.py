#!/usr/bin/env python3
"""LOCAL-205: Analyze generated paragraphs — style + anchor detection.

Run from repo root:
    python3 tests/local205_analyze.py
"""
import sys
import os
import json
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_connection import get_db_config
import psycopg2
from style_validator_detector import validate_paragraph, _is_style_navigation_paragraph
from stop_anchor_detector import (
    classify_paragraph, build_corpus_anchors, get_venue_corpus_for_tour,
    parse_tour_stops
)

VENUE_NAME = "Musee Matisse, Nice, France"
STOP_TITLES = ["Nu bleu IV", "Nymphe dans la forêt"]
TOUR_NAME = "Musée Matisse, Nice, France - Museum Tour"

# Where the text files live
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


def load_tour_text(arm, run):
    """Load tour text from file."""
    path = os.path.join(TESTS_DIR, f"local205_{arm}{run}_text.txt")
    with open(path, 'r') as f:
        return f.read()


def extract_paragraphs(tour_text):
    """Extract content paragraphs from tour text (skip headers/metadata).
    
    Returns list of dicts: {text, stop_title, role}
    where role is 'prolog', 'main', 'epilog', 'transition', 'sources', or 'directions'
    """
    paragraphs = []
    current_stop = None
    lines = tour_text.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Detect stop headers
        if re.match(r'^Stop \d+:', line):
            current_stop = re.sub(r'^Stop \d+:\s*', '', line)
            i += 1
            continue
        
        # Skip metadata lines
        if (line.startswith('Step-by-Step') or line.startswith('Tour-Category:') or
            line.startswith('Address:') or line.startswith('Coordinates:') or
            line.startswith('Museum Information:') or line.startswith('Directions:') or
            line == ''):
            if line.startswith('Directions:'):
                # This is a direction paragraph — skip for style/anchor
                pass
            i += 1
            continue
        
        # This is a content paragraph
        if current_stop and len(line) > 50:
            # Classify the paragraph role
            role = 'main'
            if 'you are about to embark' in line.lower() or 'the story begins' in line.lower():
                role = 'prolog'
            elif 'you have followed the thread' in line.lower():
                role = 'epilog'
            elif 'a collection that spans more ground' in line.lower():
                role = 'transition'
            elif line.startswith('Sources:'):
                role = 'sources'
            
            paragraphs.append({
                'text': line,
                'stop_title': current_stop,
                'role': role,
            })
        
        i += 1
    
    return paragraphs


def get_venue_corpus_from_db(conn):
    """Load the full venue_corpus for Musée Matisse from DB."""
    cur = conn.cursor()
    cur.execute("""
        SELECT qid, venue_name, canonical_titles_json, story_elements_json,
               pages_json, tier
        FROM venue_corpus
        WHERE venue_name ILIKE %s
    """, (f'%matisse%',))
    row = cur.fetchone()
    if not row:
        return {}
    
    qid, venue_name, canonical_titles, story_elements, pages, tier = row
    
    # Parse JSON fields
    if isinstance(canonical_titles, str):
        canonical_titles = json.loads(canonical_titles)
    if isinstance(story_elements, str):
        story_elements = json.loads(story_elements)
    if isinstance(pages, str):
        pages = json.loads(pages)
    
    return {
        'qid': qid,
        'venue_name': venue_name,
        'canonical_titles_json': canonical_titles,
        'story_elements_json': story_elements,
        'pages_json': pages,
        'tier': tier,
    }


def get_corpus_anchors_for_stop(stop_title, venue_corpus):
    """Build corpus anchors for a given stop using venue_corpus."""
    return build_corpus_anchors(venue_corpus, stop_title, TOUR_NAME)


def main():
    config = get_db_config()
    conn = psycopg2.connect(**config)
    
    # Load venue_corpus and pre-build corpus anchors for each stop
    venue_corpus = get_venue_corpus_from_db(conn)
    print(f"Venue corpus loaded: {venue_corpus.get('tier')}, "
          f"{len(venue_corpus.get('story_elements_json', []))} story elements, "
          f"{len(venue_corpus.get('canonical_titles_json', []))} canonical titles")
    
    corpus_anchors = {}
    for title in STOP_TITLES:
        corpus_anchors[title] = get_corpus_anchors_for_stop(title, venue_corpus)
        print(f"Corpus anchors for '{title}': people={corpus_anchors[title].get('people', set())}, "
              f"dates={corpus_anchors[title].get('dates', set())}, "
              f"facts={len(corpus_anchors[title].get('facts', []))}")
    
    # Results storage
    results = {'A': [], 'B': []}
    
    for arm in ['A', 'B']:
        for run in [1, 2, 3]:
            tour_text = load_tour_text(arm, run)
            paragraphs = extract_paragraphs(tour_text)
            
            run_results = []
            for para in paragraphs:
                # Style validation
                style_result = validate_paragraph(para['text'])
                
                # Anchor classification
                stop_anchors = corpus_anchors.get(para['stop_title'], {})
                anchor_result = classify_paragraph(
                    para['text'], stop_anchors,
                    para['stop_title'], TOUR_NAME
                )
                
                run_results.append({
                    'text': para['text'][:100] + '...' if len(para['text']) > 100 else para['text'],
                    'full_text': para['text'],
                    'stop_title': para['stop_title'],
                    'role': para['role'],
                    'style_violations': style_result.get('violations', []),
                    'style_rules_fired': [v['rule'] for v in style_result.get('violations', [])],
                    'anchor_classification': anchor_result['classification'],
                    'anchor': anchor_result.get('anchor'),
                })
            
            results[arm].append(run_results)
    
    # =================== SUMMARY REPORT ===================
    print("\n" + "="*70)
    print("LOCAL-205: MODEL A/B COMPARISON — MUSÉE MATISSE (COVERED STOPS)")
    print("="*70)
    
    # Count paragraphs per arm across all runs
    for arm_label, model in [('A', 'gpt-3.5-turbo'), ('B', 'gpt-4o-mini')]:
        print(f"\n--- ARM {arm_label}: {model} ---")
        total_paras = 0
        r1_count = 0
        r3_count = 0
        r4_count = 0
        r7_count = 0
        anchored_count = 0
        no_anchor_count = 0
        unlinked_count = 0
        
        for run_idx, run_data in enumerate(results[arm_label]):
            # Skip navigation, sources, transition for style counting
            content_paras = [p for p in run_data if p['role'] not in ('sources', 'transition')]
            total_paras += len(content_paras)
            
            for p in content_paras:
                for rule in p['style_rules_fired']:
                    if rule == 'R1':
                        r1_count += 1
                    elif rule == 'R3':
                        r3_count += 1
                    elif rule == 'R4':
                        r4_count += 1
                    elif rule == 'R7':
                        r7_count += 1
                
                if p['anchor_classification'] == 'ANCHORED':
                    anchored_count += 1
                elif p['anchor_classification'] == 'NO_ANCHOR':
                    no_anchor_count += 1
                elif p['anchor_classification'] == 'UNLINKED_ENTITY':
                    unlinked_count += 1
        
        # Compute rates
        failed_paras = sum(1 for run in results[arm_label] 
                         for p in run if p['role'] not in ('sources', 'transition') 
                         and len(p['style_rules_fired']) > 0)
        
        print(f"  Total content paragraphs: {total_paras}")
        print(f"  Style failures:")
        print(f"    R1 (imperative): {r1_count}/{total_paras} = {r1_count/total_paras:.3f}")
        print(f"    R3 (suggestive): {r3_count}/{total_paras} = {r3_count/total_paras:.3f}")
        print(f"    R4 (prescribed): {r4_count}/{total_paras} = {r4_count/total_paras:.3f}")
        print(f"    R7 (hallucinated sensory): {r7_count}/{total_paras} = {r7_count/total_paras:.3f}")
        print(f"    Overall failure: {failed_paras}/{total_paras} = {failed_paras/total_paras:.3f}")
        print(f"  Anchor classification:")
        print(f"    ANCHORED: {anchored_count}/{total_paras} = {anchored_count/total_paras:.3f}")
        print(f"    NO_ANCHOR: {no_anchor_count}/{total_paras} = {no_anchor_count/total_paras:.3f}")
        print(f"    UNLINKED_ENTITY: {unlinked_count}/{total_paras} = {unlinked_count/total_paras:.3f}")
    
    # =================== PER-RUN DETAIL ===================
    print("\n" + "="*70)
    print("PER-RUN DETAIL")
    print("="*70)
    
    for arm_label in ['A', 'B']:
        for run_idx, run_data in enumerate(results[arm_label]):
            print(f"\n--- {arm_label}{run_idx+1} ---")
            content = [p for p in run_data if p['role'] not in ('sources', 'transition')]
            for i, p in enumerate(content):
                violations = ', '.join(p['style_rules_fired']) if p['style_rules_fired'] else 'none'
                print(f"  P{i+1} [{p['stop_title'][:20]}] [{p['role']}] "
                      f"anchor={p['anchor_classification']} style={violations}")
                if p['anchor']:
                    print(f"      anchor_text: {p['anchor']}")
    
    # =================== FULL PARAGRAPHS FOR CLAIM CHECK ===================
    print("\n" + "="*70)
    print("ALL PARAGRAPHS (for unsupported-claim analysis)")
    print("="*70)
    
    for arm_label in ['A', 'B']:
        for run_idx, run_data in enumerate(results[arm_label]):
            print(f"\n{'='*40}")
            print(f"=== {arm_label}{run_idx+1} ===")
            print(f"{'='*40}")
            content = [p for p in run_data if p['role'] not in ('sources',)]
            for i, p in enumerate(content):
                print(f"\n--- P{i+1} [{p['stop_title']}] [{p['role']}] [{p['anchor_classification']}] ---")
                print(p['full_text'])
    
    conn.close()
    
    # Save structured results
    output_path = os.path.join(TESTS_DIR, 'local205_analysis_results.json')
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nStructured results saved to: {output_path}")


if __name__ == '__main__':
    main()
