#!/usr/bin/env python3
"""Tests for LOCAL-287: Gloss gate composes clauses, never splices sentences.

Verifies:
  - Host sentence descriptor detection (suppresses glossing already-explained refs)
  - Mechanical guards reject bad glosses
  - Validation catches all four fault types from the bug report

Run with: python3 -m pytest tests/test_local287_gloss_composition.py -v -s
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unglossed_reference_gate import (
    detect_unglossed_references,
    _host_sentence_already_explains,
    _has_nearby_gloss,
    validate_gloss,
    _guard_spliced_sentence,
    _guard_doubled_name,
    _guard_trailing_preposition,
    _guard_length,
    _guard_host_duplication,
    _insert_composed_gloss,
)
from style_validator_detector import _split_sentences


# ═══════════════════════════════════════════════════════════════════════════════
# HOST SENTENCE ALREADY EXPLAINS — suppression tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestHostSentenceAlreadyExplains:
    """LOCAL-287: If the host sentence already identifies the person, the gate
    must not fire. Half the damage in the bug report is the gate glossing names
    that were already explained."""

    def test_spanish_architect_before_name(self):
        """'Spanish architect Josep Lluís Sert' — already explained."""
        sent = "designed by Spanish architect Josep Lluís Sert, is a masterpiece"
        assert _host_sentence_already_explains(sent, "Josep Lluís Sert")

    def test_french_philosopher_before_name(self):
        """'French philosopher Jean-Paul Sartre' — already explained."""
        sent = "attracting luminaries like the French philosopher Jean-Paul Sartre"
        assert _host_sentence_already_explains(sent, "Jean-Paul Sartre")

    def test_italian_painter_before_name(self):
        """'Italian painter Amedeo Modigliani' — already explained."""
        sent = "The gallery features works by Italian painter Amedeo Modigliani."
        assert _host_sentence_already_explains(sent, "Amedeo Modigliani")

    def test_bare_name_not_explained(self):
        """'Josep Lluís Sert' with no descriptor — NOT explained."""
        sent = "The museum building was designed by Josep Lluís Sert."
        assert not _host_sentence_already_explains(sent, "Josep Lluís Sert")

    def test_bare_name_in_list_not_explained(self):
        """'Yves Montand' in a list with no descriptor — NOT explained."""
        sent = "the village was frequented by Yves Montand, Simone Signoret, and Lino Ventura"
        assert not _host_sentence_already_explains(sent, "Yves Montand")

    def test_descriptor_after_name(self):
        """'Sert, the Catalan architect' — explained by appositive after."""
        sent = "Josep Lluís Sert, the Catalan architect, designed the building."
        assert _host_sentence_already_explains(sent, "Josep Lluís Sert")

    def test_not_flagged_when_already_explained(self):
        """Full detection: 'Spanish architect X' should not be flagged."""
        text = "The building, designed by Spanish architect Josep Lluís Sert, is a masterpiece of modern architecture."
        refs = detect_unglossed_references(text)
        entities = [r['entity'] for r in refs]
        assert not any('Sert' in e for e in entities), \
            f"Josep Lluís Sert should NOT be flagged (already explained). Got: {entities}"


# ═══════════════════════════════════════════════════════════════════════════════
# MECHANICAL GUARDS — the five post-gloss validators
# ═══════════════════════════════════════════════════════════════════════════════

class TestMechanicalGuards:
    """LOCAL-287: Five mechanical guards that reject bad glosses."""

    # Guard 1: Spliced sentence detection
    def test_guard1_spliced_sentence_period_comma(self):
        """'., ' pattern — a full stop followed by comma."""
        assert not _guard_spliced_sentence("The influential French philosopher and playwright known for existentialism., and Pablo Picasso")

    def test_guard1_capital_sentence_spliced(self):
        """Capital-letter sentence spliced mid-sentence."""
        gloss = "The building was designed by Spanish architect Josep Lluís Sert"
        # This is a full sentence, not an appositive
        assert not _guard_spliced_sentence(gloss)

    def test_guard1_proper_appositive_ok(self):
        """Proper appositive clause passes."""
        assert _guard_spliced_sentence("the existentialist philosopher")

    # Guard 2: Doubled name
    def test_guard2_doubled_name(self):
        """Name appears twice within 120 chars."""
        sent = "Josep Lluís Sert, The building was designed by Spanish architect Josep Lluís Sert., is a masterpiece"
        assert not _guard_doubled_name(sent, "Josep Lluís Sert")

    def test_guard2_single_name_ok(self):
        """Name appears once — passes."""
        sent = "Josep Lluís Sert, the Catalan architect, designed the building."
        assert _guard_doubled_name(sent, "Josep Lluís Sert")

    # Guard 3: Trailing preposition
    def test_guard3_trailing_on_the(self):
        """Gloss ends with 'on the.' — truncation artifact."""
        assert not _guard_trailing_preposition("established in 1964 on the.")

    def test_guard3_trailing_of(self):
        """Gloss ends with 'of' — truncation artifact."""
        assert not _guard_trailing_preposition("the ruler of")

    def test_guard3_trailing_in(self):
        """Gloss ends with 'in.' — truncation."""
        assert not _guard_trailing_preposition("who worked in.")

    def test_guard3_proper_ending_ok(self):
        """Gloss ending with a content word passes."""
        assert _guard_trailing_preposition("the existentialist philosopher")

    # Guard 4: Length
    def test_guard4_too_long(self):
        """Gloss over 12 words fails."""
        assert not _guard_length("the influential French philosopher and playwright known for existentialism who wrote many books and plays")

    def test_guard4_short_ok(self):
        """Gloss under 12 words passes."""
        assert _guard_length("the existentialist philosopher")

    # Guard 5: Host duplication
    def test_guard5_duplicates_host(self):
        """Gloss duplicates ≥6 consecutive words from host."""
        host = "the village bustled with the presence of French actors Yves Montand"
        gloss = "the presence of French actors Yves Montand during"
        assert not _guard_host_duplication(gloss, host)

    def test_guard5_unique_gloss_ok(self):
        """Gloss with unique text passes."""
        host = "the village was frequented by Yves Montand"
        gloss = "the acclaimed French singer and actor"
        assert _guard_host_duplication(gloss, host)


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATE_GLOSS integration — catches all four bug-report faults
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateGlossIntegration:
    """Validate that all four fault types from the bug report are caught."""

    def test_fault1_sentence_spliced_mid_sentence(self):
        """Fault 1: A whole sentence inserted mid-sentence."""
        gloss = "The influential French philosopher and playwright known for existentialism."
        host = "attracting luminaries like Jean-Paul Sartre, The influential French philosopher and playwright known for existentialism., and Pablo Picasso"
        passed, reason = validate_gloss(gloss, host, "Jean-Paul Sartre")
        assert not passed, f"Should fail: spliced sentence. Got: passed={passed}"

    def test_fault2_gloss_repeats_name(self):
        """Fault 2: The gloss repeats the name it is glossing."""
        host = "Josep Lluís Sert, The building was designed by Spanish architect Josep Lluís Sert., is a masterpiece"
        gloss = "The building was designed by Spanish architect Josep Lluís Sert."
        passed, reason = validate_gloss(gloss, host, "Josep Lluís Sert")
        assert not passed, f"Should fail: doubled name. Got: passed={passed}, reason={reason}"

    def test_fault3_gloss_repeats_host_text(self):
        """Fault 3: The gloss repeats the host sentence verbatim."""
        host = "the village bustled with the presence of French actors Yves Montand, the village was frequented by French actors Yves Montand"
        gloss = "the village was frequented by French actors Yves Montand"
        passed, reason = validate_gloss(gloss, host, "Yves Montand")
        assert not passed, f"Should fail: host duplication. Got: passed={passed}, reason={reason}"

    def test_fault4_truncation(self):
        """Fault 4: Truncation — gloss ends with preposition/article."""
        gloss = "established by Marguerite and Aimé Maeght in 1964 on the"
        host = "Marguerite and Aimé Maeght, established by Marguerite and Aimé Maeght in 1964 on the., stands as"
        passed, reason = validate_gloss(gloss, host, "Marguerite and Aimé Maeght")
        assert not passed, f"Should fail: trailing preposition or doubled name. Got: passed={passed}, reason={reason}"

    def test_good_gloss_passes(self):
        """A proper composed gloss passes all guards."""
        gloss = "the existentialist philosopher"
        host = "attracting luminaries like Jean-Paul Sartre, the existentialist philosopher, and Pablo Picasso"
        passed, reason = validate_gloss(gloss, host, "Jean-Paul Sartre")
        assert passed, f"Good gloss should pass. Got: reason={reason}"


# ═══════════════════════════════════════════════════════════════════════════════
# INSERTION — composed glosses read naturally
# ═══════════════════════════════════════════════════════════════════════════════

class TestComposedGlossInsertion:
    """Composed glosses inserted as proper appositives."""

    def test_mid_sentence_insertion(self):
        """Appositive inserted mid-sentence reads naturally."""
        sent = "attracting luminaries like Jean-Paul Sartre and Pablo Picasso"
        result = _insert_composed_gloss(sent, "Jean-Paul Sartre", "the existentialist philosopher")
        assert "Jean-Paul Sartre, the existentialist philosopher," in result
        assert "and Pablo Picasso" in result

    def test_end_of_sentence_insertion(self):
        """Appositive before period."""
        sent = "The museum was designed by Josep Lluís Sert."
        result = _insert_composed_gloss(sent, "Josep Lluís Sert", "the Catalan architect")
        assert "Josep Lluís Sert, the Catalan architect." in result

    def test_no_double_comma(self):
        """If entity already has comma after, don't double it."""
        sent = "built by Josep Lluís Sert, the museum features modern art"
        result = _insert_composed_gloss(sent, "Josep Lluís Sert", "the Catalan architect")
        assert ",," not in result
        assert "Sert, the Catalan architect," in result
