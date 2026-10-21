#!/usr/bin/env python3
"""test_local724b_store_holds_unratable.py — LOCAL-724B defect 2 (store path).

Proves END TO END, through the REAL orchestrator store_audio_tour writing to a
throwaway Postgres schema, that a NEW original tour the rater CANNOT rate is
HELD — content_rating NULL, review_status 'pending' — so it is NOT listable,
instead of being committed unrated (which reads as general and lists).

No paid API call: tour_content_rating.rate_tour_row is monkeypatched to return
None (exactly what "no OPENAI_API_KEY in the container / model error" produces),
which is the trigger for the hold. We then assert the stored row is held and run
the REAL listing predicate map_delivery.app._content_visible over it.

Isolation mirrors tests/test_local606_replace_on_change.py: a cloned schema
(prefix t724b) that teardown DROPs, with public row counts asserted unchanged.
If the dev Postgres is not reachable the whole case skips (the hermetic
contract test in tests/test_local724_content_policy_truth.py still covers the
same rule without a DB).
"""
import os
import sys
import tempfile
import unittest
import uuid
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MAPDIR = os.path.join(_ROOT, "map_delivery")
for _p in (_HERE, _ROOT, _MAPDIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from db_connection import get_db_config  # noqa: E402

# Pin the orchestrator's internal psycopg2 connection at the SAME DB the
# isolated schema uses, BEFORE importing it (identical to LOCAL-606).
_CFG = get_db_config()
os.environ["DB_HOST"] = _CFG["host"]
os.environ["DB_PORT"] = str(_CFG["port"])
os.environ["DB_NAME"] = _CFG["dbname"]
os.environ["DB_USER"] = _CFG["user"]
os.environ["DB_PASSWORD"] = _CFG["password"]

from _isolated_db import IsolatedSchema  # noqa: E402
import tour_orchestrator_service as orch  # noqa: E402
import tour_content_rating  # noqa: E402
import app as map_app  # noqa: E402  (map_delivery/app.py)
import psycopg2  # noqa: E402

_ISO = IsolatedSchema(
    prefix="t724b",
    clone_tables=["audio_tours"],
    proof_tables=["audio_tours"],
    banner="LOCAL-724B",
)


def setUpModule():
    _ISO.setup()


def tearDownModule():
    _ISO.teardown()


def _schema_connect():
    return psycopg2.connect(
        host=_CFG["host"], port=_CFG["port"], dbname=_CFG["dbname"],
        user=_CFG["user"], password=_CFG["password"], connect_timeout=5,
    )


def _make_zip(path, payload=b"stop-audio"):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("tour.mp3", payload)


@unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
class StoreHoldsUnratableTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="local724b_tours_")
        self._orig_tours_dir = orch.TOURS_DIR
        orch.TOURS_DIR = self._tmp
        self.tour_name = f"LOCAL724B Venue {uuid.uuid4().hex[:8]}"
        # Simulate "the rater cannot rate" (no key / model error) WITHOUT any
        # paid call: rate_tour_row returns None. This is the exact trigger the
        # store's new-tour path must respond to by holding the row.
        self._orig_rate = tour_content_rating.rate_tour_row
        tour_content_rating.rate_tour_row = lambda *a, **k: None

    def tearDown(self):
        orch.TOURS_DIR = self._orig_tours_dir
        tour_content_rating.rate_tour_row = self._orig_rate

    def _store_real_tour(self):
        zip_path = os.path.join(self._tmp, "venue.zip")
        _make_zip(zip_path)
        # is_test MUST be False so the serving-path rater runs (test rows skip it).
        return orch.store_audio_tour(
            self.tour_name, "req:" + self.tour_name, zip_path,
            lat=42.3601, lng=-71.0589,  # real, usable coords -> a listable row
            tour_content="A long real tour. " * 40,  # > 200 chars
            stops_count=4, is_test=False, job_id="job-724b",
        )

    def _held_columns(self, tour_id):
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT content_rating, review_status FROM audio_tours WHERE id=%s",
                (tour_id,))
            return cur.fetchone()
        finally:
            conn.close()

    def test_unratable_new_tour_is_held_and_not_listable(self):
        res = self._store_real_tour()
        self.assertTrue(res["success"], res)
        self.assertEqual(res["action"], "inserted")

        # Read the stored row's id.
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM audio_tours WHERE lower(tour_name)=lower(%s) "
                "AND original_tour_id IS NULL", (self.tour_name,))
            row = cur.fetchone()
            self.assertIsNotNone(row, "tour was not stored")
            tour_id = row[0]
        finally:
            conn.close()

        rating, status = self._held_columns(tour_id)
        # Defect 2: the unratable new tour is HELD, not left unrated-general.
        self.assertIsNone(rating, "held tour must have NULL content_rating")
        self.assertEqual(status, "pending",
                         "an unratable new tour must be held (review_status pending)")
        # And through the REAL listing predicate it is NOT listable.
        self.assertFalse(map_app._content_visible(rating, status, False),
                         "a held new tour must not be listable")
        self.assertFalse(map_app._content_visible(rating, status, True))


if __name__ == "__main__":
    unittest.main()
