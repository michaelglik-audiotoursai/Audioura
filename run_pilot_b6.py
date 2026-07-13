"""B6 Pilot: work_stories live WRITE + cache-HIT READ + elements→generation wiring + i-con delta.

Strategy: Run TWICE on same works.
  - Run 1 (fresh): mines via SERP, proves WRITE (STORED evidence in artifact)
  - Run 2 (warm): proves READ from cache with zero SERP queries
  - Then: generation with per-status element injection + i-con evaluation

Commits both artifacts to tours/ for LEAD review.
"""
import json, sys, os, subprocess, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Capture code_sha at startup
_dev_dir = os.path.dirname(os.path.abspath(__file__))
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

# Load .env
env_path = os.path.join(_dev_dir, '.env')
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

from work_story_searcher import search_stories_for_stop, execute_fact_refinement, normalize_work_key, work_stories_get
from story_element_extractor import extract_and_score_stop, score_corroboration, select_stop_elements

os.makedirs('tours', exist_ok=True)

# --- LOCKED advisory baseline (from remind_Services_ai.md) ---
BASELINE_ICON = {
    'Matisse': 3.81,
    'Uffizi': 3.66,
    'Chagall': 3.99,
    'Chagall_cache_hit': 3.51,
}


def format_elements_for_generation(elements):
    """Format scored elements into per-status generation prompt block (B6 §3 wiring)."""
    selection = select_stop_elements(elements, max_selected=3)
    selected = selection.get('selected_elements', [])
    runners = selection.get('runner_up_elements', [])[:2]

    if not selected:
        return ""

    block = "STORY ELEMENTS (use these as primary material, follow phrasing rules per status):\n"
    for elem in selected:
        status = elem.get('corroboration_status', 'reported')
        text = elem.get('text', '')[:200]
        etype = elem.get('type', '')
        if status == 'documented':
            block += f"  [FACT — state directly, no attribution needed] ({etype}): {text}\n"
        elif status == 'reported':
            src = elem.get('source_domain', 'sources')
            block += f"  [REPORTED — use inline attribution: \"According to {src}...\"] ({etype}): {text}\n"
        elif status == 'legend':
            block += f"  [LEGEND — frame as: \"The story goes that...\"] ({etype}): {text}\n"
        elif status == 'disputed':
            block += f"  [DISPUTED — expose both sides with sources] ({etype}): {text}\n"
        else:
            block += f"  [{status}] ({etype}): {text}\n"
    if runners:
        block += "  TEXTURE (weave in if natural):\n"
        for elem in runners:
            block += f"    ({elem.get('type','')}) {elem.get('text','')[:120]}\n"
    return block


