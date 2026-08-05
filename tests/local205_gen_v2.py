#!/usr/bin/env python3
"""LOCAL-205 v2: Generate on Musée Matisse with forced COVERED stops.

Patches canonical_titles in-memory to contain only the 6 stop_corpus entries
that assess_stop_coverage marks as COVERED. The LLM spine selector can then
only pick from those.

Usage (from host):
    docker exec -e DATABASE_URL= -e STORIED_MODE=true \
        -e TOUR_LLM_MODEL=gpt-3.5-turbo \
        audioura-tour-generator-1 python3 /app/tests/local205_gen_v2.py A 1

Outputs RESULT_JSON and TOUR_TEXT_START/TOUR_TEXT_END markers for parsing.
"""
import os
import sys
import json
import time

# Force cache bypass
if 'DATABASE_URL' in os.environ:
    del os.environ['DATABASE_URL']

os.environ['STORIED_MODE'] = 'true'

# The 6 COVERED stop_corpus entries for Musée Matisse
COVERED_STOPS = {
    'Lectrice à la table jaune',
    'Nature morte aux grenades',
    'Nymphe dans la forêt',
    'Odalisque au coffret rouge',
    'Papeete-Tahiti',
    'Tempête à Nice',
}


def patch_canonical_titles():
    """Monkey-patch generate_tour_text to restrict canonical_titles to COVERED set.

    We intercept at the spine_generator's call site by patching the module-level
    canonical_titles after they're computed but before the LLM selects stops.
    
    Strategy: patch the filter_corpus_titles return to only include COVERED works.
    """
    import story_miner
    _original_filter = story_miner.filter_corpus_titles

    def _patched_filter(*args, **kwargs):
        result = _original_filter(*args, **kwargs)
        # Restrict 'works' to only COVERED stops
        original_works = result['works']
        filtered = {t for t in original_works if t in COVERED_STOPS}
        if not filtered:
            # Fuzzy match — some titles may differ slightly
            for t in original_works:
                for cs in COVERED_STOPS:
                    if cs.lower() in t.lower() or t.lower() in cs.lower():
                        filtered.add(t)
        print(f"  [LOCAL-205] Restricted canonical_titles: {len(original_works)} → {len(filtered)}")
        print(f"  [LOCAL-205] Available: {sorted(filtered)}")
        result['works'] = filtered
        return result

    story_miner.filter_corpus_titles = _patched_filter


def main():
    arm = sys.argv[1]  # 'A' or 'B'
    run_num = sys.argv[2]  # '1', '2', '3'

    model = os.environ.get('TOUR_LLM_MODEL', 'gpt-3.5-turbo')
    print(f"=== LOCAL-205 v2: Arm {arm}, Run {run_num}, Model: {model} ===")
    print(f"DATABASE_URL set: {'DATABASE_URL' in os.environ}")
    print(f"STORIED_MODE: {os.environ.get('STORIED_MODE')}")
    print(f"TOUR_LLM_MODEL: {model}")
    print(f"COVERED_STOPS: {sorted(COVERED_STOPS)}")

    # Patch before import
    patch_canonical_titles()

    from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST

    start = time.time()

    tour_text, output_file, coordinates = generate_tour_text(
        location="Musée Matisse, Nice, France",
        tour_type="museum",
        output_file=f"/tmp/local205v2_arm{arm}_run{run_num}.txt",
        total_stops=2,
        persona=None,
    )

    elapsed = time.time() - start

    cost_info = _LAST_GENERATION_COST.copy()

    result = {
        "arm": arm,
        "run": int(run_num),
        "model": model,
        "elapsed_seconds": round(elapsed, 1),
        "cost_info": cost_info,
        "tour_text_length": len(tour_text) if tour_text else 0,
        "success": tour_text is not None,
    }

    print(f"\n{'='*60}")
    print(f"RESULT_JSON: {json.dumps(result)}")
    print(f"{'='*60}")

    if tour_text:
        print(f"\nTOUR_TEXT_START")
        print(tour_text)
        print(f"TOUR_TEXT_END")
    else:
        print("ERROR: No tour text generated!")
        sys.exit(1)


if __name__ == '__main__':
    main()
