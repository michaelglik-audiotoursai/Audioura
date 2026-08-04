#!/usr/bin/env python3
"""LOCAL-205 v2: Analyze generated paragraphs — style + anchor detection.

Run from repo root:
    python3 tests/local205_analyze_v2.py
"""
import sys
import os
import json
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_connection import get_connection
from style_validator_detector import validate_paragraph

VENUE_NAME = "Musee Matisse, Nice, France"
STOP_TITLES = ["Nymphe dans la forêt", "Tempête à Nice"]
TOUR_NAME = "Musée Matisse, Nice, France - Museum Tour"

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PARA_DIR = os.path.join(TESTS_DIR, 'local205_paragraphs_v2')


def load_tour_text(arm, run):
    path = os.path.join(PARA_DIR, f'{arm}{run}_tour_text.txt')
    with open(path, 'r') as f:
        return f.read()


def extract_content_paragraphs(tour_text):
    """Extract content paragraphs: skip headers, metadata, directions, source lines.
    
    Returns list of {text, stop_title, para_type}
    """
    paragraphs = []
    current_stop = None
    lines = tour_text.split('\n')
    
    skip_prefixes = [
        'Step-by-Step', 'Tour-Category:', 'Address:', 'Coordinates:',
        'Museum Information:', 'Directions:', 'Description:', 'Sources:',
    ]
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Stop header
        if re.match(r'^Stop \d+:', line):
            current_stop = re.sub(r'^Stop \d+:\s*', '', line)
            i += 1
            continue
        
        # Skip metadata
        if any(line.startswith(p) for p in skip_prefixes) or line == '':
            i += 1
            continue
        
        # Content paragraph (min 50 chars to skip short fragments)
        if len(line) > 50:
            # Determine type
            if 'you have followed the thread' in line.lower():
                para_type = 'epilog'
            elif 'you are about to embark' in line.lower():
                para_type = 'prolog'
            elif 'a collection that spans' in line.lower():
                para_type = 'transition'
            elif line.startswith('From ') and 'to' in line and ('thread' in line.lower() or 'spans' in line.lower()):
                para_type = 'structural'
            else:
                para_type = 'content'
            
            paragraphs.append({
                'text': line,
                'stop_title': current_stop,
                'para_type': para_type,
            })
        
        i += 1
    
    return paragraphs


def run_style_analysis(paragraphs):
    """Run style validator on content paragraphs."""
    results = {
        'R1_IMPERATIVE': 0,
        'R3_SUGGESTIVE_EXPLORATION': 0,
        'R4_PRESCRIBED_FEELING': 0,
        'R7_HALLUCINATED_SENSORY': 0,
        'navigation_paragraphs': 0,
        'total_content_paragraphs': 0,
        'failing_paragraphs': 0,
        'per_paragraph': [],
    }
    
    for p in paragraphs:
        vr = validate_paragraph(p['text'])
        
        if vr['is_navigation']:
            results['navigation_paragraphs'] += 1
            results['per_paragraph'].append({
                'stop': p['stop_title'],
                'type': p['para_type'],
                'classification': 'NAVIGATION',
                'findings': [],
                'text_preview': p['text'][:100],
            })
            continue
        
        results['total_content_paragraphs'] += 1
        findings = vr.get('findings', [])
        
        if findings:
            results['failing_paragraphs'] += 1
            for f in findings:
                rule = f['rule_id']
                if rule in results:
                    results[rule] += 1
        
        results['per_paragraph'].append({
            'stop': p['stop_title'],
            'type': p['para_type'],
            'classification': 'FAIL' if findings else 'PASS',
            'findings': [f['rule_id'] for f in findings],
            'text_preview': p['text'][:100],
        })
    
    return results


def run_anchor_analysis(tour_text, paragraphs):
    """Run anchor detector."""
    from stop_anchor_detector_v2 import (
        parse_tour_stops, build_corpus_anchors, classify_paragraph,
        is_navigation_paragraph, _normalize_for_match,
        build_sibling_corpus_texts,
    )
    from stop_anchor_detector_v2_with_stop_corpus import (
        get_stop_corpus_passages, get_stop_corpus_venue_name,
        enrich_venue_corpus_with_stop_passages, get_venue_corpus_for_tour,
    )
    import psycopg2.extras
    
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Get venue_corpus
    cur.execute("""
        SELECT * FROM venue_corpus WHERE venue_name ILIKE %s LIMIT 1
    """, ('%matisse%',))
    vc_row = cur.fetchone()
    venue_corpus = dict(vc_row) if vc_row else None
    if venue_corpus:
        for jf in ('story_elements_json', 'canonical_titles_json', 'pages_json'):
            val = venue_corpus.get(jf)
            if isinstance(val, str):
                venue_corpus[jf] = json.loads(val)
    
    # Get stop_corpus venue name
    cur.execute("SELECT DISTINCT venue_name FROM stop_corpus WHERE venue_name ILIKE %s", ('%matisse%',))
    row = cur.fetchone()
    sc_venue_name = row['venue_name'] if row else None
    
    # Build enriched corpus per stop
    enriched_per_stop = {}
    for title in STOP_TITLES:
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
    for title in STOP_TITLES:
        vc = enriched_per_stop[title]
        if vc:
            anchors = build_corpus_anchors(vc, title, TOUR_NAME)
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
    totals = {'ANCHORED': 0, 'NO_ANCHOR': 0, 'UNLINKED_ENTITY': 0, 'NAVIGATION': 0, 'total': 0}
    per_para = []
    
    for p in paragraphs:
        stop_title = p['stop_title'] or STOP_TITLES[0]  # fallback
        vc = enriched_per_stop.get(stop_title, venue_corpus)
        
        corpus_anchors = build_corpus_anchors(vc, stop_title, TOUR_NAME) if vc else {
            'people': set(), 'dates': set(), 'titles': set(),
            'facts': [], 'all_corpus_people': set(), 'all_corpus_text': '',
        }
        
        result = classify_paragraph(
            p['text'], corpus_anchors, stop_title, TOUR_NAME,
            sibling_corpus_texts=sibling_corpus_texts
        )
        
        classification = result['classification']
        totals[classification] += 1
        totals['total'] += 1
        per_para.append({
            'stop': stop_title,
            'type': p['para_type'],
            'classification': classification,
            'text_preview': p['text'][:100],
        })
    
    conn.close()
    return totals, per_para


