"""test_local821_no_overwrite.py — LOCAL-821B part (B), the BOUNCE of 821(B).

821(B) added a store_mode split so a serving request never rewrote an existing
tour. LEAD review (2026-10-29) reversed that: it reintroduced the LOCAL-156
dedupe defect in a new form (a curator's edit stopped updating their tour; every
regeneration became a second "<name> [jobid8]" tour). D622 (binding, 2026-10-06)
is restored as the DEFAULT: a regenerated tour REPLACES the stale one of the same
name, keeping a reversible version.

The REAL, narrow defect behind the 465 event was reversibility, not replacement:
on GCloud the ZIP lives in the DB column ``audio_tours.audio_tour``, and the
replace archived the old TEXT to audio_tour_versions but DROPPED the old ZIP
bytes — so the replace could not be undone. (Locally the ZIP is a file and is
renamed <name>.v<N>.zip, which already was reversible.)

This suite proves the restored + fixed behaviour:

  REPLACE + REVERSIBILITY (replace-on-change is the default again):
    1. identical text twice → cache hit, no new row, no version archived.
    2. DIFFERENT text for the same (name, creator, track) → the SAME tour row is
       REPLACED in place (id and share code kept), and the OLD text AND the OLD
       ZIP BYTES are archived to audio_tour_versions FIRST.
    3. restore_tour_version.py --apply round-trips: after a restore, the live
       row's tour_content, stops_count AND the md5 of audio_tour equal the
       ORIGINAL v1 bytes exactly.

  481 / 279 ISOLATION (the existing-tour key keeps creator_user_id + track):
    4. catalog tour 481 "Metropolitan Museum of Art, New York, NY" (creator =
       catalog user) and a stuck request 279 with the SAME string from a
       DIFFERENT user. Storing 279 INSERTS its own tour and leaves 481
       byte-for-byte unchanged (content, stops, number_requested, audio md5).

Everything runs inside a throwaway Postgres schema (tests/_isolated_db.py);
teardown DROPs it and asserts public row counts are identical before/after — no
shared/production row is ever written. DB env is pinned before importing the
orchestrator so its internal psycopg2 connection routes at the throwaway schema
(libpq PGOPTIONS search_path), the same mechanism as test_local606/718.
"""
import hashlib
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
import restore_tour_version as restore_tool  # noqa: E402
import psycopg2  # noqa: E402

_ISO = IsolatedSchema(
    prefix="t821b",
    clone_tables=["audio_tours", "audio_tour_versions", "shared_tours"],
    proof_tables=["audio_tours", "audio_tour_versions", "shared_tours"],
    banner="LOCAL-821B",
)


def _schema_connect():
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
        # Drop the cloned global unique index on lower(tour_name) so a second,
        # separate tour with the same name can coexist (migration 041 behaviour),
        # exactly as test 4 (481/279) needs.
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
        cur.execute("ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS creator_user_id TEXT")
        # Let the orchestrator's own _ensure_versioning_objects build the archive
        # table in this schema with the LOCAL-606 + 821B column shape (zip_bytes).
        cur.execute(f'DROP TABLE IF EXISTS "{_ISO.schema}".audio_tour_versions CASCADE')
        conn.commit()
    finally:
        conn.close()


def tearDownModule():
    _ISO.teardown()


def _make_zip(path, payload):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("audio_1.mp3", payload)
        z.writestr("tour.txt", "content")
    with open(path, "rb") as f:
        return f.read()


@unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
class ReplaceReversibilityTest(unittest.TestCase):
    """Replace-on-change is the default (D622), and the replace is reversible
    even when the ZIP lives in the DB column audio_tours.audio_tour."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="local821b_tours_")
        self._orig_tours_dir = orch.TOURS_DIR
        orch.TOURS_DIR = self._tmp
        self.creator = "creator-" + uuid.uuid4().hex[:8]
        self.tour_name = "Ben Thanh Market - Massage Tour " + uuid.uuid4().hex[:6]

    def tearDown(self):
        orch.TOURS_DIR = self._orig_tours_dir

    def _store(self, tour_content, zip_name, payload, stops_count=4,
               job_id=None, tour_name=None, user_id=None, track="subscribed"):
        zip_path = os.path.join(self._tmp, zip_name)
        zip_bytes = _make_zip(zip_path, payload)
        res = orch.store_audio_tour(
            tour_name or self.tour_name,
            "req:" + (tour_name or self.tour_name),
            zip_path, 10.77, 106.70, tour_content=tour_content,
            stops_count=stops_count, is_test=True, track=track,
            job_id=job_id or ("job-" + uuid.uuid4().hex[:8]),
            user_id=user_id if user_id is not None else self.creator,
        )
        return res, zip_bytes

    def _live_row(self, name=None):
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, tour_content, zip_filename, stops_count, "
                "number_requested, audio_tour FROM audio_tours "
                "WHERE lower(tour_name)=lower(%s) AND original_tour_id IS NULL "
                "ORDER BY id",
                (name or self.tour_name,),
            )
            return cur.fetchall()
        finally:
            conn.close()

    def _versions(self, tour_id):
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT version_no, tour_content, stops_count, zip_bytes "
                "FROM audio_tour_versions WHERE tour_id=%s ORDER BY version_no",
                (tour_id,),
            )
            return cur.fetchall()
        finally:
            conn.close()

    @staticmethod
    def _md5(b):
        return hashlib.md5(bytes(b)).hexdigest() if b is not None else None

    # ── 1. identical text twice → cache hit, no version archived ────────────
    def test_1_identical_text_is_cache_hit(self):
        r1, _ = self._store("Identical tour text.", "v1.zip", b"zip-one")
        self.assertEqual(r1["action"], "inserted")
        rows1 = self._live_row()
        self.assertEqual(len(rows1), 1)
        tour_id, c1, z1, s1, n1, b1 = rows1[0]

        r2, _ = self._store("Identical tour text.", "v2.zip", b"zip-two")
        self.assertEqual(r2["action"], "already_exists",
                         "identical text must be a cache hit, not a replace")
        self.assertEqual(r2["existing_tour_id"], tour_id)

        rows2 = self._live_row()
        self.assertEqual(len(rows2), 1, "still ONE row on a cache hit")
        _, c2, z2, s2, n2, b2 = rows2[0]
        self.assertEqual(c2, c1, "content unchanged on cache hit")
        self.assertEqual(self._md5(b2), self._md5(b1), "audio unchanged on cache hit")
        self.assertEqual(n2, n1 + 1, "number_requested incremented")
        self.assertEqual(self._versions(tour_id), [], "no version archived on a cache hit")

    # ── 2. different text → SAME row replaced; old TEXT + ZIP BYTES archived ─
    def test_2_replace_archives_text_and_zip_bytes(self):
        r1, orig_zip_bytes = self._store(
            "Original 465 content with the real spa stops.", "o.zip",
            b"ORIGINAL-AUDIO-BYTES-v1", stops_count=4)
        self.assertEqual(r1["action"], "inserted")
        orig = self._live_row()[0]
        orig_id, orig_content, _, orig_stops, _, orig_live_bytes = orig
        self.assertEqual(self._md5(orig_live_bytes), self._md5(orig_zip_bytes),
                         "sanity: the ZIP bytes are stored in audio_tours.audio_tour")

        # Regenerate the SAME (name, creator, track) with DIFFERENT text — the
        # curator's edit. D622: REPLACE in place, keeping a reversible version.
        r2, new_zip_bytes = self._store(
            "Improved content with corrected stops.", "n.zip",
            b"NEW-AUDIO-BYTES-v2", stops_count=7)
        self.assertEqual(r2["action"], "replaced",
                         "different text must REPLACE the same tour (D622), not insert")
        self.assertEqual(r2["existing_tour_id"], orig_id, "same tour id kept")

        rows = self._live_row()
        self.assertEqual(len(rows), 1, "still ONE row — replaced in place, no duplicate")
        live = rows[0]
        self.assertEqual(live[0], orig_id, "id unchanged")
        self.assertEqual(live[1], "Improved content with corrected stops.",
                         "live row now holds the NEW text")
        self.assertEqual(self._md5(live[5]), self._md5(new_zip_bytes),
                         "live row now holds the NEW audio bytes")

        # The OLD version was archived FIRST — text AND zip bytes.
        versions = self._versions(orig_id)
        self.assertEqual([v[0] for v in versions], [1], "exactly one archived version")
        v_no, v_content, v_stops, v_zip_bytes = versions[0]
        self.assertEqual(v_content, orig_content, "archived TEXT is the OLD content")
        self.assertEqual(v_stops, orig_stops, "archived stops_count is the OLD value")
        self.assertIsNotNone(v_zip_bytes, "the OLD ZIP BYTES were archived (821B fix)")
        self.assertEqual(self._md5(v_zip_bytes), self._md5(orig_zip_bytes),
                         "archived zip_bytes md5 equals the ORIGINAL v1 ZIP bytes")

    # ── 3. restore round-trips text, stops AND audio exactly ────────────────
    def test_3_restore_round_trips_text_stops_and_audio(self):
        r1, orig_zip_bytes = self._store(
            "v1 content.", "r1.zip", b"RESTORE-ME-AUDIO-v1", stops_count=4)
        self.assertEqual(r1["action"], "inserted")
        tour_id = self._live_row()[0][0]
        orig_md5 = self._md5(orig_zip_bytes)

        # Replace with different text + different audio.
        r2, _ = self._store("v2 content changed.", "r2.zip",
                            b"DIFFERENT-AUDIO-v2", stops_count=9)
        self.assertEqual(r2["action"], "replaced")
        after_replace = self._live_row()[0]
        self.assertNotEqual(self._md5(after_replace[5]), orig_md5,
                            "sanity: live audio differs after replace")

        # Restore v1 via the tool (--apply). The tool connects with the same env;
        # PGOPTIONS (set by the harness) routes it at the throwaway schema.
        restore_tool.TOURS_DIR = self._tmp
        rc = restore_tool.restore(tour_id, 1, apply_changes=True)
        self.assertEqual(rc, 0, "restore --apply must succeed")

        restored = self._live_row()[0]
        self.assertEqual(restored[0], tour_id, "id unchanged by restore")
        self.assertEqual(restored[1], "v1 content.", "text restored to v1")
        self.assertEqual(restored[3], 4, "stops_count restored to v1")
        self.assertEqual(self._md5(restored[5]), orig_md5,
                         "AUDIO md5 restored to the ORIGINAL v1 bytes exactly")

        # The restore is itself reversible: the pre-restore (v2) state was
        # snapshotted as a new version row, so no archived row was lost.
        vnos = [v[0] for v in self._versions(tour_id)]
        self.assertIn(1, vnos, "the v1 archive still exists")
        self.assertGreaterEqual(len(vnos), 2,
                                "restore snapshotted the pre-restore state as a new version")


@unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
class Isolation481vs279Test(unittest.TestCase):
    """The existing-tour key includes creator_user_id and track: a different
    creator's request for the SAME string never matches the catalog tour."""

    MET_NAME = "Metropolitan Museum of Art, New York, NY"

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="local821b_481_")
        self._orig_tours_dir = orch.TOURS_DIR
        orch.TOURS_DIR = self._tmp
        # Distinct creators/tracks mirror the live shape: catalog tour 481 is the
        # catalog user's; stuck request 279 is a DIFFERENT user, same string.
        self.catalog_user = "catalog-" + uuid.uuid4().hex[:8]
        self.other_user = "user279-" + uuid.uuid4().hex[:8]

    def tearDown(self):
        orch.TOURS_DIR = self._orig_tours_dir

    def _store(self, user_id, tour_content, payload, stops_count, track="beta"):
        zip_path = os.path.join(self._tmp, uuid.uuid4().hex[:8] + ".zip")
        zip_bytes = _make_zip(zip_path, payload)
        res = orch.store_audio_tour(
            self.MET_NAME, "req:" + self.MET_NAME, zip_path, 40.7794, -73.9632,
            tour_content=tour_content, stops_count=stops_count, is_test=True,
            track=track, job_id="job-" + uuid.uuid4().hex[:8], user_id=user_id,
        )
        return res, zip_bytes

    def _rows(self):
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, creator_user_id, tour_content, stops_count, "
                "number_requested, audio_tour FROM audio_tours "
                "WHERE lower(tour_name)=lower(%s) AND original_tour_id IS NULL "
                "ORDER BY id",
                (self.MET_NAME,),
            )
            return cur.fetchall()
        finally:
            conn.close()

    def test_4_resuming_279_inserts_own_tour_leaves_481_unchanged(self):
        # Catalog tour 481 exists first.
        r481, bytes481 = self._store(
            self.catalog_user, "The catalog Met tour — v1 content.",
            b"CATALOG-481-AUDIO", stops_count=6)
        self.assertEqual(r481["action"], "inserted")
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        id481, _, content481, stops481, nreq481, _ = rows[0]
        md5_481 = hashlib.md5(bytes(bytes481)).hexdigest()

        # Stuck request 279: a DIFFERENT user, the SAME request string. Storing
        # it must INSERT its own tour, never match/replace 481.
        r279, _ = self._store(
            self.other_user, "A different user's Met tour — different text.",
            b"USER-279-AUDIO", stops_count=3)
        self.assertEqual(r279["action"], "inserted",
                         "a different creator must INSERT a new tour, never replace 481")
        self.assertNotEqual(r279.get("existing_tour_id"), id481)

        rows_after = self._rows()
        self.assertEqual(len(rows_after), 2, "two separate tours — 481 and 279's own")

        # 481 is byte-for-byte unchanged.
        row481 = [r for r in rows_after if r[0] == id481]
        self.assertEqual(len(row481), 1, "481 still exists under its own id")
        _, creator, content, stops, nreq, live_bytes = row481[0]
        self.assertEqual(creator, self.catalog_user, "481 creator unchanged")
        self.assertEqual(content, content481, "481 content UNCHANGED")
        self.assertEqual(stops, stops481, "481 stops_count UNCHANGED")
        self.assertEqual(nreq, nreq481, "481 number_requested UNCHANGED (not incremented)")
        self.assertEqual(hashlib.md5(bytes(live_bytes)).hexdigest(), md5_481,
                         "481 audio bytes UNCHANGED (byte-for-byte)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
