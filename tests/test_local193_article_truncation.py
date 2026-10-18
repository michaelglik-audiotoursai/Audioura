#!/usr/bin/env python3
"""
Tests for LOCAL-193: Article truncation at tier limits.

Tests:
  T1  Below limit — no notice appended, text unchanged.
  T2  Just over limit — sentence-boundary cut fires.
  T3  Far over limit — sentence-boundary cut (well within budget).
  T4  Exactly at the limit — no truncation (boundary is inclusive).
  T5  No sentence boundaries — word-boundary fallback.
  T6  Free vs subscribed — correct limit chosen for each tier.
  T7  Runtime config change — env var takes immediate effect.
  T8  TTS char count unchanged for >5000-char free article (regression guard).
  T9  Notice text compliance — no dollar amount, no "cost" wording.
  T10 Sentence boundary >15% discard — falls back to word boundary.
"""

import os
import sys
import unittest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from article_truncation import (
    truncate_article_text,
    get_free_char_limit,
    get_subscribed_char_limit,
    get_char_limit_for_tier,
    _find_sentence_boundary,
    _find_word_boundary,
    _get_notice,
    _FREE_NOTICE_A,
    _FREE_NOTICE_B,
    _SUBSCRIBED_NOTICE_A,
    _SUBSCRIBED_NOTICE_B,
)


