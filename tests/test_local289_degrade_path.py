#!/usr/bin/env python3
"""Tests for LOCAL-289: Degrade path removes the whole governed construction.

Verifies:
  - Possessive clitics are handled: "X's landscape" → "the landscape"
  - Stacked prepositions are cleaned: "along with to" → "to"
  - Dangling articles are removed: "tour a." → "tour."
  - Empty appositives are cleaned: ", ," → ","
  - Sentence-drop fallback when repair fails
  - Full-text validation catches all five guard patterns

Run with: python3 -m pytest tests/test_local289_degrade_path.py -v -s
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unglossed_reference_gate import (
    _degrade_reference_in_text,
    _excise_governed_construction,
    _clean_degrade_artifacts,
    _degrade_sentence_is_wellformed,
    _drop_sentence_from_text,
    validate_degrade_output,
    validate_and_repair_full_text,
    _DEGRADE_GUARD_ORPHAN_HYPHEN,
)


# ═══════════════════════════════════════════════════════════════════════════════
# POSSESSIVE HANDLING — "X's landscape" → "the landscape"
# ═══════════════════════════════════════════════════════════════════════════════

class TestPossessiveHandling:
    """LOCAL-289 bug #2: "'s landscape" must never appear in output."""

    def test_possessive_removed_basic(self):
        """'Entity's landscape' → 'the landscape'"""
        sent = "showcases nature's enduring power in shaping Cap Ferrat's landscape."
        result = _excise_governed_construction(sent, "Cap Ferrat")
        # Cap Ferrat's possessive should be removed; nature's is a different entity and stays
        assert "Cap Ferrat" not in result, f"Entity survived: {result}"
        assert "Cap Ferrat's" not in result, f"Entity possessive survived: {result}"
        assert "the landscape" in result or "landscape" in result
        # nature's is valid — it belongs to "nature", not to the excised entity
        assert "nature's" in result.lower()

    def test_possessive_removed_mid_sentence(self):
        """'Entity's history' in a mid-sentence position."""
        sent = "The region celebrates Jean-Pierre Duval's contributions to art."
        result = _excise_governed_construction(sent, "Jean-Pierre Duval")
        assert "'s" not in result, f"Possessive survived: {result}"
        # Should produce something like "The region celebrates the contributions to art."
        assert "contributions to art" in result

    def test_possessive_with_preceding_prep(self):
        """'in shaping X's landscape' — entity's possessive removed, others stay."""
        sent = "showcases nature's enduring power in shaping Henri Matisse's landscape."
        result = _excise_governed_construction(sent, "Henri Matisse")
        # Henri Matisse's possessive should be removed
        assert "Henri Matisse" not in result, f"Entity survived: {result}"
        assert "the landscape" in result or "landscape" in result
        # nature's is valid and should remain
        assert "nature's" in result.lower()

    def test_unicode_possessive(self):
        """Curly apostrophe: X\u2019s"""
        sent = "The museum displays Marc Chagall\u2019s finest works."
        result = _excise_governed_construction(sent, "Marc Chagall")
        assert "\u2019s" not in result, f"Unicode possessive survived: {result}"


# ═══════════════════════════════════════════════════════════════════════════════
# STACKED PREPOSITIONS — "along with to the northeast" fixed
# ═══════════════════════════════════════════════════════════════════════════════

class TestStackedPrepositions:
    """LOCAL-289 bug #1: Two prepositions with no object between."""

    def test_along_with_entity_removed(self):
        """'along with Entity to the northeast' → 'to the northeast'"""
        sent = "The iconic cape, along with Fort Royal to the northeast, has witnessed centuries of maritime history."
        result = _excise_governed_construction(sent, "Fort Royal")
        assert "along with to" not in result.lower(), f"Stacked preps: {result}"
        assert "with to" not in result.lower(), f"Stacked preps: {result}"
        # The sentence should still make sense
        assert "has witnessed centuries" in result

    def test_with_entity_before_prep(self):
        """'with Entity to' → no stacked preps."""
        sent = "The town, with Pierre Bonnard to guide you, offers stunning views."
        result = _excise_governed_construction(sent, "Pierre Bonnard")
        assert "with to" not in result.lower(), f"Stacked preps: {result}"

    def test_of_entity_in(self):
        """'of Entity in' shouldn't leave 'of in'."""
        sent = "The beauty of Villa Ephrussi in the bay was legendary."
        result = _excise_governed_construction(sent, "Villa Ephrussi")
        assert "of in" not in result.lower(), f"Stacked preps: {result}"

    def test_by_entity_from(self):
        """'by Entity from' shouldn't leave 'by from'."""
        sent = "Created by Jacques Médecin from local stone."
        result = _excise_governed_construction(sent, "Jacques Médecin")
        # After removing "by Entity", should clean up properly
        assert "by from" not in result.lower(), f"Stacked preps: {result}"


