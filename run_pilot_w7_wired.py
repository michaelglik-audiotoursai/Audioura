"""Post-W7-wiring pilot: exercises the full fact-targeted refinement flow.

Search → Extract → W7 triggers → execute_fact_refinement → re-extract new pages → merge → re-score.
Commits artifacts to tours/ for LEAD review.
"""
import json, sys, os, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Capture code_sha at startup (before any imports that might change cwd)
_dev_dir = os.path.dirname(os.path.abspath(__file__))
# In Docker, git may not be available — accept CODE_SHA env var as fallback
_code_sha = os.environ.get('CODE_SHA', '')
_dirty = os.environ.get('CODE_DIRTY', '') == 'true'
if not _code_sha:
    try:
        _code_sha = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=_dev_dir
        ).decode().strip()
        _dirty = bool(subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=_dev_dir
        ).decode().strip())
    except Exception:
        _code_sha = 'unknown'
        _dirty = True

# Load .env before importing modules
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

import work_story_searcher
work_story_searcher.SERP_API_KEY = os.environ.get('SERP_API_KEY', '')
work_story_searcher.OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
work_story_searcher.work_stories_get = lambda *a, **kw: None  # Force fresh mining

from work_story_searcher import search_stories_for_stop, execute_fact_refinement
from story_element_extractor import extract_and_score_stop, score_corroboration

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
    for x in t1t2[:5]:
        print(f"  [{x['tier']}] {x['domain']} — {x.get('title', '')[:60]}")

    # Phase 2: Extraction (first round)
    print(f"\n--- First extraction round ---")
    ext = extract_and_score_stop(r['results'], stop['canonical_title'], stop['artist'])
    print(f"Fetched: {ext['pages_fetched']}, Anchored: {ext['pages_anchored']}, Status: {ext['extraction_status']}")
    print(f"Elements: {len(ext['elements'])}")
    for e in ext.get('elements', []):
        print(f"  [{e.get('corroboration_status','?')}] ({e.get('type','?')}): {e.get('text','')[:80]}")

    # W7: Check if fact refinement triggered
    frq = ext.get('fact_refinement_queries', [])
    print(f"\nW7 fact_refinement_queries: {len(frq)}")
    for q in frq:
        print(f"  → {q}")

    # Phase 3: W7 wiring — execute fact-targeted queries if available
    w7_new_elements = []
    w7_log = []
    w7_fetch_log = []
    if frq:
        budget_remaining = 40 - r['total_queries']  # Plus tier budget minus already used
        print(f"\n--- W7 fact-targeted refinement (budget_remaining={budget_remaining}) ---")
        ref_result = execute_fact_refinement(
            fact_queries=frq,
            existing_results=r['results'],
            query_budget_remaining=budget_remaining,
        )
        print(f"W7 new results: {len(ref_result['new_results'])}, queries_used: {ref_result['queries_used']}")
        w7_log = ref_result['query_log']
        for x in ref_result['new_results'][:5]:
            print(f"  [{x.get('tier','?')}] {x.get('domain','')} — {x.get('title','')[:60]}")

        # Re-extract from new results only
        if ref_result['new_results']:
            print(f"\n--- W7 second extraction round ---")
            ext2 = extract_and_score_stop(ref_result['new_results'], stop['canonical_title'], stop['artist'])
            print(f"Fetched: {ext2['pages_fetched']}, Anchored: {ext2['pages_anchored']}")
            w7_new_elements = ext2.get('elements', [])
            w7_fetch_log = ext2.get('fetch_log', [])
            print(f"New elements from W7: {len(w7_new_elements)}")
            for e in w7_new_elements:
                print(f"  [{e.get('corroboration_status','?')}] ({e.get('type','?')}): {e.get('text','')[:80]}")

    # Phase 4: Merge and re-score if W7 produced new elements
    final_elements = ext.get('elements', [])
    if w7_new_elements:
        print(f"\n--- Merge + Re-score ---")
        # Collect raw elements (pre-scoring) from both rounds for re-scoring
        all_raw = []
        for e in ext.get('elements', []):
            # Keep source info for re-scoring
            all_raw.append(e)
        for e in w7_new_elements:
            all_raw.append(e)
        final_elements = score_corroboration(all_raw)
        print(f"Merged elements: {len(final_elements)}")
        for e in final_elements:
            print(f"  [{e.get('corroboration_status','?')}] ({e.get('type','?')}): {e.get('text','')[:80]}")

    # Target elements
    target = [e for e in final_elements
              if any(kw in e.get('text', '').lower() or kw in e.get('source_sentence', '').lower()
                     for kw in target_keywords)]
    print(f"\nTarget elements ({criterion_label}): {len(target)}")
    for e in target:
        print(f"  [{e.get('corroboration_status','?')}] ({e.get('type','?')}): {e.get('text','')[:120]}")

    criterion_met = any(e.get('corroboration_status') == 'documented' for e in target)
    print(f"\n{criterion_label}: {'TRUE ✅' if criterion_met else 'FALSE ❌'}")

    return {
        'stop': stop,
        'search': {'total_queries': r['total_queries'], 'results_count': len(r['results']),
                   'status': r['story_mining_status'], 't1t2_count': len(t1t2),
                   'query_log': r.get('query_log', []),
                   'per_query_results': [{'url': x.get('url',''), 'domain': x.get('domain',''),
                                          'tier': x.get('tier',''), 'title': x.get('title','')[:80]}
                                         for x in r['results']]},
        'first_extraction': {'pages_fetched': ext['pages_fetched'], 'pages_anchored': ext['pages_anchored'],
                            'elements_count': len(ext['elements']), 'status': ext['extraction_status'],
                            'fetch_log': ext.get('fetch_log', [])},
        'w7': {'triggered': len(frq) > 0, 'queries': frq, 'new_results': len(w7_new_elements),
               'query_log': w7_log,
               'fetch_log': w7_fetch_log},
        'final_elements': final_elements,
        'target_elements': target,
        'criterion_met': criterion_met,
    }


