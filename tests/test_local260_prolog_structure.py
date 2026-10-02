"""
LOCAL-260: Test suite for the four-part prolog structure validator.

Validates that validate_prolog_structure correctly identifies:
1. Missing parts
2. Out-of-order parts
3. Insufficient substance in each part
4. Vague forward references (Part 4)
5. Keyword-stuffing that carries no substance

Reference failure: Round 15's opening must FAIL.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prolog_structure_validator import (
    validate_prolog_structure,
    _sentence_mentions_transport,
    _sentence_has_route_substance,
    _sentence_has_sourced_fact,
    _sentence_names_stop_content,
    extract_prolog_from_tour_content,
    extract_stop_names_from_tour_content,
    extract_transport_mode_from_tour_content,
    detect_duplicate_tour_descriptions,
    _is_tour_level_description,
)


# ─── Test Data ────────────────────────────────────────────────────────────────

# MUST PASS: A conforming four-part prolog
CONFORMING_PROLOG = (
    "You are about to embark on a cycling journey through the French Riviera. "
    "This is a biking route along the coastline from Nice to Antibes, covering "
    "approximately 30 kilometers of mostly flat coastal terrain with short elevated "
    "sections on the capes. "
    "The same sheltered shoreline that once required a 130-meter fortified street — "
    "the Rue Obscure, built in 1260 — later drew the Hôtel du Cap-Eden-Roc in 1870, "
    "the model for Fitzgerald's hotel in Tender Is the Night, and Claude Monet "
    "who first experimented with painting in series here in 1888. "
    "We will explore Monet's 1888 series at Antibes, the 1306 chapel at Èze, "
    "and the medieval fortress of Saint-Paul-de-Vence."
)

CONFORMING_META = {
    'transport_mode': 'bike',
    'tour_name': 'French Riviera cycling tour',
    'stop_names': ['Cap d\'Antibes', 'Èze Village', 'Saint-Paul-de-Vence'],
}

# MUST FAIL: Round 15's opening (the reference failure)
ROUND15_OPENING = (
    "From the secluded allure of Cap d'Antibes to the medieval whispers of "
    "Eze Village, each stop reveals a layer of history and culture that has "
    "shaped the French Riviera into the destination it is today."
)

ROUND15_META = {
    'transport_mode': 'bike',
    'tour_name': 'French Riviera cycling tour',
    'stop_names': ['Cap d\'Antibes', 'Eze Village'],
}

# MUST FAIL: Parts 3 and 1 swapped
SWAPPED_PROLOG = (
    "The Rue Obscure, built in 1260, later drew the Hôtel du Cap-Eden-Roc in 1870. "
    "You are about to embark on a cycling journey through the French Riviera. "
    "This is a biking route along the coastline from Nice to Antibes, covering "
    "approximately 30 kilometers of mostly flat coastal terrain. "
    "We will explore Monet's 1888 series at Antibes and the medieval fortress "
    "of Saint-Paul-de-Vence."
)

SWAPPED_META = {
    'transport_mode': 'bike',
    'tour_name': 'French Riviera cycling tour',
    'stop_names': ['Cap d\'Antibes', 'Saint-Paul-de-Vence'],
}

# MUST FAIL: "More stories await you in the stops of this tour." as Part 4
VAGUE_PART4_PROLOG = (
    "You are about to embark on a cycling journey through the French Riviera. "
    "This is a biking route along the coastline from Nice to Antibes, covering "
    "approximately 30 kilometers of mostly flat coastal terrain. "
    "The Rue Obscure was built in 1260 as a fortified street along the shore. "
    "More stories await you in the stops of this tour."
)

VAGUE_PART4_META = {
    'transport_mode': 'bike',
    'tour_name': 'French Riviera cycling tour',
    'stop_names': ['Cap d\'Antibes', 'Saint-Paul-de-Vence'],
}

# MUST PASS: Specific Part 4 reference
SPECIFIC_PART4 = "Monet's 1888 series at Antibes, and the 1306 chapel at Èze"

# MUST FAIL: Keyword-stuffed prolog carrying no substance
KEYWORD_STUFFED_PROLOG = (
    "Cycling tour. Bike. French Riviera. "
    "Flat terrain, 30 km distance from Nice to Antibes. "
    "History and culture, a rich tapestry of art and heritage. "
    "Stories await in the stops."
)

KEYWORD_STUFFED_META = {
    'transport_mode': 'bike',
    'tour_name': 'French Riviera cycling tour',
    'stop_names': ['Cap d\'Antibes', 'Antibes', 'Nice'],
}


# ─── TESTS ────────────────────────────────────────────────────────────────────

def test_conforming_prolog_passes():
    """A well-formed four-part prolog must produce zero errors."""
    violations = validate_prolog_structure(CONFORMING_PROLOG, CONFORMING_META)
    errors = [v for v in violations if v['severity'] == 'error']
    print(f"\n  CONFORMING PROLOG:")
    print(f"    violations: {len(violations)} total, {len(errors)} errors")
    for v in violations:
        print(f"      [{v['severity']}] Part {v['part']}: {v['code']} — {v['message']}")
    assert len(errors) == 0, f"Conforming prolog should pass but got errors: {errors}"
    print("    ✓ PASS — zero errors")


def test_round15_opening_fails():
    """Round 15's opening is the reference failure — it MUST fail."""
    violations = validate_prolog_structure(ROUND15_OPENING, ROUND15_META)
    errors = [v for v in violations if v['severity'] == 'error']
    print(f"\n  ROUND 15 OPENING (reference failure):")
    print(f"    text: \"{ROUND15_OPENING[:80]}...\"")
    print(f"    violations: {len(violations)} total, {len(errors)} errors")
    for v in violations:
        print(f"      [{v['severity']}] Part {v['part']}: {v['code']} — {v['message']}")
    assert len(errors) > 0, "Round 15 opening MUST fail validation"
    # Specifically: it should fail Part 1 (no transport named with tour context),
    # Part 2 (no route substance), Part 3 (no sourced facts), and Part 4 (vague)
    error_codes = {v['code'] for v in errors}
    assert 'PART1_MISSING' in error_codes or 'PART2_MISSING' in error_codes, \
        f"Round 15 should be missing structural parts, got: {error_codes}"
    print("    ✓ FAIL (as expected) — validator correctly rejects Round 15")


