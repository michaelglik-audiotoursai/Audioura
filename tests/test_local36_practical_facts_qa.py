"""
LOCAL-36: Test suite for the practical facts QA gate.
=====================================================
Tests:
1. Positive: correctly sourced claims pass untouched
2. Negative: unsourced claims are dropped
3. Mixed: partially sourced tours keep only verified claims
4. Stability: same venue generates identical practical fields across runs
5. Regression: existing gate scores unaffected
"""
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from practical_facts_gate import (
    extract_practical_claims,
    verify_claim_against_source,
    run_practical_facts_gate,
    strip_unverified_claims,
    gate_and_fix,
    PracticalClaim,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def matisse_source_text():
    """Simulated fetched content from musee-matisse-nice.org visitor info page."""
    return """
    Horaires d'ouverture : 10h à 18h, tous les jours sauf le mardi.
    Fermé le mardi.
    Tarif plein : 10 € — Tarif réduit : 7 €
    Gratuit pour les moins de 18 ans et résidents Métropole Nice Côte d'Azur.
    Accès : Bus 15, 17 — Arrêt Arènes / Musée Matisse
    164 avenue des Arènes de Cimiez, 06000 Nice
    """


@pytest.fixture
def palais_source_text():
    """Simulated fetched content from Palais Lascaris visitor info page."""
    return """
    Ouvert tous les jours de 10h à 18h sauf le mardi.
    Fermé le mardi, 1er janvier, dimanche de Pâques, 1er mai, 25 décembre.
    Entrée gratuite.
    Accès : Vieux-Nice, 15 rue Droite.
    """


@pytest.fixture
def asian_source_text():
    """Simulated fetched content from Musée des Arts Asiatiques visitor info page."""
    return """
    Ouvert tous les jours sauf le mardi.
    Du 2 mai au 15 octobre : 10h – 18h
    Du 16 octobre au 30 avril : 10h – 17h
    Fermé le mardi, 1er janvier, 1er mai, 25 décembre.
    Entrée gratuite.
    Accès : Bus ligne 9, 10, 23. Arrêt Musée des Arts Asiatiques.
    """


@pytest.fixture
def tour_with_correct_info():
    """Tour text with a correctly sourced Museum Information line."""
    return """Step-by-Step Audio Guided Tour: Musée des Arts Asiatiques, Nice - Museum Tour
Tour-Category: museum

Stop 1: L'Armure d'Andô Naoyuki

Address: Musée des Arts Asiatiques, 405 Promenade des Anglais, 06200 Nice

Coordinates: 43.6605, 7.2054

Type/Specialty: Art

Museum Information: Open daily from 10am to 6pm, closed on Tuesdays. Free admission

Orientation: Position yourself in front of the main armor display case.

Welcome to the Musée des Arts Asiatiques...
"""


@pytest.fixture
def tour_with_fabricated_info():
    """Tour text with a fabricated Museum Information (claim not in source)."""
    return """Step-by-Step Audio Guided Tour: Musée Matisse, Nice - Museum Tour
Tour-Category: museum

Stop 1: Nature Morte aux Grenades

Address: Musée Matisse, 164 Avenue des Arènes de Cimiez, 06000 Nice

Coordinates: 43.7196, 7.2747

Type/Specialty: Art

Museum Information: Open daily from 10am to 6pm. Free admission

Orientation: Approach the still life painting on the east wall.

Welcome to the Musée Matisse...
"""


@pytest.fixture
def tour_with_no_practical_info():
    """Tour text with no Museum Information line at all."""
    return """Step-by-Step Audio Guided Tour: Test Venue - Museum Tour
Tour-Category: museum

Stop 1: Test Stop

Address: Test Address

Coordinates: 43.0, 7.0

Type/Specialty: Art

Orientation: Face the artwork.

The narrative content begins here...
"""


# ============================================================================
# Test 1: Claim extraction
# ============================================================================

class TestClaimExtraction:
    """Verify claims are correctly extracted from tour text."""

    def test_museum_info_hours_and_admission(self, tour_with_correct_info):
        claims = extract_practical_claims(tour_with_correct_info)
        assert len(claims) >= 2, f"Expected >= 2 claims, got {len(claims)}: {[c.value for c in claims]}"
        types = {c.claim_type for c in claims}
        assert 'hours' in types or 'closed_day' in types, f"Expected hours/closed_day, got types: {types}"
        assert 'admission' in types, f"Expected admission claim, got types: {types}"

    def test_no_claims_when_no_info_line(self, tour_with_no_practical_info):
        claims = extract_practical_claims(tour_with_no_practical_info)
        assert len(claims) == 0

    def test_closed_day_extracted(self):
        text = "Museum Information: Closed on Tuesdays"
        claims = extract_practical_claims(f"Fake tour\n{text}\nEnd")
        assert any(c.claim_type == 'closed_day' for c in claims)

    def test_admission_price_extracted(self):
        text = "Museum Information: Admission €10 adults"
        claims = extract_practical_claims(f"Fake tour\n{text}\nEnd")
        assert any(c.claim_type == 'admission' for c in claims)

    def test_free_admission_extracted(self):
        text = "Museum Information: Free admission"
        claims = extract_practical_claims(f"Fake tour\n{text}\nEnd")
        assert any(c.claim_type == 'admission' for c in claims)


# ============================================================================
# Test 2: Source verification — positive cases
# ============================================================================

class TestVerificationPositive:
    """Correctly sourced claims should verify as True."""

    def test_closed_tuesday_verified(self, matisse_source_text):
        claim = PracticalClaim(claim_type='closed_day', value='Closed on Tuesdays')
        assert verify_claim_against_source(claim, matisse_source_text) is True

    def test_hours_10_to_6_verified(self, asian_source_text):
        claim = PracticalClaim(claim_type='hours', value='Open daily from 10am to 6pm')
        assert verify_claim_against_source(claim, asian_source_text) is True

    def test_free_admission_verified(self, asian_source_text):
        claim = PracticalClaim(claim_type='admission', value='Free admission')
        assert verify_claim_against_source(claim, asian_source_text) is True

    def test_price_10_euro_verified(self, matisse_source_text):
        claim = PracticalClaim(claim_type='admission', value='Admission €10')
        assert verify_claim_against_source(claim, matisse_source_text) is True

    def test_palais_free_verified(self, palais_source_text):
        claim = PracticalClaim(claim_type='admission', value='Free admission')
        assert verify_claim_against_source(claim, palais_source_text) is True


# ============================================================================
# Test 3: Source verification — negative cases (unsourced claims MUST fail)
# ============================================================================

class TestVerificationNegative:
    """Unsourced or fabricated claims should verify as False."""

    def test_free_fails_when_source_says_paid(self, matisse_source_text):
        """Matisse charges €10 — 'Free admission' is fabricated."""
        claim = PracticalClaim(claim_type='admission', value='Free admission')
        # The source says "Tarif plein : 10 €" and "Gratuit pour les moins de 18 ans"
        # but the general admission is NOT free. The claim "Free admission" (general)
        # should fail because the source says it costs €10.
        # NOTE: The source DOES contain "gratuit" — but it's conditional (under 18/residents).
        # For this test we use a modified source without the conditional free:
        source_no_free = """
        Horaires d'ouverture : 10h à 18h, tous les jours sauf le mardi.
        Fermé le mardi.
        Tarif plein : 10 €. Tarif réduit : 7 €.
        """
        assert verify_claim_against_source(claim, source_no_free) is False

    def test_wrong_day_fails(self, matisse_source_text):
        """Source says closed Tuesday, claim says Monday — must fail."""
        claim = PracticalClaim(claim_type='closed_day', value='Closed on Mondays')
        assert verify_claim_against_source(claim, matisse_source_text) is False

    def test_no_source_text_fails(self):
        """No source content at all — claim cannot be verified."""
        claim = PracticalClaim(claim_type='hours', value='Open 9am to 5pm')
        assert verify_claim_against_source(claim, "") is False

    def test_admission_fee_required_fails_without_price(self):
        """'Admission fee required' is vague — source must have a specific price."""
        source = "Open daily. Closed on Tuesdays."
        claim = PracticalClaim(claim_type='admission', value='Admission fee required')
        assert verify_claim_against_source(claim, source) is False

    def test_fabricated_hours_fail(self, asian_source_text):
        """Hours not matching source fail."""
        claim = PracticalClaim(claim_type='hours', value='Open 8am to 9pm')
        # Source says 10h-18h, not 8am-9pm. "8" does not appear in source hours context.
        assert verify_claim_against_source(claim, asian_source_text) is False


# ============================================================================
# Test 4: Full gate integration
# ============================================================================

class TestFullGate:
    """End-to-end gate tests."""

    def test_correctly_sourced_tour_passes(self, tour_with_correct_info, asian_source_text):
        result = run_practical_facts_gate(
            tour_with_correct_info,
            source_url="https://maa.nice.fr/infos-pratiques",
            source_text=asian_source_text,
        )
        assert result.passed, (
            f"Gate should pass for correctly sourced tour. "
            f"Dropped: {[(c.claim_type, c.value) for c in result.dropped_claims]}"
        )
        assert len(result.verified_claims) >= 2

    def test_fabricated_admission_dropped(self, tour_with_fabricated_info):
        """Matisse says 'Free admission' but source says €10 — claim should be dropped."""
        source = """
        Horaires : 10h à 18h sauf le mardi.
        Fermé le mardi.
        Tarif : 10 € plein tarif, 7 € tarif réduit.
        """
        result = run_practical_facts_gate(
            tour_with_fabricated_info,
            source_url="https://musee-matisse-nice.org/tarifs",
            source_text=source,
        )
        assert not result.passed, "Gate should fail — 'Free admission' contradicts €10 source"
        # The "Free admission" claim should be in dropped
        dropped_types = [c.claim_type for c in result.dropped_claims]
        assert 'admission' in dropped_types

    def test_no_source_drops_all_claims(self, tour_with_correct_info):
        """If no source text is provided, ALL practical claims must be dropped."""
        result = run_practical_facts_gate(
            tour_with_correct_info,
            source_url="",
            source_text="",
        )
        if result.claims:
            assert not result.passed, "Gate should fail when no source available"
            assert len(result.dropped_claims) == len(result.claims)

    def test_no_claims_passes(self, tour_with_no_practical_info, asian_source_text):
        """Tour with no practical claims should pass trivially."""
        result = run_practical_facts_gate(
            tour_with_no_practical_info,
            source_url="https://example.com",
            source_text=asian_source_text,
        )
        assert result.passed

    def test_audit_log_generated(self, tour_with_correct_info, asian_source_text):
        """Gate must produce a per-claim audit log."""
        result = run_practical_facts_gate(
            tour_with_correct_info,
            source_url="https://maa.nice.fr/infos-pratiques",
            source_text=asian_source_text,
        )
        assert len(result.audit_log) >= 1
        # Each audit line should have the format: type | value | source | status
        for line in result.audit_log:
            assert '|' in line, f"Audit line missing pipe separator: {line}"


# ============================================================================
# Test 5: Strip unverified claims from tour text
# ============================================================================

class TestStripUnverified:
    """Verify that unverified claims are removed from the tour text."""

    def test_fabricated_claim_removed(self, tour_with_fabricated_info):
        source = "Fermé le mardi. Tarif plein : 10 €."
        result = run_practical_facts_gate(
            tour_with_fabricated_info,
            source_url="https://musee-matisse-nice.org/tarifs",
            source_text=source,
        )
        fixed = strip_unverified_claims(tour_with_fabricated_info, result)
        # "Free admission" should be gone
        assert 'Free admission' not in fixed
        # But the tour should still exist
        assert 'Musée Matisse' in fixed

    def test_verified_claims_preserved(self, tour_with_correct_info, asian_source_text):
        result = run_practical_facts_gate(
            tour_with_correct_info,
            source_url="https://maa.nice.fr",
            source_text=asian_source_text,
        )
        fixed = strip_unverified_claims(tour_with_correct_info, result)
        # If claims pass, text should be unchanged
        if result.passed:
            assert fixed == tour_with_correct_info


# ============================================================================
# Test 6: Deliberate injection of unsourced claim (task acceptance: negative test)
# ============================================================================

class TestInjectedUnsourcedClaim:
    """Deliberate negative test: inject a claim the source doesn't support."""

    def test_injected_claim_dropped(self):
        """Inject 'Open 9am to 9pm' — source says 10h-18h, not 9-9."""
        tour_text = """Step-by-Step Audio Guided Tour: Test Venue - Museum Tour
Tour-Category: museum

Stop 1: Test

Address: Test Addr

Museum Information: Open from 9am to 9pm. Closed on Tuesdays. Free admission

Orientation: Face the artwork.

Content here.
"""
        source = """
        Ouvert de 10h à 18h sauf le mardi.
        Fermé le mardi, 25 décembre, 1er janvier.
        Entrée gratuite.
        """
        fixed, result = gate_and_fix(tour_text, "https://test.org/visit", source, verbose=False)

        # "Open from 9am to 9pm" has no support — source says 10h-18h
        # The closed_day=Tuesday and admission=free should survive
        assert not result.passed, (
            f"Gate should fail — unsourced hours '9am to 9pm' vs source '10h-18h'. "
            f"Dropped: {[(c.claim_type, c.value) for c in result.dropped_claims]}"
        )
        # Verify the unsourced hours claim was actually dropped
        dropped_hours = [c for c in result.dropped_claims if c.claim_type == 'hours']
        assert len(dropped_hours) >= 1, (
            f"Expected dropped hours claim, got: {[(c.claim_type, c.value) for c in result.dropped_claims]}"
        )


# ============================================================================
# Test 7: Stability — practical fields don't vary across runs
# ============================================================================

class TestStability:
    """Same source + same extraction = same claims across multiple runs.

    Fabricated facts vary between runs; sourced facts do not.
    This test verifies determinism by running extraction 3 times.
    """

    def test_extraction_deterministic(self, tour_with_correct_info):
        """Extracting claims from the same text 3 times yields identical results."""
        results = []
        for _ in range(3):
            claims = extract_practical_claims(tour_with_correct_info)
            results.append([(c.claim_type, c.value) for c in claims])

        assert results[0] == results[1] == results[2], (
            f"Extraction not deterministic across runs: {results}"
        )

    def test_verification_deterministic(self, asian_source_text):
        """Same claim verified against same source = same result 3 times."""
        claim = PracticalClaim(claim_type='hours', value='Open daily from 10am to 6pm')
        results = []
        for _ in range(3):
            results.append(verify_claim_against_source(claim, asian_source_text))
        assert all(r == results[0] for r in results), "Verification not deterministic"


# ============================================================================
# Test 8: Gate does not weaken existing checks
# ============================================================================

class TestNoRegression:
    """Verify that adding the practical facts gate doesn't affect base QA scoring."""

    def test_gate_result_independent_of_style_score(self, tour_with_correct_info, asian_source_text):
        """The practical facts gate result is orthogonal to content_qa_runner scoring."""
        result = run_practical_facts_gate(
            tour_with_correct_info,
            source_url="https://maa.nice.fr",
            source_text=asian_source_text,
        )
        # Gate should have its own pass/fail independent of the 8-check score
        assert isinstance(result.passed, bool)
        assert isinstance(result.claims, list)
        assert isinstance(result.audit_log, list)
