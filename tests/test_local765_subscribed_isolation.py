#!/usr/bin/env python3
"""test_local765_subscribed_isolation.py — LOCAL-765 verification tests.

Backport of LOCAL-727 track isolation to `storied`, extended with the
read-path rule LOCAL-765 adds: **Storied must never serve or reuse a
Subscribed tour.**

After the Subscribed → GCloud Cloud SQL move (D708), Subscribed shares the
Beta/Storied database and writes ``track = 'subscribed'``. This suite proves,
against an ISOLATED throwaway schema (never the shared DB, zero production
writes, no generation, no DELETE on real rows), that on storied-side code:

  WRITE PATH (tour_orchestrator_service.store_audio_tour)
    1. a same-name ``track='subscribed'`` original is NOT reused by a Storied
       store — Storied inserts its OWN row (the LOCAL-432 collapse bug, now
       scoped by track).
    2. a same-name ``track='beta'`` / ``track='storied'`` pair still behaves as
       today (same-track regeneration reuses the one row).

  READ PATHS (the exact SQL the storied services run)
    3. /tours-near and /search-tours exclude ``track='subscribed'`` rows.
    4. /download-tour, /tour-info, /tour/<id>/resolve, /tour-by-code and
       tour-id resolution of a ``track='subscribed'`` id return NOTHING
       (the handler turns that into a 404).

RED on origin/storied: the orchestrator lookup is keyed on ``lower(tour_name)``
only (no track), so (1) reuses the subscribed row; the read queries have no
track predicate, so (3)/(4) surface subscribed rows. GREEN after the fix.

Isolation: the suite connects to a SCRATCH Postgres (LOCAL-765 env vars below,
defaulting to the `-p local765` scratch container on port 5465) and creates a
UNIQUELY NAMED throwaway table set in a temporary schema that it drops at the
end. It never writes to `audio_tours` in a shared database. If the scratch DB
is unreachable it exits 7 (needs-services), matching tests/db_connection.py.
"""
import os
import sys
import uuid
import unittest

EXIT_DB_UNREACHABLE = 7

# Scratch DB connection — LOCAL-765 vars win, then generic DB_* , then the
# local765 scratch defaults. NEVER defaults to the shared 5433/5432 prod DB
# name 'audiotours'; the throwaway schema makes the target harmless regardless.
_SCRATCH = {
    "host": os.getenv("LOCAL765_DB_HOST", os.getenv("DB_HOST", "localhost")),
    "port": os.getenv("LOCAL765_DB_PORT", os.getenv("DB_PORT", "5465")),
    "dbname": os.getenv("LOCAL765_DB_NAME", os.getenv("DB_NAME", "audiotours_local765")),
    "user": os.getenv("LOCAL765_DB_USER", os.getenv("DB_USER", "admin")),
    "password": os.getenv("LOCAL765_DB_PASSWORD", os.getenv("DB_PASSWORD", "password123")),
}

# A throwaway schema this run owns end-to-end. Dropped in tearDownModule.
_SCHEMA = "local765_" + uuid.uuid4().hex[:12]


def _connect():
    import psycopg2
    return psycopg2.connect(
        host=_SCRATCH["host"], port=_SCRATCH["port"], dbname=_SCRATCH["dbname"],
        user=_SCRATCH["user"], password=_SCRATCH["password"], connect_timeout=5,
    )


def _try_connect_or_skip():
    try:
        import psycopg2  # noqa: F401
    except Exception as e:
        print(f"[LOCAL-765] psycopg2 unavailable: {e}")
        sys.exit(EXIT_DB_UNREACHABLE)
    try:
        conn = _connect()
        conn.close()
    except Exception as e:
        print(f"[LOCAL-765] scratch Postgres unreachable "
              f"({_SCRATCH['host']}:{_SCRATCH['port']}/{_SCRATCH['dbname']}): {e}")
        print("[LOCAL-765] start a scratch DB, e.g. "
              "`docker run --rm -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=password123 "
              "-e POSTGRES_DB=audiotours_local765 -p 5465:5432 -d postgres:13`")
        sys.exit(EXIT_DB_UNREACHABLE)


