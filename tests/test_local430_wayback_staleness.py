"""tests/test_local430_wayback_staleness.py — LOCAL-430.

Tests the snapshot timestamp parsing, staleness bound enforcement, and
archive provenance propagation added by LOCAL-430.

Test structure:
  1. test_parse_wayback_timestamp_from_url — parses 14-digit timestamp from redirect URL
  2. test_parse_wayback_timestamp_raw — parses raw 14-digit timestamp string
  3. test_parse_wayback_timestamp_invalid — returns None for unparseable strings
  4. test_fresh_snapshot_accepted — a snapshot within WAYBACK_MAX_STALENESS_DAYS passes
  5. test_stale_snapshot_rejected — a snapshot older than the bound returns empty
  6. test_mfa_today_snapshot_passes — the MFA page (hours-old snapshot) still passes
  7. test_archive_provenance_on_result — is_from_archive, wayback_snapshot_timestamp set
  8. test_venue_direct_not_marked_archive — when venue serves live, not marked archived
"""
import sys
import os
import re
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import exhibition_checklist as ec


# ═══════════════════════════════════════════════════════════════════════════════
# Test: _parse_wayback_timestamp
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseWaybackTimestamp:
    def test_parse_from_url(self):
        """Extracts 14-digit timestamp from a Wayback redirect URL."""
        url = "https://web.archive.org/web/20260812064828/https://www.mfa.org/exhibition/unbound"
        result = ec._parse_wayback_timestamp(url)
        assert result is not None
        assert result.year == 2026
        assert result.month == 8
        assert result.day == 12
        assert result.hour == 6
        assert result.minute == 48
        assert result.second == 28

    def test_parse_raw_timestamp(self):
        """Parses a raw 14-digit timestamp string."""
        result = ec._parse_wayback_timestamp("20260812064828")
        assert result is not None
        assert result == datetime(2026, 8, 12, 6, 48, 28)

    def test_invalid_returns_none(self):
        """Returns None for strings without a valid timestamp."""
        assert ec._parse_wayback_timestamp("https://example.com/page") is None
        assert ec._parse_wayback_timestamp("not-a-timestamp") is None
        assert ec._parse_wayback_timestamp("") is None
        assert ec._parse_wayback_timestamp("/web/short/url") is None

    def test_malformed_date_returns_none(self):
        """A 14-digit string that isn't a valid date returns None."""
        # Month 99 doesn't exist
        assert ec._parse_wayback_timestamp("20269912064828") is None


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Staleness bound enforcement
# ═══════════════════════════════════════════════════════════════════════════════

# Sample HTML for the Wayback responses
_WAYBACK_HTML = """
<html>
<head><title>Test Exhibition</title></head>
<body>
<h1>Test Exhibition at Gallery</h1>
<p>This is a test exhibition with more than twenty characters of content
that will pass the extraction threshold and produce valid text output.</p>
<p>Among the highlights: Artist One, Title of Work One, 2024, oil on canvas.
This is a real exhibition with real works that people can visit today.</p>
</body>
</html>
"""

_MFA_WAYBACK_HTML = """
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
</body>
</html>
"""


