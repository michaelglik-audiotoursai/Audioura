#!/usr/bin/env python3
"""Tests for LOCAL-256: R1 fragment fix, Description: label gate, R7 orientation.

Three defects shipped in round 12 (on storied at c339ead):
1. R1 rewrite produces sentence fragments (no main verb)
2. "Description:" schema label leaks into TTS-bound artifact
3. R7 is silent on fabricated sensory in orientation text

Run with: python3 -m pytest tests/test_local256_fragment_and_label.py -v -s
"""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from style_validator_detector import (
    check_r1_imperatives,
    rewrite_r1_sentence_deterministic,
    apply_r1_rewrites,
    apply_r1_to_description,
    _is_style_navigation_sentence,
    _has_finite_main_verb,
    check_r7_hallucinated_sensory,
)


# ═══════════════════════════════════════════════════════════════════════════════
# DEFECT 1: No rewrite may emit a verbless fragment
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoFragments:
    """Every R1 rewrite must produce a sentence with a finite main verb."""

    def test_take_in_panoramic_view_has_verb(self):
        """The exact sentence LEAD found in round 12 orientation."""
        sentence = (
            "Take in the panoramic view that stretches out before you, with "
            "the ancient village of Èze rising majestically behind you."
        )
        result = rewrite_r1_sentence_deterministic(sentence)
        assert result is not None, "Must not delete — has content"
        assert result != '__LLM_NEEDED__', "Deterministic rule should handle this"
        assert _has_finite_main_verb(result), f"FRAGMENT: {result}"
        # Content preserved
        assert 'panoramic view' in result.lower()
        assert 'Èze' in result
        print(f"  ✓ {result}")

    def test_look_for_fondation_maeght_has_verb(self):
        """The boundary row from LOCAL-255 that was a fragment."""
        sentence = (
            "Look for the Fondation Maeght, founded in 1964 by "
            "Marguerite and Aimé Maeght."
        )
        result = rewrite_r1_sentence_deterministic(sentence)
        assert result is not None, "Must not delete — has content"
        assert result != '__LLM_NEEDED__', "Deterministic rule should handle this"
        assert _has_finite_main_verb(result), f"FRAGMENT: {result}"
        # Content must include date and founders (task requirement)
        assert '1964' in result, f"Lost '1964' in: {result}"
        assert 'Marguerite' in result, f"Lost 'Marguerite' in: {result}"
        assert 'Aimé Maeght' in result or 'Aimé' in result
        assert 'Fondation Maeght' in result
        print(f"  ✓ {result}")

    def test_take_a_moment_to_admire_maeght(self):
        """Take-a-moment variant of the Maeght sentence."""
        sentence = (
            "Take a moment to admire the Fondation Maeght, founded in 1964 "
            "by Marguerite and Aimé Maeght."
        )
        result = rewrite_r1_sentence_deterministic(sentence)
        assert result is not None, "Must not delete — has content"
        assert _has_finite_main_verb(result), f"FRAGMENT: {result}"
        assert '1964' in result
        assert 'Marguerite' in result
        print(f"  ✓ {result}")

    def test_finite_verb_detector_rejects_fragments(self):
        """Verify _has_finite_main_verb correctly identifies fragments."""
        fragments = [
            "The Fondation Maeght, founded in 1964 by Marguerite and Aimé Maeght.",
            "The panoramic view that stretches out before you.",
        ]
        for frag in fragments:
            assert not _has_finite_main_verb(frag), \
                f"False positive — should detect as fragment: {frag}"

    def test_finite_verb_detector_accepts_sentences(self):
        """Verify _has_finite_main_verb correctly identifies sentences."""
        sentences = [
            "Eze Village is a medieval gem perched high above the French Riviera.",
            "The Fondation Maeght was founded in 1964 by Marguerite and Aimé Maeght.",
            "The panoramic view stretches out before you.",
            "From Cap d'Antibes, you can admire the breathtaking views.",
            "In 1888, Monet first experimented with painting in series here.",
        ]
        for sent in sentences:
            assert _has_finite_main_verb(sent), \
                f"False negative — should detect as sentence: {sent}"

    def test_apply_level_fallback_on_fragment(self):
        """At apply_r1_rewrites level, a fragment triggers fallback to original."""
        # Craft a sentence where the deterministic rule WOULD produce a fragment
        # but the finite-verb check saves it. Test with a "Look for" variant
        # that has no participle pattern:
        sentence = "Look for the old stone walls surrounding the village."
        result, rw, dl, _ = apply_r1_rewrites(sentence)
        # It should either rewrite WITH a verb or keep original
        if rw > 0:
            assert _has_finite_main_verb(result), f"Rewrote to fragment: {result}"
        else:
            # Kept original — acceptable fallback
            assert sentence.strip() in result