def test_swapped_parts_fail():
    """Parts 3 and 1 swapped must produce an ordering violation."""
    violations = validate_prolog_structure(SWAPPED_PROLOG, SWAPPED_META)
    errors = [v for v in violations if v['severity'] == 'error']
    print(f"\n  SWAPPED PARTS (3 before 1):")
    print(f"    violations: {len(violations)} total, {len(errors)} errors")
    for v in violations:
        print(f"      [{v['severity']}] Part {v['part']}: {v['code']} — {v['message']}")
    order_violations = [v for v in violations if v['code'] == 'PARTS_OUT_OF_ORDER']
    assert len(order_violations) > 0, "Swapped parts must produce PARTS_OUT_OF_ORDER"
    print("    ✓ FAIL (as expected) — ordering violation detected")


def test_vague_part4_fails():
    """'More stories await' as Part 4 must fail."""
    violations = validate_prolog_structure(VAGUE_PART4_PROLOG, VAGUE_PART4_META)
    errors = [v for v in violations if v['severity'] == 'error']
    print(f"\n  VAGUE PART 4 ('More stories await'):")
    print(f"    violations: {len(violations)} total, {len(errors)} errors")
    for v in violations:
        print(f"      [{v['severity']}] Part {v['part']}: {v['code']} — {v['message']}")
    p4_vague = [v for v in violations if v['code'] == 'PART4_VAGUE_PROMISE']
    assert len(p4_vague) > 0, "'More stories await' must produce PART4_VAGUE_PROMISE"
    print("    ✓ FAIL (as expected) — vague Part 4 detected")


