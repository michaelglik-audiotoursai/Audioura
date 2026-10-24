#!/usr/bin/env python3
"""test_local756_pool_named_place.py — LOCAL-756 issue B.

"Walking tour in Danvers, MA including witchcraft victims memorial" was served
from the stop pool (tour 736, stored BEFORE LOCAL-751), so neither the area
parser nor apply_named_place_policy ran and the Witchcraft Victims Memorial was
silently missing again (D562). Field log:

    [LOCAL-590] pool: venue=loc:walking tour in danvers ma including … pooled=4
    [LOCAL-590] POOL DELIVERY: reused=4 new=0 …
    Stop 1: The Rebecca Nurse Homestead / Stop 2: Endicott Park /
    Stop 3: Danvers State Hospital / Stop 4: Danvers Town Hall

None of the 4 pooled stops is the memorial the request NAMES.

LOCAL-756 B fix: pool delivery must apply the SAME named-place rule — when the
request names a place not among the pooled stops, the pool must NOT serve the
tour as-is; it falls through to full generation so apply_named_place_policy runs
(the named place becomes a verified stop, or is announced — never silently
dropped). Also: pooled stops written by an older pipeline (a lower pool_version)
are regenerated, not served verbatim.

RED on aeaae8f9: the orchestrator serves the pool directly (no named-place gate,
no stale-version compare), so maybe_generate_with_pool returns a served result.
GREEN after the fix: it returns None (regenerate) for both the named-place miss
and the stale-row case.

Run: python3 -m pytest test_local756_pool_named_place.py -q
"""
import unittest

import stop_pool_orchestrator as orch
import stop_pool_store as store


REQUEST = "Walking tour in Danvers, MA including witchcraft victims memorial"

# The EXACT 4 pooled stops from the field run (tour 736) — none is the memorial.
POOLED_FIELD = [
    {"title": "The Rebecca Nurse Homestead", "narration": "…", "pool_version": store.POOL_VERSION},
    {"title": "Endicott Park", "narration": "…", "pool_version": store.POOL_VERSION},
    {"title": "Danvers State Hospital", "narration": "…", "pool_version": store.POOL_VERSION},
    {"title": "Danvers Town Hall", "narration": "…", "pool_version": store.POOL_VERSION},
]


class TestPoolCoversNamedPlaces(unittest.TestCase):
    def test_pool_missing_the_named_place_is_not_covered(self):
        self.assertFalse(
            orch._pool_covers_named_places(REQUEST, POOLED_FIELD),
            "a pool with none of the request's named places must NOT be "
            "considered covered")

    def test_pool_containing_the_named_place_is_covered(self):
        pooled = POOLED_FIELD + [
            {"title": "Witchcraft Victims Memorial",
             "narration": "…", "pool_version": store.POOL_VERSION}]
        self.assertTrue(
            orch._pool_covers_named_places(REQUEST, pooled),
            "a pool that already contains the named place may be served")

    def test_request_without_a_named_place_is_always_covered(self):
        self.assertTrue(
            orch._pool_covers_named_places("Walking tour in Danvers, MA",
                                           POOLED_FIELD))


class TestPoolStaleRows(unittest.TestCase):
    def test_a_row_below_current_pool_version_is_stale(self):
        stale = [dict(POOLED_FIELD[0], pool_version=store.POOL_VERSION - 1)]
        self.assertTrue(orch._pool_has_stale_rows(stale))

    def test_all_current_rows_are_not_stale(self):
        self.assertFalse(orch._pool_has_stale_rows(POOLED_FIELD))


class TestDeliveryRegeneratesOnNamedPlaceMiss(unittest.TestCase):
    """The full entry decides NOT to serve the Danvers pool verbatim: it returns
    None so the caller regenerates and the named-place policy runs."""

    def setUp(self):
        self._saved = {}
        import stop_pool_store as pool

        def _save(mod, name):
            self._saved[(mod, name)] = getattr(mod, name)

        _save(orch, "pool") if hasattr(orch, "pool") else None
        # maybe_generate_with_pool imports stop_pool_store as `pool` locally, so
        # patch the module's functions directly.
        _save(pool, "resolve_venue_identity")
        _save(pool, "get_pool_stops")
        pool.resolve_venue_identity = lambda location, city="": "loc:" + location.lower()
        pool.get_pool_stops = lambda *a, **k: list(POOLED_FIELD)

    def tearDown(self):
        for (mod, name), val in self._saved.items():
            if val is not None:
                setattr(mod, name, val)

    def test_pool_does_not_serve_when_named_place_missing(self):
        _called = {"gen": False}

        def _fake_generate(*a, **k):
            _called["gen"] = True
            return ("", None, None)

        result = orch.maybe_generate_with_pool(
            location=REQUEST,
            tour_type="walking",
            total_stops=4,
            db_url="postgresql://x/y",   # not used: get_pool_stops is stubbed
            generate_fn=_fake_generate,
        )
        self.assertIsNone(
            result,
            "pool must NOT serve the Danvers tour as-is when the named memorial "
            "is absent — it must return None so the caller regenerates")


if __name__ == "__main__":
    unittest.main(verbosity=2)
