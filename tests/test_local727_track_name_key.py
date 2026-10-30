#!/usr/bin/env python3
"""test_local727_track_name_key.py — LOCAL-727 (ClickUp wdvrdaz108, bug 432).

Proves "two tracks, same tour name → never one merged row". On GCloud a Beta
tour and a Storied/Preview tour with byte-identical names, same creator (or both
NULL creator), generated ~1 s apart COLLAPSED into ONE audio_tours row with
mixed columns: the Storied store matched the Beta row through a track-UNAWARE
lookup and REPLACED it (archiving + mixing), so the Beta tour vanished while the
job reported success (432).

Decision point under test (tour_orchestrator_service.store_audio_tour):
    SELECT id, tour_content, zip_filename, stops_count, lat, lng
    FROM audio_tours
    WHERE lower(tour_name) = lower(%s) AND creator_user_id = %s
      AND original_tour_id IS NULL
This single SELECT decides new-row-vs-update. D678/041 made it creator-scoped
but it does NOT include `track`. `track` is per-DEPLOYMENT (TOUR_TRACK env var):
Beta and Storied are separate Cloud Run services writing their own value into
the SAME shared GCloud DB. So same (NON-NULL) creator + same name + different
track still collapses: the second track's store matches the first track's row
and replaces it. (A NULL creator is already safe — `creator_user_id = NULL`
matches no row — so the collapse requires a shared non-NULL creator.)

The fix makes the lookup key include `track` (keeping the creator scoping), so a
different track always INSERTs its own row.

Isolation: everything runs inside a throwaway Postgres schema
(tests/_isolated_db.py). Teardown DROPs the schema and asserts public row counts
are identical before and after — no shared/production row is ever written. There
is NO DELETE anywhere.

Running the two tracks: the unfixed code reads the track ONLY from the
TOUR_TRACK env var inside store_audio_tour, so this test sets TOUR_TRACK around
each call to simulate the two deployments. If the fix also threads an explicit
`track=` parameter, the test passes it too (the env is left as a belt-and-braces
fallback). Either way the assertions are on the resulting rows.

RED (unfixed): the two stores produce ONE row — test_two_tracks_two_rows fails
  with len(rows) == 1.
GREEN (fixed): two rows, one per track, each with its own storied_mode, lat/lng,
  stops_count, zip_filename; the first (Beta) row is byte-for-byte unchanged.
"""
import inspect
import os
import sys
import unittest
import uuid
import zipfile
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from db_connection import get_db_config  # noqa: E402

_CFG = get_db_config()
os.environ["DB_HOST"] = _CFG["host"]
os.environ["DB_PORT"] = str(_CFG["port"])
os.environ["DB_NAME"] = _CFG["dbname"]
os.environ["DB_USER"] = _CFG["user"]
os.environ["DB_PASSWORD"] = _CFG["password"]

from _isolated_db import IsolatedSchema  # noqa: E402
import tour_orchestrator_service as orch  # noqa: E402
import psycopg2  # noqa: E402

# Migration 043 (LOCAL-727) for the idempotency test.
_MIGRATION_043 = os.path.join(_ROOT, "migration", "sql", "043_tour_track.sql")

# Does store_audio_tour accept an explicit `track=` kwarg (post-fix)?
_STORE_ACCEPTS_TRACK = "track" in inspect.signature(orch.store_audio_tour).parameters

_ISO = IsolatedSchema(
    prefix="t727",
    clone_tables=["audio_tours", "audio_tour_versions", "shared_tours"],
    proof_tables=["audio_tours", "audio_tour_versions", "shared_tours"],
    banner="LOCAL-727",
)


def _schema_connect():
    """Connection honouring PGOPTIONS (search_path = throwaway schema)."""
    return psycopg2.connect(
        host=_CFG["host"], port=_CFG["port"], dbname=_CFG["dbname"],
        user=_CFG["user"], password=_CFG["password"], connect_timeout=5,
    )


