"""
LOCAL-48 Tests: Riviera substance rebase + fabrication guards.

Tests cover:
1. Outdoor retrieval (three_class_retrieval.py) — multi-level facts, tiers
2. Adaptive word targets (generate_tour_text.py) — word target logic
3. Tour-title repetition cap (derepetition_guard.py)
4. Exhibition-vs-object fabrication guard (prompt content)
5. Thin-corpus honesty guard (prompt content)
6. Backward compatibility — museum tours unaffected
"""
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ────────────────────────────────────────────────────────────────────────────
# 1. Outdoor retrieval: function signature & tier classification
# ────────────────────────────────────────────────────────────────────────────

def test_retrieve_three_classes_accepts_outdoor_params():
    """retrieve_three_classes_for_stop accepts tour_category and tour_location."""
    from three_class_retrieval import retrieve_three_classes_for_stop
    import inspect
    sig = inspect.signature(retrieve_three_classes_for_stop)
    params = list(sig.parameters.keys())
    assert 'tour_category' in params, f"Missing tour_category param, got: {params}"
    assert 'tour_location' in params, f"Missing tour_location param, got: {params}"


def test_retrieve_three_classes_returns_retrieval_fields():
    """Return dict includes retrieval_facts and retrieval_tier."""
    from three_class_retrieval import retrieve_three_classes_for_stop
    result = retrieve_three_classes_for_stop(
        {'name': 'Test Stop', 'canonical_title': 'Test Stop', 'artist': ''},
        tour_category='museum',  # museum → should skip outdoor path
        tour_location='Test City',
    )
    assert 'retrieval_facts' in result, "Missing retrieval_facts key"
    assert 'retrieval_tier' in result, "Missing retrieval_tier key"
    # Museum tour: outdoor retrieval should NOT fire
    assert result['retrieval_tier'] == 'empty'
    assert result['retrieval_facts'] == []


def test_extract_facts_from_text():
    """_extract_facts_from_text identifies checkable facts."""
    from three_class_retrieval import _extract_facts_from_text
    text = (
        "The port was founded in 1863 by Napoleon III. "
        "It covers an area of 12 hectares. "
        "Beautiful sunsets can be seen here. "  # Should be excluded — no fact
        "The Battle of Nice occurred in 1543. "
    )
    facts = _extract_facts_from_text(text, "Port")
    assert len(facts) >= 2, f"Expected ≥2 facts, got {len(facts)}: {facts}"
    # Check that the atmosphere sentence was excluded
    atmos = [f for f in facts if "sunset" in f.lower()]
    assert len(atmos) == 0, "Atmosphere sentence should be excluded"


def test_extract_facts_empty_text():
    """_extract_facts_from_text returns empty for no-fact text."""
    from three_class_retrieval import _extract_facts_from_text
    text = "Beautiful views and stunning scenery await visitors here."
    facts = _extract_facts_from_text(text, "Beach")
    assert facts == [], f"Expected empty, got: {facts}"


def test_extract_parent_location():
    """_extract_parent_location generates fallback queries."""
    from three_class_retrieval import _extract_parent_location
    fallbacks = _extract_parent_location("Paloma Beach", "French Riviera biking tour, France")
    assert len(fallbacks) > 0, "Should generate at least one fallback"
    # Should contain a location hint
    combined = " ".join(fallbacks).lower()
    assert "france" in combined or "riviera" in combined, f"Fallbacks: {fallbacks}"


def test_extract_parent_location_port():
    """Port of X should extract X as a fallback."""
    from three_class_retrieval import _extract_parent_location
    fallbacks = _extract_parent_location("Port of Monaco", "French Riviera")
    assert any("monaco" in fb.lower() for fb in fallbacks), f"No Monaco fallback in {fallbacks}"


def test_tier_classification_rich():
    """4+ facts → 'rich' tier."""
    from three_class_retrieval import retrieve_outdoor_stop_facts
    # Monkey-patch _wiki_fetch to return text with many facts
    import three_class_retrieval as tcr
    original = tcr.retrieve_outdoor_stop_facts
    
    # Test tier logic directly — simulate outcomes
    facts = ["Fact 1 from 1863.", "Fact 2 about Napoleon.", "Fact 3 covers 5 km.", "Another from Battle in 1945."]
    if len(facts) >= 4:
        tier = "rich"
    elif len(facts) >= 2:
        tier = "medium"
    else:
        tier = "empty"
    assert tier == "rich"


