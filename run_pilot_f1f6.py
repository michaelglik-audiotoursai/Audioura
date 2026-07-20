"""Run the post-F1-F6 pilot for Matisse Blue Nude II."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from work_story_searcher import search_stories_for_stop
from story_element_extractor import extract_and_score_stop

stop = {'canonical_title': 'Blue Nude II', 'artist': 'Henri Matisse', 'venue_city': 'Nice', 'venue_lang': 'fr'}
r = search_stories_for_stop(stop, tour_type='contained', generation_tier='plus')
print(f"Queries: {r['total_queries']}, Results: {len(r['results'])}, Status: {r['story_mining_status']}")
t1t2 = [x for x in r['results'] if x['tier'] in ('tier1', 'tier2')]
print(f"T1/T2 count: {len(t1t2)}")
for x in t1t2[:5]:
    print(f"  [{x['tier']}] {x['domain']} - {x['title'][:50]}")

print("\n--- Extraction ---")
ext = extract_and_score_stop(r['results'], 'Blue Nude II', 'Henri Matisse')
print(f"Fetched: {ext['pages_fetched']}, Anchored: {ext['pages_anchored']}, Status: {ext['extraction_status']}")
print(f"Elements: {len(ext['elements'])}")
for e in ext['elements'][:5]:
    print(f"  [{e.get('corroboration_status','?')}] ({e.get('type','?')}): {e.get('text','')[:80]}")

evidence = {'stop': stop, 'search': r, 'extraction_meta': {k:v for k,v in ext.items() if k!='elements'}, 'elements': ext['elements']}
os.makedirs('tours', exist_ok=True)
with open('tours/sq_pilot_matisse_f1f6.json', 'w') as f:
    json.dump(evidence, f, indent=2, default=str)
print("\nSaved: tours/sq_pilot_matisse_f1f6.json")