def _make_article(char_count, with_sentences=True):
    """Generate a test article of exactly char_count characters.
    If with_sentences=True, inserts sentence boundaries every ~100 chars."""
    if with_sentences:
        # Build sentences of ~100 chars each
        sentences = []
        while sum(len(s) for s in sentences) < char_count:
            # Each sentence is ~95 chars + '. ' = ~97 chars
            word = "word "
            sentence = (word * 18).rstrip() + "."  # 18*5-1+1 = 90 chars
            sentences.append(sentence)
        text = " ".join(sentences)
        # Trim to exact length (may break last sentence — that's OK for testing)
        return text[:char_count]
    else:
        # No periods, exclamation marks, or question marks — just words
        word = "abcde "
        text = (word * (char_count // 6 + 1))[:char_count]
        # Ensure no sentence-ending punctuation
        text = text.replace('.', ',').replace('!', ',').replace('?', ',')
        return text


def _make_article_with_sentences(char_count):
    """Generate a test article with clear sentence boundaries."""
    sentences = []
    current_len = 0
    i = 0
    while current_len < char_count:
        i += 1
        s = f"This is sentence number {i} of the test article about various topics. "
        sentences.append(s)
        current_len += len(s)
    text = "".join(sentences)
    return text[:char_count]


class TestBelowLimit(unittest.TestCase):
    """T1: Text below limit — returned unchanged, no notice."""

    def test_free_below_limit(self):
        text = "Short article. Only 50 characters or so."
        result, was_truncated, rule = truncate_article_text(text, 'free')
        self.assertEqual(result, text)
        self.assertFalse(was_truncated)
        self.assertEqual(rule, 'none')

    def test_subscribed_below_limit(self):
        text = _make_article_with_sentences(10000)
        result, was_truncated, rule = truncate_article_text(text, 'ppu')
        self.assertEqual(result, text)
        self.assertFalse(was_truncated)
        self.assertEqual(rule, 'none')

    def test_empty_text(self):
        result, was_truncated, rule = truncate_article_text("", 'free')
        self.assertEqual(result, "")
        self.assertFalse(was_truncated)
        self.assertEqual(rule, 'none')

    def test_none_text(self):
        result, was_truncated, rule = truncate_article_text(None, 'free')
        self.assertIsNone(result)
        self.assertFalse(was_truncated)
        self.assertEqual(rule, 'none')


class TestJustOverLimit(unittest.TestCase):
    """T2: Text just over limit — sentence-boundary cut fires."""

    def test_free_just_over(self):
        # Create text that's 5100 chars (100 over the 5000 limit)
        text = _make_article_with_sentences(5100)
        result, was_truncated, rule = truncate_article_text(text, 'free')

        self.assertTrue(was_truncated)
        self.assertEqual(rule, 'sentence_boundary')
        # Result must be <= 5000 chars
        self.assertLessEqual(len(result), 5000)
        # D670: the notice describes length in PAGES and offers "See plans".
        self.assertIn("Shortened to about 1½ pages", result)
        self.assertIn("See plans", result)
        # Must end at a sentence boundary (before notice)
        notice_start = result.find("\n\nShortened to")
        content = result[:notice_start]
        self.assertTrue(
            content.rstrip().endswith('.') or
            content.rstrip().endswith('!') or
            content.rstrip().endswith('?'),
            f"Content should end at sentence boundary, got: ...{content[-20:]}"
        )

    def test_subscribed_just_over(self):
        # 15100 chars, subscribed limit is 15000 (the maximum)
        text = _make_article_with_sentences(15100)
        result, was_truncated, rule = truncate_article_text(text, 'unlimited')

        self.assertTrue(was_truncated)
        self.assertEqual(rule, 'sentence_boundary')
        self.assertLessEqual(len(result), 15000)
        # Top of the scale: page length + "the maximum", no upsell.
        self.assertIn("Shortened to about 5 pages, the maximum", result)


class TestFarOverLimit(unittest.TestCase):
    """T3: Text far over limit — sentence boundary well within budget."""

    def test_free_far_over(self):
        text = _make_article_with_sentences(20000)
        result, was_truncated, rule = truncate_article_text(text, 'free')

        self.assertTrue(was_truncated)
        self.assertEqual(rule, 'sentence_boundary')
        self.assertLessEqual(len(result), 5000)

    def test_subscribed_far_over(self):
        text = _make_article_with_sentences(50000)
        result, was_truncated, rule = truncate_article_text(text, 'ppu')

        self.assertTrue(was_truncated)
        self.assertEqual(rule, 'sentence_boundary')
        self.assertLessEqual(len(result), 15000)


class TestExactlyAtLimit(unittest.TestCase):
    """T4: Text exactly at the limit — no truncation (inclusive boundary)."""

    def test_free_exactly_at_limit(self):
        text = _make_article_with_sentences(5000)
        result, was_truncated, rule = truncate_article_text(text, 'free')
        self.assertEqual(result, text)
        self.assertFalse(was_truncated)
        self.assertEqual(rule, 'none')

    def test_subscribed_exactly_at_limit(self):
        text = _make_article_with_sentences(15000)
        result, was_truncated, rule = truncate_article_text(text, 'ppu')
        self.assertEqual(result, text)
        self.assertFalse(was_truncated)
        self.assertEqual(rule, 'none')


class TestNoSentenceBoundaries(unittest.TestCase):
    """T5: Article with no sentence boundaries — word-boundary fallback."""

    def test_no_sentences_free(self):
        # Text with no periods/exclamation/question marks
        text = _make_article(6000, with_sentences=False)
        # Verify no sentence endings
        self.assertNotIn('.', text)
        self.assertNotIn('!', text)
        self.assertNotIn('?', text)

        result, was_truncated, rule = truncate_article_text(text, 'free')

        self.assertTrue(was_truncated)
        self.assertEqual(rule, 'word_boundary')
        self.assertLessEqual(len(result), 5000)
        # Should still end cleanly (not mid-word, before the notice)

    def test_no_sentences_subscribed(self):
        text = _make_article(20000, with_sentences=False)
        result, was_truncated, rule = truncate_article_text(text, 'unlimited')

        self.assertTrue(was_truncated)
        self.assertEqual(rule, 'word_boundary')
        self.assertLessEqual(len(result), 15000)


class TestTierSelection(unittest.TestCase):
    """T6: Free vs subscribed tier selects the correct limit."""

    def test_free_tier_limit(self):
        self.assertEqual(get_char_limit_for_tier('free'), 5000)

    def test_ppu_tier_limit(self):
        self.assertEqual(get_char_limit_for_tier('ppu'), 15000)

    def test_unlimited_tier_limit(self):
        self.assertEqual(get_char_limit_for_tier('unlimited'), 15000)

    def test_free_truncates_at_5000(self):
        """8000-char article: free truncates, subscribed does not."""
        text = _make_article_with_sentences(8000)

        free_result, free_truncated, _ = truncate_article_text(text, 'free')
        sub_result, sub_truncated, _ = truncate_article_text(text, 'ppu')

        self.assertTrue(free_truncated)
        self.assertLessEqual(len(free_result), 5000)

        self.assertFalse(sub_truncated)
        self.assertEqual(sub_result, text)

    def test_both_truncate_at_different_limits(self):
        """20000-char article: both truncate, but at different limits."""
        text = _make_article_with_sentences(20000)

        free_result, free_truncated, _ = truncate_article_text(text, 'free')
        sub_result, sub_truncated, _ = truncate_article_text(text, 'ppu')

        self.assertTrue(free_truncated)
        self.assertTrue(sub_truncated)
        self.assertLessEqual(len(free_result), 5000)
        self.assertLessEqual(len(sub_result), 15000)
        # Subscribed gets more text
        self.assertGreater(len(sub_result), len(free_result))


class TestRuntimeConfig(unittest.TestCase):
    """T7: Env var change takes immediate effect (no restart)."""

    def setUp(self):
        # Save originals
        self._orig_free = os.environ.get('NEWS_FREE_CHAR_LIMIT')
        self._orig_sub = os.environ.get('NEWS_SUBSCRIBED_CHAR_LIMIT')

    def tearDown(self):
        # Restore originals
        if self._orig_free is None:
            os.environ.pop('NEWS_FREE_CHAR_LIMIT', None)
        else:
            os.environ['NEWS_FREE_CHAR_LIMIT'] = self._orig_free
        if self._orig_sub is None:
            os.environ.pop('NEWS_SUBSCRIBED_CHAR_LIMIT', None)
        else:
            os.environ['NEWS_SUBSCRIBED_CHAR_LIMIT'] = self._orig_sub

    def test_change_free_limit(self):
        os.environ['NEWS_FREE_CHAR_LIMIT'] = '3000'
        self.assertEqual(get_free_char_limit(), 3000)
        self.assertEqual(get_char_limit_for_tier('free'), 3000)

        # 4000-char article should now be truncated
        text = _make_article_with_sentences(4000)
        result, was_truncated, _ = truncate_article_text(text, 'free')
        self.assertTrue(was_truncated)
        self.assertLessEqual(len(result), 3000)

    def test_change_subscribed_limit(self):
        os.environ['NEWS_SUBSCRIBED_CHAR_LIMIT'] = '10000'
        self.assertEqual(get_subscribed_char_limit(), 10000)
        self.assertEqual(get_char_limit_for_tier('ppu'), 10000)

        # 12000-char article should now be truncated for subscribed
        text = _make_article_with_sentences(12000)
        result, was_truncated, _ = truncate_article_text(text, 'ppu')
        self.assertTrue(was_truncated)
        self.assertLessEqual(len(result), 10000)

    def test_config_shown_without_code_change(self):
        """Demonstrate the config is changeable at runtime."""
        # Default
        self.assertEqual(get_free_char_limit(), 5000)

        # Change it
        os.environ['NEWS_FREE_CHAR_LIMIT'] = '7500'
        self.assertEqual(get_free_char_limit(), 7500)

        # Change it again
        os.environ['NEWS_FREE_CHAR_LIMIT'] = '2000'
        self.assertEqual(get_free_char_limit(), 2000)


class TestTTSUnchanged(unittest.TestCase):
    """T8: [LOCAL-708 / D670] clean_text_for_polly no longer imposes a cap.

    Before LOCAL-708, clean_text_for_polly() hard-capped the text at 5,000
    characters, so a free/admin alike could never hear more than ~1.5 pages.
    LOCAL-708 removes that cap: article length is governed by the listener's
    PLAN limit, applied upstream in process_audio() via truncate_for_user(), and
    the full-article audio is synthesised from that already-truncated text.

    This test proves the cap is GONE: cleaning a 12,000-char article returns
    ~12,000 chars (only the HTML/URL/whitespace cleaning shrinks it slightly),
    NOT ~5,000. The per-plan truncation is exercised separately in the
    LOCAL-708 test suite.
    """

    def test_clean_text_no_longer_caps_at_5000(self):
        """clean_text_for_polly must NOT truncate long text to 5,000 chars."""
        from news_processor_service import clean_text_for_polly

        # A >5,000-char article with no HTML/URLs so cleaning barely changes length.
        article = _make_article_with_sentences(12000)
        cleaned = clean_text_for_polly(article)

        # The old cap would have forced this to ~5,050; it must now be well above.
        self.assertGreater(
            len(cleaned), 10000,
            f"clean_text_for_polly still appears to cap text (got {len(cleaned)} chars)"
        )
        # No "truncated for cost control" marker — that message is gone.
        self.assertNotIn("truncated for cost control", cleaned.lower())

        print(f"  Original chars:        {len(article)}")
        print(f"  clean_text_for_polly:  {len(cleaned)} (no 5,000 cap)")
        print(f"  CAP REMOVED: ✓")

    def test_display_and_audio_share_one_truncation(self):
        """The audio and the displayed text come from the SAME truncated source.

        truncate_for_user() is the single source of truth. Whatever it returns is
        both shown and voiced — there is no second, different cap applied to the
        audio. We assert the truncated text, once cleaned for TTS, still reflects
        the plan limit (not a smaller hidden cap).
        """
        from news_processor_service import clean_text_for_polly

        # Simulate the admin plan limit (15,000) via the legacy 'ppu' entry point
        # (ppu/unlimited map to the ceiling, 15,000) so this test needs no DB.
        article = _make_article_with_sentences(40000)
        display_text, was_truncated, _ = truncate_article_text(article, 'ppu')
        self.assertTrue(was_truncated)
        self.assertLessEqual(len(display_text), 15000)

        # The TTS path cleans the SAME display_text — length stays near the plan
        # limit (cleaning only strips HTML/whitespace, which this text has none).
        voiced = clean_text_for_polly(display_text)
        self.assertGreater(
            len(voiced), 10000,
            f"Voiced text shrank unexpectedly (got {len(voiced)} chars) — "
            f"a hidden cap would show up here"
        )
        print(f"  Display chars:  {len(display_text)} (<= 15,000 plan limit)")
        print(f"  Voiced chars:   {len(voiced)} (same source, no extra cap)")


class TestNoticeCompliance(unittest.TestCase):
    """T9: No dollar amount, no 'cost' wording in user-facing strings."""

    def test_free_notice_no_cost_no_dollar(self):
        notice = _FREE_NOTICE_A.format(limit="5,000", sub_limit="15,000")
        self.assertNotIn('$', notice)
        self.assertNotIn('cost', notice.lower())
        self.assertNotIn('token', notice.lower())
        self.assertNotIn('save', notice.lower())

    def test_free_notice_b_no_cost_no_dollar(self):
        notice = _FREE_NOTICE_B.format(limit="5,000", sub_limit="15,000")
        self.assertNotIn('$', notice)
        self.assertNotIn('cost', notice.lower())
        self.assertNotIn('token', notice.lower())

    def test_subscribed_notice_no_cost_no_dollar(self):
        notice = _SUBSCRIBED_NOTICE_A.format(limit="15,000")
        self.assertNotIn('$', notice)
        self.assertNotIn('cost', notice.lower())
        self.assertNotIn('token', notice.lower())

    def test_subscribed_notice_b_no_cost_no_dollar(self):
        notice = _SUBSCRIBED_NOTICE_B.format(limit="15,000")
        self.assertNotIn('$', notice)
        self.assertNotIn('cost', notice.lower())
        self.assertNotIn('token', notice.lower())

    def test_truncated_output_no_cost_no_dollar(self):
        """Full integration: truncate an article and grep the output."""
        text = _make_article_with_sentences(8000)
        result, _, _ = truncate_article_text(text, 'free')
        self.assertNotIn('$', result)
        self.assertNotIn('cost', result.lower())

        result_sub, _, _ = truncate_article_text(text * 3, 'ppu')
        self.assertNotIn('$', result_sub)
        self.assertNotIn('cost', result_sub.lower())


class TestSentenceBoundaryFallback(unittest.TestCase):
    """T10: When sentence boundary discards >15% of allowance, fall back to word boundary."""

    def test_sentence_too_far_back(self):
        """Article where the only sentence boundary is very early, forcing word fallback."""
        # First sentence ends at position 50, then no more sentence boundaries
        # for a text that's 6000 chars long
        first_sentence = "This is the only sentence in the whole article."  # 49 chars
        # Fill rest with no-punctuation text (spaces but no . ! ?)
        filler = " " + "word " * 2000  # ~10000 chars of words without sentence endings
        text = first_sentence + filler
        text = text[:6000]  # trim to 6000 chars (over free limit of 5000)

        result, was_truncated, rule = truncate_article_text(text, 'free')

        self.assertTrue(was_truncated)
        # The only sentence boundary is at position 49, which is way below
        # 85% of the content budget (~4900 * 0.85 = ~4165). So word boundary fires.
        self.assertEqual(rule, 'word_boundary')
        self.assertLessEqual(len(result), 5000)


class TestNoticeNotOverLimit(unittest.TestCase):
    """The appended notice must not push the text back over the limit."""

    def test_result_within_limit_free(self):
        text = _make_article_with_sentences(8000)
        result, was_truncated, _ = truncate_article_text(text, 'free')
        if was_truncated:
            self.assertLessEqual(len(result), get_free_char_limit())

    def test_result_within_limit_subscribed(self):
        text = _make_article_with_sentences(30000)
        result, was_truncated, _ = truncate_article_text(text, 'ppu')
        if was_truncated:
            self.assertLessEqual(len(result), get_subscribed_char_limit())

    def test_many_articles_all_within_limit(self):
        """Fuzz: 50 random-length articles all stay within limit."""
        import random
        random.seed(42)
        for _ in range(50):
            length = random.randint(5001, 50000)
            tier = random.choice(['free', 'ppu', 'unlimited'])
            text = _make_article_with_sentences(length)
            result, was_truncated, _ = truncate_article_text(text, tier)
            limit = get_char_limit_for_tier(tier)
            self.assertLessEqual(
                len(result), limit,
                f"Result ({len(result)}) exceeded limit ({limit}) for "
                f"tier={tier}, original_len={length}"
            )


if __name__ == '__main__':
    print("=" * 70)
    print("LOCAL-193: Article Truncation Tests")
    print("=" * 70)
    unittest.main(verbosity=2)
