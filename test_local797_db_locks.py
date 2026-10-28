"""LOCAL-797 — runtime DDL locks + idle-in-transaction readers must never freeze a tour.

Reproduces the live incident (Mac DB, 2026-10-28) against a THROWAWAY Postgres —
never the live 5433 DB. The DB connection is taken from LOCAL797_TEST_DSN (or the
standard DB_* env vars); if none is reachable the DB-touching tests SKIP rather
than fail, and never touch localhost:5433.

The mechanism under test:
  * A reader (connection A) opens a transaction on venue_corpus and stays idle.
  * venue_resolver._ensure_table on a fresh connection (B) must return within a
    few seconds — its ALTER is skipped (lock busy), logged — instead of queueing
    behind A for minutes.
  * A SELECT on a third connection (C) is NOT blocked.
  * _ensure_table on a table whose `tier` is already VARCHAR(20) issues NO ALTER.

Also unit-tests db_safe_ddl.safe_ddl directly (needed-check skip, lock-timeout
skip-and-continue, success path).
"""
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import psycopg2
    _HAVE_PG = True
except Exception:
    _HAVE_PG = False

import db_safe_ddl


def _test_dsn():
    """Return a DSN for the THROWAWAY test DB, or None.

    Order: LOCAL797_TEST_DSN, then DATABASE_URL/DB_* ONLY when they clearly do
    not point at the live 5433 DB. We refuse 5433 outright (the ticket: never
    touch the live DB).
    """
    dsn = os.environ.get("LOCAL797_TEST_DSN")
    if dsn:
        return dsn
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "")
    name = os.environ.get("DB_NAME", "audiotours")
    user = os.environ.get("DB_USER", "admin")
    pw = os.environ.get("DB_PASSWORD", "password123")
    if port and port != "5433":
        return f"postgresql://{user}:{pw}@{host}:{port}/{name}"
    return None


def _connect(dsn, autocommit=False):
    conn = psycopg2.connect(dsn, connect_timeout=5)
    conn.autocommit = autocommit
    return conn


def _refuse_live(dsn):
    if dsn and ":5433/" in dsn:
        raise AssertionError("refusing to run against live DB (port 5433)")


@unittest.skipUnless(_HAVE_PG, "psycopg2 not installed")
class SafeDdlUnitTests(unittest.TestCase):
    """safe_ddl behaviour that needs a real connection but no contention."""

    @classmethod
    def setUpClass(cls):
        cls.dsn = _test_dsn()
        if not cls.dsn:
            raise unittest.SkipTest("no throwaway DB DSN (set LOCAL797_TEST_DSN)")
        _refuse_live(cls.dsn)
        try:
            cls.conn = _connect(cls.dsn, autocommit=False)
        except Exception as e:
            raise unittest.SkipTest(f"throwaway DB unreachable: {e}")
        with cls.conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS sd_unit")
            cur.execute("CREATE TABLE sd_unit (id INT, tier VARCHAR(10))")
        cls.conn.commit()

    @classmethod
    def tearDownClass(cls):
        try:
            with cls.conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS sd_unit")
            cls.conn.commit()
            cls.conn.close()
        except Exception:
            pass

    def test_needed_check_false_skips_ddl(self):
        """When needed_check_sql is falsy the DDL is skipped (returns False)."""
        ran = db_safe_ddl.safe_ddl(
            self.conn,
            "ALTER TABLE sd_unit ADD COLUMN should_not_exist INT",
            needed_check_sql="SELECT 1 WHERE false",
            label="LOCAL-797-test",
        )
        self.assertFalse(ran)
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='sd_unit' AND column_name='should_not_exist'"
            )
            self.assertIsNone(cur.fetchone(), "DDL ran despite needed_check=false")
        self.conn.commit()

    def test_success_path_applies_ddl(self):
        """A needed DDL with a free lock is applied and committed."""
        ran = db_safe_ddl.safe_ddl(
            self.conn,
            "ALTER TABLE sd_unit ADD COLUMN extra INT",
            needed_check_sql=(
                "SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name='sd_unit' AND column_name='extra')"
            ),
            label="LOCAL-797-test",
        )
        self.assertTrue(ran)
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='sd_unit' AND column_name='extra'"
            )
            self.assertIsNotNone(cur.fetchone())
        self.conn.commit()


