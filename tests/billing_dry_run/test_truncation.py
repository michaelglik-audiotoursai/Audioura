"""
Test 4: Article truncation at free and subscribed limits (5,000 / 15,000).

Verifies:
  - Free tier truncates at 5,000 chars
  - Subscribed tier truncates at 15,000 chars
  - Notice is appended
  - No dollar figure in any user-facing string (D58)
"""
import os
import sys
import re

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5433")
os.environ.setdefault("DB_NAME", "audiotours_subscribed")
os.environ.setdefault("DB_USER", "admin")
os.environ.setdefault("DB_PASSWORD", "password123")
os.environ.setdefault("DATABASE_URL",
    "postgresql://admin:password123@localhost:5433/audiotours_subscribed")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from article_truncation import (
    truncate_article_text, get_free_char_limit, get_subscribed_char_limit,
)


def _has_dollar_figure(text):
    """Check if text contains a dollar amount like $0.34 or $10.00."""
    return bool(re.search(r'\$\d+\.\d{2}', text))


def test_free_tier_truncation():
    """Free tier: 5,000 char limit with upsell notice, no dollar figures."""
    limit = get_free_char_limit()
    assert limit == 5000, f"Expected 5000, got {limit}"

    # Generate text longer than 5000 chars
    # Use sentences so boundary logic can work
    sentences = "This is a test sentence for the article. " * 200  # ~8400 chars
    assert len(sentences) > 5000

    truncated, was_truncated, rule = truncate_article_text(sentences, "free")

    assert was_truncated is True, "Text should have been truncated"
    assert len(truncated) <= 5000, f"Truncated text is {len(truncated)} chars (limit 5000)"
    assert rule in ("sentence_boundary", "word_boundary"), f"Unexpected rule: {rule}"
    assert "shortened" in truncated.lower() or "truncated" in truncated.lower(), (
        "Notice should mention shortening"
    )
    assert "subscribe" in truncated.lower(), (
        "Free tier notice should encourage subscription"
    )
    assert "15,000" in truncated, (
        "Free tier notice should mention the subscribed limit (15,000)"
    )
    assert not _has_dollar_figure(truncated), (
        f"D58 violation: dollar figure found in user-facing text: {truncated[-200:]}"
    )
    print(f"  Free tier PASS: {len(sentences)} chars → {len(truncated)} chars "
          f"(rule: {rule})")
    print(f"  Notice: ...{truncated[-120:]}")


def test_subscribed_tier_truncation():
    """Subscribed tier: 15,000 char limit, no upsell, no dollar figures."""
    limit = get_subscribed_char_limit()
    assert limit == 15000, f"Expected 15000, got {limit}"

    # Generate text longer than 15000 chars
    sentences = "Here is another sample sentence for testing purposes. " * 400  # ~21600
    assert len(sentences) > 15000

    truncated, was_truncated, rule = truncate_article_text(sentences, "ppu")

    assert was_truncated is True, "Text should have been truncated"
    assert len(truncated) <= 15000, f"Truncated text is {len(truncated)} chars (limit 15000)"
    assert rule in ("sentence_boundary", "word_boundary"), f"Unexpected rule: {rule}"
    assert "subscribe" not in truncated.lower(), (
        "Subscribed tier notice should NOT mention subscribing"
    )
    assert not _has_dollar_figure(truncated), (
        f"D58 violation: dollar figure found in user-facing text: {truncated[-200:]}"
    )
    print(f"  Subscribed tier PASS: {len(sentences)} chars → {len(truncated)} chars "
          f"(rule: {rule})")
    print(f"  Notice: ...{truncated[-100:]}")


def test_under_limit_not_truncated():
    """Text under the limit is returned unchanged, no notice."""
    short_text = "Short article that fits within limits."
    result, was_truncated, rule = truncate_article_text(short_text, "free")
    assert was_truncated is False
    assert result == short_text
    assert rule == "none"
    print(f"  Under-limit PASS: text returned unchanged")


def test_unlimited_tier_uses_subscribed_limit():
    """Unlimited tier gets the same 15,000 limit as ppu."""
    sentences = "Test sentence for unlimited tier verification here. " * 400
    truncated_ppu, _, _ = truncate_article_text(sentences, "ppu")
    truncated_unl, _, _ = truncate_article_text(sentences, "unlimited")
    # Both should be truncated to same length (same limit)
    assert len(truncated_ppu) == len(truncated_unl), (
        f"ppu ({len(truncated_ppu)}) and unlimited ({len(truncated_unl)}) "
        f"should have same limit"
    )
    print(f"  Unlimited=PPU limit PASS: both {len(truncated_ppu)} chars")

    print("\n  ✓ ARTICLE TRUNCATION PASSED")