def generate_stop_text_with_elements(stop, elements, api_key):
    """Generate tour text for a single stop using scored elements with per-status phrasing."""
    import openai
    openai.api_key = api_key

    title = stop['canonical_title']
    artist = stop['artist']
    element_block = format_elements_for_generation(elements)

    prompt = f"""You are writing a museum audio tour stop about "{title}" by {artist}.

{element_block}

PHRASING RULES:
- [FACT] elements: State as fact. No attribution needed.
- [REPORTED] elements: Use inline attribution like "According to [source]..." or "It is said that..."
- [LEGEND] elements: Frame as "The story goes that..." or "Legend has it..."
- [DISPUTED] elements: Present both sides with their respective sources.

Write a 200-word engaging audio tour description that incorporates the story elements above.
Start with a brief orientation (where to stand/look), then the narrative.
Be specific and concrete — name colors, dates, people. No clichés.
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  [GEN] Generation error: {e}")
        return f"[Generation failed: {e}]"


def run_fresh_mining(name, stop, target_keywords, criterion_label):
    """Run 1: Fresh mining — proves WRITE (STORED in DB)."""
    print(f"\n{'='*70}")
    print(f"  RUN 1 (FRESH) — {name}")
    print(f"{'='*70}")

    # Force fresh mining: disable cache read for this run
    _original_get = work_story_searcher.work_stories_get
    work_story_searcher.work_stories_get = lambda *a, **kw: None

    # Phase 1: Search
    r = search_stories_for_stop(stop, tour_type='contained', generation_tier='plus')
    print(f"\nSearch: queries={r['total_queries']}, results={len(r['results'])}, status={r['story_mining_status']}")
    t1t2 = [x for x in r['results'] if x['tier'] in ('tier1', 'tier2')]
    print(f"T1/T2 count: {len(t1t2)}")
    for x in t1t2[:5]:
        print(f"  [{x['tier']}] {x['domain']} — {x.get('title', '')[:60]}")

    # Phase 2: Extraction (first round) — this calls work_stories_put internally
    print(f"\n--- First extraction round ---")
    ext = extract_and_score_stop(r['results'], stop['canonical_title'], stop['artist'],
                                 venue_name=stop.get('venue_name', ''))
    print(f"Fetched: {ext['pages_fetched']}, Anchored: {ext['pages_anchored']}, Status: {ext['extraction_status']}")
    print(f"Elements: {len(ext['elements'])}")
    for e in ext.get('elements', []):
        print(f"  [{e.get('corroboration_status','?')}] ({e.get('type','?')}): {e.get('text','')[:80]}")

    # W7: Fact refinement
    frq = ext.get('fact_refinement_queries', [])
    print(f"\nW7 fact_refinement_queries: {len(frq)}")

    w7_new_elements = []
    if frq:
        budget_remaining = 40 - r['total_queries']
        print(f"\n--- W7 fact-targeted refinement (budget_remaining={budget_remaining}) ---")
        ref_result = execute_fact_refinement(
            fact_queries=frq,
            existing_results=r['results'],
            query_budget_remaining=budget_remaining,
        )
        print(f"W7 new results: {len(ref_result['new_results'])}, queries_used: {ref_result['queries_used']}")
        if ref_result['new_results']:
            ext2 = extract_and_score_stop(ref_result['new_results'], stop['canonical_title'], stop['artist'])
            w7_new_elements = ext2.get('elements', [])
            print(f"New elements from W7: {len(w7_new_elements)}")

    # Merge and re-score
    final_elements = ext.get('elements', [])
    if w7_new_elements:
        print(f"\n--- Merge + Re-score ---")
        all_raw = list(ext.get('elements', [])) + list(w7_new_elements)
        final_elements = score_corroboration(all_raw)
        print(f"Merged elements: {len(final_elements)}")

    # Restore original work_stories_get
    work_story_searcher.work_stories_get = _original_get

    # Verify STORED evidence — read back from DB
    _work_key = normalize_work_key(stop['canonical_title'], stop['artist'])
    _stored_check = work_stories_get(_work_key)
    _stored_evidence = None
    if _stored_check:
        _stored_evidence = {
            'work_key': _work_key,
            'elements_count': len(_stored_check.get('elements', [])),
            'status': 'STORED',
        }
        print(f"\n  [work_stories] STORED VERIFIED: {_work_key[:40]} ({_stored_evidence['elements_count']} elements)")
    else:
        _stored_evidence = {'work_key': _work_key, 'status': 'STORE_FAILED'}
        print(f"\n  [work_stories] STORE VERIFICATION FAILED for {_work_key[:40]}")

    # Target elements
    target = [e for e in final_elements
              if any(kw in e.get('text', '').lower() or kw in e.get('source_sentence', '').lower()
                     for kw in target_keywords)]
    criterion_met = any(e.get('corroboration_status') == 'documented' for e in target)
    print(f"\n{criterion_label}: {'TRUE ✅' if criterion_met else 'FALSE ❌'}")

    return {
        'stop': stop,
        'search': {
            'total_queries': r['total_queries'],
            'results_count': len(r['results']),
            'status': r['story_mining_status'],
            't1t2_count': len(t1t2),
            'query_log': r.get('query_log', []),
            'per_query_results': [{'url': x.get('url',''), 'domain': x.get('domain',''),
                                   'tier': x.get('tier',''), 'title': x.get('title','')[:80]}
                                  for x in r['results']],
        },
        'first_extraction': {
            'pages_fetched': ext['pages_fetched'],
            'pages_anchored': ext['pages_anchored'],
            'elements_count': len(ext['elements']),
            'status': ext['extraction_status'],
            'fetch_log': ext.get('fetch_log', []),
        },
        'w7': {'triggered': len(frq) > 0, 'queries': frq, 'new_results': len(w7_new_elements)},
        'final_elements': final_elements,
        'target_elements': target,
        'criterion_met': criterion_met,
        'work_stories_write': _stored_evidence,
    }


def run_warm_cache(name, stop):
    """Run 2: Warm cache — proves READ with zero SERP queries."""
    print(f"\n{'='*70}")
    print(f"  RUN 2 (WARM CACHE) — {name}")
    print(f"{'='*70}")

    # This time, work_stories_get is NOT overridden — cache is live
    r = search_stories_for_stop(stop, tour_type='contained', generation_tier='plus')
    print(f"\nSearch result: status={r['story_mining_status']}, total_queries={r['total_queries']}")
    print(f"Cached elements returned: {len(r.get('cached_elements', []))}")

    cache_hit = (r['story_mining_status'] == 'cache_only' and r['total_queries'] == 0
                 and len(r.get('cached_elements', [])) > 0)
    print(f"\nCache-HIT READ proven: {'YES ✅' if cache_hit else 'NO ❌'}")
    print(f"  story_mining_status: {r['story_mining_status']}")
    print(f"  total_queries: {r['total_queries']}")
    print(f"  cached_elements count: {len(r.get('cached_elements', []))}")

    return {
        'story_mining_status': r['story_mining_status'],
        'total_queries': r['total_queries'],
        'cached_elements_count': len(r.get('cached_elements', [])),
        'cache_hit_proven': cache_hit,
        'cached_elements': r.get('cached_elements', []),
    }


def run_generation_and_icon(name, stop, elements):
    """Run generation with elements + i-con evaluation."""
    print(f"\n{'='*70}")
    print(f"  GENERATION + I-CON — {name}")
    print(f"{'='*70}")

    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        print("  [GEN] No OPENAI_API_KEY — skipping generation")
        return {'generated_text': '[NO API KEY]', 'i_con': None}

    # Generate with elements
    gen_text = generate_stop_text_with_elements(stop, elements, api_key)
    print(f"\n--- Generated text ({len(gen_text)} chars) ---")
    print(gen_text[:500])
    if len(gen_text) > 500:
        print("...")

    # Elements→generation proof: show the element block that was injected
    element_block = format_elements_for_generation(elements)
    print(f"\n--- Element block injected into prompt ---")
    print(element_block[:400])

    # I-CON evaluation
    i_con_result = None
    try:
        from icon_evaluator import evaluate_tour_icon
        # Format as a proper tour that _parse_tour_stops expects: "\nStop N: Title\n..."
        tour_format = f"\nStop 1: {stop['canonical_title']}\n\nOrientation: Position yourself in front of this work.\n\n{gen_text}\n\nDirections: End of tour."
        i_con_result = evaluate_tour_icon(tour_format, story_elements=elements)
        print(f"\n--- I-CON Evaluation ---")
        print(f"  Tour avg: {i_con_result.get('tour_avg', 0)}")
        if i_con_result.get('stops'):
            for s in i_con_result['stops']:
                print(f"  Stop '{s.get('stop_title','')}': i_con={s.get('i_con', 0)}")
    except Exception as e:
        print(f"  [I-CON] Evaluation error: {e}")
        import traceback
        traceback.print_exc()

    return {
        'generated_text': gen_text,
        'element_block_injected': element_block,
        'i_con': i_con_result,
    }


# ============================================================
# EXEMPLARS
# ============================================================

# --- Chagall ---
chagall_stop = {
    'canonical_title': 'Le Cantique des Cantiques IV',
    'local_title': 'Le Cantique des Cantiques IV',
    'english_title': 'Song of Songs IV',
    'artist': 'Marc Chagall',
    'venue_city': 'Nice',
    'venue_lang': 'fr',
    'venue_name': 'Musée national Marc Chagall',
}

# --- Matisse ---
matisse_stop = {
    'canonical_title': 'Blue Nude II',
    'local_title': 'Nu bleu II',
    'english_title': 'Blue Nude II',
    'artist': 'Henri Matisse',
    'venue_city': 'Nice',
    'venue_lang': 'fr',
    'venue_name': 'Musée Matisse Nice',
}

print(f"\n{'#'*70}")
print(f"  B6 PILOT — work_stories WRITE+READ + elements→generation + i-con delta")
print(f"  code_sha: {_code_sha[:7]}{'(dirty)' if _dirty else ''}")
print(f"{'#'*70}")

# ============ RUN 1: FRESH MINING (proves WRITE) ============
matisse_fresh = run_fresh_mining(
    "Matisse — Blue Nude II",
    matisse_stop,
    ['scissors', 'cancer', 'illness', 'surgery', 'wheelchair', 'cut-out', 'cutout', 'cut out', '1952', 'origin', 'nice'],
    "Criterion 2 (Matisse documented)"
)

chagall_fresh = run_fresh_mining(
    "Chagall — Le Cantique des Cantiques IV",
    chagall_stop,
    ['vava', 'donation', 'dedicated', 'valentina', '1966', 'dédicace', 'don'],
    "Criterion 1 (Chagall Vava documented)"
)

# ============ RUN 2: WARM CACHE (proves READ with zero SERP) ============
matisse_warm = run_warm_cache("Matisse — Blue Nude II", matisse_stop)
chagall_warm = run_warm_cache("Chagall — Le Cantique des Cantiques IV", chagall_stop)

# ============ GENERATION + I-CON (proves elements→generation wiring) ============
# Use fresh-mined elements for generation (proves the flow)
matisse_gen = run_generation_and_icon(
    "Matisse", matisse_stop, matisse_fresh['final_elements']
)
chagall_gen = run_generation_and_icon(
    "Chagall", chagall_stop, chagall_fresh['final_elements']
)

# Use cache-hit elements for Chagall (proves cache→generation flow)
chagall_cache_gen = None
if chagall_warm['cache_hit_proven'] and chagall_warm['cached_elements']:
    chagall_cache_gen = run_generation_and_icon(
        "Chagall (cache-hit)", chagall_stop, chagall_warm['cached_elements']
    )

# ============ SUMMARY ============
print(f"\n{'='*70}")
print(f"  B6 PILOT SUMMARY")
print(f"{'='*70}")
print(f"  code_sha: {_code_sha[:7]}{'(dirty)' if _dirty else ''}")
print(f"")
print(f"  --- work_stories WRITE ---")
print(f"  Matisse: {matisse_fresh['work_stories_write'].get('status', '?')} ({matisse_fresh['work_stories_write'].get('elements_count', 0)} elements)")
print(f"  Chagall: {chagall_fresh['work_stories_write'].get('status', '?')} ({chagall_fresh['work_stories_write'].get('elements_count', 0)} elements)")
print(f"")
print(f"  --- work_stories cache-HIT READ (zero SERP) ---")
print(f"  Matisse: cache_hit={matisse_warm['cache_hit_proven']}, queries={matisse_warm['total_queries']}, elements={matisse_warm['cached_elements_count']}")
print(f"  Chagall: cache_hit={chagall_warm['cache_hit_proven']}, queries={chagall_warm['total_queries']}, elements={chagall_warm['cached_elements_count']}")
print(f"")
print(f"  --- elements→generation wiring ---")
print(f"  Matisse: generated={'YES' if matisse_gen.get('generated_text') else 'NO'}, element_block={'YES' if matisse_gen.get('element_block_injected') else 'NO'}")
print(f"  Chagall: generated={'YES' if chagall_gen.get('generated_text') else 'NO'}, element_block={'YES' if chagall_gen.get('element_block_injected') else 'NO'}")
print(f"")
print(f"  --- i-con delta vs LOCKED baseline ---")
_m_icon = matisse_gen.get('i_con', {}).get('tour_avg', 0) if matisse_gen.get('i_con') else 0
_c_icon = chagall_gen.get('i_con', {}).get('tour_avg', 0) if chagall_gen.get('i_con') else 0
_cc_icon = chagall_cache_gen.get('i_con', {}).get('tour_avg', 0) if chagall_cache_gen and chagall_cache_gen.get('i_con') else 0
print(f"  Matisse:           i_con={_m_icon:.2f} (baseline: {BASELINE_ICON['Matisse']})")
print(f"  Chagall:           i_con={_c_icon:.2f} (baseline: {BASELINE_ICON['Chagall']})")
print(f"  Chagall cache-hit: i_con={_cc_icon:.2f} (baseline: {BASELINE_ICON['Chagall_cache_hit']})")
print(f"{'='*70}")

# ============ SAVE ARTIFACT ============
evidence = {
    'code_sha': _code_sha,
    'code_dirty': _dirty,
    'commit': _code_sha[:7],
    'deliverables': ['B6_work_stories_WRITE', 'B6_work_stories_READ', 'B6_elements_generation_wiring', 'B6_icon_delta'],
    'matisse_fresh': {
        'search': matisse_fresh['search'],
        'first_extraction': matisse_fresh['first_extraction'],
        'w7': matisse_fresh['w7'],
        'final_elements': matisse_fresh['final_elements'],
        'criterion_met': matisse_fresh['criterion_met'],
        'work_stories_write': matisse_fresh['work_stories_write'],
    },
    'chagall_fresh': {
        'search': chagall_fresh['search'],
        'first_extraction': chagall_fresh['first_extraction'],
        'w7': chagall_fresh['w7'],
        'final_elements': chagall_fresh['final_elements'],
        'criterion_met': chagall_fresh['criterion_met'],
        'work_stories_write': chagall_fresh['work_stories_write'],
    },
    'matisse_warm_cache': matisse_warm,
    'chagall_warm_cache': chagall_warm,
    'generation': {
        'matisse': {
            'generated_text': matisse_gen.get('generated_text', ''),
            'element_block_injected': matisse_gen.get('element_block_injected', ''),
            'i_con': matisse_gen.get('i_con'),
        },
        'chagall': {
            'generated_text': chagall_gen.get('generated_text', ''),
            'element_block_injected': chagall_gen.get('element_block_injected', ''),
            'i_con': chagall_gen.get('i_con'),
        },
        'chagall_cache_hit': {
            'generated_text': chagall_cache_gen.get('generated_text', '') if chagall_cache_gen else '',
            'element_block_injected': chagall_cache_gen.get('element_block_injected', '') if chagall_cache_gen else '',
            'i_con': chagall_cache_gen.get('i_con') if chagall_cache_gen else None,
        },
    },
    'stop_metrics_icon': {
        'matisse': {'i_con': _m_icon, 'baseline': BASELINE_ICON['Matisse']},
        'chagall': {'i_con': _c_icon, 'baseline': BASELINE_ICON['Chagall']},
        'chagall_cache_hit': {'i_con': _cc_icon, 'baseline': BASELINE_ICON['Chagall_cache_hit']},
    },
}

with open('tours/sq_pilot_b6.json', 'w') as f:
    json.dump(evidence, f, indent=2, default=str)
print(f"\nSaved: tours/sq_pilot_b6.json")
