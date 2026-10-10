#!/usr/bin/env python3
"""test_local666_translation_source_version.py — LOCAL-666.

Proves a TRANSLATION carries its SOURCE tour's version (and the downloaded /
My-Tours copy shows it too), instead of the always-"v1" LOCAL-657 produced by
joining audio_tour_versions on the translation's own (never-replaced) id.

Two surfaces are exercised, both hermetically (a scripted fake DB cursor, no
Postgres, no services up — the tests write NO rows), driving the REAL code:

1. map-delivery (map_delivery/app.py): /tour-by-code and /tour-info report a
   translation row's version from its pinned `source_version` (else the SOURCE
   tour's live version), with the translation's own created_at as updated_at.

2. translation-service helpers (translation-service/translation_service.py):
   * _source_tour_version — the number pinned at translation time.
   * _translation_version_fields — the (version, updated_at) the
     /translate-with-audio response returns per language.

Cases required by the ticket:
  (a) translation inherits v10              → source_version=10 ⇒ version 10.
  (b) translation of an UNREPLACED tour = v1 → source has no archive, no pin
                                               ⇒ version 1 (app shows no label).
  (c) source_version column ABSENT → falls back to the source's live version
      (second grouped join on original_tour_id).
"""
import os
import sys
import datetime
import unittest

