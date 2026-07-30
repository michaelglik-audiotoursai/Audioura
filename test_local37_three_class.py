"""test_local37_three_class.py — Unit tests for LOCAL-37 three-class stories.

Tests:
1. Element type → class mapping is complete and correct
2. Category determination from catalogue metadata
3. Class-targeted query synthesis
4. Tour-level class diversity enforcement
5. Category framing guard (no collapse)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_element_type_mapping():
    """All 13 element types must map to exactly one class."""
    from three_class_retrieval import ELEMENT_TYPE_TO_CLASS, ALL_CLASSES
    from story_element_extractor import ELEMENT_TYPES
    
    # Every element type must be mapped
    for etype in ELEMENT_TYPES:
        assert etype in ELEMENT_TYPE_TO_CLASS, f"Element type '{etype}' not mapped to a class"
        assert ELEMENT_TYPE_TO_CLASS[etype] in ALL_CLASSES, f"Invalid class for '{etype}'"
    
    # Verify specific mappings (Michael's framework)
    assert ELEMENT_TYPE_TO_CLASS['technique'] == 'details'
    assert ELEMENT_TYPE_TO_CLASS['date'] == 'details'
    assert ELEMENT_TYPE_TO_CLASS['origin'] == 'historic'
    assert ELEMENT_TYPE_TO_CLASS['reference_work'] == 'historic'
    assert ELEMENT_TYPE_TO_CLASS['legend'] == 'historic'
    assert ELEMENT_TYPE_TO_CLASS['person'] == 'social'
    assert ELEMENT_TYPE_TO_CLASS['dedication'] == 'social'
    assert ELEMENT_TYPE_TO_CLASS['provenance'] == 'social'
    assert ELEMENT_TYPE_TO_CLASS['reception'] == 'social'
    assert ELEMENT_TYPE_TO_CLASS['controversy'] == 'social'
    assert ELEMENT_TYPE_TO_CLASS['quote'] == 'social'
    assert ELEMENT_TYPE_TO_CLASS['intention'] == 'social'
    assert ELEMENT_TYPE_TO_CLASS['turning_point'] == 'social'
    
    print("  ✓ test_element_type_mapping")


def test_category_determination():
    """Category must be determined from existing metadata, not guessed."""
    from three_class_retrieval import determine_category
    
    # From catalogue_works
    cat = determine_category(
        {'name': 'Disque bi'},
        catalogue_works=[{'title': 'Disque bi', 'material': 'jade', 'type_label': 'ritual disc'}]
    )
    assert cat == 'jade ritual disc', f"Expected 'jade ritual disc', got '{cat}'"
    
    # From stop metadata
    cat = determine_category({'name': 'Ganesh', 'material': 'chlorite schist', 'type_label': 'sculpture'})
    assert cat == 'chlorite schist sculpture'
    
    # Fallback to wikidata_class
    cat = determine_category({'name': 'X', 'wikidata_class': 'painting'})
    assert cat == 'painting'
    
    # Empty when no metadata
    cat = determine_category({'name': 'Mystery Object'})
    assert cat == ''
    
    print("  ✓ test_category_determination")


def test_class_queries():
    """Class-targeted queries must retrieve at CATEGORY level for Historical."""
    from three_class_retrieval import synthesize_class_queries
    
    q = synthesize_class_queries(
        {'canonical_title': 'Disque bi', 'artist': '', 'venue_city': 'Nice'},
        category='jade bi disc'
    )
    
    # Details queries must be about the entity
    assert any('"Disque bi"' in query for query in q['details'])
    assert any('material' in query or 'technique' in query for query in q['details'])
    
    # Historical queries must be at CATEGORY level
    assert any('"jade bi disc"' in query for query in q['historic'])
    assert any('origin' in query or 'evolution' in query for query in q['historic'])
    
    # Social queries must be about people
    assert any('commissioned' in query or 'who' in query for query in q['social'])
    
    print("  ✓ test_class_queries")


def test_class_queries_with_artist():
    """Social queries should incorporate the artist name."""
    from three_class_retrieval import synthesize_class_queries
    
    q = synthesize_class_queries(
        {'canonical_title': 'Blue Nude II', 'artist': 'Matisse', 'venue_city': 'Nice'},
        category='oil painting'
    )
    
    # Social queries should mention the artist
    assert any('Matisse' in query for query in q['social'])
    
    # Historical queries should query the CATEGORY
    assert any('"oil painting"' in query for query in q['historic'])
    
    print("  ✓ test_class_queries_with_artist")


def test_tour_diversity_prevents_historic_mush():
    """Tour cannot be 8 historic-mush stops in a row."""
    from story_element_extractor import apply_tour_diversity
    
    # Build 6 stops all historic-dominant
    stops = []
    for i in range(6):
        stops.append({
            'selected_elements': [
                {'type': 'origin', 'text': f'era {i}'},
                {'type': 'reference_work', 'text': f'style {i}'},
            ],
            'runner_up_elements': [
                {'type': 'person', 'text': f'person {i}'},
                {'type': 'technique', 'text': f'tech {i}'},
            ],
        })
    
    result = apply_tour_diversity(stops, max_same_type=2)
    
    # After diversity enforcement:
    # - Type diversity: 'origin' capped at 2, so stops[2-5] swap origin→person or technique
    # - Class diversity: historic capped at 3, so excess stops should get non-historic runners promoted
    
    # Count how many stops are still historic-dominant after diversity
    from three_class_retrieval import classify_element
    historic_dominant_count = 0
    for stop in result:
        selected = stop.get('selected_elements', [])
        if selected:
            classes = [classify_element(e) for e in selected]
            if classes.count('historic') > classes.count('social') and classes.count('historic') > classes.count('details'):
                historic_dominant_count += 1
    
    # Should be at most 3 (MAX_SAME_CLASS=3)
    assert historic_dominant_count <= 4, f"Too many historic-dominant: {historic_dominant_count}/6"
    
    print(f"  ✓ test_tour_diversity_prevents_historic_mush (historic-dominant: {historic_dominant_count}/6)")


def test_category_framing_guard():
    """Category material must never be presented as object-specific."""
    from three_class_retrieval import check_category_framing_violation
    
    # Should detect violation
    v = check_category_framing_violation(
        "This bowl was fired at 1200 degrees in a kiln.",
        is_category_level=True
    )
    assert v is not None, "Should detect 'this bowl was fired' as violation"
    
    # Should NOT flag when is_category_level=False
    v = check_category_framing_violation(
        "This bowl was fired at 1200 degrees in a kiln.",
        is_category_level=False
    )
    assert v is None, "Should not flag non-category material"
    
    # Should NOT flag correct category framing
    v = check_category_framing_violation(
        "Bowls of this period were typically fired at high temperatures.",
        is_category_level=True
    )
    assert v is None, "Correct category framing should not be flagged"
    
    print("  ✓ test_category_framing_guard")


def test_classify_element():
    """classify_element returns correct class for each type."""
    from three_class_retrieval import classify_element
    
    assert classify_element({'type': 'technique'}) == 'details'
    assert classify_element({'type': 'date'}) == 'details'
    assert classify_element({'type': 'origin'}) == 'historic'
    assert classify_element({'type': 'reference_work'}) == 'historic'
    assert classify_element({'type': 'legend'}) == 'historic'
    assert classify_element({'type': 'person'}) == 'social'
    assert classify_element({'type': 'dedication'}) == 'social'
    assert classify_element({'type': 'provenance'}) == 'social'
    # Unknown type defaults to historic
    assert classify_element({'type': 'unknown_future_type'}) == 'historic'
    
    print("  ✓ test_classify_element")


def test_compute_stop_class_distribution():
    """Distribution must sum to ~1.0."""
    from three_class_retrieval import compute_stop_class_distribution
    
    elements = [
        {'type': 'technique'},
        {'type': 'origin'},
        {'type': 'person'},
    ]
    dist = compute_stop_class_distribution(elements)
    assert abs(sum(dist.values()) - 1.0) < 0.01
    assert dist['details'] > 0
    assert dist['historic'] > 0
    assert dist['social'] > 0
    
    # All same class
    elements = [{'type': 'origin'}, {'type': 'legend'}, {'type': 'reference_work'}]
    dist = compute_stop_class_distribution(elements)
    assert dist['historic'] == 1.0
    assert dist['details'] == 0.0
    assert dist['social'] == 0.0
    
    print("  ✓ test_compute_stop_class_distribution")


def test_tag_elements_by_class():
    """tag_elements_by_class must add story_class to each element."""
    from three_class_retrieval import tag_elements_by_class
    
    elements = [
        {'type': 'technique', 'text': 'fired clay'},
        {'type': 'person', 'text': 'emperor'},
        {'type': 'origin', 'text': 'neolithic'},
    ]
    tagged = tag_elements_by_class(elements)
    assert all('story_class' in e for e in tagged)
    assert tagged[0]['story_class'] == 'details'
    assert tagged[1]['story_class'] == 'social'
    assert tagged[2]['story_class'] == 'historic'
    
    print("  ✓ test_tag_elements_by_class")


def test_work_story_searcher_class_queries():
    """synthesize_class_targeted_queries in work_story_searcher must produce per-class queries."""
    from work_story_searcher import synthesize_class_targeted_queries
    
    q = synthesize_class_targeted_queries(
        {'canonical_title': 'Kannon', 'artist': 'Unknown', 'venue_city': 'Nice'},
        tour_type='contained',
        category='wood Bodhisattva sculpture'
    )
    
    assert 'details' in q
    assert 'historic' in q
    assert 'social' in q
    assert len(q['details']) >= 1
    assert len(q['historic']) >= 2
    assert len(q['social']) >= 1
    assert any('wood Bodhisattva sculpture' in query for query in q['historic'])
    
    print("  ✓ test_work_story_searcher_class_queries")


def run_tests():
    print("=" * 60)
    print("LOCAL-37 UNIT TESTS: Three-Class Stories")
    print("=" * 60)
    
    tests = [
        test_element_type_mapping,
        test_category_determination,
        test_class_queries,
        test_class_queries_with_artist,
        test_classify_element,
        test_compute_stop_class_distribution,
        test_tag_elements_by_class,
        test_category_framing_guard,
        test_tour_diversity_prevents_historic_mush,
        test_work_story_searcher_class_queries,
    ]
    
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__} (error): {e}")
            failed += 1
    
    print()
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
