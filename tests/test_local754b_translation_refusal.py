#!/usr/bin/env python3
"""test_local754b_translation_refusal.py — LOCAL-754B / D708 (RED first).

Translation of organiser audio is NOT offered (D708): the organiser links audio
Audioura never stored and never had the text for, so there is nothing to
translate. The translation service must REFUSE a translate request for a tour
whose audio_tours.source_kind = 'organiser_audio' with 403 translation_not_offered,
and ALLOW a generated tour (source_kind NULL) through its normal path.

Hermetic: patches translation_service.get_db_connection with a fake connection
whose source_kind the test controls, and the per-language translate function so
no real translation runs. Fails on 027584b0 (no gate exists there).

Run: python3 -m pytest tests/test_local754b_translation_refusal.py -q
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_TS = os.path.join(_ROOT, "translation-service")
for p in (_TS, _ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import translation_service as ts  # noqa: E402  (translation-service/)


class _FakeCursor:
    def __init__(self, source_kind):
        self._source_kind = source_kind
        self._rows = []

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split()).lower()
        if 'source_kind' in text:
            self._rows = [(self._source_kind,)]
        else:
            self._rows = []

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        pass


class _FakeConn:
    def __init__(self, source_kind):
        self._source_kind = source_kind

    def cursor(self):
        return _FakeCursor(self._source_kind)

    def close(self):
        pass


class TranslationRefusalTest(unittest.TestCase):
    def setUp(self):
        self.app = ts.app.test_client()
        self._orig_db = ts.translation_service.get_db_connection
        self._orig_tr = ts.translation_service.translate_tour_with_audio

    def tearDown(self):
        ts.translation_service.get_db_connection = self._orig_db
        ts.translation_service.translate_tour_with_audio = self._orig_tr

    def _install(self, source_kind):
        ts.translation_service.get_db_connection = lambda: _FakeConn(source_kind)
        # Guard: a translation must NOT actually run for an organiser-audio tour.
        def _should_not_run(*a, **k):
            raise AssertionError("translate_tour_with_audio ran for a refused tour")
        ts.translation_service.translate_tour_with_audio = _should_not_run

    def test_organiser_audio_refused_403(self):
        self._install('organiser_audio')
        r = self.app.post('/translate-with-audio', json={
            'content_id': 99, 'content_type': 'tour', 'languages': ['es'],
        })
        self.assertEqual(r.status_code, 403, r.get_data(as_text=True))
        self.assertEqual(r.get_json().get('error_code'), 'translation_not_offered')

    def test_generated_tour_allowed_through(self):
        # Generated tour → source_kind NULL → the gate lets it reach the normal
        # path. We stub the translate function to a benign success so no real
        # work happens but the gate is proven NOT to refuse.
        ts.translation_service.get_db_connection = lambda: _FakeConn(None)
        ts.translation_service.translate_tour_with_audio = \
            lambda cid, lang, **k: (1234, False)
        r = self.app.post('/translate-with-audio', json={
            'content_id': 42, 'content_type': 'tour', 'languages': ['es'],
        })
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertNotEqual(r.get_json().get('error_code'),
                            'translation_not_offered')


if __name__ == '__main__':
    unittest.main(verbosity=2)
