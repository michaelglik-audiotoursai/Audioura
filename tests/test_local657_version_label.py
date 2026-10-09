#!/usr/bin/env python3
"""test_local657_version_label.py — LOCAL-657.

Proves map-delivery exposes a tour's `version` and `updated_at` on the two list
endpoints the app's tour dialogs read (`/tours-near/<lat>/<lng>` and
`/tour-by-code/<code>`), so a replaced tour (LOCAL-606, same id + share code)
is visibly new in the app.

Why a FAKE DB and not the shared one
====================================
LOCAL-657 writes NO database rows (ticket). These tests therefore never touch
Postgres: `map_delivery.app.get_db_connection` is monkeypatched with a tiny
scripted cursor that returns exactly the rows the endpoint's SQL would, keyed
by a fragment of the query text. That keeps the test hermetic (runs with no
services up) while exercising the real endpoint code — the SELECT column order,
the `_version_fields` derivation, and the JSON the app consumes.

version      = COALESCE(MAX(version_no), 0) + 1 for the tour's own id
                 → 1 when the tour has never been replaced (no archive rows),
                   3 after two replacements (archived version_no 1 and 2).
updated_at   = newest replaced_at if ever replaced, else created_at, as an ISO
                 date (YYYY-MM-DD).
Translations carry THEIR OWN row's version (the join is on the resolved row id).
"""
import os
import sys
import datetime
import unittest

# map_delivery/ is not a package; put it on the path and import the Flask app.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MAPDIR = os.path.join(_ROOT, "map_delivery")
if _MAPDIR not in sys.path:
    sys.path.insert(0, _MAPDIR)

import app as map_app  # noqa: E402  (map_delivery/app.py)


class _FakeCursor:
    """A cursor that answers each execute() from a scripted plan.

    The plan is a list of (needle, result) pairs. On execute(sql, params) the
    first pair whose `needle` appears in the SQL (case-insensitive) is selected;
    its `result` is a list of rows. fetchone() pops the first row, fetchall()
    returns them all. This mirrors psycopg2's row tuples without a DB.
    """

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
    """Point the endpoint at a fake connection built from `plan`."""
    map_app.get_db_connection = lambda: _FakeConn(plan)


