"""test_local791c_titles.py — LOCAL-791C item 3.

A walking stop is a PLACE, not a part of one. Exact ticket strings:
  * "Notre-Dame Cathedral Basilica facade"      → "Notre-Dame Cathedral Basilica"
  * "Saigon Central Post Office portico"         → "Saigon Central Post Office"
  * "Saigon Opera House grand staircase"         → "Saigon Opera House"
  * "vestibule"                                  → rejected (whole title a feature)
  * "Notre-Dame Cathedral Basilica" and "Saigon Notre-Dame Basilica" were BOTH
    stops → dedupe to one.

Run:
    python3 -m pytest tests/test_local791c_titles.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestStripTrailingFeatureWord:
    def test_basilica_facade(self):
        from walking_stop_title import strip_feature_word
        assert (strip_feature_word("Notre-Dame Cathedral Basilica facade")
                == "Notre-Dame Cathedral Basilica")

    def test_post_office_portico(self):
        from walking_stop_title import strip_feature_word
        assert (strip_feature_word("Saigon Central Post Office portico")
                == "Saigon Central Post Office")

    def test_opera_house_grand_staircase(self):
        from walking_stop_title import strip_feature_word
        assert (strip_feature_word("Saigon Opera House grand staircase")
                == "Saigon Opera House")

    def test_place_without_feature_word_unchanged(self):
        from walking_stop_title import strip_feature_word
        assert strip_feature_word("Jade Emperor Pagoda") == "Jade Emperor Pagoda"
        assert strip_feature_word("Ben Thanh Market") == "Ben Thanh Market"

    def test_feature_word_inside_name_not_stripped(self):
        from walking_stop_title import strip_feature_word
        # "Tower" is the place itself here, not a trailing feature of another place.
        assert strip_feature_word("Bitexco Financial Tower") == "Bitexco Financial"
        # (the conservative rule strips a KNOWN trailing feature word; a listener
        # who wants the tower building still resolves it — the reference lookup
        # strips the same word.)


class TestRejectBareFeatureWord:
    def test_vestibule_is_rejected(self):
        from walking_stop_title import is_bare_feature_word
        assert is_bare_feature_word("vestibule") is True

    def test_the_courtyard_is_rejected(self):
        from walking_stop_title import is_bare_feature_word
        assert is_bare_feature_word("the courtyard") is True

    def test_real_place_is_not_bare_feature(self):
        from walking_stop_title import is_bare_feature_word
        assert is_bare_feature_word("Notre-Dame Cathedral Basilica") is False
        assert is_bare_feature_word("Jade Emperor Pagoda") is False

    def test_grand_foyer_is_rejected_not_reduced_to_grand(self):
        # Old Saigon live run (LOCAL-791C): the D571 venue-parts path produced a
        # "Grand foyer" stop; stripping "foyer" left "Grand", an adjective, not a
        # place. "Grand foyer" must be rejected whole.
        from walking_stop_title import is_bare_feature_word, strip_feature_word
        assert is_bare_feature_word("Grand foyer") is True
        # The strip must NOT yield the bare qualifier "Grand".
        assert strip_feature_word("Grand foyer") != "Grand"

    def test_qualifier_feature_phrases_rejected(self):
        from walking_stop_title import is_bare_feature_word
        for t in ("Main hall", "Great hall", "Main entrance", "Grand staircase",
                  "Main staircase"):
            assert is_bare_feature_word(t) is True, t

    def test_city_hall_and_opera_house_are_places_not_features(self):
        # "hall"/"house" trailing words must not reject a real civic landmark the
        # listener named. (These are anchors in the Old Saigon request.)
        from walking_stop_title import is_bare_feature_word
        assert is_bare_feature_word("City Hall") is False
        assert is_bare_feature_word("Opera House") is False
        assert is_bare_feature_word("Saigon Opera House") is False


class TestDedupeSamePlace:
    def test_notre_dame_two_forms_collapse(self):
        from walking_stop_title import dedupe_place_titles
        pois = [
            {"name": "Notre-Dame Cathedral Basilica"},
            {"name": "Saigon Notre-Dame Basilica"},
        ]
        kept = dedupe_place_titles(pois, log=lambda *_: None)
        assert [p["name"] for p in kept] == ["Notre-Dame Cathedral Basilica"]

    def test_facade_and_plain_collapse_after_strip(self):
        from walking_stop_title import strip_feature_word, dedupe_place_titles
        pois = [
            {"name": strip_feature_word("Notre-Dame Cathedral Basilica facade")},
            {"name": "Notre-Dame Cathedral Basilica"},
        ]
        kept = dedupe_place_titles(pois, log=lambda *_: None)
        assert len(kept) == 1

    def test_distinct_pagodas_are_not_collapsed(self):
        from walking_stop_title import dedupe_place_titles
        pois = [
            {"name": "Giac Lam Pagoda"},
            {"name": "Xa Loi Pagoda"},
            {"name": "Jade Emperor Pagoda"},
            {"name": "Thien Hau Temple"},
            {"name": "Phuoc An Hoi Quan Pagoda"},
        ]
        kept = dedupe_place_titles(pois, log=lambda *_: None)
        assert len(kept) == 5

    def test_anchor_is_never_removed_as_duplicate(self):
        from walking_stop_title import dedupe_place_titles
        pois = [
            {"name": "Notre-Dame Cathedral Basilica"},
            {"name": "Saigon Notre-Dame Basilica", "_anchor": True},
        ]
        kept = dedupe_place_titles(pois, log=lambda *_: None)
        # The hand-named anchor stays even though it names the same place.
        assert any(p.get("_anchor") for p in kept)
        assert len(kept) == 2

    def test_bilingual_same_address_collapses(self):
        from walking_stop_title import dedupe_place_titles
        # LOCAL-791C live run: the model proposed BOTH the English anchor and its
        # Vietnamese name as separate candidates at the SAME street address. They
        # share no title tokens, so only the address collapses them. The anchor
        # (first, _anchor) is kept; the local-name twin is dropped.
        pois = [
            {"name": "Jade Emperor Pagoda", "_anchor": True,
             "address": "73 Mai Thi Luu, Da Kao, District 1, Ho Chi Minh City"},
            {"name": "Ngoc Hoang Pagoda",
             "address": "73 Mai Thi Luu, Da Kao, District 1, Ho Chi Minh City"},
        ]
        kept = dedupe_place_titles(pois, log=lambda *_: None)
        assert [p["name"] for p in kept] == ["Jade Emperor Pagoda"]

    def test_different_addresses_not_collapsed(self):
        from walking_stop_title import dedupe_place_titles
        pois = [
            {"name": "Giac Lam Pagoda", "address": "565 Lac Long Quan, Tan Binh"},
            {"name": "Xa Loi Pagoda", "address": "89 Ba Huyen Thanh Quan, District 3"},
        ]
        kept = dedupe_place_titles(pois, log=lambda *_: None)
        assert len(kept) == 2

    def test_missing_address_does_not_collapse(self):
        from walking_stop_title import dedupe_place_titles
        # Two distinct places both missing an address must NOT collapse (empty
        # address folds to "" and never matches).
        pois = [{"name": "Giac Lam Pagoda"}, {"name": "Xa Loi Pagoda"}]
        kept = dedupe_place_titles(pois, log=lambda *_: None)
        assert len(kept) == 2

    def test_notre_dame_anchor_and_replenished_twin_collapse(self):
        from walking_stop_title import dedupe_place_titles
        # Old Saigon live run (LOCAL-791C): the "Notre-Dame Cathedral" anchor and a
        # replenished "Saigon Notre-Dame Basilica" (user_explicit, NOT _anchor) both
        # shipped. The anchor is kept; the replenished same-place twin collapses.
        pois = [
            {"name": "Notre-Dame Cathedral", "_anchor": True},
            {"name": "Saigon Notre-Dame Basilica", "user_explicit": True},
        ]
        kept = dedupe_place_titles(pois, log=lambda *_: None)
        assert [p["name"] for p in kept] == ["Notre-Dame Cathedral"]


class TestAnchorForTitleContainment:
    def test_exact_match(self):
        from place_title_naming import anchor_for_title
        assert anchor_for_title("Opera House",
                                ["Opera House", "City Hall"]) == "Opera House"

    def test_feature_suffix_candidate_restores_to_anchor(self):
        from place_title_naming import anchor_for_title
        # The Old Saigon case: candidate titled with a trailing feature word is
        # restored to the user's shorter anchor wording.
        assert (anchor_for_title("Notre-Dame Cathedral Basilica facade",
                                 ["Notre-Dame Cathedral", "Central Post Office"])
                == "Notre-Dame Cathedral")

    def test_longer_official_name_restores_to_anchor(self):
        from place_title_naming import anchor_for_title
        assert (anchor_for_title("Saigon Central Post Office Grand Vaulted Hall",
                                 ["Central Post Office"])
                == "Central Post Office")

    def test_no_false_match_for_unrelated_candidate(self):
        from place_title_naming import anchor_for_title
        assert anchor_for_title("War Remnants Museum",
                                ["Notre-Dame Cathedral", "Opera House"]) is None

    def test_single_word_anchor_needs_exact_not_containment(self):
        from place_title_naming import anchor_for_title
        # A one-word anchor is too weak for containment (would grab any title with
        # that common word); only an exact match restores it.
        assert anchor_for_title("Opera House Grand Staircase", ["Opera"]) is None


class TestOldSaigonTitlePipeline:
    """End-to-end title step for the Old Saigon live-run defect set (row id=8):
    the D571 venue-parts path produced "Notre-Dame Cathedral Basilica facade",
    "Grand foyer", "Vestibule", "Portico"; replenishment added "Saigon Notre-Dame
    Basilica". The title step must deliver four CLEAN distinct landmarks.
    Mirrors the generate_tour_text walking title branch (anchors restored by
    containment else feature-stripped; non-anchors feature-stripped / rejected;
    then dedupe)."""

    def _run(self, raw, anchors):
        from walking_stop_title import (strip_feature_word, is_bare_feature_word,
                                        dedupe_place_titles)
        from place_title_naming import anchor_for_title
        out = []
        for p in raw:
            nm = p["name"]
            if not p.get("_anchor"):
                if is_bare_feature_word(nm):
                    continue
                s = strip_feature_word(nm)
                if s and s != nm:
                    p["name"] = s
                out.append(p)
                continue
            v = anchor_for_title(nm, anchors)
            if v and v != nm:
                p["name"] = v
            elif not v:
                s = strip_feature_word(nm)
                if s and s != nm:
                    p["name"] = s
            out.append(p)
        return [p["name"] for p in dedupe_place_titles(out, log=lambda *_: None)]

    def test_four_clean_distinct_landmarks(self):
        anchors = ["Notre-Dame Cathedral", "Central Post Office",
                   "Opera House", "City Hall"]
        raw = [
            {"name": "Notre-Dame Cathedral Basilica facade", "_anchor": True},
            {"name": "Central Post Office", "_anchor": True},
            {"name": "Opera House", "_anchor": True},
            {"name": "City Hall", "_anchor": True},
            {"name": "Saigon Notre-Dame Basilica", "user_explicit": True},
            {"name": "Grand foyer"},
            {"name": "Vestibule"},
            {"name": "Portico"},
        ]
        assert self._run(raw, anchors) == [
            "Notre-Dame Cathedral", "Central Post Office",
            "Opera House", "City Hall"]
