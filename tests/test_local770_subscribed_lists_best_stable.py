#!/usr/bin/env python3
"""test_local770_subscribed_lists_best_stable.py — LOCAL-770 (Michael 2026-10-26).

Subscribed ALSO lists the best Stable (beta/storied) tours — a LISTING FILTER,
never a copy. The Subscribed map-delivery (DELIVERY_TRACK_FILTER=subscribed)
additionally surfaces an ORIGINAL beta/storied (or NULL-track) tour whose
evaluated editor_score is >= SUBSCRIBED_STABLE_MIN_SCORE (env; unset = feature
off = today's subscribed-only behaviour), plus that original's translations
(which follow their original's score). No row is copied, moved or deleted.

What this proves
================
RED (the feature's point):
  * env UNSET  → a beta/storied tour scored 7.3 is NOT listed (today's
    behaviour). On the unfixed code this already passes; it is the control.
  * env = 7.2  → that 7.3 beta original IS listed and its translation too, on
    BOTH /tours-near and /search-tours.

Boundaries / exclusions (env = 7.2):
  * 7.1  → not listed (below the bar).
  * NULL editor_score → not listed (unscored).
  * paid Stable row (is_paid true) → not listed (free only; asserts a Stable
    row that is mis-priced never leaks as a free Subscribed listing).
  * not_allowed / pending review Stable original → not listed (the content gate
    still applies on top of the new branch).

Invariants:
  * subscribed rows are listed with or without the env, unchanged.
  * a translation follows its ORIGINAL's score (COALESCE(orig.editor_score,
    t.editor_score)) — surfaced only through /search-tours (which carries
    translations; /tours-near is originals-only).

Isolation: everything runs inside a throwaway Postgres schema
(tests/_isolated_db.py). Teardown DROPs the schema and asserts public row counts
are identical before and after. There is NO DELETE anywhere.
"""
import importlib.util
import os
import sys
import unittest
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MAP_DIR = os.path.join(_ROOT, "map_delivery")
for _p in (_HERE, _ROOT, _MAP_DIR):
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
import psycopg2  # noqa: E402

_ISO = IsolatedSchema(
    prefix="t770",
    clone_tables=[
        "audio_tours", "audio_tour_versions", "tour_ratings",
        "communities", "community_memberships", "shared_tours",
    ],
    proof_tables=["audio_tours", "audio_tour_versions"],
    banner="LOCAL-770",
)


