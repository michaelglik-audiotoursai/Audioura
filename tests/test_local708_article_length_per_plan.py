#!/usr/bin/env python3
"""
Tests for LOCAL-708 / D670: Article length per plan (text AND audio).

The listener's PLAN limit (plans.article_char_limit) governs how long an article
is — both the text they read and the audio they hear. The Administrator plan
gets ~5 pages (15,000 chars), not the old fixed 5,000-char cap.

These tests use NO live database: the per-plan resolution path
(subscription_levels.get_device_state → plans.article_char_limit) is exercised
against a fake connection/cursor, so they run anywhere.

Coverage:
  A. Per-plan limits resolved from the plans table: l1 5k, l3 10k, admin 15k.
  B. Missing article_char_limit column → code default 5,000 (fail-safe).
  C. NULL article_char_limit value → code default 5,000.
  D. Unknown level / empty user → code default 5,000.
  E. Env var is a GLOBAL CEILING: lowering NEWS_SUBSCRIBED_CHAR_LIMIT clamps
     every plan; a per-plan value below the ceiling is honoured.
  F. Boundary rules unchanged (sentence/word) at a per-plan limit.
  G. Audio follows the text limit: the full-article text synthesised is the
     plan-truncated text (never more than the plan allows).
  H. A 15,000-char article produces ONE continuous MP3 (chunks joined) on a
     stub voice service — the polly-tts 2,000-char split is reused, not
     duplicated.
"""

import os
import sys
import json
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import article_truncation as at


def _make_article_with_sentences(char_count):
    """Generate an article with clear sentence boundaries, exactly char_count."""
    sentences = []
    current_len = 0
    i = 0
    while current_len < char_count:
        i += 1
        s = f"This is sentence number {i} of the test article about various topics. "
        sentences.append(s)
        current_len += len(s)
    return "".join(sentences)[:char_count]


# ─── Fake DB plumbing for the per-plan resolution path ───────────────────────

class _FakeCursor:
    """Minimal cursor: resolves device level and plan article_char_limit from
    the dicts handed to the fake connection."""

    def __init__(self, device_levels, plan_limits, raise_on_plan_select=False):
        self._device_levels = device_levels
        self._plan_limits = plan_limits
        self._raise_on_plan_select = raise_on_plan_select
        self._result = None

    def execute(self, sql, params=None):
        sql_l = sql.lower()
        if 'from device_entitlement' in sql_l:
            # get_device_state query — but article_truncation uses
            # subscription_levels.get_device_state directly (mocked), so this
            # path is not normally hit. Kept for completeness.
            uid = params[0]
            lvl = self._device_levels.get(uid)
            self._result = (uid, lvl, None, None, 0, 0, 0, None) if lvl else None
        elif 'article_char_limit from plans' in sql_l:
            if self._raise_on_plan_select:
                raise Exception('column "article_char_limit" does not exist')
            level = params[0]
            if level in self._plan_limits:
                self._result = (self._plan_limits[level],)
            else:
                self._result = None
        else:
            self._result = None

    def fetchone(self):
        return self._result

    def close(self):
        pass


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass


def _patch_resolution(level, plan_limits, raise_on_plan_select=False):
    """Return a context manager patching subscription_levels so that
    _resolve_plan_article_limit sees `level` for the user and `plan_limits` for
    the plans table."""
    import subscription_levels

    cur = _FakeCursor({}, plan_limits, raise_on_plan_select)
    conn = _FakeConn(cur)

    patches = [
        mock.patch.object(subscription_levels, '_get_conn', return_value=conn),
        mock.patch.object(subscription_levels, 'get_device_state',
                          return_value={'level': level, '_exists': True}),
    ]
    return patches


class _Patched:
    """Apply a list of patch objects as one context manager."""
    def __init__(self, patches):
        self._patches = patches

    def __enter__(self):
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()
        return False


# Canonical per-plan values from migration 039.
_PLAN_LIMITS = {
    'l1': 5000, 'l2': 5000, 'l3': 10000, 'l4': 15000,
    'admin': 15000, 'tester': 15000,
    'free': 5000, 'ppu': 5000, 'unlimited': 5000,
}


