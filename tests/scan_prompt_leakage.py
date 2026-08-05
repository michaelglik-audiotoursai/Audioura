#!/usr/bin/env python3
"""Part 1 — LOCAL-213: Scan stored tours for prompt leakage into narration.

Looks for phrasing from the narration prompt (generate_tour_text.py) surfacing
verbatim or near-verbatim in the generated output stored in audio_tours.tour_content.

Patterns searched (derived from the actual prompt text):
 - "one concrete sensory detail"
 - "in this paragraph"
 - "as instructed"
 - "the following" (in narration context, not nav)
 - "this description will"
 - "your task"
 - numbered-list residue ("1.", "2.", etc. starting a line)
 - "Paragraph 1:", "Paragraph 2:", etc.
 - stray markdown (##, **, ```)
 - "places the listener"
 - "envelops you in the atmosphere"
 - "what makes this stop"
 - "historical or cultural context"
 - "how this stop connects"
 - "explain-what-you-name"
 - "opening style"
 - "category voice"

Read-only. No modifications to the database.
"""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_connection import get_connection

# Patterns that indicate the model restated its instructions
LEAKAGE_PATTERNS = [
    # Exact prompt phrases
    (r'\bone concrete sensory detail\b', 'prompt phrase: "one concrete sensory detail"'),
    (r'\bplaces the listener\b', 'prompt phrase: "places the listener"'),
    (r'\benvelops? you in the atmosphere\b', 'prompt phrase: "envelops you in the atmosphere"'),
    (r'\bwhat makes this stop\b', 'prompt phrase: "what makes this stop"'),
    (r'\bhistorical or cultural context\b', 'prompt phrase: "historical or cultural context"'),
    (r'\bhow this stop connects\b', 'prompt phrase: "how this stop connects"'),
    (r'\bexplain-what-you-name\b', 'prompt phrase: "explain-what-you-name"'),
    (r'\bopening style\b', 'prompt phrase: "opening style"'),
    (r'\bcategory voice\b', 'prompt phrase: "category voice"'),
    (r'\bthis description will\b', 'prompt phrase: "this description will"'),
    (r'\byour task\b', 'prompt phrase: "your task"'),
    (r'\bas instructed\b', 'prompt phrase: "as instructed"'),
    # "In this paragraph" — meta-referential (the output doesn't have "paragraphs")
    (r'\bin this paragraph\b', 'meta-reference: "in this paragraph"'),
    # "The following" at sentence start in narration context (not nav)
    (r'(?<=[.!?]\s)The following\b', 'meta-reference: "the following" (sentence-initial)'),
    (r'^The following\b', 'meta-reference: "the following" (paragraph-initial)'),
    # Numbered list residue: "1." / "2." at start of line
    (r'(?:^|\n)\s*\d+\.\s+[A-Z]', 'numbered list residue'),
    # Stray markdown
    (r'(?:^|\n)\s*#{1,3}\s+', 'stray markdown heading (##)'),
    (r'\*\*[^*]+\*\*', 'stray markdown bold (**)'),
    (r'```', 'stray markdown code fence'),
    # "Paragraph N:" headers
    (r'\bParagraph\s+\d+\s*:', 'meta-reference: "Paragraph N:"'),
    # Direct prompt echoes from the Include list
    (r'\binclude[sd]?\s+(?:a\s+)?(?:one\s+)?(?:concrete\s+)?sensory\b', 'echoed include instruction'),
    # "a sound, material, smell" — the exact triple from the prompt
    (r'\ba sound,?\s*(?:a\s+)?material,?\s*(?:a\s+)?smell\b', 'prompt list: "a sound, material, smell"'),
    # "anchors the listener in time" — from opening style instruction
    (r'\banchors? the listener\b', 'prompt phrase: "anchors the listener"'),
]

COMPILED_PATTERNS = [(re.compile(p, re.IGNORECASE | re.MULTILINE), desc) for p, desc in LEAKAGE_PATTERNS]


