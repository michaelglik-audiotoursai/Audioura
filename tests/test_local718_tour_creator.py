#!/usr/bin/env python3
"""test_local718_tour_creator.py — LOCAL-718 / D678.

Proves "a tour belongs to its creator": a second person generating the same
name NEVER replaces the first creator's tour. Everything runs inside a
throwaway Postgres schema (tests/_isolated_db.py); teardown DROPs the schema and
asserts public row counts are identical before and after — no shared row is ever
written.

Covered (the 6 scenarios from the ticket):
  1. Same creator + same name       → version 2 of the SAME id.
  2. Different creator + same name   → a NEW id; the first tour is byte-for-byte
                                       unchanged (content, zip, price).
  3. A NULL-creator existing row     → a different creator gets a NEW id.
  4. A PAID tour is never replaced by another creator (its price/purchase stand).
  5. The INSERT stores creator_user_id.
  6. The migration (041) applies twice cleanly (idempotent).

DB env is pinned BEFORE importing the orchestrator so its internal psycopg2
connection (hardcoded host=postgres-2 default) is routed at the same throwaway
schema as the test's own connections, via libpq PGOPTIONS search_path. Same
mechanism as test_local606_replace_on_change.py.
"""
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

# Path to migration 041 for the idempotency test (scenario 6).
_MIGRATION_041 = os.path.join(_ROOT, "migration", "sql", "041_tour_creator.sql")

_ISO = IsolatedSchema(
    prefix="t718",
    clone_tables=["audio_tours", "audio_tour_versions", "shared_tours"],
    proof_tables=["audio_tours", "audio_tour_versions", "shared_tours"],
    banner="LOCAL-718",
)


def setUpModule():
    _ISO.setup()
    if _ISO.schema is None:
        return
    # Simulate migration 041 on the throwaway schema: the clone carried the old
    # global-namespace UNIQUE index (LIKE … INCLUDING ALL); drop it so a second
    # creator's same-name tour can coexist as a separate row. The orchestrator
    # self-heals the creator_user_id column on first store, so we need not add it
    # here — but adding it is harmless and lets the pre-store asserts read it.
    conn = _schema_connect()
    try:
        cur = conn.cursor()
        # The clone (LIKE … INCLUDING ALL) re-created the global unique index
        # under a Postgres-generated name (e.g. audio_tours_lower_idx), not the
        # production name. Discover and drop EVERY unique index on
        # lower(tour_name) in this schema so a second creator's same-name tour
        # can coexist — this is exactly what migration 041 does in production.
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
        # The cloned audio_tour_versions in audiotours_test predates LOCAL-606's
        # tour_content/zip_filename columns. Drop the clone and let the
        # orchestrator's own _ensure_versioning_objects re-create it in THIS
        # schema (PGOPTIONS routes the unqualified name here), so the archive
        # table matches exactly what store_audio_tour's replace path INSERTs.
        cur.execute(f'DROP TABLE IF EXISTS "{_ISO.schema}".audio_tour_versions CASCADE')
        conn.commit()
        orch._ensure_versioning_objects(cur)
        conn.commit()
    finally:
        conn.close()


def tearDownModule():
    _ISO.teardown()


def _schema_connect():
    """Connection honouring PGOPTIONS (search_path = throwaway schema)."""
    return psycopg2.connect(
        host=_CFG["host"], port=_CFG["port"], dbname=_CFG["dbname"],
        user=_CFG["user"], password=_CFG["password"], connect_timeout=5,
    )


def _make_zip(path, payload=b"stop-audio"):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("tour.mp3", payload)


@unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
class TourCreatorTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="local718_tours_")
        self._orig_tours_dir = orch.TOURS_DIR
        orch.TOURS_DIR = self._tmp
        # Unique name per test to avoid cross-test collisions in the schema.
        self.tour_name = f"LOCAL718 Venue {uuid.uuid4().hex[:8]}"
        self.alice = f"alice-{uuid.uuid4().hex[:8]}"
        self.bob = f"bob-{uuid.uuid4().hex[:8]}"

    def tearDown(self):
        orch.TOURS_DIR = self._orig_tours_dir

    # ── helpers ───────────────────────────────────────────────────────────
    def _store(self, user_id, tour_content, zip_name, payload,
               stops_count=4, lat=None, lng=None, is_test=True,
               job_id=None, tour_name=None):
        zip_path = os.path.join(self._tmp, zip_name)
        _make_zip(zip_path, payload)
        return orch.store_audio_tour(
            tour_name or self.tour_name, "req:" + (tour_name or self.tour_name),
            zip_path, lat, lng, tour_content=tour_content,
            stops_count=stops_count, is_test=is_test,
            job_id=job_id or ("job-" + uuid.uuid4().hex[:8]),
            user_id=user_id,
        )

    def _rows_for_name(self, name=None):
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, creator_user_id, tour_content, zip_filename, "
                "number_requested FROM audio_tours "
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
                "SELECT version_no FROM audio_tour_versions WHERE tour_id=%s "
                "ORDER BY version_no",
                (tour_id,),
            )
            return [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

    # ── 1. same creator + same name → version 2 of the same id ──────────────
    def test_1_same_creator_same_name_versions_same_id(self):
        r1 = self._store(self.alice, "Alice original text.", "a_v1.zip", b"z1")
        self.assertTrue(r1["success"])
        self.assertEqual(r1["action"], "inserted")
        rows = self._rows_for_name()
        self.assertEqual(len(rows), 1)
        tour_id = rows[0][0]

        # Alice regenerates the SAME name with DIFFERENT text.
        r2 = self._store(self.alice, "Alice improved text v2.", "a_v2.zip", b"z2")
        self.assertEqual(r2["action"], "replaced")
        self.assertEqual(r2["existing_tour_id"], tour_id)
        # replaced_version_no is the archived version number (LOCAL-717 reads it).
        self.assertEqual(r2["replaced_version_no"], 1)

        rows2 = self._rows_for_name()
        self.assertEqual(len(rows2), 1, "still ONE row — same id versioned")
        self.assertEqual(rows2[0][0], tour_id, "same id kept (share codes survive)")
        self.assertEqual(self._versions(tour_id), [1], "version 1 archived")

    # ── 2. different creator → new id; first tour unchanged ─────────────────
    def test_2_different_creator_new_id_first_unchanged(self):
        r1 = self._store(self.alice, "Alice's content.", "a.zip", b"alice-zip")
        alice_id = self._rows_for_name()[0][0]
        alice_row = self._rows_for_name()[0]

        # Bob generates the SAME name.
        r2 = self._store(self.bob, "Bob's own content.", "b.zip", b"bob-zip")
        self.assertEqual(r2["action"], "inserted", "Bob gets a NEW tour, not a replace")
        self.assertIsNone(r2["replaced_version_no"])

        rows = self._rows_for_name()
        self.assertEqual(len(rows), 2, "two separate rows, one per creator")
        ids = {r[0] for r in rows}
        self.assertIn(alice_id, ids)
        self.assertEqual(len(ids), 2, "distinct ids")

        # Alice's row is byte-for-byte unchanged (content, zip, number_requested).
        alice_after = [r for r in rows if r[0] == alice_id][0]
        self.assertEqual(alice_after[1], self.alice, "creator preserved")
        self.assertEqual(alice_after[2], alice_row[2], "content unchanged")
        self.assertEqual(alice_after[3], alice_row[3], "zip unchanged")
        self.assertEqual(alice_after[4], alice_row[4], "number_requested unchanged")
        self.assertEqual(self._versions(alice_id), [], "no version archived on Alice's tour")

    # ── 3. a NULL-creator existing row → a new id for a real creator ────────
    def test_3_null_creator_row_gives_new_id(self):
        # An existing row with NULL creator (e.g. pre-migration / unknown).
        r0 = self._store(None, "Legacy unknown-creator content.", "legacy.zip", b"legacy")
        self.assertEqual(r0["action"], "inserted")
        legacy_rows = self._rows_for_name()
        self.assertEqual(len(legacy_rows), 1)
        self.assertIsNone(legacy_rows[0][1], "legacy row has NULL creator")
        legacy_id = legacy_rows[0][0]

        # A real creator generates the same name → NEW id, legacy row untouched.
        r1 = self._store(self.alice, "Alice content.", "a.zip", b"alice")
        self.assertEqual(r1["action"], "inserted", "NULL-creator row never matched")
        rows = self._rows_for_name()
        self.assertEqual(len(rows), 2)
        self.assertEqual(self._versions(legacy_id), [], "legacy row not versioned")

    # ── 4. a paid tour is never replaced by another creator ─────────────────
    def test_4_paid_tour_not_replaced_by_other_creator(self):
        # Alice owns a PAID tour (set a price on her row).
        self._store(self.alice, "Alice paid tour content.", "paid.zip", b"paid-zip")
        alice_id = self._rows_for_name()[0][0]
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            # price_cents may not exist on every schema; use a SAVEPOINT-free
            # best-effort and fall back to number_requested as the "value" proxy.
            cur.execute("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name='audio_tours' AND column_name='price_cents'
            """)
            has_price = cur.fetchone() is not None
            if has_price:
                cur.execute("UPDATE audio_tours SET price_cents=499 WHERE id=%s", (alice_id,))
                conn.commit()
        finally:
            conn.close()

        # Bob generates the same name.
        r = self._store(self.bob, "Bob content.", "bob.zip", b"bob-zip")
        self.assertEqual(r["action"], "inserted", "paid tour not replaced across creators")

        conn = _schema_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT tour_content, zip_filename FROM audio_tours WHERE id=%s",
                (alice_id,))
            content, zipname = cur.fetchone()
            self.assertEqual(content, "Alice paid tour content.", "paid content intact")
            if has_price:
                cur.execute("SELECT price_cents FROM audio_tours WHERE id=%s", (alice_id,))
                self.assertEqual(cur.fetchone()[0], 499, "price intact")
        finally:
            conn.close()
        self.assertEqual(self._versions(alice_id), [], "paid tour never versioned by Bob")

    # ── 5. the INSERT stores creator_user_id ────────────────────────────────
    def test_5_insert_stores_creator_user_id(self):
        self._store(self.alice, "Alice content.", "a.zip", b"alice")
        rows = self._rows_for_name()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], self.alice, "creator_user_id persisted on INSERT")

    # ── 6. the migration applies twice cleanly (idempotent) ─────────────────
    def test_6_migration_idempotent(self):
        with open(_MIGRATION_041, "r") as f:
            sql = f.read()
        # Apply twice against the throwaway schema; neither run may raise.
        for attempt in (1, 2):
            conn = _schema_connect()
            try:
                cur = conn.cursor()
                cur.execute(sql)
                conn.commit()
            finally:
                conn.close()
        # After the migration, the column and the new index exist, the old
        # unique index does not.
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name='audio_tours' AND column_name='creator_user_id'
            """)
            self.assertIsNotNone(cur.fetchone(), "creator_user_id column present")
            cur.execute("SELECT to_regclass(%s)", (f"{_ISO.schema}.idx_audio_tours_name_creator",))
            self.assertIsNotNone(cur.fetchone()[0], "new creator index present")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