class TestPerPlanLimits(unittest.TestCase):
    """A: Each plan resolves to its own article_char_limit."""

    def test_l1_gets_5000(self):
        with _Patched(_patch_resolution('l1', _PLAN_LIMITS)):
            self.assertEqual(at.get_article_limit_for_user('user-l1'), 5000)

    def test_l3_gets_10000(self):
        with _Patched(_patch_resolution('l3', _PLAN_LIMITS)):
            self.assertEqual(at.get_article_limit_for_user('user-l3'), 10000)

    def test_admin_gets_15000(self):
        with _Patched(_patch_resolution('admin', _PLAN_LIMITS)):
            self.assertEqual(at.get_article_limit_for_user('user-admin'), 15000)

    def test_l4_and_tester_get_15000(self):
        with _Patched(_patch_resolution('l4', _PLAN_LIMITS)):
            self.assertEqual(at.get_article_limit_for_user('user-l4'), 15000)
        with _Patched(_patch_resolution('tester', _PLAN_LIMITS)):
            self.assertEqual(at.get_article_limit_for_user('user-tester'), 15000)


class TestMissingColumnOrValue(unittest.TestCase):
    """B/C/D: Fail-safe to the code default of 5,000."""

    def test_missing_column_falls_back_to_5000(self):
        # The SELECT article_char_limit ... raises (un-migrated DB).
        with _Patched(_patch_resolution('admin', _PLAN_LIMITS, raise_on_plan_select=True)):
            self.assertEqual(at.get_article_limit_for_user('user-admin'), 5000)

    def test_null_value_falls_back_to_5000(self):
        limits = dict(_PLAN_LIMITS)
        limits['admin'] = None  # column present but NULL for this plan
        with _Patched(_patch_resolution('admin', limits)):
            self.assertEqual(at.get_article_limit_for_user('user-admin'), 5000)

    def test_unknown_level_falls_back_to_5000(self):
        with _Patched(_patch_resolution('does-not-exist', _PLAN_LIMITS)):
            self.assertEqual(at.get_article_limit_for_user('user-x'), 5000)

    def test_empty_user_falls_back_to_5000(self):
        # Empty user never hits the DB.
        self.assertEqual(at.get_article_limit_for_user(''), 5000)
        self.assertEqual(at.get_article_limit_for_user(None), 5000)


class TestEnvCeiling(unittest.TestCase):
    """E: NEWS_SUBSCRIBED_CHAR_LIMIT is a global ceiling (emergency throttle)."""

    def setUp(self):
        self._orig = os.environ.get('NEWS_SUBSCRIBED_CHAR_LIMIT')

    def tearDown(self):
        if self._orig is None:
            os.environ.pop('NEWS_SUBSCRIBED_CHAR_LIMIT', None)
        else:
            os.environ['NEWS_SUBSCRIBED_CHAR_LIMIT'] = self._orig

    def test_ceiling_clamps_admin_down(self):
        os.environ['NEWS_SUBSCRIBED_CHAR_LIMIT'] = '8000'
        with _Patched(_patch_resolution('admin', _PLAN_LIMITS)):
            # admin's per-plan value is 15,000, but the ceiling clamps it to 8,000.
            self.assertEqual(at.get_article_limit_for_user('user-admin'), 8000)

    def test_ceiling_above_plan_value_is_noop(self):
        os.environ['NEWS_SUBSCRIBED_CHAR_LIMIT'] = '15000'
        with _Patched(_patch_resolution('l3', _PLAN_LIMITS)):
            # l3 is 10,000, below the ceiling — honoured as-is.
            self.assertEqual(at.get_article_limit_for_user('user-l3'), 10000)