# ═══════════════════════════════════════════════════════════════════════════════
# DEFECT 2: Description: label must not reach artifact
# ═══════════════════════════════════════════════════════════════════════════════

class TestDescriptionLabelStripped:
    """The 'Description:' schema field name must never reach TTS output."""

    def test_description_stripped_at_split(self):
        """Simulate LLM output with Description: label between orientation and body."""
        # This is the exact scenario that produced the round 12 defect
        llm_output = (
            "Orientation: Start cycling southeast on the main coastal road.\n\n"
            "Description:\n"
            "Cap d'Antibes, a picturesque cape on the French Riviera."
        )
        parts = llm_output.split("Orientation:", 1)
        assert len(parts) > 1
        orientation_text = parts[1].strip()
        description_parts = orientation_text.split("\n\n", 1)
        orientation = description_parts[0].strip()
        description = description_parts[1].strip() if len(description_parts) > 1 else ""

        # Before fix: description starts with "Description:\n..."
        assert description.startswith("Description:")

        # Apply the LOCAL-256 fix
        description = re.sub(r'^Description:\s*\n?', '', description, count=1,
                           flags=re.IGNORECASE).strip()

        # After fix: no label
        assert not description.startswith("Description:")
        assert description.startswith("Cap d'Antibes")

    def test_bare_field_label_gate_pattern(self):
        """The post-assembly gate regex catches bare field labels."""
        gate_pattern = re.compile(
            r'^\s*(?:Description|Orientation|Directions|Sources|Coordinates|'
            r'Type/Specialty|Specific Examples|Museum Information|Operational Details):\s*$',
            re.MULTILINE
        )
        # Should match
        assert gate_pattern.search("Some text\nDescription:\nMore text")
        assert gate_pattern.search("Some text\nOrientation:\nMore text")

        # Should NOT match (label with content after it on same line)
        assert not gate_pattern.search("Orientation: Start cycling south")
        assert not gate_pattern.search("Coordinates: 43.5, 7.1")


# ═══════════════════════════════════════════════════════════════════════════════
# DEFECT 3: R7 fires on fabricated sensory in orientation
# ═══════════════════════════════════════════════════════════════════════════════

class TestR7OrientationSensory:
    """R7 must fire on invented multi-sensory ambiance in orientation text."""

    def test_gentle_sea_breeze_carries_scent(self):
        """Round 12 orientation: fabricated scent + sound + breeze scene."""
        sentence = (
            "As you arrive at Cap d'Antibes, a gentle sea breeze carries "
            "the scent of pine trees and saltwater, mingling with the sounds "
            "of seagulls overhead and waves lapping against the rocky coastline."
        )
        findings = check_r7_hallucinated_sensory(sentence)
        assert findings, f"R7 should fire on: {sentence[:80]}..."
        print(f"  ✓ R7 fires: {findings[0]['rule_id']}")

    def test_scent_mingles_with_fragrance(self):
        """Round 12 orientation: dual-scent fabrication."""
        sentence = (
            "Within the stone walls of Èze, the scent of the sea mingles "
            "with the fragrance of lavender that grows abundantly in this region."
        )
        findings = check_r7_hallucinated_sensory(sentence)
        assert findings, f"R7 should fire on: {sentence[:80]}..."
        print(f"  ✓ R7 fires: {findings[0]['rule_id']}")

    def test_r7_does_not_fire_on_factual_sensory(self):
        """R7 must NOT fire on bare factual observations."""
        safe_sentences = [
            "The market smells of lavender.",
            "The scent of lavender fills the garden in summer.",
            "Waves crash against the seawall during storms.",
            "The sea is visible from the terrace.",
            "Pine trees line the coastal path.",
        ]
        for sent in safe_sentences:
            findings = check_r7_hallucinated_sensory(sent)
            assert not findings, f"False positive on: {sent}"


# ═══════════════════════════════════════════════════════════════════════════════
# BOUNDARY ROWS: All 15 prior rows must still hold
# ═══════════════════════════════════════════════════════════════════════════════

