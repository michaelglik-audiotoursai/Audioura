#!/usr/bin/env python3
"""test_local798_name_search_tokens.py — LOCAL-798.

Tour-name search was an exact contiguous phrase: Michael (iPhone 84,
2026-10-28) searched "Mui Ne seafood*" and found NOTHING, although tour 466
"Seafood restaurants in Mui Ne, Vietnam - Tour" exists. The old WHERE matched
the WHOLE query as one substring (`tour_name ILIKE '%mui ne seafood%'`), so the
words had to be adjacent and in that order.

The fix (map-delivery only) splits the query into words and requires EVERY word
to appear in tour_name OR request_string (AND across words, any order), case-
and diacritic-insensitive ("Mũi Né" == "Mui Ne"), then ranks all-words-in-name
first, more-words-in-name next, newest last. The response shape and the
track/visibility/community filters are unchanged.

What this proves
================
PURE HELPERS (no DB, always run) — the tokeniser + matcher that both services
share, lifted from each file so a DB-less CI still exercises the core:
  * tokenisation drops a trailing '*', punctuation and stop-words, folds
    diacritics, and is word-order independent;
  * the four ticket queries ("Mui Ne seafood", "seafood mui ne",
    "MŨI NÉ Seafood*", "seafood") all match tour 466's text;
  * "Mui Ne pizza" does NOT match (pizza absent);
  * ranking counts words-in-name correctly.

DEPLOYED ROUTE (map_delivery/app.py, hermetic fake cursor) — the real
/search-tours endpoint over a scripted cursor, unaccent() forced OFF so the
Python fold path (the live/test-DB path) runs:
  * the four queries return tour 466's row with the response shape intact;
  * "Mui Ne pizza" returns zero rows;
  * ranking puts the all-words-in-name tour ahead of a request-string-only hit.

REAL DB (map_delivery_service.py via an isolated throwaway schema, skipped when
Postgres is down) — proves the actual SQL WHERE matches, seeding 3 tours:
  * the four queries each return tour 466; "Mui Ne pizza" returns nothing;
  * the existing track filter still isolates subscribed/beta (unchanged).

Isolation: the DB class runs entirely inside a throwaway schema
(tests/_isolated_db.py); teardown DROPs it and asserts public row counts are
identical before and after. No DELETE anywhere; the live DB is never written.
"""
import ast
import datetime
import importlib.util
import os
import pathlib
import sys
import unittest
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MAPDIR = os.path.join(_ROOT, "map_delivery")
for _p in (_HERE, _ROOT, _MAPDIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Tour 466's real text (Michael's evidence).
T466_NAME = "Seafood restaurants in Mui Ne, Vietnam - Tour"
T466_REQ = "seafood restaurants mui ne vietnam"

# The four ticket queries and the negative.
Q_MATCH = ["Mui Ne seafood", "seafood mui ne", "MŨI NÉ Seafood*", "seafood"]
Q_NOMATCH = "Mui Ne pizza"


# ── Lift the pure helpers out of each service without importing (no DB) ──────
def _load_pure_helpers(src_path):
    """exec just the LOCAL-798 pure helpers from a service file, so the module's
    import-time Postgres/Flask wiring never runs."""
    import re as _re
    import unicodedata as _ud
    tree = ast.parse(pathlib.Path(src_path).read_text())
    want = {"_fold_text", "_tokenize_search", "_is_ascii_token",
            "_token_match_py", "_words_in_name"}
    fns = [n for n in tree.body
           if isinstance(n, ast.FunctionDef) and n.name in want]
    assigns = [n for n in tree.body if isinstance(n, ast.Assign)
               and any(getattr(t, "id", None) == "_SEARCH_STOP_WORDS"
                       for t in n.targets)]
    ns = {"re": _re, "_unicodedata": _ud}
    exec(compile(ast.Module(body=assigns + fns, type_ignores=[]),
                 str(src_path), "exec"), ns)
    return ns