def scan_tours():
    """Scan all tours for prompt leakage. Returns structured results."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Get all tours with content
    cur.execute("""
        SELECT id, tour_name, tour_content, is_test 
        FROM audio_tours 
        WHERE tour_content IS NOT NULL AND tour_content != ''
        ORDER BY id
    """)
    rows = cur.fetchall()
    
    print(f"Total tours with content: {len(rows)}")
    print(f"{'='*78}")
    
    total_tours = len(rows)
    tours_with_leakage = 0
    total_paragraphs = 0
    paragraphs_with_leakage = 0
    all_findings = []
    
    for tour_id, tour_name, tour_content, is_test in rows:
        # Split into paragraphs (stop-level)
        # Tour content uses "## Stop" or numbered headers
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', tour_content) if p.strip() and len(p.strip()) > 50]
        
        tour_findings = []
        for para_idx, para in enumerate(paragraphs):
            total_paragraphs += 1
            para_leaked = False
            for pattern, desc in COMPILED_PATTERNS:
                matches = pattern.findall(para)
                if matches:
                    for match in matches:
                        match_text = match if isinstance(match, str) else match[0] if match else ''
                        # Get surrounding context
                        m = pattern.search(para)
                        if m:
                            start = max(0, m.start() - 40)
                            end = min(len(para), m.end() + 60)
                            context = para[start:end].replace('\n', ' ')
                            tour_findings.append({
                                'tour_id': tour_id,
                                'tour_name': tour_name,
                                'para_idx': para_idx,
                                'pattern_desc': desc,
                                'context': context,
                                'is_test': is_test,
                            })
                            if not para_leaked:
                                para_leaked = True
                                paragraphs_with_leakage += 1
                            break  # One finding per pattern per paragraph
        
        if tour_findings:
            tours_with_leakage += 1
            all_findings.extend(tour_findings)
    
    conn.close()
    return {
        'total_tours': total_tours,
        'tours_with_leakage': tours_with_leakage,
        'total_paragraphs': total_paragraphs,
        'paragraphs_with_leakage': paragraphs_with_leakage,
        'findings': all_findings,
    }


def print_report(results):
    """Print a formatted report."""
    print(f"\n{'='*78}")
    print(f"PROMPT LEAKAGE SCAN — LOCAL-213 Part 1")
    print(f"{'='*78}")
    print(f"\nTotal tours scanned: {results['total_tours']}")
    print(f"Tours with leakage: {results['tours_with_leakage']}")
    print(f"Total paragraphs scanned: {results['total_paragraphs']}")
    print(f"Paragraphs with leakage: {results['paragraphs_with_leakage']}")
    
    if results['total_paragraphs'] > 0:
        rate = 100 * results['paragraphs_with_leakage'] / results['total_paragraphs']
        print(f"Leakage rate: {rate:.1f}% of paragraphs")
    
    print(f"\n{'─'*78}")
    print(f"FINDINGS BY PATTERN")
    print(f"{'─'*78}")
    
    # Group by pattern
    from collections import Counter
    pattern_counts = Counter(f['pattern_desc'] for f in results['findings'])
    for desc, count in pattern_counts.most_common():
        print(f"  {count:3d}× {desc}")
    
    print(f"\n{'─'*78}")
    print(f"DETAILED EXAMPLES (first 3 per pattern)")
    print(f"{'─'*78}")
    
    shown = Counter()
    for f in results['findings']:
        if shown[f['pattern_desc']] < 3:
            shown[f['pattern_desc']] += 1
            test_flag = " [TEST]" if f['is_test'] else ""
            print(f"\n  [{f['pattern_desc']}] Tour {f['tour_id']}{test_flag}: {f['tour_name'][:40]}")
            print(f"    ...{f['context']}...")
    
    # Breakdown: test vs production
    print(f"\n{'─'*78}")
    print(f"TEST vs PRODUCTION BREAKDOWN")
    print(f"{'─'*78}")
    test_findings = [f for f in results['findings'] if f.get('is_test')]
    prod_findings = [f for f in results['findings'] if not f.get('is_test')]
    test_tours = set(f['tour_id'] for f in test_findings)
    prod_tours = set(f['tour_id'] for f in prod_findings)
    print(f"  Test tours with leakage: {len(test_tours)}")
    print(f"  Production tours with leakage: {len(prod_tours)}")
    print(f"  Test findings: {len(test_findings)}")
    print(f"  Production findings: {len(prod_findings)}")


if __name__ == '__main__':
    results = scan_tours()
    print_report(results)
