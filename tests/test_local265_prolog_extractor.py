"""
LOCAL-265: Test suite for the prolog extractor across all three layout variants.

The prolog (tour-level description) has moved three times:
  - Round 16:  AFTER the Orientation line, as a separate paragraph
  - Round 17L: BEFORE the Orientation line (above it)
  - Round 17M: INSIDE the Orientation line (embedded, followed by directive + stop orientation)

The extractor must find the correct span in all three layouts, structurally.
It must NOT return a stop-specific paragraph or the full Orientation text.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prolog_structure_validator import (
    extract_prolog_from_tour_content,
    validate_prolog_structure,
    extract_stop_names_from_tour_content,
    extract_transport_mode_from_tour_content,
    detect_duplicate_tour_descriptions,
    _is_tour_level_description,
    _extract_tour_level_span,
    _is_sentence_tour_level,
    _is_directive_sentence,
    _is_stop_orientation_sentence,
)


# ─── Fixture paths ────────────────────────────────────────────────────────────

# Tour fixture data is embedded directly (tours/ is gitignored).
# These are the exact outputs from round 16 (LOCAL-259) and round 17M (LOCAL-264).

ROUND16_TOUR_CONTENT = """\
Step-by-Step Audio Guided Tour: French Riviera cycling tour, France - Cycling Tour
Tour-Category: walking

Stop 1: Cap d'Antibes

Address: Cap d'Antibes, 06160 Antibes, France

Coordinates: 43.5411, 7.1356

Type/Specialty: Scenic coastal area

Specific Examples: Beautiful beaches, luxury villas, panoramic views

Orientation: Start biking southwest on the coastal road, enjoy the sea breeze. Positioned on the French Riviera between Cannes and Nice, this cape stands as a testament to the region's rich cultural heritage. The largest yachting harbor in Europe, Antibes boasts a population of 77,637 as of 2023, making it a bustling seaside retreat.

You are about to embark on a cycling journey through the French Riviera. This route will take you from the opulent Cap d'Antibes to the ancient Eze Village, spanning approximately 28 kilometers of coastal terrain. The path winds through a landscape where artists like Monet found inspiration and where historical events shaped the region's identity. Claude Monet's artistic exploration in Antibes and Eze Village's strategic significance under the House of Savoy are testaments to the intertwined legacies of art and power in the French Riviera. In the stops ahead, you will encounter Monet's 1888 paintings at Cap d'Antibes and the 1706 destruction of Eze Village's fortifications during the War of the Spanish Succession.

Strolling along the winding Tire-Poil trail, the azure sea stretches endlessly before you, offering a breathtaking view of the Lerins Islands and the Mercantour heights. Amidst the luxurious villas that dot the landscape, a hidden gem awaits: the ancient Chapel of Garoupe. In 1888, Claude Monet first experimented with painting in series in this very region, producing masterpieces like "Morning at Antibes."

Directions: Hey there cyclist! Starting from Cap d'Antibes, pedal east along the scenic coastal road towards Nice.

Stop 2: Eze Village

Address: 06360 Eze, France

Coordinates: 43.7296, 7.3616

Type/Specialty: Medieval hilltop village

Specific Examples: Narrow cobblestone streets, exotic gardens, stunning views

Orientation: As you approach Eze Village, perched dramatically on a high cliff 427 meters above sea level, pause to take in the breathtaking views of the French Riviera below.
"""

ROUND17M_TOUR_CONTENT = """\
Step-by-Step Audio Guided Tour: French Riviera cycling tour, France - Cycling Tour
Tour-Category: walking

Stop 1: Cap Ferrat

Address: Cap Ferrat, 06230 Saint-Jean-Cap-Ferrat, France

Coordinates: 43.6804, 7.3316

Type/Specialty: Scenic coastal spot

Specific Examples: Beautiful views of the Mediterranean Sea, luxurious villas, coastal walkways

