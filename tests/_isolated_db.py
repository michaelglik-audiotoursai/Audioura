#!/usr/bin/env python3
"""tests/_isolated_db.py — shared throwaway-schema DB isolation (LOCAL-601).

Why this exists
===============
Several DB-touching tests used to write into the SHARED/production tables
(`public.stop_pool`, `public.audio_tours`, …). The worst offender,
``test_local590_orchestrator.py``, stored a fresh ``loc:zz_isolated_*`` venue on
every run through ``stop_pool_store.store_delivered_tour`` and never cleaned up,
so the dev Postgres ``stop_pool`` (the one Michael's phone reads) accumulated
hundreds of test rows — 927 of them by 2026-10-06.

LOCAL-597B solved the identical problem for the by-reference suite with a
**private throwaway schema**: route every connection in the process at a schema
whose tables shadow ``public`` via ``PGOPTIONS=-c search_path=<schema>,public``,
then ``DROP SCHEMA … CASCADE`` in teardown. No row ever lands in ``public``.
This module extracts that mechanism verbatim so any suite can reuse it in two
lines, instead of re-inlining ~120 lines of fragile schema plumbing.

The mechanism (unchanged from 597B)
===================================
``PGOPTIONS`` is read by libpq for EVERY new connection in the process — the
ones a test opens directly AND the ones production modules open internally
(``stop_pool_store``, ``subscription_levels``, ``l2_by_reference`` …). With the
throwaway schema first on the ``search_path``, an unqualified ``stop_pool`` /
``audio_tours`` / ``device_entitlement`` / ``tour_requests`` / ``users`` resolves
to the schema copy; ``public`` is never written. The schema's tables are created
``LIKE public.<t> INCLUDING ALL`` so they are byte-compatible with the exact
INSERTs/UPSERTs the production code issues (defaults, PK/unique for ON CONFLICT,
indexes). Teardown drops the schema and PROVES ``public`` row counts for the
proof tables are identical before and after — a hard assertion, not a hope.

Usage (unittest module-level)
=============================
    from _isolated_db import IsolatedSchema   # tests/ is on sys.path

    _ISO = IsolatedSchema(
        prefix="t590",
        clone_tables=["stop_pool", "audio_tours", "users"],
        proof_tables=["stop_pool", "audio_tours"],
        banner="LOCAL-590",
    )

    def setUpModule():
        _ISO.setup()        # no-op + classes SKIP if DB is down

    def tearDownModule():
        _ISO.teardown()     # drops schema, asserts public unchanged, prints proof

    # Gate DB classes on the DB being reachable:
    @unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
    class TestX(unittest.TestCase): ...

Resolving the database
======================
By default the helper resolves the connection from ``db_connection.get_db_config``
(so under pytest it targets ``audiotours_test`` — never production). A caller that
builds its own URL (e.g. a repo-root script-style test) can pass ``db_url=`` and
the helper will parse host/port/dbname/user/password from it, so the proof
connection and the schema admin connection target the SAME database the code
under test writes to.

No DELETE anywhere: cleanup is exclusively ``DROP SCHEMA … CASCADE``. There is no
name-pattern or date-range delete, and ``public`` is never mutated.
"""
import os
import sys
import uuid
from urllib.parse import urlparse, unquote

import psycopg2


def _config_from_url(db_url):
    """Parse a postgresql:// URL into a psycopg2 kwargs dict."""
    p = urlparse(db_url)
    return {
        "host": p.hostname or "localhost",
        "port": str(p.port or 5432),
        "dbname": (p.path or "/").lstrip("/") or "postgres",
        "user": unquote(p.username) if p.username else "postgres",
        "password": unquote(p.password) if p.password else "",
    }


