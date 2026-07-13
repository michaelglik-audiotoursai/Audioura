"""test_w7_wiring.py — W7 fact-targeted refinement wiring fixture.

Proves the end-to-end pipeline: reported high-value element → fact_refinement_queries 
generated → execute_fact_refinement returns new results → second extraction merges →
corroboration upgrades to 'documented'.

All mocked — no network calls.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unittest.mock import patch, MagicMock
from story_element_extractor import extract_and_score_stop, score_corroboration
from work_story_searcher import (
    execute_fact_refinement, synthesize_fact_targeted_queries,
    _strip_trailing_numeral,
)


def run_tests() -> bool:
    all_passed = True

    # --- Test 1: extract_and_score_stop returns fact_refinement_queries for reported HV element ---
    print("  W7 Wiring: extract_and_score_stop returns fact_refinement_queries")

    # Mock the extraction pipeline: simulate a single-source dedication element
    mock_search_results = [
        {'url': 'https://museum.org/chagall', 'title': 'Chagall page', 'snippet': 'S1',
         'domain': 'museum.org', 'tier': 'tier1'},
    ]

    # Mock fetch_page_text to return a page about Chagall's donation
    mock_page = """The Song of Songs cycle by Marc Chagall was donated by Marc and Valentina Chagall in 1966 
    to the French state. This dedication marked the beginning of what would become the Musée National 
    Marc Chagall. Le Cantique des Cantiques represents Chagall's love for his wife Vava."""

    # Mock extract_elements_from_text to return a single dedication element
    mock_elements = [
        {'text': 'Chagall dedicated the cycle to Vava in 1966', 'type': 'dedication',
         'source_sentence': 'The Song of Songs cycle was donated by Marc and Valentina Chagall in 1966.',
         'source_url': 'https://museum.org/chagall', 'source_domain': 'museum.org',
         'people': ['Valentina Chagall', 'Vava'], 'dates': ['1966'], 'confidence': 'high'},
    ]

    with patch('story_element_extractor.fetch_page_text', return_value=mock_page), \
         patch('story_element_extractor.check_work_anchor', return_value=True), \
         patch('story_element_extractor.extract_elements_from_text', return_value=mock_elements), \
         patch('story_element_extractor.work_stories_put'):  # Don't try DB

        result = extract_and_score_stop(
            mock_search_results,
            canonical_title='Le Cantique des Cantiques IV',
            artist='Marc Chagall',
        )

    # Verify fact_refinement_queries is in output and non-empty
    frq = result.get('fact_refinement_queries', [])
    passed = len(frq) >= 1
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] fact_refinement_queries returned: {len(frq)} queries")
    if frq:
        print(f"           Query: '{frq[0][:80]}...'")
    if not passed:
        all_passed = False

    # Verify the element is reported (single source)
    elements = result.get('elements', [])
    dedication_elem = [e for e in elements if e.get('type') == 'dedication']
    passed = len(dedication_elem) == 1 and dedication_elem[0].get('corroboration_status') == 'reported'
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] Dedication element is 'reported' (single source): {dedication_elem[0].get('corroboration_status') if dedication_elem else 'none'}")
    if not passed:
        all_passed = False

    # --- Test 2: execute_fact_refinement runs queries and returns new results ---
    print("\n  W7 Wiring: execute_fact_refinement executes within budget")

    mock_serp_results = [
        {'url': 'https://francetoday.com/chagall-vence', 'title': 'France Today - Chagall',
         'snippet': 'The dedication to Vava...'},
        {'url': 'https://museedevence.fr/chagall', 'title': 'Musée de Vence',
         'snippet': 'Donated in 1966...'},
    ]

    with patch('work_story_searcher._serp_search', return_value=(mock_serp_results, 150.0)):
        refinement_result = execute_fact_refinement(
            fact_queries=frq,
            existing_results=mock_search_results,  # museum.org already seen
            query_budget_remaining=3,
            domain_cache={'francetoday.com': 'tier2', 'museedevence.fr': 'tier1'},
        )

    new_results = refinement_result['new_results']
    passed = len(new_results) == 2  # Both new URLs should come through
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] execute_fact_refinement returns {len(new_results)} new results (expected 2)")
    if not passed:
        all_passed = False

    passed = refinement_result['queries_used'] == 1
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] Queries used: {refinement_result['queries_used']} (expected 1)")
    if not passed:
        all_passed = False

    # Verify query_log has fact_refinement flag
    log_entries = refinement_result['query_log']
    passed = len(log_entries) == 1 and log_entries[0].get('fact_refinement') is True
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] Query log marked fact_refinement=True")
    if not passed:
        all_passed = False

    # --- Test 3: Full round-trip → reported upgrades to documented ---
    print("\n  W7 Wiring: Full round-trip (reported → second round → documented)")

    # Simulate: first extraction found one source, second extraction found another
    # Merge and re-score → should upgrade to documented
    first_round_elements = [
        {'text': 'Chagall dedicated the cycle to Vava in 1966', 'type': 'dedication',
         'source_sentence': 'The Song of Songs cycle was donated by Marc and Valentina Chagall in 1966.',
         'source_url': 'https://museum.org/chagall', 'source_domain': 'museum.org'},
    ]
    second_round_elements = [
        {'text': 'Chagall dedicated the cycle to Vava in 1966', 'type': 'dedication',
         'source_sentence': 'Marc Chagall made a dedication of his Song of Songs paintings to his wife Vava in 1966.',
         'source_url': 'https://francetoday.com/chagall-vence', 'source_domain': 'francetoday.com'},
    ]

    # Merge and re-score
    merged = first_round_elements + second_round_elements
    re_scored = score_corroboration(merged)

    # The dedication element should now be 'documented' (2 independent sources)
    dedication_results = [e for e in re_scored if e.get('type') == 'dedication']
    passed = (len(dedication_results) == 1 and
              dedication_results[0].get('corroboration_status') == 'documented')
    status = "PASS" if passed else "FAIL"
    indep = dedication_results[0].get('independent_source_count', 0) if dedication_results else 0
    print(f"    [{status}] After merge+re-score: dedication → 'documented' (independent={indep})")
    if not passed:
        all_passed = False
        if dedication_results:
            print(f"           Got: {dedication_results[0].get('corroboration_status')}")

    # --- Test 4: Budget exhaustion prevents fact refinement ---
    print("\n  W7 Wiring: Budget exhaustion prevents execution")

    with patch('work_story_searcher._serp_search') as mock_serp:
        refinement_result = execute_fact_refinement(
            fact_queries=['query 1', 'query 2'],
            existing_results=[],
            query_budget_remaining=0,  # No budget left
        )
        # _serp_search should NOT have been called
        passed = mock_serp.call_count == 0
        status = "PASS" if passed else "FAIL"
        print(f"    [{status}] Zero budget → zero SERP calls: call_count={mock_serp.call_count}")
        if not passed:
            all_passed = False

    # --- Test 5: Non-HV elements don't trigger refinement ---
    print("\n  W7 Wiring: Non-high-value elements don't produce queries")

    mock_date_elements = [
        {'text': 'Created in 1952', 'type': 'date',
         'source_sentence': 'Blue Nude II was created in 1952.',
         'source_url': 'https://museum.org/matisse', 'source_domain': 'museum.org',
         'people': [], 'dates': ['1952'], 'confidence': 'high'},
    ]

    with patch('story_element_extractor.fetch_page_text', return_value='Blue Nude II by Henri Matisse was created in 1952'), \
         patch('story_element_extractor.check_work_anchor', return_value=True), \
         patch('story_element_extractor.extract_elements_from_text', return_value=mock_date_elements), \
         patch('story_element_extractor.work_stories_put'):

        result2 = extract_and_score_stop(
            [{'url': 'https://museum.org/matisse', 'tier': 'tier1', 'domain': 'museum.org'}],
            canonical_title='Blue Nude II',
            artist='Henri Matisse',
        )

    frq2 = result2.get('fact_refinement_queries', [])
    passed = len(frq2) == 0
    status = "PASS" if passed else "FAIL"
    print(f"    [{status}] 'date' element (non-HV) → 0 fact_refinement_queries: {len(frq2)}")
    if not passed:
        all_passed = False

    return all_passed


if __name__ == "__main__":
    print("=" * 70)
    print("W7 Wiring Fixture — Fact-Targeted Refinement End-to-End")
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