Orientation: You are about to embark on a cycling journey through the French Riviera. In 2012, Cap Ferrat was named the second most expensive residential location in the world, after Monaco, earning it the nickname 'Billionaires' Peninsula'. From the Celto-Ligurian tribes settling Cap Ferrat to the fortified stronghold of Eze under the House of Savoy, each stop unveils layers of the region's captivating past. In the stops ahead, you will explore the underground tunnels of Villa Ephrussi, used during WWII, and soak in the panoramic views of Eze Village, once inspiring perfume makers and visited by Walt Disney in 1956. Start biking south on the main road, enjoy the sea breeze along the way. Sparkling blue Mediterranean Sea is the gentle sea breeze carrying the scent of salt and pine trees. Villa Ephrussi de Rothschild rises elegantly above you, surrounded by terraced gardens and fountains.

Cap Ferrat, the 'Billionaires' Peninsula,' holds tales of ancient tribes and Lombard settlements dating back to the 6th century. Sant Ospizio, a hermit friar, once inhabited a tower on the Eastern part of the peninsula, adding a spiritual depth to its storied past. In the early 20th century, King Leopold II of Belgium graced this land with his estate, leaving behind the majestic Villa des Cedres, now in the hands of Marnier-Lapostolle.

Directions: Hey there cyclist! From Cap Ferrat, pedal eastward along the scenic coastal road.

Stop 2: Eze Village

Address: 06360 Eze, France

Coordinates: 43.7276, 7.3615

Type/Specialty: Medieval hilltop village

Specific Examples: Narrow cobblestone streets, ancient architecture, panoramic views

Orientation: Cliff is overlooking the azure Mediterranean Sea. Eze Village rises majestically above, perched 427 meters high, offering a commanding view of the French Riviera coastline.
"""


# ─── Boundary Row 1: Round 16 (prolog after Orientation, separate paragraph) ─

def test_round16_extraction():
    """Round 16: prolog is a separate paragraph AFTER the Orientation field.
    Must extract 'You are about to embark...' paragraph, not the Orientation text.
    """
    content = ROUND16_TOUR_CONTENT
    prolog = extract_prolog_from_tour_content(content)

    # Must contain tour-level language
    assert "You are about to embark" in prolog, f"Missing prolog start: {prolog[:80]}"
    assert "cycling journey" in prolog
    # Must NOT contain Orientation text (directive)
    assert "Start biking southwest" not in prolog, "Contains Orientation directive"
    # Must NOT contain stop-specific body paragraph
    assert "Tire-Poil trail" not in prolog, "Contains stop-specific text"

    print(f"\n  ROW 1 — Round 16 (prolog after Orientation):")
    print(f"    extracted: \"{prolog[:100]}...\"")
    print(f"    words: {len(prolog.split())}")
    print(f"    ✓ PASS")
    return prolog


# ─── Boundary Row 2: Round 17M (prolog inside Orientation line) ──────────────

def test_round17M_extraction():
    """Round 17M: prolog is INSIDE the Orientation field, before the directive.
    Must extract 'You are about to embark...' span WITHOUT the trailing
    directive ('Start biking south...') or stop orientation.
    """
    content = ROUND17M_TOUR_CONTENT
    prolog = extract_prolog_from_tour_content(content)

    # Must contain tour-level language
    assert "You are about to embark" in prolog, f"Missing prolog start: {prolog[:80]}"
    assert "cycling journey" in prolog
    # Must NOT contain directive
    assert "Start biking south" not in prolog, "Contains directive text"
    # Must NOT contain stop orientation
    assert "Sparkling blue Mediterranean" not in prolog, "Contains stop orientation"
    assert "Villa Ephrussi de Rothschild rises" not in prolog, "Contains stop orientation"

    print(f"\n  ROW 2 — Round 17M (prolog inside Orientation):")
    print(f"    extracted: \"{prolog[:100]}...\"")
    print(f"    words: {len(prolog.split())}")
    print(f"    ✓ PASS")
    return prolog


# ─── Boundary Row 3: No tour-level description at all ────────────────────────

def test_no_prolog_returns_empty():
    """A tour with no tour-level description must return empty and NOT
    accidentally return a stop-specific paragraph.
    """
    no_prolog_tour = """Step-by-Step Audio Guided Tour: French Riviera cycling tour, France - Cycling Tour
