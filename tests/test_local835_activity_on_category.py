"""test_local835_activity_on_category.py — LOCAL-835.

Unit tests, pure/offline, using the EXACT field strings from the ticket:

  GCloud_Storied wave 12 proof 507, gen 00018-8vt, cheap arm for all categories —
  "Kiteboarding lessons in Mui Ne, Vietnam" (5) returned Deja Vu Restaurant, Kite
  Bar, Sea Breeze Restaurant, Source Kiteboarding, Mui Ne Fishing Village. Only
  ONE (Source Kiteboarding) is a kite school. The FRESH places path (pool did not
  serve this request) still let food/leisure places and a generic landmark
  through. LOCAL-830 wired an on-category check only into POOL REUSE, and its
  business detector does not treat "lessons"/"classes"/"courses"/"rental"/"hire"
  as an activity-provider request.

An ACTIVITY-PROVIDER request (lessons, classes, courses, school, rental, hire,
instructor, centre/center, club for a sport) must keep ONLY providers of that
activity. Food/drink venues are off-category (unless the request is about food).
A generic landmark (fishing village, beach) is off-category for a provider
request unless it is a named anchor. Honest shortfall over padding: the guard
only ever REMOVES off-category candidates.

Run:
    python3 -m pytest tests/test_local835_activity_on_category.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ───────────── requested_activity — provider-request detection ───────────────
class TestRequestedActivity:
    def test_kiteboarding_lessons_is_provider_request(self):
        from category_match_guard import requested_activity
        act = requested_activity("Kiteboarding lessons in Mui Ne, Vietnam")
        assert act is not None
        assert act["trigger"] == "lessons"
        assert act["is_food"] is False
        # Synonyms let a candidate named "kitesurf" / "kite" match.
        assert "kite" in act["tokens"]
        assert "kitesurf" in act["tokens"]

    def test_all_provider_triggers_detected(self):
        from category_match_guard import requested_activity
        cases = {
            "Yoga classes in Hoi An": "classes",
            "Scuba diving courses in Nha Trang": "courses",
            "Bike rental in Hoi An": "rental",
            "Surf school in Da Nang": "school",
            "Kiteboarding instructor in Mui Ne": "instructor",
            "Surfboard hire in Da Nang": "hire",
            "Dive centre in Nha Trang": "centre",
        }
        for req, trig in cases.items():
            act = requested_activity(req)
            assert act is not None, req
            assert act["trigger"] == trig, (req, act)

    def test_non_provider_requests_are_none(self):
        from category_match_guard import requested_activity
        for req in ("Museums in Paris",
                    "Pagodas and temples of Ho Chi Minh City",
                    "Old Saigon walking tour, District 1",
                    "Art centers in Berlin",      # weak trigger, not an activity
                    "Book clubs in London",       # weak trigger, not an activity
                    "City tour of Rome",          # weak trigger "tour", no activity
                    "Kiteboarding"):              # one-word subject, no trigger
            assert requested_activity(req) is None, req

    def test_cooking_classes_is_a_provider_request(self):
        # A cooking CLASS asks for a cooking school/provider, not restaurants —
        # so it is a provider request (is_food False: "cooking" is not a "find me
        # restaurants" word).
        from category_match_guard import requested_activity
        act = requested_activity("Cooking classes in Hoi An")
        assert act is not None
        assert act["trigger"] == "classes"


# ───────────── filter — the exact ticket 5 names ─────────────────────────────
class TestKiteboardingLessonsFiveNames:
    # The EXACT five stops the field tour returned (fresh path, cheap arm).
    ROWS = [
        {"name": "Deja Vu Restaurant", "_serper_category": "Restaurant"},
        {"name": "Kite Bar", "_serper_category": "Bar"},
        {"name": "Sea Breeze Restaurant", "_serper_category": "Restaurant"},
        {"name": "Source Kiteboarding", "_serper_category": "Kiteboarding school"},
        {"name": "Mui Ne Fishing Village", "_serper_category": "Tourist attraction"},
    ]

    def test_only_source_kiteboarding_kept(self):
        from category_match_guard import filter_off_category_activity
        logs = []
        kept, dropped = filter_off_category_activity(
            list(self.ROWS), "Kiteboarding lessons in Mui Ne, Vietnam",
            log=logs.append)
        assert [r["name"] for r in kept] == ["Source Kiteboarding"]
        assert dropped == 4
        # Every off-category drop is logged with the LOCAL-835 marker.
        joined = " ".join(logs)
        for off in ("Deja Vu Restaurant", "Kite Bar", "Sea Breeze Restaurant",
                    "Mui Ne Fishing Village"):
            assert off in joined, off
        assert "[LOCAL-835]" in joined

    def test_kite_bar_dropped_even_though_name_has_kite(self):
        # "Kite Bar" carries the activity word "kite" but is a BAR — a food/drink
        # venue is off-category regardless of the activity word in its name.
        from category_match_guard import candidate_is_activity_provider, requested_activity
        act = requested_activity("Kiteboarding lessons in Mui Ne")
        assert candidate_is_activity_provider(
            {"name": "Kite Bar", "_serper_category": "Bar"}, act) is False

    def test_fishing_village_dropped_as_generic_landmark(self):
        from category_match_guard import candidate_is_activity_provider, requested_activity
        act = requested_activity("Kiteboarding lessons in Mui Ne")
        assert candidate_is_activity_provider(
            {"name": "Mui Ne Fishing Village",
             "_serper_category": "Tourist attraction"}, act) is False

    def test_input_list_not_mutated(self):
        from category_match_guard import filter_off_category_activity
        original = list(self.ROWS)
        before = len(original)
        filter_off_category_activity(
            original, "Kiteboarding lessons in Mui Ne", log=lambda *_: None)
        assert len(original) == before


# ───────────── filter — the other ticket cases ──────────────────────────────
class TestOtherTicketCases:
    def test_kitesurfing_schools_still_five_of_five(self):
        from category_match_guard import filter_off_category_activity
        rows = [
            {"name": "Jibe's Beach Club", "_serper_category": "Kitesurfing school"},
            {"name": "Muine Kitesurf School (MKS)", "_serper_category": "Water sports center"},
            {"name": "C2Sky KiteSurfing", "_serper_category": ""},
            {"name": "Palm Kite Club Mui Ne", "_serper_category": ""},
            {"name": "Source Kiteboarding", "_serper_category": "Kiteboarding school"},
        ]
        kept, dropped = filter_off_category_activity(
            rows, "Kitesurfing schools in Mui Ne", log=lambda *_: None)
        assert dropped == 0
        assert len(kept) == 5

    def test_seafood_restaurants_keeps_restaurants(self):
        # "Seafood restaurants" is NOT an activity-provider request → no-op.
        from category_match_guard import filter_off_category_activity, requested_activity
        assert requested_activity("Seafood restaurants in Mui Ne") is None
        rows = [
            {"name": "Bo Ke Seafood", "_serper_category": "Seafood restaurant"},
            {"name": "Sandals Restaurant", "_serper_category": "Restaurant"},
        ]
        kept, dropped = filter_off_category_activity(
            rows, "Seafood restaurants in Mui Ne", log=lambda *_: None)
        assert dropped == 0
        assert [r["name"] for r in kept] == ["Bo Ke Seafood", "Sandals Restaurant"]

    def test_yoga_classes_keeps_only_studios(self):
        from category_match_guard import filter_off_category_activity
        rows = [
            {"name": "Nguyen Yoga Studio", "_serper_category": "Yoga studio"},
            {"name": "Morning Glory Restaurant", "_serper_category": "Restaurant"},
            {"name": "An Bang Beach", "_serper_category": "Beach"},
        ]
        kept, dropped = filter_off_category_activity(
            rows, "Yoga classes in Hoi An", log=lambda *_: None)
        assert [r["name"] for r in kept] == ["Nguyen Yoga Studio"]
        assert dropped == 2

    def test_scuba_diving_courses_keeps_only_dive_providers(self):
        from category_match_guard import filter_off_category_activity
        rows = [
            {"name": "Rainbow Divers", "_serper_category": "Scuba diving center"},
            {"name": "Sailing Club Nha Trang", "_serper_category": "Bar"},
            {"name": "Nha Trang Beach", "_serper_category": "Beach"},
        ]
        kept, dropped = filter_off_category_activity(
            rows, "Scuba diving courses in Nha Trang", log=lambda *_: None)
        assert [r["name"] for r in kept] == ["Rainbow Divers"]
        assert dropped == 2

    def test_bike_rental_keeps_only_bike_providers(self):
        from category_match_guard import filter_off_category_activity
        rows = [
            {"name": "Hoi An Bicycle Tours", "_serper_category": "Bicycle rental"},
            {"name": "Banh Mi Phuong", "_serper_category": "Sandwich shop"},
            {"name": "Japanese Covered Bridge", "_serper_category": "Tourist attraction"},
        ]
        kept, dropped = filter_off_category_activity(
            rows, "Bike rental in Hoi An", log=lambda *_: None)
        assert [r["name"] for r in kept] == ["Hoi An Bicycle Tours"]
        assert dropped == 2


# ───────────── named anchors, type-field, honest shortfall, safety ───────────
class TestAnchorsTypeFieldAndSafety:
    def test_named_landmark_anchor_kept(self):
        # A generic landmark the user named by hand is kept even on a provider tour.
        from category_match_guard import filter_off_category_activity
        rows = [{"name": "Mui Ne Fishing Village", "_serper_category": "Tourist attraction"}]
        kept, dropped = filter_off_category_activity(
            rows, "Kiteboarding lessons near Mui Ne Fishing Village",
            named_anchors=["Mui Ne Fishing Village"], log=lambda *_: None)
        assert dropped == 0
        assert len(kept) == 1

    def test_serper_type_field_used(self):
        # A candidate whose NAME gives no activity signal is kept on its Serper
        # `type` ("Water sports center") — the places API's own category field.
        from category_match_guard import candidate_is_activity_provider, requested_activity
        act = requested_activity("Kiteboarding lessons in Mui Ne")
        cand = {"name": "Jibe's", "type": "Water sports center"}
        assert candidate_is_activity_provider(cand, act) is True

    def test_unclassifiable_candidate_kept(self):
        # No signal either way → None → kept (never drop a place we cannot classify).
        from category_match_guard import filter_off_category_activity
        rows = [{"name": "C2Sky", "_serper_category": ""}]
        kept, dropped = filter_off_category_activity(
            rows, "Kiteboarding lessons in Mui Ne", log=lambda *_: None)
        assert dropped == 0
        assert len(kept) == 1

    def test_honest_shortfall_never_pads(self):
        # When only ONE provider exists among five candidates, the guard returns
        # exactly that one — it never invents or substitutes a food/leisure place.
        from category_match_guard import filter_off_category_activity
        rows = [
            {"name": "Source Kiteboarding", "_serper_category": "Kiteboarding school"},
            {"name": "Deja Vu Restaurant", "_serper_category": "Restaurant"},
            {"name": "Kite Bar", "_serper_category": "Bar"},
            {"name": "Sea Breeze Restaurant", "_serper_category": "Restaurant"},
            {"name": "Mui Ne Fishing Village", "_serper_category": "Beach"},
        ]
        kept, dropped = filter_off_category_activity(
            rows, "Kiteboarding lessons in Mui Ne", log=lambda *_: None)
        assert len(kept) == 1  # honest shortfall, not padded back to 5
        assert kept[0]["name"] == "Source Kiteboarding"

    def test_empty_list_is_safe(self):
        from category_match_guard import filter_off_category_activity
        kept, dropped = filter_off_category_activity(
            [], "Kiteboarding lessons in Mui Ne", log=lambda *_: None)
        assert kept == []
        assert dropped == 0

    def test_non_provider_request_is_noop(self):
        from category_match_guard import filter_off_category_activity
        rows = [{"name": "Louvre", "_serper_category": "Art museum"}]
        kept, dropped = filter_off_category_activity(
            rows, "Museums in Paris", log=lambda *_: None)
        assert dropped == 0
        assert len(kept) == 1


# ───────────── fresh-path wiring in generate_tour_text ───────────────────────
class TestFreshPathWiring:
    def test_generate_tour_text_imports_the_activity_guard(self):
        # The fresh places path must reference the LOCAL-835 guard import so the
        # on-category check runs after discovery and in the replenish loop.
        import re
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "generate_tour_text.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        assert "filter_off_category_activity" in src
        assert "requested_activity" in src
        # The post-discovery guard and both replenish filters are present.
        assert src.count("filter_off_category_activity") >= 3
        assert "[LOCAL-835] activity-provider guard active" in src


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
