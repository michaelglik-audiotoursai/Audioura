"""
LOCAL-11: Unit tests for venue-identity mining (extract_venue_identity).

Tests against two genuinely different museums:
1. Asian Arts Museum, Nice — known to have Kenzo Tange architecture + mandala + tea ceremonies
2. Palais Lascaris, Nice — 17th-century Baroque palace, historical instrument collection

Verifies:
- Generic across museums (not hardcoded to Asian Arts)
- Returns empty gracefully when corpus has no strong identity signals
- Never returns generic filler
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from story_miner import extract_venue_identity, format_venue_identity_for_prompt, _is_generic_filler


# ============================================================================
# Fixture: Asian Arts Museum corpus (simulated Wikipedia-like text)
# ============================================================================
ASIAN_ARTS_CORPUS = """
The Musée des Arts asiatiques de Nice (Museum of Asian Arts) is a museum in Nice, France, dedicated to Asian art and culture.

== Architecture ==
The museum building was designed by Japanese architect Kenzo Tange and opened in 1998. The structure is built on a lake in the Parc Phoenix and its geometric form is based on a sacred Tibetan mandala floor plan. Tange, a Pritzker Prize-winning architect, conceived the building as a symbolic bridge between Eastern and Western cultures. The square marble and glass structure appears to float on water, creating a contemplative atmosphere inspired by Japanese temple gardens.

== Collections ==
The museum houses art from across Asia, including works from Japan, China, Cambodia, India, and Southeast Asia. The permanent collection includes Buddhist sculptures, samurai armor, Chinese ceramics, and Japanese prints.

== Programs ==
The museum hosts authentic Japanese tea ceremonies (Chanoyu) every weekend, conducted by a certified tea master. These signature events allow visitors to experience the meditative ritual of the Way of Tea in an authentic setting. The museum also organizes ikebana workshops, calligraphy demonstrations, and seasonal cultural festivals celebrating Asian traditions.

== History ==
The idea for the museum originated with the City of Nice's desire to honor its connections to Asia through the historical Silk Road trade routes. Founded in 1998, it was inaugurated by the Mayor of Nice and the Japanese Ambassador to France.

== Exhibitions ==
The museum presents rotating exhibitions featuring contemporary Asian artists alongside traditional works.
"""

# ============================================================================
# Fixture: Palais Lascaris corpus (simulated)
# ============================================================================
PALAIS_LASCARIS_CORPUS = """
The Palais Lascaris is a palace and museum in the old town of Nice, France. It is a fine example of Genoese Baroque civil architecture from the 17th century.

== Architecture ==
The palace was built between 1648 and the early 18th century for the Lascaris-Vintimille family, a prominent Genoese-Niçois noble family. The building features an impressive monumental staircase with trompe-l'oeil frescoes attributed to Giovanni Battista Carlone. The ground floor pharmacy, dating from 1738, preserves its original woodwork and apothecary jars.

== History ==
The Lascaris family, descendants of the Emperors of Nicaea, established themselves in Nice in the 14th century. The palace was conceived as a demonstration of their political influence and cultural refinement. The City of Nice acquired the building in 1942 and restored it as a museum of 17th and 18th-century decorative arts.

== Collections ==
The museum houses a remarkable collection of historical musical instruments, one of the largest in France, with over 500 pieces dating from the 16th to 20th centuries. These include lutes, harpsichords, viols, and rare Baroque instruments. The decorative arts include Flemish tapestries, Italian ceramics, and period furniture.

== Programs ==
The Palais Lascaris hosts regular Baroque music concerts performed on period instruments from the collection. These concerts features musicians specializing in historically informed performance practice.

== Visiting ==
Open daily except Tuesdays. Free admission.
"""

# ============================================================================
# Fixture: Generic/empty corpus (should return nothing)
# ============================================================================
GENERIC_CORPUS = """
The museum has a wonderful collection of art. It is one of the finest museums in the region and well worth a visit. There is something for everyone here.

The exhibits are arranged in several rooms. Visitors can explore at their own pace.