def test_keyword_stuffing_fails():
    """A keyword-stuffed prolog carrying no substance must fail.
    
    This is the key anti-gaming test. The prolog contains:
    - 'cycling tour', 'bike' → would pass Part 1 if keyword-only
    - '30 km', 'flat terrain' → would pass Part 2
    - 'history and culture' → would pass Part 3 if fluff accepted
    - 'Stories await' → would pass Part 4 if vague accepted
    
    But it MUST fail because:
    - Part 1 says 'Cycling tour. Bike.' — no sentence with tour context
    - Part 3 has 'history and culture' without a single sourced fact
    - Part 4 is vague
    """
    violations = validate_prolog_structure(KEYWORD_STUFFED_PROLOG, KEYWORD_STUFFED_META)
    errors = [v for v in violations if v['severity'] == 'error']
    print(f"\n  KEYWORD-STUFFED PROLOG (anti-gaming test):")
    print(f"    text: \"{KEYWORD_STUFFED_PROLOG}\"")
    print(f"    violations: {len(violations)} total, {len(errors)} errors")
    for v in violations:
        print(f"      [{v['severity']}] Part {v['part']}: {v['code']} — {v['message']}")
    assert len(errors) > 0, "Keyword-stuffed prolog MUST fail"
    error_codes = {v['code'] for v in errors}
    # Must fail on Part 3 (no sourced facts) and Part 4 (vague)
    assert 'PART3_MISSING' in error_codes or 'PART4_VAGUE_PROMISE' in error_codes, \
        f"Keyword stuffing should fail on substance, got: {error_codes}"
    print("    ✓ FAIL (as expected) — keyword stuffing detected")


def test_empty_prolog_fails():
    """An empty prolog must produce PROLOG_MISSING."""
    violations = validate_prolog_structure("", {})
    assert any(v['code'] == 'PROLOG_MISSING' for v in violations)
    violations2 = validate_prolog_structure("   ", {})
    assert any(v['code'] == 'PROLOG_MISSING' for v in violations2)
    print("\n  EMPTY PROLOG: ✓ PROLOG_MISSING raised")


def test_specific_part4_passes():
    """A Part 4 that names specific stop content must pass Part 4 check."""
    # Build a prolog with all four parts, including specific Part 4
    full_prolog = (
        "You are about to embark on a cycling journey through the French Riviera. "
        "This is a biking route from Nice to Antibes, covering 30 kilometers "
        "of mostly flat coastal terrain. "
        "Claude Monet first experimented with painting in series here in 1888. "
        f"We will explore {SPECIFIC_PART4}."
    )
    meta = {
        'transport_mode': 'bike',
        'stop_names': ['Antibes', 'Èze'],
    }
    violations = validate_prolog_structure(full_prolog, meta)
    p4_errors = [v for v in violations if v['part'] == 4 and v['severity'] == 'error']
    print(f"\n  SPECIFIC PART 4 ('{SPECIFIC_PART4[:40]}...'):")
    print(f"    Part 4 errors: {len(p4_errors)}")
    for v in p4_errors:
        print(f"      [{v['severity']}] {v['code']} — {v['message']}")
    assert len(p4_errors) == 0, f"Specific Part 4 should pass but got: {p4_errors}"
    print("    ✓ PASS — specific Part 4 accepted")


def test_transport_detection_for_part1():
    """Part 1 detection must require transport mode in tour context, not bare keyword."""
    # Bare keyword should NOT pass
    assert not _sentence_mentions_transport("Bike.", 'bike')
    assert not _sentence_mentions_transport("Cycling is fun.", 'bike')
    # Transport with tour context SHOULD pass
    assert _sentence_mentions_transport(
        "You are about to embark on a cycling journey through the French Riviera.", 'bike')
    assert _sentence_mentions_transport(
        "This is a biking route along the coastline.", 'bike')
    print("\n  TRANSPORT DETECTION:")
    print("    ✓ Bare 'Bike.' → rejected")
    print("    ✓ 'Cycling is fun.' → rejected") 
    print("    ✓ 'cycling journey through...' → accepted")
    print("    ✓ 'biking route along...' → accepted")


