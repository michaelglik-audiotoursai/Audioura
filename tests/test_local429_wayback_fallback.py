"""LOCAL-429: Wayback Machine fallback for Cloudflare-challenged pages.

Tests that _fetch_page detects Cloudflare managed challenge (cf-mitigated: challenge)
and falls through to _fetch_from_wayback instead of wasting the 30s retry budget.

Tests the production symbol `_fetch_from_wayback` directly and the integration via
`_fetch_page`.
"""
import sys
import os
import re
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import exhibition_checklist as ec


# Sample HTML that looks like what the Wayback Machine returns for mfa.org
_WAYBACK_HTML = """
<html>
<head><title>Picasso, Miró, Dalí: Unbound</title></head>
<body>
<h1>Picasso, Miró, Dalí: Unbound</h1>
<p>Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail),
published by Louis Broder, printed by Mourlot Frères, Paris, 1971. Illustrated book
with 40 color lithographs (including wrapper front and cover); publisher's vellum.
Gift of Boris Fridman. © Successió Miró / Artists Rights Society (ARS), New York /
ADAGP, Paris 2026.</p>
<p>Bold, experimental, extravagant, and unbound, both literally and in the creative
minds that produced them, livres d'artiste had no precedent.</p>
<a href="https://www.mfa.org/collections">Collections</a>
</body>
</html>
"""

# Cloudflare challenge response
_CLOUDFLARE_HTML = """
<html><head><title>Just a moment...</title></head>
<body><noscript>Enable JavaScript and cookies to continue</noscript></body>
</html>
"""


class TestFetchFromWayback:
    """Test that _fetch_from_wayback extracts text and links correctly."""

    def test_extracts_paragraphs_and_headings(self):
        """Wayback Machine HTML is correctly parsed into text and links."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = _WAYBACK_HTML

        with patch('exhibition_checklist.requests.get', return_value=mock_resp):
            text, links = ec._fetch_from_wayback('https://www.mfa.org/exhibition/picasso-miro-dali-unbound')

        assert 'Boris Fridman' in text, f"'Boris Fridman' not found in: {text[:200]}"
        assert 'Louis Broder' in text
        assert 'Mourlot Frères' in text
        assert len(text) > 100

    def test_returns_empty_on_404(self):
        """Wayback returns empty tuple on non-200 response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch('exhibition_checklist.requests.get', return_value=mock_resp):
            text, links = ec._fetch_from_wayback('https://www.mfa.org/nonexistent')

        assert text == ''
        assert links == []


class TestFetchPageCloudflareDetection:
    """Test that _fetch_page detects Cloudflare challenge and falls to Wayback."""

    def test_cloudflare_challenge_triggers_wayback_fallback(self):
        """When _fetch_page gets a 429 with cf-mitigated:challenge, it calls
        _fetch_from_wayback instead of retrying for 30s."""
        # Mock the direct request to return Cloudflare challenge
        cf_resp = MagicMock()
        cf_resp.status_code = 429
        cf_resp.headers = {'cf-mitigated': 'challenge'}
        cf_resp.text = _CLOUDFLARE_HTML

        with patch('exhibition_checklist.requests.get', return_value=cf_resp), \
             patch.object(ec, '_fetch_from_wayback', return_value=('Wayback text with Boris Fridman', [])) as mock_wb, \
             patch.object(ec, '_cache_get', return_value=None), \
             patch.object(ec, '_cache_put'):
            text, links = ec._fetch_page('https://www.mfa.org/exhibition/picasso-miro-dali-unbound')

        # Wayback was called
        mock_wb.assert_called_once_with('https://www.mfa.org/exhibition/picasso-miro-dali-unbound')
        assert 'Boris Fridman' in text

    def test_normal_429_retries_normally(self):
        """A 429 WITHOUT cf-mitigated:challenge still retries (existing behavior)."""
        # This test verifies we didn't break normal retry logic
        normal_429_resp = MagicMock()
        normal_429_resp.status_code = 429
        normal_429_resp.headers = {}  # No cf-mitigated header

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.text = '<html><p>Normal content after retry</p></html>'
        ok_resp.headers = {}

        # First call returns 429 (normal), second returns 200
        with patch('exhibition_checklist.requests.get', side_effect=[normal_429_resp, ok_resp]), \
             patch.object(ec, '_cache_get', return_value=None), \
             patch.object(ec, '_cache_put'), \
             patch('exhibition_checklist._time_mod') as mock_time, \
             patch.object(ec, '_fetch_from_wayback') as mock_wb:
            # Make the time budget appear sufficient
            mock_time.monotonic.side_effect = [0, 0, 0, 5, 5, 10]  # Within budget
            mock_time.sleep = MagicMock()
            text, links = ec._fetch_page('https://example.com/page')

        # Wayback was NOT called (normal 429 retries)
        mock_wb.assert_not_called()
        assert 'Normal content after retry' in text


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v']))