def _config_from_db_connection():
    """Resolve the config via the repo's db_connection helper, if importable.

    Ensures the tests/ dir and repo root are both importable so this works for
    modules living either place.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    for p in (here, root):
        if p not in sys.path:
            sys.path.insert(0, p)
    from db_connection import get_db_config  # noqa: E402
    return dict(get_db_config())


class IsolatedSchema:
    """A throwaway Postgres schema that shadows ``public`` for the duration of a
    test module, created from ``LIKE public.<t> INCLUDING ALL`` clones and dropped
    (CASCADE) in teardown, with a before/after ``public`` row-count proof.

    Parameters
    ----------
    prefix:
        Short identifier folded into the schema name (``<prefix>_<uuid12>``).
    clone_tables:
        Tables to mirror into the throwaway schema. Must include every table the
        code under test writes (directly or via CASCADE) so no write escapes to
        ``public``.
    proof_tables:
        Tables whose ``public`` row counts must be identical before and after.
        Defaults to ``clone_tables``.
    db_url:
        Optional explicit connection URL. When omitted, the connection is
        resolved from ``db_connection.get_db_config`` (``audiotours_test`` under
        pytest).
    banner:
        Label used in the printed proof line.
    """

    def __init__(self, prefix, clone_tables, proof_tables=None, db_url=None,
                 banner="isolated"):
        self.prefix = prefix
        self.clone_tables = list(clone_tables)
        self.proof_tables = list(proof_tables) if proof_tables else list(clone_tables)
        self._db_url = db_url
        self.banner = banner

        self.schema = None            # set in setup()
        self._prev_pgoptions = None   # saved PGOPTIONS, restored in teardown()
        self._counts_before = {}      # public.<t> counts captured before any test

    # ── connection helpers ──────────────────────────────────────────────────
    def _config(self):
        if self._db_url:
            return _config_from_url(self._db_url)
        return _config_from_db_connection()

    def _admin_connect(self):
        """A connection with the DEFAULT search_path (public), for schema admin
        and for reading public row counts. Deliberately does NOT inherit
        PGOPTIONS (so it always sees ``public``, never the throwaway schema)."""
        cfg = self._config()
        saved = os.environ.pop("PGOPTIONS", None)
        try:
            return psycopg2.connect(
                host=cfg["host"], port=cfg["port"], dbname=cfg["dbname"],
                user=cfg["user"], password=cfg["password"], connect_timeout=5,
            )
        finally:
            if saved is not None:
                os.environ["PGOPTIONS"] = saved

    def db_up(self):
        try:
            c = self._admin_connect()
            c.close()
            return True
        except Exception:
            return False

    def _public_counts(self):
        counts = {}
        conn = self._admin_connect()
        try:
            with conn.cursor() as cur:
                for t in self.proof_tables:
                    cur.execute(f"SELECT COUNT(*) FROM public.{t}")
                    counts[t] = cur.fetchone()[0]
        finally:
            conn.close()
        return counts

    # ── lifecycle ────────────────────────────────────────────────────────────
    def setup(self):
        """Create the throwaway schema, mirror ``clone_tables`` into it, and route
        every connection in this process at it via PGOPTIONS. Captures the public
        proof counts first. No-op when the DB is unreachable (classes SKIP)."""
        if not self.db_up():
            return  # DB classes will SKIP; nothing to set up.

        self._counts_before = self._public_counts()

        self.schema = f"{self.prefix}_{uuid.uuid4().hex[:12]}"
        conn = self._admin_connect()
        try:
            with conn.cursor() as cur:
                cur.execute(f'CREATE SCHEMA "{self.schema}"')
                for t in self.clone_tables:
                    # INCLUDING ALL copies columns, defaults, PK/unique/indexes so
                    # the copy accepts the exact INSERTs the code issues (notably
                    # ON CONFLICT targets like device_entitlement.user_id).
                    cur.execute(
                        f'CREATE TABLE "{self.schema}".{t} '
                        f'(LIKE public.{t} INCLUDING ALL)'
                    )
            conn.commit()  # explicit — a guarded connection wrapper may not
                           # delegate the autocommit attribute to the real conn.
        finally:
            conn.close()

        # Route EVERY subsequent connection (direct and module-internal) at the
        # throwaway schema. public stays as fallback so shared types/functions
        # resolve, but our cloned tables shadow public.
        self._prev_pgoptions = os.environ.get("PGOPTIONS")
        os.environ["PGOPTIONS"] = f"-c search_path={self.schema},public"

    def teardown(self):
        """Drop the throwaway schema and PROVE public row counts are unchanged."""
        # Restore PGOPTIONS first so the admin connection targets public.
        if self._prev_pgoptions is None:
            os.environ.pop("PGOPTIONS", None)
        else:
            os.environ["PGOPTIONS"] = self._prev_pgoptions

        if self.schema is None:
            return  # DB was down; nothing created.

        conn = self._admin_connect()
        try:
            with conn.cursor() as cur:
                cur.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
            conn.commit()
        finally:
            conn.close()
        self.schema = None

        after = self._public_counts()
        print(f"\n[{self.banner}] public row counts before/after "
              f"(must be identical):")
        drift = {}
        for t in self.proof_tables:
            b, a = self._counts_before.get(t), after.get(t)
            print(f"  public.{t:20} before={b:<8} after={a}")
            if b != a:
                drift[t] = (b, a)
        assert not drift, (
            f"PRODUCTION ROW DRIFT (isolation failed): {drift}. "
            f"A write escaped the throwaway schema into public.")
        print(f"[{self.banner}] OK — zero shared/production writes.")

    # Convenience so a `with` block can be used in non-unittest contexts.
    def __enter__(self):
        self.setup()
        return self

    def __exit__(self, *exc):
        self.teardown()
        return False