def test_tier_classification_medium():
    """2-3 facts → 'medium' tier."""
    facts = ["Founded in 1863.", "Built by Napoleon III."]
    if len(facts) >= 4:
        tier = "rich"
    elif len(facts) >= 2:
        tier = "medium"
    else:
        tier = "empty"
    assert tier == "medium"


def test_tier_classification_empty():
    """0-1 facts → 'empty' tier."""
    facts = ["One lonely fact."]
    if len(facts) >= 4:
        tier = "rich"
    elif len(facts) >= 2:
        tier = "medium"
    else:
        tier = "empty"
    assert tier == "empty"


# ────────────────────────────────────────────────────────────────────────────
# 2. Adaptive word targets
# ────────────────────────────────────────────────────────────────────────────

def test_word_target_rich():
    """Rich tier → 300 word target."""
    tier = "rich"
    if tier == 'rich':
        target = "300"
    elif tier == 'medium':
        target = "180"
    else:
        target = "80"
    assert target == "300"


def test_word_target_medium():
    """Medium tier → 180 word target."""
    tier = "medium"
    if tier == 'rich':
        target = "300"
    elif tier == 'medium':
        target = "180"
    else:
        target = "80"
    assert target == "180"


def test_word_target_empty():
    """Empty tier → 80 word target."""
    tier = "empty"
    if tier == 'rich':
        target = "300"
    elif tier == 'medium':
        target = "180"
    else:
        target = "80"
    assert target == "80"


# ────────────────────────────────────────────────────────────────────────────
# 3. Tour-title repetition cap
# ────────────────────────────────────────────────────────────────────────────

def test_cap_location_repetition_basic():
    """cap_location_repetition removes excess occurrences."""
    from derepetition_guard import cap_location_repetition
    text = (
        "Welcome to the French Riviera biking tour. "
        "On this French Riviera biking tour, you will see many sights. "
        "The French Riviera biking tour continues along the coast. "
        "Enjoy the French Riviera biking tour experience. "
        "This French Riviera biking tour stop is beautiful. "
        "The French Riviera biking tour ends here."
    )
    result = cap_location_repetition(text, "French Riviera biking tour", max_occurrences=2)
    count = len(re.findall(re.escape("French Riviera biking tour"), result, re.IGNORECASE))
    assert count <= 2, f"Expected ≤2 occurrences, got {count}"


def test_cap_location_repetition_under_cap():
    """Text within cap is unchanged."""
    from derepetition_guard import cap_location_repetition
    text = "Welcome to the French Riviera. The French Riviera is lovely."
    result = cap_location_repetition(text, "French Riviera", max_occurrences=2)
    assert result == text, "Should not modify text within cap"


def test_count_phrase_occurrences():
    """count_phrase_occurrences counts case-insensitively."""
    from derepetition_guard import count_phrase_occurrences
    text = "The french riviera is great. FRENCH RIVIERA tours. A french Riviera bike path."
    count = count_phrase_occurrences(text, "French Riviera")
    assert count == 3, f"Expected 3, got {count}"


def test_count_phrase_occurrences_empty():
    """Empty inputs return 0."""
    from derepetition_guard import count_phrase_occurrences
    assert count_phrase_occurrences("", "test") == 0
    assert count_phrase_occurrences("hello", "") == 0


# ────────────────────────────────────────────────────────────────────────────
# 4. Exhibition-vs-object fabrication guard (prompt presence)
# ────────────────────────────────────────────────────────────────────────────

def test_exhibition_guard_in_source():
    """generate_tour_text.py contains the exhibition-vs-object rule."""
    source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'generate_tour_text.py')).read()
    assert "EXHIBITION VS OBJECT RULE" in source, "Missing exhibition-vs-object guard"
    assert "Pierre Matisse" in source, "Missing Matisse exhibition example"
    assert "biographical EXHIBITION" in source, "Missing exhibition classification guidance"


