"""test_local355_osm_venue_facts.py — LOCAL-355: Practical facts for ALL venue kinds.

Tests:
1. Venue kind classification from OSM tags
2. Museum facts: fee, opening_hours, admission details
3. Park facts: opening_hours (seasonal), free access
4. Dining backward-compat: LOCAL-353 results unchanged
5. Gate integration: museum/park sourced claims PASS gate
6. Gate strictness: unsourced claims still DROPPED
7. Sentence format: one sentence per venue, per Michael's format
8. Absence handling: missing tags → omitted, not invented

D242 compliance: tests import production module and would FAIL against the
unfixed osm_dining_facts.py (which cannot classify or extract museum facts).
"""
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from osm_venue_facts import (
    OsmVenueFacts,
    classify_venue_kind,
    _extract_payment_info,
    _extract_reservation,
    _extract_fee,
    _extract_price_range,
    _build_source_text,
    extract_city_from_venue_name,
    fetch_osm_venue_facts,
    fetch_osm_facts_for_stops,
    # Backward-compat aliases
    OsmDiningFacts,
    fetch_osm_dining_facts,
)
from practical_facts_gate import (
    extract_practical_claims,
    verify_claim_against_source,
    run_practical_facts_gate,
    gate_and_fix,
    PracticalClaim,
)

# verify_claim_against_source returns bool (True = supported)


# ============================================================================
# Venue kind classification
# ============================================================================

class TestVenueKindClassification:
    """Test that OSM tags map to the correct venue kind."""

    def test_restaurant(self):
        tags = {"amenity": "restaurant", "name": "La Merenda"}
        assert classify_venue_kind(tags) == "dining"

    def test_cafe(self):
        tags = {"amenity": "cafe", "name": "Café de Turin"}
        assert classify_venue_kind(tags) == "dining"

    def test_museum_tourism(self):
        tags = {"tourism": "museum", "name": "Musée Matisse"}
        assert classify_venue_kind(tags) == "museum"

    def test_gallery(self):
        tags = {"tourism": "gallery", "name": "Galerie des Ponchettes"}
        assert classify_venue_kind(tags) == "museum"

    def test_museum_amenity(self):
        """Some OSM entries use amenity=museum instead of tourism=museum."""
        tags = {"amenity": "museum", "name": "Some Museum"}
        assert classify_venue_kind(tags) == "museum"

    def test_park(self):
        tags = {"leisure": "park", "name": "Colline du Château"}
        assert classify_venue_kind(tags) == "park"

    def test_garden(self):
        tags = {"leisure": "garden", "name": "Jardin Albert I"}
        assert classify_venue_kind(tags) == "park"

    def test_viewpoint(self):
        tags = {"tourism": "viewpoint", "name": "Colline du Château"}
        assert classify_venue_kind(tags) == "viewpoint"

    def test_historic(self):
        tags = {"historic": "castle", "name": "Fort du Mont Alban"}
        assert classify_venue_kind(tags) == "historic"

    def test_unknown(self):
        """A highway or building with no tourism/leisure/amenity tag."""
        tags = {"highway": "pedestrian", "name": "Place Masséna"}
        assert classify_venue_kind(tags) == "unknown"


# ============================================================================
# Fee extraction (museum/park equivalent of price_range)
# ============================================================================