# map_delivery/ and translation-service/ are not packages; put them on the path.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MAPDIR = os.path.join(_ROOT, "map_delivery")
_TRDIR = os.path.join(_ROOT, "translation-service")
for _d in (_MAPDIR, _TRDIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

import app as map_app  # noqa: E402  (map_delivery/app.py)


class _FakeCursor:
    """Answers each execute() from a scripted plan of (needle, rows) pairs: the
    first pair whose needle appears (case-insensitively) in the normalised SQL
    wins. Mirrors psycopg2 tuples without a DB. The information_schema probe for
    the optional source_version column is just another needle, so a test decides
    'column present' vs 'absent' by including or omitting that pair."""

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


def _install_map_db(plan):
    map_app.get_db_connection = lambda: _FakeConn(plan)


# Column present / absent answers for the source_version schema probe.
_COL_PRESENT = ("information_schema", [("source_version",)])
_COL_ABSENT = ("information_schema", [])


class MapDeliveryTranslationVersionTest(unittest.TestCase):
    """map-delivery reports a translation's SOURCE version on /tour-by-code and
    /tour-info. Row/column order (13 cols):
    id, name, request_string, lat, lng, number_requested, language,
    original_tour_id, max_version_no, last_replaced_at, created_at,
    source_version, source_max_version_no.
    """

    def setUp(self):
        self._orig_db = map_app.get_db_connection
        map_app._HAS_SOURCE_VERSION = None  # reset cached schema probe
        self.client = map_app.app.test_client()

    def tearDown(self):
        map_app.get_db_connection = self._orig_db
        map_app._HAS_SOURCE_VERSION = None

    # ── (a) translation inherits v10 ─────────────────────────────────────────
    def test_tour_by_code_translation_inherits_source_v10(self):
        """Russian 615 of 557, regenerated for v10 → source_version=10 ⇒ the
        listener's Russian copy says v10, with its OWN created_at as updated."""
        created = datetime.datetime(2026, 10, 10, 9, 0, 0)
        _install_map_db([
            _COL_PRESENT,
            ("from shared_tours", [(615,)]),
            ("from audio_tours t", [
                # id=615 is the RU translation of 557; its own archive is empty
                # (never replaced in place) but source_version=10 is pinned.
                (615, "Прогулка [ru]", "boston politics walk", 42.36, -71.06, 7,
                 "ru", 557, None, None, created, 10, 9),
            ]),
        ])
        resp = self.client.get("/tour-by-code/ru615code")
        self.assertEqual(resp.status_code, 200)
        tour = resp.get_json()["tours"][0]
        self.assertEqual(tour["id"], 615)
        self.assertEqual(tour["original_tour_id"], 557)
        self.assertEqual(tour["language"], "ru")
        self.assertEqual(tour["version"], 10)          # SOURCE version, not v1
        self.assertEqual(tour["updated_at"], "2026-10-10")  # translation's own date

    def test_tour_info_translation_inherits_source_v10(self):
        """Same rule on /tour-info (which previously returned no version at all)."""
        created = datetime.datetime(2026, 10, 10, 9, 0, 0)
        _install_map_db([
            _COL_PRESENT,
            ("from audio_tours t", [
                (615, "Прогулка [ru]", "boston politics walk", 42.36, -71.06, 7,
                 "ru", 557, None, None, created, 10, 9),
            ]),
        ])
        resp = self.client.get("/tour-info/615")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["version"], 10)
        self.assertEqual(body["updated_at"], "2026-10-10")
        self.assertTrue(body["is_translation"])
        self.assertEqual(body["parent_tour_id"], 557)

    # ── (b) translation of an unreplaced source = v1 (no label) ──────────────
    def test_translation_of_unreplaced_source_is_v1(self):
        """Source 557 was NEVER replaced (no archive rows) and the translation was
        pinned at that time: source_version=1, source_max_version_no NULL ⇒ the
        translation is version 1 → the app renders no label (only shows >= 2)."""
        created = datetime.datetime(2026, 9, 1, 12, 0, 0)
        _install_map_db([
            _COL_PRESENT,
            ("from shared_tours", [(620,)]),
            ("from audio_tours t", [
                (620, "Promenade [fr]", "boston walk", 42.36, -71.06, 2,
                 "fr", 557, None, None, created, 1, None),
            ]),
        ])
        resp = self.client.get("/tour-by-code/fr620code")
        self.assertEqual(resp.status_code, 200)
        tour = resp.get_json()["tours"][0]
        self.assertEqual(tour["version"], 1)
        self.assertEqual(tour["updated_at"], "2026-09-01")

    def test_translation_with_no_pin_and_no_archive_is_v1(self):
        """A pre-666 translation (source_version NULL) of a source with no archive
        rows (source_max_version_no NULL) falls back to the source's live version,
        which is 1 → still no label. Proves the NULL-pin fallback path."""
        created = datetime.datetime(2026, 8, 15, 10, 0, 0)
        _install_map_db([
            _COL_PRESENT,
            ("from shared_tours", [(621,)]),
            ("from audio_tours t", [
                (621, "Tour [de]", "boston walk", 42.36, -71.06, 1,
                 "de", 557, None, None, created, None, None),
            ]),
        ])
        resp = self.client.get("/tour-by-code/de621code")
        self.assertEqual(resp.status_code, 200)
        tour = resp.get_json()["tours"][0]
        self.assertEqual(tour["version"], 1)

    # ── (c) source_version column absent → fall back to source's live version ─
    def test_column_absent_falls_back_to_source_live_version(self):
        """On an older schema the source_version column does not exist, so the
        SELECT emits NULL for it; the translation then takes the SOURCE tour's LIVE
        version from the second grouped join (source_max_version_no=9 ⇒ v10)."""
        created = datetime.datetime(2026, 10, 10, 9, 0, 0)
        _install_map_db([
            _COL_ABSENT,  # information_schema returns no row → column absent
            ("from shared_tours", [(615,)]),
            ("from audio_tours t", [
                # source_version comes back NULL (SELECTed as NULL::integer); the
                # source 557 has 9 archived versions so its live version is 10.
                (615, "Прогулка [ru]", "boston politics walk", 42.36, -71.06, 7,
                 "ru", 557, None, None, created, None, 9),
            ]),
        ])
        resp = self.client.get("/tour-by-code/ru615code")
        self.assertEqual(resp.status_code, 200)
        tour = resp.get_json()["tours"][0]
        self.assertEqual(tour["version"], 10)          # source's LIVE version
        self.assertEqual(tour["updated_at"], "2026-10-10")

    # ── an ORIGINAL row is unchanged (regression guard for LOCAL-657) ────────
    def test_original_row_unchanged(self):
        """An original (original_tour_id NULL) still derives its version from its
        OWN archive and uses replaced_at as updated_at — LOCAL-657 behaviour."""
        created = datetime.datetime(2026, 1, 1, 0, 0, 0)
        last_replaced = datetime.datetime(2026, 10, 9, 15, 0, 0)
        _install_map_db([
            _COL_PRESENT,
            ("from shared_tours", [(557,)]),
            ("from audio_tours t", [
                (557, "Boston", "boston walk", 42.36, -71.06, 40,
                 "en", None, 9, last_replaced, created, None, None),
            ]),
        ])
        resp = self.client.get("/tour-by-code/boston")
        self.assertEqual(resp.status_code, 200)
        tour = resp.get_json()["tours"][0]
        self.assertEqual(tour["version"], 10)          # 9 archived + 1
        self.assertEqual(tour["updated_at"], "2026-10-09")  # replaced_at, not created


