#!/usr/bin/env python3
"""
LOCAL-588 — add a cache version to the tour-cache key (D359).

`tour_cache_layer1` keyed on (normalised location, tour_type, stop bucket) with
NO code version, so a repeated request forever got the tour made by the code of
the day it was first stored (e.g. Michael's Griffin junk tour 391, served to
every later 4–6-stop Griffin request with none of LOCAL-580/583/584 applied).

TOUR_CACHE_VERSION folds a code generation into the key hash (like
venue_resolver.CORPUS_VERSION). This suite verifies, as pure functions so no DB
is needed:

  1. The version is part of the key: the SAME request hashes to DIFFERENT keys
     under different versions (miss after a bump), and to the SAME key under the
     same version (hit).
  2. A bump leaves the LOCAL-494 bucket + collision behaviour intact: 4 and 6
     still collide, 11+ still exact, different venue/type still never collide —
     the version only shifts ALL keys together, it does not reshape buckets.
  3. The [S20] lookup log line and the never-delete guarantee are documented.
"""
import hashlib
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tour_cache_layer1 as cache


class TestCacheVersionConstant(unittest.TestCase):
    def test_version_starts_at_two(self):
        """AC1: TOUR_CACHE_VERSION ships at 2 — v1 rows (old code) are retired."""
        self.assertGreaterEqual(cache.TOUR_CACHE_VERSION, 2)  # bumped to 3 by LEAD 2026-10-06

    def test_version_is_in_the_key(self):
        """The constant actually participates in the hash."""
        key = cache._cache_key("Griffin Museum of Photography", "walking", 4)
        bucket = cache._stop_bucket(4)
        expected = hashlib.sha256(
            f"v{cache.TOUR_CACHE_VERSION}|griffin museum of photography|walking|{bucket}"
            .encode("utf-8")
        ).hexdigest()
        self.assertEqual(key, expected)


class TestVersionBumpInvalidates(unittest.TestCase):
    LOC = "Griffin Museum of Photography, Winchester, MA"
    TYPE = "walking"
    STOPS = 4

    def _key_at_version(self, version):
        with mock.patch.object(cache, "TOUR_CACHE_VERSION", version):
            return cache._cache_key(self.LOC, self.TYPE, self.STOPS)

    def test_same_version_same_key_hit(self):
        """Same request + same version → identical key (a HIT)."""
        self.assertEqual(self._key_at_version(2), self._key_at_version(2))

    def test_version_bump_changes_key_miss(self):
        """Same request after a version bump → different key (a MISS)."""
        k_v2 = self._key_at_version(2)
        k_v3 = self._key_at_version(3)
        self.assertNotEqual(
            k_v2, k_v3,
            "bumping TOUR_CACHE_VERSION must change the key so old rows miss",
        )

    def test_old_version_rows_unreachable(self):
        """A row stored under v1 is unreachable once code runs at v2+."""
        k_v1 = self._key_at_version(1)
        k_v2 = self._key_at_version(2)
        self.assertNotEqual(k_v1, k_v2)

    def test_legacy_fallback_key_also_versioned(self):
        """The migration-fallback key is version-gated too (no old-code bypass)."""
        with mock.patch.object(cache, "TOUR_CACHE_VERSION", 2):
            lk2 = cache._legacy_cache_key(self.LOC, self.TYPE, self.STOPS)
        with mock.patch.object(cache, "TOUR_CACHE_VERSION", 3):
            lk3 = cache._legacy_cache_key(self.LOC, self.TYPE, self.STOPS)
        self.assertNotEqual(lk2, lk3)


class TestBucketBehaviourUnchangedByVersion(unittest.TestCase):
    """A version bump shifts ALL keys together; it must not reshape LOCAL-494
    bucketing. Re-assert the bucket collisions at the current version."""

    def test_four_and_six_still_collide(self):
        self.assertEqual(cache._cache_key("X", "museum", 4),
                         cache._cache_key("X", "museum", 6))

    def test_one_two_three_still_collide(self):
        keys = {cache._cache_key("X", "museum", n) for n in (1, 2, 3)}
        self.assertEqual(len(keys), 1)

    def test_seven_through_ten_still_collide(self):
        keys = {cache._cache_key("X", "museum", n) for n in (7, 8, 9, 10)}
        self.assertEqual(len(keys), 1)

    def test_eleven_plus_still_exact(self):
        self.assertNotEqual(cache._cache_key("X", "museum", 10),
                            cache._cache_key("X", "museum", 11))

    def test_different_venue_or_type_still_never_collides(self):
        self.assertNotEqual(cache._cache_key("A", "museum", 4),
                            cache._cache_key("B", "museum", 4))
        self.assertNotEqual(cache._cache_key("A", "museum", 4),
                            cache._cache_key("A", "restaurant", 4))


class TestLookupLogLine(unittest.TestCase):
    """AC2 — every lookup logs `[S20] cache v<N> HIT|MISS key=<first 12>`.

    No DB in this suite; we assert the log line shape against a mocked
    connection so the string contract is pinned.
    """

    def test_miss_logs_s20_line(self):
        key = cache._cache_key("Nowhere", "walking", 3)
        with mock.patch.object(cache, "psycopg2") as pg, \
             self.assertLogs(cache.logger, level="INFO") as cm:
            conn = mock.MagicMock()
            pg.connect.return_value = conn
            cur = conn.cursor.return_value.__enter__.return_value
            cur.fetchone.return_value = None
            cache.get_cached_tour("Nowhere", "walking", 3, "postgresql://x")
        line = f"[S20] cache v{cache.TOUR_CACHE_VERSION} MISS key={key[:12]}"
        self.assertTrue(
            any(line in m for m in cm.output),
            f"expected a MISS log line {line!r}, got {cm.output}",
        )

    def test_hit_logs_s20_line(self):
        key = cache._cache_key("Somewhere", "walking", 3)
        with mock.patch.object(cache, "psycopg2") as pg, \
             self.assertLogs(cache.logger, level="INFO") as cm:
            conn = mock.MagicMock()
            pg.connect.return_value = conn
            cur = conn.cursor.return_value.__enter__.return_value
            # (tour_content, total_stops) — same count so no trim path.
            cur.fetchone.return_value = ("Step-by-Step Audio Guided Tour: X\n", 3)
            cache.get_cached_tour("Somewhere", "walking", 3, "postgresql://x")
        line = f"[S20] cache v{cache.TOUR_CACHE_VERSION} HIT key={key[:12]}"
        self.assertTrue(
            any(line in m for m in cm.output),
            f"expected a HIT log line {line!r}, got {cm.output}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)


def test_lead_cache_never_serves_fewer_stops_than_requested(monkeypatch):
    """A 4-stop tour cached in the 4–6 bucket must NOT answer a 6-stop request (LEAD 2026-10-05;
    LOCAL-590's live run saw `CACHE HIT: Boston Common / walking / 6` return 4 stops)."""
    import tour_cache_layer1 as t

    class _Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a, **k): pass
        def fetchone(self): return ("Stop 1: A\n\nStop 2: B\n\nStop 3: C\n\nStop 4: D\n", 4)
        def close(self): pass

    class _Conn:
        def cursor(self): return _Cur()
        def commit(self): pass
        def close(self): pass

    monkeypatch.setattr(t.psycopg2, "connect", lambda *a, **k: _Conn())
    assert t.get_cached_tour("Boston Common, Boston, MA", "walking", 6, "postgresql://x") is None
    # and a request for FEWER than cached is still a (trimmed) hit
    assert t.get_cached_tour("Boston Common, Boston, MA", "walking", 4, "postgresql://x") is not None