# ═══════════════════════════════════════════════════════════════════════════════
# DANGLING ARTICLES — "tour a." fixed
# ═══════════════════════════════════════════════════════════════════════════════

class TestDanglingArticles:
    """LOCAL-289 bug #3: Article at end of sentence with no noun."""

    def test_trailing_article_a(self):
        """'tour a.' → 'tour.'"""
        sent = "The sacred space serves as a sanctuary during your cycling tour a."
        # This would happen if "X" was after "tour" and before "." with "a" left over
        result = _clean_degrade_artifacts(sent)
        assert not result.endswith("a."), f"Dangling article: {result}"

    def test_trailing_article_the(self):
        """'visited the.' → 'visited.'"""
        sent = "Many travelers visited the."
        result = _clean_degrade_artifacts(sent)
        assert not result.endswith("the."), f"Dangling article: {result}"

    def test_sentence_ending_preposition(self):
        """'traveled to.' → should be caught by guard."""
        sent = "The pilgrims traveled to."
        assert not _degrade_sentence_is_wellformed(sent)


# ═══════════════════════════════════════════════════════════════════════════════
# EMPTY APPOSITIVES — ", ," cleaned
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmptyAppositives:
    """Empty appositives from excised entities."""

    def test_double_comma(self):
        """', ,' → ','"""
        sent = "The cape, , has witnessed centuries."
        result = _clean_degrade_artifacts(sent)
        assert ", ," not in result, f"Empty appositive: {result}"
        assert ",," not in result

    def test_comma_period(self):
        """', .' → '.'"""
        sent = "The region is known for, ."
        result = _clean_degrade_artifacts(sent)
        assert ", ." not in result, f"Comma-period survived: {result}"
        assert result.endswith(".")


# ═══════════════════════════════════════════════════════════════════════════════
# SENTENCE-DROP FALLBACK — broken sentences are removed entirely
# ═══════════════════════════════════════════════════════════════════════════════

class TestSentenceDropFallback:
    """When repair can't produce well-formed text, drop the sentence."""

    def test_drop_sentence_basic(self):
        """Sentence removed from text entirely."""
        text = "First sentence. Bad sentence here. Third sentence."
        result = _drop_sentence_from_text(text, "Bad sentence here.")
        assert "Bad sentence" not in result
        assert "First sentence." in result
        assert "Third sentence." in result

    def test_degrade_drops_on_malformed(self):
        """Full degrade path drops sentence when excision fails."""
        text = "Good sentence here. The iconic cape, along with Fort Royal to the northeast, has witnessed centuries. Another good sentence."
        # If excision of Fort Royal can't produce well-formed text, sentence drops
        # (In practice our excision handles this, but test the fallback mechanism)
        result = _degrade_reference_in_text(text, "Fort Royal",
            "The iconic cape, along with Fort Royal to the northeast, has witnessed centuries.")
        # Either excision worked OR sentence was dropped — either way no stacked preps
        assert "along with to" not in result.lower()
        assert "with to" not in result.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# DEGRADE GUARDS — five patterns that must never appear
# ═══════════════════════════════════════════════════════════════════════════════

class TestDegradeGuards:
    """The five guards on degrade output."""

    def test_guard_bare_possessive(self):
        """' 's' with no word before fails."""
        assert not _degrade_sentence_is_wellformed("showcases power in shaping 's landscape.")

    def test_guard_stacked_preps(self):
        """'with to', 'of in' etc. fail."""
        assert not _degrade_sentence_is_wellformed("The cape, along with to the northeast, has witnessed centuries.")
        assert not _degrade_sentence_is_wellformed("The beauty of in the bay was legendary.")

    def test_guard_sentence_ending_func(self):
        """Sentence ending in article/prep fails."""
        assert not _degrade_sentence_is_wellformed("The tour concludes at the.")
        assert not _degrade_sentence_is_wellformed("Many visitors traveled to.")
        assert not _degrade_sentence_is_wellformed("Your cycling tour a.")

    def test_guard_empty_appositive(self):
        """', ,' or ', .' fails."""
        assert not _degrade_sentence_is_wellformed("The cape, , has witnessed centuries.")
        assert not _degrade_sentence_is_wellformed("Known for its beauty, .")

    def test_guard_double_space(self):
        """Double space fails."""
        assert not _degrade_sentence_is_wellformed("The cape  has witnessed centuries.")

    def test_wellformed_passes(self):
        """Normal sentences pass all guards."""
        assert _degrade_sentence_is_wellformed("The iconic cape has witnessed centuries of maritime history.")
        assert _degrade_sentence_is_wellformed("Visitors enjoy the stunning coastal views.")