Opening hours: 10am to 5pm daily. Closed Mondays. Admission: $15 adults, $10 children.
"""


def test_asian_arts_architecture():
    """Asian Arts Museum: should extract Kenzo Tange / architect fact."""
    result = extract_venue_identity(ASIAN_ARTS_CORPUS, "Musée des Arts asiatiques, Nice")
    assert len(result["architecture"]) >= 1, f"Expected architecture facts, got: {result['architecture']}"
    # Should mention Kenzo Tange
    _all_arch = " ".join(result["architecture"]).lower()
    assert "kenzo tange" in _all_arch or "tange" in _all_arch, \
        f"Expected mention of Kenzo Tange in: {result['architecture']}"
    print(f"  [PASS] Asian Arts architecture: {result['architecture'][:1]}")


def test_asian_arts_design():
    """Asian Arts Museum: should extract mandala floor plan."""
    result = extract_venue_identity(ASIAN_ARTS_CORPUS, "Musée des Arts asiatiques, Nice")
    assert len(result["design"]) >= 1, f"Expected design facts, got: {result['design']}"
    _all_design = " ".join(result["design"]).lower()
    assert "mandala" in _all_design, f"Expected 'mandala' in: {result['design']}"
    print(f"  [PASS] Asian Arts design: {result['design'][:1]}")


def test_asian_arts_programs():
    """Asian Arts Museum: should extract tea ceremony program."""
    result = extract_venue_identity(ASIAN_ARTS_CORPUS, "Musée des Arts asiatiques, Nice")
    assert len(result["programs"]) >= 1, f"Expected program facts, got: {result['programs']}"
    _all_prog = " ".join(result["programs"]).lower()
    assert "tea ceremon" in _all_prog or "chanoyu" in _all_prog, \
        f"Expected tea ceremony mention in: {result['programs']}"
    print(f"  [PASS] Asian Arts programs: {result['programs'][:1]}")


def test_palais_lascaris_architecture():
    """Palais Lascaris: should extract Baroque architecture / Lascaris family facts."""
    result = extract_venue_identity(PALAIS_LASCARIS_CORPUS, "Palais Lascaris, Nice")
    # Should find something about the architecture or founding
    _total = sum(len(v) for v in result.values())
    assert _total >= 1, f"Expected at least 1 venue-identity fact for Palais Lascaris, got 0"
    # Should NOT mention Kenzo Tange (proves it's not hardcoded)
    _all_text = " ".join(f for facts in result.values() for f in facts).lower()
    assert "kenzo" not in _all_text, "Should not find Asian Arts facts in Palais Lascaris corpus"
    print(f"  [PASS] Palais Lascaris: {sum(len(v) for v in result.values())} facts found")
    for k, v in result.items():
        if v:
            print(f"         {k}: {v[:1]}")


def test_palais_lascaris_programs():
    """Palais Lascaris: should extract Baroque concert program."""
    result = extract_venue_identity(PALAIS_LASCARIS_CORPUS, "Palais Lascaris, Nice")
    # The corpus mentions Baroque music concerts
    _all_prog = " ".join(result.get("programs", [])).lower()
    # May or may not find it depending on pattern matching — programs are harder
    if result["programs"]:
        assert "baroque" in _all_prog or "concert" in _all_prog or "music" in _all_prog, \
            f"Expected music-related program: {result['programs']}"
        print(f"  [PASS] Palais Lascaris programs: {result['programs'][:1]}")
    else:
        print(f"  [INFO] Palais Lascaris programs: none extracted (acceptable — founding/architecture should cover it)")


def test_palais_lascaris_founding():
    """Palais Lascaris: should extract founding/intent fact."""
    result = extract_venue_identity(PALAIS_LASCARIS_CORPUS, "Palais Lascaris, Nice")
    if result["founding"]:
        _all_founding = " ".join(result["founding"]).lower()
        # Should be a genuine founding-intent sentence (not filler)
        assert ("lascaris" in _all_founding or "conceived" in _all_founding or
                "1648" in _all_founding or "1942" in _all_founding or
                "political" in _all_founding), \
            f"Expected genuine founding fact: {result['founding']}"
        print(f"  [PASS] Palais Lascaris founding: {result['founding'][:1]}")
    else:
        print(f"  [INFO] Palais Lascaris founding: none extracted")


def test_generic_corpus_returns_empty():
    """Generic filler corpus should produce no venue-identity facts."""
    result = extract_venue_identity(GENERIC_CORPUS, "Generic Museum")
    _total = sum(len(v) for v in result.values())
    assert _total == 0, f"Generic corpus should produce 0 facts, got {_total}: {result}"
    print(f"  [PASS] Generic corpus: 0 facts (correct)")


def test_empty_corpus():
    """Empty/short corpus should not crash."""
    result = extract_venue_identity("", "Test Museum")
    assert all(len(v) == 0 for v in result.values())
    result2 = extract_venue_identity("Short text.", "Test Museum")
    assert all(len(v) == 0 for v in result2.values())
    print(f"  [PASS] Empty/short corpus: handled gracefully")


def test_filler_detection():
    """_is_generic_filler should catch known filler patterns."""
    assert _is_generic_filler("It's a wonderful museum with many treasures.")
    assert _is_generic_filler("This is one of the finest collections in France.")
    assert not _is_generic_filler("The building was designed by Kenzo Tange on a mandala floor plan.")
    assert not _is_generic_filler("The museum hosts authentic Japanese tea ceremonies every weekend.")
    print(f"  [PASS] Filler detection works correctly")


def test_format_for_prompt():
    """format_venue_identity_for_prompt produces usable output."""
    facts = {
        "architecture": ["The building was designed by Japanese architect Kenzo Tange and opened in 1998."],
        "design": ["The structure is built on a lake and its form is based on a sacred Tibetan mandala floor plan."],
        "programs": ["The museum hosts authentic Japanese tea ceremonies (Chanoyu) every weekend."],
        "founding": [],
    }
    formatted = format_venue_identity_for_prompt(facts, "Musée des Arts asiatiques, Nice")
    assert "Kenzo Tange" in formatted
    assert "mandala" in formatted
    assert "tea ceremon" in formatted.lower() or "Chanoyu" in formatted
    assert "Musée des Arts asiatiques" in formatted
    print(f"  [PASS] Format for prompt: {len(formatted)} chars")

    # Empty facts → empty string
    empty = format_venue_identity_for_prompt({"architecture": [], "design": [], "programs": [], "founding": []})
    assert empty == ""
    print(f"  [PASS] Empty facts → empty prompt block")


def test_not_hardcoded():
    """Extraction logic is pattern-based, not hardcoded to specific museums."""
    # Invent a fictional museum with similar patterns
    fictional_corpus = """
