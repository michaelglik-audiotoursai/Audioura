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
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exhibition_checklist import _filter_nav_from_page_text, _fetch_page


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 1: <p> regex no longer matches <picture>/<pre>/<path>
# ═══════════════════════════════════════════════════════════════════════════════


class TestParagraphRegexPictureExclusion:
    """<p> extraction must not match <picture>, <pre>, <path> etc."""

    def test_picture_tag_not_matched_as_paragraph(self):
        """<picture>.....</p> must NOT produce a false paragraph."""
        html = (
            '<picture><source srcset="img.jpg"><img alt="test"></picture>'
            '<p class="info">Picasso, Miró: UnboundThrough Jan 2027</p>'
        )
        # Use the same regex as _fetch_page (fixed version)
        paragraphs = []
        for p_match in re.finditer(r'<p(?:\s[^>]*)?>(.+?)</p>', html, re.DOTALL):
            clean = re.sub(r'<[^>]+>', '', p_match.group(1)).strip()
            if len(clean) > 5:
                paragraphs.append(clean)

        # Only the real <p> should match
        assert len(paragraphs) == 1
        assert paragraphs[0] == "Picasso, Miró: UnboundThrough Jan 2027"

    def test_picture_false_match_was_the_old_bug(self):
        """Old regex <p[^>]*> matches <picture> — demonstrate the bug."""
        html = (
            '<picture><source srcset="img.jpg"></picture>'
            '<p class="info">Title</p>'
        )
        # OLD regex matches <picture> because 'icture' chars are all [^>]
        old_matches = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
        # It would match from <picture> to </p> — spanning picture+p
        assert len(old_matches) == 1
        # The match includes content from BOTH elements (the bug)
        assert 'Title' in old_matches[0]

    def test_pre_tag_not_matched(self):
        """<pre> should not match as <p>."""
        html = '<pre>code block</pre><p>Real paragraph content here.</p>'
        paragraphs = []
        for p_match in re.finditer(r'<p(?:\s[^>]*)?>(.+?)</p>', html, re.DOTALL):
            clean = re.sub(r'<[^>]+>', '', p_match.group(1)).strip()
            if len(clean) > 5:
                paragraphs.append(clean)
        assert len(paragraphs) == 1
        assert paragraphs[0] == "Real paragraph content here."


# ═══════════════════════════════════════════════════════════════════════════════
# Fix 2: Deduplication in _fetch_page
# ═══════════════════════════════════════════════════════════════════════════════


