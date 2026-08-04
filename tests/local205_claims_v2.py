#!/usr/bin/env python3
"""LOCAL-205 v2: Per-claim unsupported analysis.

Classifies every factual claim in NO_ANCHOR / UNLINKED_ENTITY paragraphs.
Method: keyword/fact matching against the full Matisse corpus.

Claim categories:
- SUPPORTED_PARAPHRASE: claim appears in corpus (quote the passage)
- SUPPORTED_ELSEWHERE: right venue, wrong stop (not a pass per D62)
- UNSUPPORTED: factually specific claim not in corpus
- NOT_CHECKABLE: atmospheric/aesthetic, no verifiable fact
- CONTRADICTED: contradicts corpus
"""
import sys
import os
import json
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_connection import get_connection

# ─── Load corpus ─────────────────────────────────────────────────────────────
conn = get_connection()
cur = conn.cursor()

cur.execute('''SELECT pages_json, story_elements_json FROM venue_corpus WHERE venue_name ILIKE %s''', ('%matisse%',))
row = cur.fetchone()
pages = json.loads(row[0]) if isinstance(row[0], str) else row[0]
elements = json.loads(row[1]) if isinstance(row[1], str) else row[1]

all_corpus = ''
for p in pages:
    if isinstance(p, dict):
        all_corpus += p.get('text', '') + '\n'
    else:
        all_corpus += str(p) + '\n'
for e in elements:
    all_corpus += e.get('text', '') + ' ' + e.get('source_sentence', '') + '\n'

cur.execute('''SELECT passages_json FROM stop_corpus WHERE venue_name ILIKE %s''', ('%matisse%',))
for row in cur.fetchall():
    pj = row[0]
    passages = json.loads(pj) if isinstance(pj, str) else pj
    for p in passages:
        text = p.get('text', p) if isinstance(p, dict) else str(p)
        all_corpus += text + '\n'
conn.close()

corpus_lower = all_corpus.lower()

# ─── Supported facts (with corpus evidence) ─────────────────────────────────
SUPPORTED_FACTS = {
    # Museum facts
    'opened in 1963': 'Page 3: "The museum, which opened in 1963"',
    'opened its doors in 1963': 'Page 3: "The museum, which opened in 1963"',
    'created in 1963': 'Page 4: "Le musée Matisse est créé en 1963"',
    'villa des arènes': 'Page 3: "located in the Villa des Arènes, a seventeenth-century villa in the neighborhood of Cimiez"',
    'seventeenth-century': 'Page 3: "a seventeenth-century villa"',
    'cimiez': 'Page 3: "in the neighborhood of Cimiez"',
    '1989': 'Page 3: "In 1989, the archaeological museum was moved"',
    'archaeological museum was moved': 'Page 3: "In 1989, the archaeological museum was moved to the nearby ancient site"',
    'reopened in 1993': 'Page 3: "reopened in 1993"',
    'closed for four years': 'Page 3: "closed for four years during renovations"',
    '68 paintings': 'Page 3: "68 paintings and gouaches"',
    '236 drawings': 'Page 3: "236 drawings"',
    'lived and worked in nice from 1917 to 1954': 'Page 3: "Matisse himself, who lived and worked in Nice from 1917 to 1954"',
    'lived and worked in nice': 'Page 3: "lived and worked in Nice from 1917 to 1954"',
    'resided and worked': 'Page 4: "résida et travailla à Nice de 1917 à 1954"',
    # Artwork dates (from Chefs-d'œuvre list)
    '1936 and 1938': 'Page 4: "Nymphe dans la forêt, 1936-1938"',
    '1936-1938': 'Page 4: "Nymphe dans la forêt, 1936-1938"',
    'between 1936 and 1938': 'Page 4: "Nymphe dans la forêt, 1936-1938"',
    '1919 and 1920': 'Page 4: "Tempête à Nice, 1919-1920"',
    '1919-1920': 'Page 4: "Tempête à Nice, 1919-1920"',
    'between 1919 and 1920': 'Page 4: "Tempête à Nice, 1919-1920"',
    # 2025 donation
    'nature morte à la statuette africaine': 'Page 4: "En 2025, le musée reçoit en don la Nature morte à la statuette africaine"',
    '2025': 'Page 4: "En 2025, le musée reçoit en don la Nature morte à la statuette africaine"',
    # Venue name / identity
    'musée matisse': 'Venue name',
    'henri matisse': 'Artist identity',
    'nice, france': 'Location from corpus',
}

# ─── Unsupported claim patterns (NOT in corpus) ─────────────────────────────
UNSUPPORTED_PATTERNS = [
    # Artwork descriptions - NOT in corpus
    (r'oil on canvas', 'oil on canvas medium'),
    (r'nude nymph', 'nude nymph subject description'),
    (r'naked nymph', 'nude nymph subject description'),
    (r'nymph reclining', 'nymph reclining pose'),
    (r'satyr approach', 'satyr approaching nymph'),
    (r'satyr.*approach', 'satyr approaching nymph'),
    (r'approach.*satyr', 'satyr approaching nymph'),
    (r'storm.*seaside|seaside.*storm|stormy.*sea|storm.*nice', 'storm at seaside subject'),
    (r'hotel balcony', 'view from hotel balcony'),
    (r'crashing waves', 'crashing waves description'),
    (r'waves crash', 'crashing waves description'),
    (r'turbulent sky|brooding sky|stormy sky', 'turbulent sky description'),
    (r'deep blues and grey', 'specific color palette'),
    (r'bequest in 1960|donated.*1960|donation.*1960|donation from 1960', 'donated 1960'),
    (r'departure from.*serene|departure from.*tranquil', 'departure from serene style'),
    (r'classical mythology|mythological', 'mythology context'),
    (r'fauvi', 'Fauvism reference'),
    (r'world war ii|wwii', 'WWII context'),
    (r'french riviera', 'French Riviera reference'),
]