class TestBoundaryRulesAtPlanLimit(unittest.TestCase):
    """F: Sentence/word boundary rules unchanged when driven per-plan."""

    def test_admin_truncates_at_sentence_boundary(self):
        article = _make_article_with_sentences(40000)
        with _Patched(_patch_resolution('admin', _PLAN_LIMITS)):
            result, was_truncated, rule = at.truncate_for_user(article, 'user-admin')
        self.assertTrue(was_truncated)
        self.assertEqual(rule, 'sentence_boundary')
        self.assertLessEqual(len(result), 15000)
        # Content before the notice ends at a sentence boundary.
        notice_idx = result.find('\n\nThis article has been shortened')
        content = result[:notice_idx] if notice_idx > 0 else result
        self.assertIn(content.rstrip()[-1], '.!?')

    def test_word_boundary_fallback_no_sentences(self):
        article = ("word " * 5000)  # ~25,000 chars, no sentence endings
        with _Patched(_patch_resolution('l3', _PLAN_LIMITS)):
            result, was_truncated, rule = at.truncate_for_user(article, 'user-l3')
        self.assertTrue(was_truncated)
        self.assertEqual(rule, 'word_boundary')
        self.assertLessEqual(len(result), 10000)

    def test_under_plan_limit_not_truncated(self):
        article = _make_article_with_sentences(4000)
        with _Patched(_patch_resolution('l1', _PLAN_LIMITS)):
            result, was_truncated, rule = at.truncate_for_user(article, 'user-l1')
        self.assertFalse(was_truncated)
        self.assertEqual(rule, 'none')
        self.assertEqual(result, article)

    def test_admin_keeps_more_than_l1(self):
        """The admin plan delivers materially more text than L1 for one article."""
        article = _make_article_with_sentences(40000)
        with _Patched(_patch_resolution('l1', _PLAN_LIMITS)):
            l1_text, _, _ = at.truncate_for_user(article, 'user-l1')
        with _Patched(_patch_resolution('admin', _PLAN_LIMITS)):
            admin_text, _, _ = at.truncate_for_user(article, 'user-admin')
        self.assertLessEqual(len(l1_text), 5000)
        self.assertGreater(len(admin_text), len(l1_text))
        self.assertLessEqual(len(admin_text), 15000)
        # ~5 pages vs ~1.5 pages: admin should be roughly 3x the L1 text.
        self.assertGreater(len(admin_text), 2 * len(l1_text))


class TestNoticeByPlan(unittest.TestCase):
    """The upsell notice fires only for entry (floor) plans; higher plans get
    the limit-only notice (D58: no dollar figure)."""

    def test_entry_plan_gets_upsell(self):
        article = _make_article_with_sentences(8000)
        with _Patched(_patch_resolution('l1', _PLAN_LIMITS)):
            result, _, _ = at.truncate_for_user(article, 'user-l1')
        self.assertIn('5,000', result)
        self.assertIn('15,000', result)          # names the higher ceiling
        self.assertNotIn('$', result)

    def test_higher_plan_no_upsell(self):
        article = _make_article_with_sentences(40000)
        with _Patched(_patch_resolution('admin', _PLAN_LIMITS)):
            result, _, _ = at.truncate_for_user(article, 'user-admin')
        self.assertIn('15,000', result)
        # No "Subscribe to read ..." invitation on the top plan.
        self.assertNotIn('Subscribe to read', result)
        self.assertNotIn('$', result)


class TestAudioFollowsTextLimit(unittest.TestCase):
    """G: The full-article audio is synthesised from the plan-truncated text."""

    def test_audio_text_equals_plan_truncated_text(self):
        """Mirror the news_processor audio path: audio-99 voices display_text,
        which is truncate_for_user(full_text). Prove the voiced text never
        exceeds the plan limit and matches the displayed text."""
        from news_processor_service import clean_text_for_polly

        full_text = _make_article_with_sentences(40000)
        with _Patched(_patch_resolution('admin', _PLAN_LIMITS)):
            display_text, was_truncated, _ = at.truncate_for_user(full_text, 'user-admin')

        self.assertTrue(was_truncated)
        self.assertLessEqual(len(display_text), 15000)

        # This is exactly what process_audio feeds to TTS for audio-99.
        voiced = clean_text_for_polly(f"Full Article: {display_text}")
        # Cleaning only strips whitespace/HTML; length stays near the plan limit.
        self.assertGreater(len(voiced), 10000)
        self.assertLessEqual(len(voiced), 15100)  # +"Full Article: " prefix, within ceiling