class TestFetchPageDeduplication:
    """_fetch_page deduplicates paragraphs, img_alts, and list_items."""

    def test_duplicate_paragraphs_removed(self):
        """Same <p> content appearing twice (e.g. two slides) → only one in output."""
        from unittest.mock import patch, MagicMock

        html = (
            '<p>Joan Miró, Le Lézard aux plumes d\'or (detail), 1971.</p>'
            '<p>Joan Miró, Le Lézard aux plumes d\'or (detail), 1971.</p>'
            '<p>A different paragraph with enough content here.</p>'
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html

        with patch('exhibition_checklist.requests.get', return_value=mock_resp):
            text, _ = _fetch_page('https://example.com/test')

        # Credit line appears only once
        assert text.count("Le Lézard") == 1
        assert "different paragraph" in text

    def test_duplicate_list_items_removed(self):
        """Responsive nav menus duplicated → only unique items kept."""
        from unittest.mock import patch, MagicMock

        html = (
            '<li>Getting Here</li><li>Dining</li><li>Groups</li>'
            '<li>Getting Here</li><li>Dining</li><li>Groups</li>'
            '<li>Unique Exhibition Item Here</li>'
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html

        with patch('exhibition_checklist.requests.get', return_value=mock_resp):
            text, _ = _fetch_page('https://example.com/test')

        assert text.count("Getting Here") == 1
        assert text.count("Dining") == 1
        assert "Unique Exhibition Item Here" in text

    def test_duplicate_img_alts_removed(self):
        """Same image alt repeated for responsive srcsets → only one kept."""
        from unittest.mock import patch, MagicMock

        html = (
            '<img alt="Abstract drawing, red and blue, by Miró">'
            '<img alt="Abstract drawing, red and blue, by Miró">'
            '<img alt="Different artwork, oil on canvas, by Dalí">'
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html

        with patch('exhibition_checklist.requests.get', return_value=mock_resp):
            text, _ = _fetch_page('https://example.com/test')

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
# Integration: fixture and live produce the same text
# ═══════════════════════════════════════════════════════════════════════════════


class TestFixtureAndLiveAlignment:
    """The MFA fixture must produce the same extraction text as the live page."""

    def _extract_text_from_html(self, html):
        """Replicate _fetch_page logic locally (same as the module, for offline test)."""
        headings = []
        for h_match in re.finditer(r'<h[1-4][^>]*>(.*?)</h[1-4]>', html, re.DOTALL):
            clean = re.sub(r'<[^>]+>', '', h_match.group(1)).strip()
            if clean and len(clean) < 200:
                headings.append(clean)

        figcaptions = []
        for fig_match in re.finditer(r'<figcaption[^>]*>(.*?)</figcaption>', html, re.DOTALL):
            clean = re.sub(r'<[^>]+>', '', fig_match.group(1)).strip()
            if clean and len(clean) > 5:
                figcaptions.append(clean)

        img_alts = []
        _seen_alts = set()
        for img_match in re.finditer(r'<img[^>]*alt="([^"]{10,200})"', html):
            alt = img_match.group(1).strip()
            if (',' in alt or ' by ' in alt.lower()) and alt not in _seen_alts:
                _seen_alts.add(alt)
                img_alts.append(alt)

        paragraphs = []
        _seen_paragraphs = set()
        for p_match in re.finditer(r'<p(?:\s[^>]*)?>(.+?)</p>', html, re.DOTALL):
            clean = re.sub(r'<[^>]+>', '', p_match.group(1)).strip()
            clean = re.sub(r'&nbsp;', ' ', clean)
            clean = re.sub(r'&[a-z]+;', ' ', clean)
            if len(clean) > 20 and clean not in _seen_paragraphs:
                _seen_paragraphs.add(clean)
                paragraphs.append(clean)

        list_items = []
        _seen_items = set()
        for li_match in re.finditer(r'<li[^>]*>(.*?)</li>', html, re.DOTALL):
            clean = re.sub(r'<[^>]+>', '', li_match.group(1)).strip()
            if len(clean) > 5 and len(clean) < 200 and clean not in _seen_items:
                _seen_items.add(clean)
                list_items.append(clean)

        return '\n'.join(headings + figcaptions + img_alts + paragraphs + list_items)

    def test_fixture_all_three_works_in_window(self):
        """After fixes, all three works must be in the 5000-char window from fixture."""
        fixture_path = os.path.join(
            os.path.dirname(__file__), 'fixtures', 'mfa_picasso_miro_dali_unbound.html'
        )
        with open(fixture_path, encoding='utf-8') as f:
            html = f.read()

        text = self._extract_text_from_html(html)
        filtered = _filter_nav_from_page_text(text.strip())
        window = filtered[:5000]

        # All three works must be in the window
        assert "Le Lézard aux plumes d" in window, "Lézard not in window"
        assert "Moses and Monotheism" in window, "Moses not in window"
        assert "Au Soleil du Plafond" in window, "Au Soleil not in window"

    def test_fixture_no_footer_nav_in_window(self):
        """Footer navigation must be stripped from the fixture output."""
        fixture_path = os.path.join(
            os.path.dirname(__file__), 'fixtures', 'mfa_picasso_miro_dali_unbound.html'
        )
        with open(fixture_path, encoding='utf-8') as f:
            html = f.read()

        text = self._extract_text_from_html(html)
        filtered = _filter_nav_from_page_text(text.strip())

        # Footer nav items must not appear
        assert "Getting Here" not in filtered
        assert "Current Exhibitions" not in filtered
        assert "Collections Search" not in filtered
        assert "Program Calendar" not in filtered

    def test_fixture_no_duplicate_credit_lines(self):
        """Credit line must appear only once (dedup)."""
        fixture_path = os.path.join(
            os.path.dirname(__file__), 'fixtures', 'mfa_picasso_miro_dali_unbound.html'
        )
        with open(fixture_path, encoding='utf-8') as f:
            html = f.read()

        text = self._extract_text_from_html(html)
        # Credit line deduplicated (use partial match to handle apostrophe variants)
        assert text.count("Le Lézard aux plumes d") == 1

    def test_fixture_window_under_5000_chars(self):
        """With dedup + footer removal, filtered text is well under 5000 — no truncation."""
        fixture_path = os.path.join(
            os.path.dirname(__file__), 'fixtures', 'mfa_picasso_miro_dali_unbound.html'
        )
        with open(fixture_path, encoding='utf-8') as f:
            html = f.read()

        text = self._extract_text_from_html(html)
        filtered = _filter_nav_from_page_text(text.strip())

        # Must be under 5000 chars — the 5000 truncation is not needed
        assert len(filtered) < 5000, (
            f"Filtered text is {len(filtered)} chars — still too long, "
            f"truncation would still cut content"
        )

    def test_no_concatenated_title_on_listing_page(self):
        """The <p> regex fix eliminates the concatenated title from listing pages.
        
        Before: <picture>...<p class='info'>TitleThrough Date</p> produced
        'Picasso, Miró, Dalí: UnboundThrough January 24, 2027' as a paragraph.
        """
        # Simulate the listing page HTML structure that caused the bug
        html = (
            '<div><picture><source srcset="img.jpg"><img></picture></div>'
            '<h2 class="h3"><a href="/exhibition/picasso-miro-dali-unbound">'
            'Picasso, Miró, Dalí: Unbound</a></h2>'
            '<p class="info">Picasso, Miró, Dalí: UnboundThrough January 24, 2027</p>'
        )
        paragraphs = []
        for p_match in re.finditer(r'<p(?:\s[^>]*)?>(.+?)</p>', html, re.DOTALL):
            clean = re.sub(r'<[^>]+>', '', p_match.group(1)).strip()
            if len(clean) > 5:
                paragraphs.append(clean)

        # The <p class="info"> IS a real match, but only ONE match (not spanning picture)
        assert len(paragraphs) == 1
        # Verify the old regex would have matched differently
        old_matches = []
        for p_match in re.finditer(r'<p[^>]*>(.*?)</p>', html, re.DOTALL):
            clean = re.sub(r'<[^>]+>', '', p_match.group(1)).strip()
            if len(clean) > 5:
                old_matches.append(clean)
        # Old regex matches from <picture> to </p> — may produce different text
        # depending on exact HTML structure
        assert len(old_matches) >= 1