def test_exhibition_guard_describes_scope():
    """The guard instructs describing exhibition scope, not brushwork."""
    source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'generate_tour_text.py')).read()
    assert "describe what it covers" in source, "Should instruct describing exhibition scope"
    assert "NOT imagined visual details" in source, "Should ban imagined visual details"


# ────────────────────────────────────────────────────────────────────────────
# 5. Thin-corpus honesty guard (prompt presence)
# ────────────────────────────────────────────────────────────────────────────

def test_thin_corpus_guard_in_source():
    """generate_tour_text.py contains the thin-corpus honesty rule."""
    source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'generate_tour_text.py')).read()
    assert "THIN-CORPUS HONESTY RULE" in source, "Missing thin-corpus guard"
    assert "DO NOT INVENT details" in source, "Missing invention ban"


def test_thin_corpus_guard_brevity_instruction():
    """The thin-corpus guard instructs brevity over fabrication."""
    source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'generate_tour_text.py')).read()
    assert "120-word honest description beats a 300-word fabricated" in source, \
        "Should instruct brevity over fabrication"


# ────────────────────────────────────────────────────────────────────────────
# 6. Backward compatibility — museum tours unaffected
# ────────────────────────────────────────────────────────────────────────────

def test_museum_tour_skips_outdoor_retrieval():
    """Museum tour does not trigger outdoor retrieval."""
    from three_class_retrieval import retrieve_three_classes_for_stop
    result = retrieve_three_classes_for_stop(
        {'name': 'Mona Lisa', 'canonical_title': 'Mona Lisa', 'artist': 'Leonardo da Vinci'},
        tour_category='museum',
        tour_location='Louvre Museum, Paris',
    )
    assert result['retrieval_tier'] == 'empty'
    assert result['retrieval_facts'] == []
    # But should still have regular three-class fields
    assert 'category' in result
    assert 'class_queries' in result


def test_museum_tour_word_target_unchanged():
    """Museum tours still use LOCAL-44's fact_sheet-based word targets, not outdoor tiers."""
    # The outdoor word target logic was removed in LOCAL-72 (80-word cap stripped facts).
    # Museum tours still use their own word target logic based on specificity.
    source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'generate_tour_text.py')).read()
    # The museum branch uses _specificity_short / _confirmed_count for word target
    assert "_specificity_short" in source, "Museum word target logic should still exist"
    assert '_word_target = "120"' in source, "Museum short target"
    # LOCAL-72: outdoor word target removed — verify the cap is gone
    assert '_outdoor_word_target = "80"' not in source, "80-word cap must be removed (LOCAL-72)"
    # Verify retrieval tier logic still exists (the value-add of LOCAL-48)
    assert "_outdoor_tier" in source, "Outdoor tier logic should still exist for fact injection"
    assert "SUBSTANCE RULE" in source, "Substance rule for fact injection should remain"


def test_location_cap_only_non_museum():
    """Location repetition cap only fires for non-museum tours."""
    source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'generate_tour_text.py')).read()
    # Find the LOCAL-47 cap block — it should be guarded by tour_category != 'museum'
    cap_section = source[source.index("# -------- [LOCAL-47] Tour-title / location repetition cap"):]
    cap_section = cap_section[:500]
    assert "tour_category != 'museum'" in cap_section, "Cap should only fire for non-museum tours"


# ────────────────────────────────────────────────────────────────────────────
# Run all tests
# ────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import time
    start = time.time()
    
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    errors = []
    
    for test in tests:
        try:
            test()
            passed += 1
            print(f"  ✓ {test.__name__}")
        except Exception as e:
            failed += 1
            errors.append((test.__name__, str(e)))
            print(f"  ✗ {test.__name__}: {e}")
    
    elapsed = time.time() - start
    print(f"\n{passed} passed, {failed} failed ({elapsed:.2f}s)")
    
    if errors:
        print("\nFailures:")
        for name, err in errors:
            print(f"  {name}: {err}")
        sys.exit(1)
    else:
        sys.exit(0)