Tour-Category: walking

Stop 1: Cap d'Antibes

Address: Cap d'Antibes, 06160 Antibes, France

Coordinates: 43.5411, 7.1356

Type/Specialty: Scenic coastal area

Specific Examples: Beautiful beaches, luxury villas, panoramic views

Orientation: Start biking southwest on the coastal road, enjoy the sea breeze. The largest yachting harbor in Europe, Antibes boasts a population of 77,637 as of 2023.

Strolling along the winding Tire-Poil trail, the azure sea stretches endlessly before you. In 1888, Claude Monet first experimented with painting in series in this very region, producing masterpieces. The vibrant colors of the landscape come alive in his work.

Directions: Continue north.

Stop 2: Eze Village

Address: Eze, France

Coordinates: 43.7296, 7.3616
"""
    prolog = extract_prolog_from_tour_content(no_prolog_tour)

    assert prolog == "", f"Should return empty but got: {prolog[:80]}"

    print(f"\n  ROW 3 — No tour-level description:")
    print(f"    extracted: (empty)")
    print(f"    ✓ PASS — correctly returns empty")
    return prolog


# ─── Boundary Row 4: Round 16 prolog passes validation (0 errors) ────────────

def test_round16_prolog_validates_zero_errors():
    """The round 16 prolog must pass validation with zero errors."""
    content = ROUND16_TOUR_CONTENT
    prolog = extract_prolog_from_tour_content(content)
    stop_names = extract_stop_names_from_tour_content(content)
    mode = extract_transport_mode_from_tour_content(content)
    meta = {'transport_mode': mode, 'stop_names': stop_names}

    violations = validate_prolog_structure(prolog, meta)
    errors = [v for v in violations if v['severity'] == 'error']

    print(f"\n  ROW 4 — Round 16 validation:")
    print(f"    violations: {len(violations)} total, {len(errors)} errors")
    for v in violations:
        print(f"      [{v['severity']}] Part {v['part']}: {v['code']}")
    assert len(errors) == 0, f"Round 16 prolog must pass with zero errors, got: {errors}"
    print(f"    ✓ PASS — 0 errors")
    return violations


# ─── Boundary Row 5: Round 15 opening must FAIL ─────────────────────────────

def test_round15_opening_fails():
    """Round 15's opening must fail validation (reference failure)."""
    round15 = (
        "From the secluded allure of Cap d'Antibes to the medieval whispers of "
        "Eze Village, each stop reveals a layer of history and culture that has "
        "shaped the French Riviera into the destination it is today."
    )
    meta = {
        'transport_mode': 'bike',
        'tour_name': 'French Riviera cycling tour',
        'stop_names': ["Cap d'Antibes", 'Eze Village'],
    }
    violations = validate_prolog_structure(round15, meta)
    errors = [v for v in violations if v['severity'] == 'error']

    print(f"\n  ROW 5 — Round 15 opening (must FAIL):")
    print(f"    text: \"{round15[:80]}...\"")
    print(f"    violations: {len(violations)} total, {len(errors)} errors")
    for v in violations:
        print(f"      [{v['severity']}] Part {v['part']}: {v['code']}")
    assert len(errors) > 0, "Round 15 must produce errors"
    print(f"    ✓ FAIL (as expected)")
    return violations


# ─── Boundary Row 6: Keyword-stuffed decoy must FAIL ─────────────────────────

