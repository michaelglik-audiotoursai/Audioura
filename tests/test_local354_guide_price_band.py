"""test_local354_guide_price_band.py — LOCAL-354: Price band from dining guides.

Tests:
1. Guide lookup: La Merenda and Le Safari have price bands; Fenocchio and Acchiardo do not
2. Threshold derivation: conservative rounding up to next €10
3. Sentence combination: price + payment in Michael's one-sentence format
4. Gate integration: guide-sourced price band PASSES the practical facts gate
5. Gate strictness: unsourced price band still DROPPED (gate not weakened)
6. Absence: venues without guide listings emit no price (silence is correct)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from guide_price_band import (
    GuidePriceBand,
    derive_threshold,
    lookup_guide_price,
    combine_price_and_payment,
    get_dining_sentence,
    build_price_source_text,
    _GUIDE_PRICE_REGISTRY,
    _GUIDE_NO_LISTING,
)
from practical_facts_gate import (
    extract_practical_claims,
    verify_claim_against_source,
    run_practical_facts_gate,
    PracticalClaim,
)


# ============================================================================
# Unit tests: Threshold derivation
# ============================================================================

class TestThresholdDerivation:
    """Test conservative "under €X" threshold derivation."""

    def test_high_43_yields_50(self):
        """Le Fooding says à la carte €31-43 → 'under €50'."""
        assert derive_threshold(43.0) == 50

    def test_high_55_yields_60(self):
        """Gault&Millau says 32-55 → 'under €60'."""
        assert derive_threshold(55.0) == 60

    def test_high_50_yields_60(self):
        """Boundary: high=50 → threshold must be ABOVE 50 → 60."""
        assert derive_threshold(50.0) == 60

    def test_high_32_yields_40(self):
        """Low range: high=32 → 'under €40'."""
        assert derive_threshold(32.0) == 40

    def test_high_60_yields_70(self):
        """high=60 → 70."""
        assert derive_threshold(60.0) == 70

    def test_high_10_yields_20(self):
        """Very cheap venue: high=10 → 20."""
        assert derive_threshold(10.0) == 20

    def test_high_41_yields_50(self):
        """high=41 → next 10 above is 50."""
        assert derive_threshold(41.0) == 50


# ============================================================================
# Unit tests: Guide lookup
# ============================================================================

class TestGuideLookup:
    """Test guide price band lookup for known venues."""

    def test_la_merenda_has_price(self):
        """La Merenda is listed on Le Fooding with à la carte €31-43."""
        band = lookup_guide_price("La Merenda")
        assert band.has_price is True
        assert band.guide_name == "Le Fooding"
        assert band.low_eur == 31.0
        assert band.high_eur == 43.0
        assert band.threshold_eur == 50
        assert "lefooding.com" in band.guide_url

    def test_le_safari_has_price(self):
        """Le Safari is listed on Gault&Millau with 32-55 per person."""
        band = lookup_guide_price("Le Safari")
        assert band.has_price is True
        assert band.guide_name == "Gault&Millau"
        assert band.low_eur == 32.0
        assert band.high_eur == 55.0
        assert band.threshold_eur == 60
        assert "gaultmillau.com" in band.guide_url

    def test_fenocchio_no_price(self):
        """Fenocchio: Gault&Millau lists as Artisan glacier — no meal budget."""
        band = lookup_guide_price("Fenocchio")
        assert band.has_price is False
        assert band.guide_name == ""
        assert band.threshold_eur is None

    def test_acchiardo_no_price(self):
        """Acchiardo: not listed on any guide — silence is correct."""
        band = lookup_guide_price("Acchiardo")
        assert band.has_price is False
        assert band.guide_name == ""
        assert band.threshold_eur is None

    def test_unknown_venue_no_price(self):
        """Arbitrary venue not in registry → no price."""
        band = lookup_guide_price("Random Restaurant XYZ")
        assert band.has_price is False


# ============================================================================
# Unit tests: Sentence combination (Michael's format)
# ============================================================================

class TestSentenceCombination:
    """Test one-sentence combination of price band + payment fact."""

    def test_la_merenda_combined(self):
        """La Merenda: price band + cash only → one sentence."""
        band = lookup_guide_price("La Merenda")
        sentence = combine_price_and_payment(band, "Cash only")
        # Michael's format
        assert "under €50" in sentence
        assert "credit cards are not accepted" in sentence
        # Must be ONE sentence (no period separating the two facts)
        assert sentence.count(". ") == 0, f"Must be one sentence, got: {sentence}"
        # Must start with capital
        assert sentence[0].isupper()

    def test_le_safari_price_only(self):
        """Le Safari: price band + no payment restriction → price-only."""
        band = lookup_guide_price("Le Safari")
        sentence = combine_price_and_payment(band, "")
        assert "under €60" in sentence
        assert "credit cards" not in sentence

    def test_fenocchio_no_price_no_payment(self):
        """Fenocchio: no price, no payment fact → empty string (silence)."""
        band = lookup_guide_price("Fenocchio")
        sentence = combine_price_and_payment(band, "")
        assert sentence == ""

    def test_acchiardo_no_price_no_payment(self):
        """Acchiardo: no price, no payment fact → empty string."""
        band = lookup_guide_price("Acchiardo")
        sentence = combine_price_and_payment(band, "")
        assert sentence == ""

    def test_payment_only_no_price(self):
        """Venue with payment fact but no price band → payment-only sentence."""
        band = GuidePriceBand(venue_name="Test")  # No price
        sentence = combine_price_and_payment(band, "Cash only")
        assert "credit cards are not accepted" in sentence.lower()
        assert "under €" not in sentence

    def test_michael_format_verbatim_structure(self):
        """Verify the sentence matches Michael's stated format."""
        band = lookup_guide_price("La Merenda")
        sentence = combine_price_and_payment(band, "Cash only")
        # "An average dinner or lunch would cost under €50 but credit cards are not accepted"
        assert sentence.startswith("An average dinner or lunch would cost under €50")
        assert sentence.endswith("credit cards are not accepted")
        assert " but " in sentence


