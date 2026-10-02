"""Dump the actual SERP snippets for stops 2 and 3 of the MFA Unbound eval.

This script reveals whether the failure is retrieval (junk snippets) or
injection (good snippets, ignored by the model).

We construct the stop_data dicts matching what generate_tour_text passes to
search_stories_for_stop — which is the PROBLEM: publisher/credit_line/medium
are empty because _new_poi doesn't carry them, and synthesize_queries therefore
can't build targeted collaborator queries.

We test BOTH: (A) with empty fields (current behavior) and (B) with the
credit_line/publisher/medium that the checklist DOES have but never passes.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from work_story_searcher import search_stories_for_stop, synthesize_queries

LOCATION = "Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA"

# The three works as they appear in the exhibition (from LOCAL-418 verification)
# Stop 1 data included for comparison — it already works
WORKS = [
    {
        'canonical_title': 'Le Lézard aux plumes d\'or',
        'english_title': 'The Lizard with Golden Feathers',
        'artist': 'Joan Miró',
        'medium': 'Illustrated book with 40 color lithographs',
        'publisher': 'Louis Broder',
        'credit_line': 'Gift of Boris Fridman. Published by Louis Broder. Printed by Mourlot Frères. 1971.',
        'date': '1971',
    },
    {
        'canonical_title': 'Moses and Monotheism',
        'english_title': 'Moses and Monotheism',
        'artist': 'Salvador Dalí',
        'medium': '',  # Unknown from current extraction
        'publisher': '',  # Unknown — THIS IS THE GAP
        'credit_line': '',  # Unknown — THIS IS THE GAP
        'date': '1974',
    },
    {
        'canonical_title': 'Au Soleil du Plafond',
        'english_title': 'Au Soleil du Plafond',
        'artist': 'Joan Miró',  # Actually Miró illustrated Reverdy's text
        'medium': '',
        'publisher': '',
        'credit_line': '',
        'date': '',
    },
]

print("=" * 72)
print("  SNIPPET DUMP: MFA Unbound — all 3 stops")
print("  Testing: (A) empty fields (current) vs (B) enriched fields (if available)")
print("=" * 72)

all_dump = {}

for idx, work in enumerate(WORKS):
    stop_name = work['canonical_title']

    # (A) Current behavior: empty publisher/credit_line/medium for stops 2,3
    stop_data_current = {
        'canonical_title': stop_name,
        'artist': work['artist'],
        'venue_city': 'Boston',
        'venue_lang': 'en',
        'venue_name': 'Museum of Fine Arts, Boston',
        'publisher': work.get('publisher', ''),
        'credit_line': work.get('credit_line', ''),
        'medium': work.get('medium', ''),
        'english_title': work.get('english_title', stop_name),
    }

    print(f"\n{'─' * 72}")
    print(f"  STOP {idx+1}: {stop_name}")
    print(f"  Artist: {work['artist']}")
    print(f"  Publisher: '{work.get('publisher', '')}' (empty = no targeted queries)")
    print(f"  Credit line: '{work.get('credit_line', '')}' (empty = no targeted queries)")
    print(f"  Medium: '{work.get('medium', '')}'")
    print(f"{'─' * 72}")

    # Show what queries get synthesized with current data
    queries = synthesize_queries(stop_data_current, 'contained')
    print(f"\n  QUERIES SYNTHESIZED ({len(queries)}):")
    for qi, q in enumerate(queries, 1):
        print(f"    Q{qi}: {q}")

    # Run the actual search
    print(f"\n  RUNNING SERP SEARCH...")
    result = search_stories_for_stop(
        stop_data_current, tour_type='contained',
        generation_tier='plus',
    )

    snippets = result.get('results', [])
    cached = result.get('cached_elements', [])
    query_log = result.get('query_log', [])

    print(f"\n  RESULTS: {len(snippets)} snippets, {len(cached)} cached, "
          f"{len(query_log)} queries issued")
    print(f"  Mining status: {result.get('story_mining_status', '?')}")

    # Show query-by-query results
    print(f"\n  QUERY LOG:")
    for ql in query_log:
        print(f"    '{ql['query']}' → {ql['result_count']} results ({ql['latency_ms']}ms)"
              f"{' [REFINED]' if ql.get('refinement') else ''}")

    # Dump ALL snippets
    print(f"\n  ALL SNIPPETS ({len(snippets)}):")
    stop_snippets = []
    for si, snip in enumerate(snippets, 1):
        entry = {
            'index': si,
            'title': snip.get('title', ''),
            'snippet': snip.get('snippet', ''),
            'url': snip.get('url', ''),
            'domain': snip.get('domain', ''),
            'tier': snip.get('tier', ''),
        }
        stop_snippets.append(entry)
        print(f"    [{si:2d}] tier={entry['tier']:6s} {entry['domain'][:30]}")
        print(f"         title: {entry['title'][:100]}")
        print(f"         text:  {entry['snippet'][:250]}")
        print()

    if cached:
        print(f"\n  CACHED ELEMENTS ({len(cached)}):")
        for ci, ce in enumerate(cached, 1):
            print(f"    [C{ci}] type={ce.get('type', '?')}")
            print(f"        text: {ce.get('text', '')[:200]}")
            print()

    all_dump[f"stop_{idx+1}"] = {
        'name': stop_name,
        'artist': work['artist'],
        'stop_data_as_passed': stop_data_current,
        'queries_synthesized': queries,
        'query_log': query_log,
        'snippet_count': len(snippets),
        'snippets': stop_snippets,
        'cached_count': len(cached),
    }

# Save full dump
dump_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "SNIPPET_DUMP_MFA_STOPS_2_3.json")
with open(dump_path, 'w') as f:
    json.dump(all_dump, f, indent=2, ensure_ascii=False)

print(f"\n{'=' * 72}")
print(f"  FULL DUMP SAVED: {dump_path}")
print(f"{'=' * 72}")

# ─── ANALYSIS: Do snippets contain work-specific facts? ───
print(f"\n{'=' * 72}")
print(f"  ANALYSIS: Do the snippets contain work-specific facts?")
print(f"{'=' * 72}")

# Facts we'd WANT for each stop
EXPECTED_FACTS = {
    'stop_2': {
        'name': 'Moses and Monotheism',
        'keywords': ['edition', 'etch', 'aquatint', 'publisher', 'printer',
                     'published', 'printed', 'plates', 'paper', 'signed',
                     'numbered', 'copy', 'copies', 'provenance', 'gift',
                     'donated', 'shorewood', 'broder', 'mourlot', 'reverdy',
                     'freud', '1939', '1974', 'giuseppe', 'albaretto'],
    },
    'stop_3': {
        'name': 'Au Soleil du Plafond',
        'keywords': ['edition', 'lithograph', 'publisher', 'printer',
                     'published', 'printed', 'reverdy', 'pierre reverdy',
                     'tériade', 'mourlot', 'paper', 'signed', 'numbered',
                     'poems', 'text', '1955', 'aimé maeght'],
    },
}

for stop_key, expected in EXPECTED_FACTS.items():
    data = all_dump.get(stop_key, {})
    snips = data.get('snippets', [])
    print(f"\n  {expected['name']} ({len(snips)} snippets):")
    facts_found = []
    generic_count = 0
    for s in snips:
        text = (s.get('snippet', '') + ' ' + s.get('title', '')).lower()
        matched_kw = [kw for kw in expected['keywords'] if kw in text]
        if matched_kw:
            facts_found.append((s['index'], matched_kw, s['snippet'][:120]))
        else:
            generic_count += 1

    print(f"    Snippets with expected-fact keywords: {len(facts_found)}/{len(snips)}")
    print(f"    Snippets with NO fact keywords (generic): {generic_count}/{len(snips)}")
    for idx_f, kws, text in facts_found[:8]:
        print(f"      [{idx_f}] keywords={kws}")
        print(f"          '{text}'")
    if generic_count > 0:
        print(f"\n    SAMPLE GENERIC SNIPPETS (no facts):")
        shown = 0
        for s in snips:
            text = (s.get('snippet', '') + ' ' + s.get('title', '')).lower()
            if not any(kw in text for kw in expected['keywords']):
                print(f"      [{s['index']}] '{s['snippet'][:150]}'")
                shown += 1
                if shown >= 3:
                    break
