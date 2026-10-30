"""test_local821_no_overwrite.py — LOCAL-821 part (B).

Proves a NEW request never rewrites an existing tour's stops.

Evidence being closed (GCloud_Storied wave-4, 2026-10-30): a proof request
"Massage and spa near Ben Thanh Market…" with the SAME request string as
existing tour 465 OVERWROTE 465 (new stops; its ru translation flagged stale).
The store's existing-tour lookup keys on (tour_name, creator_user_id, track) and
the LOCAL-606 "replace-on-change" branch fired for ANY serving request whose
text differed — so a serve request silently replaced a stranger's tour content.

The fix adds store_mode to store_audio_tour:
  * serve (default, every normal request): NEVER replaces. Identical text →
    cache hit (number_requested++). Different text → a NEW, SEPARATE tour.
  * regenerate (explicit admin path only): the LOCAL-606 replace, archiving the
    old content to audio_tour_versions FIRST.

Covered (one assertion focus each):
  1. identical request twice → the first tour is byte-for-byte UNCHANGED
     (number_requested incremented, action 'already_exists'); no version row.
  2. serve request with DIFFERENT text for the same name/creator → a NEW tour
     is inserted; the original tour's content/zip/stops are UNCHANGED and no
     version is archived (the overwrite that hit 465 cannot happen).
  3. regenerate with DIFFERENT text → the original tour IS replaced and its old
     content is archived to audio_tour_versions FIRST (admin path intact).

Everything runs inside a throwaway Postgres schema (tests/_isolated_db.py);
teardown DROPs it and asserts public row counts are identical before/after — no
shared/production row is ever written. DB env is pinned before importing the
orchestrator so its internal psycopg2 connection routes at the throwaway schema
(libpq PGOPTIONS search_path), the same mechanism as test_local606/718.
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
        # separate tour with the same name can coexist (migration 041 behaviour).
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
        # Let the orchestrator's own _ensure_versioning_objects build the
        # archive table in this schema with the LOCAL-606 column shape.
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


@unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
class NoOverwriteTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="local821b_tours_")
        self._orig_tours_dir = orch.TOURS_DIR
        orch.TOURS_DIR = self._tmp
        # A unique creator+name per test so cases never collide in the schema.
        self.creator = "creator-" + uuid.uuid4().hex[:8]
        self.tour_name = "Ben Thanh Market - Massage Tour " + uuid.uuid4().hex[:6]

    def tearDown(self):
        orch.TOURS_DIR = self._orig_tours_dir

    def _store(self, tour_content, zip_name, payload, store_mode="serve",
               stops_count=4, job_id=None, tour_name=None):
        zip_path = os.path.join(self._tmp, zip_name)
        _make_zip(zip_path, payload)
        return orch.store_audio_tour(
            tour_name or self.tour_name,
            "req:" + (tour_name or self.tour_name),
            zip_path, 10.77, 106.70, tour_content=tour_content,
            stops_count=stops_count, is_test=True, track="subscribed",
            job_id=job_id or ("job-" + uuid.uuid4().hex[:8]),
            user_id=self.creator, store_mode=store_mode,
        )

    def _rows_for_name(self, name=None):
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, tour_content, zip_filename, stops_count, "
                "number_requested FROM audio_tours "
                "WHERE lower(tour_name)=lower(%s) AND original_tour_id IS NULL "
                "ORDER BY id",
                (name or self.tour_name,),
            )
            return cur.fetchall()
        finally:
            conn.close()

    def _rows_like_name(self):
        """Rows whose name is self.tour_name OR a disambiguated variant of it
        (serve mode inserts a NEW tour under '<name> [<jobid8>]')."""
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, tour_content, zip_filename, stops_count, "
                "number_requested FROM audio_tours "
                "WHERE lower(tour_name) LIKE lower(%s) AND original_tour_id IS NULL "
                "ORDER BY id",
                (self.tour_name + "%",),
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

    # ── 1. identical request twice → first tour untouched (cache hit) ───────
    def test_1_identical_request_twice_leaves_tour_untouched(self):
        r1 = self._store("Identical tour text.", "v1.zip", b"zip-one")
        self.assertEqual(r1["action"], "inserted")
        rows1 = self._rows_for_name()
        self.assertEqual(len(rows1), 1)
        tour_id, content1, zip1, stops1, nreq1 = rows1[0]

        # The SAME request again (serve mode, byte-identical text).
        r2 = self._store("Identical tour text.", "v2.zip", b"zip-two")
        self.assertEqual(r2["action"], "already_exists",
                         "identical text must be a cache hit, not a new/replaced tour")
        self.assertEqual(r2["existing_tour_id"], tour_id)

        rows2 = self._rows_for_name()
        self.assertEqual(len(rows2), 1, "still ONE row — no new tour on a cache hit")
        _, content2, zip2, stops2, nreq2 = rows2[0]
        self.assertEqual(content2, content1, "content unchanged on cache hit")
        self.assertEqual(zip2, zip1, "zip unchanged on cache hit")
        self.assertEqual(stops2, stops1, "stops unchanged on cache hit")
        self.assertEqual(nreq2, nreq1 + 1, "number_requested incremented")
        self.assertEqual(self._versions(tour_id), [], "no version archived on a cache hit")

    # ── 2. serve + DIFFERENT text → NEW tour; original UNCHANGED ────────────
    def test_2_serve_different_text_inserts_new_and_leaves_original(self):
        r1 = self._store("Original 465 content with the real spa stops.", "o.zip", b"orig")
        self.assertEqual(r1["action"], "inserted")
        orig = self._rows_for_name()[0]
        orig_id, orig_content, orig_zip, orig_stops, orig_nreq = orig

        # A NEW serve request, same name+creator+track, but DIFFERENT text —
        # exactly the shape that overwrote tour 465.
        r2 = self._store("Totally different proof-run content.", "n.zip", b"new",
                         stops_count=7)
        self.assertEqual(r2["action"], "inserted",
                         "serve mode must INSERT a new tour, never replace")
        self.assertNotEqual(r2.get("existing_tour_id"), orig_id)

        # Two tours now share the base name (the original + the disambiguated
        # new one); the overwrite that hit 465 would instead have left ONE row
        # with rewritten content.
        all_rows = self._rows_like_name()
        self.assertEqual(len(all_rows), 2, "two separate tours — the new one did not overwrite")
        ids = {r[0] for r in all_rows}
        self.assertIn(orig_id, ids, "the original tour id still exists")

        # The ORIGINAL tour (exact name) is byte-for-byte unchanged (the
        # LOCAL-821 invariant).
        rows = self._rows_for_name()
        self.assertEqual(len(rows), 1, "the exact-name original row is still a single row")
        orig_after = rows[0]
        self.assertEqual(orig_after[0], orig_id, "same original id")
        self.assertEqual(orig_after[1], orig_content, "original content UNCHANGED")
        self.assertEqual(orig_after[2], orig_zip, "original zip UNCHANGED")
        self.assertEqual(orig_after[3], orig_stops, "original stops UNCHANGED")
        self.assertEqual(orig_after[4], orig_nreq, "original number_requested UNCHANGED")
        self.assertEqual(self._versions(orig_id), [],
                         "serve must NOT archive a version of the original")

    # ── 3. regenerate + DIFFERENT text → replace, archiving old first ───────
    def test_3_regenerate_replaces_and_archives_old_version(self):
        r1 = self._store("Admin tour v1 content.", "r1.zip", b"r1")
        self.assertEqual(r1["action"], "inserted")
        tour_id = self._rows_for_name()[0][0]

        # Explicit admin regenerate with DIFFERENT text.
        r2 = self._store("Admin tour v2 improved content.", "r2.zip", b"r2",
                         store_mode="regenerate", stops_count=6)
        self.assertEqual(r2["action"], "replaced",
                         "regenerate mode replaces the existing tour")
        self.assertEqual(r2["existing_tour_id"], tour_id)

        rows = self._rows_for_name()
        self.assertEqual(len(rows), 1, "still one row — same id, versioned")
        self.assertEqual(rows[0][0], tour_id, "same id kept")
        self.assertEqual(rows[0][1], "Admin tour v2 improved content.",
                         "row now holds the new content")
        # The OLD content was archived to audio_tour_versions FIRST (reversible).
        self.assertEqual(self._versions(tour_id), [1],
                         "old version archived before replacement")
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT tour_content FROM audio_tour_versions "
                "WHERE tour_id=%s AND version_no=1",
                (tour_id,),
            )
            archived = cur.fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(archived, "Admin tour v1 content.",
                         "the archived version holds the PREVIOUS content")


if __name__ == "__main__":
    unittest.main(verbosity=2)