def main():
    print("LOCAL-205 v2: Style + Anchor Analysis")
    print("=" * 60)
    
    all_style = {'A': [], 'B': []}
    all_anchor = {'A': [], 'B': []}
    all_paras = {'A': [], 'B': []}
    
    for arm in ['A', 'B']:
        for run in range(1, 4):
            tour_text = load_tour_text(arm, run)
            paragraphs = extract_content_paragraphs(tour_text)
            
            print(f"\n--- {arm}{run} ({len(paragraphs)} paragraphs) ---")
            
            # Style
            style = run_style_analysis(paragraphs)
            all_style[arm].append(style)
            
            # Anchor
            anchor_totals, anchor_per_para = run_anchor_analysis(tour_text, paragraphs)
            all_anchor[arm].append(anchor_totals)
            all_paras[arm].append(paragraphs)
            
            print(f"  Style: {style['failing_paragraphs']}/{style['total_content_paragraphs']} failing")
            print(f"  Anchor: {anchor_totals['ANCHORED']}/{anchor_totals['total']} anchored")
            
            # Print findings
            for pp in style['per_paragraph']:
                if pp['findings']:
                    print(f"    FAIL [{', '.join(pp['findings'])}]: {pp['text_preview']}")
    
    # Aggregate
    print(f"\n\n{'='*60}")
    print(f"AGGREGATE RESULTS")
    print(f"{'='*60}")
    
    for arm in ['A', 'B']:
        model = 'gpt-3.5-turbo' if arm == 'A' else 'gpt-4o-mini'
        total_content = sum(s['total_content_paragraphs'] for s in all_style[arm])
        total_failing = sum(s['failing_paragraphs'] for s in all_style[arm])
        total_r1 = sum(s['R1_IMPERATIVE'] for s in all_style[arm])
        total_r3 = sum(s['R3_SUGGESTIVE_EXPLORATION'] for s in all_style[arm])
        total_r4 = sum(s['R4_PRESCRIBED_FEELING'] for s in all_style[arm])
        total_r7 = sum(s['R7_HALLUCINATED_SENSORY'] for s in all_style[arm])
        
        total_anchor_paras = sum(a['total'] for a in all_anchor[arm])
        total_anchored = sum(a['ANCHORED'] for a in all_anchor[arm])
        total_no_anchor = sum(a['NO_ANCHOR'] for a in all_anchor[arm])
        total_unlinked = sum(a['UNLINKED_ENTITY'] for a in all_anchor[arm])
        total_nav = sum(a['NAVIGATION'] for a in all_anchor[arm])
        
        print(f"\nARM {arm} ({model}):")
        print(f"  STYLE (D71 corrected R1):")
        if total_content:
            print(f"    R1 (imperative):  {total_r1}/{total_content} = {total_r1/total_content:.3f}")
            print(f"    R3 (suggestive):  {total_r3}/{total_content} = {total_r3/total_content:.3f}")
            print(f"    R4 (prescribed):  {total_r4}/{total_content} = {total_r4/total_content:.3f}")
            print(f"    R7 (hallucinated):{total_r7}/{total_content} = {total_r7/total_content:.3f}")
            print(f"    Overall failure:  {total_failing}/{total_content} = {total_failing/total_content:.3f}")
        
        print(f"  ANCHOR:")
        if total_anchor_paras:
            print(f"    ANCHORED:        {total_anchored}/{total_anchor_paras} = {total_anchored/total_anchor_paras:.3f}")
            print(f"    NO_ANCHOR:       {total_no_anchor}/{total_anchor_paras}")
            print(f"    UNLINKED_ENTITY: {total_unlinked}/{total_anchor_paras}")
            print(f"    NAVIGATION:      {total_nav}/{total_anchor_paras}")


if __name__ == '__main__':
    main()
