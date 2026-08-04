#!/usr/bin/env python3
"""Extract full leaked sentences for R8 labelled set."""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_connection import get_connection

# Only patterns that actually fired
LEAKAGE_PATTERNS = [
    re.compile(r'\bone concrete sensory detail\b', re.IGNORECASE),
    re.compile(r'\benvelops? you in the atmosphere\b', re.IGNORECASE),
    re.compile(r'\bwhat makes this stop\b', re.IGNORECASE),
]

def extract_leaked_sentences():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, tour_name, tour_content
        FROM audio_tours 
        WHERE tour_content IS NOT NULL AND tour_content != ''
        ORDER BY id
    """)
    rows = cur.fetchall()
    
    results = []
    for tour_id, tour_name, content in rows:
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', content)
        for sent in sentences:
            for pat in LEAKAGE_PATTERNS:
                if pat.search(sent):
                    results.append({
                        'tour_id': tour_id,
                        'sentence': sent.strip()[:300],
                        'pattern': pat.pattern,
                    })
                    break
    
    conn.close()
    
    print(f"Total leaked sentences found: {len(results)}")
    print()
    for r in results:
        print(f"Tour {r['tour_id']} | Pattern: {r['pattern']}")
        print(f"  \"{r['sentence']}\"")
        print()

if __name__ == '__main__':
    extract_leaked_sentences()