class TestFeeExtraction:
    """Test fee/admission extraction from OSM tags."""

    def test_free_museum(self):
        """fee=no → 'no', no details."""
        tags = {"fee": "no", "tourism": "museum", "name": "Musée des Arts Asiatiques"}
        fee, details = _extract_fee(tags)
        assert fee == "no"
        assert details == ""

    def test_paid_museum_with_charge(self):
        """fee=yes with charge tag → extract price."""
        tags = {"fee": "yes", "charge": "8 EUR", "tourism": "museum"}
        fee, details = _extract_fee(tags)
        assert fee == "yes"
        assert details == "8 EUR"

    def test_paid_museum_with_description(self):
        """fee=yes with description:en containing prices."""
        tags = {
            "fee": "yes",
            "tourism": "museum",
            "description:en": "Full rate : €8, Reduced rate : €6, Free: under 26",
        }
        fee, details = _extract_fee(tags)
        assert fee == "yes"
        assert "€8" in details

    def test_absent_fee(self):
        """No fee tag → empty (never infer)."""
        tags = {"tourism": "museum", "name": "Unknown Museum"}
        fee, details = _extract_fee(tags)
        assert fee == ""
        assert details == ""

    def test_park_free(self):
        """Parks with fee=no."""
        tags = {"fee": "no", "leisure": "park", "name": "Parc Phoenix"}
        fee, details = _extract_fee(tags)
        assert fee == "no"

    def test_charge_without_fee_tag(self):
        """charge tag present but no fee tag — still extract charge."""
        tags = {"charge": "5 EUR", "tourism": "museum"}
        fee, details = _extract_fee(tags)
        assert fee == ""
        assert details == "5 EUR"


# ============================================================================
# Museum practical sentence formatting
# ============================================================================

class TestMuseumSentenceFormat:
    """Museum facts → one sentence, Michael's format."""

    def test_free_with_hours(self):
        """Free museum with opening hours."""
        facts = OsmVenueFacts(
            stop_title="Musée des Arts Asiatiques",
            venue_kind="museum",
            fee="no",
            opening_hours="Mo-Su 10:00-17:00; Tu off",
        )
        sentence = facts.format_practical_sentence()
        assert "Free admission" in sentence
        assert "10:00-17:00" in sentence
        assert "Tu off" in sentence

    def test_paid_with_details(self):
        """Paid museum with pricing details from description."""
        facts = OsmVenueFacts(
            stop_title="Musée Marc Chagall",
            venue_kind="museum",
            fee="yes",
            fee_details="Full rate : €8, Reduced rate : €6, Free: under 26",
            opening_hours="10:00-18:00; Tu off",
        )
        sentence = facts.format_practical_sentence()
        assert "€8" in sentence
        assert "Tu off" in sentence

    def test_paid_no_details(self):
        """fee=yes but no charge tag — say 'Admission charged'."""
        facts = OsmVenueFacts(
            stop_title="Musée Matisse",
            venue_kind="museum",
            fee="yes",
            opening_hours="Mo-Su 10:00-18:00",
        )
        sentence = facts.format_practical_sentence()
        assert "Admission charged" in sentence
        assert "10:00-18:00" in sentence

    def test_empty_yields_nothing(self):
        """No facts → empty string."""
        facts = OsmVenueFacts(stop_title="Unknown", venue_kind="museum")
        assert facts.format_practical_sentence() == ""

    def test_reservation_included(self):
        """If reservation tag exists, include it."""
        facts = OsmVenueFacts(
            stop_title="Timed Museum",
            venue_kind="museum",
            fee="yes",
            fee_details="€10",
            reservation="Reservations required",
        )
        sentence = facts.format_practical_sentence()
        assert "Reservations required" in sentence
        assert "€10" in sentence


# ============================================================================
# Park/outdoor sentence formatting
# ============================================================================

class TestParkSentenceFormat:
    """Park/viewpoint/historic facts → one sentence."""

    def test_free_park_with_hours(self):
        """Free park with seasonal hours."""
        facts = OsmVenueFacts(
            stop_title="Colline du Château",
            venue_kind="park",
            fee="no",
            opening_hours="Oct-Mar Mo-Su 08:30-18:00, Apr-Sep Mo-Su 08:30-20:00",
        )
        sentence = facts.format_practical_sentence()
        assert "Free access" in sentence
        assert "08:30" in sentence

    def test_viewpoint_no_facts(self):
        """Viewpoint with no hours/fee → empty."""
        facts = OsmVenueFacts(
            stop_title="Colline du Château",
            venue_kind="viewpoint",
        )
        assert facts.format_practical_sentence() == ""

    def test_paid_historic(self):
        """Historic site with entry fee."""
        facts = OsmVenueFacts(
            stop_title="Fort du Mont Alban",
            venue_kind="historic",
            fee="yes",
            fee_details="3 EUR",
            opening_hours="Mo-Su 10:00-17:00",
        )
        sentence = facts.format_practical_sentence()
        assert "3 EUR" in sentence
        assert "10:00-17:00" in sentence


