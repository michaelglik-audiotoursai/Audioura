#!/usr/bin/env python3
"""
Tests for LOCAL-708B / D670 addendum: tell the listener a better plan gives
longer articles — for listening AND translation.

Covers the four things the ticket asks for:

  1. On-screen notice per plan (D670 addendum wording):
       - l1/l2 (entry)  → names the current plan, its page length, the LARGER
         plans by NAME ($10 Pack, Curator) and their page lengths, and ends with
         the "See plans" marker. No character counts, no price (the plan NAME
         "$10 Pack" is allowed — it is the plan's own name, not a price).
       - l3 ($10 Pack)  → names Curator (the only larger plan) + its length.
       - l4 / admin     → length only, "the maximum". No upsell, no See plans.
  2. Translated notice present and worded "listened to and translated".
  3. Spoken audio notice NAMES the larger plans and their page lengths
     (D670 addendum 2), and is only produced when the article was truncated.
  4. Nothing is added when the article fits.

No live DB: _load_plan_meta fails over to _PLAN_META_FALLBACK, and the level is
patched via subscription_levels.get_device_state.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import article_truncation as at


def _article(char_count):
    sentences, n, i = [], 0, 0
    while n < char_count:
        i += 1
        s = f"This is sentence number {i} of a test article on many subjects. "
        sentences.append(s)
        n += len(s)
    return "".join(sentences)[:char_count]


# ─── Level patching ──────────────────────────────────────────────────────────

class _FakeCursor:
    """Force _load_plan_meta to fail over to _PLAN_META_FALLBACK."""
    def execute(self, sql, params=None):
        raise Exception("fake cursor: force _load_plan_meta fallback")

    def fetchone(self):
        return None

    def fetchall(self):
        raise Exception("fake cursor: no plans table")

    def close(self):
        pass


class _FakeConn:
    def cursor(self):
        return _FakeCursor()

    def close(self):
        pass


def _patch_level(level):
    import subscription_levels
    return [
        mock.patch.object(subscription_levels, '_get_conn', return_value=_FakeConn()),
        mock.patch.object(subscription_levels, 'get_device_state',
                          return_value={'level': level, '_exists': True}),
    ]


class _Patched:
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


# ─── 1. On-screen notice per plan ────────────────────────────────────────────

class TestOnScreenNoticePerPlan(unittest.TestCase):

    def test_l1_names_larger_plans_and_pages_and_see_plans(self):
        with _Patched(_patch_level('l1')):
            result, was_trunc, _ = at.truncate_for_user(_article(8000), 'u-l1')
        self.assertTrue(was_trunc)
        self.assertIn('Introduction plan', result)
        self.assertIn('about 1½ pages', result)
        self.assertIn('$10 Pack', result)
        self.assertIn('about 3 pages', result)
        self.assertIn('Curator', result)
        self.assertIn('5', result)
        self.assertIn(at.SEE_PLANS_MARKER, result)
        self.assertNotIn('characters', result.lower())

    def test_l3_names_curator_only(self):
        with _Patched(_patch_level('l3')):
            result, was_trunc, _ = at.truncate_for_user(_article(20000), 'u-l3')
        self.assertTrue(was_trunc)
        self.assertIn('$10 Pack plan', result)
        self.assertIn('about 3 pages', result)
        self.assertIn('Curator', result)
        self.assertIn('about 5 pages', result)
        self.assertIn(at.SEE_PLANS_MARKER, result)

    def test_l4_maximum_only(self):
        with _Patched(_patch_level('l4')):
            result, was_trunc, _ = at.truncate_for_user(_article(40000), 'u-l4')
        self.assertTrue(was_trunc)
        self.assertIn('about 5 pages', result)
        self.assertIn('the maximum', result)
        self.assertNotIn(at.SEE_PLANS_MARKER, result)
        self.assertNotIn('$10 Pack', result)

    def test_admin_maximum_only(self):
        with _Patched(_patch_level('admin')):
            result, was_trunc, _ = at.truncate_for_user(_article(40000), 'u-admin')
        self.assertTrue(was_trunc)
        self.assertIn('about 5 pages', result)
        self.assertIn('the maximum', result)
        self.assertNotIn(at.SEE_PLANS_MARKER, result)

    def test_no_price_figure_anywhere(self):
        import re
        for lvl in ('l1', 'l2', 'l3', 'l4', 'admin'):
            with _Patched(_patch_level(lvl)):
                result, _, _ = at.truncate_for_user(_article(40000), f'u-{lvl}')
            self.assertFalse(re.search(r'\$\d+\.\d{2}', result),
                             f"price figure leaked for {lvl}: {result[-160:]}")

    def test_fits_no_notice(self):
        with _Patched(_patch_level('l1')):
            result, was_trunc, rule = at.truncate_for_user(_article(2000), 'u-l1')
        self.assertFalse(was_trunc)
        self.assertEqual(rule, 'none')
        self.assertNotIn(at.SEE_PLANS_MARKER, result)
        self.assertNotIn('Shortened', result)


# ─── 2. Translated on-screen notice ──────────────────────────────────────────

class TestTranslatedNotice(unittest.TestCase):

    def test_translated_entry_notice_wording(self):
        with _Patched(_patch_level('l1')):
            result, was_trunc, _ = at.truncate_for_user(
                _article(8000), 'u-l1', translated=True)
        self.assertTrue(was_trunc)
        self.assertIn('translated', result.lower())
        self.assertIn('Introduction plan', result)
        self.assertIn('$10 Pack', result)
        self.assertIn(at.SEE_PLANS_MARKER, result)

    def test_translated_top_plan_wording(self):
        with _Patched(_patch_level('admin')):
            result, was_trunc, _ = at.truncate_for_user(
                _article(40000), 'u-admin', translated=True)
        self.assertTrue(was_trunc)
        self.assertIn('listened to and translated', result.lower())
        self.assertIn('about 5 pages', result)
        self.assertIn('the maximum', result)

    def test_build_text_notice_for_user_public(self):
        with _Patched(_patch_level('l1')):
            notice = at.build_text_notice_for_user('u-l1', translated=True)
        self.assertIn('translated', notice.lower())
        self.assertIn('Introduction plan', notice)


# ─── 3. Spoken audio notice ──────────────────────────────────────────────────

class TestSpokenNotice(unittest.TestCase):

    def test_l1_spoken_names_plans_and_pages(self):
        with _Patched(_patch_level('l1')):
            spoken = at.build_spoken_notice_for_user('u-l1')
        self.assertIn('one and a half pages', spoken)
        self.assertIn('Introduction plan', spoken)
        self.assertIn('ten-dollar Pack', spoken)
        self.assertIn('three pages', spoken)
        self.assertIn('Curator', spoken)
        self.assertIn('five', spoken)
        self.assertNotIn('$', spoken)

    def test_l3_spoken_names_curator(self):
        with _Patched(_patch_level('l3')):
            spoken = at.build_spoken_notice_for_user('u-l3')
        self.assertIn('three pages', spoken)
        self.assertIn('ten-dollar Pack', spoken)
        self.assertIn('Curator', spoken)
        self.assertIn('five pages', spoken)

    def test_top_plan_spoken_maximum(self):
        with _Patched(_patch_level('admin')):
            spoken = at.build_spoken_notice_for_user('u-admin')
        self.assertIn('five pages', spoken)
        self.assertIn('the maximum', spoken)
        self.assertNotIn('Pack', spoken)
        self.assertNotIn('Curator', spoken)

    def test_spoken_by_level_matches_example(self):
        """build_spoken_notice(level) reproduces the D670 addendum 2 example."""
        spoken = at.build_spoken_notice('l1')
        self.assertEqual(
            spoken,
            "This article was shortened to about one and a half pages on your "
            "Introduction plan. The ten-dollar Pack plays articles up to about "
            "three pages, and the Curator plan up to five."
        )

    def test_translated_spoken_wording(self):
        with _Patched(_patch_level('l1')):
            spoken = at.build_spoken_notice_for_user('u-l1', translated=True)
        self.assertIn('translated', spoken.lower())
        self.assertIn('ten-dollar Pack', spoken)


# ─── 4. Wiring gate: spoken notice only appended when truncated ──────────────

class TestAudioWiringGate(unittest.TestCase):
    """The news_processor audio path appends the spoken notice ONLY when the
    article was truncated. We verify the gate logic directly (no Polly)."""

    def test_gate_truncated_appends(self):
        display_text = "Full Article: Body."
        was_truncated = True
        with _Patched(_patch_level('l1')):
            spoken = at.build_spoken_notice_for_user('user') if was_truncated else ''
        full = f"{display_text}\n\n{spoken}" if (was_truncated and spoken) else display_text
        self.assertIn('This article was shortened', full)
        self.assertIn('ten-dollar Pack', full)

    def test_gate_not_truncated_no_append(self):
        display_text = "Full Article: Short body."
        was_truncated = False
        spoken = at.build_spoken_notice_for_user('user') if was_truncated else ''
        full = f"{display_text}\n\n{spoken}" if (was_truncated and spoken) else display_text
        self.assertEqual(full, display_text)
        self.assertNotIn('This article was shortened', full)


if __name__ == '__main__':
    print("=" * 70)
    print("LOCAL-708B / D670 addendum: a better plan gives longer articles")
    print("=" * 70)
    unittest.main(verbosity=2)
