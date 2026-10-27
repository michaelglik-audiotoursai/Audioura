#!/usr/bin/env python3
"""LOCAL-788 item 1/A — a REUSED (pooled or mined) stop must pass the SAME
LOCAL-786 scope test as a new lookup before it is counted toward K.

Evidence (GCloud Subscribed, 2026-10-27): "middle eastern restaurants near me,
west Roxbury, MA" (tour 454's exact wording) reused yesterday's Stardust (West
Roxbury, correct) + Byblos (Norwood, ~10 km) from the stop pool. LOCAL-786's
``_bind_in_scope`` only runs on NEW place lookups; the pool reuse path
(``stop_pool_orchestrator``) never re-checked scope, so the ~10 km Norwood place
rode into a West Roxbury tour unchecked.

The fix reuses the LOCAL-786 scope helpers verbatim through the new public
``places_search.row_in_scope``, called by
``stop_pool_orchestrator._revalidate_pooled_scope`` before K is counted. Rejected
rows are dropped from THIS tour only; nothing is deleted from the pool.

Fixtures only — no live web, no DB.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import places_search as ps
import stop_pool_orchestrator as orch


# West Roxbury centre + its real bbox (from the LOCAL-786 fixtures). Byblos is in
# Norwood, ~10 km south, OUTSIDE the West Roxbury bbox.
_WR_CENTER = (42.2843, -71.1627)
_WR_BBOX = ["42.255", "42.302", "-71.185", "-71.135"]

_STARDUST = {
    "title": "Stardust: Inspired Mediterranean, Persian",
    "address": "1753 Centre St, West Roxbury, MA",
    "coordinates": "42.28744, -71.15047",
}
_BYBLOS_NORWOOD = {
    "title": "Byblos Restaurant",
    "address": "678 Washington St, Norwood, MA 02062",
    "coordinates": "42.1945, -71.1997",
}


# ─────────────────────── row_in_scope: the gate itself ──────────────────────
class TestRowInScope:
    def test_byblos_norwood_rejected_by_bbox(self):
        keep, reason, dist = ps.row_in_scope(
            _BYBLOS_NORWOOD["coordinates"], _BYBLOS_NORWOOD["address"],
            "West Roxbury, MA", scope_center=_WR_CENTER, scope_bbox=_WR_BBOX)
        assert keep is False
        assert dist > 5.0  # ~10 km away

    def test_byblos_rejected_by_radius_without_bbox(self):
        # With no bbox, Byblos is still rejected: its Norwood address is a
        # town-name mismatch, and failing that the ~2.5 km NEIGHBOURHOOD radius
        # drops a 10 km spillover.
        keep, reason, dist = ps.row_in_scope(
            _BYBLOS_NORWOOD["coordinates"], _BYBLOS_NORWOOD["address"],
            "West Roxbury, MA", scope_center=_WR_CENTER)
        assert keep is False
        assert reason  # a concrete reject reason was recorded

    def test_coordless_far_place_rejected_by_radius(self):
        # A place whose address does NOT name a town (so no mismatch) but whose
        # coords are ~10 km away is rejected purely by the radius.
        keep, reason, dist = ps.row_in_scope(
            _BYBLOS_NORWOOD["coordinates"], "678 Washington St",
            "West Roxbury, MA", scope_center=_WR_CENTER)
        assert keep is False
        assert "km" in reason

    def test_byblos_town_mismatch_with_bbox(self):
        # Even if a loose radius would admit it, a Norwood address OUTSIDE the
        # West Roxbury bbox is a town-name mismatch reject.
        keep, reason, dist = ps.row_in_scope(
            _BYBLOS_NORWOOD["coordinates"], _BYBLOS_NORWOOD["address"],
            "West Roxbury, MA", scope_center=_WR_CENTER, scope_bbox=_WR_BBOX)
        assert keep is False

    def test_no_coords_kept(self):
        # A coordinate-less stop cannot be proven outside → kept (LOCAL-786 rule).
        keep, reason, dist = ps.row_in_scope(
            "", _BYBLOS_NORWOOD["address"], "West Roxbury, MA",
            scope_center=_WR_CENTER, scope_bbox=_WR_BBOX)
        assert keep is True

    def test_stardust_kept(self):
        keep, reason, dist = ps.row_in_scope(
            _STARDUST["coordinates"], _STARDUST["address"],
            "West Roxbury, MA", scope_center=_WR_CENTER, scope_bbox=_WR_BBOX)
        assert keep is True, reason
        assert dist < 2.0

    def test_near_me_uses_device_coords_3km(self):
        # Device at the West Roxbury centre: Stardust (~1 km) kept, Byblos
        # (~10 km) dropped by the 3 km near-me radius — the device, not the scope
        # centre, is the origin.
        keep_s, _, _ = ps.row_in_scope(
            _STARDUST["coordinates"], _STARDUST["address"], "West Roxbury, MA",
            near=_WR_CENTER)
        keep_b, _, dist_b = ps.row_in_scope(
            _BYBLOS_NORWOOD["coordinates"], _BYBLOS_NORWOOD["address"],
            "West Roxbury, MA", near=_WR_CENTER)
        assert keep_s is True
        assert keep_b is False
        assert dist_b > 3.0


# ─────────── _revalidate_pooled_scope: the orchestrator's reuse gate ─────────
class TestRevalidatePooledScope:
    def _patch_geocoder(self, monkeypatch, center=_WR_CENTER, bbox=_WR_BBOX):
        monkeypatch.setattr(orch, "_geocode_scope",
                            lambda location: (center, bbox))

    def test_byblos_dropped_stardust_kept(self, monkeypatch):
        self._patch_geocoder(monkeypatch)
        rows = [_STARDUST, _BYBLOS_NORWOOD]
        kept, rejected = orch._revalidate_pooled_scope(
            rows, "middle eastern restaurants near me, West Roxbury, MA",
            "restaurant", contained=False)
        titles = [r["title"] for r in kept]
        assert _STARDUST["title"] in titles
        assert _BYBLOS_NORWOOD["title"] not in titles
        assert rejected == 1

    def test_contained_museum_not_revalidated(self, monkeypatch):
        # A museum tour's "stops" are works inside one building; they must NOT be
        # judged against a neighbourhood radius. contained=True → untouched.
        self._patch_geocoder(monkeypatch)
        rows = [_STARDUST, _BYBLOS_NORWOOD]
        kept, rejected = orch._revalidate_pooled_scope(
            rows, "Museum of Fine Arts, Boston", "museum", contained=True)
        assert len(kept) == 2
        assert rejected == 0

    def test_no_geocode_keeps_all(self, monkeypatch):
        # No centre, no bbox, and a scope with no town token to mismatch against →
        # keep everything (cannot prove any stop out of scope).
        monkeypatch.setattr(orch, "_geocode_scope", lambda location: (None, None))
        rows = [_STARDUST, _BYBLOS_NORWOOD]
        kept, rejected = orch._revalidate_pooled_scope(
            rows, "", "restaurant", contained=False)
        assert len(kept) == 2
        assert rejected == 0

    def test_rejection_never_deletes_from_pool(self, monkeypatch):
        # The function only returns a filtered list; the input list (the pool's
        # rows) is never mutated.
        self._patch_geocoder(monkeypatch)
        rows = [dict(_STARDUST), dict(_BYBLOS_NORWOOD)]
        _before = [dict(r) for r in rows]
        orch._revalidate_pooled_scope(
            rows, "West Roxbury, MA", "restaurant", contained=False)
        assert rows == _before  # unchanged


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
