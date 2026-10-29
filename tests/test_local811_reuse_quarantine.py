#!/usr/bin/env python3
"""LOCAL-811 — reuse-path museum quarantine (DB-backed).

Proves, against a throwaway Postgres schema, that the orchestrator's
``_auto_reject_museum_stops`` (the pooled-stop equivalent of the fresh-path
LOCAL-809 guards):

  1. MOVES a pooled Belvedere row that is a foreign work (P195 excludes the venue)
     out of the pool, and a Met gift-shop row, and a disambiguation-body row;
  2. KEEPS a genuine in-collection stop in the pool;
  3. does the move through the verified ``move_to_rejected`` — the moved rows land
     in ``stop_pool_rejected`` and are gone from ``stop_pool``, so a later reuse
     read never serves them and the N>K path researches the remainder fresh.

Backed by a real throwaway Postgres (same pattern as test_local792): the move SQL
uses unnest / INSERT…SELECT, which only Postgres provides. Connects to
LOCAL811_TEST_DB_URL / LOCAL792_TEST_DB_URL / DATABASE_URL; SKIPS when none is
reachable. Each test runs in a uniquely-named transient schema.
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


_DB_URL = (os.environ.get("LOCAL811_TEST_DB_URL")
           or os.environ.get("LOCAL792_TEST_DB_URL")
           or os.environ.get("DATABASE_URL"))

_LOCATION = "Belvedere Museum, Vienna, Austria"
_TOUR_TYPE = "museum"
_VENUE_QID = "Q303139"

# The Belvedere's OWN works (Klimt), as a venue SPARQL/cache set carries them.
_BELVEDERE_WORKS = [
    {"label_en": "The Kiss", "collection_qids": [_VENUE_QID],
     "instance_of": ["Q3305213"], "creator": "Gustav Klimt"},
]


def _connect_or_skip():
    if not _DB_URL:
        pytest.skip("no LOCAL811_TEST_DB_URL / LOCAL792_TEST_DB_URL / DATABASE_URL")
    try:
        return psycopg2.connect(_DB_URL)
    except Exception as e:  # pragma: no cover
        pytest.skip(f"test Postgres unreachable: {e}")


@pytest.fixture()
def conn():
    c = _connect_or_skip()
    schema = "l811_" + uuid.uuid4().hex[:12]
    with c.cursor() as cur:
        cur.execute(f'CREATE SCHEMA "{schema}"')
        cur.execute(f'SET search_path TO "{schema}"')
    c.commit()
    rej.ensure_table(c)
    yield c
    try:
        with c.cursor() as cur:
            cur.execute(f'DROP SCHEMA "{schema}" CASCADE')
        c.commit()
    finally:
        c.close()


def _key(title):
    ident = pool.venue_identity(_LOCATION)
    return pool._pool_key(ident, _TOUR_TYPE), pool._title_norm(title)


def _insert(conn, title, narration="body", artist="", raw_block=""):
    pk, tn = _key(title)
    ident = pool.venue_identity(_LOCATION)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO stop_pool (
                pool_key, title_norm, venue_identity, tour_type, pool_version,
                title, artist, narration, raw_block, order_seq
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (pool_key, title_norm) DO NOTHING
            """,
            (pk, tn, ident, _TOUR_TYPE, pool.POOL_VERSION, title, artist,
             narration, raw_block, 0),
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