@unittest.skipUnless(_HAVE_PG, "psycopg2 not installed")
class VenueCorpusLockTests(unittest.TestCase):
    """The live freeze mechanism: an idle reader must not stall _ensure_table."""

    @classmethod
    def setUpClass(cls):
        cls.dsn = _test_dsn()
        if not cls.dsn:
            raise unittest.SkipTest("no throwaway DB DSN (set LOCAL797_TEST_DSN)")
        _refuse_live(cls.dsn)
        try:
            c = _connect(cls.dsn, autocommit=True)
        except Exception as e:
            raise unittest.SkipTest(f"throwaway DB unreachable: {e}")
        c.close()

    def setUp(self):
        # Point venue_resolver at the throwaway DB and reset its once-per-process
        # guard so _ensure_table actually runs this test.
        self._saved_env = {k: os.environ.get(k) for k in
                           ("VENUE_CACHE_DB_URL", "DATABASE_URL")}
        os.environ["VENUE_CACHE_DB_URL"] = self.dsn
        os.environ.pop("DATABASE_URL", None)
        import venue_resolver
        venue_resolver._TABLE_ENSURED = False
        self.vr = venue_resolver
        # Clean slate: drop venue_corpus so each test controls the schema.
        admin = _connect(self.dsn, autocommit=True)
        with admin.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS venue_corpus")
        admin.close()

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.vr._TABLE_ENSURED = False
        admin = _connect(self.dsn, autocommit=True)
        with admin.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS venue_corpus")
        admin.close()

    def _seed_venue_corpus_narrow_tier(self):
        """Create venue_corpus with a tier narrower than 20 so an ALTER WOULD be
        needed, then insert a row so a reader can hold a lock on it."""
        admin = _connect(self.dsn, autocommit=True)
        with admin.cursor() as cur:
            cur.execute("""
                CREATE TABLE venue_corpus (
                    qid VARCHAR(20) PRIMARY KEY,
                    venue_name TEXT NOT NULL,
                    official_url TEXT,
                    canonical_titles_json JSONB NOT NULL,
                    story_elements_json JSONB,
                    sparql_works_json JSONB,
                    pages_json JSONB,
                    language VARCHAR(10),
                    tier VARCHAR(10) NOT NULL,
                    corpus_version INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                )
            """)
            cur.execute("""
                INSERT INTO venue_corpus
                    (qid, venue_name, canonical_titles_json, tier, corpus_version, expires_at)
                VALUES ('Q1', 'Arnold Arboretum', '[]'::jsonb, 'thin', 7, NOW() + INTERVAL '1 day')
            """)
        admin.close()

    def test_ensure_table_not_blocked_by_idle_reader(self):
        """With an idle-in-transaction reader holding venue_corpus and the tier
        narrower than 20, _ensure_table must return fast (ALTER skipped), and a
        third connection's SELECT must not be blocked."""
        self._seed_venue_corpus_narrow_tier()

        # Connection A: open a read transaction and STAY idle (holds AccessShare).
        reader = _connect(self.dsn, autocommit=False)
        rcur = reader.cursor()
        rcur.execute("SELECT count(*) FROM venue_corpus")
        rcur.fetchall()
        # Do NOT commit — reader is now idle in transaction holding a lock.

        try:
            # Connection B: _ensure_table (via _get_db_connection) must NOT hang.
            t0 = time.time()
            conn_b = self.vr._get_db_connection()
            self.assertIsNotNone(conn_b, "could not open venue_resolver connection")
            elapsed = time.time() - t0
            self.assertLess(
                elapsed, 8.0,
                f"_ensure_table took {elapsed:.1f}s — the ALTER blocked behind the "
                f"idle reader (the LOCAL-797 freeze)")

            # Connection C: a plain SELECT must not be blocked either.
            conn_c = _connect(self.dsn, autocommit=True)
            t1 = time.time()
            with conn_c.cursor() as cur:
                cur.execute("SELECT count(*) FROM venue_corpus")
                cur.fetchone()
            self.assertLess(time.time() - t1, 5.0, "SELECT on C was blocked")
            conn_c.close()
            conn_b.close()
        finally:
            try:
                reader.rollback()
                reader.close()
            except Exception:
                pass

    def test_ensure_table_issues_no_alter_when_tier_already_wide(self):
        """On a table whose tier is already VARCHAR(20), _ensure_table issues NO
        ALTER (the needed-check short-circuits)."""
        # Let _ensure_table build the table fresh (CREATE makes tier VARCHAR(20)).
        conn = self.vr._get_db_connection()
        self.assertIsNotNone(conn)
        conn.close()

        # Confirm tier is VARCHAR(20).
        admin = _connect(self.dsn, autocommit=True)
        with admin.cursor() as cur:
            cur.execute(
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_name='venue_corpus' AND column_name='tier'")
            self.assertEqual(cur.fetchone()[0], 20)

        # Now run the exact ALTER through safe_ddl with the same needed_check the
        # product code uses; it must SKIP (return False), proving no ALTER fires.
        self.vr._TABLE_ENSURED = False
        ran = db_safe_ddl.safe_ddl(
            admin,
            "ALTER TABLE venue_corpus ALTER COLUMN tier TYPE VARCHAR(20)",
            needed_check_sql=(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'venue_corpus' AND column_name = 'tier' "
                "AND (character_maximum_length IS NULL "
                "     OR character_maximum_length < 20)"
            ),
            label="LOCAL-797",
        )
        self.assertFalse(ran, "ALTER fired even though tier was already VARCHAR(20)")
        admin.close()

    def test_safe_ddl_skips_and_continues_under_lock_contention(self):
        """safe_ddl on a table locked ACCESS EXCLUSIVE by another session gives up
        within its lock_timeout and returns False without raising."""
        self._seed_venue_corpus_narrow_tier()

        # Holder: take an ACCESS EXCLUSIVE lock on venue_corpus and keep it.
        holder = _connect(self.dsn, autocommit=False)
        hcur = holder.cursor()
        hcur.execute("LOCK TABLE venue_corpus IN ACCESS EXCLUSIVE MODE")
        # Lock held until we roll back.

        victim = _connect(self.dsn, autocommit=True)
        try:
            t0 = time.time()
            ran = db_safe_ddl.safe_ddl(
                victim,
                "ALTER TABLE venue_corpus ALTER COLUMN tier TYPE VARCHAR(20)",
                needed_check_sql=None,  # force the DDL attempt
                lock_timeout="2s",
                label="LOCAL-797",
            )
            elapsed = time.time() - t0
            self.assertFalse(ran, "DDL claimed success while the table was locked")
            self.assertLess(elapsed, 8.0,
                            f"safe_ddl waited {elapsed:.1f}s — lock_timeout not applied")
            self.assertGreater(elapsed, 1.0,
                               "safe_ddl returned instantly — did it even attempt the DDL?")
        finally:
            victim.close()
            try:
                holder.rollback()
                holder.close()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
