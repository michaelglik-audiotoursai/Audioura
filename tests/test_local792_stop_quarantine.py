#!/usr/bin/env python3
"""LOCAL-792 / D726 — stop quarantine unit tests.

The ticket's four required properties:
  1. a rejected row is NEVER returned by any reuse path (get_pool_stops, and the
     LOCAL-778 existing-tour miner);
  2. ``reject_stops.py --restore`` brings the row back INTACT;
  3. a SCOPE (distance) failure does NOT move the row — it is skip-only (LOCAL-788);
  4. a copy-count mismatch ABORTS the transaction (no stop_pool row is removed
     without a verified copy).

Backed by a real throwaway Postgres (the move/restore SQL uses unnest / to_regclass
/ INSERT…SELECT, which only Postgres provides). The test connects to
LOCAL792_TEST_DB_URL (or DATABASE_URL); if neither is reachable it SKIPS — so the
suite stays green where no DB is available, and runs for real where one is.

Each test uses a uniquely-named transient schema (search_path) so the tables never
collide with anything in the target database, and drops it in teardown.
"""
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

psycopg2 = pytest.importorskip("psycopg2")

import stop_pool_store as pool
import stop_pool_rejected as rej
import stop_pool_orchestrator as orch


_DB_URL = os.environ.get("LOCAL792_TEST_DB_URL") or os.environ.get("DATABASE_URL")


def _connect_or_skip():
    if not _DB_URL:
        pytest.skip("no LOCAL792_TEST_DB_URL / DATABASE_URL for the DB-backed tests")
    try:
        return psycopg2.connect(_DB_URL)
    except Exception as e:  # pragma: no cover
        pytest.skip(f"test Postgres unreachable: {e}")


@pytest.fixture()
def conn():
    c = _connect_or_skip()
    schema = "l792_" + uuid.uuid4().hex[:12]
    with c.cursor() as cur:
        cur.execute(f'CREATE SCHEMA "{schema}"')
        cur.execute(f'SET search_path TO "{schema}"')
    c.commit()
    # Build the tables in the isolated schema.
    rej.ensure_table(c)
    yield c
    try:
        with c.cursor() as cur:
            cur.execute(f'DROP SCHEMA "{schema}" CASCADE')
        c.commit()
    finally:
        c.close()


# ── helpers ───────────────────────────────────────────────────────────────────

_LOCATION = "War Remnants Museum, Ho Chi Minh City"
_TOUR_TYPE = "museum"


def _key(title):
    ident = pool.venue_identity(_LOCATION)
    return pool._pool_key(ident, _TOUR_TYPE), pool._title_norm(title)