# ============================================================================
# Dining backward compatibility (LOCAL-353 must not regress)
# ============================================================================

class TestDiningBackwardCompat:
    """Verify LOCAL-353 dining results still hold through the new module."""

    def test_cash_only_formatting(self):
        """La Merenda style: cash only + opening hours."""
        facts = OsmVenueFacts(
            stop_title="La Merenda",
            venue_kind="dining",
            opening_hours="Mo-Fr 12:00-14:00, 19:00-21:30",
            payment_info="Cash only",
        )
        sentence = facts.format_practical_sentence()
        assert "Cash only" in sentence
        assert "12:00-14:00" in sentence
        # Uses ". " separator for dining (legacy format)
        assert ". " in sentence

    def test_reservation_required(self):
        """Dining with reservation required."""
        facts = OsmVenueFacts(
            stop_title="Le Chantecler",
            venue_kind="dining",
            reservation="Reservations required",
        )
        sentence = facts.format_practical_sentence()
        assert sentence == "Reservations required"

    def test_dining_empty(self):
        """No dining tags → empty."""
        facts = OsmVenueFacts(stop_title="Unknown", venue_kind="dining")
        assert facts.format_practical_sentence() == ""

    def test_payment_extraction_cash_only(self):
        """Cash only detection unchanged."""
        tags = {"payment:cash": "yes", "payment:credit_cards": "no", "payment:debit_cards": "no"}
        assert _extract_payment_info(tags) == "Cash only"

    def test_payment_extraction_card_only(self):
        """Card only detection unchanged."""
        tags = {"payment:cash": "no", "payment:credit_cards": "yes", "payment:debit_cards": "yes"}
        assert _extract_payment_info(tags) == "Card payments only"

    def test_backward_compat_alias(self):
        """OsmDiningFacts is an alias for OsmVenueFacts."""
        assert OsmDiningFacts is OsmVenueFacts
        assert fetch_osm_dining_facts is fetch_osm_venue_facts


# ============================================================================
# Gate integration: sourced museum/park claims PASS
# ============================================================================

class TestGateIntegrationMuseum:
    """Verify that OSM-sourced museum claims pass the practical facts gate."""

    def test_museum_hours_pass_gate(self):
        """Museum opening_hours from OSM source_text → SUPPORTED."""
        source_text = (
            "OSM way 81023334 tags:\n"
            "  fee = no\n"
            "  name = Musée des Arts Asiatiques\n"
            "  opening_hours = Mo-Su 10:00-17:00; Tu off\n"
            "  tourism = museum\n"
        )
        claim = PracticalClaim(
            claim_type="hours",
            value="10:00-17:00",
        )
        result = verify_claim_against_source(claim, source_text)
        assert result is True, "Expected hours claim to be supported by source"

    def test_museum_free_admission_pass(self):
        """fee=no in source → 'free' admission claim SUPPORTED."""
        source_text = (
            "OSM way 81023334 tags:\n"
            "  fee = no\n"
            "  name = Musée des Arts Asiatiques\n"
            "  tourism = museum\n"
        )
        claim = PracticalClaim(
            claim_type="admission",
            value="Free admission",
        )
        result = verify_claim_against_source(claim, source_text)
        assert result is True, "Expected 'free' admission claim to be supported (fee = no in source)"

    def test_museum_closed_tuesday_pass(self):
        """'Tu off' in source → 'closed Tuesday' SUPPORTED."""
        source_text = (
            "OSM way 81023334 tags:\n"
            "  opening_hours = Mo-Su 10:00-17:00; Tu off\n"
            "  tourism = museum\n"
        )
        claim = PracticalClaim(
            claim_type="closed_day",
            value="Closed Tuesday",
        )
        result = verify_claim_against_source(claim, source_text)
        assert result is True, "Expected 'closed Tuesday' to be supported by 'Tu off' in source"


