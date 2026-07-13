"""Final pilot targeting acceptance criteria 1+2 at documented level."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from work_story_searcher import search_stories_for_stop
from story_element_extractor import extract_and_score_stop

def run_stop(stop, tour_type='contained', label=''):
    print(f"\n{'='*60}")
    print(f"PILOT: {label} — {stop['canonical_title']}")
    print(f"{'='*60}")
    r = search_stories_for_stop(stop, tour_type=tour_type, generation_tier='plus')
    print(f"Queries: {r['total_queries']}, Results: {len(r['results'])}, Status: {r['story_mining_status']}")
    
    # Check for cache hit
    if 'cached_elements' in r and r['cached_elements']:
        print(f"CACHE HIT: {len(r['cached_elements'])} cached elements returned (zero SERP cost)")
        return r, {'elements': r['cached_elements'], 'extraction_status': 'cache_hit', 'pages_fetched': 0, 'pages_anchored': 0}
    
    t1t2 = [x for x in r['results'] if x['tier'] in ('tier1', 'tier2')]
    print(f"T1/T2: {len(t1t2)}")
    for x in t1t2[:5]:
        print(f"  [{x['tier']}] {x['domain']} - {x['title'][:50]}")
    
    refined = [q for q in r['query_log'] if q.get('refinement')]
    if refined:
        print(f"Refinement: {len(refined)} queries")
    
    print("\n--- Extraction ---")
    ext = extract_and_score_stop(r['results'], stop['canonical_title'], stop['artist'])
    print(f"Fetched: {ext['pages_fetched']}, Anchored: {ext['pages_anchored']}, Status: {ext['extraction_status']}")
    print(f"Elements: {len(ext['elements'])}")
    for e in ext['elements'][:6]:
        print(f"  [{e.get('corroboration_status','?')}] ({e.get('type','?')}): {e.get('text','')[:80]}")
    return r, ext

# --- Matisse: target illness→scissors at documented ---
matisse_stop = {
    'canonical_title': 'Blue Nude II',
    'artist': 'Henri Matisse',
    'venue_city': 'Nice',
    'venue_lang': 'fr',
}
m_search, m_ext = run_stop(matisse_stop, label='Matisse (illness→scissors target)')

# Check for scissors/illness/cancer elements
matisse_target = [e for e in m_ext.get('elements', [])
                  if any(kw in e.get('text', '').lower() for kw in ['scissors', 'cancer', 'illness', 'surgery', 'wheelchair', 'cut-out', 'cutout'])]
print(f"\nMatisse scissors/illness elements: {len(matisse_target)}")
for e in matisse_target:
    print(f"  [{e.get('corroboration_status','?')}] {e.get('text','')[:100]}")

# --- Chagall: target Vava dedication at documented ---
chagall_stop = {
    'canonical_title': 'Song of Songs',
    'artist': 'Marc Chagall',
    'venue_name': 'Musée national Marc Chagall',
    'venue_city': 'Nice',
    'venue_lang': 'fr',
}
c_search, c_ext = run_stop(chagall_stop, label='Chagall (Vava dedication target)')

# Check for Vava/donation/dedication elements
chagall_target = [e for e in c_ext.get('elements', [])
                  if any(kw in e.get('text', '').lower() for kw in ['vava', 'valentina', 'donation', 'dedicated', 'dation'])]
print(f"\nChagall Vava/dedication elements: {len(chagall_target)}")
for e in chagall_target:
    print(f"  [{e.get('corroboration_status','?')}] {e.get('text','')[:100]}")

# Save evidence
evidence = {
    'pilot_date': '2026-07-12',
    'pilot_purpose': 'F4 wiring + target documented status for criteria 1+2',
    'matisse': {
        'stop': matisse_stop,
        'search_summary': {'queries': m_search['total_queries'], 'status': m_search['story_mining_status'], 'results': len(m_search['results'])},
        'extraction_summary': {k: v for k, v in m_ext.items() if k != 'elements' and k != 'fetch_log'},
        'elements': m_ext.get('elements', []),
        'target_elements': matisse_target,
        'criterion_2_met': any(e.get('corroboration_status') == 'documented' for e in matisse_target),
    },
    'chagall': {
        'stop': chagall_stop,
        'search_summary': {'queries': c_search['total_queries'], 'status': c_search['story_mining_status'], 'results': len(c_search['results'])},
        'extraction_summary': {k: v for k, v in c_ext.items() if k != 'elements' and k != 'fetch_log'},
        'elements': c_ext.get('elements', []),
        'target_elements': chagall_target,
        'criterion_1_met': any(e.get('corroboration_status') == 'documented' for e in chagall_target),
    },
}
os.makedirs('tours', exist_ok=True)
with open('tours/sq_pilot_final_f4.json', 'w') as f:
    json.dump(evidence, f, indent=2, default=str)
print(f"\n\n{'='*60}")
print(f"SAVED: tours/sq_pilot_final_f4.json")
print(f"Criterion 1 (Chagall Vava documented): {evidence['chagall']['criterion_1_met']}")
print(f"Criterion 2 (Matisse scissors documented): {evidence['matisse']['criterion_2_met']}")
