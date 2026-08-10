"""LOCAL-372: Tests for theme-word filter word-boundary matching and book-scope exemption.

Tests the module-scope functions:
- theme_word_match: word-boundary check (not substring)
- _is_book_exhibition_scope: detects book/print exhibitions
- _filter_nav_from_page_text: removes navigation lines from page text
"""
import pytest
import sys
import os

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestThemeWordMatch:
    """theme_word_match uses word boundaries, not substring containment."""

    def setup_method(self):
        from generate_tour_text import theme_word_match
        self.match = theme_word_match

    def test_exact_word_matches(self):
        """A theme word that IS a standalone word in the title should match."""
        assert self.match("the golden age of dutch painting", {"golden"}) == "golden"

    def test_substring_does_not_match(self):
        """'or' must NOT match inside \"d'or\" — this is the LOCAL-372 fix."""
        # This was the actual failure: 'or' matching inside "Le Lézard aux plumes d'or"
        result = self.match(
            "le lézard aux plumes d'or (the lizard with golden feathers)",
            {"or"}
        )
        assert result == "", f"Expected no match but got '{result}'"

    def test_book_word_inside_title_no_match(self):
        """'book' inside 'facebook' should not match."""
        assert self.match("the facebook era", {"book"}) == ""

    def test_book_word_as_standalone(self):
        """'book' as standalone word should match."""
        assert self.match("the artist's book collection", {"book"}) == "book"

    def test_theme_word_at_start(self):
        """Theme word at the start of the title."""
        assert self.match("golden feathers of spring", {"golden"}) == "golden"

    def test_theme_word_at_end(self):
        """Theme word at the end of the title."""
        assert self.match("the dawn of gold", {"gold"}) == "gold"

    def test_no_theme_words_returns_empty(self):
        """Empty theme_words set → no match."""
        assert self.match("anything here", set()) == ""

    def test_multiple_theme_words_returns_first_match(self):
        """When multiple match, returns one of them."""
        result = self.match("blue feathers and gold wings", {"feathers", "gold"})
        assert result in ("feathers", "gold")

    def test_short_word_no_false_positive(self):
        """Short theme words like 'art' should not match inside 'artist'."""
        assert self.match("the great artist", {"art"}) == ""

    def test_short_word_standalone_match(self):
        """Short theme word 'art' should match when standalone."""
        assert self.match("the art of war", {"art"}) == "art"


class TestIsBookExhibitionScope:
    """_is_book_exhibition_scope detects book/print/illustration exhibitions."""

    def setup_method(self):
        from generate_tour_text import _is_book_exhibition_scope
        self.is_book = _is_book_exhibition_scope

    def test_none_scope_returns_false(self):
        assert self.is_book(None) is False

    def test_empty_dict_returns_false(self):
        assert self.is_book({}) is False

    def test_unbound_exhibition(self):
        """The actual MFA exhibition 'Picasso, Miró, Dalí: Unbound' should trigger."""
        scope = {'requirements': 'Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA'}
        assert self.is_book(scope) is True

    def test_book_keyword(self):
        scope = {'requirements': 'Artists Books at the Library'}
        assert self.is_book(scope) is True

    def test_livre_keyword(self):
        scope = {'requirements': "Livres d'artiste exhibition"}
        assert self.is_book(scope) is True

    def test_prints_keyword(self):
        scope = {'requirements': 'Japanese Woodblock Prints'}
        assert self.is_book(scope) is True

    def test_lithograph_keyword(self):
        scope = {'requirements': 'Modern Lithographs from Paris'}
        assert self.is_book(scope) is True

    def test_normal_exhibition_no_match(self):
        """A normal painting exhibition should NOT trigger."""
        scope = {'requirements': 'Impressionism and the Sea at the National Gallery'}
        assert self.is_book(scope) is False

    def test_sculpture_exhibition_no_match(self):
        scope = {'requirements': 'Rodin: Sculptor of Modernity'}
        assert self.is_book(scope) is False