class TestGateIntegrationPark:
    """Verify that OSM-sourced park claims pass the practical facts gate."""

    def test_park_hours_pass_gate(self):
        """Park seasonal hours from OSM source → SUPPORTED."""
        source_text = (
            "OSM way 19668745 tags:\n"
            "  leisure = park\n"
            "  name = Colline du Château\n"
            "  opening_hours = Oct-Mar Mo-Su 08:30-18:00; Apr-Sep Mo-Su 08:30-20:00\n"
        )
        claim = PracticalClaim(
            claim_type="hours",
            value="08:30-18:00",
        )
        result = verify_claim_against_source(claim, source_text)
        assert result is True, "Expected park hours claim to be supported by source"


# ============================================================================
# Gate strictness: unsourced claims DROPPED
# ============================================================================

class TestGateStrictnessPreserved:
    """Unsourced claims for museums/parks still dropped — no exemptions."""

    def test_unsourced_museum_hours_dropped(self):
        """A museum hours claim with no source → NOT supported."""
        source_text = (
            "OSM way 81023334 tags:\n"
            "  name = Musée des Arts Asiatiques\n"
            "  tourism = museum\n"
        )
        # Claim says 09:00-18:00 but source has no opening_hours
        claim = PracticalClaim(
            claim_type="hours",
            value="09:00-18:00",
        )
        result = verify_claim_against_source(claim, source_text)
        assert result is False, "Hours claim should not be supported when source has no opening_hours"

    def test_unsourced_admission_dropped(self):
        """Claiming free when fee tag absent → not supported."""
        source_text = (
            "OSM way 12345 tags:\n"
            "  name = Unknown Museum\n"
            "  tourism = museum\n"
        )
        claim = PracticalClaim(
            claim_type="admission",
            value="Free admission",
        )
        result = verify_claim_against_source(claim, source_text)
        # Source doesn't say "free" or "gratuit" or "fee = no" — should not support
        assert result is False, "Free claim should not pass without fee=no in source"

    def test_invented_queue_advice_dropped(self):
        """'Arrive early to beat crowds' — invented, no source → not supported."""
        source_text = (
            "OSM way 81023334 tags:\n"
            "  fee = no\n"
            "  name = Musée des Arts Asiatiques\n"
            "  opening_hours = Mo-Su 10:00-17:00; Tu off\n"
            "  tourism = museum\n"
        )
        # Queue advice is not a claim type the gate handles — it would never
        # be produced by our module since OSM doesn't carry it.
        # Use a time not present in source to avoid false match
        claim = PracticalClaim(
            claim_type="hours",
            value="arrive before 9am to avoid queues",
        )
        result = verify_claim_against_source(claim, source_text)
        assert result is False, "Invented queue advice should not pass as an hours claim"


# ============================================================================
# Source text format (gate verification target)
# ============================================================================

class TestSourceTextFormat:
    """Source text must be in a format the gate can parse."""

    def test_museum_source_text(self):
        """Museum source_text includes fee, opening_hours, tourism tags."""
        tags = {
            "fee": "no",
            "name": "Musée des Arts Asiatiques",
            "opening_hours": "Mo-Su 10:00-17:00; Tu off",
            "tourism": "museum",
        }
        source = _build_source_text(tags, 81023334, "way")
        assert "OSM way 81023334 tags:" in source
        assert "fee = no" in source
        assert "opening_hours = Mo-Su 10:00-17:00; Tu off" in source
        assert "tourism = museum" in source

    def test_park_source_text(self):
        """Park source_text includes leisure, opening_hours."""
        tags = {
            "leisure": "park",
            "name": "Colline du Château",
            "opening_hours": "Oct-Mar Mo-Su 08:30-18:00; Apr-Sep Mo-Su 08:30-20:00",
        }
        source = _build_source_text(tags, 19668745, "way")
        assert "OSM way 19668745 tags:" in source
        assert "leisure = park" in source
        assert "08:30-18:00" in source

    def test_dining_source_text_unchanged(self):
        """Dining source_text format identical to LOCAL-353."""
        tags = {
            "amenity": "restaurant",
            "name": "La Merenda",
            "opening_hours": "Mo-Fr 12:00-14:00, 19:00-21:30",
            "payment:cash": "yes",
            "payment:credit_cards": "no",
            "payment:debit_cards": "no",
        }
        source = _build_source_text(tags, 1130923412, "node")
        assert "OSM node 1130923412 tags:" in source
        assert "payment:cash = yes" in source
        assert "payment:credit_cards = no" in source