class MapDeliveryHelperTest(unittest.TestCase):
    """_resolved_version_fields directly — the shared derivation."""

    def test_original_delegates_to_version_fields(self):
        created = datetime.datetime(2026, 10, 1, 8, 30, 0)
        replaced = datetime.datetime(2026, 10, 9, 15, 0, 0)
        # original (original_tour_id None): 2 archived → v3, updated = replaced_at.
        self.assertEqual(
            map_app._resolved_version_fields(None, None, None, 2, replaced, created),
            (3, "2026-10-09"))

    def test_translation_uses_pinned_source_version(self):
        created = datetime.datetime(2026, 10, 10, 9, 0, 0)
        # pinned source_version=10 wins; updated = translation's created_at.
        self.assertEqual(
            map_app._resolved_version_fields(557, 10, 9, None, None, created),
            (10, "2026-10-10"))

    def test_translation_falls_back_to_source_live_version(self):
        created = datetime.datetime(2026, 10, 10, 9, 0, 0)
        # no pin → source_max_version_no=9 ⇒ v10.
        self.assertEqual(
            map_app._resolved_version_fields(557, None, 9, None, None, created),
            (10, "2026-10-10"))

    def test_translation_v1_when_source_unreplaced(self):
        created = datetime.datetime(2026, 9, 1, 0, 0, 0)
        self.assertEqual(
            map_app._resolved_version_fields(557, None, None, None, None, created),
            (1, "2026-09-01"))


class _TrFakeCursor(_FakeCursor):
    """Same scripted cursor, reused for the translation-service helper tests."""


class TranslationServiceHelperTest(unittest.TestCase):
    """translation-service helpers that pin and read the source version. These do
    not need the Flask app or boto3 — we build a bare instance via __new__ to call
    the pure DB helpers with a fake cursor."""

    @classmethod
    def setUpClass(cls):
        # translation_service.py imports boto3 at module top and constructs a
        # TranslationService() at import (which calls boto3.client). boto3 is only
        # present inside the service container, not on this host, so stub it with a
        # minimal fake before import. The helpers under test never touch boto3.
        import types
        if "boto3" not in sys.modules:
            _boto3 = types.ModuleType("boto3")
            _boto3.client = lambda *a, **k: object()
            sys.modules["boto3"] = _boto3
        import translation_service as tr
        cls.tr = tr
        # Avoid TranslationService.__init__ (boto3 clients); we only call methods
        # that take a cursor and read module-level helpers.
        cls.svc = tr.TranslationService.__new__(tr.TranslationService)

    def test_source_tour_version_counts_archive(self):
        # COALESCE(MAX(version_no),0)+1: 9 archived → 10.
        cur = _TrFakeCursor([("from audio_tour_versions", [(10,)])])
        self.assertEqual(self.svc._source_tour_version(cur, 557), 10)

    def test_source_tour_version_unreplaced_is_1(self):
        # No archive rows → COALESCE(...,0)+1 = 1.
        cur = _TrFakeCursor([("from audio_tour_versions", [(1,)])])
        self.assertEqual(self.svc._source_tour_version(cur, 557), 1)

    def test_ensure_source_version_column_present(self):
        cur = _TrFakeCursor([("information_schema", [("source_version",)])])
        self.assertTrue(self.svc._ensure_source_version_column(cur))

    def test_translation_version_fields_uses_pin(self):
        created = datetime.datetime(2026, 10, 10, 9, 0, 0)
        conn = _FakeConn([
            ("information_schema", [("source_version",)]),
            # SELECT original_tour_id, source_version, created_at FROM audio_tours
            ("from audio_tours", [(557, 10, created)]),
        ])
        version, updated_at = self.tr._translation_version_fields(conn, 615)
        self.assertEqual(version, 10)
        self.assertEqual(updated_at, "2026-10-10")

    def test_translation_version_fields_fallback_to_source_live(self):
        created = datetime.datetime(2026, 10, 10, 9, 0, 0)
        conn = _FakeConn([
            ("information_schema", [("source_version",)]),
            # source_version NULL on the row → fall back to source live version.
            ("from audio_tours", [(557, None, created)]),
            ("from audio_tour_versions", [(10,)]),  # source live version = 10
        ])
        version, updated_at = self.tr._translation_version_fields(conn, 615)
        self.assertEqual(version, 10)
        self.assertEqual(updated_at, "2026-10-10")


if __name__ == "__main__":
    unittest.main(verbosity=2)