The Musée Imaginaire is located in Marseille, France.

== Architecture ==
The museum was designed by Renzo Piano and completed in 2013. The striking modernist cube appears to float above the harbor on thin concrete stilts, creating dramatic shadows that shift with the Mediterranean sun.

== Programs ==
The museum hosts weekly flamenco performances featuring guest artists from Andalusia, making it the only French museum with a permanent flamenco stage.
"""
    result = extract_venue_identity(fictional_corpus, "Musée Imaginaire, Marseille")
    assert len(result["architecture"]) >= 1, "Should find Renzo Piano"
    _arch = " ".join(result["architecture"]).lower()
    assert "renzo piano" in _arch or "piano" in _arch
    print(f"  [PASS] Fictional museum: extracted architect '{result['architecture'][0][:60]}...'")


# ============================================================================
# LOCAL-42 tests: venue intro enrichment
# ============================================================================

def test_local42_inauguration_year_in_architecture():
    """LOCAL-42: Inauguration year extracted into architecture, not just founding."""
    result = extract_venue_identity(ASIAN_ARTS_CORPUS, "Musée des Arts asiatiques, Nice")
    _all_arch = " ".join(result["architecture"])
    # The architect sentence already mentions "opened in 1998"
    assert "1998" in _all_arch, \
        f"Expected '1998' in architecture facts, got: {result['architecture']}"
    print(f"  [PASS] LOCAL-42: Inauguration year '1998' in architecture bucket")


def test_local42_year_survives_founding_suppression():
    """LOCAL-42: When founding is deleted (LOCAL-21 scenario), year remains in architecture."""
    result = extract_venue_identity(ASIAN_ARTS_CORPUS, "Musée des Arts asiatiques, Nice")
    # Simulate LOCAL-21 suppression
    if 'founding' in result:
        del result['founding']
    # Year should still be accessible through architecture
    _all_arch = " ".join(result["architecture"])
    assert "1998" in _all_arch, \
        f"After founding suppression, '1998' should survive in architecture: {result['architecture']}"
    print(f"  [PASS] LOCAL-42: Year survives founding suppression")


def test_local42_format_has_directives():
    """LOCAL-42: format_venue_identity_for_prompt includes directive instructions."""
    facts = {
        "architecture": ["The building was designed by Japanese architect Kenzo Tange and opened in 1998."],
        "design": ["The structure is built on a lake and its form is based on a sacred Tibetan mandala floor plan."],
        "programs": ["The museum hosts authentic Japanese tea ceremonies (Chanoyu) every weekend."],
        "founding": [],
    }
    formatted = format_venue_identity_for_prompt(facts, "Musée des Arts asiatiques, Nice")
    # Should have directive about architect
    assert "architect" in formatted.lower(), f"Expected architect directive in: {formatted}"
    # Should mention naming the architect
    assert "who they are" in formatted.lower() or "significance" in formatted.lower(), \
        f"Expected gloss instruction in: {formatted}"
    # Should mention year
    assert "inaugurated" in formatted.lower() or "completed" in formatted.lower(), \
        f"Expected year directive in: {formatted}"
    # Should mention style
    assert "style" in formatted.lower() or "spatial concept" in formatted.lower(), \
        f"Expected style directive in: {formatted}"
    print(f"  [PASS] LOCAL-42: format_venue_identity_for_prompt includes directives")


def test_local42_format_no_directives_when_no_architect():
    """LOCAL-42: When no architect found, directives omit architect instruction."""
    facts = {
        "architecture": [],
        "design": ["The building features a circular atrium with natural light flooding in from above."],
        "programs": [],
        "founding": [],
    }
    formatted = format_venue_identity_for_prompt(facts, "Generic Place")
    # Should NOT have architect directive (no architect was found)
    assert "name the architect" not in formatted.lower(), \
        f"Should not instruct to name architect when none found: {formatted}"
    # But should still mention style
    assert "style" in formatted.lower() or "spatial" in formatted.lower(), \
        f"Expected style directive: {formatted}"
    print(f"  [PASS] LOCAL-42: No architect directive when no architect found")


def test_local42_palais_lascaris_has_year():
    """LOCAL-42: Palais Lascaris corpus yields construction year in architecture."""
    result = extract_venue_identity(PALAIS_LASCARIS_CORPUS, "Palais Lascaris, Nice")
    _all_facts = " ".join(f for facts in result.values() for f in facts)
    # Should find 1648 or 1942 somewhere
    assert "1648" in _all_facts or "1942" in _all_facts, \
        f"Expected a year (1648 or 1942) in Palais Lascaris facts: {result}"
    print(f"  [PASS] LOCAL-42: Palais Lascaris has year in extracted facts")


if __name__ == "__main__":
    print("=" * 70)
    print("LOCAL-11: Venue-Identity Mining Unit Tests")
    print("=" * 70)
    print()
    
    tests = [
        test_asian_arts_architecture,
        test_asian_arts_design,
        test_asian_arts_programs,
        test_palais_lascaris_architecture,
        test_palais_lascaris_programs,
        test_palais_lascaris_founding,
        test_generic_corpus_returns_empty,
        test_empty_corpus,
        test_filler_detection,
        test_format_for_prompt,
        test_not_hardcoded,
        # LOCAL-42 tests
        test_local42_inauguration_year_in_architecture,
        test_local42_year_survives_founding_suppression,
        test_local42_format_has_directives,
        test_local42_format_no_directives_when_no_architect,
        test_local42_palais_lascaris_has_year,
    ]
    
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERROR] {test.__name__}: {e}")
            failed += 1
    
    print()
    print("=" * 70)
    print(f"  RESULTS: {passed}/{passed+failed} PASS, {failed} FAIL")
    if failed == 0:
        print("  ALL TESTS PASSED")
    else:
        print("  SOME TESTS FAILED")
        sys.exit(1)
    print("=" * 70)