# ============================================================================
# City extraction (generalised noise words)
# ============================================================================

class TestCityExtraction:
    """City extraction handles museum/park tour names."""

    def test_museum_nice(self):
        assert extract_city_from_venue_name("Musée Matisse, Nice, France") == "Nice"

    def test_restaurant_old_nice(self):
        """Dining still works."""
        result = extract_city_from_venue_name("restaurant tour in Old Nice, France")
        assert result == "Nice"

    def test_walking_area(self):
        result = extract_city_from_venue_name("Nice walking area")
        assert result == "Nice"

    def test_park_name(self):
        result = extract_city_from_venue_name("Parc Phoenix, Nice, France")
        # "Parc" is not noise, Phoenix is first proper noun
        assert result in ("Parc", "Phoenix", "Nice")


# ============================================================================
# Absence handling: no inference
# ============================================================================

class TestAbsenceHandling:
    """Missing OSM data → omission, never inference."""

    def test_no_fee_tag_no_admission_claim(self):
        """Museum without fee tag → no admission sentence."""
        facts = OsmVenueFacts(
            stop_title="Unknown Museum",
            venue_kind="museum",
            opening_hours="Mo-Su 09:00-17:00",
            # fee deliberately absent
        )
        sentence = facts.format_practical_sentence()
        assert "Free" not in sentence
        assert "Admission" not in sentence
        # But hours still show
        assert "09:00-17:00" in sentence

    def test_no_hours_no_hours_claim(self):
        """Venue without opening_hours → no hours in sentence."""
        facts = OsmVenueFacts(
            stop_title="Promenade des Anglais",
            venue_kind="viewpoint",
            # no opening_hours, no fee
        )
        assert facts.format_practical_sentence() == ""
        assert facts.is_empty()

    def test_no_inference_from_category(self):
        """Never infer 'free' from the fact that it's a park."""
        facts = OsmVenueFacts(
            stop_title="Some Park",
            venue_kind="park",
            # fee tag absent — we must NOT say "Free access"
        )
        sentence = facts.format_practical_sentence()
        assert "Free" not in sentence


# ============================================================================
# Queue advice — explicitly not obtainable
# ============================================================================

class TestQueueAdvice:
    """Queue advice is NOT sourced from OSM — module must not produce it."""

    def test_no_queue_field_in_facts(self):
        """OsmVenueFacts has no queue_advice field."""
        facts = OsmVenueFacts(stop_title="Musée", venue_kind="museum")
        assert not hasattr(facts, 'queue_advice')

    def test_no_queue_in_formatted_sentence(self):
        """Even with all museum tags present, no queue advice emerges."""
        facts = OsmVenueFacts(
            stop_title="Musée Marc Chagall",
            venue_kind="museum",
            fee="yes",
            fee_details="€8",
            opening_hours="10:00-18:00; Tu off",
        )
        sentence = facts.format_practical_sentence()
        assert "queue" not in sentence.lower()
        assert "crowd" not in sentence.lower()
        assert "arrive early" not in sentence.lower()


# ============================================================================
# Integration: OsmVenueFacts.is_empty()
# ============================================================================

class TestIsEmpty:
    """is_empty reflects whether any sourceable facts exist."""

    def test_empty_when_no_facts(self):
        facts = OsmVenueFacts(stop_title="X", venue_kind="unknown")
        assert facts.is_empty()

    def test_not_empty_with_hours(self):
        facts = OsmVenueFacts(stop_title="X", venue_kind="museum", opening_hours="09-17")
        assert not facts.is_empty()

    def test_not_empty_with_fee(self):
        facts = OsmVenueFacts(stop_title="X", venue_kind="museum", fee="no")
        assert not facts.is_empty()

    def test_not_empty_with_payment(self):
        facts = OsmVenueFacts(stop_title="X", venue_kind="dining", payment_info="Cash only")
        assert not facts.is_empty()