# ─── H: one continuous MP3 from the stub voice service ───────────────────────

class _FakeAudioStream:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data


class _StubPollyClient:
    """Stub Polly: each synthesize_speech call returns a distinct byte blob for
    the chunk it was given, so we can verify the chunks were joined in order."""

    def __init__(self):
        self.calls = []

    def synthesize_speech(self, **kwargs):
        text = kwargs.get('Text', '')
        self.calls.append(text)
        # Deterministic per-chunk payload: a header-less raw frame stand-in.
        blob = (f"[CHUNK:{len(self.calls)}:{len(text)}]").encode('utf-8')
        return {'AudioStream': _FakeAudioStream(blob)}


class TestContinuousMp3OnStub(unittest.TestCase):
    """H: A 15,000-char article is split by polly-tts (2,000-char chunks) and
    joined into ONE deliverable. We reuse the real polly_tts_service split; we do
    not duplicate it."""

    def _synthesize(self, text, voice_id='Joanna'):
        import importlib
        os.environ['TTS_ENGINE'] = 'polly'  # force the Polly split/join path
        import polly_tts_service
        importlib.reload(polly_tts_service)

        stub = _StubPollyClient()
        polly_tts_service.polly_client = stub

        app = polly_tts_service.app
        app.config['TESTING'] = True
        client = app.test_client()
        resp = client.post('/synthesize', json={
            'text': text, 'voice_id': voice_id, 'output_format': 'mp3',
        })
        return resp, stub

    def test_15000_char_article_single_joined_mp3(self):
        # Build the admin-plan article (15,000 chars delivered).
        article = _make_article_with_sentences(40000)
        with _Patched(_patch_resolution('admin', _PLAN_LIMITS)):
            display_text, was_truncated, _ = at.truncate_for_user(article, 'user-admin')
        self.assertTrue(was_truncated)
        self.assertGreater(len(display_text), 10000)
        self.assertLessEqual(len(display_text), 15000)

        resp, stub = self._synthesize(f"Full Article: {display_text}")

        self.assertEqual(resp.status_code, 200,
                         f"synthesize failed: {resp.status_code} {resp.data[:200]}")

        # polly-tts splits >2,000 chars: a ~15,000-char text => multiple chunks.
        self.assertGreater(len(stub.calls), 1,
                           "Expected the 2,000-char split to produce multiple chunks")
        # No single chunk exceeds the 2,000-char Polly limit.
        for c in stub.calls:
            self.assertLessEqual(len(c), 2000, f"chunk exceeded 2000 chars: {len(c)}")

        # ONE deliverable: the response body is the ordered concatenation of all
        # chunk blobs (pure-Polly path byte-concats raw frames).
        expected = b''.join(
            (f"[CHUNK:{i+1}:{len(c)}]").encode('utf-8')
            for i, c in enumerate(stub.calls)
        )
        self.assertEqual(resp.data, expected,
                         "Joined MP3 is not the in-order concatenation of the chunks")

        # Every character of the (truncated) article reached TTS: the sum of
        # chunk lengths equals the submitted text length (minus the inter-chunk
        # spaces the word splitter drops).
        total_chunk_chars = sum(len(c) for c in stub.calls)
        submitted = len(f"Full Article: {display_text}")
        self.assertGreaterEqual(total_chunk_chars, submitted - len(stub.calls) - 5)

        print(f"  Delivered text:  {len(display_text)} chars (admin plan, <=15,000)")
        print(f"  Chunks (split):  {len(stub.calls)}")
        print(f"  Joined MP3 size: {len(resp.data)} bytes (one deliverable)")

    def test_short_article_single_chunk(self):
        """A short (<2,000-char) article is one chunk — no split, still one MP3."""
        resp, stub = self._synthesize("Short article. Only a few words here.")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(stub.calls), 1)


if __name__ == '__main__':
    print("=" * 70)
    print("LOCAL-708 / D670: Article length per plan (text AND audio)")
    print("=" * 70)
    unittest.main(verbosity=2)
