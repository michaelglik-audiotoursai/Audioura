"""test_sq3_fixtures.py — SQ3 deterministic fixtures.

Tests character-shingle Jaccard syndication detection, work-anchor check,
claim normalization, and corroboration scoring logic. All deterministic — no network/LLM calls.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from story_element_extractor import (
    jaccard_similarity, check_work_anchor, _normalize_claim_key,
    score_corroboration, _char_shingles,
)


def run_tests() -> bool:
    all_passed = True

    # --- Character-shingle Jaccard (R3) ---
    print("  Syndication Detection (character-shingle Jaccard, R3):")
    
    # Known syndicated pair: near-identical text from different domains
    syndicated_a = "In 1941, Matisse was diagnosed with abdominal cancer and after surgery was confined to a wheelchair, leading him to develop his revolutionary cut-out technique."
    syndicated_b = "In 1941, Matisse was diagnosed with abdominal cancer and after surgery was confined to a wheelchair, leading him to develop his revolutionary cut-out technique using painted paper."
    sim = jaccard_similarity(syndicated_a, syndicated_b)
    passed = sim >= 0.85
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] Syndicated pair: Jaccard={sim:.3f} (expected ≥0.85)")
    if not passed:
        all_passed = False
    
    # Independent sources: same fact, different wording
    independent_a = "After a cancer diagnosis in 1941, Matisse turned to scissors and paper as his primary artistic medium."
    independent_b = "The cut-outs began after Matisse's surgery for duodenal cancer left him largely bedridden in 1941."
    sim2 = jaccard_similarity(independent_a, independent_b)
    passed = sim2 < 0.85
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] Independent pair: Jaccard={sim2:.3f} (expected <0.85)")
    if not passed:
        all_passed = False
    
    # Completely unrelated
    unrelated_a = "The painting depicts a vibrant blue nude against a white background."
    unrelated_b = "Construction of the Promenade des Anglais began in 1820."
    sim3 = jaccard_similarity(unrelated_a, unrelated_b)
    passed = sim3 < 0.3
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] Unrelated pair: Jaccard={sim3:.3f} (expected <0.3)")
    if not passed:
        all_passed = False

    # --- Work-anchor check ---
    print("\n  Work-Anchor Check:")
    
    page_about_song = "The Song of Songs cycle by Chagall represents his love for Vava. These five canvases were painted between 1957 and 1966."
    passed = check_work_anchor(page_about_song, "Song of Songs IV")
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] Page about 'Song of Songs' anchors to 'Song of Songs IV': {passed}")
    if not passed:
        all_passed = False
    
    # Artist-generic page (no work mention)
    generic_page = "Marc Chagall was born in Vitebsk in 1887. He studied art in Paris and became famous for his colorful dreamlike paintings."
    passed = not check_work_anchor(generic_page, "Song of Songs IV")
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] Artist-generic page does NOT anchor to 'Song of Songs IV': {passed}")
    if not passed:
        all_passed = False
    
    # French title
    french_page = "Le Cantique des Cantiques est une oeuvre majeure de Chagall, peinte entre 1957 et 1966."
    passed = check_work_anchor(french_page, "Le Cantique des Cantiques I")
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] French page anchors to 'Le Cantique des Cantiques I': {passed}")
    if not passed:
        all_passed = False

    # --- Claim normalization ---
    print("\n  Claim Normalization:")
    
    norm_fixtures = [
        ("Matisse developed cut-outs in 1941 after surgery.", "matisse developed cutouts in after surgery"),
        ("The painting was completed in 1957.", "the painting was completed in"),
        ("Chagall's LOVE for Vava inspired the work!", "chagalls love for vava inspired the work"),
    ]
    for original, expected in norm_fixtures:
        result = _normalize_claim_key(original)
        passed = result == expected
        status = "PASS" if passed else "FAIL"
        print(f"    [{status}] '{original[:40]}...' → '{result}' (expected '{expected}')")
        if not passed:
            all_passed = False

    # --- Corroboration scoring ---
    print("\n  Corroboration Scoring:")
    
    # Two independent sources → documented
    elements_documented = [
        {'text': 'Matisse developed cut-outs after cancer surgery', 'type': 'turning_point',
         'source_sentence': 'After a cancer diagnosis in 1941, Matisse turned to scissors.',
         'source_url': 'https://tate.org.uk/matisse', 'source_domain': 'tate.org.uk'},
        {'text': 'Matisse developed cut-outs after cancer surgery', 'type': 'turning_point',
         'source_sentence': 'The cut-outs began after his surgery for duodenal cancer.',
         'source_url': 'https://moma.org/matisse-cutouts', 'source_domain': 'moma.org'},
    ]
    scored = score_corroboration(elements_documented)
    passed = len(scored) == 1 and scored[0].get('corroboration_status') == 'documented'
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] 2 independent sources → 'documented': {scored[0].get('corroboration_status') if scored else 'none'}")
    if not passed:
        all_passed = False
    
    # Single source → reported
    elements_reported = [
        {'text': 'Chagall dedicated the cycle to Vava', 'type': 'dedication',
         'source_sentence': 'He dedicated the Song of Songs to his wife Vava.',
         'source_url': 'https://france-today.com/chagall', 'source_domain': 'france-today.com'},
    ]
    scored2 = score_corroboration(elements_reported)
    passed = len(scored2) == 1 and scored2[0].get('corroboration_status') == 'reported'
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] 1 source → 'reported': {scored2[0].get('corroboration_status') if scored2 else 'none'}")
    if not passed:
        all_passed = False
    
    # Syndicated sources (near-identical text) → counts as ONE, reported
    elements_syndicated = [
        {'text': 'The work was painted in Nice', 'type': 'origin',
         'source_sentence': 'Chagall painted the Song of Songs cycle in his studio in Nice between 1957 and 1966.',
         'source_url': 'https://wikiwand.com/chagall', 'source_domain': 'wikiwand.com'},
        {'text': 'The work was painted in Nice', 'type': 'origin',
         'source_sentence': 'Chagall painted the Song of Songs cycle in his studio in Nice between 1957 and 1966.',
         'source_url': 'https://wiki2.org/chagall', 'source_domain': 'wiki2.org'},
    ]
    scored3 = score_corroboration(elements_syndicated)
    passed = len(scored3) == 1 and scored3[0].get('corroboration_status') == 'reported'
    status = "PASS" if passed else "FAIL"
    n_indep = scored3[0].get('independent_source_count', 0) if scored3 else 0
    print(f"    [{status}] 2 syndicated sources → 'reported' (1 independent): indep={n_indep}")
    if not passed:
        all_passed = False
    
    # Legend type → always 'legend'
    elements_legend = [
        {'text': 'Legend says the painting brings luck', 'type': 'legend',
         'source_sentence': 'According to local legend, the painting brings good fortune.',
         'source_url': 'https://example.com/a', 'source_domain': 'example.com'},
        {'text': 'Legend says the painting brings luck', 'type': 'legend',
         'source_sentence': 'Legend has it that the painting was believed to bring luck.',
         'source_url': 'https://other.com/b', 'source_domain': 'other.com'},
    ]
    scored4 = score_corroboration(elements_legend)
    passed = len(scored4) == 1 and scored4[0].get('corroboration_status') == 'legend'
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] Legend-typed elements → 'legend' regardless of source count: {scored4[0].get('corroboration_status') if scored4 else 'none'}")
    if not passed:
        all_passed = False

    # --- W2: Artist-token anchor for contained tours ---
    print("\n  W2: Artist-Token Anchor (Contained Tours):")

    # W2: Bible article should NOT anchor to Chagall painting
    bible_page = "The Song of Songs, also called the Song of Solomon, is a biblical poem about love between a man and a woman. It is part of the Hebrew Bible."
    passed = not check_work_anchor(bible_page, "Song of Songs", artist="Marc Chagall")
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] W2: Bible article without Chagall → NOT anchored (artist token required)")
    if not passed:
        all_passed = False

    # --- W3: Legend phrase detection ---
    print("\n  W3: Legend Phrase Detection:")

    # W3: "Legend has it" forces legend status regardless of LLM type
    elements_legend_phrase = [
        {'text': 'Work was created in a single cut', 'type': 'technique',
         'source_sentence': 'Legend has it that the work was created in a single, fluid cut of the scissors.',
         'source_url': 'https://museum.org/a', 'source_domain': 'museum.org'},
    ]
    scored_w3 = score_corroboration(elements_legend_phrase)
    passed = len(scored_w3) == 1 and scored_w3[0].get('corroboration_status') == 'legend'
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] W3: 'Legend has it' in source_sentence → forces 'legend' status: {scored_w3[0].get('corroboration_status') if scored_w3 else 'none'}")
    if not passed:
        all_passed = False

    return all_passed


if __name__ == "__main__":
    print("=" * 70)
    print("SQ3 Fixtures — Syndication + Work-Anchor + Corroboration Scoring")
    print("=" * 70)
    print()

    success = run_tests()

    print()
    if success:
        print("ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED")
        sys.exit(1)
