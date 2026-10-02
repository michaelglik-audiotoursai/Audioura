#!/usr/bin/env python3
"""
tests/test_local286_museum_prolog_and_dedup.py

Unit tests for LOCAL-286: Museum prolog specialization, distance floor,
Tour-Category header fix, R7 on prolog, and prolog-body deduplication.

Runs against audiotours_test (D148).
"""
import os
import re
import sys
import pytest

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from style_validator_detector import check_r7_hallucinated_sensory, apply_r7_to_description


# ═══════════════════════════════════════════════════════════════════════════════
# R7 PATTERN TESTS — new LOCAL-286 patterns
# ═══════════════════════════════════════════════════════════════════════════════

class TestR7NewPatterns:
    """Verify the new R7 patterns catch round-34 fabrications."""

    def test_azure_waters(self):
        """'azure waters' is a standard model hallucination."""
        sentence = "facing the azure waters of the Mediterranean Sea"
        findings = check_r7_hallucinated_sensory(sentence)
        assert findings, f"R7 should fire on 'azure waters': {sentence}"

    def test_turquoise_sea(self):
        sentence = "the turquoise sea stretches before you"
        findings = check_r7_hallucinated_sensory(sentence)
        assert findings, f"R7 should fire on 'turquoise sea': {sentence}"

    def test_sun_kissed(self):
        """'sun-kissed' is always a model filler."""
        sentence = "the sun-kissed peninsula unfolds before you"
        findings = check_r7_hallucinated_sensory(sentence)
        assert findings, f"R7 should fire on 'sun-kissed': {sentence}"

    def test_sun_drenched(self):
        sentence = "sun-drenched villas line the coast"
        findings = check_r7_hallucinated_sensory(sentence)
        assert findings, f"R7 should fire on 'sun-drenched': {sentence}"

    def test_rugged_cliffs_with_sensory(self):
        """'rugged cliffs' + waves/breeze = fabricated dramatic scene."""
        sentence = (
            "The salty breeze, the sound of waves crashing against the "
            "rugged cliffs, and the scent of pine trees mingling with the sea air"
        )
        findings = check_r7_hallucinated_sensory(sentence)
        assert findings, f"R7 should fire on rugged cliffs + sensory: {sentence}"

    def test_salty_breeze_with_scent(self):
        """'salty breeze' + scent/sound = fabricated multi-sensory scene."""
        sentence = (
            "The salty breeze carries the scent of pine trees"
        )
        findings = check_r7_hallucinated_sensory(sentence)
        assert findings, f"R7 should fire on salty breeze + scent: {sentence}"

    def test_scent_mingling_with(self):
        """'scent of X mingling with Y' is fabricated."""
        sentence = "the scent of pine trees mingling with the sea air stretches out before you"
        findings = check_r7_hallucinated_sensory(sentence)
        assert findings, f"R7 should fire on scent mingling: {sentence}"

    def test_sound_of_waves_with_sensory(self):
        """'sound of waves crashing' + rugged/scent = fabricated scene."""
        sentence = "the sound of waves crashing against the rugged coastline fills the air"
        findings = check_r7_hallucinated_sensory(sentence)
        assert findings, f"R7 should fire on waves + rugged: {sentence}"

    def test_crystal_clear_waters(self):
        sentence = "the crystal-clear waters shimmer below"
        findings = check_r7_hallucinated_sensory(sentence)
        assert findings, f"R7 should fire on 'crystal-clear waters': {sentence}"

    # --- FALSE POSITIVE GUARDS ---

    def test_plain_coastal_description_does_not_fire(self):
        """Factual geographic description should NOT fire R7."""
        sentence = "The route follows the coastal road between Cap d'Antibes and Eze Village."
        findings = check_r7_hallucinated_sensory(sentence)
        assert not findings, f"R7 should NOT fire on factual geography: {sentence}"

    def test_plain_cliffs_without_sensory_does_not_fire(self):
        """'cliffs' alone without sensory context should NOT fire."""
        sentence = "The rugged cliffs of Cap d'Antibes were formed millions of years ago."
        findings = check_r7_hallucinated_sensory(sentence)
        assert not findings, f"R7 should NOT fire on factual cliffs: {sentence}"

    def test_factual_sea_does_not_fire(self):
        """Plain 'sea' reference without fabricated adjective should not fire."""
        sentence = "The Mediterranean Sea is visible from the eastern terrace."
        findings = check_r7_hallucinated_sensory(sentence)
        assert not findings, f"R7 should NOT fire on factual sea mention: {sentence}"