# ============================================================================
# Gate integration: guide-sourced price band passes the practical facts gate
# ============================================================================

class TestGateIntegrationPriceBand:
    """Test that guide-sourced price bands pass the practical facts gate."""

    def test_la_merenda_price_band_passes(self):
        """Price band claim with Le Fooding source text verifies."""
        # Simulate the tour text with the combined sentence
        tour_text = (
            "Stop 1: La Merenda\n\n"
            "Operational Details: An average dinner or lunch would cost under €50 "
            "but credit cards are not accepted\n\n"
        )
        # Source text = Guide provenance + OSM payment tags
        band = lookup_guide_price("La Merenda")
        osm_source = (
            "OSM node 1130923412 tags:\n"
            "  payment:cash = yes\n"
            "  payment:credit_cards = no\n"
            "  payment:debit_cards = no\n"
        )
        source_text = band.source_text_for_gate + "\n\n" + osm_source
        source_url = band.guide_url

        result = run_practical_facts_gate(tour_text, source_url, source_text)

        # Should detect claims
        assert len(result.claims) > 0, "Gate should detect the price+payment claim"

        # Price band claim should verify against guide source
        price_claims = [c for c in result.claims if c.claim_type == 'price_band']
        assert len(price_claims) >= 1, (
            f"Gate should classify 'cost under €50' as price_band. "
            f"Claims found: {[(c.claim_type, c.value) for c in result.claims]}"
        )
        for claim in price_claims:
            assert claim.verified, (
                f"Price band claim should verify against guide source. "
                f"Claim: {claim.value}, Source has: {source_text[:200]}"
            )

    def test_le_safari_price_band_passes(self):
        """Le Safari price band from Gault&Millau verifies."""
        tour_text = (
            "Stop 3: Le Safari\n\n"
            "Operational Details: An average dinner or lunch would cost under €60\n\n"
        )
        band = lookup_guide_price("Le Safari")
        source_text = band.source_text_for_gate

        result = run_practical_facts_gate(tour_text, band.guide_url, source_text)

        price_claims = [c for c in result.claims if c.claim_type == 'price_band']
        assert len(price_claims) >= 1
        for claim in price_claims:
            assert claim.verified, (
                f"Le Safari price band should verify. Claim: {claim.value}"
            )


# ============================================================================
# Gate strictness: unsourced price claims still dropped
# ============================================================================

