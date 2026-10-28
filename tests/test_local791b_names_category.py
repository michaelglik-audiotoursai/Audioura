"""test_local791b_names_category.py — LOCAL-791B items 1 & 2.

Unit tests, pure/offline, using the EXACT ticket strings:
  * item 1 — English tour title with the local name in parentheses, from the
    user's wording / a Wikidata label in the tour language / the Serper title.
  * item 2 — an off-category stop (Tao Dan Park in a pagodas-and-temples tour) is
    rejected unless the request asks for a mix.

Run:
    python3 -m pytest tests/test_local791b_names_category.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────── Item 1 ─────────────────────────────────────
class TestItem1EnglishTitleLocalParen:
    def test_format_english_with_local_paren(self):
        from place_title_naming import format_place_title
        assert (format_place_title("Jade Emperor Pagoda", "Chùa Ngọc Hoàng")
                == "Jade Emperor Pagoda (Chùa Ngọc Hoàng)")
        assert (format_place_title("Thien Hau Temple", "Chùa Bà Thiên Hậu")
                == "Thien Hau Temple (Chùa Bà Thiên Hậu)")

    def test_same_name_not_doubled(self):
        from place_title_naming import format_place_title
        # Local == primary (accent/case-folded) → single name, no "X (X)".
        assert format_place_title("Ben Thanh Market", "ben thanh market") == "Ben Thanh Market"
        # No empty parentheses when there is no local name.
        assert format_place_title("Independence Palace", "") == "Independence Palace"
        # A primary that already carries a gloss is not wrapped again.
        assert (format_place_title("Jade Emperor Pagoda (Chùa Ngọc Hoàng)", "Chùa Ngọc Hoàng")
                == "Jade Emperor Pagoda (Chùa Ngọc Hoàng)")

    def test_priority1_user_wording_kept_verbatim(self):
        from place_title_naming import title_for_candidate
        # The request NAMED "Jade Emperor Pagoda"; even though Wikidata would offer
        # a different label, the user's exact wording is kept.
        cand = {"name": "Jade Emperor Pagoda",
                "label_en": "Tortoise Pagoda", "label_local": "Chùa Ngọc Hoàng"}
        assert title_for_candidate(
            cand, tour_language="en",
            named_anchors=["Jade Emperor Pagoda"]) == "Jade Emperor Pagoda"

    def test_priority2_wikidata_label_in_tour_language(self):
        from place_title_naming import title_for_candidate
        # Not a named anchor → use the English Wikidata label + local in parens.
        cand = {"name": "Chùa Bà Ấn Độ",
                "label_en": "Mariamman Hindu Temple",
                "label_local": "Chùa Bà Ấn Độ"}
        assert title_for_candidate(cand, tour_language="en") == \
            "Mariamman Hindu Temple (Chùa Bà Ấn Độ)"

    def test_priority2_russian_tour_russian_label(self):
        from place_title_naming import title_for_candidate
        # A Russian tour: the Russian label is the primary name, local in parens.
        cand = {"name": "Notre-Dame Cathedral Basilica of Saigon",
                "labels": {"en": "Saigon Notre-Dame Basilica",
                           "ru": "Собор Сайгонской Богоматери",
                           "vi": "Nhà thờ Đức Bà Sài Gòn"},
                "label_local": "Nhà thờ Đức Bà Sài Gòn"}
        assert title_for_candidate(cand, tour_language="ru") == \
            "Собор Сайгонской Богоматери (Nhà thờ Đức Bà Sài Gòn)"

    def test_priority3_serper_english_title(self):
        from place_title_naming import title_for_candidate
        # No Wikidata labels, no named anchor: fall back to the Serper title, with
        # the local name (if different) in parentheses.
        cand = {"name": "Vinh Nghiem Pagoda",
                "serper_title": "Vinh Nghiem Pagoda",
                "label_local": "Chùa Vĩnh Nghiêm"}
        assert title_for_candidate(cand, tour_language="en") == \
            "Vinh Nghiem Pagoda (Chùa Vĩnh Nghiêm)"

    def test_vietnamese_tour_single_local_name(self):
        from place_title_naming import title_for_candidate
        # A Vietnamese-language tour: the tour-language label IS the local name, so
        # no parenthetical is added.
        cand = {"name": "Chùa Ngọc Hoàng",
                "labels": {"vi": "Chùa Ngọc Hoàng", "en": "Jade Emperor Pagoda"},
                "label_local": "Chùa Ngọc Hoàng"}
        assert title_for_candidate(cand, tour_language="vi") == "Chùa Ngọc Hoàng"


# ─────────────────────────────── Item 2 ─────────────────────────────────────
class TestItem2OffCategoryGuard:
    def test_pagodas_temples_requests_worship_only(self):
        from category_match_guard import requested_categories
        assert requested_categories(
            "Pagodas and temples of HCMC (Jade Emperor Pagoda, Thien Hau Temple)") \
            == {"worship"}

    def test_tao_dan_park_is_off_category(self):
        from category_match_guard import (classify_place,
                                          candidate_matches_category,
                                          requested_categories)
        req = requested_categories("Pagodas and temples of Ho Chi Minh City")
        assert classify_place("Tao Dan Park", "Park") == "park"
        assert candidate_matches_category(
            {"name": "Tao Dan Park", "_serper_category": "Park"}, req) is False

    def test_pagoda_matches_worship(self):
        from category_match_guard import (candidate_matches_category,
                                          requested_categories)
        req = requested_categories("Pagodas and temples of Ho Chi Minh City")
        assert candidate_matches_category(
            {"name": "Jade Emperor Pagoda", "_serper_category": "Buddhist temple"},
            req) is True
        # The Vietnamese local-name word "Chùa" also classifies as worship.
        assert candidate_matches_category(
            {"name": "Chùa Bà Thiên Hậu", "_serper_category": ""}, req) is True

    def test_filter_drops_park_logs_marker(self):
        from category_match_guard import filter_off_category
        logs = []
        cands = [
            {"name": "Ngoc Hoang Pagoda", "_serper_category": "Buddhist temple"},
            {"name": "Chùa Bà Ấn Độ", "_serper_category": "Hindu temple"},
            {"name": "Tao Dan Park", "_serper_category": "Park"},
            {"name": "Vinh Nghiem Pagoda", "_serper_category": "Pagoda"},
            {"name": "Chùa Bà Thiên Hậu", "_serper_category": "Taoist temple"},
        ]
        kept = filter_off_category(
            cands, "Pagodas and temples of Ho Chi Minh City", log=logs.append)
        kept_names = [c["name"] for c in kept]
        assert "Tao Dan Park" not in kept_names
        assert len(kept) == 4
        assert logs == ["[LOCAL-791B] off-category Tao Dan Park park"]

    def test_mix_request_keeps_both(self):
        from category_match_guard import (requested_categories,
                                          filter_off_category)
        req = requested_categories("Temples and parks of Ho Chi Minh City")
        assert req == {"worship", "park"}
        cands = [
            {"name": "Jade Emperor Pagoda", "_serper_category": "Buddhist temple"},
            {"name": "Tao Dan Park", "_serper_category": "Park"},
        ]
        kept = filter_off_category(cands, "Temples and parks of Ho Chi Minh City")
        assert len(kept) == 2

    def test_non_category_request_is_noop(self):
        from category_match_guard import requested_categories, filter_off_category
        # A plain walking/dining request is NOT a category tour → keep everything.
        assert requested_categories(
            "Old Saigon walking tour, District 1, Ho Chi Minh City") == set()
        cands = [{"name": "Tao Dan Park", "_serper_category": "Park"}]
        assert len(filter_off_category(cands, "Old Saigon walking tour")) == 1

    def test_unknown_class_kept(self):
        from category_match_guard import candidate_matches_category, requested_categories
        req = requested_categories("Pagodas and temples of Ho Chi Minh City")
        # A candidate we cannot classify is NOT dropped (verdict None → keep).
        assert candidate_matches_category(
            {"name": "Some Unusual Place", "_serper_category": "Point of interest"},
            req) is None

    def test_named_anchor_kept_even_if_off_category(self):
        from category_match_guard import filter_off_category
        # If the user named "Tao Dan Park" themselves, it is kept despite the
        # worship-only category (the user chose it).
        cands = [{"name": "Tao Dan Park", "_serper_category": "Park"}]
        kept = filter_off_category(
            cands, "Pagodas and temples of HCMC and Tao Dan Park",
            named_anchors=["Tao Dan Park"])
        assert len(kept) == 1


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
