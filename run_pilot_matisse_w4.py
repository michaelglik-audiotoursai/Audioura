"""Quick Matisse pilot for W4-W7 fixes."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load env vars from .env BEFORE importing modules that read them at module level
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

import work_story_searcher
# Force-patch module globals in case they were read before env was loaded
work_story_searcher.SERP_API_KEY = os.environ.get('SERP_API_KEY', '')
work_story_searcher.OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
work_story_searcher.work_stories_get = lambda *a, **kw: None

from work_story_searcher import search_stories_for_stop
from story_element_extractor import extract_and_score_stop

stop = {'canonical_title': 'Blue Nude II', 'local_title': 'Nu bleu II',
        'artist': 'Henri Matisse', 'venue_city': 'Nice', 'venue_lang': 'fr'}

print("=== Matisse Blue Nude II (W4-W7 pilot) ===")
r = search_stories_for_stop(stop, tour_type='contained', generation_tier='plus')
print(f"Queries: {r['total_queries']}, Results: {len(r['results'])}, Status: {r['story_mining_status']}")

t1t2 = [x for x in r['results'] if x['tier'] in ('tier1', 'tier2')]
print(f"T1/T2: {len(t1t2)}")
for x in t1t2[:8]:
    print(f"  [{x['tier']}] {x['domain']} — {x.get('title','')[:60]}")

all_urls = [x['url'] for x in r['results']]
unique_urls = set(all_urls)
print(f"\nURL stats: {len(all_urls)} total, {len(unique_urls)} unique")

print("\n--- Extraction ---")
ext = extract_and_score_stop(r['results'], 'Blue Nude II', 'Henri Matisse')
print(f"Fetched: {ext['pages_fetched']}, Anchored: {ext['pages_anchored']}, Status: {ext['extraction_status']}")
print(f"Elements: {len(ext['elements'])}")

for f in ext.get('fetch_log', []):
    print(f"  [{f.get('tier','')}] {f.get('domain','')} — fetched={f.get('fetched')}, chars={f.get('chars',0)}")

print("\nAll elements:")
for e in ext.get('elements', []):
    print(f"  [{e.get('corroboration_status','?')}] ({e.get('type','?')}): {e.get('text','')[:100]}")

target_kw = ['scissors', 'cancer', 'illness', 'surgery', 'cut-out', 'cutout', 'confined', 'wheelchair']
target = [e for e in ext.get('elements', [])
          if any(kw in e.get('text', '').lower() or kw in e.get('source_sentence', '').lower() for kw in target_kw)]
print(f"\nCriterion 2 target elements: {len(target)}")
for e in target:
    print(f"  [{e.get('corroboration_status')}] ({e.get('type')}): {e.get('text','')[:120]}")

criterion_met = any(e.get('corroboration_status') == 'documented' for e in target)
print(f"\nCriterion 2 MET: {criterion_met}")