def _insert_pool_stop(conn, title, coordinates="", address="", narration="body"):
    pk, tn = _key(title)
    ident = pool.venue_identity(_LOCATION)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO stop_pool (
                pool_key, title_norm, venue_identity, tour_type, pool_version,
                title, narration, address, coordinates, order_seq
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (pool_key, title_norm) DO NOTHING
            """,
            (pk, tn, ident, _TOUR_TYPE, pool.POOL_VERSION, title, narration,
             address, coordinates, 0),
        )
    conn.commit()
    return pk, tn


def _pool_count(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM stop_pool")
        return cur.fetchone()[0]


def _rej_count(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM stop_pool_rejected")
        return cur.fetchone()[0]


# ── 1. a rejected row is never returned by a reuse read ─────────────────────────

class TestRejectedNeverReused:
    def test_get_pool_stops_excludes_rejected(self, conn, monkeypatch):
        good = "Independence Palace"
        bad = "Interesting"
        _insert_pool_stop(conn, good, coordinates="10.777, 106.695")
        _insert_pool_stop(conn, bad)
        # Reject the bad stop.
        moved = rej.move_to_rejected(conn, [_key(bad)],
                                     reason="fabricated", rejected_by="test")
        conn.commit()
        assert moved == 1

        # get_pool_stops opens its OWN connection to _DB_URL; point it at the same
        # schema by giving it a db_url whose options set the search_path. Simplest:
        # monkeypatch psycopg2.connect inside the store to return a cursor on OUR
        # schema. We do that by wrapping connect to also SET search_path.
        _schema = _current_schema(conn)
        _patch_store_connect(monkeypatch, _schema)

        stops = pool.get_pool_stops(_LOCATION, _TOUR_TYPE, _DB_URL)
        titles = [s["title"] for s in stops]
        assert good in titles
        assert bad not in titles, "a rejected stop must never be returned by reuse"

    def test_miner_skips_rejected(self, conn, monkeypatch):
        bad = "Interesting"
        _insert_pool_stop(conn, bad)
        rej.move_to_rejected(conn, [_key(bad)], reason="fabricated",
                             rejected_by="test")
        conn.commit()
        ident = pool.venue_identity(_LOCATION)
        norms = rej.rejected_norms_by_identity(conn, ident)
        assert pool._title_norm(bad) in norms


# ── 2. --restore brings the row back intact ─────────────────────────────────────

class TestRestore:
    def test_restore_round_trip_intact(self, conn):
        title = "Independence Palace"
        coords = "10.7772, 106.6958"
        addr = "135 Nam Ky Khoi Nghia, HCMC"
        _insert_pool_stop(conn, title, coordinates=coords, address=addr,
                          narration="a real palace")
        before = _snapshot(conn, title)

        rej.move_to_rejected(conn, [_key(title)], reason="wrong venue",
                             rejected_by="test", source_tour_id=463)
        conn.commit()
        assert _pool_count(conn) == 0
        assert _rej_count(conn) == 1

        restored = rej.restore_from_rejected(conn, [_key(title)])
        conn.commit()
        assert restored == 1
        assert _pool_count(conn) == 1
        assert _rej_count(conn) == 0

        after = _snapshot(conn, title)
        assert after == before, "restored row must be byte-identical to the original"


# ── 3. a scope failure does NOT move the row ────────────────────────────────────

class TestScopeFailureDoesNotMove:
    def test_revalidate_scope_never_rejects_from_pool(self, conn, monkeypatch):
        # A far-away place is dropped from THIS tour by LOCAL-788, but the pool row
        # must remain (it is good material for the tour it belongs to).
        far = "Byblos Restaurant"
        _insert_pool_stop(conn, far, coordinates="42.1945, -71.1997",
                          address="678 Washington St, Norwood, MA")
        assert _pool_count(conn) == 1

        # Force the LOCAL-788 scope gate to reject the row (geocode to a far scope).
        monkeypatch.setattr(orch, "_geocode_scope",
                            lambda location: ((42.2843, -71.1627),
                                              ["42.255", "42.302", "-71.185", "-71.135"]))
        rows = [{"title": far, "coordinates": "42.1945, -71.1997",
                 "address": "678 Washington St, Norwood, MA"}]
        kept, rejected = orch._revalidate_pooled_scope(
            rows, "West Roxbury, MA", "restaurant", contained=False)
        assert rejected == 1
        assert [r["title"] for r in kept] == []
        # The crucial assertion: the pool row was NOT moved/removed.
        assert _pool_count(conn) == 1
        assert _rej_count(conn) == 0


# ── 4. a copy-count mismatch aborts the transaction ─────────────────────────────

class TestCopyCountMismatchAborts:
    def test_mismatch_raises_and_pool_unchanged(self, conn):
        title = "Independence Palace"
        _insert_pool_stop(conn, title, coordinates="10.777, 106.695")
        assert _pool_count(conn) == 1

        # Wrap the connection so the VERIFY-count query returns a too-low number,
        # simulating a copy that did not fully land. move_to_rejected must raise
        # BEFORE any delete; the caller rolls back; the pool row survives.
        wrapped = _MismatchConn(conn)
        with pytest.raises(RuntimeError):
            rej.move_to_rejected(wrapped, [_key(title)], reason="x",
                                 rejected_by="test")
        conn.rollback()
        assert _pool_count(conn) == 1, "no stop_pool row may be removed on a mismatch"


# ── 5. automatic junk/other-venue reject moves it out; good stop stays ──────────

class TestAutoRejectJunkTitles:
    def test_junk_title_moved_good_kept(self, conn, monkeypatch):
        good = "Independence Palace"
        junk = "Profile « War Remnants Museum"   # page-chrome breadcrumb
        _insert_pool_stop(conn, good, coordinates="10.777, 106.695")
        _insert_pool_stop(conn, junk)
        assert _pool_count(conn) == 2

        # auto_reject_rows opens its own connection to _DB_URL; route it to OUR
        # schema the same way get_pool_stops is routed.
        schema = _current_schema(conn)
        import stop_pool_rejected as _rej_mod
        _real = psycopg2.connect

        def _connect(*a, **k):
            c = _real(*a, **k)
            with c.cursor() as cur:
                cur.execute(f'SET search_path TO "{schema}"')
            c.commit()
            return c

        monkeypatch.setattr(_rej_mod.psycopg2, "connect", _connect)

        good_row = {"title": good, "coordinates": "10.777, 106.695"}
        junk_row = {"title": junk}
        kept = orch._auto_reject_junk_titles(
            [good_row, junk_row], _LOCATION, _TOUR_TYPE, _DB_URL)

        kept_titles = [r["title"] for r in kept]
        assert good in kept_titles
        assert junk not in kept_titles, "a junk-title stop must be dropped from the tour"
        # And the junk stop was quarantined out of the pool (good stop remains).
        assert _pool_count(conn) == 1
        assert _rej_count(conn) == 1
        with conn.cursor() as cur:
            cur.execute("SELECT title, reject_reason, rejected_by "
                        "FROM stop_pool_rejected")
            t, reason, by = cur.fetchone()
        assert t == junk
        assert "junk" in (reason or "").lower()
        assert by == "auto:junk_title_guard"


# ── tiny infra ──────────────────────────────────────────────────────────────────

def _current_schema(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT current_schema()")
        schema = cur.fetchone()[0]
    # [LEAD 19:3x] COMMIT before the code under test opens its OWN connection: an
    # open transaction here (seeded rows) holds a lock on stop_pool, and the store's
    # runtime ALTER TABLE … ADD COLUMN IF NOT EXISTS then waits forever (2 h hang).
    conn.commit()
    return schema


def _patch_store_connect(monkeypatch, schema):
    """Make stop_pool_store's psycopg2.connect land in OUR transient schema."""
    import stop_pool_store as _store
    _real = psycopg2.connect

    def _connect(*a, **k):
        c = _real(*a, **k)
        with c.cursor() as cur:
            cur.execute(f'SET search_path TO "{schema}"')
        c.commit()
        return c

    monkeypatch.setattr(_store.psycopg2, "connect", _connect)


def _snapshot(conn, title):
    _, tn = _key(title)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT " + ", ".join(rej.POOL_COLUMNS) + " FROM stop_pool "
            "WHERE title_norm = %s", (tn,))
        return cur.fetchone()


class _MismatchCursor:
    """A cursor proxy that under-reports the VERIFY count query so the copy check
    fails. Every other call passes through to the real cursor."""
    def __init__(self, real):
        self._real = real
        self._last_was_verify = False

    def execute(self, sql, params=None):
        self._last_was_verify = (
            "SELECT COUNT(*) FROM stop_pool_rejected r" in sql
            and "unnest" in sql)
        return self._real.execute(sql, params)

    def fetchone(self):
        row = self._real.fetchone()
        if self._last_was_verify:
            return (0,)  # pretend nothing was copied → force the mismatch raise
        return row

    @property
    def rowcount(self):
        return self._real.rowcount

    def __enter__(self):
        self._real.__enter__()
        return self

    def __exit__(self, *a):
        return self._real.__exit__(*a)


class _MismatchConn:
    def __init__(self, real):
        self._real = real

    def cursor(self):
        return _MismatchCursor(self._real.cursor())

    def commit(self):
        return self._real.commit()

    def rollback(self):
        return self._real.rollback()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
