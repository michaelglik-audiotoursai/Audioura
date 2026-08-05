#!/usr/bin/env python3
"""Tests for LOCAL-269: Unglossed-reference gate.

The inverse of LOCAL-263: a fact that assumes knowledge the listener lacks.

Run with: python3 -m pytest tests/test_local269_unglossed_reference_gate.py -v -s
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unglossed_reference_gate import (
    detect_unglossed_references,
    _is_well_known,
    _has_nearby_gloss,
    _insert_gloss,
)
from style_validator_detector import (
    _split_sentences,
    _is_style_navigation_sentence,
)


# ═══════════════════════════════════════════════════════════════════════════════
# LOCAL-269 BOUNDARY ROWS — 8 from the task specification
# ═══════════════════════════════════════════════════════════════════════════════

class TestLocal269BoundaryRows:
    """All eight boundary rows from the task spec.

    LEFT column (MUST be flagged — unglossed, audience doesn't know):
    1. "…the first town liberated during Operation Dragoon."
    2. "…designed by Josep Lluís Sert."
    3. "…hosted Jean-Paul Sartre and Pablo Picasso." (load-bearing)
    4. "…under the House of Savoy."

    RIGHT column (must NOT be flagged):
    5. "…until World War II…" (general audience knows it)
    6. "In 1888, Monet first experimented with painting in series here."
    7. "The Rue Obscure, a 130-metre fortified street built for protection." (already glossed)
    8. "Start cycling south on the main road." (navigation)
    """

    # ─── LEFT: must be FLAGGED ───────────────────────────────────────────

    def test_flag_operation_dragoon(self):
        """Operation Dragoon — general audience does not know this."""
        text = ("In the early 20th century, Saint-Tropez was a quiet fishing "
                "village until World War II, when it became the first town "
                "liberated during Operation Dragoon.")
        refs = detect_unglossed_references(text)
        entities = [r['entity'] for r in refs]
        assert any('Dragoon' in e for e in entities), \
            f"Operation Dragoon must be flagged. Got: {entities}"

    def test_flag_josep_lluis_sert(self):
        """Josep Lluís Sert — obscure architect to general audience."""
        text = ("The museum building was designed by Josep Lluís Sert.")
        refs = detect_unglossed_references(text)
        entities = [r['entity'] for r in refs]
        assert any('Sert' in e for e in entities), \
            f"Josep Lluís Sert must be flagged. Got: {entities}"

    def test_flag_sartre_picasso_load_bearing(self):
        """Sartre is the reason the hotel matters — load-bearing.

        Note: Picasso is well-known and should NOT be flagged.
        Sartre is borderline but in context of "why this hotel matters", it's
        load-bearing. The detection stage flags it; triage decides.
        """
        text = ("The La Colombe d'Or hotel has hosted Jean-Paul Sartre "
                "and Pablo Picasso.")
        refs = detect_unglossed_references(text)
        entities = [r['entity'] for r in refs]
        # Sartre should be detected (not universally known in tourism context)
        # Picasso should NOT be detected (well-known)
        # The triage stage will determine if it's load-bearing
        # At minimum: Jean-Paul Sartre should be found by person pattern
        assert any('Sartre' in e for e in entities), \
            f"Jean-Paul Sartre should be detected. Got: {entities}"
        # Picasso should be filtered out by well-known list
        assert not any(e == 'Pablo Picasso' for e in entities), \
            f"Pablo Picasso should NOT be flagged (well-known). Got: {entities}"

    def test_flag_house_of_savoy(self):
        """House of Savoy — general audience doesn't know what this means."""
        text = ("By 1388, Èze fell under the House of Savoy's rule, "
                "fortified as a stronghold due to its strategic location.")
        refs = detect_unglossed_references(text)
        entities = [r['entity'] for r in refs]
        assert any('Savoy' in e for e in entities), \
            f"House of Savoy must be flagged. Got: {entities}"

    # ─── RIGHT: must NOT be flagged ──────────────────────────────────────

    def test_skip_world_war_ii(self):
        """World War II — general audience knows it."""
        text = ("In the early 20th century, Saint-Tropez was a quiet fishing "
                "village until World War II.")
        refs = detect_unglossed_references(text)
        entities = [r['entity'] for r in refs]
        assert not any('World War' in e for e in entities), \
            f"World War II must NOT be flagged (well-known). Got: {entities}"

    def test_skip_monet(self):
        """Monet — well-known artist, no gloss needed."""
        text = ("In 1888, Monet first experimented with painting in series here.")
        refs = detect_unglossed_references(text)
        entities = [r['entity'] for r in refs]
        assert not any('Monet' in e for e in entities), \
            f"Monet must NOT be flagged (well-known). Got: {entities}"

    def test_skip_already_glossed(self):
        """Rue Obscure with appositive — already has a gloss."""
        text = ("The Rue Obscure, a 130-metre fortified street built for "
                "protection, winds beneath the seafront buildings.")
        refs = detect_unglossed_references(text)
        entities = [r['entity'] for r in refs]
        # Rue Obscure should not be flagged because it has an appositive gloss
        assert not any('Rue Obscure' in e for e in entities), \
            f"Rue Obscure must NOT be flagged (already glossed). Got: {entities}"

    def test_skip_navigation(self):
        """Navigation sentence — exempt per D164."""
        text = ("Start cycling south on the main road.")
        refs = detect_unglossed_references(text)
        assert len(refs) == 0, f"Navigation must not be processed. Got: {refs}"


# ═══════════════════════════════════════════════════════════════════════════════
# WELL-KNOWN FILTER TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestWellKnownFilter:
    """Test the well-known entity filter."""

    def test_monet_well_known(self):
        assert _is_well_known("Monet")

    def test_claude_monet_well_known(self):
        assert _is_well_known("Claude Monet")

    def test_picasso_well_known(self):
        assert _is_well_known("Pablo Picasso")

    def test_napoleon_well_known(self):
        assert _is_well_known("Napoleon")

    def test_walt_disney_well_known(self):
        assert _is_well_known("Walt Disney")

    def test_world_war_ii_well_known(self):
        assert _is_well_known("World War II")

    def test_operation_dragoon_not_known(self):
        assert not _is_well_known("Operation Dragoon")

    def test_house_of_savoy_not_known(self):
        assert not _is_well_known("House of Savoy")

    def test_josep_sert_not_known(self):
        assert not _is_well_known("Josep Lluís Sert")

    def test_beatrice_ephrussi_not_known(self):
        assert not _is_well_known("Béatrice Ephrussi de Rothschild")


# ═══════════════════════════════════════════════════════════════════════════════
# GLOSS DETECTION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestGlossDetection:
    """Test that existing glosses are detected correctly."""

    def test_appositive_detected(self):
        """Entity followed by ', a/an [explanation]' is glossed."""
        sent = "The Villa Ephrussi de Rothschild, a Tuscan-style marvel, was completed in 1912."
        sents = _split_sentences(sent)
        assert _has_nearby_gloss(sent, "Villa Ephrussi de Rothschild", sents, 0)

    def test_relative_clause_detected(self):
        """Entity followed by ', which/who [verb]' is glossed."""
        sent = "The Chapelle de la Sainte Croix, which dates back to 1306, served as a sanctuary."
        sents = _split_sentences(sent)
        assert _has_nearby_gloss(sent, "Chapelle de la Sainte Croix", sents, 0)

    def test_parenthetical_detected(self):
        """Entity followed by (explanation) is glossed."""
        sent = "Operation Dragoon (the Allied invasion of southern France in 1944) was a turning point."
        sents = _split_sentences(sent)
        assert _has_nearby_gloss(sent, "Operation Dragoon", sents, 0)

    def test_no_gloss_bare_mention(self):
        """Entity with no following explanation is NOT glossed."""
        sent = "The town was liberated during Operation Dragoon."
        sents = _split_sentences(sent)
        assert not _has_nearby_gloss(sent, "Operation Dragoon", sents, 0)

    def test_adjacent_sentence_gloss(self):
        """Explanation in adjacent sentence counts as glossed."""
        sent1 = "The villa was commissioned by Béatrice Ephrussi de Rothschild in 1905."
        sent2 = "Béatrice Ephrussi de Rothschild was a prominent French socialite and art collector."
        sents = [sent1, sent2]
        assert _has_nearby_gloss(sent1, "Béatrice Ephrussi de Rothschild", sents, 0)


# ═══════════════════════════════════════════════════════════════════════════════
# GLOSS INSERTION TESTS (STAGE 4)
# ═══════════════════════════════════════════════════════════════════════════════

class TestGlossInsertion:
    """Test that glosses are inserted correctly."""

    def test_insert_appositive_mid_sentence(self):
        """Gloss inserted as appositive after entity."""
        sent = "The town was liberated during Operation Dragoon."
        gloss = "the Allied landings in southern France in August 1944"
        result = _insert_gloss(sent, "Operation Dragoon", gloss)
        assert "Operation Dragoon, the Allied landings" in result
        assert result.endswith(".")

    def test_insert_before_period(self):
        """Gloss inserted before sentence-final period."""
        sent = "Èze fell under the House of Savoy."
        gloss = "the Italian royal dynasty that ruled until 1860"
        result = _insert_gloss(sent, "House of Savoy", gloss)
        assert "House of Savoy, the Italian royal dynasty" in result

    def test_gloss_word_count_enforcement(self):
        """Glosses longer than 14 words are truncated."""
        sent = "The building was designed by Josep Lluís Sert."
        gloss = "the Catalan architect born in Barcelona who later moved to the United States and designed many important buildings across the world"
        result = _insert_gloss(sent, "Josep Lluís Sert", gloss)
        # The inserted gloss should be at most 14 words
        # Find the inserted portion
        after_entity = result[result.find("Sert,") + 5:].strip()
        gloss_end = after_entity.find(",")
        if gloss_end < 0:
            gloss_end = after_entity.find(".")
        inserted_gloss = after_entity[:gloss_end].strip()
        assert len(inserted_gloss.split()) <= 14


# ═══════════════════════════════════════════════════════════════════════════════
# ROUND 19 INTEGRATION TEST — the sentence Michael found
# ═══════════════════════════════════════════════════════════════════════════════

class TestRound19OperationDragoon:
    """The specific sentence Michael identified in round 19."""

    def test_operation_dragoon_detected_in_full_stop(self):
        """The full stop 1 text from round 19 — Operation Dragoon flagged."""
        stop_text = (
            "The Port of Saint-Tropez, once a humble fishing village, now "
            "stands as a testament to the evolution of this coastal community. "
            "The town transformed from a military stronghold to a vibrant hub "
            "of maritime activity. In the early 20th century, Saint-Tropez was "
            "a quiet fishing village until World War II, when it became the "
            "first town liberated during Operation Dragoon. Connecting to the "
            "theme of our cycling tour, the Port of Saint-Tropez showcases the "
            "enduring ties between the region's past and present."
        )
        refs = detect_unglossed_references(stop_text)
        entities = [r['entity'] for r in refs]
        # Must flag Operation Dragoon
        assert any('Dragoon' in e for e in entities), \
            f"Operation Dragoon must be flagged in round 19 text. Got: {entities}"
        # Must NOT flag World War II
        assert not any('World War' in e for e in entities), \
            f"World War II must NOT be flagged. Got: {entities}"


# ═══════════════════════════════════════════════════════════════════════════════
# ROUND 21 INTEGRATION TEST — Eze Village references
# ═══════════════════════════════════════════════════════════════════════════════

class TestRound21EzeVillage:
    """Round 21's Eze Village text — multiple references to check."""

    def test_eze_village_references(self):
        """Multiple unglossed references in round 21 Eze stop."""
        text = (
            "By 1388, Èze fell under the House of Savoy's rule, fortified as "
            "a stronghold due to its strategic location near Nice. Traces of "
            "history linger in the air, from the French and Ottoman troops "
            "seizing the village in 1543 to Louis XIV's destruction in 1706 "
            "during the War of the Spanish Succession. Explore the Chapelle de "
            "la Sainte Croix in Èze, the village's oldest building dating back "
            "to 1306. This chapel served as a sanctuary for the White "
            "Penitents, offering aid to plague victims during tumultuous times. "
            "Walt Disney himself was captivated by the charm of Eze, visiting "
            "in 1956 and suggesting the transformation of the Château de la "
            "Chèvre d'Or into a picturesque hotel."
        )
        refs = detect_unglossed_references(text)
        entities = [r['entity'] for r in refs]

        # House of Savoy MUST be flagged (no explanation given)
        assert any('Savoy' in e for e in entities), \
            f"House of Savoy must be flagged. Got: {entities}"

        # Walt Disney must NOT be flagged (well-known)
        assert not any(e == 'Walt Disney' for e in entities), \
            f"Walt Disney must NOT be flagged. Got: {entities}"

        # Chapelle de la Sainte Croix HAS a gloss ("the village's oldest building dating back to 1306")
        assert not any('Sainte Croix' in e for e in entities), \
            f"Chapelle de la Sainte Croix must NOT be flagged (has appositive). Got: {entities}"

        # White Penitents — likely should be flagged (obscure religious order)
        # War of the Spanish Succession — should be flagged (obscure to tourists)
        assert any('Spanish Succession' in e for e in entities), \
            f"War of the Spanish Succession should be flagged. Got: {entities}"
