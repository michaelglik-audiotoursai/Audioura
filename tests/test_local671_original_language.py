#!/usr/bin/env python3
"""test_local671_original_language.py — LOCAL-671.

Proves map-delivery carries `original_language` on every tour element so the
app's tour dialogs can show "Original: <Language name>" (D648). The rule:

  * ORIGINAL row (original_tour_id NULL): original_language == its OWN
    content_language (the language it was written in).
  * TRANSLATION row (original_tour_id set): original_language == the ORIGINAL
    tour's content_language, reached by a self-LEFT-JOIN on original_tour_id —
    NOT the translation's own language ('ru', 'fr', …).
  * Unknown on either side → defaults to 'en' (never a blank "Original:").

Hermetic: a scripted fake DB cursor (no Postgres, no services, writes NO rows)
drives the REAL endpoint code. Row/column order is the 17-column shape after
LOCAL-671 appended own_content_language + source_content_language as the final
two SELECTed columns:

  id, name, request_string, lat, lng, number_requested,
  (content_)language, original_tour_id, max_version_no, last_replaced_at,
  created_at, source_version, source_max_version_no, rating_count,
  rating_values, own_content_language, source_content_language

All four endpoints are exercised: /tours-near, /tour-by-code, /tour-info,
/search-tours — the first is originals-only, the other three surface
translations.
"""
import os
import sys
import datetime
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MAPDIR = os.path.join(_ROOT, "map_delivery")
if _MAPDIR not in sys.path:
    sys.path.insert(0, _MAPDIR)

import app as map_app  # noqa: E402  (map_delivery/app.py)


class _FakeCursor:
    """Answers each execute() from a scripted plan of (needle, rows) pairs: the
    first pair whose needle appears (case-insensitively) in the normalised SQL
    wins. Mirrors psycopg2 tuples without a DB."""

    def __init__(self, plan):
        self._plan = plan
        self._rows = []

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split()).lower()
        for needle, result in self._plan:
            if needle.lower() in text:
                self._rows = list(result)
                return
        self._rows = []

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        pass


class _FakeConn:
    def __init__(self, plan):
        self._plan = plan

    def cursor(self):
        return _FakeCursor(self._plan)

    def commit(self):
        pass

    def close(self):
        pass


def _install_db(plan):
    map_app.get_db_connection = lambda: _FakeConn(plan)


_COL_PRESENT = ("information_schema", [("source_version",)])


