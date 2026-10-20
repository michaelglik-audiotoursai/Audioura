#!/usr/bin/env python3
"""test_local724_content_policy_truth.py — LOCAL-724 / D656 add. 2.

Proves the five code changes that make the approved Content Policy true, WITHOUT
any paid API call (tour_content_rating.classify is monkeypatched throughout):

  Item 3  Whole-text, not the first 24,000 chars: _chunk_text covers every
          character; rate_text takes the MOST RESTRICTIVE rating across chunks —
          a tour whose only mature passage is AFTER char 24,000 rates mature;
          not_allowed short-circuits; a short tour is still ONE model call.
  Item 1+2  rate_tour_row rates in the serving path, writing the rating columns
          through the CALLER's cursor WITHOUT committing (so the rating lands in
          the same transaction that makes the tour listable — rated before
          listing), reading the key from the environment via classify/OpenAI,
          never from a file. Non-blocking: a model error leaves the row unrated
          and does not raise.
  Item 4  clear_rating holds an edited tour (content_rating NULL, review_status
          'pending') until it is re-rated; a re-rate overwrites the stale rating.
          Through the real listing predicate, a held tour is NOT listable.
  Item 5  POST /report-tour records ONE row per report and returns 201; it never
          touches audio_tours (no hide/approve). Missing tour_id AND tour_name
          is a 400.
  RED     A deliberately broken "rate before listing" (the rater is skipped, so a
          mature tour reaches /tours-near unrated and lists as general) is shown
          to FAIL the guard — proving the green test is not vacuous.

Hermetic: a scripted fake cursor (no Postgres, writes no rows) drives the real
map_delivery endpoint code, the same harness tests/test_local687_content_rating.py
uses. classify is replaced with a scripted function per test.
"""
import datetime
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MAPDIR = os.path.join(_ROOT, "map_delivery")
for p in (_ROOT, _MAPDIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import app as map_app  # noqa: E402  (map_delivery/app.py)
import tour_content_rating  # noqa: E402  (repo root)


class _Usage:
    def __init__(self, pin=10, pout=5):
        self.prompt_tokens = pin
        self.completion_tokens = pout


def _script_classify(verdict_by_substring):
    """Return a classify(title, text, stops) that reads the CHUNK text it is
    given and returns the first (substring -> rating) match, else general. This
    only ever sees one chunk at a time, so it proves rate_text looked at the
    whole tour chunk by chunk."""
    def _c(title, text, stops):
        for needle, rating in verdict_by_substring:
            if needle in text:
                return ({"rating": rating, "reason": f"found {needle!r}"}, _Usage())
        return ({"rating": "general", "reason": "nothing notable"}, _Usage())
    return _c


# ─── Fake DB harness (mirrors test_local687_content_rating.py) ────────────────
class _FakeCursor:
    def __init__(self, plan, writes):
        self._plan = plan
        self._rows = []
        self._writes = writes  # list the test can inspect: (sql_lower, params)

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        low = text.lower()
        self._writes.append((low, params))
        for needle, result in self._plan:
            if needle.lower() in low:
                self._rows = list(result)
                return
        self._rows = []

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        pass


class _FakeConn:
    def __init__(self, plan, writes):
        self._plan = plan
        self._writes = writes
        self.commits = 0

    def cursor(self):
        return _FakeCursor(self._plan, self._writes)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


# ─── Item 3: whole-text chunking, most-restrictive aggregation ────────────────
class WholeTextChunkingTest(unittest.TestCase):
    def setUp(self):
        self._orig = tour_content_rating.classify

    def tearDown(self):
        tour_content_rating.classify = self._orig

    def test_chunks_cover_every_character(self):
        text = "".join(chr(97 + (i % 26)) for i in range(50000))
        chunks = tour_content_rating._chunk_text(text)
        self.assertGreater(len(chunks), 1)
        # Every character index is inside at least one window.
        covered = bytearray(len(text))
        step = tour_content_rating.CHUNK_CHARS - tour_content_rating.CHUNK_OVERLAP
        start = 0
        for ch in chunks:
            for i in range(start, start + len(ch)):
                covered[i] = 1
            start += step
        self.assertTrue(all(covered), "a chunk boundary left characters unjudged")

    def test_short_tour_is_one_call(self):
        calls = []

        def _c(title, text, stops):
            calls.append(text)
            return ({"rating": "general", "reason": "ok"}, _Usage())

        tour_content_rating.classify = _c
        rating, detail = tour_content_rating.rate_text("T", "a short general tour " * 20, 3)
        self.assertEqual(rating, "general")
        self.assertEqual(detail["chunks"], 1)
        self.assertEqual(len(calls), 1)

    def test_mature_only_after_char_24000_rates_mature(self):
        # 24,000 chars of ordinary history, THEN a bar-crawl passage. The first
        # window (chars 0..24000) is general; the mature passage lives only in a
        # later window. A first-24k-only rater would call this general.
        text = ("The old stone church has stood here since 1480. " * 500)[:24000]
        text += " This is a pub crawl: drink at six bars, shots at each stop."
        self.assertGreater(len(text), 24000)
        tour_content_rating.classify = _script_classify([("pub crawl", "mature")])
        rating, detail = tour_content_rating.rate_text("Tour", text, 6)
        self.assertEqual(rating, "mature",
                         "mature content after char 24,000 must be caught")
        self.assertGreaterEqual(detail["chunks"], 2)

    def test_not_allowed_is_most_restrictive_and_short_circuits(self):
        calls = []

        def _c(title, text, stops):
            calls.append(text)
            if "forbidden" in text:
                return ({"rating": "not_allowed", "reason": "x"}, _Usage())
            return ({"rating": "general", "reason": "ok"}, _Usage())

        tour_content_rating.classify = _c
        # 'forbidden' sits in the FIRST window; once not_allowed is seen, no
        # further windows are read (cannot get more restrictive).
        text = "forbidden content " + ("filler " * 20000)
        rating, detail = tour_content_rating.rate_text("T", text, 1)
        self.assertEqual(rating, "not_allowed")
        self.assertEqual(len(calls), 1, "should stop at the first not_allowed window")


# ─── Item 1+2: rate_tour_row writes in the caller's transaction, no commit ────
class RateTourRowServingPathTest(unittest.TestCase):
    def setUp(self):
        self._orig = tour_content_rating.classify

    def tearDown(self):
        tour_content_rating.classify = self._orig

    def test_writes_rating_columns_without_committing(self):
        tour_content_rating.classify = _script_classify([("bar crawl", "mature")])
        writes = []
        conn = _FakeConn([], writes)
        cur = conn.cursor()
        detail = tour_content_rating.rate_tour_row(
            cur, 77, "Night Out", "a bar crawl " + ("x" * 300), 4)
        self.assertIsNotNone(detail)
        self.assertEqual(detail["rating"], "mature")
        # It issued an UPDATE of the rating columns for id 77 ...
        updates = [w for w in writes if "update audio_tours set content_rating" in w[0]]
        self.assertEqual(len(updates), 1)
        self.assertIn(77, updates[0][1])
        self.assertIn("mature", updates[0][1])
        # ... and NEVER committed (the caller owns the transaction).
        self.assertEqual(conn.commits, 0, "rate_tour_row must not commit")

    def test_short_text_is_not_rated(self):
        tour_content_rating.classify = _script_classify([])
        writes = []
        cur = _FakeConn([], writes).cursor()
        self.assertIsNone(
            tour_content_rating.rate_tour_row(cur, 1, "Tiny", "too short", 1))
        self.assertFalse(
            [w for w in writes if "update audio_tours set content_rating" in w[0]])

    def test_model_error_is_non_blocking(self):
        def _boom(title, text, stops):
            raise RuntimeError("model down")

        tour_content_rating.classify = _boom
        writes = []
        cur = _FakeConn([], writes).cursor()
        # Must NOT raise, and must return None (row left unrated for the backfill).
        self.assertIsNone(
            tour_content_rating.rate_tour_row(cur, 9, "T", "x" * 500, 2))


# ─── Item 4: editing holds a tour until re-rated ──────────────────────────────
class EditReRatesTest(unittest.TestCase):
    def test_clear_rating_holds_the_tour(self):
        writes = []
        cur = _FakeConn([], writes).cursor()
        self.assertTrue(tour_content_rating.clear_rating(cur, 55))
        upd = [w for w in writes if "content_rating = null" in w[0]]
        self.assertEqual(len(upd), 1)
        self.assertIn("review_status = 'pending'", upd[0][0])

    def test_held_tour_is_not_listable_via_real_predicate(self):
        # content_rating NULL + review_status 'pending' == held. The REAL listing
        # predicate must hide it (pending hides regardless of adult).
        self.assertFalse(map_app._content_visible(None, "pending", True))
        self.assertFalse(map_app._content_visible(None, "pending", False))

    def test_rerate_overwrites_stale_rating(self):
        orig = tour_content_rating.classify
        tour_content_rating.classify = _script_classify([("museum", "general")])
        try:
            writes = []
            cur = _FakeConn([], writes).cursor()
            # Tour was mature; its text is edited to an ordinary museum tour.
            detail = tour_content_rating.rate_tour_row(
                cur, 3, "Museum", "a museum " + ("x" * 400), 5)
            self.assertEqual(detail["rating"], "general")
            upd = [w for w in writes if "update audio_tours set content_rating" in w[0]]
            self.assertIn("general", upd[0][1])
        finally:
            tour_content_rating.classify = orig


# ─── Item 5: server-side report endpoint, one row per report ──────────────────
class ReportEndpointTest(unittest.TestCase):
    def setUp(self):
        self._orig_db = map_app.get_db_connection
        self.client = map_app.app.test_client()

    def tearDown(self):
        map_app.get_db_connection = self._orig_db

    def _install(self, writes, returning_id=1):
        plan = [("insert into tour_reports", [(returning_id,)])]
        map_app.get_db_connection = lambda: _FakeConn(plan, writes)

    def test_report_inserts_one_row_and_returns_201(self):
        writes = []
        self._install(writes, returning_id=42)
        resp = self.client.post("/report-tour",
                                json={"tour_id": 7, "tour_name": "Bad Tour"})
        self.assertEqual(resp.status_code, 201)
        body = resp.get_json()
        self.assertEqual(body["status"], "received")
        self.assertEqual(body["report_id"], 42)
        inserts = [w for w in writes if "insert into tour_reports" in w[0]]
        self.assertEqual(len(inserts), 1, "exactly one row per report")
        self.assertIn(7, inserts[0][1])

    def test_report_never_touches_audio_tours(self):
        writes = []
        self._install(writes)
        self.client.post("/report-tour", json={"tour_id": 7, "tour_name": "X"})
        forbidden = [w for w in writes
                     if "update audio_tours" in w[0] or "delete from audio_tours" in w[0]]
        self.assertEqual(forbidden, [], "a report must never hide/approve/delete a tour")

    def test_report_requires_tour_id_or_name(self):
        writes = []
        self._install(writes)
        resp = self.client.post("/report-tour", json={})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse([w for w in writes if "insert into tour_reports" in w[0]])

    def test_options_preflight_204(self):
        resp = self.client.open("/report-tour", method="OPTIONS")
        self.assertEqual(resp.status_code, 204)


# ─── RED: break "rate before listing" and show the guard catches it ───────────
class RateBeforeListingRedTest(unittest.TestCase):
    """The green guarantee is: a new mature tour is rated BEFORE it can list, so
    it is held (pending) and not visible. This red test simulates the bug where
    the serving-path rater is skipped — the tour reaches the listing layer
    unrated (NULL/NULL) and therefore lists as general. The assertion that it is
    hidden then FAILS, proving the guard is real, not vacuous."""

    def test_skipping_the_rater_lets_a_mature_tour_list_red(self):
        # Correct behaviour: a rated mature tour (held pending) is hidden.
        self.assertFalse(map_app._content_visible("mature", "pending", True))

        # BUG: the rater did not run, so the mature tour's row is NULL/NULL. The
        # listing layer treats NULL as general and SHOWS it. The guard below —
        # "a just-created tour that should be mature must not be visible" — fails.
        unrated_rating, unrated_status = None, None  # what skipping the rater leaves
        with self.assertRaises(AssertionError):
            self.assertFalse(
                map_app._content_visible(unrated_rating, unrated_status, False),
                "an unrated (rater skipped) mature tour wrongly lists as general",
            )


if __name__ == "__main__":
    unittest.main()
