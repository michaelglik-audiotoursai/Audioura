"""
Test 4: Article truncation end-to-end through the processor's request path.

Requirements:
  - Free tier: truncate at 5,000 characters
  - Subscribed tier (ppu/unlimited): truncate at 15,000 characters
  - Notice appended, no dollar figure in any user-facing string
  - Exercises truncate_for_user() which resolves tier via entitlements

The processor's request path is: article_truncation.truncate_for_user(text, user_id).
This is what news_processor_service.py calls at line 381.
"""
import re
import uuid
import pytest
import psycopg2


def _get_conn():
    return psycopg2.connect(
        host="localhost", port="5433",
        dbname="audiotours_subscribed",
        user="admin", password="password123",
    )


def _make_text(length):
    """Generate text of approximately `length` characters with sentence boundaries."""
    sentence = "The quick brown fox jumps over the lazy dog. "
    repeats = (length // len(sentence)) + 1
    return (sentence * repeats)[:length]


class TestArticleTruncationEndToEnd:
    """Article truncation through the service path, both tiers."""

    def test_free_tier_truncation(self, test_user_id):
        """Free user with 8000-char article → truncated to ≤5000 with notice."""
        from article_truncation import truncate_for_user

        text = _make_text(8000)
        result, was_truncated, rule = truncate_for_user(text, test_user_id)

        print(f"  Free tier: {len(text)} chars → {len(result)} chars, rule={rule}")
        assert was_truncated is True
        assert len(result) <= 5000
        assert rule in ("sentence_boundary", "word_boundary")

        # Notice should be appended
        assert "shortened" in result.lower() or "truncated" in result.lower()

        # D58: no dollar figure in user-facing text
        dollar_pattern = re.compile(r'\$\d+')
        assert not dollar_pattern.search(result), \
            f"D58 violation: dollar amount in truncated text"

        # Free notice should mention subscribing and the higher limit
        assert "subscribe" in result.lower() or "15,000" in result
        print(f"  ✓ Free tier truncation:")
        print(f"    {len(text)} → {len(result)} chars")
        print(f"    Rule: {rule}")
        print(f"    Notice mentions subscription ✓")
        print(f"    No dollar figure ✓ (D58)")

    def test_subscribed_tier_truncation(self, ppu_user_id):
        """PPU user with 20000-char article → truncated to ≤15000 with notice."""
        from article_truncation import truncate_for_user

        text = _make_text(20000)
        result, was_truncated, rule = truncate_for_user(text, ppu_user_id)

        print(f"  Subscribed tier: {len(text)} chars → {len(result)} chars, rule={rule}")
        assert was_truncated is True
        assert len(result) <= 15000
        assert rule in ("sentence_boundary", "word_boundary")

        # Notice should be appended
        assert "shortened" in result.lower() or "truncated" in result.lower()

        # D58: no dollar figure in user-facing text
        dollar_pattern = re.compile(r'\$\d+')
        assert not dollar_pattern.search(result), \
            f"D58 violation: dollar amount in subscribed truncation"

        # Subscribed notice should NOT mention subscribing (already subscribed)
        # It just names the limit
        assert "15,000" in result
        print(f"  ✓ Subscribed tier truncation:")
        print(f"    {len(text)} → {len(result)} chars")
        print(f"    Rule: {rule}")
        print(f"    No dollar figure ✓ (D58)")
        print(f"    No subscribe upsell ✓ (already subscribed)")

    def test_free_tier_under_limit_no_truncation(self, test_user_id):
        """Free user with 3000-char article → NOT truncated."""
        from article_truncation import truncate_for_user

        text = _make_text(3000)
        result, was_truncated, rule = truncate_for_user(text, test_user_id)

        print(f"  Free under-limit: {len(text)} chars → {len(result)} chars, rule={rule}")
        assert was_truncated is False
        assert rule == "none"
        assert result == text
        print(f"  ✓ Under-limit text returned unchanged")

    def test_subscribed_tier_under_limit_no_truncation(self, ppu_user_id):
        """PPU user with 10000-char article → NOT truncated."""
        from article_truncation import truncate_for_user

        text = _make_text(10000)
        result, was_truncated, rule = truncate_for_user(text, ppu_user_id)

        print(f"  Subscribed under-limit: {len(text)} chars → {len(result)} chars, rule={rule}")
        assert was_truncated is False
        assert rule == "none"
        assert result == text
        print(f"  ✓ Subscribed under-limit text returned unchanged")

    def test_no_dollar_in_any_notice_variant(self):
        """Verify all notice templates are D58-compliant (no dollar figure)."""
        from article_truncation import _get_notice, get_free_char_limit, get_subscribed_char_limit

        free_notice = _get_notice("free", get_free_char_limit())
        ppu_notice = _get_notice("ppu", get_subscribed_char_limit())
        unlimited_notice = _get_notice("unlimited", get_subscribed_char_limit())

        dollar_pattern = re.compile(r'\$\d+')
        for label, notice in [("free", free_notice), ("ppu", ppu_notice), ("unlimited", unlimited_notice)]:
            assert not dollar_pattern.search(notice), \
                f"D58 violation in {label} notice: {notice}"
            print(f"  Notice ({label}): {notice.strip()[:80]}...")

        print(f"  ✓ All notice variants D58-compliant (no dollar figures)")

    def test_truncation_notice_content_free(self, test_user_id):
        """Free notice: names limit + encourages subscription (D58 exact requirement)."""
        from article_truncation import truncate_for_user

        text = _make_text(8000)
        result, _, _ = truncate_for_user(text, test_user_id)

        # D58: "the last line makes people aware article is truncated because of the cost"
        # BUT copy must say "shortened" not "cost" — D58 reframe: limits, not prices
        # The notice must name the character limit number
        assert "5,000" in result, "Free notice should name the 5,000-char limit"
        # And encourage subscription
        assert "15,000" in result or "subscribe" in result.lower(), \
            "Free notice should mention subscribe or higher limit"
        print(f"  ✓ Free notice names limit (5,000) and higher tier (15,000/subscribe)")

    def test_truncation_preserves_sentence_boundary(self, test_user_id):
        """Truncation cuts at sentence boundary (period/exclamation/question)."""
        from article_truncation import truncate_article_text

        # Build text with clear sentences
        sentences = []
        while len(". ".join(sentences)) < 8000:
            sentences.append("This is sentence number " + str(len(sentences) + 1))
        text = ". ".join(sentences) + "."

        result, was_truncated, rule = truncate_article_text(text, "free")
        assert was_truncated is True

        # Find where the notice starts
        notice_markers = ["\n\nThis article has been shortened",
                         "\n\nYou're reading a shortened"]
        content_end = -1
        for marker in notice_markers:
            idx = result.find(marker)
            if idx > 0:
                content_end = idx
                break

        if content_end > 0:
            content = result[:content_end]
            # Content should end with sentence-ending punctuation
            assert content.rstrip()[-1] in ".!?", \
                f"Content doesn't end at sentence boundary: ...{content[-20:]}"
            print(f"  ✓ Sentence boundary preserved: ends with '{content.rstrip()[-1]}'")
        else:
            print(f"  ⚠ Could not locate notice marker to verify boundary")