def setUpModule():
    _ISO.setup()
    if _ISO.schema is None:
        return
    conn = _schema_connect()
    try:
        cur = conn.cursor()
        # Drop every UNIQUE index on lower(tour_name) carried by the clone
        # (LIKE ... INCLUDING ALL) — exactly what migration 041 does — so two
        # tracks' same-name rows can coexist. The track collapse this test
        # targets is NOT caused by that unique index (the lookup replaces the
        # row before any insert), but dropping it keeps the schema faithful to
        # production post-041 and lets a fixed INSERT store the second row.
        cur.execute(
            """
            SELECT indexname FROM pg_indexes
            WHERE schemaname = %s AND tablename = 'audio_tours'
              AND indexdef ILIKE '%%unique%%'
              AND indexdef ILIKE '%%lower%%tour_name%%'
            """,
            (_ISO.schema,),
        )
        for (idxname,) in cur.fetchall():
            cur.execute(f'DROP INDEX IF EXISTS "{_ISO.schema}"."{idxname}"')
        # creator_user_id is self-healed by the orchestrator on first store;
        # add it up front so the pre-store asserts can read it.
        cur.execute("ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS creator_user_id TEXT")
        # Rebuild audio_tour_versions from the orchestrator's own DDL so the
        # replace path's archive INSERT matches (same as the 718 test).
        cur.execute(f'DROP TABLE IF EXISTS "{_ISO.schema}".audio_tour_versions CASCADE')
        conn.commit()
        orch._ensure_versioning_objects(cur)
        conn.commit()
    finally:
        conn.close()


def tearDownModule():
    _ISO.teardown()


def _make_zip(path, payload=b"stop-audio"):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("tour.mp3", payload)


@unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
class TrackNameKeyTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="local727_tours_")
        self._orig_tours_dir = orch.TOURS_DIR
        orch.TOURS_DIR = self._tmp
        self._prev_track = os.environ.get("TOUR_TRACK")
        self._prev_storied = os.environ.get("STORIED_MODE")
        # Unique name per test to avoid cross-test collisions in the schema.
        self.tour_name = f"LOCAL727 Venue {uuid.uuid4().hex[:8]}"
        self.creator = f"creator-{uuid.uuid4().hex[:8]}"

    def tearDown(self):
        orch.TOURS_DIR = self._orig_tours_dir
        for key, val in (("TOUR_TRACK", self._prev_track),
                         ("STORIED_MODE", self._prev_storied)):
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    # ── helpers ───────────────────────────────────────────────────────────
    def _store(self, *, track, user_id, tour_content, zip_name, payload,
               storied_mode=False, stops_count=4, lat=None, lng=None,
               is_test=True, job_id=None):
        """Store a tour as if the given deployment track produced it.

        The unfixed code reads the track from TOUR_TRACK; a fixed code may also
        accept an explicit track= kwarg. We set both so the test works before
        and after the fix. storied_mode is read from STORIED_MODE env on insert.
        """
        zip_path = os.path.join(self._tmp, zip_name)
        _make_zip(zip_path, payload)
        os.environ["TOUR_TRACK"] = track
        os.environ["STORIED_MODE"] = "true" if storied_mode else "false"
        kwargs = dict(
            tour_content=tour_content, stops_count=stops_count,
            is_test=is_test, job_id=job_id or ("job-" + uuid.uuid4().hex[:8]),
            user_id=user_id,
        )
        if _STORE_ACCEPTS_TRACK:
            kwargs["track"] = track
        return orch.store_audio_tour(
            self.tour_name, "req:" + self.tour_name, zip_path, lat, lng, **kwargs
        )

    def _rows_for_name(self):
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, creator_user_id, track, storied_mode, tour_content, "
                "zip_filename, stops_count, lat, lng, number_requested "
                "FROM audio_tours "
                "WHERE lower(tour_name)=lower(%s) AND original_tour_id IS NULL "
                "ORDER BY id",
                (self.tour_name,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        finally:
            conn.close()

    # ── 1. two tracks, same name, same creator → TWO rows (the 432 fix) ─────
    def test_two_tracks_same_creator_two_rows(self):
        # Beta deployment stores first.
        r_beta = self._store(
            track="beta", user_id=self.creator,
            tour_content="Beta track content.", zip_name="beta.zip",
            payload=b"beta-zip", storied_mode=False,
            stops_count=4, lat=42.1, lng=-71.1)
        self.assertTrue(r_beta["success"])
        self.assertEqual(r_beta["action"], "inserted")

        rows_after_beta = self._rows_for_name()
        self.assertEqual(len(rows_after_beta), 1)
        beta_id = rows_after_beta[0]["id"]
        beta_row = rows_after_beta[0]

        # Storied deployment stores the byte-identical NAME ~1 s later, same
        # creator, DIFFERENT track + storied_mode + coordinates + stops.
        r_storied = self._store(
            track="storied", user_id=self.creator,
            tour_content="Storied track content.", zip_name="storied.zip",
            payload=b"storied-zip", storied_mode=True,
            stops_count=7, lat=48.8, lng=2.3)
        self.assertTrue(r_storied["success"])
        # The storied store must NOT have replaced the beta row.
        self.assertEqual(
            r_storied["action"], "inserted",
            "Storied track must get its OWN new row, not replace the Beta row")
        self.assertIsNone(r_storied["replaced_version_no"])

        rows = self._rows_for_name()
        # THE 432 ASSERTION: two separate rows, one per track (RED on unfixed:
        # the track-unaware lookup matched the beta row and replaced it → 1 row).
        self.assertEqual(
            len(rows), 2,
            f"Expected TWO rows (one per track); got {len(rows)} — the Beta and "
            f"Storied tours collapsed into one (bug 432).")

        by_track = {row["track"]: row for row in rows}
        self.assertIn("beta", by_track, "beta row present")
        self.assertIn("storied", by_track, "storied row present")

        # Each row carries its OWN columns (no mixing).
        self.assertEqual(by_track["beta"]["id"], beta_id, "beta row keeps its id")
        self.assertEqual(by_track["beta"]["tour_content"], "Beta track content.")
        self.assertEqual(by_track["beta"]["storied_mode"], False)
        self.assertEqual(by_track["beta"]["stops_count"], 4)
        self.assertAlmostEqual(by_track["beta"]["lat"], 42.1)
        self.assertAlmostEqual(by_track["beta"]["lng"], -71.1)

        self.assertEqual(by_track["storied"]["tour_content"], "Storied track content.")
        self.assertEqual(by_track["storied"]["storied_mode"], True)
        self.assertEqual(by_track["storied"]["stops_count"], 7)
        self.assertAlmostEqual(by_track["storied"]["lat"], 48.8)
        self.assertAlmostEqual(by_track["storied"]["lng"], 2.3)

        # The Beta row is byte-for-byte unchanged (nothing archived, no column
        # mixing, number_requested not bumped by the storied store).
        self.assertEqual(by_track["beta"]["zip_filename"], beta_row["zip_filename"])
        self.assertEqual(by_track["beta"]["number_requested"],
                         beta_row["number_requested"],
                         "Beta row's number_requested untouched by the storied store")

    # ── 2. two tracks, BOTH NULL creator → TWO rows (guard) ─────────────────
    #       NOTE: a NULL creator is ALREADY safe pre-fix — the lookup
    #       `creator_user_id = %s` with a NULL param matches no row (SQL
    #       `NULL = NULL` is unknown), so each NULL-creator store always INSERTs.
    #       The real collapse needs a shared NON-NULL creator (test 1). This
    #       test guards that the track key does not regress the NULL case.
    def test_two_tracks_null_creator_two_rows(self):
        self._store(track="beta", user_id=None,
                    tour_content="Beta null-creator.", zip_name="bn.zip",
                    payload=b"bn", storied_mode=False)
        r = self._store(track="storied", user_id=None,
                        tour_content="Storied null-creator.", zip_name="sn.zip",
                        payload=b"sn", storied_mode=True)
        self.assertEqual(
            r["action"], "inserted",
            "A different track with NULL creator must still get its OWN row")
        rows = self._rows_for_name()
        self.assertEqual(
            len(rows), 2,
            f"NULL-creator Beta and Storied must be two rows; got {len(rows)}.")
        self.assertEqual({row["track"] for row in rows}, {"beta", "storied"})

    # ── 3. SAME track, same creator, text differs → still ONE row (versioned)
    #       The track key must NOT break the legitimate same-track versioning.
    def test_same_track_same_creator_versions_one_row(self):
        self._store(track="beta", user_id=self.creator,
                    tour_content="Beta v1.", zip_name="v1.zip", payload=b"v1")
        rows1 = self._rows_for_name()
        self.assertEqual(len(rows1), 1)
        beta_id = rows1[0]["id"]

        r2 = self._store(track="beta", user_id=self.creator,
                         tour_content="Beta v2 improved.", zip_name="v2.zip",
                         payload=b"v2")
        self.assertEqual(
            r2["action"], "replaced",
            "Same track + same creator + changed text must VERSION the same row")
        self.assertEqual(r2["existing_tour_id"], beta_id)
        rows2 = self._rows_for_name()
        self.assertEqual(len(rows2), 1, "still ONE row for the same track")
        self.assertEqual(rows2[0]["id"], beta_id)

    # ── 4. migration 043 applies twice cleanly (idempotent) ─────────────────
    def test_migration_043_idempotent(self):
        if not os.path.exists(_MIGRATION_043):
            self.skipTest("migration 043 not present yet (pre-fix run)")
        with open(_MIGRATION_043, "r") as f:
            sql = f.read()
        for _ in (1, 2):
            conn = _schema_connect()
            try:
                cur = conn.cursor()
                cur.execute(sql)
                conn.commit()
            finally:
                conn.close()
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT to_regclass(%s)",
                (f"{_ISO.schema}.idx_audio_tours_name_creator_track",))
            self.assertIsNotNone(cur.fetchone()[0],
                                 "track-aware index present after migration 043")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