# Minimal audio_tours shape the storied code touches. Mirrors the self-healing
# columns in tour_orchestrator_service / map_delivery_service. `track` defaults
# to 'beta' exactly like the production self-heal.
_DDL = """
CREATE SCHEMA IF NOT EXISTS {schema};
SET search_path TO {schema};
CREATE TABLE audio_tours (
    id SERIAL PRIMARY KEY,
    tour_name VARCHAR(255) NOT NULL,
    request_string TEXT,
    audio_tour BYTEA,
    tour_blob_uri TEXT,
    number_requested INTEGER NOT NULL DEFAULT 0,
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    tour_content TEXT,
    content_language VARCHAR(8) DEFAULT 'en',
    language VARCHAR(8) DEFAULT 'en',
    storied_mode BOOLEAN DEFAULT FALSE,
    stops_count INTEGER,
    zip_filename VARCHAR(512),
    is_test BOOLEAN DEFAULT FALSE,
    original_tour_id INTEGER,
    track VARCHAR(16) NOT NULL DEFAULT 'beta',
    tour_kind VARCHAR(16) NOT NULL DEFAULT 'full'
);
CREATE TABLE custom_tours (
    id SERIAL PRIMARY KEY,
    custom_tour_id VARCHAR(255) UNIQUE NOT NULL,
    original_tour_id INTEGER,
    user_id VARCHAR(255),
    tour_name VARCHAR(255),
    request_string TEXT,
    audio_tour BYTEA,
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    number_requested INTEGER DEFAULT 0
);
CREATE TABLE shared_tours (
    tour_id VARCHAR(16) PRIMARY KEY,
    audio_tour_id INTEGER
);
"""


def _seed_three_same_name(cur, name, with_audio=True):
    """Insert one original per track (beta, storied, subscribed), same name.

    Rows are is_test=FALSE on purpose: /tours-near and /search exclude
    is_test rows, so to prove the TRACK predicate (not the is_test filter) is
    what hides subscribed, the rows must otherwise be fully visible. Safe
    because the whole schema is a throwaway this run owns and drops — never the
    shared DB. Each carries a tiny fake zip in BYTEA so the serve paths find
    something. Returns dict track->id.
    """
    ids = {}
    blob = b"PK\x03\x04local765" if with_audio else None
    for track in ("beta", "storied", "subscribed"):
        cur.execute(
            "INSERT INTO audio_tours "
            "(tour_name, request_string, audio_tour, number_requested, lat, lng, "
            " tour_content, content_language, is_test, original_tour_id, track) "
            "VALUES (%s, %s, %s, 1, %s, %s, %s, 'en', FALSE, NULL, %s) RETURNING id",
            (name, name, blob, 42.0, -71.0, f"content for {track}", track),
        )
        ids[track] = cur.fetchone()[0]
    return ids


def setUpModule():
    _try_connect_or_skip()
    conn = _connect()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(_DDL.format(schema=_SCHEMA))
    # Make the throwaway schema the DEFAULT search_path for EVERY connection to
    # this scratch DB (role-scoped), so the service code — which opens its own
    # connections and never sees our SET — still lands in the throwaway schema.
    # This is why the scratch DB must be a dedicated local765 container, never
    # the shared one. Reset in tearDownModule.
    cur.execute(f'ALTER ROLE {_SCRATCH["user"]} IN DATABASE {_SCRATCH["dbname"]} '
                f'SET search_path TO {_SCHEMA}, public')
    cur.close()
    conn.close()


def tearDownModule():
    try:
        conn = _connect()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(f'ALTER ROLE {_SCRATCH["user"]} IN DATABASE {_SCRATCH["dbname"]} '
                    f'RESET search_path')
        cur.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[LOCAL-765] schema cleanup warning: {e}")


class _ScratchCase(unittest.TestCase):
    """Base: fresh connection with search_path pinned to the throwaway schema."""

    def setUp(self):
        self.conn = _connect()
        self.conn.autocommit = True
        self.cur = self.conn.cursor()
        self.cur.execute(f"SET search_path TO {_SCHEMA}")

    def tearDown(self):
        # Clean only rows this run created (throwaway schema, but keep it tidy
        # between tests so counts are deterministic).
        try:
            self.cur.execute("TRUNCATE audio_tours RESTART IDENTITY CASCADE")
            self.cur.execute("TRUNCATE shared_tours")
        except Exception:
            pass
        self.cur.close()
        self.conn.close()


# ─── Read-path: drive the REAL service handlers ───────────────────────────────
# Each service builds its own psycopg2 connection via get_db_connection(); the
# handler cases below monkeypatch that to a connection pinned to the throwaway
# schema, so every handler query runs against the seeded rows. RED on base code
# (no track predicate → subscribed row surfaces); GREEN after the fix.



