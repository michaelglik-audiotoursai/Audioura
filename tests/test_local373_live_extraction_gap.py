"""LOCAL-373: Tests for the live extraction gap.

The live page and the fixture must produce the same text through _fetch_page
and _filter_nav_from_page_text. Three root causes fixed:

1. <p[^>]*> regex matched <picture>, <pre>, <path> elements — producing false
   paragraph content (e.g. concatenated title+date from <picture>...<p>Title Date</p>).
   Fix: use <p(?:\\s[^>]*)?>(.+?)</p> which requires <p> or <p + whitespace.

2. Duplicate content from responsive sites (same credit lines, same nav menus
   repeated for mobile/desktop). Fix: deduplicate paragraphs, img_alts, list_items.

3. Footer/nav lines (museum site menus like "Getting Here", "Dining", "Collections")
   not caught by _NAV_LINE_PATTERNS but consuming 44% of the window.
   Fix: detect footer boundary (street address / copyright line) and stop.
"""
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exhibition_checklist import _filter_nav_from_page_text, _fetch_page


def _mock_fetch(html):
    """Helper: call _fetch_page with mocked requests.get returning the given HTML."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html
    with patch('exhibition_checklist.requests.get', return_value=mock_resp):
        text, links = _fetch_page('https://example.com/test')
    return text, links


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 1: <p> regex no longer matches <picture>/<pre>/<path>
# ═══════════════════════════════════════════════════════════════════════════════


class TestParagraphRegexPictureExclusion:
    """<p> extraction must not match <picture>, <pre>, <path> etc.

    All tests drive the real _fetch_page through mocked requests.get.
    The old regex <p[^>]*> matched <picture> (since 'icture' chars are [^>]),
    causing it to span from <picture> to the nearest </p>, concatenating
    everything in between. These tests detect that concatenation.
    """

    def test_picture_tag_not_matched_as_paragraph(self):
        """<picture> followed by a <p> must not concatenate their text content.

        The old regex matched <picture> and spanned to </p>, concatenating
        any text between the two elements into the paragraph content.
        """
        # Text "Exhibition Card Label" sits between </picture> and <p> — old
        # regex would concatenate it with the paragraph text.
        html = (
            '<picture><source srcset="img.jpg"><img alt="test"></picture>'
            'Exhibition Card Label'
            '<p class="info">Picasso, Miró: Unbound — Through Jan 2027</p>'
        )
        text, _ = _mock_fetch(html)

        # The <p> content must be present
        assert "Picasso, Miró: Unbound" in text
        # The text between </picture> and <p> must NOT be concatenated into
        # the paragraph output (old regex would include "Exhibition Card Label")
        assert "Exhibition Card Label" not in text

    def test_picture_does_not_produce_concatenation(self):
        """Listing page: <picture>...<h2>Title</h2><p>TitleDate</p> must not
        produce a paragraph containing the title text twice.

        The old regex spanned from <picture> through <h2> to </p>, producing
        'TitleTitle + Date' after tag stripping. The fix must produce only the
        <p> content.
        """
        html = (
            '<div class="card">'
            '<picture><source srcset="img.jpg"><img src="img.jpg"></picture>'
            '<h2>Picasso, Miró, Dalí: Unbound</h2>'
            '<p class="info">Picasso, Miró, Dalí: UnboundThrough January 24, 2027</p>'
            '</div>'
        )
        text, _ = _mock_fetch(html)

        # Count how many times 'Unbound' appears. The heading produces one
        # instance, and the paragraph produces one instance. The old regex
        # would produce a THIRD instance (concatenated heading+paragraph text
        # in a single paragraph match).
        # With the fix: heading line + paragraph line = 2 occurrences.
        assert text.count("Unbound") == 2, (
            f"Expected 'Unbound' exactly 2 times (heading + paragraph), "
            f"got {text.count('Unbound')}. Text:\n{text}"
        )

    def test_pre_tag_not_matched(self):
        """<pre> should not match as <p> — its content must not appear in output.

        The old regex matched <pre> (since 're' are valid [^>] chars after <p),
        spanning from <pre> to the nearest </p> and concatenating content.
        """
        html = (
            '<pre>code block content that is long enough to be extracted</pre>'
            '<p>Real paragraph content here that is long enough.</p>'
        )
        text, _ = _mock_fetch(html)

        assert "Real paragraph content" in text
        # Old regex would concatenate <pre> content into the paragraph match
        assert "code block" not in text

    def test_path_svg_tag_not_matched(self):
        """<path> in SVG should not contribute content to paragraph extraction.

        Old regex matched <path d="..."> (since 'ath d="..."' are [^>] chars),
        and spanned to the next </p>.
        """
        html = (
            '<svg><path d="M10 10 H 90 V 90 H 10 Z"></path></svg>'
            'SVG label text here'
            '<p>Actual paragraph with real exhibition content here.</p>'
        )
        text, _ = _mock_fetch(html)

        assert "Actual paragraph with real exhibition" in text
        # Old regex would span from <path> to </p>, including "SVG label text"
        assert "SVG label text" not in text


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 2: Deduplication in _fetch_page
# ═══════════════════════════════════════════════════════════════════════════════


class TestFetchPageDeduplication:
    """_fetch_page deduplicates paragraphs, img_alts, and list_items."""

    def test_duplicate_paragraphs_removed(self):
        """Same <p> content appearing twice (e.g. two slides) → only one in output."""
        html = (
            '<p>Joan Miró, Le Lézard aux plumes d\'or (detail), 1971.</p>'
            '<p>Joan Miró, Le Lézard aux plumes d\'or (detail), 1971.</p>'
            '<p>A different paragraph with enough content here.</p>'
        )
        text, _ = _mock_fetch(html)

        # Credit line appears only once
        assert text.count("Le Lézard") == 1
        assert "different paragraph" in text

    def test_duplicate_list_items_removed(self):
        """Responsive nav menus duplicated → only unique items kept."""
        html = (
            '<li>Getting Here</li><li>Dining</li><li>Groups</li>'
            '<li>Getting Here</li><li>Dining</li><li>Groups</li>'
            '<li>Unique Exhibition Item Here</li>'
        )
        text, _ = _mock_fetch(html)

        assert text.count("Getting Here") == 1
        assert text.count("Dining") == 1
        assert "Unique Exhibition Item Here" in text

    def test_duplicate_img_alts_removed(self):
        """Same image alt repeated for responsive srcsets → only one kept."""
        html = (
            '<img alt="Abstract drawing, red and blue, by Miró">'
            '<img alt="Abstract drawing, red and blue, by Miró">'
            '<img alt="Different artwork, oil on canvas, by Dalí">'
        )
        text, _ = _mock_fetch(html)

        assert text.count("Abstract drawing") == 1
        assert "Different artwork" in text


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 3: Footer boundary detection
# ═══════════════════════════════════════════════════════════════════════════════


class TestFooterBoundaryDetection:
    """_filter_nav_from_page_text stops at footer boundary lines."""

    def test_stops_at_street_address(self):
        """Content after a street address line is discarded."""
        # Need > 500 chars of content before the boundary to trigger
        content = (
            "Exhibition Title\n"
            "Bold, experimental works by Spanish artists in this groundbreaking show "
            "that features livres d'artiste from three masters. These extraordinary "
            "works revolutionized the book as an art form at the turn of the century.\n"
            "This exhibition introduces these extraordinary works by Pablo Picasso, "
            "Joan Miró, and Salvador Dalí who were deeply collaborative artists.\n"
            "Lead support is provided by the Jean S. and Frederic A. Sharf Exhibition Fund.\n"
            "Major support is provided by the Lia and William Poorvu Fund and anon.\n"
        )
        text = (
            content
            + "465 Huntington Avenue\n"
            "Boston, Massachusetts 02115\n"
            "Getting Here\n"
            "Dining\n"
            "Groups\n"
            "Current Exhibitions\n"
        )
        result = _filter_nav_from_page_text(text)
        assert "Exhibition Title" in result
        assert "Lead support" in result
        assert "465 Huntington Avenue" not in result
        assert "Getting Here" not in result
        assert "Current Exhibitions" not in result

    def test_stops_at_copyright(self):
        """Content after a © line is discarded."""
        text = (
            "Exhibition content that is substantial enough to read and provides "
            "detailed information about the artworks on display in this show.\n"
            "More exhibition content describing the artworks on display including "
            "paintings, sculptures, and mixed media installations by many artists.\n"
            "Sponsor acknowledgments and credits for the show including multiple "
            "generous donors and foundations that made this exhibition possible.\n"
            "Additional information about the exhibition's history and context "
            "that provides visitors with background on the artistic movement.\n"
            "Final paragraph of content describing closing reception details.\n"
            "© 2026 Museum of Fine Arts Boston\n"
            "Footer navigation items\n"
            "Collections Search\n"
        )
        result = _filter_nav_from_page_text(text)
        assert "Exhibition content" in result
        assert "© 2026" not in result
        assert "Footer navigation" not in result

    def test_no_false_positive_on_early_address(self):
        """Address in first 500 chars should NOT trigger boundary."""
        text = (
            "465 Huntington Avenue is where you'll find this exhibition.\n"
            "The show features works by Picasso, Miró, and Dalí.\n"
        )
        result = _filter_nav_from_page_text(text)
        # Both lines preserved because 500-char guard is not reached
        assert "465 Huntington Avenue" in result
        assert "Picasso" in result

    def test_boundary_only_after_500_chars(self):
        """Footer boundary only triggers after collecting 500+ chars."""
        content = "X" * 501 + "\n"  # Exactly 501 chars of content
        text = content + "100 Main Street\nFooter Items\n"
        result = _filter_nav_from_page_text(text)
        assert "100 Main Street" not in result

    def test_all_rights_reserved_boundary(self):
        """'All Rights Reserved' triggers boundary."""
        text = (
            "Exhibition content with at least five hundred characters of real text. " * 8 + "\n"
            "All Rights Reserved\n"
            "Navigation stuff\n"
        )
        # Verify we have > 500 chars
        assert sum(len(l.strip()) for l in text.split('\n') if l.strip() and l.strip() != "All Rights Reserved" and l.strip() != "Navigation stuff") > 500
        result = _filter_nav_from_page_text(text)
        assert "Exhibition content" in result
        assert "All Rights Reserved" not in result
        assert "Navigation" not in result


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: fixture produces correct text through _fetch_page
# ═══════════════════════════════════════════════════════════════════════════════


class TestFixtureAndLiveAlignment:
    """The MFA fixture must produce correct extraction through the real _fetch_page."""

    def _fetch_fixture(self):
        """Load the MFA fixture HTML and run it through the real _fetch_page."""
        fixture_path = os.path.join(
            os.path.dirname(__file__), 'fixtures', 'mfa_picasso_miro_dali_unbound.html'
        )
        with open(fixture_path, encoding='utf-8') as f:
            html = f.read()
        text, links = _mock_fetch(html)
        return text, links

    def test_fixture_all_three_works_in_window(self):
        """After fixes, all three works must be in the 5000-char window from fixture."""
        text, _ = self._fetch_fixture()
        filtered = _filter_nav_from_page_text(text.strip())
        window = filtered[:5000]

        # All three works must be in the window
        assert "Le Lézard aux plumes d" in window, "Lézard not in window"
        assert "Moses and Monotheism" in window, "Moses not in window"
        assert "Au Soleil du Plafond" in window, "Au Soleil not in window"

    def test_fixture_no_footer_nav_in_window(self):
        """Footer navigation must be stripped from the fixture output."""
        text, _ = self._fetch_fixture()
        filtered = _filter_nav_from_page_text(text.strip())

        # Footer nav items must not appear
        assert "Getting Here" not in filtered
        assert "Current Exhibitions" not in filtered
        assert "Collections Search" not in filtered
        assert "Program Calendar" not in filtered

    def test_fixture_no_duplicate_credit_lines(self):
        """Credit line must appear only once (dedup)."""
        text, _ = self._fetch_fixture()
        # Credit line deduplicated (use partial match to handle apostrophe variants)
        assert text.count("Le Lézard aux plumes d") == 1

    def test_fixture_window_under_5000_chars(self):
        """With dedup + footer removal, filtered text is well under 5000 — no truncation."""
        text, _ = self._fetch_fixture()
        filtered = _filter_nav_from_page_text(text.strip())

        # Must be under 5000 chars — the 5000 truncation is not needed
        assert len(filtered) < 5000, (
            f"Filtered text is {len(filtered)} chars — still too long, "
            f"truncation would still cut content"
        )

    def test_no_concatenated_title_on_listing_page(self):
        """The <p> regex fix eliminates the concatenated title from listing pages.

        Before: <picture>...<h2>Title</h2><p class='info'>TitleDate</p> matched
        from <picture> to </p>, producing 'TitleTitleDate' after tag stripping.
        The fix ensures only real <p> tags match.
        """
        # Simulate the listing page HTML structure that caused the bug
        html = (
            '<div><picture><source srcset="img.jpg"><img></picture></div>'
            '<h2 class="h3"><a href="/exhibition/picasso-miro-dali-unbound">'
            'Picasso, Miró, Dalí: Unbound</a></h2>'
            '<p class="info">Picasso, Miró, Dalí: UnboundThrough January 24, 2027</p>'
        )
        text, _ = _mock_fetch(html)

        # The heading extracts "Picasso, Miró, Dalí: Unbound" (1 occurrence).
        # The paragraph extracts the <p> content (1 occurrence of "Unbound").
        # The old regex would span from <picture> to </p>, capturing the heading
        # text + paragraph text together, creating a THIRD "Unbound".
        assert text.count("Unbound") == 2, (
            f"Expected 'Unbound' exactly 2 times (heading + paragraph), "
            f"got {text.count('Unbound')}. Old regex would produce 3. Text:\n{text}"
        )
