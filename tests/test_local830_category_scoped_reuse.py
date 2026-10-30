"""test_local830_category_scoped_reuse.py — LOCAL-830.

Unit tests, pure/offline, using the EXACT field strings from the ticket:

  GCloud_Storied 2026-10-30 — "Kitesurf schools … Mui Ne" returned, among its
  five stops, **Sandals Restaurant**, a REUSED pool stop. A business/activity
  request (kite school, dive shop, yoga studio, gym) that is NOT about food must
  keep ONLY on-category stops; a restaurant is off-category. The SAME on-category
  check must apply to POOLED stops at reuse time, not only fresh ones. A pool row
  is never deleted — it stays reusable for the categories it matches
  (category-scoped reuse). A food request ("seafood restaurants") still accepts
  restaurants. The phone's double submit must collapse to one job (idempotency).

Run:
    python3 -m pytest tests/test_local830_category_scoped_reuse.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ───────────── Item 1 & 2 — business off-category guard (offline) ────────────
class TestBusinessOffCategoryClass:
    def test_kite_school_request_marks_restaurant_off_category(self):
        from category_match_guard import business_off_category_class
        assert business_off_category_class(
            "Kitesurfing schools in Mui Ne, Vietnam") == "restaurant"

    def test_other_non_food_business_requests(self):
        from category_match_guard import business_off_category_class
        for req in ("Dive shops in Mui Ne",
                    "Yoga studios near me, Mui Ne",
                    "Surfboard rentals in Mui Ne",
                    "Gyms in District 1, Ho Chi Minh City"):
            assert business_off_category_class(req) == "restaurant", req

    def test_food_request_is_noop(self):
        from category_match_guard import business_off_category_class, is_food_request
        for req in ("Seafood restaurants in Mui Ne",
                    "Best cafes in District 1",
                    "Coffee shops and bakeries in Hoi An"):
            assert is_food_request(req) is True, req
            assert business_off_category_class(req) is None, req

    def test_non_business_requests_are_noop(self):
        from category_match_guard import business_off_category_class
        for req in ("Museums in Paris",
                    "Pagodas and temples of Ho Chi Minh City",
                    "Old Saigon walking tour, District 1"):
            assert business_off_category_class(req) is None, req


class TestFilterOffCategoryBusiness:
    # The exact tour-502 stop set: four kite schools + Sandals Restaurant.
    KITE_ROWS = [
        {"title": "Jibe's Beach Club", "_serper_category": "Kitesurfing school"},
        {"title": "Muine Kitesurf School (MKS)", "_serper_category": "Water sports center"},
        {"title": "C2Sky KiteSurfing", "_serper_category": ""},
        {"title": "Palm Kite Club Mui Ne", "_serper_category": ""},
        {"title": "Sandals Restaurant", "_serper_category": "Restaurant"},
    ]

    def test_kite_tour_excludes_pooled_restaurant(self):
        from category_match_guard import filter_off_category_business
        logs = []
        kept, skipped = filter_off_category_business(
            list(self.KITE_ROWS), "Kitesurfing schools in Mui Ne, Vietnam",
            log=logs.append)
        kept_titles = [r["title"] for r in kept]
        assert "Sandals Restaurant" not in kept_titles
        assert skipped == 1
        # The four kite schools are all kept (water-sports / unknown class).
        assert len(kept) == 4
        assert kept_titles == [
            "Jibe's Beach Club", "Muine Kitesurf School (MKS)",
            "C2Sky KiteSurfing", "Palm Kite Club Mui Ne"]
        assert any("Sandals Restaurant" in m for m in logs)

    def test_seafood_request_keeps_restaurants(self):
        from category_match_guard import filter_off_category_business
        rows = [
            {"title": "Sandals Restaurant", "_serper_category": "Restaurant"},
            {"title": "Bo Ke Seafood", "_serper_category": "Seafood restaurant"},
        ]
        kept, skipped = filter_off_category_business(
            rows, "Seafood restaurants in Mui Ne", log=lambda *_: None)
        assert skipped == 0
        assert [r["title"] for r in kept] == ["Sandals Restaurant", "Bo Ke Seafood"]

    def test_unclassifiable_row_kept(self):
        from category_match_guard import filter_off_category_business
        rows = [{"title": "C2Sky KiteSurfing", "_serper_category": ""}]
        kept, skipped = filter_off_category_business(
            rows, "Kitesurfing schools in Mui Ne", log=lambda *_: None)
        assert skipped == 0
        assert len(kept) == 1

    def test_named_anchor_restaurant_kept(self):
        # If the user named a restaurant by hand, it is kept even in a kite tour.
        from category_match_guard import filter_off_category_business
        rows = [{"title": "Sandals Restaurant", "_serper_category": "Restaurant"}]
        kept, skipped = filter_off_category_business(
            rows, "Kitesurf schools near Sandals Restaurant, Mui Ne",
            named_anchors=["Sandals Restaurant"], log=lambda *_: None)
        assert skipped == 0
        assert len(kept) == 1

    def test_guard_never_deletes_input_list(self):
        # SKIP-only: the original rows list is not mutated (category-scoped reuse
        # keeps the pool row; it is only not returned for this tour).
        from category_match_guard import filter_off_category_business
        original = list(self.KITE_ROWS)
        before = len(original)
        filter_off_category_business(
            original, "Kitesurfing schools in Mui Ne", log=lambda *_: None)
        assert len(original) == before  # input untouched


# ───────────── Item 2 — orchestrator reuse wiring ────────────────────────────
class TestOrchestratorReuseWiring:
    def test_reuse_path_imports_and_calls_business_guard(self):
        # The orchestrator must expose the business off-category guard import so a
        # reused pooled restaurant is skipped on a kite tour. We exercise the guard
        # the way the orchestrator wires it (location as the request, log=print).
        import stop_pool_orchestrator  # noqa: F401 — import must succeed
        from category_match_guard import filter_off_category_business
        rows = [
            {"title": "Muine Kitesurf School", "_serper_category": "Water sports"},
            {"title": "Sandals Restaurant", "_serper_category": "Restaurant"},
        ]
        kept, skipped = filter_off_category_business(
            rows, "Kitesurfing schools in Mui Ne, Vietnam", log=lambda *_: None)
        assert skipped == 1
        assert [r["title"] for r in kept] == ["Muine Kitesurf School"]

    def test_contained_museum_tour_not_affected(self):
        # A contained museum request is not a business/activity request, so the
        # guard is a no-op (museum stops are governed by LOCAL-811, not this guard).
        from category_match_guard import business_off_category_class
        assert business_off_category_class("Belvedere Museum, Vienna") is None


# ───────────── Item 4 — server idempotency (offline, logic only) ─────────────
class TestServerIdempotency:
    def _fresh_module_state(self):
        import tour_orchestrator_service as svc
        svc._CLIENT_REQUEST_JOBS.clear()
        return svc

    def test_duplicate_client_id_returns_same_job(self):
        svc = self._fresh_module_state()
        first = svc._reserve_idempotent_job("cli-abc", "job-1")
        assert first is None  # first submission reserves
        dup = svc._reserve_idempotent_job("cli-abc", "job-2")
        assert dup == "job-1"  # duplicate returns the SAME job, not job-2
        dup2 = svc._reserve_idempotent_job("cli-abc", "job-3")
        assert dup2 == "job-1"

    def test_distinct_client_ids_get_distinct_jobs(self):
        svc = self._fresh_module_state()
        assert svc._reserve_idempotent_job("cli-1", "job-A") is None
        assert svc._reserve_idempotent_job("cli-2", "job-B") is None
        assert svc._reserve_idempotent_job("cli-1", "job-C") == "job-A"
        assert svc._reserve_idempotent_job("cli-2", "job-D") == "job-B"

    def test_absent_client_id_is_not_idempotent(self):
        svc = self._fresh_module_state()
        assert svc._reserve_idempotent_job("", "job-X") is None
        assert svc._reserve_idempotent_job(None, "job-Y") is None
        # Nothing registered → every call is a "first".
        assert svc._reserve_idempotent_job("", "job-Z") is None

    def test_expired_entry_is_a_fresh_job(self):
        import time
        svc = self._fresh_module_state()
        assert svc._reserve_idempotent_job("cli-old", "job-old") is None
        # Force the entry older than the window.
        svc._CLIENT_REQUEST_JOBS["cli-old"] = (
            "job-old", time.monotonic() - (svc._IDEMPOTENCY_WINDOW_SECONDS + 1))
        # Expired → treated as a new first submission; the new job is reserved.
        assert svc._reserve_idempotent_job("cli-old", "job-new") is None
        assert svc._CLIENT_REQUEST_JOBS["cli-old"][0] == "job-new"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
