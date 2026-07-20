"""Run SQ2 search pilot on host (no extraction — that needs LLM). Saves evidence."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from work_story_searcher import search_stories_for_stop

# Chagall
stop1 = {'canonical_title': 'Le Cantique des Cantiques IV', 'artist': 'Marc Chagall', 'venue_city': 'Nice'}
r1 = search_stories_for_stop(stop1, tour_type='contained', generation_tier='plus')
print(f"Chagall: {r1['total_queries']} queries, {len(r1['results'])} results, status={r1['story_mining_status']}")
for r in r1['results'][:8]:
    print(f"  [{r['tier']}] {r['domain']} - {r['title'][:50]}")

print()

# Matisse
stop2 = {'canonical_title': 'Blue Nude II', 'artist': 'Henri Matisse', 'venue_city': 'Nice'}
r2 = search_stories_for_stop(stop2, tour_type='contained', generation_tier='plus')
print(f"Matisse: {r2['total_queries']} queries, {len(r2['results'])} results, status={r2['story_mining_status']}")
for r in r2['results'][:8]:
    print(f"  [{r['tier']}] {r['domain']} - {r['title'][:50]}")

# Save evidence
evidence = {
    'pilot_date': '2026-07-12',
    'chagall': {'stop': stop1, 'search': r1},
    'matisse': {'stop': stop2, 'search': r2},
}
os.makedirs('tours', exist_ok=True)
with open('tours/sq_pilot_search_evidence.json', 'w') as f:
    json.dump(evidence, f, indent=2, default=str)
print("\nSaved: tours/sq_pilot_search_evidence.json")
