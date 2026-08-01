"""Unit tests for theme_thread_discoverer — SQ-S6b.

Tests deterministic logic without API calls:
- Entity extraction from elements
- Entity-overlap clustering
- Theme scoring
- Multi-thread blending
- Degradation
- Element-to-stop assignment
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from theme_thread_discoverer import (
    _extract_entities_from_element,
    _compute_entity_overlap_clusters,
    _score_themes,
    _blend_threads,
    _check_degradation,
    _assign_elements_to_stops,
    _build_per_stop_context,
    ThemeThread,
    ThreadDiscoveryResult,
    MIN_COVERAGE_THRESHOLD,
)


def test_entity_extraction():
    """Test entity extraction from a story element."""
    elem = {
        "id": "se_001",
        "type": "origin",
        "text": "The museum was founded in 1960 by André Malraux as part of a cultural initiative.",
        "people": ["André Malraux"],
        "dates": ["1960"],
    }
    entities = _extract_entities_from_element(elem)
    assert "andré malraux" in entities["people"], f"Expected 'andré malraux' in people, got {entities['people']}"
    assert "1960" in entities["dates"], f"Expected '1960' in dates, got {entities['dates']}"
    print("  ✓ Entity extraction: people and dates extracted correctly")


def test_entity_extraction_from_text():
    """Test entity extraction parses proper nouns from text."""
    elem = {
        "id": "se_002",
        "type": "provenance",
        "text": "Charles Sorlier donated his personal archive of Chagall prints in 1986.",
        "people": [],
        "dates": [],
    }
    entities = _extract_entities_from_element(elem)
    assert "1986" in entities["dates"], f"Expected '1986' in dates from text, got {entities['dates']}"
    # Charles Sorlier should be detected as proper noun
    assert any("charles" in p for p in entities["people"]), \
        f"Expected 'Charles Sorlier' detected, got {entities['people']}"
    print("  ✓ Entity extraction from text: proper nouns and dates parsed")


def test_entity_overlap_clustering():
    """Test deterministic entity-overlap pass across stops."""
    elements_per_stop = {
        0: [
            {"id": "se_001", "type": "origin", "text": "Built in 1706 by the Savoyard dynasty",
             "people": ["Louis XIV"], "dates": ["1706"]},
        ],
        1: [
            {"id": "se_002", "type": "provenance", "text": "Under Sardinian rule until 1860",
             "people": [], "dates": ["1860"]},
        ],
        2: [
            {"id": "se_003", "type": "turning_point", "text": "The Treaty of Turin in 1860 made Nice part of France",
             "people": [], "dates": ["1860"]},
        ],
        3: [
            {"id": "se_004", "type": "origin", "text": "Louis XIV ordered the citadel razed in 1706",
             "people": ["Louis XIV"], "dates": ["1706"]},
        ],
    }

    clusters = _compute_entity_overlap_clusters(elements_per_stop, 4)
    
    # Should find "1860" shared across stops 1,2 and "1706" shared across 0,3
    # and "Louis XIV" shared across 0,3
    date_1860 = [c for c in clusters if c["entity"] == "1860"]
    date_1706 = [c for c in clusters if c["entity"] == "1706"]
    
    assert len(date_1860) > 0, "Expected cluster for '1860'"
    assert set(date_1860[0]["stops"]) == {1, 2}, f"Expected stops 1,2 for 1860, got {date_1860[0]['stops']}"
    
    assert len(date_1706) > 0, "Expected cluster for '1706'"
    assert set(date_1706[0]["stops"]) == {0, 3}, f"Expected stops 0,3 for 1706, got {date_1706[0]['stops']}"
    
    print("  ✓ Entity overlap clustering: shared dates across stops detected")


def test_theme_scoring():
    """Test theme scoring with valid candidates."""
    elements_per_stop = {
        0: [{"id": "se_001", "type": "origin", "text": "Italian alleys", "people": [], "dates": [], "corroboration_status": "documented"}],
        1: [{"id": "se_002", "type": "origin", "text": "Turin-style arcades", "people": [], "dates": [], "corroboration_status": "documented"}],
        2: [{"id": "se_003", "type": "turning_point", "text": "Citadel razed 1706", "people": [], "dates": ["1706"], "corroboration_status": "documented"}],
        3: [{"id": "se_004", "type": "origin", "text": "Sardinian harbor", "people": [], "dates": [], "corroboration_status": "reported"}],
        4: [{"id": "se_005", "type": "origin", "text": "Ligurian market", "people": [], "dates": [], "corroboration_status": "documented"}],
        5: [{"id": "se_006", "type": "turning_point", "text": "1860 annexation", "people": [], "dates": ["1860"], "corroboration_status": "documented"}],
        6: [{"id": "se_007", "type": "origin", "text": "French city over border river", "people": [], "dates": [], "corroboration_status": "reported"}],
    }
    all_elements = []
    for elems in elements_per_stop.values():
        all_elements.extend(elems)

    candidates = [{
        "name": "An Italian city that became French",
        "description": "From Savoyard citadel to French annexation — the story of Nice's identity transformation",
        "grounded_on": ["se_001", "se_002", "se_003", "se_004", "se_005", "se_006", "se_007"],
        "stops_covered": [1, 2, 3, 4, 5, 6, 7],  # 1-based from LLM
        "arc_sketch": "Begins Italian, turns at 1706, pays off at 1860",
    }]

    scored = _score_themes(candidates, elements_per_stop, all_elements, 7)
    assert len(scored) == 1, f"Expected 1 scored theme, got {len(scored)}"
    assert scored[0].coverage == 1.0, f"Expected coverage 1.0 (7/7), got {scored[0].coverage}"
    assert scored[0].evidence_strength > 0.7, f"Expected evidence >0.7, got {scored[0].evidence_strength}"
    print(f"  ✓ Theme scoring: coverage={scored[0].coverage:.2f}, evidence={scored[0].evidence_strength:.2f}, total={scored[0].total_score:.3f}")


def test_theme_scoring_rejects_weak():
    """Test that themes with insufficient grounding are rejected."""
    elements_per_stop = {
        0: [{"id": "se_001", "type": "origin", "text": "A painting", "people": [], "dates": [], "corroboration_status": "documented"}],
    }
    all_elements = [{"id": "se_001", "type": "origin", "text": "A painting", "people": [], "dates": [], "corroboration_status": "documented"}]

    # Theme citing only 1 element should be rejected
    candidates = [{
        "name": "Weak theme",
        "description": "Only one element",
        "grounded_on": ["se_001"],
        "stops_covered": [1],
        "arc_sketch": "No arc",
    }]

    scored = _score_themes(candidates, elements_per_stop, all_elements, 5)
    assert len(scored) == 0, f"Expected 0 scored themes (rejected), got {len(scored)}"
    print("  ✓ Theme scoring: weak theme (1 element) rejected")


def test_blend_threads():
    """Test coverage-proportional weight assignment."""
    t1 = ThemeThread("Thread A", "desc", ["se_001"], [0,1,2,3,4,5,6], ["se_001"])
    t1.coverage = 7/8
    t1.total_score = 0.8
    
    t2 = ThemeThread("Thread B", "desc", ["se_002"], [0,1,2,3,4], ["se_002"])
    t2.coverage = 5/8
    t2.total_score = 0.6
    
    t3 = ThemeThread("Thread C", "desc", ["se_003"], [0,1,2,3], ["se_003"])
    t3.coverage = 4/8
    t3.total_score = 0.5
    
    blended = _blend_threads([t1, t2, t3], 8)
    
    assert len(blended) == 3
    # Weights should be 7/16, 5/16, 4/16
    assert abs(blended[0].weight - 7/16) < 0.01, f"Expected 7/16, got {blended[0].weight}"
    assert abs(blended[1].weight - 5/16) < 0.01, f"Expected 5/16, got {blended[1].weight}"
    assert abs(blended[2].weight - 4/16) < 0.01, f"Expected 4/16, got {blended[2].weight}"
    # Weights sum to 1
    total_weight = sum(t.weight for t in blended)
    assert abs(total_weight - 1.0) < 0.01, f"Expected weights sum=1.0, got {total_weight}"
    
    print(f"  ✓ Multi-thread blending: weights {[f'{t.weight:.3f}' for t in blended]} sum to {total_weight:.3f}")


def test_degradation_threaded():
    """Test that high-coverage theme passes degradation check."""
    t = ThemeThread("Good thread", "desc", [], [0,1,2,3,4], [])
    t.coverage = 0.71  # 5/7 stops
    
    mode, _ = _check_degradation([t], 7)
    assert mode == "threaded", f"Expected 'threaded', got '{mode}'"
    print("  ✓ Degradation: 71% coverage → threaded mode")


def test_degradation_organizing_principle():
    """Test that medium coverage falls back to organizing principle."""
    t = ThemeThread("Medium thread", "desc", [], [0,1,2], [])
    t.coverage = 0.43  # 3/7 stops
    
    mode, principle = _check_degradation([t], 7)
    assert mode == "organizing_principle", f"Expected 'organizing_principle', got '{mode}'"
    assert principle == "chronological"
    print("  ✓ Degradation: 43% coverage → organizing_principle (chronological)")


def test_degradation_mosaic():
    """Test that very low coverage falls back to mosaic."""
    t = ThemeThread("Weak thread", "desc", [], [0,1], [])
    t.coverage = 0.25  # 2/8 stops
    
    mode, _ = _check_degradation([t], 8)
    assert mode == "mosaic", f"Expected 'mosaic', got '{mode}'"
    print("  ✓ Degradation: 25% coverage → mosaic mode")


def test_degradation_no_themes():
    """Test that no themes at all → mosaic."""
    mode, _ = _check_degradation([], 8)
    assert mode == "mosaic", f"Expected 'mosaic', got '{mode}'"
    print("  ✓ Degradation: no themes → mosaic mode")


def test_assign_elements_to_stops():
    """Test heuristic element→stop assignment."""
    elements = [
        {"id": "se_001", "text": "The Song of Songs cycle by Chagall depicts biblical love stories", "source_sentence": ""},
        {"id": "se_002", "text": "The Blue Nude series was created after Matisse's illness", "source_sentence": ""},
        {"id": "se_003", "text": "The museum was founded in 1960", "source_sentence": ""},  # Generic — round-robin
    ]
    poi_names = ["Song of Songs cycle", "Blue Nude series", "The Reception Hall"]
    
    mapping = _assign_elements_to_stops(elements, poi_names)
    
    # se_001 should map to stop 0 (Song of Songs)
    stop0_ids = [e["id"] for e in mapping.get(0, [])]
    assert "se_001" in stop0_ids, f"Expected se_001 at stop 0, got {stop0_ids}"
    
    # se_002 should map to stop 1 (Blue Nude)
    stop1_ids = [e["id"] for e in mapping.get(1, [])]
    assert "se_002" in stop1_ids, f"Expected se_002 at stop 1, got {stop1_ids}"
    
    # se_003 (generic) should be at 1-2 stops via round-robin (NOT all 3)
    all_stop_ids = []
    for i in range(3):
        ids = [e["id"] for e in mapping.get(i, [])]
        if "se_003" in ids:
            all_stop_ids.append(i)
    assert len(all_stop_ids) <= 2, f"Expected se_003 at ≤2 stops (round-robin), got stops {all_stop_ids}"
    assert len(all_stop_ids) >= 1, f"Expected se_003 at ≥1 stop, got stops {all_stop_ids}"
    
    print("  ✓ Element-to-stop assignment: title-matched + round-robin distribution")


def test_per_stop_context_callbacks():
    """Test that per-stop context identifies cross-stop callbacks."""
    elements_per_stop = {
        0: [{"id": "se_001", "type": "origin", "text": "Hokusai's Great Wave woodblock print technique",
             "people": ["Hokusai"], "dates": [], "corroboration_status": "documented"}],
        1: [{"id": "se_002", "type": "technique", "text": "Influenced by Japanese woodblock printing",
             "people": ["Hokusai"], "dates": [], "corroboration_status": "documented"}],
    }
    all_elements = [e for elems in elements_per_stop.values() for e in elems]
    
    # Create a thread covering both stops
    thread = ThemeThread(
        "Japanese woodblock influence",
        "How Hokusai's technique connects these works",
        ["se_001", "se_002"],
        [0, 1],
        ["se_001", "se_002"],
    )
    thread.weight = 1.0
    
    per_stop = _build_per_stop_context([thread], elements_per_stop, all_elements, 2)
    
    # Stop 1 should have a callback to stop 0
    assert len(per_stop) == 2
    assert len(per_stop[1].get("callbacks", [])) > 0, \
        f"Expected callback at stop 1, got {per_stop[1].get('callbacks', [])}"
    cb = per_stop[1]["callbacks"][0]
    assert cb["from_stop"] == 0, f"Expected callback from stop 0, got {cb['from_stop']}"
    print(f"  ✓ Per-stop callbacks: stop 1 references stop 0 via '{cb['element_text'][:50]}...'")


def run_all_tests():
    """Run all unit tests."""
    print("=" * 60)
    print("LOCAL-38 Unit Tests: theme_thread_discoverer.py")
    print("=" * 60)
    
    tests = [
        test_entity_extraction,
        test_entity_extraction_from_text,
        test_entity_overlap_clustering,
        test_theme_scoring,
        test_theme_scoring_rejects_weak,
        test_blend_threads,
        test_degradation_threaded,
        test_degradation_organizing_principle,
        test_degradation_mosaic,
        test_degradation_no_themes,
        test_assign_elements_to_stops,
        test_per_stop_context_callbacks,
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
            print(f"  ✗ {test.__name__}: EXCEPTION: {e}")
            failed += 1
    
    print(f"\n{'='*60}")
    print(f"RESULTS: {passed} passed, {failed} failed, {passed+failed} total")
    print(f"{'='*60}")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
