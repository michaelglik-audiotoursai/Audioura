"""Post-W1 pilot: fresh run (bypass stale cache) to test Wikipedia API fetch."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Monkey-patch work_stories_get to return None (force fresh mining)
import work_story_searcher
_original_get = work_story_searcher.work_stories_get
work_story_searcher.work_stories_get = lambda *a, **kw: None

from work_story_searcher import search_stories_for_stop
from story_element_extractor import extract_and_score_stop

# Matisse: target illness→scissors
stop = {'canonical_title': 'Blue Nude II', 'artist': 'Henri Matisse', 'venue_city': 'Nice', 'venue_lang': 'fr'}
print("=== Matisse Blue Nude II (W1: Wikipedia API) ===")
r = search_stories_for_stop(stop, tour_type='contained', generation_tier='plus')
print(f"Queries: {r['total_queries']}, Results: {len(r['results'])}, Status: {r['story_mining_status']}")
t1t2 = [x for x in r['results'] if x['tier'] in ('tier1', 'tier2')]
print(f"T1/T2: {len(t1t2)}")

print("\n--- Extraction ---")
ext = extract_and_score_stop(r['results'], 'Blue Nude II', 'Henri Matisse')
print(f"Fetched: {ext['pages_fetched']}, Anchored: {ext['pages_anchored']}, Status: {ext['extraction_status']}")
print(f"Elements: {len(ext['elements'])}")

# Look for scissors/illness/cancer
target = [e for e in ext.get('elements', [])
          if any(kw in e.get('text', '').lower() for kw in ['scissors', 'cancer', 'illness', 'surgery', 'wheelchair', 'cut-out', 'cutout', 'confined'])]
print(f"\nScissors/illness elements: {len(target)}")
for e in target:
    print(f"  [{e.get('corroboration_status','?')}] ({e.get('type','?')}): {e.get('text','')[:100]}")

# Check fetch log for Wikipedia char count
fetch_log = ext.get('fetch_log', [])
wiki_entries = [f for f in fetch_log if 'wikipedia' in f.get('domain', '')]
print(f"\nWikipedia fetch stats: {wiki_entries}")

# Save
evidence = {'stop': stop, 'search': r, 'extraction': ext, 'target_elements': target,
            'criterion_2_met': any(e.get('corroboration_status') == 'documented' for e in target)}
os.makedirs('tours', exist_ok=True)
with open('tours/sq_pilot_w1_matisse.json', 'w') as f:
    json.dump(evidence, f, indent=2, default=str)
print(f"\nCriterion 2 (scissors documented): {evidence['criterion_2_met']}")
print("Saved: tours/sq_pilot_w1_matisse.json")
