#!/usr/bin/env python3
"""tests/run_local345_corpus_usage_audit.py — LOCAL-345 scope item 2.

For every stop across scorable tours: does it have corpus, and does its body
contain anything traceable to that corpus?

Output: the count of "had corpus, used none of it" stops.
"""
import os
import sys
import re
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from db_connection import get_connection
from stop_corpus_reader import get_stop_corpus_for_tour
from tour_rubric_scorer import parse_tour

# Reuse helper from test
import unicodedata

_STOP_WORDS = {
    'the', 'and', 'for', 'was', 'were', 'are', 'that', 'this', 'with',
    'from', 'have', 'has', 'had', 'been', 'being', 'which', 'their',
    'there', 'they', 'what', 'when', 'where', 'will', 'would', 'could',
    'should', 'about', 'into', 'over', 'after', 'before', 'also', 'more',
    'most', 'other', 'than', 'then', 'these', 'those', 'some', 'such',
    'each', 'many', 'much', 'very', 'only', 'just', 'your', 'city',
    'including', 'well', 'known', 'market', 'area', 'located', 'france',
    'nice', 'tour', 'walking', 'here', 'like', 'back', 'made', 'time',
    'place', 'part', 'first', 'years', 'today',
}


def _fold(text):
    text = text.replace('\u2019', "'").replace('\u2018', "'")
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def extract_content_words(passages, stop_title):
    title_words = set(
        w.lower() for w in re.findall(r'[A-Za-z\u00C0-\u00FF]+', _fold(stop_title))
        if len(w) >= 4
    )
    content_words = set()
    for passage in passages:
        words = re.findall(r'[A-Za-z\u00C0-\u00FF]+', _fold(passage))
        for w in words:
            wl = w.lower()
            if len(wl) >= 4 and wl not in _STOP_WORDS and wl not in title_words:
                content_words.add(wl)
    return content_words


def body_uses_corpus(body_text, content_words):
    body_folded = _fold(body_text).lower()
    body_words = set(re.findall(r'[a-z]{4,}', body_folded))
    matched = content_words & body_words
    return len(matched) > 0, matched


def main():
    tours_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tours')

    # Find scorable tour files (those with actual stop content)
    tour_files = []
    for f in sorted(os.listdir(tours_dir)):
        if f.endswith('.txt'):
            tour_files.append(os.path.join(tours_dir, f))

    conn = get_connection()

    total_stops = 0
    stops_with_corpus = 0
    stops_corpus_unused = 0
    details = []

    for tour_file in tour_files:
        with open(tour_file, 'r', encoding='utf-8') as fh:
            text = fh.read()

        stops = parse_tour(text)
        if not stops:
            continue

        # Extract venue name from header
        first_line = text.split('\n')[0]
        m = re.match(r'^Step-by-Step.*?:\s*(.+)$', first_line)
        venue_name = m.group(1).strip() if m else os.path.basename(tour_file)

        stop_names = [s['title'] for s in stops]
        try:
            corpus_data = get_stop_corpus_for_tour(venue_name, stop_names, conn)
        except Exception as e:
            print(f"  SKIP {os.path.basename(tour_file)}: {e}")
            continue

        for stop in stops:
            title = stop['title']
            body = stop.get('body', '')
            if not body or len(body.strip()) < 30:
                continue

            total_stops += 1
            corpus_entry = corpus_data.get(title)
            if not corpus_entry or not corpus_entry.get('passages'):
                continue

            stops_with_corpus += 1
            content_words = extract_content_words(corpus_entry['passages'], title)
            if not content_words:
                continue

            uses, matched = body_uses_corpus(body, content_words)
            if not uses:
                stops_corpus_unused += 1
                details.append({
                    'tour': os.path.basename(tour_file),
                    'stop': title,
                    'corpus_words_sample': sorted(content_words)[:10],
                    'passages_count': len(corpus_entry['passages']),
                })

    conn.close()

    print("=" * 70)
    print("LOCAL-345: CORPUS USAGE AUDIT")
    print("=" * 70)
    print(f"Total stops with body text:         {total_stops}")
    print(f"Stops with corpus available:        {stops_with_corpus}")
    print(f"Stops with corpus UNUSED in body:   {stops_corpus_unused}")
    print(f"Usage rate:                         {((stops_with_corpus - stops_corpus_unused) / max(1, stops_with_corpus)) * 100:.1f}%")
    print()

    if details:
        print(f"DETAIL: {len(details)} stops had corpus but body used NONE of it:")
        print("-" * 70)
        for d in details:
            print(f"  Tour: {d['tour']}")
            print(f"    Stop: {d['stop']}")
            print(f"    Passages: {d['passages_count']}")
            print(f"    Corpus words (sample): {d['corpus_words_sample']}")
            print()

    return stops_corpus_unused


if __name__ == '__main__':
    count = main()
    print(f"\n{'='*70}")
    print(f"DELIVERABLE: {count} stops had corpus but used none of it in body")
    print(f"{'='*70}")