class TestGateStrictnessPriceBand:
    """Verify the gate is NOT weakened — unsourced price bands still dropped."""

    def test_invented_price_band_no_source_dropped(self):
        """A fabricated 'under €40' with no source text → DROPPED."""
        tour_text = (
            "Stop 1: Mystery Restaurant\n\n"
            "Operational Details: An average dinner or lunch would cost under €40\n\n"
        )
        # No source text at all
        result = run_practical_facts_gate(tour_text, "", "")

        price_claims = [c for c in result.claims if c.claim_type == 'price_band']
        if price_claims:
            for claim in price_claims:
                assert not claim.verified, (
                    "Price band without source must NOT verify"
                )

    def test_invented_price_band_wrong_source_dropped(self):
        """A price band claim with source that has no guide provenance → DROPPED."""
        tour_text = (
            "Stop 1: Fake Place\n\n"
            "Operational Details: An average dinner or lunch would cost under €30\n\n"
        )
        # Source is just OSM tags — no guide provenance
        source_text = (
            "OSM node 999999 tags:\n"
            "  amenity = restaurant\n"
            "  cuisine = french\n"
            "  name = Fake Place\n"
        )
        result = run_practical_facts_gate(tour_text, "https://osm.org/node/999999", source_text)

        price_claims = [c for c in result.claims if c.claim_type == 'price_band']
        for claim in price_claims:
            assert not claim.verified, (
                "Price band claim without guide in source must not verify"
            )

    def test_inflated_threshold_dropped(self):
        """Claiming 'under €100' when guide says €31-43 → DROPPED (threshold mismatch)."""
        tour_text = (
            "Stop 1: La Merenda\n\n"
            "Operational Details: An average dinner or lunch would cost under €100\n\n"
        )
        band = lookup_guide_price("La Merenda")
        source_text = band.source_text_for_gate

        result = run_practical_facts_gate(tour_text, band.guide_url, source_text)

        price_claims = [c for c in result.claims if c.claim_type == 'price_band']
        for claim in price_claims:
            assert not claim.verified, (
                "Inflated threshold (€100 for a €31-43 restaurant) must not verify"
            )

    def test_payment_claim_still_needs_osm_source(self):
        """Payment claim 'cash only' without OSM tags in source → still dropped."""
        tour_text = (
            "Stop 1: La Merenda\n\n"
            "Operational Details: Credit cards are not accepted\n\n"
        )
        # Source has guide price but no OSM payment tags
        band = lookup_guide_price("La Merenda")
        source_text = band.source_text_for_gate  # Guide only, no OSM

        result = run_practical_facts_gate(tour_text, band.guide_url, source_text)

        payment_claims = [c for c in result.claims if c.claim_type == 'payment']
        if payment_claims:
            for claim in payment_claims:
                # The guide source does NOT contain "payment:cash = yes" etc.
                # so payment claims need OSM backing separately
                assert not claim.verified, (
                    "Payment claim needs OSM source, not guide source"
                )


# ============================================================================
# Absence handling: no price where no guide lists the venue
# ============================================================================

class TestAbsenceHandling:
    """Test that missing guide data produces silence, not invention."""

    def test_fenocchio_get_dining_sentence_empty(self):
        """Fenocchio: no guide price, no payment → empty sentence."""
        sentence, url, source = get_dining_sentence("Fenocchio", "")
        assert sentence == ""
        assert url == ""
        assert source == ""

    def test_acchiardo_get_dining_sentence_empty(self):
        """Acchiardo: no guide price, no payment → empty sentence."""
        sentence, url, source = get_dining_sentence("Acchiardo", "")
        assert sentence == ""
        assert url == ""
        assert source == ""

    def test_la_merenda_get_dining_sentence_full(self):
        """La Merenda: guide price + cash only → full combined sentence."""
        sentence, url, source = get_dining_sentence("La Merenda", "Cash only")
        assert "under €50" in sentence
        assert "credit cards are not accepted" in sentence
        assert url != ""
        assert source != ""


# ============================================================================
# Source text format enables gate verification
# ============================================================================

class TestSourceTextFormat:
    """Test that guide source text format enables gate verification."""

    def test_source_text_contains_guide_name(self):
        """Source text must contain the guide name for provenance check."""
        band = lookup_guide_price("La Merenda")
        source = band.source_text_for_gate
        assert "Le Fooding" in source

    def test_source_text_contains_price_range(self):
        """Source text must contain the price range numbers."""
        band = lookup_guide_price("La Merenda")
        source = band.source_text_for_gate
        assert "31" in source
        assert "43" in source

    def test_source_text_contains_threshold(self):
        """Source text must state the derived threshold for verification."""
        band = lookup_guide_price("La Merenda")
        source = band.source_text_for_gate
        assert "under €50" in source

    def test_source_text_contains_url(self):
        """Source text must contain the guide URL."""
        band = lookup_guide_price("La Merenda")
        source = band.source_text_for_gate
        assert "lefooding.com" in source

    def test_empty_band_no_source_text(self):
        """Venue without guide listing → empty source text."""
        band = lookup_guide_price("Acchiardo")
        source = band.source_text_for_gate
        assert source == ""


# ============================================================================
# Integration: full get_dining_sentence returns
# ============================================================================

class TestGetDiningSentence:
    """Test the full public API."""

    def test_la_merenda_full_return(self):
        """La Merenda returns sentence + source_url + source_text."""
        sentence, url, source_text = get_dining_sentence("La Merenda", "Cash only")
        assert sentence == "An average dinner or lunch would cost under €50 but credit cards are not accepted"
        assert url == "https://lefooding.com/en/restaurants/restaurant-la-merenda-nice-6"
        assert "Le Fooding" in source_text
        assert "Range: €31.0-43.0" in source_text

    def test_le_safari_full_return(self):
        """Le Safari returns price-only sentence (no payment restriction)."""
        sentence, url, source_text = get_dining_sentence("Le Safari", "")
        assert sentence == "An average dinner or lunch would cost under €60"
        assert "gaultmillau.com" in url
        assert "Gault&Millau" in source_text