# --- Chagall ---
chagall_stop = {
    'canonical_title': 'Le Cantique des Cantiques IV',
    'local_title': 'Le Cantique des Cantiques IV',  # French venue: local = canonical
    'english_title': 'Song of Songs IV',  # Q3: English label from Wikidata
    'artist': 'Marc Chagall',
    'venue_city': 'Nice',
    'venue_lang': 'fr',
}
chagall_result = run_exemplar(
    "Chagall — Le Cantique des Cantiques IV (W7 wired)",
    chagall_stop,
    ['vava', 'donation', 'dedicated', 'valentina', '1966', 'dédicace', 'don'],
    "Criterion 1 (Vava dedication documented)"
)

# --- Matisse ---
matisse_stop = {
    'canonical_title': 'Blue Nude II',
    'local_title': 'Nu bleu II',
    'english_title': 'Blue Nude II',  # Q3: same as canonical (English work)
    'artist': 'Henri Matisse',
    'venue_city': 'Nice',
    'venue_lang': 'fr',
}
matisse_result = run_exemplar(
    "Matisse — Blue Nude II (W7 wired)",
    matisse_stop,
    ['scissors', 'cancer', 'illness', 'surgery', 'wheelchair', 'cut-out', 'cutout', 'confined', 'cut out'],
    "Criterion 2 (scissors/illness documented)"
)

# --- Summary + Save ---
print(f"\n{'='*70}")
print(f"  PILOT SUMMARY (Q1+Q3+code_sha — {_code_sha[:7]}{'+dirty' if _dirty else ''})")
print(f"{'='*70}")
print(f"  Criterion 1 (Chagall Vava): {chagall_result['criterion_met']}")
print(f"  Criterion 2 (Matisse scissors): {matisse_result['criterion_met']}")
print(f"{'='*70}")

evidence = {
    'code_sha': _code_sha,
    'code_dirty': _dirty,
    'commit': _code_sha[:7],
    'fixes': ['Q1_person_picker_skip_artist', 'Q3_english_title_query', 'code_sha_field'],
    'chagall': chagall_result,
    'matisse': matisse_result,
}
with open('tours/sq_pilot_w7_wired.json', 'w') as f:
    json.dump(evidence, f, indent=2, default=str)
print("Saved: tours/sq_pilot_w7_wired.json")