# ═══════════════════════════════════════════════════════════════════════════════
# FULL-TEXT VALIDATION — validate_degrade_output
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullTextValidation:
    """validate_degrade_output catches all violations across full text."""

    def test_clean_text_no_violations(self):
        """Well-formed text returns empty violations list."""
        text = "The tour begins at the harbor. Continue along the coastal path. The lighthouse offers panoramic views."
        violations = validate_degrade_output(text)
        assert violations == [], f"Unexpected violations: {violations}"

    def test_catches_bare_possessive(self):
        """Detects bare possessive in full text."""
        text = "The tour starts here. Nature's power shapes 's landscape. Continue walking."
        violations = validate_degrade_output(text)
        guards = [v['guard'] for v in violations]
        assert 'bare_possessive' in guards, f"Missed bare possessive: {violations}"

    def test_catches_stacked_preps(self):
        """Detects stacked prepositions."""
        text = "The cape, along with to the northeast, has centuries of history."
        violations = validate_degrade_output(text)
        guards = [v['guard'] for v in violations]
        assert 'stacked_prepositions' in guards, f"Missed stacked preps: {violations}"

    def test_catches_sentence_ending_func(self):
        """Detects sentence ending in function word."""
        text = "Start at the harbor. Your cycling tour a. Continue east."
        violations = validate_degrade_output(text)
        guards = [v['guard'] for v in violations]
        assert 'sentence_ending_function_word' in guards, f"Missed: {violations}"

    def test_catches_empty_appositive(self):
        """Detects empty appositive."""
        text = "The cape, , has witnessed centuries of history."
        violations = validate_degrade_output(text)
        guards = [v['guard'] for v in violations]
        assert 'empty_appositive' in guards, f"Missed: {violations}"

    def test_catches_double_space(self):
        """Detects double spaces."""
        text = "The cape  has witnessed centuries."
        violations = validate_degrade_output(text)
        guards = [v['guard'] for v in violations]
        assert 'double_space' in guards, f"Missed: {violations}"


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATE_AND_REPAIR — drops offending sentences from full text
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateAndRepair:
    """validate_and_repair_full_text drops bad sentences."""

    def test_drops_bad_sentence(self):
        """Sentence with violation is removed."""
        text = "Good sentence here. The cape, along with to the northeast, has witnessed centuries. Another good sentence."
        repaired, dropped = validate_and_repair_full_text(text)
        assert "with to" not in repaired
        assert len(dropped) >= 1
        assert "Good sentence here." in repaired
        assert "Another good sentence." in repaired

    def test_clean_text_unchanged(self):
        """Clean text passes through unchanged."""
        text = "The harbor dates to Roman times. Continue along the promenade."
        repaired, dropped = validate_and_repair_full_text(text)
        assert dropped == []
        assert repaired == text


# ═══════════════════════════════════════════════════════════════════════════════
# REGRESSION — the three verbatim examples from the bug report
# ═══════════════════════════════════════════════════════════════════════════════

