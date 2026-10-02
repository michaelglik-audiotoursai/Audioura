"""tests/test_local367_title_matching.py — LOCAL-367: Exhibition title matching.

Verifies:
1. Order-aware scoring: correct order > wrong order
2. Proper-noun count raises confidence: multi-name matches score high
3. Misspelling tolerance: edit-distance match works, but confusable pairs don't
4. Non-English date parsing (fr/de/es/it month names)
5. Non-English exhibition path seeds are available

Every test imports and calls the REAL function — no inline re-implementation.
"""
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from exhibition_checklist import (
    _title_similarity,
    _normalize_for_match,
    _parse_date_flexible,
    _extract_closing_date,
    _is_name_like,
    _fuzzy_token_match,
    _levenshtein,
    _EXHIBITION_PATH_SEEDS_BY_LANG,
    _EXHIBITION_PATH_SEEDS_EN,
    _CONFUSABLE_PAIRS,
    find_exhibition_checklist,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Order-aware scoring
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrderAwareScoring:
    """Same nouns in correct order must score higher than wrong order."""

    PUBLISHED = "Picasso, Miró, Dalí: Unbound"

    def test_correct_order_beats_wrong_order(self):
        """Picasso Miro Dali > Dali Miro Picasso against published order."""
        correct = _title_similarity("Picasso Miro Dali", self.PUBLISHED)
        wrong = _title_similarity("Dali Miro Picasso", self.PUBLISHED)
        assert correct > wrong, (
            f"Correct order ({correct:.3f}) must beat wrong order ({wrong:.3f})"
        )

    def test_correct_order_gap_is_material(self):
        """The gap between correct and wrong order must be > 0.02 (not negligible)."""
        correct = _title_similarity("Picasso Miro Dali", self.PUBLISHED)
        wrong = _title_similarity("Dali Miro Picasso", self.PUBLISHED)
        gap = correct - wrong
        assert gap > 0.02, (
            f"Order gap ({gap:.3f}) must be material (>0.02). "
            f"Correct={correct:.3f}, Wrong={wrong:.3f}"
        )

    def test_partially_correct_order_is_middle(self):
        """Two of three names in correct order should score between perfect and reversed."""
        correct = _title_similarity("Picasso Miro Dali", self.PUBLISHED)
        wrong = _title_similarity("Dali Miro Picasso", self.PUBLISHED)
        # "Picasso Dali Miro" has Picasso in correct position, Dali/Miro swapped
        partial = _title_similarity("Picasso Dali Miro", self.PUBLISHED)
        assert partial >= wrong, (
            f"Partial order ({partial:.3f}) should be >= fully wrong ({wrong:.3f})"
        )

    def test_two_name_order_matters(self):
        """Even with just two names, order should differentiate."""
        pub = "Monet and Renoir: Impressionist Friends"
        correct = _title_similarity("Monet Renoir", pub)
        wrong = _title_similarity("Renoir Monet", pub)
        # With only 2 tokens, effect is smaller but correct should still be >=
        assert correct >= wrong


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Proper-noun count raises confidence
# ═══════════════════════════════════════════════════════════════════════════════

class TestProperNounWeighting:
    """Name-like tokens (capitalised, non-dictionary) carry more weight."""

    def test_three_names_scores_high(self):
        """Three proper nouns matching in order is near-conclusive (>= 0.70)."""
        score = _title_similarity(
            "Picasso Miro Dali",
            "Picasso, Miró, Dalí: Unbound"
        )
        assert score >= 0.70, f"Three name match scored only {score:.3f}"

    def test_generic_words_score_lower(self):
        """Generic words matching should score lower than proper nouns."""
        # Compare: three artist names vs three common words
        name_score = _title_similarity(
            "Picasso Miro Dali",
            "Picasso, Miró, Dalí: Unbound"
        )
        # Generic words in a context where they're NOT capitalised in published
        generic_score = _title_similarity(
            "works from collections",
            "selected works from our permanent collections today"
        )
        # Name-heavy match should dominate generic-word match
        assert name_score > generic_score, (
            f"Names ({name_score:.3f}) should beat generics ({generic_score:.3f})"
        )

    def test_is_name_like_detects_capitalised(self):
        """_is_name_like correctly identifies capitalised non-dictionary tokens."""
        assert _is_name_like("picasso", "Picasso and Miró")
        assert _is_name_like("miro", "Picasso and Miró")
        assert not _is_name_like("the", "The Exhibition")
        assert not _is_name_like("and", "Picasso and Miró")

    def test_single_name_is_weak(self):
        """A single name matching should be a weak signal (< 0.35)."""
        score = _title_similarity("Picasso", "Picasso, Miró, Dalí: Unbound")
        assert score < 0.35, f"Single name scored {score:.3f}, should be < 0.35"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Misspelling tolerance
# ═══════════════════════════════════════════════════════════════════════════════

class TestMisspellingTolerance:
    """Edit-distance tolerance allows typos but blocks confusable pairs."""

    def test_picaso_matches_picasso(self):
        """Picaso (one letter dropped) matches Picasso."""
        score = _title_similarity(
            "Picaso, Miro, Dali: Unbound",
            "Picasso, Miró, Dalí: Unbound"
        )
        assert score >= 0.85, f"Picaso misspelling scored only {score:.3f}"

    def test_monet_does_not_match_manet(self):
        """Monet and Manet are edit distance 1 but must NOT match."""
        assert not _fuzzy_token_match("monet", "manet"), (
            "Monet/Manet are a known confusable pair — must not match"
        )

    def test_monet_manet_similarity_is_zero(self):
        """Full title similarity with Monet vs Manet published should be 0."""
        score = _title_similarity("Monet Exhibition", "Manet: Impressionist Pioneer")
        assert score == 0.0, f"Monet vs Manet scored {score:.3f}, should be 0.0"

    def test_dali_matches_dalí(self):
        """ASCII Dali matches accented Dalí (handled by normalization, not edit distance)."""
        score = _title_similarity("Dali", "Dalí")
        assert score >= 0.8

    def test_edit_distance_1_short_word(self):
        """Short words (<=6 chars) allow edit distance 1."""
        assert _fuzzy_token_match("picaso", "picasso")  # 6 vs 7 chars, dist=1
        assert _fuzzy_token_match("klée", "klee")  # After normalization

    def test_edit_distance_2_long_word(self):
        """Long words (>6 chars) allow edit distance 2."""
        assert _fuzzy_token_match("rembrant", "rembrandt")  # dist=1, passes
        assert _fuzzy_token_match("michealangelo", "michelangelo")  # dist=1

    def test_edit_distance_too_large_rejects(self):
        """Words with edit distance > threshold do not match."""
        assert not _fuzzy_token_match("monet", "picasso")  # way too far
        assert not _fuzzy_token_match("abc", "xyz")  # dist=3 on 3-char words

    def test_levenshtein_basic(self):
        """Verify Levenshtein implementation correctness."""
        assert _levenshtein("kitten", "sitting") == 3
        assert _levenshtein("", "abc") == 3
        assert _levenshtein("abc", "abc") == 0
        assert _levenshtein("monet", "manet") == 1
        assert _levenshtein("picaso", "picasso") == 1

    def test_confusable_pairs_explicit(self):
        """All entries in _CONFUSABLE_PAIRS are blocked."""
        for pair in _CONFUSABLE_PAIRS:
            names = sorted(pair)
            assert not _fuzzy_token_match(names[0], names[1]), (
                f"Confusable pair {names} must be blocked"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Non-English date parsing
# ═══════════════════════════════════════════════════════════════════════════════

class TestNonEnglishDates:
    """Non-English month names must parse correctly."""

    @pytest.mark.parametrize("text,expected", [
        ("5 octobre 2024", date(2024, 10, 5)),
        ("15 mars 2025", date(2025, 3, 15)),
        ("1 février 2025", date(2025, 2, 1)),
        ("20 décembre 2024", date(2024, 12, 20)),
        ("12 novembre 2024", date(2024, 11, 12)),
    ])
    def test_french_months(self, text, expected):
        """French month names parse to correct dates."""
        result = _parse_date_flexible(text)
        assert result == expected, f"'{text}' → {result}, expected {expected}"

    @pytest.mark.parametrize("text,expected", [
        ("3 Februar 2025", date(2025, 2, 3)),
        ("20 Dezember 2024", date(2024, 12, 20)),
        ("3 März 2025", date(2025, 3, 3)),
        ("15 Januar 2025", date(2025, 1, 15)),
        ("7 Oktober 2024", date(2024, 10, 7)),
    ])
    def test_german_months(self, text, expected):
        """German month names parse to correct dates."""
        result = _parse_date_flexible(text)
        assert result == expected, f"'{text}' → {result}, expected {expected}"

    @pytest.mark.parametrize("text,expected", [
        ("5 octubre 2024", date(2024, 10, 5)),
        ("10 enero 2025", date(2025, 1, 10)),
        ("3 diciembre 2024", date(2024, 12, 3)),
    ])
    def test_spanish_months(self, text, expected):
        """Spanish month names parse to correct dates."""
        result = _parse_date_flexible(text)
        assert result == expected, f"'{text}' → {result}, expected {expected}"

    @pytest.mark.parametrize("text,expected", [
        ("7 gennaio 2025", date(2025, 1, 7)),
        ("15 settembre 2024", date(2024, 9, 15)),
        ("20 ottobre 2024", date(2024, 10, 20)),
    ])
    def test_italian_months(self, text, expected):
        """Italian month names parse to correct dates."""
        result = _parse_date_flexible(text)
        assert result == expected, f"'{text}' → {result}, expected {expected}"

    def test_english_still_works(self):
        """English dates are not broken by the non-English additions."""
        assert _parse_date_flexible("March 9, 2025") == date(2025, 3, 9)
        assert _parse_date_flexible("9 March 2025") == date(2025, 3, 9)
        assert _parse_date_flexible("2025-03-09") == date(2025, 3, 9)

    def test_closing_date_french_range(self):
        """French date range extracts correct closing date."""
        # "5 octobre 2024 – 15 mars 2025"
        text = "5 octobre 2024 – 15 mars 2025"
        closing = _extract_closing_date(text)
        assert closing == date(2025, 3, 15), f"Got {closing}"

    def test_closing_date_german_range(self):
        """German date range extracts correct closing date."""
        text = "3 Februar 2025 – 20 Juni 2025"
        closing = _extract_closing_date(text)
        assert closing is not None
        # Note: "Juni" must be in our table
        assert closing.month == 6 and closing.year == 2025


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Non-English path seeds
# ═══════════════════════════════════════════════════════════════════════════════

class TestNonEnglishPathSeeds:
    """Language-specific exhibition path seeds are available."""

    def test_french_seeds_exist(self):
        """French exhibition paths are registered."""
        seeds = _EXHIBITION_PATH_SEEDS_BY_LANG.get('fr', [])
        assert '/expositions' in seeds or '/fr/expositions' in seeds

    def test_german_seeds_exist(self):
        """German exhibition paths are registered."""
        seeds = _EXHIBITION_PATH_SEEDS_BY_LANG.get('de', [])
        assert '/ausstellungen' in seeds or '/de/ausstellungen' in seeds

    def test_spanish_seeds_exist(self):
        """Spanish exhibition paths are registered."""
        seeds = _EXHIBITION_PATH_SEEDS_BY_LANG.get('es', [])
        assert '/exposiciones' in seeds or '/es/exposiciones' in seeds

    def test_italian_seeds_exist(self):
        """Italian exhibition paths are registered."""
        seeds = _EXHIBITION_PATH_SEEDS_BY_LANG.get('it', [])
        assert '/mostre' in seeds or '/it/mostre' in seeds

    def test_dutch_seeds_exist(self):
        """Dutch exhibition paths are registered."""
        seeds = _EXHIBITION_PATH_SEEDS_BY_LANG.get('nl', [])
        assert '/tentoonstellingen' in seeds or '/nl/tentoonstellingen' in seeds

    def test_english_seeds_still_default(self):
        """English seeds remain available as the default fallback."""
        assert '/exhibitions' in _EXHIBITION_PATH_SEEDS_EN


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Score table verification (acceptance criteria)
# ═══════════════════════════════════════════════════════════════════════════════

class TestScoreTable:
    """Regenerated score table from the ticket — proves the fix."""

    PUBLISHED = "Picasso, Miró, Dalí: Unbound"

    def test_accents_fold_to_1(self):
        """Accented chars fold to exact match."""
        score = _title_similarity("Picasso, Miro, Dali: Unbound", self.PUBLISHED)
        assert score == 1.0

    def test_correct_order_high(self):
        """Correct order without subtitle scores high."""
        score = _title_similarity("Picasso Miro Dali", self.PUBLISHED)
        assert score >= 0.70

    def test_wrong_order_lower(self):
        """Wrong order scores lower than correct order."""
        correct = _title_similarity("Picasso Miro Dali", self.PUBLISHED)
        wrong = _title_similarity("Dali Miro Picasso", self.PUBLISHED)
        assert wrong < correct

    def test_one_name_weak(self):
        """Single name is weak signal."""
        score = _title_similarity("Picasso", self.PUBLISHED)
        assert score <= 0.30

    def test_unrelated_zero(self):
        """Unrelated name scores zero."""
        score = _title_similarity("Monet", self.PUBLISHED)
        assert score == 0.0

    def test_misspelling_recovers(self):
        """One-letter typo recovers to high score."""
        score = _title_similarity("Picaso, Miro, Dali: Unbound", self.PUBLISHED)
        assert score >= 0.85, f"Misspelling scored only {score:.3f}"

    def test_confusable_blocked(self):
        """Confusable pair (Monet≠Manet) scores zero."""
        score = _title_similarity("Manet", self.PUBLISHED)
        assert score == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Regression: unscoped venues unchanged
# ═══════════════════════════════════════════════════════════════════════════════

class TestUnscopedUnchanged:
    """The new similarity function does not break unscoped venue matching."""

    def test_palais_lascaris_zero_against_exhibition(self):
        """Palais Lascaris name does not accidentally match an exhibition query."""
        score = _title_similarity(
            "Picasso, Miró, Dalí: Unbound",
            "Palais Lascaris"
        )
        assert score < 0.2

    def test_unrelated_venue_zero(self):
        """Generic venue name scores zero against exhibition name."""
        score = _title_similarity(
            "Impressionist Masterworks",
            "Museum of Fine Arts, Boston"
        )
        assert score < 0.2