def test_route_substance_detection():
    """Part 2 detection must require at least 2 indicators."""
    # One indicator only
    indicators = _sentence_has_route_substance("The terrain is flat and coastal.")
    assert 'terrain' in indicators
    assert len(indicators) < 2  # Just terrain, no endpoints/distance/duration
    
    # Two indicators
    indicators2 = _sentence_has_route_substance(
        "This is a 30-kilometer route along flat coastal terrain from Nice to Antibes."
    )
    assert len(indicators2) >= 2, f"Expected >=2, got {indicators2}"
    print(f"\n  ROUTE SUBSTANCE DETECTION:")
    print(f"    'flat and coastal' → {indicators} (insufficient)")
    print(f"    '30-km flat terrain from Nice to Antibes' → {indicators2} (sufficient)")
    print(f"    ✓ Threshold enforced correctly")


def test_sourced_fact_detection():
    """Part 3 detection must require year, named-person-action, or documented event."""
    # Vague fluff alone must NOT pass
    assert not _sentence_has_sourced_fact(
        "A rich tapestry of history and culture awaits.")
    assert not _sentence_has_sourced_fact(
        "Each stop reveals a layer of history and culture.")
    # Year must pass
    assert _sentence_has_sourced_fact(
        "The Rue Obscure was built in 1260 as a fortified street.")
    # Named person with action must pass
    assert _sentence_has_sourced_fact(
        "Claude Monet painted his famous series here in 1888.")
    # Event must pass
    assert _sentence_has_sourced_fact(
        "The siege of the fortress lasted three months.")
    print(f"\n  SOURCED FACT DETECTION:")
    print(f"    ✓ 'rich tapestry of history' → rejected")
    print(f"    ✓ 'layer of history and culture' → rejected")
    print(f"    ✓ 'built in 1260' → accepted")
    print(f"    ✓ 'Monet painted...1888' → accepted")
    print(f"    ✓ 'siege of the fortress' → accepted")


def test_extract_from_tour_content():
    """Can extract prolog from assembled tour_content format.
    
    LOCAL-260 bounce fix: the extractor must detect the prolog STRUCTURALLY
    (tour-level language) not positionally (first paragraph after Orientation).
    The round 16 format has Orientation as a separate field, and the prolog
    is the paragraph AFTER it.
    """
    # Round 16 format: Orientation is a structured field,
    # prolog is the body paragraph that addresses the tour as a whole
    sample_tour = """Step-by-Step Audio Guided Tour: French Riviera cycling tour
Tour-Category: walking

Stop 1: Cap d'Antibes

Address: Cap d'Antibes, France

Coordinates: 43.5411, 7.1206

Orientation: Start biking southwest on the coastal road, enjoy the sea breeze.

You are about to embark on a cycling journey through the French Riviera. This route takes you from Cap d'Antibes to Eze Village, covering 28 kilometers of coastal terrain.

The stop-specific description of Cap d'Antibes goes here with local details.

Directions: Continue north.

Stop 2: Eze Village

Address: Eze, France
"""
    prolog = extract_prolog_from_tour_content(sample_tour)
    assert "cycling journey" in prolog, f"Expected 'cycling journey' in prolog, got: {prolog[:100]}"
    # Must NOT return the Orientation text
    assert "Start biking southwest" not in prolog, \
        f"Extractor returned Orientation text, not prolog: {prolog[:100]}"
    stops = extract_stop_names_from_tour_content(sample_tour)
    assert "Cap d'Antibes" in stops
    mode = extract_transport_mode_from_tour_content(sample_tour)
    assert mode == 'bike'
    print(f"\n  EXTRACTION FROM TOUR CONTENT (round 16 format):")
    print(f"    prolog: \"{prolog[:80]}...\"")
    print(f"    stops: {stops}")
    print(f"    mode: {mode}")
    print(f"    ✓ Extracts prolog (not Orientation)")