class TestBugReportExamples:
    """The exact three broken sentences from the LOCAL-289 bug report."""

    def test_bug1_stacked_prepositions(self):
        """'along with to the northeast' — stacked preps must not survive."""
        sent = "The iconic cape, along with Fort Royal to the northeast, has witnessed centuries of maritime history."
        result = _excise_governed_construction(sent, "Fort Royal")
        assert "along with to" not in result.lower(), f"Bug #1 not fixed: {result}"
        assert "with to" not in result.lower(), f"Bug #1 not fixed: {result}"
        assert _degrade_sentence_is_wellformed(result), f"Result not wellformed: {result}"

    def test_bug2_bare_possessive(self):
        """'in shaping 's landscape' — possessive must not survive."""
        sent = "showcases nature's enduring power in shaping Cap Ferrat's landscape."
        result = _excise_governed_construction(sent, "Cap Ferrat")
        assert " 's" not in result, f"Bug #2 not fixed: {result}"
        assert "'s landscape" not in result or "nature's" in result, f"Bug #2 not fixed: {result}"
        # nature's is fine — it's Cap Ferrat's that must go
        assert "Cap Ferrat" not in result

    def test_bug3_dangling_article(self):
        """'during your cycling tour a.' — dangling article must not survive."""
        sent = "The sacred space serves as a sanctuary for both the body and the soul during your cycling tour a."
        # This is the END result after a prior broken degrade — test the guard catches it
        assert not _degrade_sentence_is_wellformed(sent), \
            f"Guard should reject this: {sent}"

    def test_full_degrade_bug1(self):
        """Full _degrade_reference_in_text on bug #1."""
        text = "Some intro text. The iconic cape, along with Fort Royal to the northeast, has witnessed centuries of maritime history. More text here."
        result = _degrade_reference_in_text(text, "Fort Royal",
            "The iconic cape, along with Fort Royal to the northeast, has witnessed centuries of maritime history.")
        assert "along with to" not in result.lower()
        assert "with to" not in result.lower()

    def test_full_degrade_bug2(self):
        """Full _degrade_reference_in_text on bug #2."""
        text = "Some intro. The area showcases nature's enduring power in shaping Cap Ferrat's landscape. More follows."
        sent = "The area showcases nature's enduring power in shaping Cap Ferrat's landscape."
        result = _degrade_reference_in_text(text, "Cap Ferrat", sent)
        assert " 's landscape" not in result or "nature's" in result.split("'s landscape")[0]
        # The critical check: no BARE possessive (space + 's)
        import re
        bare_poss = re.search(r"\s's\b", result)
        if bare_poss:
            # Check it's nature's (which is valid), not a bare orphan
            ctx = result[max(0, bare_poss.start()-10):bare_poss.end()+10]
            assert "nature's" in ctx, f"Bare possessive found: '{ctx}' in '{result}'"


# ═══════════════════════════════════════════════════════════════════════════════
# PROSE-READ REGRESSION — issues found in generation run
# ═══════════════════════════════════════════════════════════════════════════════

class TestProseReadRegression:
    """Issues found by prose-reading the generated tours (D161)."""

    def test_designated_as_of_france(self):
        """'designated as [Remarkable Gardens] of France' must not leave 'as of'."""
        sent = "Outside, the gardens are designated as Remarkable Gardens of France, featuring fountains."
        result = _excise_governed_construction(sent, "Remarkable Gardens")
        assert "as of" not in result.lower(), f"'as of' survived: {result}"
        assert _degrade_sentence_is_wellformed(result), f"Not wellformed: {result}"

    def test_built_on_via_julia(self):
        """'Built on Via Julia Augusta, it marks' must not leave 'Built on it marks'."""
        sent = "Built on Via Julia Augusta, it marks the triumph and the might of an empire."
        result = _excise_governed_construction(sent, "Via Julia Augusta")
        # Should either drop sentence or repair to something sensible
        assert "on it marks" not in result.lower(), f"'on it marks' survived: {result}"

    def test_hyphenated_name_pierre_yves(self):
        """'Pierre-Yves Trémois' degrading only 'Yves Trémois' must not leave 'Pierre-'."""
        sent = "Pierre-Yves Trémois envisioned these landscapes as essential."
        result = _excise_governed_construction(sent, "Yves Trémois")
        assert "Pierre-" not in result or "Pierre-Yves" in result, \
            f"Orphan hyphen: {result}"
        assert not _DEGRADE_GUARD_ORPHAN_HYPHEN.search(result), \
            f"Orphan hyphen guard fired: {result}"

    def test_hyphenated_possessive(self):
        """'Pierre-Yves Trémois' vision' — removing 'Yves Trémois' must not leave 'Pierre- ''."""
        sent = "This aligns with Pierre-Yves Trémois' vision and influence."
        result = _excise_governed_construction(sent, "Yves Trémois")
        assert "Pierre- " not in result, f"Orphan hyphen: {result}"
        assert "Pierre-'" not in result, f"Orphan hyphen + quote: {result}"

    def test_guard_catches_orphan_hyphen(self):
        """Guard detects 'Pierre- envisioned'."""
        assert not _degrade_sentence_is_wellformed(
            "Pierre- envisioned these landscapes as essential.")
        assert not _degrade_sentence_is_wellformed(
            "This aligns with Pierre- ' vision and Kenzo Tange's influence.")

    def test_guard_catches_designated_as_of(self):
        """Guard detects 'designated as of France'."""
        assert not _degrade_sentence_is_wellformed(
            "The gardens are designated as of France, featuring fountains.")