def _load_map_delivery_app():
    """Import map_delivery/app.py as its own module (the DEPLOYED image), fresh
    each time so the column-existence caches re-probe the cloned schema."""
    app_path = os.path.join(_MAP_DIR, "app.py")
    spec = importlib.util.spec_from_file_location("map_delivery_app_770", app_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _schema_connect():
    return psycopg2.connect(
        host=_CFG["host"], port=_CFG["port"], dbname=_CFG["dbname"],
        user=_CFG["user"], password=_CFG["password"], connect_timeout=5,
    )


def setUpModule():
    _ISO.setup()


def tearDownModule():
    _ISO.teardown()


@unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
class SubscribedStableListingTest(unittest.TestCase):
    """Seed one tour per scenario at the SAME coordinates, drive the real
    map_delivery/app.py Flask routes, and assert which names come back with the
    env off vs SUBSCRIBED_STABLE_MIN_SCORE=7.2."""

    LAT, LNG = 42.3601, -71.0589  # Boston

    @classmethod
    def setUpClass(cls):
        if not _ISO.db_up():
            return
        cls.mod = _load_map_delivery_app()
        cls.mod.app.config["TESTING"] = True
        cls.client = cls.mod.app.test_client()
        cls.names = {}          # label -> tour_name
        cls.ids = {}            # label -> id
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            # Ensure the columns the branch needs exist on the clone (they do in
            # audiotours_test; guard for an older clone just in case).
            cur.execute("ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS track VARCHAR(16)")

            def seed(label, *, track, editor_score=None, price_tier=None,
                     original_label=None, content_rating=None,
                     review_status=None, language="en"):
                # NOTE: is_paid is a GENERATED column (price_tier IS NOT NULL) in
                # the production schema, so a "paid" row is one with a price_tier
                # set — never an is_paid insert. This mirrors reality: the paid
                # exclusion in the LOCAL-770 branch reads the generated is_paid.
                name = f"LOCAL770 {label} {uuid.uuid4().hex[:8]}"
                original_id = cls.ids.get(original_label)
                cur.execute(
                    "INSERT INTO audio_tours "
                    "(tour_name, request_string, lat, lng, number_requested, "
                    " is_test, track, editor_score, price_tier, original_tour_id, "
                    " content_language, content_rating, review_status) "
                    "VALUES (%s,%s,%s,%s,%s,FALSE,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (name, "req:" + name, cls.LAT, cls.LNG, 1, track,
                     editor_score, price_tier, original_id, language,
                     content_rating, review_status),
                )
                cls.ids[label] = cur.fetchone()[0]
                cls.names[label] = name

            # The subscribed own-track control.
            seed("sub", track="subscribed", editor_score=None)
            # Stable originals at various scores.
            seed("beta_73", track="beta", editor_score=7.3)
            seed("storied_73", track="storied", editor_score=7.3)
            seed("beta_71", track="beta", editor_score=7.1)
            seed("beta_null", track="beta", editor_score=None)
            seed("beta_73_paid", track="beta", editor_score=7.3, price_tier=3)
            seed("beta_73_notallowed", track="beta", editor_score=7.3,
                 content_rating="not_allowed")
            seed("beta_73_pending", track="beta", editor_score=7.3,
                 review_status="pending")
            # A translation of the good beta original (score lives on the
            # original, its own score is NULL) — surfaced via search-tours.
            seed("beta_73_ru", track="beta", editor_score=None,
                 original_label="beta_73", language="ru")
            conn.commit()
        finally:
            conn.close()

    # ── env helpers ──────────────────────────────────────────────────────────
    def setUp(self):
        self._saved = {}
        for k in ("DELIVERY_TRACK_FILTER", "SUBSCRIBED_STABLE_MIN_SCORE"):
            self._saved[k] = os.environ.get(k)
        # Reset the module's cached column probes so each test re-reads cleanly.
        self.mod._HAS_TRACK_COLUMN = None
        self.mod._HAS_EDITOR_SCORE_COLUMN = None
        self.mod._HAS_CONTENT_RATING_COLUMN = None
        self.mod._HAS_IS_PAID_COLUMN = None

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _set_env(self, *, subscribed=True, min_score=None):
        if subscribed:
            os.environ["DELIVERY_TRACK_FILTER"] = "subscribed"
        else:
            os.environ.pop("DELIVERY_TRACK_FILTER", None)
        if min_score is None:
            os.environ.pop("SUBSCRIBED_STABLE_MIN_SCORE", None)
        else:
            os.environ["SUBSCRIBED_STABLE_MIN_SCORE"] = str(min_score)

    def _labels_near(self):
        resp = self.client.get(f"/tours-near/{self.LAT}/{self.LNG}?radius=5")
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        by_name = {n: lbl for lbl, n in self.names.items()}
        return sorted(by_name[t["name"]] for t in resp.get_json()["tours"]
                      if t["name"] in by_name)

    def _labels_search(self):
        resp = self.client.get(f"/search-tours?pattern=LOCAL770&lat={self.LAT}&lng={self.LNG}")
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        by_name = {n: lbl for lbl, n in self.names.items()}
        return sorted(by_name[t["name"]] for t in resp.get_json()["tours"]
                      if t["name"] in by_name)

    # ── env UNSET: today's behaviour (subscribed only) ───────────────────────
    def test_env_off_tours_near_lists_only_subscribed(self):
        self._set_env(subscribed=True, min_score=None)
        self.assertEqual(self._labels_near(), ["sub"],
                         "env unset must keep today's subscribed-only behaviour")

    def test_env_off_search_lists_only_subscribed(self):
        self._set_env(subscribed=True, min_score=None)
        self.assertEqual(self._labels_search(), ["sub"])

    # ── env = 7.2: the best Stable originals appear ──────────────────────────
    def test_env_72_tours_near_lists_subscribed_plus_good_stable(self):
        self._set_env(subscribed=True, min_score=7.2)
        got = self._labels_near()
        # beta_73 and storied_73 qualify; the subscribed own tour stays.
        self.assertIn("sub", got)
        self.assertIn("beta_73", got)
        self.assertIn("storied_73", got)
        # Below the bar / unscored / paid / held are excluded.
        for excluded in ("beta_71", "beta_null", "beta_73_paid",
                         "beta_73_notallowed", "beta_73_pending"):
            self.assertNotIn(excluded, got, f"{excluded} must NOT be listed")

    def test_env_72_search_lists_good_stable_and_translation(self):
        self._set_env(subscribed=True, min_score=7.2)
        got = self._labels_search()
        self.assertIn("sub", got)
        self.assertIn("beta_73", got)
        self.assertIn("storied_73", got)
        # The translation follows its ORIGINAL's 7.3 score (its own is NULL).
        self.assertIn("beta_73_ru", got,
                      "a translation must follow its original's editor_score")
        for excluded in ("beta_71", "beta_null", "beta_73_paid",
                         "beta_73_notallowed", "beta_73_pending"):
            self.assertNotIn(excluded, got, f"{excluded} must NOT be listed")

    # ── the subscribed own row is unaffected either way ──────────────────────
    def test_subscribed_row_always_listed(self):
        self._set_env(subscribed=True, min_score=None)
        self.assertIn("sub", self._labels_near())
        self._set_env(subscribed=True, min_score=7.2)
        self.assertIn("sub", self._labels_near())