class VersionLabelTest(unittest.TestCase):
    def setUp(self):
        self._orig_db = map_app.get_db_connection
        self.client = map_app.app.test_client()

    def tearDown(self):
        map_app.get_db_connection = self._orig_db

    # ── /tours-near ────────────────────────────────────────────────────────
    # tours-near column order:
    # id, tour_name, request_string, lat, lng, number_requested,
    # content_language, original_tour_id, max_version_no, last_replaced_at,
    # created_at
    def test_tours_near_v1_when_no_archive_rows(self):
        """A never-replaced tour → version 1, updated_at = created_at date."""
        created = datetime.datetime(2026, 10, 1, 8, 30, 0)
        _install_db([
            ("from audio_tours t", [
                (557, "Old Town", "old town walk", 43.70, 7.26, 12,
                 "en", None, None, None, created),
            ]),
        ])
        resp = self.client.get("/tours-near/43.70/7.26?radius=50")
        self.assertEqual(resp.status_code, 200)
        tours = resp.get_json()["tours"]
        self.assertEqual(len(tours), 1)
        self.assertEqual(tours[0]["version"], 1)
        self.assertEqual(tours[0]["updated_at"], "2026-10-01")

    def test_tours_near_v3_after_two_replacements(self):
        """Two archived versions (max_version_no=2) → live row is version 3,
        updated_at = newest replaced_at date (not created_at)."""
        created = datetime.datetime(2026, 1, 1, 0, 0, 0)
        last_replaced = datetime.datetime(2026, 10, 9, 15, 42, 0)
        _install_db([
            ("from audio_tours t", [
                (557, "Old Town", "old town walk", 43.70, 7.26, 30,
                 "en", None, 2, last_replaced, created),
            ]),
        ])
        resp = self.client.get("/tours-near/43.70/7.26?radius=50")
        self.assertEqual(resp.status_code, 200)
        tours = resp.get_json()["tours"]
        self.assertEqual(tours[0]["version"], 3)
        self.assertEqual(tours[0]["updated_at"], "2026-10-09")

    # ── /tour-by-code ───────────────────────────────────────────────────────
    # tour-by-code first resolves the share code, then selects the row.
    # row order: id, tour_name, request_string, lat, lng, number_requested,
    # language, original_tour_id, max_version_no, last_replaced_at, created_at
    def test_tour_by_code_returns_version_ge_2_for_replaced_tour(self):
        """The live check's shape: q9oSUebU → tour 557, replaced once → v2."""
        created = datetime.datetime(2026, 1, 1, 0, 0, 0)
        last_replaced = datetime.datetime(2026, 10, 9, 12, 0, 0)
        _install_db([
            # share-code resolution: SELECT audio_tour_id FROM shared_tours ...
            ("from shared_tours", [(557,)]),
            # the row select (joined with the versions aggregate)
            ("from audio_tours t", [
                (557, "Old Town", "old town walk", 43.70, 7.26, 25,
                 "en", None, 1, last_replaced, created),
            ]),
        ])
        resp = self.client.get("/tour-by-code/q9oSUebU")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["count"], 1)
        tour = body["tours"][0]
        self.assertEqual(tour["id"], 557)
        self.assertGreaterEqual(tour["version"], 2)
        self.assertEqual(tour["version"], 2)
        self.assertEqual(tour["updated_at"], "2026-10-09")
        self.assertIsNone(tour["distance_km"])  # not location-based

    def test_tour_by_code_v1_for_never_replaced(self):
        """A share code to a fresh tour → version 1, updated_at = created_at."""
        created = datetime.datetime(2026, 9, 15, 9, 0, 0)
        _install_db([
            ("from shared_tours", [(900,)]),
            ("from audio_tours t", [
                (900, "Fresh Tour", "fresh", 48.85, 2.35, 3,
                 "en", None, None, None, created),
            ]),
        ])
        resp = self.client.get("/tour-by-code/freshcode")
        self.assertEqual(resp.status_code, 200)
        tour = resp.get_json()["tours"][0]
        self.assertEqual(tour["version"], 1)
        self.assertEqual(tour["updated_at"], "2026-09-15")

    def test_tour_by_code_translation_carries_own_version(self):
        """A share code that resolves to a TRANSLATION row (original_tour_id set)
        carries that translation row's own version — the join is on the resolved
        row id, so this is the version of the exact tour the listener downloads."""
        created = datetime.datetime(2026, 2, 1, 0, 0, 0)
        last_replaced = datetime.datetime(2026, 10, 8, 10, 0, 0)
        _install_db([
            ("from shared_tours", [(1201,)]),
            ("from audio_tours t", [
                # id=1201 is an ES translation of original 557; it has its own
                # single archived version (max_version_no=1 → live is v2).
                (1201, "Old Town [es]", "old town walk", 43.70, 7.26, 4,
                 "es", 557, 1, last_replaced, created),
            ]),
        ])
        resp = self.client.get("/tour-by-code/estrans")
        self.assertEqual(resp.status_code, 200)
        tour = resp.get_json()["tours"][0]
        self.assertEqual(tour["id"], 1201)
        self.assertEqual(tour["original_tour_id"], 557)
        self.assertEqual(tour["language"], "es")
        self.assertEqual(tour["version"], 2)           # its OWN version
        self.assertEqual(tour["updated_at"], "2026-10-08")

    # ── the _version_fields helper directly ─────────────────────────────────
    def test_version_fields_helper(self):
        created = datetime.datetime(2026, 10, 1, 8, 30, 0)
        replaced = datetime.datetime(2026, 10, 9, 15, 0, 0)

        # No archive rows → v1, updated_at = created_at.
        self.assertEqual(
            map_app._version_fields(None, None, created), (1, "2026-10-01"))
        # Two archived (max=2) → v3, updated_at = replaced_at (wins over created).
        self.assertEqual(
            map_app._version_fields(2, replaced, created), (3, "2026-10-09"))
        # A plain date object (not datetime) is handled.
        self.assertEqual(
            map_app._version_fields(0, None, datetime.date(2026, 7, 4)),
            (1, "2026-07-04"))
        # No timestamp at all → updated_at is None, still version 1.
        self.assertEqual(map_app._version_fields(None, None, None), (1, None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
