"""tests/test_local366_aic_api_checklist.py — LOCAL-366: Exhibition checklist from venue APIs.

Verifies:
1. AIC API is tried when venue_name matches Art Institute of Chicago
2. AIC API is NOT tried for non-AIC venues
3. Artwork titles and artists are extracted from the live API response shape
4. Exhibition title matching works against API search results
5. Closed exhibitions are correctly detected via aic_end_at
6. The MFA exhibition page (prose-only, no API) correctly falls through to
   the existing HTML scraping path and reports 'prose_only'
7. Integration: generate_tour_text uses the AIC API path end-to-end
"""
import sys
import os
import json
import re
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from exhibition_checklist import (
    _try_aic_api,
    _title_similarity,
    find_exhibition_checklist,
    ExhibitionChecklistResult,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────
FIXTURES_DIR = Path(__file__).parent / 'fixtures'


def _load_fixture(name: str):
    """Load a JSON fixture file."""
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


def _load_html_fixture(name: str) -> str:
    """Load an HTML fixture file."""
    with open(FIXTURES_DIR / name) as f:
        return f.read()


# ═══════════════════════════════════════════════════════════════════════════════
# Route 1: AIC API integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestAICAPIDetection:
    """_try_aic_api fires only for Art Institute of Chicago."""

    def test_aic_detected_by_full_name(self):
        """Venue name 'Art Institute of Chicago' triggers AIC API path."""
        # Mock the network calls to use fixture data
        fixture_exh = _load_fixture('aic_exhibition_10694.json')
        fixture_art = _load_fixture('aic_artworks_10694.json')

        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if 'exhibitions/search' in url:
                resp.json.return_value = {'data': [fixture_exh['data']]}
            elif '/artworks?' in url:
                # Return the artworks for whatever IDs are requested
                resp.json.return_value = fixture_art
            else:
                resp.status_code = 404
                resp.json.return_value = {}
            return resp

        with patch('exhibition_checklist.requests.get', side_effect=mock_get):
            result = _try_aic_api(
                exhibition_name="Beyond Form: Abstraction at Midcentury",
                venue_name="Art Institute of Chicago",
            )

        assert result is not None
        assert result.path == 'checklist'
        assert result.page_shape == 'api_structured'
        assert len(result.works) > 0
        assert result.exhibition_title == "Beyond Form: Abstraction at Midcentury"

    def test_aic_detected_by_partial_name(self):
        """'Art Institute, Chicago' also triggers AIC API path."""
        with patch('exhibition_checklist.requests.get') as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {'data': []}
            mock_get.return_value = mock_resp
            result = _try_aic_api("Some Exhibition", "Art Institute, Chicago")
        # Returns None because no exhibitions match, but it DID try the API
        assert result is None
        mock_get.assert_called()  # API was called

    def test_non_aic_venue_skipped(self):
        """Non-AIC venues return None immediately without network calls."""
        with patch('exhibition_checklist.requests.get') as mock_get:
            result = _try_aic_api("Some Exhibition", "Museum of Fine Arts, Boston")
        assert result is None
        mock_get.assert_not_called()

    def test_non_aic_venue_mfa(self):
        """MFA Boston does NOT trigger AIC path."""
        with patch('exhibition_checklist.requests.get') as mock_get:
            result = _try_aic_api(
                "Picasso, Miró, Dalí: Unbound",
                "Museum of Fine Arts, Boston"
            )
        assert result is None
        mock_get.assert_not_called()

    def test_non_aic_venue_tate(self):
        """Tate Modern does NOT trigger AIC path."""
        with patch('exhibition_checklist.requests.get') as mock_get:
            result = _try_aic_api("Whistler", "Tate Modern, London")
        assert result is None
        mock_get.assert_not_called()


class TestAICAPIArtworkExtraction:
    """Artworks are correctly extracted from real AIC API response shape."""

    def test_artwork_titles_extracted(self):
        """All 71 artworks from fixture are extracted with titles."""
        fixture_exh = _load_fixture('aic_exhibition_10694.json')
        fixture_art = _load_fixture('aic_artworks_10694.json')
        all_art_data = fixture_art['data']

        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if 'exhibitions/search' in url:
                resp.json.return_value = {'data': [fixture_exh['data']]}
            elif '/artworks?' in url:
                # Parse requested IDs from URL and return matching subset
                import urllib.parse
                parsed = urllib.parse.urlparse(url)
                params = urllib.parse.parse_qs(parsed.query)
                requested_ids = [int(x) for x in params.get('ids', [''])[0].split(',') if x]
                matching = [a for a in all_art_data if a['id'] in requested_ids]
                resp.json.return_value = {'data': matching}
            return resp

        with patch('exhibition_checklist.requests.get', side_effect=mock_get):
            result = _try_aic_api(
                "Beyond Form: Abstraction at Midcentury",
                "Art Institute of Chicago",
            )

        assert result is not None
        assert len(result.works) == 71
        # Verify specific known works from the fixture
        titles = [w['title'] for w in result.works]
        assert 'Hyderabad' in titles
        assert 'Chicago' in titles  # Franz Kline
        assert 'Fire Painting' in titles  # Otto Piene

    def test_artist_names_included(self):
        """Artist names are included when available from artworks endpoint."""
        fixture_exh = _load_fixture('aic_exhibition_10694.json')
        fixture_art = _load_fixture('aic_artworks_10694.json')
        all_art_data = fixture_art['data']

        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if 'exhibitions/search' in url:
                resp.json.return_value = {'data': [fixture_exh['data']]}
            elif '/artworks?' in url:
                import urllib.parse
                parsed = urllib.parse.urlparse(url)
                params = urllib.parse.parse_qs(parsed.query)
                requested_ids = [int(x) for x in params.get('ids', [''])[0].split(',') if x]
                matching = [a for a in all_art_data if a['id'] in requested_ids]
                resp.json.return_value = {'data': matching}
            return resp

        with patch('exhibition_checklist.requests.get', side_effect=mock_get):
            result = _try_aic_api(
                "Beyond Form: Abstraction at Midcentury",
                "Art Institute of Chicago",
            )

        # Find specific works and check artists
        artists_by_title = {w['title']: w.get('artist', '') for w in result.works}
        # Note: there may be multiple 'Untitled' — check for known unique works
        kline_work = next((w for w in result.works if w['title'] == 'Chicago'), None)
        assert kline_work is not None
        assert kline_work['artist'] == 'Franz Kline'

        pollock_work = next((w for w in result.works
                            if w.get('artist') == 'Jackson Pollock'), None)
        assert pollock_work is not None


class TestAICAPIClosedExhibition:
    """Closed exhibitions are detected and refused."""

    def test_closed_exhibition_detected(self):
        """Exhibition with aic_end_at in the past is marked closed."""
        past_date = (date.today() - timedelta(days=30)).isoformat() + "T00:00:00-05:00"
        mock_exh = {
            'id': 99999,
            'title': 'Test Closed Exhibition',
            'status': 'Closed',
            'artwork_ids': [1, 2, 3],
            'artwork_titles': ['A', 'B', 'C'],
            'aic_start_at': '2024-01-01T00:00:00-05:00',
            'aic_end_at': past_date,
            'web_url': 'https://www.artic.edu/exhibitions/99999/test',
        }

        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if 'exhibitions/search' in url:
                resp.json.return_value = {'data': [mock_exh]}
            return resp

        with patch('exhibition_checklist.requests.get', side_effect=mock_get):
            result = _try_aic_api("Test Closed Exhibition", "Art Institute of Chicago")

        assert result is not None
        assert result.is_closed is True
        assert result.path == 'closed'
        assert 'closed' in result.reason.lower()


class TestAICAPITitleMatching:
    """Fuzzy title matching works for API search results."""

    def test_exact_match_found(self):
        """Exact title match gets high score."""
        fixture_exh = _load_fixture('aic_exhibition_10694.json')
        fixture_art = _load_fixture('aic_artworks_10694.json')

        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if 'exhibitions/search' in url:
                resp.json.return_value = {'data': [fixture_exh['data']]}
            elif '/artworks?' in url:
                resp.json.return_value = fixture_art
            return resp

        with patch('exhibition_checklist.requests.get', side_effect=mock_get):
            result = _try_aic_api(
                "Beyond Form: Abstraction at Midcentury",
                "Art Institute of Chicago",
            )
        assert result is not None
        assert result.path == 'checklist'

    def test_partial_match_works(self):
        """Partial title still matches (user might say 'Abstraction at Midcentury')."""
        fixture_exh = _load_fixture('aic_exhibition_10694.json')
        fixture_art = _load_fixture('aic_artworks_10694.json')

        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if 'exhibitions/search' in url:
                resp.json.return_value = {'data': [fixture_exh['data']]}
            elif '/artworks?' in url:
                resp.json.return_value = fixture_art
            return resp

        with patch('exhibition_checklist.requests.get', side_effect=mock_get):
            result = _try_aic_api(
                "Abstraction at Midcentury",
                "Art Institute of Chicago",
            )
        assert result is not None
        assert result.path == 'checklist'

    def test_low_score_rejected(self):
        """Completely unrelated title does not match."""
        mock_exh = {
            'id': 1,
            'title': 'Impressionist Landscapes of France',
            'status': 'Confirmed',
            'artwork_ids': [1, 2, 3],
            'artwork_titles': ['A', 'B', 'C'],
            'aic_start_at': '2026-01-01T00:00:00-05:00',
            'aic_end_at': '2027-01-01T00:00:00-05:00',
            'web_url': 'https://artic.edu/exhibitions/1',
        }

        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if 'exhibitions/search' in url:
                resp.json.return_value = {'data': [mock_exh]}
            return resp

        with patch('exhibition_checklist.requests.get', side_effect=mock_get):
            result = _try_aic_api(
                "Japanese Ceramics of the Edo Period",
                "Art Institute of Chicago",
            )
        # Should return None because no match above threshold
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# Route 1 (MFA): Drupal settings blob yields no artwork data
# ═══════════════════════════════════════════════════════════════════════════════

class TestMFAExhibitionPage:
    """The MFA exhibition page is prose-only — no extractable works."""

    def test_mfa_page_has_no_collection_links(self):
        """MFA exhibition page contains zero /collections/object links."""
        html = _load_html_fixture('mfa_picasso_exhibition.html')
        assert '/collections/object' not in html

    def test_mfa_page_has_no_json_ld(self):
        """MFA exhibition page contains no JSON-LD structured data."""
        html = _load_html_fixture('mfa_picasso_exhibition.html')
        assert 'application/ld+json' not in html

    def test_mfa_drupal_settings_has_no_artwork_data(self):
        """The drupal-settings-json blob contains views/banner only, no artwork references."""
        html = _load_html_fixture('mfa_picasso_exhibition.html')
        m = re.search(r'data-drupal-selector="drupal-settings-json"[^>]*>(.*?)</script', html, re.DOTALL)
        assert m is not None, "drupal-settings-json should exist"
        settings = json.loads(m.group(1))
        # The views section only has banner, no collections or artworks
        views = settings.get('views', {})
        ajax_views = views.get('ajaxViews', {})
        for key, view_config in ajax_views.items():
            assert view_config.get('view_name') == 'banner', (
                f"Expected only 'banner' view, found '{view_config.get('view_name')}'"
            )

    def test_mfa_page_is_prose_only_to_our_extractor(self):
        """Our work extractor correctly returns empty for MFA's JS-rendered page."""
        from exhibition_checklist import extract_works_from_exhibition_page, _fetch_page
        html = _load_html_fixture('mfa_picasso_exhibition.html')

        # Simulate what _fetch_page returns: extracted text + links
        links = []
        for m in re.finditer(r'<a\s+[^>]*href=["\']([^"\']{1,300})["\'][^>]*>(.*?)</a>', html, re.DOTALL):
            href = m.group(1)
            link_text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if link_text and len(link_text) < 200:
                links.append((link_text, href))

        # Extract text (headings + paragraphs)
        headings = []
        for h_match in re.finditer(r'<h[1-4][^>]*>(.*?)</h[1-4]>', html, re.DOTALL):
            clean = re.sub(r'<[^>]+>', '', h_match.group(1)).strip()
            if clean and len(clean) < 200:
                headings.append(clean)

        paragraphs = []
        for p_match in re.finditer(r'<p[^>]*>(.*?)</p>', html, re.DOTALL):
            clean = re.sub(r'<[^>]+>', '', p_match.group(1)).strip()
            clean = re.sub(r'&nbsp;', ' ', clean)
            if len(clean) > 20:
                paragraphs.append(clean)

        text = '\n'.join(headings + paragraphs)
        works = extract_works_from_exhibition_page(text, links)

        # The MFA page should yield very few or zero usable works
        # (may pick up the credit line "Joan Miró, Le Lézard..." but that's 1 work max)
        assert len(works) <= 2, (
            f"Expected ≤2 works from prose-only MFA page, got {len(works)}: "
            f"{[w['title'] for w in works]}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: find_exhibition_checklist routes to AIC API
# ═══════════════════════════════════════════════════════════════════════════════

class TestFindExhibitionChecklistIntegration:
    """find_exhibition_checklist correctly routes to AIC API when appropriate."""

    def test_aic_venue_uses_api_path(self):
        """When venue is AIC, the API path is used and HTML scraping is skipped."""
        fixture_exh = _load_fixture('aic_exhibition_10694.json')
        fixture_art = _load_fixture('aic_artworks_10694.json')
        all_art_data = fixture_art['data']

        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if 'exhibitions/search' in url or 'api.artic.edu' in url:
                if 'exhibitions/search' in url:
                    resp.json.return_value = {'data': [fixture_exh['data']]}
                elif '/artworks?' in url:
                    import urllib.parse
                    parsed = urllib.parse.urlparse(url)
                    params = urllib.parse.parse_qs(parsed.query)
                    requested_ids = [int(x) for x in params.get('ids', [''])[0].split(',') if x]
                    matching = [a for a in all_art_data if a['id'] in requested_ids]
                    resp.json.return_value = {'data': matching}
                else:
                    resp.status_code = 404
                    resp.json.return_value = {}
            else:
                # If we reach here, it means HTML scraping is happening — should NOT for AIC
                resp.status_code = 200
                resp.text = '<html><body>Should not fetch this</body></html>'
                resp.json.return_value = {}
            return resp

        with patch('exhibition_checklist.requests.get', side_effect=mock_get):
            result = find_exhibition_checklist(
                venue_base_url="https://www.artic.edu",
                exhibition_name="Beyond Form: Abstraction at Midcentury",
                venue_name="Art Institute of Chicago",
            )

        assert result.path == 'checklist'
        assert result.page_shape == 'api_structured'
        assert len(result.works) == 71

    def test_non_aic_venue_falls_through_to_html_scraping(self):
        """Non-AIC venue skips API and proceeds to HTML scraping path."""
        # Mock all network to return empty — we just verify it doesn't use AIC API
        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = '<html><body><h1>No exhibitions</h1></body></html>'
            resp.json.return_value = {}
            return resp

        with patch('exhibition_checklist.requests.get', side_effect=mock_get):
            result = find_exhibition_checklist(
                venue_base_url="https://www.mfa.org",
                exhibition_name="Picasso, Miró, Dalí: Unbound",
                venue_name="Museum of Fine Arts, Boston",
            )

        # Should NOT be api_structured — falls through to HTML path
        assert result.page_shape != 'api_structured'
        # Should be fallback since the mocked HTML has no exhibitions
        assert result.path == 'fallback'


# ═══════════════════════════════════════════════════════════════════════════════
# Existing behaviour unchanged: unscoped museums
# ═══════════════════════════════════════════════════════════════════════════════

class TestUnscopedUnchanged:
    """Unscoped venue tours (no exhibition name) are not affected."""

    def test_exhibition_scope_none_for_plain_museum(self):
        """A plain museum request (no exhibition name) should not trigger the
        exhibition checklist path at all — the _exhibition_scope remains None.
        
        Validates by checking that _try_aic_api returns None for a plain venue
        name with no exhibition query (empty string)."""
        with patch('exhibition_checklist.requests.get') as mock_get:
            result = _try_aic_api("", "Museum of Fine Arts, Boston")
        assert result is None
        mock_get.assert_not_called()

    def test_aic_no_exhibition_name_still_searches(self):
        """Even for AIC, an empty exhibition name should gracefully handle."""
        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {'data': []}
            return resp

        with patch('exhibition_checklist.requests.get', side_effect=mock_get):
            result = _try_aic_api("", "Art Institute of Chicago")
        # Empty search returns no matches → None
        assert result is None