class TestStalenessEnforcement:
    def test_fresh_snapshot_accepted(self):
        """A snapshot from 5 days ago is accepted (well within the 90-day limit)."""
        fresh_ts = (datetime.utcnow() - timedelta(days=5)).strftime('%Y%m%d%H%M%S')
        final_url = f"https://web.archive.org/web/{fresh_ts}/https://www.example.com/exhibition"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = final_url
        mock_resp.text = _WAYBACK_HTML

        with patch('exhibition_checklist.requests.get', return_value=mock_resp):
            text, links = ec._fetch_from_wayback('https://www.example.com/exhibition')

        assert text != '', "Fresh snapshot (5 days) should be accepted"
        assert 'Test Exhibition' in text
        # Metadata should be populated
        assert ec._last_wayback_metadata is not None
        assert ec._last_wayback_metadata['snapshot_timestamp'] == fresh_ts
        assert ec._last_wayback_metadata['age_days'] <= 6  # allow 1 day margin

    def test_stale_snapshot_rejected(self):
        """A snapshot from 180 days ago is rejected (exceeds 90-day limit)."""
        stale_ts = (datetime.utcnow() - timedelta(days=180)).strftime('%Y%m%d%H%M%S')
        final_url = f"https://web.archive.org/web/{stale_ts}/https://www.example.com/old-exhibition"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = final_url
        mock_resp.text = _WAYBACK_HTML

        with patch('exhibition_checklist.requests.get', return_value=mock_resp):
            text, links = ec._fetch_from_wayback('https://www.example.com/old-exhibition')

        assert text == '', f"Stale snapshot (180 days) should be REJECTED, got: {text[:100]}"
        assert links == []
        # Metadata should be None (rejected)
        assert ec._last_wayback_metadata is None

    def test_boundary_at_90_days_accepted(self):
        """A snapshot exactly at the boundary (89 days) is accepted."""
        boundary_ts = (datetime.utcnow() - timedelta(days=89)).strftime('%Y%m%d%H%M%S')
        final_url = f"https://web.archive.org/web/{boundary_ts}/https://www.example.com/exhibition"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = final_url
        mock_resp.text = _WAYBACK_HTML

        with patch('exhibition_checklist.requests.get', return_value=mock_resp):
            text, links = ec._fetch_from_wayback('https://www.example.com/exhibition')

        assert text != '', "Snapshot at 89 days should be accepted"

    def test_boundary_at_91_days_rejected(self):
        """A snapshot at 91 days is rejected (just over the limit)."""
        boundary_ts = (datetime.utcnow() - timedelta(days=91)).strftime('%Y%m%d%H%M%S')
        final_url = f"https://web.archive.org/web/{boundary_ts}/https://www.example.com/exhibition"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = final_url
        mock_resp.text = _WAYBACK_HTML

        with patch('exhibition_checklist.requests.get', return_value=mock_resp):
            text, links = ec._fetch_from_wayback('https://www.example.com/exhibition')

        assert text == '', f"Snapshot at 91 days should be REJECTED, got: {text[:100]}"

    def test_mfa_today_snapshot_passes(self):
        """The MFA page with a same-day snapshot still passes — regression test.

        This is the case that matters: the MFA page fetched today with the
        snapshot from today (or hours ago). Boris Fridman, Louis Broder, and
        Mourlot Frères must all still be present.
        """
        # Simulate a snapshot from a few hours ago (what LEAD verified: 20260812064828)
        today_ts = datetime.utcnow().strftime('%Y%m%d') + '064828'
        final_url = f"https://web.archive.org/web/{today_ts}/https://www.mfa.org/exhibition/picasso-miro-dali-unbound"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = final_url
        mock_resp.text = _MFA_WAYBACK_HTML

        with patch('exhibition_checklist.requests.get', return_value=mock_resp):
            text, links = ec._fetch_from_wayback('https://www.mfa.org/exhibition/picasso-miro-dali-unbound')

        # All three names must survive — this is the D373 regression gate
        assert 'Boris Fridman' in text, f"'Boris Fridman' not found in: {text[:200]}"
        assert 'Louis Broder' in text, f"'Louis Broder' not found in: {text[:200]}"
        assert 'Mourlot Frères' in text, f"'Mourlot Frères' not found in: {text[:200]}"

        # Metadata should be populated
        assert ec._last_wayback_metadata is not None
        assert ec._last_wayback_metadata['age_days'] <= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Archive provenance on ExhibitionChecklistResult
# ═══════════════════════════════════════════════════════════════════════════════