class TestFilterNavFromPageText:
    """_filter_nav_from_page_text removes navigation garbage from page text."""

    def setup_method(self):
        from exhibition_checklist import _filter_nav_from_page_text
        self.filter = _filter_nav_from_page_text

    def test_removes_login_lines(self):
        text = "Exhibition Title\nLog In\nSome artwork description here that is long enough."
        result = self.filter(text)
        assert "Log In" not in result
        assert "Exhibition Title" in result
        assert "Some artwork description" in result

    def test_removes_view_cart(self):
        text = "Picasso\nView Cart\nGet Tickets\nJoin Today\nArtwork info here."
        result = self.filter(text)
        assert "View Cart" not in result
        assert "Get Tickets" not in result
        assert "Join Today" not in result
        assert "Picasso" in result

    def test_removes_account_management(self):
        text = "Title\nEdit Account\nManage Interests\nManage Memberships\nContent here."
        result = self.filter(text)
        assert "Edit Account" not in result
        assert "Manage Interests" not in result

    def test_preserves_exhibition_content(self):
        """Long lines with exhibition content should be preserved."""
        content = (
            "Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) "
            "(detail), published by Louis Broder, printed by Mourlot Frères, Paris, 1971."
        )
        text = f"Main navigation\n{content}\nFooter"
        result = self.filter(text)
        assert "Joan Miró" in result
        # Nav lines removed
        assert "Main navigation" not in result
        assert "Footer" not in result

    def test_removes_footer_and_nav_labels(self):
        text = "Content\nFooter\nMain navigation\nConnect with Us\nVisit Us"
        result = self.filter(text)
        assert "Footer" not in result
        assert "Main navigation" not in result
        assert "Connect with Us" not in result

    def test_fixture_nav_removal(self):
        """Simulate the fixture scenario: nav list items push content past truncation."""
        # Build text similar to fixture: content at top, nav garbage at bottom
        content_lines = [
            "Picasso, Miró, Dalí: Unbound",
            "Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), "
            "published by Louis Broder, printed by Mourlot Frères, Paris, 1971.",
            "Bold, experimental, extravagant, and unbound.",
        ]
        nav_lines = [
            "Log In", "View Cart", "Get Tickets", "Join Today",
            "Edit Account", "Manage Interests", "Manage Memberships",
            "Upcoming Events", "Video Content", "Log Out",
            "Main navigation", "Footer", "Connect with Us", "Visit Us",
            "Sign up for MFA Mail", "Corporate Membership",
            "Gifts of Art", "Gifts of Securities", "Donor-Advised Funds",
        ]
        text = '\n'.join(content_lines + nav_lines)
        result = self.filter(text)
        # All nav removed
        for nav in nav_lines:
            assert nav not in result, f"Nav line '{nav}' was not filtered"
        # Content preserved
        assert "Picasso" in result
        assert "Joan Miró" in result


# ═══════════════════════════════════════════════════════════════════════════════
# LEAD review (2026-08-10) — the D1v2 bypass must not mean "no grounding".
#
# Skipping D1v2 for exhibition stops is correct: it verifies against the venue's
# PERMANENT collection, which a temporary show is not in — that is what deleted
# 'Le Lézard aux plumes d'or'. But as submitted, exhibition stops had NO check at
# all, so a title invented by the extraction LLM would ship unchallenged in the
# one path whose premise is that the venue's page is authoritative.
#
# Grounding now runs against that page instead.
# ═══════════════════════════════════════════════════════════════════════════════

import re as _re
import html as _html
from pathlib import Path as _Path


def _mfa_page_text():
    p = _Path(__file__).parent / 'fixtures' / 'mfa_picasso_miro_dali_unbound.html'
    raw = p.read_text(encoding='utf-8', errors='replace')
    raw = _re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', raw)
    return _html.unescape(_re.sub(r'(?s)<[^>]+>', ' ', raw))


class TestExhibitionStopsAreGroundedInThePage:

    @pytest.mark.parametrize("title", [
        "Le Lézard aux plumes d'or (The Lizard with Golden Feathers)",
        "Moses and Monotheism",
        "Au Soleil du Plafond",
    ])
    def test_real_works_from_the_page_pass(self, title):
        from generate_tour_text import title_appears_in_page
        assert title_appears_in_page(title, _mfa_page_text()) is True

    @pytest.mark.parametrize("title", [
        "Guernica",
        "The Persistence of Memory",
        "Les Demoiselles d'Avignon",
        "Woman with a Flower Hat",
    ])
    def test_invented_works_by_the_same_artists_are_rejected(self, title):
        """
        The dangerous case: famous works by Picasso, Miró and Dalí that are NOT in
        this show. An LLM completing from memory would produce exactly these.
        """
        from generate_tour_text import title_appears_in_page
        assert title_appears_in_page(title, _mfa_page_text()) is False

    def test_accent_and_punctuation_reformatting_tolerated(self):
        """The extractor may normalise the title; that must not fail grounding."""
        from generate_tour_text import title_appears_in_page
        page = _mfa_page_text()
        assert title_appears_in_page("Le Lezard aux plumes d or", page) is True

    def test_empty_inputs_are_not_grounded(self):
        from generate_tour_text import title_appears_in_page
        assert title_appears_in_page('', 'anything') is False
        assert title_appears_in_page('Something', '') is False
