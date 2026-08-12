"""tests/test_local426_third_party_provenance.py — LOCAL-426.

A work extracted from a third-party source must NOT report the venue URL as
its source. The verifier (LOCAL-424) treats source_url as evidence; feeding it
the wrong URL means it passes claims it should question.

This test exercises the production provenance logic at module scope — no mirrors,
no inspect.getsource string assertions. It calls the production functions directly.

Test structure:
  1. test_third_party_works_carry_their_actual_source_url
     — Simulates the third-party fallback path (venue returns 429, third-party
       arts publication has the works). Asserts that:
       (a) Each work in the result has source_url == the third-party URL
       (b) result.content_url == the third-party URL
       (c) result.exhibition_url == the venue URL (for reference, not provenance)
       (d) result.is_third_party == True
       (e) NO work has source_url == the venue URL

  2. test_venue_path_works_do_not_get_third_party_source
     — When the venue serves content directly, works should NOT have source_url
       set (or it should match the venue URL), and is_third_party must be False.

  3. test_source_quality_gate_rejects_content_farms
     — The domain quality gate rejects Reddit, Medium, Pinterest, etc.

  4. test_source_quality_gate_accepts_arts_publications
     — The domain quality gate accepts arts publications and newspapers.
"""
import sys
import os
from unittest.mock import patch, MagicMock
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from exhibition_checklist import (
    ExhibitionChecklistResult,
    find_exhibition_checklist,
    _search_exhibition_works_from_web,
    is_usable_exhibition_source,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

VENUE_URL = "https://www.mfa.org"
VENUE_EXHIBITION_URL = "https://www.mfa.org/exhibition/picasso-miro-dali-unbound"
THIRD_PARTY_URL = "https://airmail.news/arts-intel/events/picasso-miro-dali-unbound"
EXHIBITION_NAME = "Picasso, Miró, Dalí: Unbound"

# Simulated third-party page text that mentions the exhibition and works
THIRD_PARTY_PAGE_TEXT = """\
Picasso, Miró, Dalí: Unbound opens at the Museum of Fine Arts, Boston

The exhibition Picasso, Miró, Dalí: Unbound runs through March 2025 at the
Museum of Fine Arts, Boston. The show brings together rarely seen works by
these three giants of modern art.

Among the highlights:

Pablo Picasso, *Guitar*, 1913, oil on canvas
Joan Miró, *The Farm*, 1921-1922, oil on canvas
Salvador Dalí, *The Persistence of Memory*, 1931, oil on canvas

The exhibition was organized by the MFA in collaboration with the Fundació
Joan Miró, Barcelona.
"""

# Simulated LLM extraction result
MOCK_LLM_WORKS = [
    {"title": "Guitar", "artist": "Pablo Picasso", "date": "1913"},
    {"title": "The Farm", "artist": "Joan Miró", "date": "1921-1922"},
    {"title": "The Persistence of Memory", "artist": "Salvador Dalí", "date": "1931"},
]


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1: Third-party works carry their actual source URL
# ═══════════════════════════════════════════════════════════════════════════════

def test_third_party_works_carry_their_actual_source_url():
    """A work extracted from airmail.news must report airmail.news as its source,
    NOT mfa.org. This is the core LOCAL-426 provenance assertion."""

    # Mock strategy: patch _search_exhibition_works_from_web to return works
    # with the third-party URL, simulating what happens when the venue 429s.
    # Also patch _fetch_page so the venue is unreachable and _search_exhibition_url
    # returns the venue's exhibition URL.

    def mock_fetch_page(url, timeout=15):
        """All venue URLs return empty (simulating 429)."""
        return '', []

    def mock_search_exhibition_url(exhibition_name, venue_base_url):
        """Simulate Serper finding the venue's exhibition URL."""
        return VENUE_EXHIBITION_URL

    def mock_search_works_from_web(exhibition_name, venue_name, venue_base_url=''):
        """Return works as if they came from the third-party URL."""
        works = [dict(w) for w in MOCK_LLM_WORKS]
        return works, THIRD_PARTY_URL

    with patch('exhibition_checklist._fetch_page', side_effect=mock_fetch_page), \
         patch('exhibition_checklist._search_exhibition_url', side_effect=mock_search_exhibition_url), \
         patch('exhibition_checklist._search_exhibition_works_from_web', side_effect=mock_search_works_from_web):

        result = find_exhibition_checklist(
            venue_base_url=VENUE_URL,
            exhibition_name=EXHIBITION_NAME,
            venue_name="Museum of Fine Arts, Boston",
        )

    # ─── Assertions ───────────────────────────────────────────────────────────
    assert result.has_works, f"Expected works, got: {result}"
    assert len(result.works) == 3, f"Expected 3 works, got {len(result.works)}"

    # (a) Each work must carry source_url == the third-party URL
    for work in result.works:
        assert 'source_url' in work, (
            f"Work '{work.get('title')}' has no source_url field — "
            f"provenance is lost (LOCAL-426)"
        )
        assert work['source_url'] == THIRD_PARTY_URL, (
            f"Work '{work.get('title')}' reports source_url='{work['source_url']}' "
            f"but text came from {THIRD_PARTY_URL} — the venue URL must NOT be the source"
        )

    # (b) result.content_url must be the third-party URL
    assert result.content_url == THIRD_PARTY_URL, (
        f"result.content_url='{result.content_url}' should be '{THIRD_PARTY_URL}'"
    )

    # (c) result.exhibition_url is the venue URL (for reference, not provenance)
    assert result.exhibition_url == VENUE_EXHIBITION_URL, (
        f"result.exhibition_url should be '{VENUE_EXHIBITION_URL}', got '{result.exhibition_url}'"
    )

    # (d) result.is_third_party must be True
    assert result.is_third_party is True, (
        "result.is_third_party must be True when works came from a non-venue source"
    )

    # (e) NO work should report the venue URL as source_url
    for work in result.works:
        assert work.get('source_url') != VENUE_EXHIBITION_URL, (
            f"CRITICAL (LOCAL-426): Work '{work.get('title')}' reports venue URL "
            f"as source_url — this is exactly the bug: the verifier would treat "
            f"third-party content as museum-sourced evidence"
        )
        assert 'mfa.org' not in work.get('source_url', ''), (
            f"Work '{work.get('title')}' source_url contains 'mfa.org' — "
            f"content came from airmail.news, not the museum"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2: Venue-sourced works do not get third-party provenance
# ═══════════════════════════════════════════════════════════════════════════════

def test_venue_path_works_do_not_get_third_party_source():
    """When the venue serves content directly, is_third_party must be False
    and content_url must equal exhibition_url (or be empty)."""

    # Simulate the venue responding successfully with exhibition text
    VENUE_PAGE_TEXT = """\
    Picasso, Miró, Dalí: Unbound
    October 5, 2024 – March 9, 2025

    Pablo Picasso, Guitar, 1913, oil on canvas
    Joan Miró, The Farm, 1921-1922, oil on canvas
    Salvador Dalí, The Persistence of Memory, 1931, oil on canvas
    """

    def mock_fetch_page(url, timeout=15):
        parsed = urlparse(url)
        if 'mfa.org' in parsed.netloc and 'unbound' in url.lower():
            return VENUE_PAGE_TEXT, [("Picasso, Miró, Dalí: Unbound", "/exhibition/picasso-miro-dali-unbound")]
        if 'mfa.org' in parsed.netloc and '/exhibition' in url:
            return VENUE_PAGE_TEXT, [("Picasso, Miró, Dalí: Unbound", "/exhibition/picasso-miro-dali-unbound")]
        return '', []

    def mock_search_exhibition_url(exhibition_name, venue_base_url):
        return VENUE_EXHIBITION_URL

    with patch('exhibition_checklist._fetch_page', side_effect=mock_fetch_page), \
         patch('exhibition_checklist._search_exhibition_url', side_effect=mock_search_exhibition_url):

        result = find_exhibition_checklist(
            venue_base_url=VENUE_URL,
            exhibition_name=EXHIBITION_NAME,
            venue_name="Museum of Fine Arts, Boston",
        )

    # Venue path: is_third_party must be False
    assert result.is_third_party is False, (
        "Venue-sourced result must not be flagged as third-party"
    )

    # content_url should be empty (venue path doesn't set it — exhibition_url IS the source)
    # OR it should match the exhibition_url
    if result.content_url:
        assert result.content_url == result.exhibition_url, (
            "When venue serves content, content_url (if set) must match exhibition_url"
        )

    # Works from venue should NOT have source_url pointing elsewhere
    for work in result.works:
        if work.get('source_url'):
            assert 'mfa.org' in work['source_url'] or work['source_url'] == result.exhibition_url, (
                f"Venue work source_url should be on mfa.org, got '{work['source_url']}'"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 3: Source quality gate — rejects content farms
# ═══════════════════════════════════════════════════════════════════════════════

def test_source_quality_gate_rejects_content_farms():
    """is_usable_exhibition_source must reject content farms, UGC, and aggregators."""
    blocked_urls = [
        "https://www.reddit.com/r/ArtHistory/comments/123/picasso_exhibit",
        "https://medium.com/@artlover/picasso-miro-dali-at-mfa",
        "https://www.pinterest.com/pin/picasso-exhibition-mfa",
        "https://www.buzzfeed.com/arts/picasso-exhibit-boston",
        "https://en.wikipedia.org/wiki/Picasso",
        "https://www.quora.com/What-works-are-in-the-Picasso-exhibition",
        "https://artlover42.blogspot.com/2024/picasso-mfa.html",
        "https://www.youtube.com/watch?v=abc123",
        "https://www.facebook.com/mfa/posts/exhibition",
    ]

    for url in blocked_urls:
        usable, reason = is_usable_exhibition_source(url)
        assert usable is False, (
            f"Source quality gate SHOULD reject {url} but accepted it: {reason}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 4: Source quality gate — accepts arts publications
# ═══════════════════════════════════════════════════════════════════════════════

def test_source_quality_gate_accepts_arts_publications():
    """is_usable_exhibition_source must accept arts publications and newspapers."""
    allowed_urls = [
        "https://airmail.news/arts-intel/events/picasso-miro-dali-unbound",
        "https://www.artnews.com/art-news/reviews/picasso-miro-dali-mfa-1234/",
        "https://www.theguardian.com/artanddesign/2024/oct/picasso-mfa-review",
        "https://hyperallergic.com/picasso-miro-dali-unbound-mfa-boston/",
        "https://www.nytimes.com/2024/10/05/arts/picasso-mfa-boston.html",
        "https://www.bostonglobe.com/arts/picasso-miro-dali-mfa-exhibition",
        "https://www.artsy.net/article/artsy-editorial-picasso-mfa",
        "https://www.smithsonianmag.com/arts-culture/picasso-miro-dali-exhibit/",
        "https://www.bbc.com/culture/article/picasso-exhibition",
    ]

    for url in allowed_urls:
        usable, reason = is_usable_exhibition_source(url)
        assert usable is True, (
            f"Source quality gate SHOULD accept {url} but rejected it: {reason}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 5: Unknown domains with arts path keywords are accepted
# ═══════════════════════════════════════════════════════════════════════════════

def test_source_quality_gate_unknown_domain_with_arts_path():
    """An unknown domain with arts keywords in the URL path should be accepted."""
    # Regional arts publication not in the allowlist but with arts path
    usable, reason = is_usable_exhibition_source(
        "https://www.bostonartreview.org/exhibition/picasso-miro-dali"
    )
    assert usable is True, f"Unknown domain with arts path should be accepted: {reason}"

    # Random domain with no arts signal should be rejected
    usable, reason = is_usable_exhibition_source(
        "https://www.example-seo-farm.com/news/12345"
    )
    assert usable is False, f"Unknown domain without arts signal should be rejected: {reason}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