class _HandlerCase(_ScratchCase):
    """Base that loads a service module BY FILE PATH and monkeypatches its
    ``get_db_connection`` to hand back a connection pinned to the throwaway
    schema, then exposes a Flask test client. Loading by path avoids package
    issues (map_delivery/ is not a package) and the monkeypatch avoids relying
    on each service's own connection plumbing."""

    SERVICE_PATH = None   # relative path to the .py file
    SERVICE_NAME = None   # unique module name for importlib

    def _scratch_conn(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute(f"SET search_path TO {_SCHEMA}")
        cur.close()
        return conn

    def setUp(self):
        super().setUp()
        import importlib.util
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        spec = importlib.util.spec_from_file_location(
            self.SERVICE_NAME, os.path.join(root, self.SERVICE_PATH))
        self.mod = importlib.util.module_from_spec(spec)
        sys.modules[self.SERVICE_NAME] = self.mod
        spec.loader.exec_module(self.mod)
        # Route every handler at the throwaway schema.
        self.mod.get_db_connection = self._scratch_conn
        # map_delivery_service caches the track-column probe at module scope.
        if hasattr(self.mod, "_TRACK_COLUMN"):
            self.mod._TRACK_COLUMN = None
        self.client = self.mod.app.test_client()

    def tearDown(self):
        sys.modules.pop(self.SERVICE_NAME, None)
        super().tearDown()


class TestMapDeliveryReadPaths(_HandlerCase):
    SERVICE_PATH = "map_delivery_service.py"
    SERVICE_NAME = "local765_map_delivery_service"

    def test_tours_near_excludes_subscribed(self):
        _seed_three_same_name(self.cur, "Salem Witch Museum")
        resp = self.client.get("/tours-near/42.0/-71.0?radius=50")
        self.assertEqual(resp.status_code, 200)
        tracks = {t.get("track") for t in resp.get_json()["tours"]}
        print(f"\n  [LOCAL-765] /tours-near tracks: {sorted(x for x in tracks if x)}")
        self.assertNotIn("subscribed", tracks,
                         "/tours-near must never list a subscribed tour")

    def test_search_excludes_subscribed(self):
        ids = _seed_three_same_name(self.cur, "Salem Witch Museum")
        resp = self.client.get("/search-tours?query=salem")
        self.assertEqual(resp.status_code, 200)
        returned_ids = {t["id"] for t in resp.get_json()["tours"]}
        print(f"  [LOCAL-765] /search-tours ids: {sorted(returned_ids)} "
              f"(subscribed={ids['subscribed']})")
        self.assertNotIn(ids["subscribed"], returned_ids,
                         "/search-tours must never return the subscribed tour")
        self.assertIn(ids["storied"], returned_ids)

    def test_download_subscribed_id_is_404(self):
        ids = _seed_three_same_name(self.cur, "Paid Community Tour")
        sub = self.client.get(f"/download-tour/{ids['subscribed']}")
        print(f"  [LOCAL-765] /download-tour subscribed → {sub.status_code}")
        self.assertEqual(sub.status_code, 404,
                         "download-tour of a subscribed id must 404")
        ok = self.client.get(f"/download-tour/{ids['storied']}")
        self.assertEqual(ok.status_code, 200,
                         "download-tour of a storied id must still serve")

    def test_tour_info_subscribed_id_is_404(self):
        ids = _seed_three_same_name(self.cur, "Paid Community Tour")
        resp = self.client.get(f"/tour-info/{ids['subscribed']}")
        print(f"  [LOCAL-765] /tour-info subscribed → {resp.status_code}")
        self.assertEqual(resp.status_code, 404,
                         "tour-info of a subscribed id must 404")

    def test_resolve_subscribed_id_is_404(self):
        ids = _seed_three_same_name(self.cur, "Paid Community Tour")
        resp = self.client.get(f"/tour/{ids['subscribed']}/resolve")
        print(f"  [LOCAL-765] /tour/<id>/resolve subscribed → {resp.status_code}")
        self.assertEqual(resp.status_code, 404,
                         "resolve of a subscribed id must 404")


class TestMapDeliveryAppReadPaths(_HandlerCase):
    SERVICE_PATH = "map_delivery/app.py"
    SERVICE_NAME = "local765_map_delivery_app"

    def test_tour_by_code_subscribed_is_404(self):
        ids = _seed_three_same_name(self.cur, "Members Only Tour")
        self.cur.execute(
            "INSERT INTO shared_tours (tour_id, audio_tour_id) VALUES (%s, %s)",
            ("CODE765", ids["subscribed"]),
        )
        resp = self.client.get("/tour-by-code/CODE765")
        print(f"\n  [LOCAL-765] /tour-by-code subscribed → {resp.status_code}")
        self.assertEqual(resp.status_code, 404,
                         "tour-by-code of a subscribed tour must 404")

    def test_tour_by_code_storied_still_resolves(self):
        ids = _seed_three_same_name(self.cur, "Members Only Tour")
        self.cur.execute(
            "INSERT INTO shared_tours (tour_id, audio_tour_id) VALUES (%s, %s)",
            ("CODEOK", ids["storied"]),
        )
        resp = self.client.get("/tour-by-code/CODEOK")
        self.assertEqual(resp.status_code, 200,
                         "tour-by-code of a storied tour must still resolve")


# ─── Write-path: the real orchestrator store_audio_tour ───────────────────────

class TestOrchestratorReuse(_ScratchCase):

    def _store(self, name, track_env):
        """Call the real store_audio_tour against the scratch schema.

        store_audio_tour builds its own psycopg2 connection from DB_* env, so
        we point those at the scratch DB and set a per-connection search_path
        via PGOPTIONS so its CREATE/ALTER/INSERT all land in the throwaway
        schema. TOUR_TRACK selects the deployment track.
        """
        import importlib
        env_backup = {k: os.environ.get(k) for k in
                      ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD",
                       "TOUR_TRACK", "PGOPTIONS", "TOUR_TEST_MODE")}
        os.environ["DB_HOST"] = _SCRATCH["host"]
        os.environ["DB_PORT"] = _SCRATCH["port"]
        os.environ["DB_NAME"] = _SCRATCH["dbname"]
        os.environ["DB_USER"] = _SCRATCH["user"]
        os.environ["DB_PASSWORD"] = _SCRATCH["password"]
        os.environ["TOUR_TRACK"] = track_env
        os.environ["TOUR_TEST_MODE"] = "true"
        os.environ["PGOPTIONS"] = f"-c search_path={_SCHEMA}"
        try:
            import tour_orchestrator_service as tos
            importlib.reload(tos)
            # Tiny fixture ZIP — $0, no generation.
            import tempfile, zipfile
            fd, zpath = tempfile.mkstemp(suffix=".zip", prefix="local765_")
            os.close(fd)
            with zipfile.ZipFile(zpath, "w") as z:
                z.writestr("index.html", "<html>local765</html>")
                z.writestr("audio_1.mp3", b"\x00\x00")
            try:
                return tos.store_audio_tour(
                    name, name, zpath, 42.0, -71.0,
                    tour_content="local765 content", stops_count=1, is_test=True,
                )
            finally:
                os.remove(zpath)
        finally:
            for k, v in env_backup.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def _rows(self, name):
        self.cur.execute(
            "SELECT id, track FROM audio_tours WHERE lower(tour_name)=lower(%s) "
            "AND original_tour_id IS NULL ORDER BY id",
            (name,),
        )
        return self.cur.fetchall()

    def test_storied_does_not_reuse_subscribed(self):
        name = "Salem Witch Museum"
        # Seed a subscribed original with the SAME name first.
        self.cur.execute(
            "INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested, "
            "lat, lng, tour_content, content_language, is_test, original_tour_id, track) "
            "VALUES (%s,%s,%s,1,%s,%s,%s,'en',TRUE,NULL,'subscribed') RETURNING id",
            (name, name, b"PK\x03\x04", 42.0, -71.0, "subscribed content"),
        )
        sub_id = self.cur.fetchone()[0]

        result = self._store(name, track_env="storied")
        print(f"\n  [LOCAL-765] store(storied) over existing subscribed row → {result}")
        self.assertTrue(result.get("success"))
        # It must NOT reuse the subscribed row.
        self.assertNotEqual(result.get("existing_tour_id"), sub_id,
                            "Storied store must not reuse the subscribed tour's id")
        self.assertEqual(result.get("action"), "inserted",
                         "Storied store must INSERT its own row, not reuse subscribed")
        rows = self._rows(name)
        tracks = sorted(t for _, t in rows)
        print(f"  [LOCAL-765] rows after store: {rows}")
        self.assertIn("subscribed", tracks)
        self.assertIn("storied", tracks)
        # The subscribed row survives untouched.
        self.cur.execute("SELECT track FROM audio_tours WHERE id=%s", (sub_id,))
        self.assertEqual(self.cur.fetchone()[0], "subscribed")

    def test_same_track_still_versions_one_row(self):
        name = "Beta Only Tour"
        r1 = self._store(name, track_env="beta")
        r2 = self._store(name, track_env="beta")
        print(f"\n  [LOCAL-765] two beta stores → {r1.get('action')}, {r2.get('action')}")
        self.assertEqual(r1.get("action"), "inserted")
        self.assertEqual(r2.get("action"), "already_exists",
                         "Same name + same track must reuse the one row (unchanged behaviour)")
        rows = self._rows(name)
        self.assertEqual(len(rows), 1, "same-track regeneration must not create a second row")

    def test_beta_and_storied_same_name_are_separate_rows(self):
        name = "Dual Track Tour"
        r_beta = self._store(name, track_env="beta")
        r_storied = self._store(name, track_env="storied")
        print(f"\n  [LOCAL-765] beta then storied → {r_beta.get('action')}, {r_storied.get('action')}")
        self.assertEqual(r_beta.get("action"), "inserted")
        self.assertEqual(r_storied.get("action"), "inserted",
                         "A storied store must not collapse into the beta row")
        rows = self._rows(name)
        tracks = sorted(t for _, t in rows)
        self.assertEqual(tracks, ["beta", "storied"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