def test_round16_real_prolog_passes():
    """The actual round 16 prolog — extracted from the real tour file — must PASS
    with zero violations.
    
    This is the LEAD bounce fix validation: the extractor must correctly identify
    the prolog paragraph, and the Part 4 check must not false-positive on the
    specific, dated forward reference.
    """
    # This is the exact paragraph from LOCAL259_riviera_2stop_round16.txt
    round16_prolog = (
        "You are about to embark on a cycling journey through the French Riviera. "
        "This route will take you from the opulent Cap d'Antibes to the ancient "
        "Eze Village, spanning approximately 28 kilometers of coastal terrain. "
        "The path winds through a landscape where artists like Monet found "
        "inspiration and where historical events shaped the region's identity. "
        "Claude Monet's artistic exploration in Antibes and Eze Village's strategic "
        "significance under the House of Savoy are testaments to the intertwined "
        "legacies of art and power in the French Riviera. "
        "In the stops ahead, you will encounter Monet's 1888 paintings at Cap "
        "d'Antibes and the 1706 destruction of Eze Village's fortifications "
        "during the War of the Spanish Succession."
    )
    meta = {
        'transport_mode': 'bike',
        'tour_name': 'French Riviera cycling tour',
        'stop_names': ["Cap d'Antibes", 'Eze Village'],
    }
    violations = validate_prolog_structure(round16_prolog, meta)
    errors = [v for v in violations if v['severity'] == 'error']
    print(f"\n  ROUND 16 REAL PROLOG:")
    print(f"    text: \"{round16_prolog[:100]}...\"")
    print(f"    violations: {len(violations)} total, {len(errors)} errors")
    for v in violations:
        print(f"      [{v['severity']}] Part {v['part']}: {v['code']} — {v['message'][:80]}")
    assert len(errors) == 0, f"Round 16 prolog must pass with zero errors, got: {errors}"
    print("    ✓ PASS — zero errors (bounce fix confirmed)")


def test_duplicate_tour_description_detected():
    """A tour with two tour-level descriptions must produce DUPLICATE_TOUR_DESCRIPTION."""
    tour_with_two = (
        "Step-by-Step Audio Guided Tour: French Riviera cycling tour\n"
        "Tour-Category: walking\n\n"
        "Stop 1: Cap d'Antibes\n\n"
        "Address: Cap d'Antibes, France\n\n"
        "Coordinates: 43.5411, 7.1356\n\n"
        "Orientation: Start biking southwest on the coastal road.\n\n"
        "You are about to embark on a cycling journey through the French Riviera. "
        "This route takes you from Cap d'Antibes to Eze Village, covering 28 km.\n\n"
        "On this cycling tour of the French Riviera, you will discover the stories "
        "that connect Cap d'Antibes to Eze Village through centuries of art.\n\n"
        "Directions: Continue north.\n\n"
        "Stop 2: Eze Village\n\n"
        "Address: Eze, France\n"
    )
    stop_names = ["Cap d'Antibes", "Eze Village"]
    dups = detect_duplicate_tour_descriptions(tour_with_two, stop_names)
    print(f"\n  DUPLICATE TOUR DESCRIPTION (two tour-level passages):")
    print(f"    violations: {len(dups)}")
    for v in dups:
        print(f"      [{v['severity']}] {v['code']}")
    assert len(dups) == 1, f"Expected 1 DUPLICATE_TOUR_DESCRIPTION, got {len(dups)}"
    assert dups[0]['code'] == 'DUPLICATE_TOUR_DESCRIPTION'
    print("    ✓ DUPLICATE_TOUR_DESCRIPTION detected")