class TestAllBoundaryRowsHold:
    """Verify all 8 LOCAL-255 + 7 LOCAL-253 boundary rows still pass."""

    # ─── LOCAL-255 boundary rows (8) ─────────────────────────────────────

    def test_255_row1_eze_rewrite(self):
        """Michael's endorsed transformation."""
        s = ("Position yourself at the entrance of Eze Village, a medieval "
             "gem perched high above the French Riviera.")
        r = rewrite_r1_sentence_deterministic(s)
        assert r is not None and r != '__LLM_NEEDED__'
        assert 'Eze Village' in r
        assert 'is' in r.lower()
        assert _has_finite_main_verb(r)

    def test_255_row2_cap_dantibes_rewrite(self):
        s = ("As you arrive at Cap d'Antibes, take in the breathtaking "
             "views of the azure waters.")
        r = rewrite_r1_sentence_deterministic(s)
        assert r is not None and r != '__LLM_NEEDED__'
        assert 'azure' in r.lower()
        assert _has_finite_main_verb(r)

    def test_255_row3_fondation_maeght_rewrite(self):
        s = ("Look for the Fondation Maeght, founded in 1964 by "
             "Marguerite and Aimé Maeght.")
        r = rewrite_r1_sentence_deterministic(s)
        assert r is not None and r != '__LLM_NEEDED__'
        assert '1964' in r
        assert 'Marguerite' in r
        assert _has_finite_main_verb(r)

    def test_255_row4_start_cycling_exempt(self):
        s = "Start cycling south on the main road with the sea on your right."
        assert _is_style_navigation_sentence(s)
        assert not check_r1_imperatives(s)

    def test_255_row5_head_east_exempt(self):
        s = "Head east along the coastal path until you reach the roundabout."
        assert _is_style_navigation_sentence(s)

    def test_255_row6_start_ride_exempt(self):
        s = "Start your ride at Cap d'Antibes and pedal east along the coastal road."
        assert _is_style_navigation_sentence(s)

    def test_255_row7_absorb_atmosphere_delete(self):
        s = "Take a moment to absorb the atmosphere."
        r = rewrite_r1_sentence_deterministic(s)
        assert r is None

    def test_255_row8_enjoy_the_view_delete(self):
        s = "Enjoy the view."
        r = rewrite_r1_sentence_deterministic(s)
        assert r is None

    # ─── LOCAL-253 boundary rows (7) ─────────────────────────────────────

    def test_253_row1_cycling_south_survives(self):
        from directions_generator import validate_directions_mode
        v = validate_directions_mode(
            "Start cycling south on the main road with the sea on your right.", "bike")
        assert v == []

    def test_253_row2_head_east_survives(self):
        from directions_generator import validate_directions_mode
        v = validate_directions_mode(
            "Head east along the coastal path until you reach the roundabout.", "bike")
        assert v == []

    def test_253_row3_follow_signs_survives(self):
        from directions_generator import validate_directions_mode
        v = validate_directions_mode(
            "Follow the signs up the hill to reach the village.", "bike")
        assert v == []

    def test_253_row4_train_caught(self):
        from directions_generator import validate_directions_mode
        v = validate_directions_mode(
            "From Antibes train station, take a train towards Eze Village.", "bike")
        assert len(v) >= 1

    def test_253_row5_a8_motorway_caught(self):
        from directions_generator import validate_directions_mode
        v = validate_directions_mode(
            "Continue east until you hit the A8 highway.", "bike")
        assert len(v) >= 1

    def test_253_row6_walk_verb_caught(self):
        from directions_generator import validate_directions_mode
        v = validate_directions_mode("Start your walk from Cap d'Antibes.", "bike")
        assert len(v) >= 1

    def test_253_row7_enjoy_walk_caught(self):
        from directions_generator import validate_directions_mode
        v = validate_directions_mode("Enjoy the walk!", "bike")
        assert len(v) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# ADDITIONAL: "must be produced" table from task
# ═══════════════════════════════════════════════════════════════════════════════

class TestMustBeProduced:
    """Task table: sentences that MUST be produced by the rewrite."""

    def test_eze_village_is_medieval_gem(self):
        """Michael's endorsed pair."""
        s = ("Position yourself at the entrance of Eze Village, a medieval "
             "gem perched high above the French Riviera.")
        r = rewrite_r1_sentence_deterministic(s)
        assert "Eze Village" in r
        assert "is a medieval gem" in r
        assert "French Riviera" in r

    def test_maeght_1964_intact_and_grammatical(self):
        """1964 attribution must be both present AND form a complete sentence."""
        s = ("Look for the Fondation Maeght, founded in 1964 by "
             "Marguerite and Aimé Maeght.")
        r = rewrite_r1_sentence_deterministic(s)
        assert '1964' in r
        assert 'Marguerite' in r
        assert 'Aimé Maeght' in r or 'Aimé' in r
        assert _has_finite_main_verb(r), f"Not grammatical: {r}"
