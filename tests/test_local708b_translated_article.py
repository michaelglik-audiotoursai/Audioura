#!/usr/bin/env python3
"""
LOCAL-708B / D670 addendum — translated-article path.

A translated article must carry the SAME D670 truncation notice as the English
one, worded "listened to and translated" and in the listener's language when the
app is localised (English otherwise), and its full-article audio must end with
the spoken notice that NAMES the larger plans. Nothing is added when it fits.

This drives TranslationService._create_english_structure_zip with the network
stubbed: translate_text is a marker ("[es] ..."), generate_audio records the
text it was handed. We assert on the recorded full-article audio text and on the
translated full_text that reaches the HTML.
"""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'translation-service'))

import article_truncation as at
import translation_service as ts


def _article(char_count):
    sentences, n, i = [], 0, 0
    while n < char_count:
        i += 1
        s = f"This is sentence number {i} of a translated article about things. "
        sentences.append(s)
        n += len(s)
    return "".join(sentences)[:char_count]


class _FakeCursor:
    def execute(self, sql, params=None):
        raise Exception("force plan-meta fallback")

    def fetchone(self):
        return None

    def fetchall(self):
        raise Exception("no plans table")

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


def _make_service():
    """Build a TranslationService without constructing boto3 clients."""
    svc = ts.TranslationService.__new__(ts.TranslationService)
    svc.audio_calls = []  # (text, lang)

    def fake_translate_text(text, target_language, preserve_voice_commands=False):
        if target_language == 'en' or not text:
            return text
        return f"[{target_language}] {text}"

    def fake_generate_audio(text, target_language, *a, **k):
        svc.audio_calls.append((text, target_language))
        return b"MP3DATA"

    def fake_html(title, summary_text, full_text, topics, audio_files, target_language):
        svc.last_html_full_text = full_text
        return "<html></html>"

    svc.translate_text = fake_translate_text
    svc.generate_audio = fake_generate_audio
    svc._create_english_format_html = fake_html
    svc.last_html_full_text = None
    return svc


class TestTranslatedArticleTruncationAndNotice(unittest.TestCase):

    def _run(self, level, target_language, char_count):
        svc = _make_service()
        full_body = _article(char_count)
        content = f"Summary: A short summary.\n\nFull Article:{full_body}"
        with _Patched(_patch_level(level)):
            zip_data = svc._create_english_structure_zip(
                "Title", content, [], target_language, user_id="u-" + level)
        return svc, zip_data

    def test_entry_translated_notice_and_spoken_audio(self):
        svc, zip_data = self._run('l1', 'es', 12000)
        self.assertIsNotNone(zip_data)
        audio_texts = [t for (t, lang) in svc.audio_calls]
        joined = "\n".join(audio_texts)
        # Spoken notice NAMES the plans and was translated (marker present).
        self.assertIn('ten-dollar Pack', joined)
        self.assertIn('Curator', joined)
        self.assertIn('[es]', joined)
        # On-screen (HTML) full_text carries the translated notice + See plans.
        self.assertIsNotNone(svc.last_html_full_text)
        self.assertIn('[es]', svc.last_html_full_text)
        self.assertIn(at.SEE_PLANS_MARKER, svc.last_html_full_text)

    def test_top_plan_translated_maximum(self):
        svc, zip_data = self._run('admin', 'fr', 40000)
        audio_texts = [t for (t, lang) in svc.audio_calls]
        joined = "\n".join(audio_texts)
        self.assertIn('the maximum', joined)
        self.assertNotIn('Pack', joined.replace('[fr]', ''))
        self.assertIn('the maximum', svc.last_html_full_text)

    def test_fits_no_notice_no_spoken(self):
        svc, zip_data = self._run('l1', 'es', 1500)  # under 5,000 → no truncation
        audio_texts = [t for (t, lang) in svc.audio_calls]
        joined = "\n".join(audio_texts)
        self.assertNotIn('This article was shortened', joined)
        self.assertNotIn(at.SEE_PLANS_MARKER, svc.last_html_full_text or '')

    def test_english_target_notice_not_translated(self):
        svc, zip_data = self._run('l1', 'en', 12000)
        self.assertIn(at.SEE_PLANS_MARKER, svc.last_html_full_text)
        self.assertNotIn('[en]', svc.last_html_full_text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