def test_single_tour_description_passes():
    """A tour with exactly one tour-level description must NOT trigger DUPLICATE."""
    tour_with_one = (
        "Step-by-Step Audio Guided Tour: French Riviera cycling tour\n"
        "Tour-Category: walking\n\n"
        "Stop 1: Cap d'Antibes\n\n"
        "Address: Cap d'Antibes, France\n\n"
        "Coordinates: 43.5411, 7.1356\n\n"
        "Orientation: Start biking southwest on the coastal road.\n\n"
        "You are about to embark on a cycling journey through the French Riviera. "
        "This route takes you from Cap d'Antibes to Eze Village, covering 28 km.\n\n"
        "Strolling along the Tire-Poil trail, the azure sea stretches before you. "
        "In 1888, Claude Monet first painted in this region.\n\n"
        "Directions: Continue north.\n\n"
        "Stop 2: Eze Village\n\n"
        "Address: Eze, France\n"
    )
    stop_names = ["Cap d'Antibes", "Eze Village"]
    dups = detect_duplicate_tour_descriptions(tour_with_one, stop_names)
    print(f"\n  SINGLE TOUR DESCRIPTION (one tour-level passage):")
    print(f"    violations: {len(dups)}")
    assert len(dups) == 0, f"Single description should pass, got: {dups}"
    print("    ✓ No duplicate — PASS")


def test_part1_must_name_the_tour():
    """Part 1 that uses transport mode but never names what the tour IS must get a warning.
    
    Michael: 'the serious problem is that it does not name the tour'
    'From the secluded allure...' → FAIL (never says what it IS)
    'On this biking tour of French Riviera...' → PASS
    """
    meta = {'transport_mode': 'bike', 'stop_names': ["Cap d'Antibes", 'Eze Village']}
    
    # MUST FAIL: doesn't name the tour
    fail_prolog = (
        "From the secluded allure of Cap d'Antibes to the medieval whispers of Eze Village, "
        "this biking route covers 28 kilometers of coastal terrain. "
        "The Rue Obscure was built in 1260 as a fortified street. "
        "We will explore Monet's 1888 paintings at Cap d'Antibes and Eze Village's medieval fortress."
    )
    v1 = validate_prolog_structure(fail_prolog, meta)
    p1_issues = [v for v in v1 if v['part'] == 1]
    
    # MUST PASS: names the tour
    pass_prolog = (
        "On this biking tour of the French Riviera, from the secluded allure of Cap d'Antibes "
        "to the medieval whispers of Eze Village, this route covers 28 kilometers of coastal terrain. "
        "The Rue Obscure was built in 1260 as a fortified street. "
        "We will explore Monet's 1888 paintings at Cap d'Antibes and Eze Village's medieval fortress."
    )
    v2 = validate_prolog_structure(pass_prolog, meta)
    errors2 = [v for v in v2 if v['severity'] == 'error']
    
    print(f"\n  PART 1 NAMING TEST:")
    print(f"    'From the secluded allure...' → Part 1 issues: {len(p1_issues)}")
    for v in p1_issues:
        print(f"      [{v['severity']}] {v['code']}")
    print(f"    'On this biking tour of...' → errors: {len(errors2)}")
    
    assert len(p1_issues) > 0, "Must-fail case should have Part 1 naming issue"
    assert len(errors2) == 0, f"Must-pass case should have zero errors, got: {errors2}"
    print("    ✓ Naming requirement enforced correctly")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 70)
    print("LOCAL-260: PROLOG STRUCTURE VALIDATOR — BOUNDARY TESTS")
    print("=" * 70)
    
    tests = [
        test_conforming_prolog_passes,
        test_round15_opening_fails,
        test_swapped_parts_fail,
        test_vague_part4_fails,
        test_keyword_stuffing_fails,
        test_empty_prolog_fails,
        test_specific_part4_passes,
        test_transport_detection_for_part1,
        test_route_substance_detection,
        test_sourced_fact_detection,
        test_extract_from_tour_content,
        test_round16_real_prolog_passes,
        test_duplicate_tour_description_detected,
        test_single_tour_description_passes,
        test_part1_must_name_the_tour,
    ]
    
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"\n  ✗ FAILED: {t.__name__}: {e}")
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
    print("=" * 70)
    
    if failed > 0:
        sys.exit(1)
