#!/usr/bin/env python3
"""test_local737_track_subscribed.py — LOCAL-737 (D708).

'subscribed' is a third first-class track value, everywhere `track` is read,
written, defaulted or filtered. Beta and Storied behaviour is unchanged.

What this proves
================
1. RED TEST (test_subscribed_stored_as_subscribed):
   A tour stored with track='subscribed' is persisted as 'subscribed' — NOT
   normalised away to 'beta'. On the unfixed code (VALID set = {'beta',
   'storied'}) the store coerced it to 'beta' and this test FAILS. That is the
   whole point of the ticket: a Subscribed tour written as Beta re-opens the
   same-name collision class (bug 432) between Subscribed and Beta.

2. test_subscribed_and_beta_same_name_two_rows:
   A subscribed tour and a beta tour with the SAME name and creator stay two
   separate rows (the (name, creator, track) key from migration 043 now spans
   three tracks). The beta row is byte-for-byte unchanged.

3. test_normalize_track_* : the shared helper in each service accepts
   beta/storied/subscribed (any case, with surrounding space) and maps missing/
   unknown to 'beta'.

4. tours-near / search-tours track filter (map_delivery_service):
   * no ?track= → every track's tours are listed, each labelled with its own
     track (historic behaviour; Beta and Storied unchanged).
   * ?track=subscribed → ONLY the subscribed tour.
   * ?track=beta → ONLY the beta tour (the storied/subscribed ones excluded),
     proving the filter is symmetric and does not single out subscribed.

Isolation: everything runs inside a throwaway Postgres schema
(tests/_isolated_db.py). Teardown DROPs the schema and asserts public row counts
are identical before and after — no shared/production row is ever written. There
is NO DELETE anywhere.
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
_TRANSLATION_DIR = os.path.join(_ROOT, "translation-service")
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
import map_delivery_service as mapsvc  # noqa: E402
import psycopg2  # noqa: E402

_STORE_ACCEPTS_TRACK = "track" in inspect.signature(orch.store_audio_tour).parameters

_ISO = IsolatedSchema(
    prefix="t737",
    clone_tables=["audio_tours", "audio_tour_versions", "shared_tours"],
    proof_tables=["audio_tours", "audio_tour_versions"],
    banner="LOCAL-737",
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
        # Match the production post-041/043 schema: a creator may hold the same
        # name on multiple tracks, so drop any UNIQUE index on lower(tour_name).
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
        cur.execute(f'DROP TABLE IF EXISTS "{_ISO.schema}".audio_tour_versions CASCADE')
        # tours-near / search-tours also read custom_tours, which is absent from
        # audiotours_test. Create a minimal one in the throwaway schema so the
        # real routes run; we seed no rows into it (the track filter is about
        # audio_tours). Columns match exactly what the queries select.
        cur.execute(
            f'CREATE TABLE IF NOT EXISTS "{_ISO.schema}".custom_tours ('
            "custom_tour_id SERIAL PRIMARY KEY, tour_name VARCHAR(255), "
            "request_string TEXT, lat DOUBLE PRECISION, lng DOUBLE PRECISION, "
            "number_requested INTEGER DEFAULT 0, original_tour_id INTEGER)"
        )
        conn.commit()
        orch._ensure_versioning_objects(cur)
        conn.commit()
    finally:
        conn.close()
    # map_delivery caches whether audio_tours.track exists in a module global;
    # the cloned schema has the column, so reset the cache to force a fresh look.
    mapsvc._TRACK_COLUMN = None


def tearDownModule():
    _ISO.teardown()


def _make_zip(path, payload=b"stop-audio"):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("tour.mp3", payload)


# ── Pure unit tests for the shared helpers (no DB needed) ───────────────────
class NormalizeTrackHelperTest(unittest.TestCase):
    def _check(self, normalize, valid):
        self.assertEqual(tuple(valid), ("beta", "storied", "subscribed"))
        # Known values pass through.
        self.assertEqual(normalize("beta"), "beta")
        self.assertEqual(normalize("storied"), "storied")
        self.assertEqual(normalize("subscribed"), "subscribed")
        # Case-insensitive + whitespace-tolerant.
        self.assertEqual(normalize("  SUBSCRIBED "), "subscribed")
        self.assertEqual(normalize("Storied"), "storied")
        # Missing / unknown ⇒ beta.
        self.assertEqual(normalize(None), "beta")
        self.assertEqual(normalize(""), "beta")
        self.assertEqual(normalize("   "), "beta")
        self.assertEqual(normalize("premium"), "beta")

    def test_orchestrator_helper(self):
        self._check(orch.normalize_track, orch.VALID_TRACKS)

    def test_map_delivery_helper(self):
        self._check(mapsvc.normalize_track, mapsvc.VALID_TRACKS)

    def test_translation_helper(self):
        if _TRANSLATION_DIR not in sys.path:
            sys.path.insert(0, _TRANSLATION_DIR)
        try:
            import translation_service as tr  # noqa: E402
        except Exception as e:  # pragma: no cover - heavy optional deps
            self.skipTest(f"translation_service not importable: {e}")
        self._check(tr.normalize_track, tr.VALID_TRACKS)

    def test_deployed_map_delivery_helper(self):
        # The DEPLOYED map-delivery is map_delivery/app.py (docker-compose-master
        # + subscribed-local build ./map_delivery). Verify its helper too, plus
        # the ?track= request parser's "no param ⇒ None" contract that keeps
        # Beta/Storied behaviour unchanged.
        import importlib.util
        app_path = os.path.join(_ROOT, "map_delivery", "app.py")
        if not os.path.exists(app_path):
            self.skipTest("map_delivery/app.py not present")
        sys.path.insert(0, os.path.join(_ROOT, "map_delivery"))
        spec = importlib.util.spec_from_file_location("map_delivery_app", app_path)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as e:  # pragma: no cover - optional heavy deps
            self.skipTest(f"map_delivery/app.py not importable: {e}")
        self._check(mod.normalize_track, mod.VALID_TRACKS)

        class _Req:
            def __init__(self, args):
                self.args = args
        # No ?track= ⇒ None (historic behaviour preserved for Beta/Storied).
        self.assertIsNone(mod._requested_track(_Req({})))
        self.assertIsNone(mod._requested_track(_Req({"track": ""})))
        # Explicit values resolve, unknown ⇒ beta.
        self.assertEqual(mod._requested_track(_Req({"track": "subscribed"})), "subscribed")
        self.assertEqual(mod._requested_track(_Req({"track": "beta"})), "beta")
        self.assertEqual(mod._requested_track(_Req({"track": "storied"})), "storied")
        self.assertEqual(mod._requested_track(_Req({"track": "weird"})), "beta")


@unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
class SubscribedStoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="local737_tours_")
        self._orig_tours_dir = orch.TOURS_DIR
        orch.TOURS_DIR = self._tmp
        self._prev_track = os.environ.get("TOUR_TRACK")
        self._prev_storied = os.environ.get("STORIED_MODE")
        self.tour_name = f"LOCAL737 Venue {uuid.uuid4().hex[:8]}"
        self.creator = f"creator-{uuid.uuid4().hex[:8]}"

    def tearDown(self):
        orch.TOURS_DIR = self._orig_tours_dir
        for key, val in (("TOUR_TRACK", self._prev_track),
                         ("STORIED_MODE", self._prev_storied)):
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    def _store(self, *, track, user_id, tour_content, zip_name, payload,
               storied_mode=False, stops_count=4, lat=None, lng=None,
               is_test=True, job_id=None, store_mode="regenerate"):
        zip_path = os.path.join(self._tmp, zip_name)
        _make_zip(zip_path, payload)
        os.environ["TOUR_TRACK"] = track
        os.environ["STORIED_MODE"] = "true" if storied_mode else "false"
        # [LOCAL-821] Track-scoped versioning (replace) now lives behind the
        # explicit regenerate path; different-track cases INSERT regardless (no
        # match), so defaulting to regenerate keeps every case's intent.
        kwargs = dict(
            tour_content=tour_content, stops_count=stops_count,
            is_test=is_test, job_id=job_id or ("job-" + uuid.uuid4().hex[:8]),
            user_id=user_id, store_mode=store_mode,
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
                "SELECT id, creator_user_id, track, tour_content, stops_count "
                "FROM audio_tours WHERE lower(tour_name)=lower(%s) "
                "AND original_tour_id IS NULL ORDER BY id",
                (self.tour_name,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        finally:
            conn.close()

    # ── THE RED TEST ────────────────────────────────────────────────────────
    def test_subscribed_stored_as_subscribed(self):
        r = self._store(
            track="subscribed", user_id=self.creator,
            tour_content="Subscribed track content.", zip_name="sub.zip",
            payload=b"sub-zip", stops_count=5, lat=40.0, lng=-73.0)
        self.assertTrue(r["success"])
        self.assertEqual(r["action"], "inserted")
        rows = self._rows_for_name()
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["track"], "subscribed",
            "A track='subscribed' store MUST persist 'subscribed', not be "
            "normalised to 'beta' (that is bug 432 between Subscribed and Beta).")

    # ── subscribed + beta, same name/creator → two rows ─────────────────────
    def test_subscribed_and_beta_same_name_two_rows(self):
        r_beta = self._store(
            track="beta", user_id=self.creator,
            tour_content="Beta content.", zip_name="b.zip", payload=b"b",
            stops_count=4, lat=42.1, lng=-71.1)
        self.assertTrue(r_beta["success"])
        self.assertEqual(r_beta["action"], "inserted")
        beta_rows = self._rows_for_name()
        self.assertEqual(len(beta_rows), 1)
        beta_id = beta_rows[0]["id"]

        r_sub = self._store(
            track="subscribed", user_id=self.creator,
            tour_content="Subscribed content.", zip_name="s.zip", payload=b"s",
            stops_count=9, lat=48.8, lng=2.3)
        self.assertTrue(r_sub["success"])
        self.assertEqual(
            r_sub["action"], "inserted",
            "Subscribed must get its OWN new row, not replace the Beta row")

        rows = self._rows_for_name()
        self.assertEqual(
            len(rows), 2,
            f"Expected two rows (beta + subscribed); got {len(rows)}.")
        by_track = {row["track"]: row for row in rows}
        self.assertEqual(set(by_track), {"beta", "subscribed"})
        # Beta row unchanged.
        self.assertEqual(by_track["beta"]["id"], beta_id)
        self.assertEqual(by_track["beta"]["tour_content"], "Beta content.")
        self.assertEqual(by_track["beta"]["stops_count"], 4)
        # Subscribed row carries its own columns.
        self.assertEqual(by_track["subscribed"]["tour_content"], "Subscribed content.")
        self.assertEqual(by_track["subscribed"]["stops_count"], 9)

    # ── same track (subscribed) re-generation still versions ONE row ────────
    def test_same_subscribed_track_versions_one_row(self):
        self._store(track="subscribed", user_id=self.creator,
                    tour_content="Sub v1.", zip_name="sv1.zip", payload=b"sv1")
        rows1 = self._rows_for_name()
        self.assertEqual(len(rows1), 1)
        r2 = self._store(track="subscribed", user_id=self.creator,
                         tour_content="Sub v2 improved.", zip_name="sv2.zip",
                         payload=b"sv2")
        self.assertEqual(r2["action"], "replaced")
        rows2 = self._rows_for_name()
        self.assertEqual(len(rows2), 1, "same track + creator versions one row")


@unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
class ToursNearTrackFilterTest(unittest.TestCase):
    """tours-near / search-tours honour an optional ?track= filter.

    Seeds one tour per track at the SAME coordinates, then drives the real
    map_delivery_service Flask routes via its test client. Because the isolated
    schema is first on the search_path (PGOPTIONS), the service's own
    get_db_connection() reads/writes the throwaway schema, not public.
    """
    @classmethod
    def setUpClass(cls):
        if not _ISO.db_up():
            return
        mapsvc.app.config["TESTING"] = True
        cls.client = mapsvc.app.test_client()
        cls.lat, cls.lng = 42.3601, -71.0589
        cls.names = {}
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            cur.execute("ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS track VARCHAR(16) NOT NULL DEFAULT 'beta'")
            for trk in ("beta", "storied", "subscribed"):
                name = f"LOCAL737 Near {trk} {uuid.uuid4().hex[:8]}"
                cls.names[trk] = name
                cur.execute(
                    "INSERT INTO audio_tours (tour_name, request_string, lat, lng, "
                    "number_requested, is_test, track) VALUES (%s,%s,%s,%s,%s,FALSE,%s)",
                    (name, "req:" + name, cls.lat, cls.lng, 1, trk),
                )
            conn.commit()
        finally:
            conn.close()
        mapsvc._TRACK_COLUMN = None

    def _tracks_for(self, query=""):
        resp = self.client.get(f"/tours-near/{self.lat}/{self.lng}?radius=5{query}")
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        data = resp.get_json()
        # Restrict to the rows this test seeded (the schema may hold others).
        ours = {n: t for t, n in self.names.items()}
        return sorted(
            ours[t["name"]] for t in data["tours"] if t["name"] in ours
        )

    def test_no_filter_lists_all_tracks(self):
        got = self._tracks_for("")
        self.assertEqual(got, ["beta", "storied", "subscribed"],
                         "no ?track= must list every track (historic behaviour)")

    def test_filter_subscribed_only(self):
        self.assertEqual(self._tracks_for("&track=subscribed"), ["subscribed"])

    def test_filter_beta_only(self):
        self.assertEqual(self._tracks_for("&track=beta"), ["beta"])

    def test_filter_storied_only(self):
        self.assertEqual(self._tracks_for("&track=storied"), ["storied"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


def test_delivery_track_filter_env_defaults_the_filter(monkeypatch):
    """[LEAD] DELIVERY_TRACK_FILTER makes a one-track deployment filter without ?track=."""
    import importlib.util, os as _os
    from flask import Flask
    spec = importlib.util.spec_from_file_location(
        "md_app_737_env",
        _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "map_delivery", "app.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    app = Flask(__name__)
    with app.test_request_context('/tours-near/1/1'):
        from flask import request
        monkeypatch.delenv('DELIVERY_TRACK_FILTER', raising=False)
        assert mod._requested_track(request) is None
        monkeypatch.setenv('DELIVERY_TRACK_FILTER', 'subscribed')
        assert mod._requested_track(request) == 'subscribed'
    with app.test_request_context('/tours-near/1/1?track=beta'):
        from flask import request
        assert mod._requested_track(request) == 'beta'
