"""LOCAL-344: Fact and claim extractor alignment.

THE PROPERTY: Anything the fact detector counts as a fact must be checkable
by the claim extractor. Stated as a structural property, not an enumeration
of categories.

This test:
1. Runs both extractors on the same text.
2. Asserts that every counted fact has a corresponding claim.
3. Exercises the specific categories that were MISSING from the claim
   extractor before this fix: materials, measurements, named periods.

The test MUST FAIL against the unfixed version of groundedness_check.py
(where extract_fact_claims only handles persons, dates, artworks).

Usage:
    python3 -m pytest tests/test_local344_fact_claim_alignment.py -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from groundedness_check import extract_fact_claims, FactClaim
from tour_rubric_scorer import analyze_stop


def _make_stop(text: str, title: str = "Test Stop") -> dict:
    return {'index': 1, 'title': title, 'body': text}


# ═══════════════════════════════════════════════════════════════════════════════
# THE PROPERTY: every fact counted by analyze_stop has a corresponding claim
# ═══════════════════════════════════════════════════════════════════════════════

class TestFactClaimAlignmentProperty:
    """The structural property: counted facts ⊆ extractable claims."""

    def _get_facts_and_claims(self, text: str, title: str = "Test Stop"):
        """Run both extractors and return (facts_set, claims_set)."""
        stop = _make_stop(text, title)
        sa = analyze_stop(stop, [stop])

        # All facts the scorer counts
        facts = set()
        for d in set(sa.dates_years):
            facts.add(('date', d.lower()))
        for p in sa.named_people:
            facts.add(('person', p.lower()))
        for m in sa.materials_techniques:
            facts.add(('material', m.lower()))
        for n in sa.measurements_numbers:
            facts.add(('measurement', n.lower()))
        for per in sa.named_periods:
            facts.add(('period', per.lower()))

        # All claims the groundedness checker extracts
        claims = extract_fact_claims(text, title)
        claim_texts = set()
        for c in claims:
            claim_texts.add((c.claim_type, c.text.lower()))

        return facts, claim_texts, sa, claims

    def test_material_facts_produce_claims(self):
        """A material counted by the fact detector must appear in claims.

        'carved from chlorite' → fact_count includes 'chlorite' →
        extract_fact_claims must produce a claim for 'chlorite'.
        """
        text = (
            "This remarkable sculpture was carved from chlorite, a dark "
            "metamorphic stone prized by artisans of the Pala dynasty."
        )
        facts, claims, sa, _ = self._get_facts_and_claims(text)

        # Verify the fact detector sees materials
        assert sa.materials_techniques, (
            f"Fact detector should find 'chlorite' in materials_techniques"
        )
        # Verify each material has a claim
        for mat in sa.materials_techniques:
            matching = [c for c in claims if mat.lower() in c[1]]
            assert matching, (
                f"Material '{mat}' counted as fact but no corresponding claim. "
                f"Claims: {claims}"
            )

    def test_measurement_facts_produce_claims(self):
        """A measurement counted by the fact detector must appear in claims.

        'three Michelin stars' → measurements_numbers → must have a claim.
        """
        text = (
            "Franck Cerutti earned three Michelin stars for his innovative "
            "cuisine that blended traditional and modern techniques."
        )
        facts, claims, sa, _ = self._get_facts_and_claims(text)

        assert sa.measurements_numbers, (
            f"Fact detector should find 'three Michelin stars' in measurements"
        )
        for meas in sa.measurements_numbers:
            matching = [c for c in claims if meas.lower() in c[1]]
            assert matching, (
                f"Measurement '{meas}' counted as fact but no corresponding claim. "
                f"Claims: {claims}"
            )

    def test_period_facts_produce_claims(self):
        """A named period counted by the fact detector must appear in claims.

        'the Heian period' → named_periods → must have a claim.
        """
        text = (
            "This delicate lacquerwork dates from the Heian period, when "
            "Japanese artisans perfected the layering technique."
        )
        facts, claims, sa, _ = self._get_facts_and_claims(text)

        assert sa.named_periods, (
            f"Fact detector should find 'Heian' in named_periods"
        )
        for per in sa.named_periods:
            matching = [c for c in claims if per.lower() in c[1]]
            assert matching, (
                f"Period '{per}' counted as fact but no corresponding claim. "
                f"Claims: {claims}"
            )

    def test_museum_stop_kannon(self):
        """The case from the defect report: Stop 7 Kannon à mille bras.

        Had distinct_fact_count=4, groundedness_claims=0. After fix, all
        counted facts must have claims.
        """
        # Approximate the content of a Kannon stop with materials/periods
        text = (
            "Before you stands a remarkable Kannon à mille bras, the "
            "thousand-armed Kannon. This exquisite sculpture was crafted from "
            "cypress wood during the Kamakura period. The figure features "
            "forty-two arms radiating outward, each carved with extraordinary "
            "precision. Gold leaf adorns the surface, a technique perfected by "
            "Buddhist artisans over eight centuries of practice."
        )
        facts, claims, sa, raw_claims = self._get_facts_and_claims(
            text, "Kannon à mille bras"
        )

        assert sa.distinct_fact_count > 0, "Should detect facts"
        # The property: every fact has a claim
        uncovered = []
        for fact_type, fact_val in facts:
            matching = [c for c in claims if fact_val in c[1]]
            if not matching:
                uncovered.append((fact_type, fact_val))
        assert not uncovered, (
            f"Facts without claims: {uncovered}. "
            f"distinct_fact_count={sa.distinct_fact_count}, "
            f"total_claims={len(raw_claims)}"
        )

    def test_restaurant_stop_with_measurements(self):
        """Restaurant stop: 'three Michelin stars' must be checkable."""
        text = (
            "Chef Franck Cerutti, a culinary master with three Michelin stars, "
            "introduced his signature socca to Nice in 1926. The restaurant "
            "features twelve tables arranged in the traditional Niçoise style."
        )
        facts, claims, sa, raw_claims = self._get_facts_and_claims(text)

        # Both measurements should be checkable
        for meas in sa.measurements_numbers:
            matching = [c for c in claims if meas.lower() in c[1]]
            assert matching, (
                f"Measurement '{meas}' is a counted fact but has no claim"
            )

    def test_walking_stop_with_periods(self):
        """Walking stop: '12th century' named period must be checkable."""
        text = (
            "The fortress walls date from the Romanesque period, built during "
            "the reign of Count Berenger. The twelve arches of the gateway "
            "frame the old town beyond."
        )
        facts, claims, sa, raw_claims = self._get_facts_and_claims(text)

        # Periods should be checkable
        for per in sa.named_periods:
            matching = [c for c in claims if per.lower() in c[1]]
            assert matching, (
                f"Period '{per}' is a counted fact but has no claim"
            )

    def test_alignment_property_comprehensive(self):
        """Comprehensive: text with ALL fact categories present.

        Every single category the rubric scores must produce claims.
        """
        text = (
            "Marc Chagall painted this masterpiece in 1961 using oil on canvas. "
            "The work measures 3 metres across and depicts scenes from the "
            "Edo period. Crafted from bronze and gold leaf, the frame itself "
            "is a work of art with twenty panels arranged symmetrically."
        )
        facts, claims, sa, raw_claims = self._get_facts_and_claims(text)

        # Verify all fact categories are present
        assert sa.dates_years, "Should find dates"
        assert sa.named_people, "Should find people"
        assert sa.materials_techniques, "Should find materials"
        assert sa.measurements_numbers or sa.named_periods, (
            "Should find measurements or periods"
        )

        # THE PROPERTY: no fact without a claim
        uncovered = []
        for fact_type, fact_val in facts:
            matching = [c for c in claims if fact_val in c[1]]
            if not matching:
                uncovered.append((fact_type, fact_val))

        assert not uncovered, (
            f"Property violated: {len(uncovered)} facts without claims: {uncovered}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICATION: New claim types check against corpus correctly
# ═══════════════════════════════════════════════════════════════════════════════

class TestNewClaimTypesGrounding:
    """New claim types (material, measurement, period) can be checked."""

    def test_material_grounded_in_corpus(self):
        """A material claim found in corpus passages → GROUNDED."""
        from groundedness_check import check_claim_grounded
        claim = FactClaim(
            text='chlorite',
            claim_type='material',
            sentence='This sculpture was carved from chlorite.'
        )
        passages = ["The statue is made of chlorite stone from Bihar."]
        verdict, evidence = check_claim_grounded(claim, passages)
        assert verdict == 'GROUNDED', f"Expected GROUNDED, got {verdict}"

    def test_material_not_in_corpus(self):
        """A material claim NOT in corpus → UNGROUNDED."""
        from groundedness_check import check_claim_grounded
        claim = FactClaim(
            text='chlorite',
            claim_type='material',
            sentence='This sculpture was carved from chlorite.'
        )
        passages = ["The statue depicts a seated Buddha figure."]
        verdict, evidence = check_claim_grounded(claim, passages)
        assert verdict == 'UNGROUNDED', f"Expected UNGROUNDED, got {verdict}"

    def test_measurement_grounded_in_corpus(self):
        """A measurement claim found in corpus → GROUNDED."""
        from groundedness_check import check_claim_grounded
        claim = FactClaim(
            text='three michelin stars',
            claim_type='measurement',
            sentence='The restaurant holds three Michelin stars.'
        )
        passages = ["Awarded three Michelin stars in 2005."]
        verdict, evidence = check_claim_grounded(claim, passages)
        assert verdict == 'GROUNDED', f"Expected GROUNDED, got {verdict}"

    def test_period_grounded_in_corpus(self):
        """A period claim found in corpus → GROUNDED."""
        from groundedness_check import check_claim_grounded
        claim = FactClaim(
            text='Heian',
            claim_type='period',
            sentence='This dates from the Heian period.'
        )
        passages = ["Created during the Heian period (794-1185)."]
        verdict, evidence = check_claim_grounded(claim, passages)
        assert verdict == 'GROUNDED', f"Expected GROUNDED, got {verdict}"

    def test_period_ungrounded(self):
        """A period claim NOT in corpus → UNGROUNDED."""
        from groundedness_check import check_claim_grounded
        claim = FactClaim(
            text='Kamakura',
            claim_type='period',
            sentence='This dates from the Kamakura period.'
        )
        passages = ["The sculpture was made in the 12th century."]
        verdict, evidence = check_claim_grounded(claim, passages)
        assert verdict == 'UNGROUNDED', f"Expected UNGROUNDED, got {verdict}"
