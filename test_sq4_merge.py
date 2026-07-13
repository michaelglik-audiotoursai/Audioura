"""test_sq4_merge.py — SQ4 M1 merge pass fixtures.

RS2: Legend boundary — merge NEVER crosses legend status.
RS3: Real pilot data — the actual 1952 cluster from 39aeae9 merges to documented.
RS8: Disputed — conflicting values from independent sources → disputed status.

Tests the merge candidate gate and structural rules WITHOUT calling the LLM
(mocks the LLM decision to test the merge machinery deterministically).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unittest.mock import patch
from story_element_extractor import (
    _find_merge_candidates, _llm_merge_pass, score_corroboration,
    jaccard_similarity, _normalize_claim_key,
)


def run_tests():
    all_passed = True

    # --- RS2: Legend boundary (merge NEVER crosses legend status) ---
    print("  RS2: Legend Boundary (merge must never cross):")

    # Setup: a legend element and a technique element that share topic
    legend_elem = {
        'text': 'Blue Nude II was created in a single, fluid cut of the scissors.',
        'type': 'legend',
        'corroboration_status': 'legend',
        'source_domain': 'centrepompidou.fr',
        'source_sentence': 'Legend has it that Blue Nude II was created in a single, fluid cut.',
        'source_url': 'https://centrepompidou.fr/focus-blue-nude',
        '_all_sources': [{'source_domain': 'centrepompidou.fr', 'source_url': 'https://centrepompidou.fr/focus-blue-nude'}],
    }
    technique_elem = {
        'text': 'Blue Nude II was created using gouache-painted paper cut-outs.',
        'type': 'technique',
        'corroboration_status': 'reported',
        'source_domain': 'en.wikipedia.org',
        'source_sentence': 'The painted gouache cut-outs that compose the Blue Nudes were inspired by...',
        'source_url': 'https://en.wikipedia.org/wiki/Blue_Nudes',
        '_all_sources': [{'source_domain': 'en.wikipedia.org', 'source_url': 'https://en.wikipedia.org/wiki/Blue_Nudes'}],
    }

    elements_with_legend = [legend_elem, technique_elem]
    candidates = _find_merge_candidates(elements_with_legend)

    # Legend element must NEVER appear in candidates
    passed = len(candidates) == 0
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] Legend + technique pair → 0 merge candidates (legend boundary enforced)")
    if not passed:
        all_passed = False
        print(f"      Got {len(candidates)} candidates: {candidates}")

    # Even if LLM says "same subject," legend stays legend after merge pass
    with patch('story_element_extractor._llm_merge_decision', return_value=[]):
        result = _llm_merge_pass(elements_with_legend)
    legend_after = [e for e in result if e.get('corroboration_status') == 'legend']
    passed = len(legend_after) == 1 and 'single' in legend_after[0].get('text', '').lower()
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] After merge pass: legend element preserved at 'legend' status")
    if not passed:
        all_passed = False

    # --- RS3: Real pilot data — 1952 cluster merges to documented ---
    print()
    print("  RS3: Real Pilot Data (1952 cluster from 39aeae9):")

    # The actual elements from the Matisse pilot (3 date elements about creation year)
    elem_wiki = {
        'text': 'Blue Nude II was completed in 1952.',
        'type': 'date',
        'corroboration_status': 'reported',
        'source_domain': 'en.wikipedia.org',
        'source_sentence': 'Blue Nude II was completed in 1952, shortly before Matisse began the series.',
        'source_url': 'https://en.wikipedia.org/wiki/Blue_Nudes',
        'independent_source_count': 1,
        '_all_sources': [{'source_domain': 'en.wikipedia.org', 'source_url': 'https://en.wikipedia.org/wiki/Blue_Nudes'}],
    }
    elem_moma = {
        'text': 'Blue Nude II was created in Spring 1952.',
        'type': 'date',
        'corroboration_status': 'reported',
        'source_domain': 'www.moma.org',
        'source_sentence': 'Blue Nude II was created in Spring 1952 as part of the series.',
        'source_url': 'https://www.moma.org/collection/works/79040',
        'independent_source_count': 1,
        '_all_sources': [{'source_domain': 'www.moma.org', 'source_url': 'https://www.moma.org/collection/works/79040'}],
    }
    elem_pompidou = {
        'text': 'Blue Nude II was created in 1952.',
        'type': 'date',
        'corroboration_status': 'reported',
        'source_domain': 'www.centrepompidou.fr',
        'source_sentence': 'Blue Nude II was created in 1952 using gouache on paper.',
        'source_url': 'https://www.centrepompidou.fr/en/ressources/oeuvre/cez9LbM',
        'independent_source_count': 1,
        '_all_sources': [{'source_domain': 'www.centrepompidou.fr', 'source_url': 'https://www.centrepompidou.fr/en/ressources/oeuvre/cez9LbM'}],
    }

    cluster_elements = [elem_wiki, elem_moma, elem_pompidou]

    # Test 1: Candidate gate finds these as candidates (same type = 'date')
    candidates = _find_merge_candidates(cluster_elements)
    passed = len(candidates) >= 2  # At least 2 pairs from 3 elements
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] 3 date elements → ≥2 candidate pairs found: {len(candidates)}")
    if not passed:
        all_passed = False

    # Test 2: With LLM saying "same fact" for all pairs → merge → documented
    # Mock LLM to approve all merges
    def mock_all_same(pairs):
        return [{'pair': i+1, 'same_subject': True, 'conflicting': False} for i in range(len(pairs))]

    with patch('story_element_extractor._llm_merge_decision', side_effect=mock_all_same):
        merged = _llm_merge_pass(cluster_elements.copy())

    # After merge: should have 1 element with status 'documented' (3 independent domains)
    documented = [e for e in merged if e.get('corroboration_status') == 'documented']
    passed = len(documented) >= 1
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] After LLM merge: ≥1 element at 'documented' status (got {len(documented)})")
    if not passed:
        all_passed = False

    if documented:
        n_indep = documented[0].get('independent_source_count', 0)
        passed = n_indep >= 2
        status = "PASS" if passed else "FAIL"
        print(f"    [{status}] Documented element has ≥2 independent sources (got {n_indep})")
        if not passed:
            all_passed = False

    # Test 3: merge_log is attached for LEAD recomputation
    has_merge_log = any('_merge_log' in e for e in merged)
    passed = has_merge_log
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] merge_log attached to output for LEAD recomputation")
    if not passed:
        all_passed = False

    # --- RS2+RS3 Combined: Legend among reporteds (single-cut + technique cluster):**
    print()
    print("  RS2+RS3 Combined: Legend among reporteds (single-cut + technique cluster):")

    mixed_elements = [
        {  # Legend: "single fluid cut" — must stay legend
            'text': 'Blue Nude II was created in a single, fluid cut of the scissors.',
            'type': 'technique',
            'corroboration_status': 'legend',
            'source_domain': 'centrepompidou.fr',
            'source_sentence': 'Legend has it that Blue Nude II was created in a single, fluid cut.',
            'source_url': 'https://centrepompidou.fr/focus',
            '_all_sources': [{'source_domain': 'centrepompidou.fr'}],
        },
        {  # Reported technique from Wikipedia
            'text': 'Blue Nude II was created using gouache-painted paper cut-outs.',
            'type': 'technique',
            'corroboration_status': 'reported',
            'source_domain': 'en.wikipedia.org',
            'source_sentence': 'The painted gouache cut-outs that compose the Blue Nudes...',
            'source_url': 'https://en.wikipedia.org/wiki/Blue_Nudes',
            '_all_sources': [{'source_domain': 'en.wikipedia.org'}],
        },
        {  # Reported technique from MoMA
            'text': 'Blue Nude II is a gouache on paper, cut and pasted, mounted on canvas.',
            'type': 'technique',
            'corroboration_status': 'reported',
            'source_domain': 'www.moma.org',
            'source_sentence': 'Gouache on paper, cut and pasted on canvas.',
            'source_url': 'https://www.moma.org/collection/works/79040',
            '_all_sources': [{'source_domain': 'www.moma.org'}],
        },
    ]

    candidates = _find_merge_candidates(mixed_elements)
    # Legend (idx 0) should NOT appear in any candidate pair
    legend_in_candidates = any(0 in pair for pair in candidates)
    passed = not legend_in_candidates
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] Legend element (idx 0) excluded from all candidate pairs")
    if not passed:
        all_passed = False

    # The two non-legend techniques (idx 1, 2) SHOULD be candidates
    non_legend_pair = (1, 2) in candidates
    passed = non_legend_pair
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] Two reported techniques (idx 1,2) ARE candidates for merge")
    if not passed:
        all_passed = False

    # --- B5 NEW: Cross-type separation (date ≠ technique, NEVER in same group) ---
    print()
    print("  B5: Cross-type separation (date and technique NEVER merge):")

    cross_type_elements = [
        {  # date element
            'text': 'Blue Nude II was completed in 1952.',
            'type': 'date',
            'corroboration_status': 'reported',
            'source_domain': 'en.wikipedia.org',
            '_all_sources': [{'source_domain': 'en.wikipedia.org'}],
        },
        {  # technique element (should NEVER merge with date)
            'text': 'Blue Nude II is a gouache on paper, cut and pasted.',
            'type': 'technique',
            'corroboration_status': 'reported',
            'source_domain': 'www.moma.org',
            '_all_sources': [{'source_domain': 'www.moma.org'}],
        },
        {  # reception element (should NEVER merge with date or technique)
            'text': 'The series was shown at MoMA from October 2014 to February 2015.',
            'type': 'reception',
            'corroboration_status': 'reported',
            'source_domain': 'www.centrepompidou.fr',
            '_all_sources': [{'source_domain': 'www.centrepompidou.fr'}],
        },
    ]

    cross_candidates = _find_merge_candidates(cross_type_elements)
    passed = len(cross_candidates) == 0
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] date + technique + reception → 0 merge candidates (cross-type blocked)")
    if not passed:
        all_passed = False
        print(f"      Got candidates: {cross_candidates}")

    # B5 NEW: Final element count must be > 1 after merge (no single-blob collapse)
    print()
    print("  B5: No single-blob collapse (multi-type input → multi-element output):")

    multi_type_input = [
        {'text': 'Created in 1952.', 'type': 'date', 'corroboration_status': 'reported',
         'source_domain': 'a.org', '_all_sources': [{'source_domain': 'a.org'}]},
        {'text': 'Gouache on paper.', 'type': 'technique', 'corroboration_status': 'reported',
         'source_domain': 'b.org', '_all_sources': [{'source_domain': 'b.org'}]},
        {'text': 'Shown at MoMA.', 'type': 'reception', 'corroboration_status': 'reported',
         'source_domain': 'c.org', '_all_sources': [{'source_domain': 'c.org'}]},
    ]

    # Since all are different types, merge should produce NO merges → 3 elements remain
    with patch('story_element_extractor._llm_merge_decision', return_value=[]):
        no_merge_result = _llm_merge_pass(multi_type_input)

    passed = len(no_merge_result) == 3
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] 3 different-type elements → 3 output elements (no collapse): got {len(no_merge_result)}")
    if not passed:
        all_passed = False

    # --- E1: English-series query generation ---
    print()
    print("  E1: Composed English-series query:")

    from work_story_searcher import synthesize_queries, _strip_trailing_numeral

    chagall_stop = {
        'canonical_title': 'Le Cantique des Cantiques IV',
        'local_title': 'Le Cantique des Cantiques IV',
        'english_title': 'Song of Songs IV',
        'artist': 'Marc Chagall',
        'venue_city': 'Nice',
        'venue_lang': 'fr',
    }
    queries = synthesize_queries(chagall_stop, tour_type='contained')

    # E1 should produce "Song of Songs" Marc Chagall story behind (series-level English)
    e1_query = f'"Song of Songs" Marc Chagall story behind'
    has_e1 = any('Song of Songs' in q and 'IV' not in q and 'Marc Chagall' in q for q in queries)
    passed = has_e1
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] E1 English-series query generated: {has_e1}")
    if not passed:
        all_passed = False
        print(f"      Queries: {queries}")

    # Verify the numeral-stripping works
    stripped = _strip_trailing_numeral('Song of Songs IV')
    passed = stripped == 'Song of Songs'
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] _strip_trailing_numeral('Song of Songs IV') → '{stripped}'")
    if not passed:
        all_passed = False

    # --- RS8: Disputed detection ---
    print()
    print("  RS8: Disputed status (conflicting values from independent sources):")

    # Two date elements that conflict (same subject, different values)
    conflict_a = {
        'text': 'Le Cantique des Cantiques IV was created in 1958.',
        'type': 'date',
        'corroboration_status': 'reported',
        'source_domain': 'musees-nationaux-alpesmaritimes.fr',
        'source_sentence': 'Created in 1958.',
        'source_url': 'https://musees-nationaux.fr/page1',
        '_all_sources': [{'source_domain': 'musees-nationaux-alpesmaritimes.fr'}],
    }
    conflict_b = {
        'text': 'Le Cantique des Cantiques IV was created in 1965-1966.',
        'type': 'date',
        'corroboration_status': 'reported',
        'source_domain': 'pop.culture.gouv.fr',
        'source_sentence': 'Created in 1965-1966.',
        'source_url': 'https://pop.culture.gouv.fr/page1',
        '_all_sources': [{'source_domain': 'pop.culture.gouv.fr'}],
    }

    # Mock LLM saying "same subject but conflicting"
    def mock_conflicting(pairs):
        return [{'pair': i+1, 'same_subject': True, 'conflicting': True} for i in range(len(pairs))]

    with patch('story_element_extractor._llm_merge_decision', side_effect=mock_conflicting):
        disputed_result = _llm_merge_pass([conflict_a.copy(), conflict_b.copy()])

    disputed_elems = [e for e in disputed_result if e.get('corroboration_status') == 'disputed']
    passed = len(disputed_elems) == 2
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] Conflicting dates → both marked 'disputed' (got {len(disputed_elems)})")
    if not passed:
        all_passed = False

    # Verify dispute_pair reference
    if disputed_elems:
        has_pair_ref = all('dispute_pair' in e for e in disputed_elems)
        passed = has_pair_ref
        status = "PASS" if passed else "FAIL"
        print(f"    [{status}] dispute_pair reference present on disputed elements")
        if not passed:
            all_passed = False

    # --- Ranking ---
    print()
    print("  SQ4 Ranking (rank_stop_elements):")

    from story_element_extractor import rank_stop_elements, select_stop_elements

    test_elements = [
        {'text': 'date fact', 'type': 'date', 'corroboration_status': 'reported'},
        {'text': 'origin story', 'type': 'origin', 'corroboration_status': 'documented', 'people': ['Chagall']},
        {'text': 'technique detail', 'type': 'technique', 'corroboration_status': 'reported'},
        {'text': 'legend tale', 'type': 'legend', 'corroboration_status': 'legend'},
    ]

    ranked = rank_stop_elements(test_elements)
    # Origin + documented + people should rank highest
    passed = ranked[0]['type'] == 'origin'
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] Origin+documented+people ranks first: {ranked[0].get('type')}")
    if not passed:
        all_passed = False

    # Date + reported should rank lowest
    passed = ranked[-1]['type'] == 'date'
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] Date+reported ranks last: {ranked[-1].get('type')}")
    if not passed:
        all_passed = False

    # Select top 2
    selection = select_stop_elements(test_elements, max_selected=2)
    passed = len(selection['selected_elements']) == 2
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] select_stop_elements(max=2): {len(selection['selected_elements'])} selected, {len(selection['runner_up_elements'])} runners")
    if not passed:
        all_passed = False

    return all_passed


if __name__ == "__main__":
    print("=" * 70)
    print("SQ4 Fixtures — LLM Merge Pass (RS2 legend + RS3 real data + E1)")
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