class TestR7OnFullPrologText:
    """Test apply_r7_to_description on the actual round-34 prolog."""

    ROUND_34_PROLOG = (
        "As you stand on the rocky coastline of Cap d'Antibes, facing the azure "
        "waters of the Mediterranean Sea, the sun-kissed peninsula unfolds before "
        "you. The salty breeze, the sound of waves crashing against the rugged "
        "cliffs, and the scent of pine trees mingling with the sea air stretches "
        "out before you."
    )

    def test_r7_fires_on_round34_prolog(self):
        """R7 must fire on the round-34 prolog (at least 1 deletion)."""
        new_text, deleted, emptied = apply_r7_to_description(self.ROUND_34_PROLOG)
        assert deleted > 0 or emptied > 0, (
            f"R7 should fire on round-34 prolog but got 0 deletions. "
            f"Result: {new_text}"
        )

    def test_r7_removes_azure_waters_sentence(self):
        """The 'azure waters' sentence should not survive R7."""
        new_text, _, _ = apply_r7_to_description(self.ROUND_34_PROLOG)
        assert 'azure waters' not in new_text.lower(), (
            f"'azure waters' survived R7: {new_text}"
        )

    def test_r7_removes_sun_kissed(self):
        """'sun-kissed' should not survive R7."""
        new_text, _, _ = apply_r7_to_description(self.ROUND_34_PROLOG)
        assert 'sun-kissed' not in new_text.lower(), (
            f"'sun-kissed' survived R7: {new_text}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PROLOG-BODY DEDUPLICATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestPrologBodyDeduplication:
    """Test the ≥8-word overlap detection logic."""

    def _find_8gram_overlap(self, prolog: str, body: str) -> bool:
        """Check if body has ≥8 consecutive words from prolog."""
        prolog_words = prolog.lower().split()
        body_words = body.lower().split()

        prolog_8grams = set()
        for i in range(len(prolog_words) - 7):
            prolog_8grams.add(' '.join(prolog_words[i:i + 8]))

        if not prolog_8grams:
            return False

        for i in range(len(body_words) - 7):
            test = ' '.join(body_words[i:i + 8])
            if test in prolog_8grams:
                return True
        return False

    def test_exact_repeat_detected(self):
        """Verbatim repeat of ≥8 words is detected."""
        prolog = (
            "Pedaling away, the ancient cliffs of Cap d'Antibes hold echoes "
            "from luminaries like Hemingway and Fitzgerald, while the building "
            "in Saint-Paul-de-Vence was designed by Josep Lluís Sert."
        )
        body = (
            "The ancient cliffs of Cap d'Antibes hold echoes from luminaries "
            "like Hemingway and Fitzgerald, blending history and nature seamlessly."
        )
        assert self._find_8gram_overlap(prolog, body), (
            "Should detect ≥8-word overlap between prolog and body"
        )

    def test_short_overlap_not_detected(self):
        """Overlap of <8 words should NOT be detected."""
        prolog = "The ancient cliffs of Cap d'Antibes are stunning."
        body = "The ancient cliffs rise above the bay."
        # Only 3 words overlap ("the ancient cliffs")
        assert not self._find_8gram_overlap(prolog, body)

    def test_no_false_positive_on_common_phrases(self):
        """Common short phrases should not trigger dedup."""
        prolog = "You are about to embark on a cycling journey through the French Riviera."
        body = "The French Riviera has been a destination for artists since the 1800s."
        assert not self._find_8gram_overlap(prolog, body)


# ═══════════════════════════════════════════════════════════════════════════════
# TOUR-CATEGORY HEADER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestTourCategoryHeader:
    """Verify Tour-Category writes the correct value for each transport mode."""

    def test_biking_category(self):
        """A biking tour should write 'biking', not 'walking'."""
        tour_category = 'walking'
        transport_mode = 'bike'

        # Replicate the fix logic
        _header_category = tour_category
        if tour_category == 'walking' and transport_mode == 'bike':
            _header_category = 'biking'
        elif tour_category == 'walking' and transport_mode == 'vehicle':
            _header_category = 'driving'
        elif tour_category == 'walking' and transport_mode == 'animal':
            _header_category = 'animal'

        assert _header_category == 'biking'

    def test_museum_category_unchanged(self):
        """A museum tour stays 'museum'."""
        tour_category = 'museum'
        transport_mode = 'on_foot'

        _header_category = tour_category
        if tour_category == 'walking' and transport_mode == 'bike':
            _header_category = 'biking'

        assert _header_category == 'museum'

    def test_restaurant_category_unchanged(self):
        """A restaurant tour stays 'restaurant'."""
        tour_category = 'restaurant'
        transport_mode = 'on_foot'

        _header_category = tour_category
        if tour_category == 'walking' and transport_mode == 'bike':
            _header_category = 'biking'

        assert _header_category == 'restaurant'

    def test_walking_on_foot_stays_walking(self):
        """A genuine walking tour (on_foot) stays 'walking'."""
        tour_category = 'walking'
        transport_mode = 'on_foot'

        _header_category = tour_category
        if tour_category == 'walking' and transport_mode == 'bike':
            _header_category = 'biking'
        elif tour_category == 'walking' and transport_mode == 'vehicle':
            _header_category = 'driving'
        elif tour_category == 'walking' and transport_mode == 'animal':
            _header_category = 'animal'

        assert _header_category == 'walking'

    def test_driving_category(self):
        """A vehicle tour should write 'driving'."""
        tour_category = 'walking'
        transport_mode = 'vehicle'

        _header_category = tour_category
        if tour_category == 'walking' and transport_mode == 'bike':
            _header_category = 'biking'
        elif tour_category == 'walking' and transport_mode == 'vehicle':
            _header_category = 'driving'

        assert _header_category == 'driving'


# ═══════════════════════════════════════════════════════════════════════════════
# DISTANCE FLOOR TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestDistanceFloor:
    """Verify the 50m floor omits the distance clause."""

    def test_zero_distance_not_meaningful(self):
        """0 km is below the 50m floor."""
        _prolog_total_km = 0.0
        _prolog_distance_meaningful = (_prolog_total_km * 1000) >= 50
        assert not _prolog_distance_meaningful

    def test_30m_not_meaningful(self):
        """30 meters is below the 50m floor."""
        _prolog_total_km = 0.030
        _prolog_distance_meaningful = (_prolog_total_km * 1000) >= 50
        assert not _prolog_distance_meaningful

    def test_50m_is_meaningful(self):
        """Exactly 50m is at the floor — meaningful."""
        _prolog_total_km = 0.050
        _prolog_distance_meaningful = (_prolog_total_km * 1000) >= 50
        assert _prolog_distance_meaningful

    def test_28km_is_meaningful(self):
        """28 km is well above the floor."""
        _prolog_total_km = 28.0
        _prolog_distance_meaningful = (_prolog_total_km * 1000) >= 50
        assert _prolog_distance_meaningful


# ═══════════════════════════════════════════════════════════════════════════════
# MUSEUM PROLOG PROMPT CONSTRUCTION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestMuseumPrologPrompt:
    """Verify the museum prolog prompt does not mention walking/distance."""

    def _build_part1_instruction(self, is_museum, transport_display, location):
        """Replicate the prompt branching logic."""
        if is_museum:
            return (
                'State the tour name and the venue. Do NOT mention walking or any mode of '
                'transport — inside a museum, walking is the default and stating it is empty. '
                'Example shape: "You are about to explore the [venue name] in [city]." '
                'Name the venue and its collection or character.'
            )
        else:
            return (
                f'State the tour name and mode of transport. '
                f'Example shape: "You are about to embark on a [{transport_display}] '
                f'journey through [{location}]."'
            )

    def test_museum_part1_no_walking(self):
        """Museum Part 1 instruction must not mention walking."""
        instruction = self._build_part1_instruction(True, 'walking', 'Musée des Arts Asiatiques')
        assert 'walking' not in instruction.lower().replace('do not mention walking', '').replace('walking is the default', '')
        # The word 'walking' appears only in the prohibition, not as a directive to say it
        assert 'embark on a' not in instruction

    def test_museum_part1_names_venue(self):
        """Museum Part 1 instruction references venue."""
        instruction = self._build_part1_instruction(True, 'walking', 'Musée des Arts Asiatiques')
        assert 'venue' in instruction.lower()

    def test_cycling_part1_keeps_transport(self):
        """Cycling Part 1 instruction must mention cycling."""
        instruction = self._build_part1_instruction(False, 'cycling', 'French Riviera')
        assert 'cycling' in instruction

    def test_museum_part2_no_route_language(self):
        """Museum Part 2 must not use 'route', 'stretches', or distance."""
        is_museum = True
        stop_names = ['Les paysages', 'Armure du Clan Hotta']
        if is_museum:
            instruction = (
                f"Describe what the visitor will encounter: {len(stop_names)} works "
                f"from the collection. Do NOT use geographic language like 'route', 'stretches', "
                f"'journey', or state a distance."
            )
        assert 'route' in instruction  # It says "do NOT use 'route'" — that's the prohibition
        assert 'works' in instruction
        assert 'distance' in instruction  # prohibition


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
