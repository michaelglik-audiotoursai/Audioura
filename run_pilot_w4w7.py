"""Post-W4/W5/W6/W7/URL-dedup pilot: re-run BOTH exemplars (Chagall + Matisse).

Expected outcomes per LEAD directive:
- Chagall: Vava dedication → 'documented' via francetoday.com + museedevence.fr (+ museum third)
- Matisse: scissors/illness → 'documented' via MoMA Cut-Outs/Tate (once dup slots freed)
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Monkey-patch work_stories_get to return None (force fresh mining, bypass stale cache)
import work_story_searcher
work_story_searcher.work_stories_get = lambda *a, **kw: None

from work_story_searcher import search_stories_for_stop, synthesize_fact_targeted_queries
from story_element_extractor import extract_and_score_stop

os.makedirs('tours', exist_ok=True)


def run_exemplar(name, stop, target_keywords, criterion_label):
    print(f"\n{'='*70}")
    print(f"  {name}")
    print(f"{'='*70}")

    # Phase 1: Search
    r = search_stories_for_stop(stop, tour_type='contained', generation_tier='plus')
    print(f"\nSearch: queries={r['total_queries']}, results={len(r['results'])}, status={r['story_mining_status']}")
    t1t2 = [x for x in r['results'] if x['tier'] in ('tier1', 'tier2')]
    print(f"T1/T2 count: {len(t1t2)}")
    for x in t1t2[:8]:
        print(f"  [{x['tier']}] {x['domain']} — {x.get('title', '')[:60]}")

    # URL dedup check
    all_urls = [x['url'] for x in r['results']]
    unique_urls = set(all_urls)
    print(f"\nURL stats: {len(all_urls)} total results, {len(unique_urls)} unique URLs")
    if len(all_urls) != len(unique_urls):
        print(f"  WARNING: {len(all_urls) - len(unique_urls)} duplicate URLs in results (will be deduped in extraction)")

    # Phase 2: Extraction
    print(f"\n--- Extraction ---")
    ext = extract_and_score_stop(r['results'], stop['canonical_title'], stop['artist'])
    print(f"Fetched: {ext['pages_fetched']}, Anchored: {ext['pages_anchored']}, Status: {ext['extraction_status']}")
    print(f"Elements: {len(ext['elements'])}")

    # Fetch log
    for f in ext.get('fetch_log', []):
        print(f"  [{f.get('tier','')}] {f.get('domain','')} — fetched={f.get('fetched')}, chars={f.get('chars',0)}")

    # Target elements
    target = [e for e in ext.get('elements', [])
              if any(kw in e.get('text', '').lower() or kw in e.get('source_sentence', '').lower()
                     for kw in target_keywords)]
    print(f"\nTarget elements ({criterion_label}): {len(target)}")
    for e in target:
        print(f"  [{e.get('corroboration_status','?')}] ({e.get('type','?')}): {e.get('text','')[:120]}")

    # All elements summary
    print(f"\nAll elements:")
    for e in ext.get('elements', []):
        print(f"  [{e.get('corroboration_status','?')}] ({e.get('type','?')}): {e.get('text','')[:100]}")

    # W7: Check if fact-targeted refinement would trigger
    reported_hv = [e for e in ext.get('elements', [])
                   if e.get('corroboration_status') == 'reported'
                   and e.get('type') in ('dedication', 'origin', 'turning_point')]
    if reported_hv:
        fact_queries = synthesize_fact_targeted_queries(stop, reported_hv)
        print(f"\nW7 refinement would produce {len(fact_queries)} fact-targeted queries:")
        for q in fact_queries:
            print(f"  → {q}")

    criterion_met = any(e.get('corroboration_status') == 'documented' for e in target)
    print(f"\n{criterion_label}: {'TRUE ✅' if criterion_met else 'FALSE ❌'}")

    return {
        'stop': stop,
        'search': r,
        'extraction': ext,
        'target_elements': target,
        'criterion_met': criterion_met,
        'w7_reported_hv': [{'type': e['type'], 'text': e['text']} for e in reported_hv] if reported_hv else [],
    }


# --- Chagall: Vava dedication ---
chagall_stop = {
    'canonical_title': 'Le Cantique des Cantiques IV',
    'local_title': 'Song of Songs IV',
    'artist': 'Marc Chagall',
    'venue_city': 'Nice',
    'venue_lang': 'fr',
}
chagall_keywords = ['vava', 'donation', 'dedicated', 'valentina', '1966', 'dédicace', 'don']
chagall_result = run_exemplar(
    "Chagall — Le Cantique des Cantiques IV (Vava dedication)",
    chagall_stop, chagall_keywords,
    "Criterion 1 (Vava dedication documented)"
)

# --- Matisse: scissors/illness ---
matisse_stop = {
    'canonical_title': 'Blue Nude II',
    'local_title': 'Nu bleu II',
    'artist': 'Henri Matisse',
    'venue_city': 'Nice',
    'venue_lang': 'fr',
}
matisse_keywords = ['scissors', 'cancer', 'illness', 'surgery', 'wheelchair', 'cut-out', 'cutout', 'confined', 'cut out']
matisse_result = run_exemplar(
    "Matisse — Blue Nude II (scissors/illness)",
    matisse_stop, matisse_keywords,
    "Criterion 2 (scissors/illness documented)"
)

# --- Summary ---
print(f"\n{'='*70}")
print(f"  PILOT SUMMARY (W4+W5+W6+W7+URL dedup)")
print(f"{'='*70}")
print(f"  Criterion 1 (Chagall Vava): {chagall_result['criterion_met']}")
print(f"  Criterion 2 (Matisse scissors): {matisse_result['criterion_met']}")
print(f"{'='*70}")

# Save evidence
evidence = {
    'commit': 'e5a4f96',
    'fixes': ['W4_query_granularity', 'W5_title_language_split', 'W6_tier_typo', 'W7_fact_refinement', 'URL_dedup'],
    'chagall': chagall_result,
    'matisse': matisse_result,
}
with open('tours/sq_pilot_w4w7.json', 'w') as f:
    json.dump(evidence, f, indent=2, default=str)
print("Saved: tours/sq_pilot_w4w7.json")