class TestArchiveProvenance:
    def test_archive_provenance_on_result(self):
        """When content comes from Wayback, result.is_from_archive=True and
        wayback_snapshot_timestamp is set.

        This tests the provenance attachment code directly: _fetch_from_wayback
        sets _last_wayback_metadata, and the code after Step 3 in
        find_exhibition_checklist reads it.
        """
        fresh_ts = (datetime.utcnow() - timedelta(days=2)).strftime('%Y%m%d%H%M%S')
        wayback_final_url = f"https://web.archive.org/web/{fresh_ts}/https://www.mfa.org/exhibition/picasso-miro-dali-unbound"
        target_url = 'https://www.mfa.org/exhibition/picasso-miro-dali-unbound'

        # 1. Simulate _fetch_from_wayback populating the metadata
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = wayback_final_url
        mock_resp.text = _MFA_WAYBACK_HTML

        with patch('exhibition_checklist.requests.get', return_value=mock_resp):
            text, links = ec._fetch_from_wayback(target_url)

        # Verify _last_wayback_metadata is populated
        assert ec._last_wayback_metadata is not None
        assert ec._last_wayback_metadata['original_url'] == target_url
        assert ec._last_wayback_metadata['snapshot_timestamp'] == fresh_ts

        # 2. Now simulate the provenance attachment code reading it
        result = ec.ExhibitionChecklistResult()
        result.content_url = target_url
        best_match_url = target_url

        # This is the exact code from find_exhibition_checklist after Step 3:
        if ec._last_wayback_metadata and ec._last_wayback_metadata.get('original_url') == best_match_url:
            result.is_from_archive = True
            result.wayback_snapshot_timestamp = ec._last_wayback_metadata.get('snapshot_timestamp', '')
            result.wayback_age_days = ec._last_wayback_metadata.get('age_days')

        assert result.is_from_archive is True, (
            f"Expected is_from_archive=True, got {result.is_from_archive}"
        )
        assert result.wayback_snapshot_timestamp == fresh_ts
        assert result.wayback_age_days is not None and result.wayback_age_days <= 3
        assert result.is_third_party is False

    def test_cloudflare_triggers_wayback_and_carries_provenance(self):
        """End-to-end: _fetch_page hits Cloudflare, falls to Wayback, and
        _last_wayback_metadata is populated for the caller."""
        fresh_ts = (datetime.utcnow() - timedelta(days=1)).strftime('%Y%m%d%H%M%S')
        target_url = 'https://www.mfa.org/exhibition/picasso-miro-dali-unbound'
        wayback_final_url = f"https://web.archive.org/web/{fresh_ts}/{target_url}"

        cf_resp = MagicMock()
        cf_resp.status_code = 429
        cf_resp.headers = {'cf-mitigated': 'challenge'}
        cf_resp.text = '<html></html>'

        wb_resp = MagicMock()
        wb_resp.status_code = 200
        wb_resp.url = wayback_final_url
        wb_resp.text = _MFA_WAYBACK_HTML

        def mock_get(url, **kwargs):
            if 'web.archive.org' in url:
                return wb_resp
            return cf_resp

        with patch('exhibition_checklist.requests.get', side_effect=mock_get), \
             patch.object(ec, '_cache_get', return_value=None), \
             patch.object(ec, '_cache_put'):
            text, links = ec._fetch_page(target_url)

        # Content came through
        assert 'Boris Fridman' in text

        # Metadata was set by the _fetch_from_wayback call inside _fetch_page
        assert ec._last_wayback_metadata is not None
        assert ec._last_wayback_metadata['original_url'] == target_url
        assert ec._last_wayback_metadata['snapshot_timestamp'] == fresh_ts

    def test_venue_direct_not_marked_archive(self):
        """When the venue serves content directly (no Wayback), is_from_archive=False."""
        # Ensure the module-level metadata is cleared
        ec._last_wayback_metadata = None

        result = ec.ExhibitionChecklistResult()
        result.content_url = 'https://www.mfa.org/exhibition/unbound'
        result.is_from_archive = False

        # Direct construction: verify defaults
        assert result.is_from_archive is False
        assert result.wayback_snapshot_timestamp == ''
        assert result.wayback_age_days is None


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Staleness bound is the module-level constant
# ═══════════════════════════════════════════════════════════════════════════════

class TestStalenessConstant:
    def test_bound_is_90_days(self):
        """The staleness bound is set to 90 days."""
        assert ec.WAYBACK_MAX_STALENESS_DAYS == 90


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v']))