class OriginalLanguageTest(unittest.TestCase):
    def setUp(self):
        self._orig_db = map_app.get_db_connection
        map_app._HAS_SOURCE_VERSION = None
        self.client = map_app.app.test_client()

    def tearDown(self):
        map_app.get_db_connection = self._orig_db
        map_app._HAS_SOURCE_VERSION = None

    # ── /tours-near: an ORIGINAL reports its own content_language ────────────
    def test_tours_near_original_reports_own_language(self):
        """An English original: own content_language 'en', no source row
        (source_content_language NULL) ⇒ original_language 'en'."""
        created = datetime.datetime(2026, 10, 1, 8, 30, 0)
        _install_db([
            _COL_PRESENT,
            ("from audio_tours t", [
                (557, "Old Town", "old town walk", 43.70, 7.26, 12,
                 "en", None, None, None, created, None, None, None, None,
                 "en", None),
            ]),
        ])
        resp = self.client.get("/tours-near/43.70/7.26?radius=50")
        self.assertEqual(resp.status_code, 200)
        tour = resp.get_json()["tours"][0]
        self.assertEqual(tour["original_language"], "en")

    def test_tours_near_non_english_original_reports_its_own_language(self):
        """A non-English ORIGINAL (written in French, no original_tour_id) reports
        'fr' — the original_language is the row's OWN language, not a hardcoded
        'en'. /tours-near normally filters to en/NULL, but the field derivation is
        language-agnostic, which this proves directly."""
        created = datetime.datetime(2026, 10, 1, 8, 30, 0)
        _install_db([
            _COL_PRESENT,
            ("from audio_tours t", [
                (700, "Vieux Nice", "vieux nice", 43.70, 7.26, 5,
                 "fr", None, None, None, created, None, None, None, None,
                 "fr", None),
            ]),
        ])
        resp = self.client.get("/tours-near/43.70/7.26?radius=50")
        self.assertEqual(resp.status_code, 200)
        tour = resp.get_json()["tours"][0]
        self.assertEqual(tour["original_language"], "fr")

    # ── /tour-by-code: a TRANSLATION reports its SOURCE's language ───────────
    def test_tour_by_code_translation_reports_source_language(self):
        """Russian 615 of English original 557: own language 'ru', source language
        'en' ⇒ original_language 'en' (NOT 'ru')."""
        created = datetime.datetime(2026, 10, 10, 9, 0, 0)
        _install_db([
            _COL_PRESENT,
            ("from shared_tours", [(615,)]),
            ("from audio_tours t", [
                (615, "Прогулка [ru]", "boston politics walk", 42.36, -71.06, 7,
                 "ru", 557, None, None, created, 10, 9, None, None, "ru", "en"),
            ]),
        ])
        resp = self.client.get("/tour-by-code/ru615code")
        self.assertEqual(resp.status_code, 200)
        tour = resp.get_json()["tours"][0]
        self.assertEqual(tour["language"], "ru")
        self.assertEqual(tour["original_language"], "en")

    def test_tour_by_code_original_reports_own_language(self):
        """A share code to an English original ⇒ original_language 'en'."""
        created = datetime.datetime(2026, 9, 15, 9, 0, 0)
        _install_db([
            _COL_PRESENT,
            ("from shared_tours", [(900,)]),
            ("from audio_tours t", [
                (900, "Fresh Tour", "fresh", 48.85, 2.35, 3,
                 "en", None, None, None, created, None, None, None, None,
                 "en", None),
            ]),
        ])
        resp = self.client.get("/tour-by-code/freshcode")
        self.assertEqual(resp.status_code, 200)
        tour = resp.get_json()["tours"][0]
        self.assertEqual(tour["original_language"], "en")

    # ── /tour-info: translation + original ───────────────────────────────────
    def test_tour_info_translation_reports_source_language(self):
        created = datetime.datetime(2026, 10, 10, 9, 0, 0)
        _install_db([
            _COL_PRESENT,
            ("from audio_tours t", [
                (615, "Прогулка [ru]", "boston politics walk", 42.36, -71.06, 7,
                 "ru", 557, None, None, created, 10, 9, None, None, "ru", "en"),
            ]),
        ])
        resp = self.client.get("/tour-info/615")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["is_translation"])
        self.assertEqual(body["original_language"], "en")

    def test_tour_info_original_reports_own_language(self):
        created = datetime.datetime(2026, 1, 1, 0, 0, 0)
        _install_db([
            _COL_PRESENT,
            ("from audio_tours t", [
                (557, "Boston", "boston walk", 42.36, -71.06, 40,
                 "en", None, None, None, created, None, None, None, None,
                 "en", None),
            ]),
        ])
        resp = self.client.get("/tour-info/557")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertFalse(body["is_translation"])
        self.assertEqual(body["original_language"], "en")

    # ── /search-tours: translation + original in one result set ──────────────
    def test_search_tours_carries_original_language(self):
        """Search surfaces both. The German translation of English 557 reports
        'en'; the English original reports 'en'. A translation's own language is
        NOT what we show as the original."""
        created = datetime.datetime(2026, 10, 8, 10, 0, 0)
        _install_db([
            _COL_PRESENT,
            ("from audio_tours t", [
                # German translation of 557 (English original).
                (621, "Boston [de]", "boston walk", 42.36, -71.06, 4,
                 "de", 557, None, None, created, 1, None, None, None, "de", "en"),
                # The English original itself.
                (557, "Boston", "boston walk", 42.36, -71.06, 40,
                 "en", None, None, None, created, None, None, None, None,
                 "en", None),
            ]),
        ])
        resp = self.client.get("/search-tours?pattern=boston&lat=42.36&lng=-71.06")
        self.assertEqual(resp.status_code, 200)
        results = {r["id"]: r for r in resp.get_json()["tours"]}
        self.assertEqual(results[621]["language"], "de")
        self.assertEqual(results[621]["original_language"], "en")  # source lang
        self.assertEqual(results[557]["original_language"], "en")  # own lang

    # ── unknown language defaults to 'en' (never blank) ──────────────────────
    def test_translation_with_null_source_language_defaults_to_en(self):
        """A legacy original with NULL content_language (predates the column
        default): the translation's source_content_language is NULL ⇒ we fall back
        to 'en' rather than emitting null/blank."""
        created = datetime.datetime(2026, 10, 10, 9, 0, 0)
        _install_db([
            _COL_PRESENT,
            ("from shared_tours", [(615,)]),
            ("from audio_tours t", [
                (615, "Прогулка [ru]", "boston politics walk", 42.36, -71.06, 7,
                 "ru", 557, None, None, created, 10, 9, None, None, "ru", None),
            ]),
        ])
        resp = self.client.get("/tour-by-code/ru615code")
        self.assertEqual(resp.status_code, 200)
        tour = resp.get_json()["tours"][0]
        self.assertEqual(tour["original_language"], "en")


class ResolvedOriginalLanguageHelperTest(unittest.TestCase):
    """_resolved_original_language directly — the shared derivation."""

    def test_original_uses_own_language(self):
        self.assertEqual(
            map_app._resolved_original_language("en", None, None), "en")
        self.assertEqual(
            map_app._resolved_original_language("fr", None, None), "fr")

    def test_translation_uses_source_language(self):
        # Own language 'ru' is IGNORED; the source's 'en' wins.
        self.assertEqual(
            map_app._resolved_original_language("ru", 557, "en"), "en")

    def test_null_defaults_to_en(self):
        # Original with NULL own language.
        self.assertEqual(
            map_app._resolved_original_language(None, None, None), "en")
        # Translation with NULL source language.
        self.assertEqual(
            map_app._resolved_original_language("ru", 557, None), "en")


if __name__ == "__main__":
    unittest.main(verbosity=2)