def _current_schema(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT current_schema()")
        schema = cur.fetchone()[0]
    conn.commit()
    return schema


def _route_rej_connect(monkeypatch, schema):
    """Route stop_pool_rejected's own psycopg2.connect into OUR transient schema
    (auto_reject_rows / move_to_rejected open their own connection to _DB_URL)."""
    _real = psycopg2.connect

    def _connect(*a, **k):
        c = _real(*a, **k)
        with c.cursor() as cur:
            cur.execute(f'SET search_path TO "{schema}"')
        c.commit()
        return c

    monkeypatch.setattr(rej.psycopg2, "connect", _connect)


def _stub_venue_works(monkeypatch, works=_BELVEDERE_WORKS, parents=()):
    """Avoid any network: the orchestrator's venue-works lookup returns our fake
    Belvedere set. is_art_museum is forced True (an art museum)."""
    monkeypatch.setattr(orch, "_venue_works_for_membership",
                        lambda qid: (list(works), tuple(parents)))
    import generate_tour_text as g
    monkeypatch.setattr(g, "_is_art_museum", lambda venue, w=None: True)


class TestReuseMuseumQuarantine:
    def test_foreign_and_shop_and_disambig_moved_good_kept(self, conn, monkeypatch):
        good = "The Kiss"                       # in the Belvedere → kept
        # [LOCAL-811B] Monet's "Portrait of Père Paul" IS in the Belvedere (LEAD
        # correction), so a truly foreign work is used: Leonardo's "Mona Lisa"
        # (Louvre, Q19675) — a unique painting that cannot be in the Belvedere.
        mona = "Mona Lisa"                      # Leonardo, Louvre → wrong_collection
        shop = "Starry Night Mug — The Met Store"  # merchandise → shop/junk
        disambig = "Belvedere Palace"           # disambiguation body

        _insert(conn, good, artist="Gustav Klimt",
                narration="Klimt painted this between 1907 and 1908.")
        _insert(conn, mona, artist="Leonardo da Vinci", narration="Leonardo's portrait.")
        _insert(conn, shop, narration="A ceramic mug.")
        _insert(conn, disambig,
                narration="Belvedere may refer to: a palace, a place, a ship.")
        assert _pool_count(conn) == 4

        schema = _current_schema(conn)
        _route_rej_connect(monkeypatch, schema)

        # The Mona Lisa row must carry a foreign P195 for the wrong_collection reject
        # — supply it the way a freshly-researched stop_record would (via rows).
        rows = [
            {"title": good, "artist": "Gustav Klimt",
             "narration": "Klimt painted this between 1907 and 1908."},
            {"title": mona, "artist": "Leonardo da Vinci", "narration": "Leonardo's portrait.",
             "stop_record": {"collection_qids": ["Q19675"], "instance_of": ["Q3305213"]}},
            {"title": shop, "narration": "A ceramic mug.",
             "sources": ["https://store.metmuseum.org/products/x"]},
            {"title": disambig,
             "narration": "Belvedere may refer to: a palace, a place, a ship."},
        ]
        _stub_venue_works(monkeypatch)

        kept = orch._auto_reject_museum_stops(
            rows, _LOCATION, _TOUR_TYPE, _DB_URL, qid=_VENUE_QID)

        kept_titles = [r["title"] for r in kept]
        assert good in kept_titles
        assert mona not in kept_titles
        assert shop not in kept_titles
        assert disambig not in kept_titles

        # The three bad rows were quarantined; the good one stays in the pool.
        assert _pool_count(conn) == 1
        assert _rej_count(conn) == 3
        with conn.cursor() as cur:
            cur.execute("SELECT title FROM stop_pool")
            assert cur.fetchone()[0] == good
            cur.execute("SELECT reject_reason, rejected_by FROM stop_pool_rejected")
            for reason, by in cur.fetchall():
                assert by == "auto:pool_museum_checks"
                assert reason.startswith("auto:local811:")

    def test_all_good_rows_untouched(self, conn, monkeypatch):
        good = "The Kiss"
        _insert(conn, good, artist="Gustav Klimt", narration="Klimt, 1907-08.")
        assert _pool_count(conn) == 1

        schema = _current_schema(conn)
        _route_rej_connect(monkeypatch, schema)
        _stub_venue_works(monkeypatch)

        rows = [{"title": good, "artist": "Gustav Klimt",
                 "narration": "Klimt, 1907-08."}]
        kept = orch._auto_reject_museum_stops(
            rows, _LOCATION, _TOUR_TYPE, _DB_URL, qid=_VENUE_QID)
        assert [r["title"] for r in kept] == [good]
        assert _pool_count(conn) == 1
        assert _rej_count(conn) == 0

    def test_rejected_row_not_returned_by_reuse_read(self, conn, monkeypatch):
        # After the move, a reuse read (get_pool_stops) must never return the
        # quarantined stop — the N>K path then researches the remainder fresh.
        good = "The Kiss"
        mona = "Mona Lisa"  # [LOCAL-811B] Louvre — truly foreign to the Belvedere
        _insert(conn, good, artist="Gustav Klimt", narration="Klimt.")
        _insert(conn, mona, artist="Leonardo da Vinci", narration="Leonardo.")

        schema = _current_schema(conn)
        _route_rej_connect(monkeypatch, schema)
        _stub_venue_works(monkeypatch)

        rows = [
            {"title": good, "artist": "Gustav Klimt", "narration": "Klimt."},
            {"title": mona, "artist": "Leonardo da Vinci", "narration": "Leonardo.",
             "stop_record": {"collection_qids": ["Q19675"], "instance_of": ["Q3305213"]}},
        ]
        orch._auto_reject_museum_stops(rows, _LOCATION, _TOUR_TYPE, _DB_URL,
                                       qid=_VENUE_QID)

        # Route the store's connection into our schema and read back.
        import stop_pool_store as _store
        _real = psycopg2.connect

        def _connect(*a, **k):
            c = _real(*a, **k)
            with c.cursor() as cur:
                cur.execute(f'SET search_path TO "{schema}"')
            c.commit()
            return c

        monkeypatch.setattr(_store.psycopg2, "connect", _connect)
        stops = pool.get_pool_stops(_LOCATION, _TOUR_TYPE, _DB_URL, qid=_VENUE_QID)
        titles = [s["title"] for s in stops]
        assert good in titles
        assert mona not in titles