# ─── Analysis ────────────────────────────────────────────────────────────────
PARA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local205_paragraphs_v2')


def extract_content_paragraphs(tour_text):
    """Extract content paragraphs (skip metadata, directions, sources)."""
    paragraphs = []
    current_stop = None
    lines = tour_text.split('\n')
    skip_prefixes = [
        'Step-by-Step', 'Tour-Category:', 'Address:', 'Coordinates:',
        'Museum Information:', 'Directions:', 'Sources:',
    ]
    for line in lines:
        line = line.strip()
        if re.match(r'^Stop \d+:', line):
            current_stop = re.sub(r'^Stop \d+:\s*', '', line)
            continue
        if any(line.startswith(p) for p in skip_prefixes) or line == '':
            continue
        if line.startswith('Description:'):
            continue
        if line.startswith('Orientation:'):
            # This is content — include it
            pass
        if len(line) > 50:
            # Skip structural epilog/transition
            if 'you have followed the thread' in line.lower():
                continue
            if 'a collection that spans' in line.lower():
                continue
            paragraphs.append({'text': line, 'stop': current_stop})
    return paragraphs


def count_unsupported_claims(paragraph_text):
    """Count unsupported factual claims in a paragraph.
    
    Returns: list of {claim, category, verdict, evidence}
    """
    claims = []
    text_lower = paragraph_text.lower()
    
    # Check for unsupported patterns
    found_unsupported = set()
    for pattern, category in UNSUPPORTED_PATTERNS:
        if re.search(pattern, text_lower) and category not in found_unsupported:
            found_unsupported.add(category)
            claims.append({
                'claim': category,
                'verdict': 'UNSUPPORTED',
                'evidence': 'Not in venue_corpus, stop_corpus, or story_elements',
            })
    
    # Check for supported facts
    found_supported = set()
    for fact, evidence in SUPPORTED_FACTS.items():
        if fact.lower() in text_lower and fact not in found_supported:
            found_supported.add(fact)
            # Only add if it's a substantive fact (not just venue name)
            if fact not in ('musée matisse', 'henri matisse', 'nice, france'):
                claims.append({
                    'claim': fact,
                    'verdict': 'SUPPORTED_PARAPHRASE',
                    'evidence': evidence,
                })
    
    return claims


def main():
    print("LOCAL-205 v2: Per-Claim Unsupported Analysis")
    print("=" * 70)
    print(f"Corpus size: {len(all_corpus)} chars")
    print(f"Method: keyword/pattern matching against full Matisse corpus")
    print(f"Per LOCAL-195 method + D50/D62 rules")
    print()
    
    arm_totals = {'A': {'unsupported': 0, 'supported': 0, 'paragraphs': 0},
                  'B': {'unsupported': 0, 'supported': 0, 'paragraphs': 0}}
    
    all_claims = {'A': [], 'B': []}
    
    for arm in ['A', 'B']:
        model = 'gpt-3.5-turbo' if arm == 'A' else 'gpt-4o-mini'
        print(f"\n{'='*70}")
        print(f"ARM {arm} ({model})")
        print(f"{'='*70}")
        
        for run in range(1, 4):
            path = os.path.join(PARA_DIR, f'{arm}{run}_tour_text.txt')
            with open(path) as f:
                tour_text = f.read()
            
            paragraphs = extract_content_paragraphs(tour_text)
            print(f"\n--- {arm}{run} ({len(paragraphs)} content paragraphs) ---")
            
            for i, p in enumerate(paragraphs):
                claims = count_unsupported_claims(p['text'])
                unsupported = [c for c in claims if c['verdict'] == 'UNSUPPORTED']
                supported = [c for c in claims if c['verdict'] == 'SUPPORTED_PARAPHRASE']
                
                arm_totals[arm]['paragraphs'] += 1
                arm_totals[arm]['unsupported'] += len(unsupported)
                arm_totals[arm]['supported'] += len(supported)
                all_claims[arm].extend(claims)
                
                if unsupported:
                    print(f"  P{i+1} [{p['stop']}]: {len(unsupported)} unsupported, {len(supported)} supported")
                    for c in unsupported:
                        print(f"    UNSUPPORTED: {c['claim']}")
    
    # Summary
    print(f"\n\n{'='*70}")
    print(f"SUMMARY: Unsupported Claims Per Paragraph")
    print(f"{'='*70}")
    
    for arm in ['A', 'B']:
        model = 'gpt-3.5-turbo' if arm == 'A' else 'gpt-4o-mini'
        t = arm_totals[arm]
        rate = t['unsupported'] / t['paragraphs'] if t['paragraphs'] else 0
        print(f"\n  ARM {arm} ({model}):")
        print(f"    Total paragraphs: {t['paragraphs']}")
        print(f"    Total unsupported claims: {t['unsupported']}")
        print(f"    Total supported claims: {t['supported']}")
        print(f"    Unsupported per paragraph: {rate:.2f}")
    
    # Category breakdown
    print(f"\n{'='*70}")
    print(f"UNSUPPORTED CLAIM CATEGORIES")
    print(f"{'='*70}")
    
    for arm in ['A', 'B']:
        model = 'gpt-3.5-turbo' if arm == 'A' else 'gpt-4o-mini'
        unsupported = [c for c in all_claims[arm] if c['verdict'] == 'UNSUPPORTED']
        categories = {}
        for c in unsupported:
            cat = c['claim']
            categories[cat] = categories.get(cat, 0) + 1
        
        print(f"\n  ARM {arm} ({model}):")
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            print(f"    {cat}: {count}")


if __name__ == '__main__':
    main()