class PureHelperTest(unittest.TestCase):
    """The tokeniser + matcher, lifted from BOTH service files (must agree)."""

    def _check(self, ns):
        tok = ns["_tokenize_search"]
        match = ns["_token_match_py"]
        win = ns["_words_in_name"]

        # Trailing '*', punctuation and stop-words dropped; diacritics folded.
        self.assertEqual(tok("Mui Ne seafood*"), ["mui", "ne", "seafood"])
        self.assertEqual(tok("MŨI NÉ Seafood*"), ["mui", "ne", "seafood"])
        self.assertEqual(
            tok("Seafood restaurants in Mui Ne, Vietnam - Tour"),
            ["seafood", "restaurants", "mui", "ne", "vietnam"])
        # Word order does not matter.
        self.assertEqual(set(tok("seafood mui ne")), {"seafood", "mui", "ne"})
        # Stop-words-only ⇒ no tokens (caller treats as the historic path).
        self.assertEqual(tok("the of in tour"), [])

        # The four ticket queries all match tour 466's text.
        for q in Q_MATCH:
            toks = tok(q)
            self.assertTrue(
                match(toks, T466_NAME, T466_REQ),
                f"query {q!r} → {toks} should match tour 466")
        # The negative does not.
        self.assertFalse(match(tok(Q_NOMATCH), T466_NAME, T466_REQ))

        # Ranking: all three words are in the NAME for "Mui Ne seafood".
        self.assertEqual(win(tok("Mui Ne seafood"), T466_NAME), 3)
        # A word only in the request_string is not counted in the name.
        self.assertEqual(win(["vietnam"], "Seafood Mui Ne"), 0)

    def test_deployed_app_helpers(self):
        self._check(_load_pure_helpers(os.path.join(_MAPDIR, "app.py")))

    def test_service_helpers(self):
        self._check(_load_pure_helpers(os.path.join(_ROOT, "map_delivery_service.py")))


# ── Deployed route over a hermetic fake cursor (no DB, unaccent OFF) ──────────
class _FakeCursor:
    """Answers execute() from a scripted plan of (needle, rows); first needle
    found (case-insensitively) in the normalised SQL wins. The unaccent('x')
    probe raises so _has_unaccent() resolves to False — the Python-fold path,
    exactly what the live/test DB (no unaccent extension) runs."""

    def __init__(self, plan):
        self._plan = plan
        self._rows = []
        self.connection = self

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split()).lower()
        if "unaccent(" in text:
            raise Exception("function unaccent(unknown) does not exist")
        for needle, result in self._plan:
            if needle.lower() in text:
                self._rows = list(result)
                return
        self._rows = []

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def rollback(self):
        pass

    def close(self):
        pass


