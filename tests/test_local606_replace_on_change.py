#!/usr/bin/env python3
"""test_local606_replace_on_change.py — LOCAL-606 / D622.

Proves the replace-on-change rule for regenerated tours, entirely inside a
throwaway Postgres schema (tests/_isolated_db.py). No production/shared row is
ever written: teardown DROPs the schema and asserts public row counts are
identical before and after.

Covered (one assertion each, per the ticket):
  1. new text REPLACES the row, a version is archived, and the old ZIP is
     renamed <name>.v<N>.zip (never deleted);
  2. byte-identical text is only incremented (no version row, no replacement);
  3. translations (original_tour_id = this id) are flagged stale;
  4. the share code (shared_tours row) is unchanged and still points at the
     same tour id;
  5. restore_tour_version.py --apply puts the old content back.

Why the DB env is pinned before import
======================================
tour_orchestrator_service.store_audio_tour opens its own psycopg2 connection
with hardcoded DEFAULTS of host=postgres-2 (the in-container name, unreachable
from the host). We point those env vars at the same local DB that
_isolated_db resolves (localhost:5433/audiotours_test), so libpq's PGOPTIONS
search_path (set by IsolatedSchema) routes BOTH this test's connections and the
orchestrator's internal connection at the throwaway schema.
"""
import os
import sys
import unittest
import uuid
import zipfile
import tempfile

# tests/ dir on path so _isolated_db and db_connection import; repo root too so
# tour_orchestrator_service and restore_tour_version import.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from db_connection import get_db_config  # noqa: E402

# Pin the orchestrator's internal connection at the SAME DB _isolated_db uses,
# BEFORE importing it. get_db_config() resolves audiotours_test under pytest.
_CFG = get_db_config()
os.environ["DB_HOST"] = _CFG["host"]
os.environ["DB_PORT"] = str(_CFG["port"])
os.environ["DB_NAME"] = _CFG["dbname"]
os.environ["DB_USER"] = _CFG["user"]
os.environ["DB_PASSWORD"] = _CFG["password"]

from _isolated_db import IsolatedSchema  # noqa: E402
import tour_orchestrator_service as orch  # noqa: E402
import restore_tour_version as restore_helper  # noqa: E402
import psycopg2  # noqa: E402

_ISO = IsolatedSchema(
    prefix="t606",
    clone_tables=["audio_tours", "shared_tours"],
    proof_tables=["audio_tours", "shared_tours"],
    banner="LOCAL-606",
)


def setUpModule():
    _ISO.setup()


def tearDownModule():
    _ISO.teardown()


def _schema_connect():
    """A connection that honours PGOPTIONS (search_path = throwaway schema)."""
    return psycopg2.connect(
        host=_CFG["host"], port=_CFG["port"], dbname=_CFG["dbname"],
        user=_CFG["user"], password=_CFG["password"], connect_timeout=5,
    )


def _make_zip(path, payload=b"stop-audio"):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("tour.mp3", payload)


@unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
class ReplaceOnChangeTest(unittest.TestCase):
    def setUp(self):
        # A fresh temp TOURS_DIR per test so ZIP renames are observable and
        # isolated. Point the orchestrator and the restore helper at it.
        self._tmp = tempfile.mkdtemp(prefix="local606_tours_")
        self._orig_tours_dir = orch.TOURS_DIR
        orch.TOURS_DIR = self._tmp
        self._orig_restore_tours_dir = restore_helper.TOURS_DIR
        restore_helper.TOURS_DIR = self._tmp
        # Unique tour name per test to avoid cross-test collisions in the schema.
        self.tour_name = f"LOCAL606 Venue {uuid.uuid4().hex[:8]}"

    def tearDown(self):
        orch.TOURS_DIR = self._orig_tours_dir
        restore_helper.TOURS_DIR = self._orig_restore_tours_dir

    # ── helpers ───────────────────────────────────────────────────────────
    def _store(self, tour_content, stops_count, zip_name, payload, lat=None,
               lng=None, job_id="job-xxxx"):
        zip_path = os.path.join(self._tmp, zip_name)
        _make_zip(zip_path, payload)
        return orch.store_audio_tour(
            self.tour_name, "req:" + self.tour_name, zip_path, lat, lng,
            tour_content=tour_content, stops_count=stops_count,
            is_test=True, job_id=job_id,
        )

    def _row(self):
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, tour_content, zip_filename, stops_count, lat, lng, "
                "number_requested FROM audio_tours "
                "WHERE lower(tour_name)=lower(%s) AND original_tour_id IS NULL",
                (self.tour_name,),
            )
            return cur.fetchone()
        finally:
            conn.close()

    def _versions(self, tour_id):
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT version_no, tour_content, zip_filename, stops_count, "
                "lat, lng, replaced_by_job FROM audio_tour_versions "
                "WHERE tour_id=%s ORDER BY version_no",
                (tour_id,),
            )
            return cur.fetchall()
        finally:
            conn.close()

    # ── 1. replace saves a version and renames the old ZIP ─────────────────
    def test_1_new_text_replaces_and_archives_and_renames_zip(self):
        r1 = self._store("Alphabetical pre-fix stops.", 4,
                         "venue_v1.zip", b"zip-one")
        self.assertTrue(r1["success"])
        self.assertEqual(r1["action"], "inserted")
        row1 = self._row()
        tour_id = row1[0]

        # Regenerate with DIFFERENT text and a different stop count.
        r2 = self._store("Improved 6-stop text after G4 corrective.", 6,
                         "venue_v2.zip", b"zip-two")
        self.assertEqual(r2["action"], "replaced")
        self.assertEqual(r2["existing_tour_id"], tour_id)

        row2 = self._row()
        # Same id (so share codes/curator links keep working).
        self.assertEqual(row2[0], tour_id)
        # Live content replaced.
        self.assertEqual(row2[1], "Improved 6-stop text after G4 corrective.")
        self.assertEqual(row2[3], 6)  # stops_count replaced

        # A version row archived the OLD content.
        versions = self._versions(tour_id)
        self.assertEqual(len(versions), 1)
        v = versions[0]
        self.assertEqual(v[0], 1)                                  # version_no
        self.assertEqual(v[1], "Alphabetical pre-fix stops.")      # old content
        self.assertEqual(v[3], 4)                                  # old stops
        self.assertEqual(v[2], "venue_v1.v1.zip")                  # archived name

        # The old ZIP was renamed on disk, never deleted.
        self.assertFalse(os.path.exists(os.path.join(self._tmp, "venue_v1.zip")))
        self.assertTrue(os.path.exists(os.path.join(self._tmp, "venue_v1.v1.zip")))

    # ── 2. identical text only increments ──────────────────────────────────
    def test_2_identical_text_only_increments(self):
        same = "Byte identical narration."
        self._store(same, 5, "venue_a.zip", b"zip-a")
        row1 = self._row()
        tour_id, nreq1 = row1[0], row1[6]

        r2 = self._store(same, 5, "venue_b.zip", b"zip-b")
        self.assertEqual(r2["action"], "already_exists")

        row2 = self._row()
        self.assertEqual(row2[0], tour_id)             # same row
        self.assertEqual(row2[6], nreq1 + 1)           # number_requested bumped
        self.assertEqual(self._versions(tour_id), [])  # no version archived
        # Original ZIP not renamed (no replacement happened).
        self.assertTrue(os.path.exists(os.path.join(self._tmp, "venue_a.zip")))

    # ── 3. translations flagged stale on replacement ──────────────────────
    def test_3_translations_flagged_stale(self):
        self._store("Original EN text.", 4, "venue_o.zip", b"zip-o")
        tour_id = self._row()[0]

        # Insert two translation rows referencing this original.
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            for lang in ("es", "fr"):
                cur.execute(
                    "INSERT INTO audio_tours (tour_name, request_string, "
                    "original_tour_id, content_language, number_requested, is_test) "
                    "VALUES (%s,%s,%s,%s,0,TRUE)",
                    (f"{self.tour_name} [{lang}]", "req", tour_id, lang),
                )
            conn.commit()
        finally:
            conn.close()

        # Regenerate original with different text → translations go stale.
        self._store("Revised EN text, different.", 5, "venue_o2.zip", b"zip-o2")

        conn = _schema_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT content_language, translation_stale FROM audio_tours "
                "WHERE original_tour_id=%s ORDER BY content_language",
                (tour_id,),
            )
            rows = cur.fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r[1] is True for r in rows),
                        f"all translations must be stale, got {rows}")

    # ── 4. share code unchanged across replacement ────────────────────────
    def test_4_share_code_unchanged(self):
        self._store("Content with a curator share link.", 4,
                    "venue_s.zip", b"zip-s")
        tour_id = self._row()[0]

        share_code = "SHR" + uuid.uuid4().hex[:5]
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            # Only the columns guaranteed present in the clone.
            cur.execute(
                "INSERT INTO shared_tours (tour_id, tour_text, location, "
                "tour_type, total_stops) VALUES (%s,%s,%s,%s,%s)",
                (share_code, "Content with a curator share link.",
                 self.tour_name, "walking", 4),
            )
            conn.commit()
        finally:
            conn.close()

        # Replace the tour content.
        self._store("Replaced content; link must still resolve.", 6,
                    "venue_s2.zip", b"zip-s2")

        # Tour id unchanged → the share code still targets the same tour.
        self.assertEqual(self._row()[0], tour_id)
        # The shared_tours row itself is byte-for-byte unchanged.
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT tour_id, tour_text, location, tour_type, total_stops "
                "FROM shared_tours WHERE tour_id=%s",
                (share_code,),
            )
            srow = cur.fetchone()
        finally:
            conn.close()
        self.assertEqual(
            srow,
            (share_code, "Content with a curator share link.",
             self.tour_name, "walking", 4),
        )

    # ── 5. restore puts the old content back ───────────────────────────────
    def test_5_restore_reverses_replacement(self):
        self._store("The ORIGINAL content.", 4, "venue_r.zip", b"zip-r")
        tour_id = self._row()[0]
        self._store("The REPLACED content.", 7, "venue_r2.zip", b"zip-r2")

        # Precondition: live row holds the replaced content.
        live = self._row()
        self.assertEqual(live[1], "The REPLACED content.")
        self.assertEqual(live[3], 7)

        # Dry-run touches nothing.
        rc = restore_helper.restore(tour_id, 1, apply_changes=False)
        self.assertEqual(rc, 0)
        self.assertEqual(self._row()[1], "The REPLACED content.")

        # Apply restores version 1's content.
        rc = restore_helper.restore(tour_id, 1, apply_changes=True)
        self.assertEqual(rc, 0)
        restored = self._row()
        self.assertEqual(restored[0], tour_id)              # same row
        self.assertEqual(restored[1], "The ORIGINAL content.")
        self.assertEqual(restored[3], 4)                    # old stops back

        # The restore is itself reversible: current (replaced) content was
        # snapshotted as a new version before overwriting.
        versions = self._versions(tour_id)
        snap = [v for v in versions if v[1] == "The REPLACED content."]
        self.assertTrue(snap, "restore must snapshot current content as a new version")


if __name__ == "__main__":
    unittest.main(verbosity=2)