def test_keyword_stuffed_decoy_fails():
    """A keyword-stuffed prolog must fail (anti-gaming)."""
    stuffed = (
        "Cycling tour. Bike. French Riviera. "
        "Flat terrain, 30 km distance from Nice to Antibes. "
        "History and culture, a rich tapestry of art and heritage. "
        "Stories await in the stops."
    )
    meta = {
        'transport_mode': 'bike',
        'tour_name': 'French Riviera cycling tour',
        'stop_names': ["Cap d'Antibes", 'Antibes', 'Nice'],
    }
    violations = validate_prolog_structure(stuffed, meta)
    errors = [v for v in violations if v['severity'] == 'error']

    print(f"\n  ROW 6 — Keyword-stuffed decoy (must FAIL):")
    print(f"    text: \"{stuffed[:80]}...\"")
    print(f"    violations: {len(violations)} total, {len(errors)} errors")
    for v in violations:
        print(f"      [{v['severity']}] Part {v['part']}: {v['code']}")
    assert len(errors) > 0, "Keyword-stuffed decoy must produce errors"
    print(f"    ✓ FAIL (as expected)")
    return violations


# ─── Boundary Row 7: Two tour-level descriptions → DUPLICATE ────────────────

def test_duplicate_tour_description():
    """A tour with two tour-level descriptions must produce DUPLICATE_TOUR_DESCRIPTION."""
    tour_with_two = (
        "Step-by-Step Audio Guided Tour: French Riviera cycling tour\n"
        "Tour-Category: walking\n\n"
        "Stop 1: Cap d'Antibes\n\n"
        "Address: Cap d'Antibes, France\n\n"
        "Coordinates: 43.5411, 7.1356\n\n"
        "Orientation: You are about to embark on a cycling journey through the French Riviera. "
        "This route takes you from Cap d'Antibes to Eze Village, spanning 28 km of coastal terrain. "
        "Start biking southwest on the coastal road.\n\n"
        "On this cycling tour of the French Riviera, you will discover the stories "
        "that connect Cap d'Antibes to Eze Village through centuries of art and history.\n\n"
        "Directions: Continue north.\n\n"
        "Stop 2: Eze Village\n\n"
        "Address: Eze, France\n"
    )
    stop_names = ["Cap d'Antibes", "Eze Village"]
    dups = detect_duplicate_tour_descriptions(tour_with_two, stop_names)

    print(f"\n  ROW 7 — Duplicate tour descriptions (must produce DUPLICATE):")
    print(f"    violations: {len(dups)}")
    for v in dups:
        print(f"      [{v['severity']}] {v['code']}")
    assert len(dups) == 1, f"Expected 1 DUPLICATE, got {len(dups)}"
    assert dups[0]['code'] == 'DUPLICATE_TOUR_DESCRIPTION'
    print(f"    ✓ DUPLICATE_TOUR_DESCRIPTION detected")
    return dups


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 70)
    print("LOCAL-265: PROLOG EXTRACTOR — ALL THREE LAYOUTS + BOUNDARY ROWS")
    print("=" * 70)

    tests = [
        ("ROW 1: Round 16 extraction", test_round16_extraction),
        ("ROW 2: Round 17M extraction", test_round17M_extraction),
        ("ROW 3: No prolog → empty", test_no_prolog_returns_empty),
        ("ROW 4: Round 16 → 0 violations", test_round16_prolog_validates_zero_errors),
        ("ROW 5: Round 15 → violations", test_round15_opening_fails),
        ("ROW 6: Keyword-stuffed → violations", test_keyword_stuffed_decoy_fails),
        ("ROW 7: Duplicate → DUPLICATE_TOUR_DESCRIPTION", test_duplicate_tour_description),
    ]

    passed = 0
    failed = 0
    for name, t in tests:
        try:
            t()
            passed += 1
        except (AssertionError, FileNotFoundError) as e:
            print(f"\n  ✗ FAILED: {name}: {e}")
            failed += 1

    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
    print("=" * 70)

    if failed > 0:
        sys.exit(1)