class _FakeConn:
    def __init__(self, plan):
        self._plan = plan

    def cursor(self):
        return _FakeCursor(self._plan)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _load_map_app():
    spec = importlib.util.spec_from_file_location(
        "md_app_local798", os.path.join(_MAPDIR, "app.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# The /search-tours SELECT shape: 21 head columns, then content_rating +
# review_status appended (LOCAL-687), unpacked via _row_with_rating(row, 21).
# Positions used by the route: 0 id, 1 name, 2 request_string, 3 lat, 4 lng,
# 5 number_requested, 6 content_language, 7 original_tour_id, 10 created_at.
def _t466_row(tour_id=466, name=T466_NAME, req=T466_REQ, lat=10.93, lng=108.29,
              pop=12, created=None):
    created = created or datetime.datetime(2026, 10, 1, 8, 30, 0)
    return (tour_id, name, req, lat, lng, pop,
            "en", None, None, None, created,
            None, None,                 # source_version, source_max_version_no
            None, None, None, None,     # rating_count, rating_values, verified, created
            False, None,                # is_paid, price_tier
            "en", None)                 # own_lang, source_lang  (content_rating/review padded)


class DeployedSearchRouteTest(unittest.TestCase):
    def setUp(self):
        self.mod = _load_map_app()
        self.mod._HAS_UNACCENT = None          # force a fresh (failing) probe
        self.mod._HAS_SOURCE_VERSION = None
        self._orig_db = self.mod.get_db_connection
        self.client = self.mod.app.test_client()

    def tearDown(self):
        self.mod.get_db_connection = self._orig_db

    def _install(self, rows):
        plan = [
            ("information_schema", [("source_version",)]),
            ("from audio_tours t", rows),
        ]
        self.mod.get_db_connection = lambda: _FakeConn(plan)

    def _search(self, query):
        from urllib.parse import quote
        resp = self.client.get(
            f"/search-tours?pattern={quote(query)}&lat=10.9&lng=108.2")
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        return resp.get_json()

    def test_four_queries_return_tour_466_with_shape(self):
        for q in Q_MATCH:
            self._install([_t466_row()])
            body = self._search(q)
            ids = [r["id"] for r in body["tours"]]
            self.assertIn(466, ids, f"query {q!r} must surface tour 466")
            row = next(r for r in body["tours"] if r["id"] == 466)
            # Response shape preserved: the usual search fields are all present,
            # and the internal ranking keys are stripped.
            for key in ("id", "name", "request_string", "lat", "lng",
                        "distance_km", "popularity", "type", "language",
                        "version", "updated_at"):
                self.assertIn(key, row, f"{key} missing for query {q!r}")
            for internal in ("_rank_all_in_name", "_rank_words_in_name",
                             "_rank_created_at"):
                self.assertNotIn(internal, row)

    def test_pizza_returns_nothing(self):
        self._install([_t466_row()])
        body = self._search(Q_NOMATCH)
        self.assertEqual([r["id"] for r in body["tours"]], [],
                         "'Mui Ne pizza' must not match tour 466")

    def test_rank_all_words_in_name_first(self):
        # Two tours: 466 has all words in the NAME; 999 matches only via
        # request_string (name has none of the words). 466 must rank first.
        name_hit = _t466_row(tour_id=466, pop=1)
        req_only = _t466_row(
            tour_id=999, name="Local Eats Guide",
            req="seafood mui ne vietnam", pop=500)
        self._install([req_only, name_hit])   # deliberately worst order
        body = self._search("Mui Ne seafood")
        ids = [r["id"] for r in body["tours"]]
        self.assertEqual(ids[0], 466,
                         "the tour with all words in the NAME ranks first, "
                         "ahead of a more popular request-string-only hit")
        self.assertIn(999, ids)


# ── Real-DB SQL proof via an isolated throwaway schema (skips if DB down) ─────
try:
    from _isolated_db import IsolatedSchema
    import map_delivery_service as mapsvc
    import psycopg2
    from db_connection import get_db_config

    _CFG = get_db_config()
    os.environ.setdefault("DB_HOST", _CFG["host"])
    os.environ.setdefault("DB_PORT", str(_CFG["port"]))
    os.environ.setdefault("DB_NAME", _CFG["dbname"])
    os.environ.setdefault("DB_USER", _CFG["user"])
    os.environ.setdefault("DB_PASSWORD", _CFG["password"])

    _ISO = IsolatedSchema(
        prefix="t798",
        clone_tables=["audio_tours"],
        proof_tables=["audio_tours"],
        banner="LOCAL-798",
    )
    _ISO_OK = True
except Exception:  # pragma: no cover - optional deps absent
    _ISO = None
    _ISO_OK = False


def _schema_connect():
    return psycopg2.connect(
        host=_CFG["host"], port=_CFG["port"], dbname=_CFG["dbname"],
        user=_CFG["user"], password=_CFG["password"], connect_timeout=5)


def setUpModule():
    if not _ISO_OK:
        return
    _ISO.setup()
    if _ISO.schema is None:
        return
    conn = _schema_connect()
    try:
        cur = conn.cursor()
        # search-tours also reads custom_tours; create a minimal one (no rows)
        # in the throwaway schema so the real route runs.
        cur.execute(
            f'CREATE TABLE IF NOT EXISTS "{_ISO.schema}".custom_tours ('
            "custom_tour_id SERIAL PRIMARY KEY, tour_name VARCHAR(255), "
            "request_string TEXT, lat DOUBLE PRECISION, lng DOUBLE PRECISION, "
            "number_requested INTEGER DEFAULT 0, original_tour_id INTEGER)")
        cur.execute(
            'ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS track VARCHAR(16) '
            "NOT NULL DEFAULT 'beta'")
        conn.commit()
    finally:
        conn.close()
    mapsvc._TRACK_COLUMN = None
    mapsvc._HAS_UNACCENT = None


def tearDownModule():
    if _ISO_OK and _ISO is not None:
        _ISO.teardown()


@unittest.skipUnless(_ISO_OK and _ISO.db_up(), "dev Postgres not reachable")
class RealDbSearchSqlTest(unittest.TestCase):
    """Drives map_delivery_service.py /search-tours against seeded rows so the
    ACTUAL SQL WHERE (not just the Python filter) is exercised."""

    @classmethod
    def setUpClass(cls):
        mapsvc.app.config["TESTING"] = True
        cls.client = mapsvc.app.test_client()
        cls.lat, cls.lng = 10.9334, 108.2873
        cls.tag = uuid.uuid4().hex[:8]
        cls.name466 = f"Seafood restaurants in Mui Ne, Vietnam - Tour {cls.tag}"
        conn = _schema_connect()
        try:
            cur = conn.cursor()
            # 466-shape tour (subscribed), plus two decoys on other tracks.
            cur.execute(
                "INSERT INTO audio_tours (tour_name, request_string, lat, lng, "
                "number_requested, is_test, track) VALUES (%s,%s,%s,%s,%s,FALSE,%s) "
                "RETURNING id",
                (cls.name466, "seafood restaurants mui ne vietnam",
                 cls.lat, cls.lng, 12, "subscribed"))
            cls.id466 = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO audio_tours (tour_name, request_string, lat, lng, "
                "number_requested, is_test, track) VALUES (%s,%s,%s,%s,%s,FALSE,%s)",
                (f"Pizza places in Rome {cls.tag}", "pizza rome italy",
                 41.9, 12.5, 99, "beta"))
            cur.execute(
                "INSERT INTO audio_tours (tour_name, request_string, lat, lng, "
                "number_requested, is_test, track) VALUES (%s,%s,%s,%s,%s,FALSE,%s)",
                (f"Street food in Hanoi {cls.tag}", "street food hanoi vietnam",
                 21.0, 105.8, 50, "beta"))
            conn.commit()
        finally:
            conn.close()
        mapsvc._TRACK_COLUMN = None
        mapsvc._HAS_UNACCENT = None

    def _ids(self, query, extra=""):
        from urllib.parse import quote
        resp = self.client.get(f"/search-tours?query={quote(query)}{extra}")
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        return [r["id"] for r in resp.get_json()["tours"]]

    def test_four_queries_find_466(self):
        for q in Q_MATCH:
            ids = self._ids(q)
            self.assertIn(self.id466, ids,
                          f"query {q!r} must find tour 466 via real SQL")

    def test_pizza_does_not_match_466(self):
        ids = self._ids(Q_NOMATCH)
        self.assertNotIn(self.id466, ids,
                         "'Mui Ne pizza' must not match the seafood tour")

    def test_response_shape_unchanged(self):
        from urllib.parse import quote
        resp = self.client.get(f"/search-tours?query={quote('Mui Ne seafood')}")
        body = resp.get_json()
        self.assertEqual(set(body), {"tours", "count", "pattern"})
        row = next(r for r in body["tours"] if r["id"] == self.id466)
        for key in ("id", "name", "request_string", "lat", "lng",
                    "distance_km", "popularity", "type", "is_custom"):
            self.assertIn(key, row)
        for internal in ("_rank_all_in_name", "_rank_words_in_name",
                         "_rank_created_at"):
            self.assertNotIn(internal, row)

    def test_track_filter_unchanged(self):
        # ?track=subscribed → the subscribed 466 is present for a vietnam search.
        ids = self._ids("vietnam", extra="&track=subscribed")
        self.assertIn(self.id466, ids)
        # Under track=beta the subscribed 466 must NOT appear (filter unchanged).
        ids_only_beta = self._ids("vietnam", extra="&track=beta")
        self.assertNotIn(self.id466, ids_only_beta)


if __name__ == "__main__":
    unittest.main(verbosity=2)