@unittest.skipUnless(_ISO.db_up(), "dev Postgres not reachable")
class TrackFilterClauseUnitTest(unittest.TestCase):
    """The helper contract, exercised directly against the cloned schema's
    cursor so the SQL/params shape is pinned without the full Flask stack."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_map_delivery_app()

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in
                       ("DELIVERY_TRACK_FILTER", "SUBSCRIBED_STABLE_MIN_SCORE")}
        self.mod._HAS_TRACK_COLUMN = None
        self.mod._HAS_EDITOR_SCORE_COLUMN = None
        self.mod._HAS_IS_PAID_COLUMN = None

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    class _Req:
        def __init__(self, args):
            self.args = args

    def test_min_score_parser(self):
        os.environ.pop("SUBSCRIBED_STABLE_MIN_SCORE", None)
        self.assertIsNone(self.mod._subscribed_stable_min_score())
        os.environ["SUBSCRIBED_STABLE_MIN_SCORE"] = "7.2"
        self.assertEqual(self.mod._subscribed_stable_min_score(), 7.2)
        os.environ["SUBSCRIBED_STABLE_MIN_SCORE"] = "   "
        self.assertIsNone(self.mod._subscribed_stable_min_score())
        os.environ["SUBSCRIBED_STABLE_MIN_SCORE"] = "notanumber"
        self.assertIsNone(self.mod._subscribed_stable_min_score())

    def test_subscribed_env_off_is_plain_equality(self):
        os.environ["DELIVERY_TRACK_FILTER"] = "subscribed"
        os.environ.pop("SUBSCRIBED_STABLE_MIN_SCORE", None)
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            sql, params = self.mod._track_filter_clause(cur, self._Req({}))
        finally:
            conn.close()
        self.assertEqual(params, ["subscribed"])
        self.assertNotIn("editor_score", sql)

    def test_subscribed_env_on_widens_clause(self):
        os.environ["DELIVERY_TRACK_FILTER"] = "subscribed"
        os.environ["SUBSCRIBED_STABLE_MIN_SCORE"] = "7.2"
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            sql, params = self.mod._track_filter_clause(cur, self._Req({}))
        finally:
            conn.close()
        self.assertEqual(params, ["subscribed", 7.2])
        self.assertIn("editor_score", sql)
        self.assertIn("'beta', 'storied'", sql)

    def test_beta_filter_ignores_min_score(self):
        # A non-subscribed track filter never widens, even if the env is set.
        os.environ["DELIVERY_TRACK_FILTER"] = "beta"
        os.environ["SUBSCRIBED_STABLE_MIN_SCORE"] = "7.2"
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            sql, params = self.mod._track_filter_clause(cur, self._Req({}))
        finally:
            conn.close()
        self.assertEqual(params, ["beta"])
        self.assertNotIn("editor_score", sql)

    def test_no_track_filter_returns_empty(self):
        os.environ.pop("DELIVERY_TRACK_FILTER", None)
        os.environ["SUBSCRIBED_STABLE_MIN_SCORE"] = "7.2"
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            sql, params = self.mod._track_filter_clause(cur, self._Req({}))
        finally:
            conn.close()
        self.assertEqual((sql, params), ("", []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
