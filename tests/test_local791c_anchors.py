"""test_local791c_anchors.py — LOCAL-791C item 1.

REGRESSION the 791B live run exposed: "Pagodas and temples of HCMC (Jade Emperor
Pagoda, Thien Hau Temple)" asked 5 stops and got 3 (Giac Lam, Xa Loi, Phuoc An Hoi
Quan) — NEITHER named anchor. At LOCAL-790 the same request gave 5 stops WITH both
anchors.

Root cause (these tests pin it): the 791B naming + off-category steps took their
named-anchor list from intent.named_places (restaurant/venue only) +
extract_named_places_from_clause ("including X" only) — BOTH EMPTY for this
request. The request names its anchors in PARENTHESES, which live in
named_anchors(user_request)['anchors']. With an empty anchor list the title step
renamed "Jade Emperor Pagoda" → "Jade Emperor Pagoda (Chùa Ngọc Hoàng)", losing
the user's verbatim wording that every downstream title-keyed gate relies on.

Fix asserted here:
  * named_anchors() DOES extract the parenthetical anchors (the correct source).
  * title_for_candidate keeps the user's EXACT wording when the full anchor set is
    passed, and would reformat it when the (wrong) empty list is passed.
  * the off-category guard keeps the worship anchors either way.

Run:
    python3 -m pytest tests/test_local791c_anchors.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REQUEST = "Pagodas and temples of HCMC (Jade Emperor Pagoda, Thien Hau Temple)"


class TestParentheticalAnchorsAreTheSource:
    def test_named_anchors_extracts_the_parenthetical_anchors(self):
        from generate_tour_text import named_anchors
        anchors = named_anchors(REQUEST)["anchors"]
        assert "Jade Emperor Pagoda" in anchors
        assert "Thien Hau Temple" in anchors

    def test_the_791b_sources_are_empty_for_this_request(self):
        # The exact bug: the two lists 791B used carry NEITHER anchor.
        import area_resolver as ar
        assert ar.extract_named_places_from_clause(REQUEST) == []
        # intent.named_places for a worship/category request is empty by design
        # (the intent prompt restricts named_places to restaurants/venues/shops).


class TestUserWordingKeptVerbatim:
    def test_anchor_kept_verbatim_with_full_anchor_set(self):
        from place_title_naming import title_for_candidate
        from generate_tour_text import named_anchors
        cand = {
            "name": "Jade Emperor Pagoda",
            "label_en": "Jade Emperor Pagoda",
            "label_local": "Chùa Ngọc Hoàng",
            "_serper_title": "Ngoc Hoang Pagoda",
            "_anchor": True,
        }
        anchors = named_anchors(REQUEST)["anchors"]
        # With the CORRECT (full) anchor set, the user's wording is verbatim.
        assert title_for_candidate(cand, "en", named_anchors=anchors) == "Jade Emperor Pagoda"

    def test_empty_anchor_list_reproduces_the_bug(self):
        from place_title_naming import title_for_candidate
        cand = {
            "name": "Jade Emperor Pagoda",
            "label_en": "Jade Emperor Pagoda",
            "label_local": "Chùa Ngọc Hoàng",
        }
        # The 791B bug: with the empty list the anchor is reformatted (not verbatim).
        assert (title_for_candidate(cand, "en", named_anchors=[])
                == "Jade Emperor Pagoda (Chùa Ngọc Hoàng)")

    def test_thien_hau_temple_also_verbatim(self):
        from place_title_naming import title_for_candidate
        from generate_tour_text import named_anchors
        cand = {"name": "Thien Hau Temple", "label_local": "Chùa Bà Thiên Hậu"}
        anchors = named_anchors(REQUEST)["anchors"]
        assert title_for_candidate(cand, "en", named_anchors=anchors) == "Thien Hau Temple"


class TestOffCategoryKeepsWorshipAnchors:
    def test_worship_anchors_survive_the_guard(self):
        from category_match_guard import filter_off_category, requested_categories
        from generate_tour_text import named_anchors
        pois = [
            {"name": "Jade Emperor Pagoda", "_anchor": True},
            {"name": "Thien Hau Temple", "_anchor": True},
            {"name": "Giac Lam Pagoda"},
            {"name": "Xa Loi Pagoda"},
            {"name": "Tao Dan Park", "_serper_category": "Park"},
        ]
        anchors = named_anchors(REQUEST)["anchors"]
        kept = filter_off_category(pois, REQUEST, log=lambda *_: None,
                                   named_anchors=anchors)
        kept_names = [p["name"] for p in kept]
        assert "Jade Emperor Pagoda" in kept_names
        assert "Thien Hau Temple" in kept_names
        assert "Tao Dan Park" not in kept_names  # the off-category park is dropped
        assert requested_categories(REQUEST) == {"worship"}


class TestAnchorsNeverRenamedByTheWalkingTitleStep:
    """The impl skips renaming a poi flagged _anchor/user_explicit — this asserts
    the contract the impl relies on: an anchor keeps its name even when the step
    runs. (title_for_candidate is what the impl calls for non-anchors.)"""

    def test_anchor_flag_means_verbatim_regardless(self):
        from place_title_naming import title_for_candidate
        from generate_tour_text import named_anchors
        anchors = named_anchors(REQUEST)["anchors"]
        for nm in ("Jade Emperor Pagoda", "Thien Hau Temple"):
            cand = {"name": nm, "label_local": "x", "_serper_title": "y"}
            assert title_for_candidate(cand, "en", named_anchors=anchors) == nm

    def test_gloss_contains_anchor_is_recognised(self):
        # The impl's gloss-aware restore: when an upstream rename pushed the user's
        # anchor into the parenthetical ("Ngọc Hoàng Pagoda (Jade Emperor Pagoda)"),
        # the anchor is still found inside the "(…)" and the title is restored.
        import re
        from place_title_naming import is_named_anchor
        from generate_tour_text import named_anchors
        anchors = named_anchors(REQUEST)["anchors"]
        name = "Ngọc Hoàng Pagoda (Jade Emperor Pagoda)"
        # primary does not match …
        assert is_named_anchor(name, anchors) is None
        # … but the parenthetical content does.
        gloss = re.search(r"\(([^)]*)\)", name).group(1)
        assert is_named_anchor(gloss, anchors) == "Jade Emperor Pagoda"
