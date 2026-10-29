#!/usr/bin/env python3
"""test_local800_customer_voice.py — LOCAL-800.

"What customers say" for a business/place stop (spa, café, restaurant, shop,
school). The narration for such a stop gets a short, SOURCED "What people say"
paragraph built ONLY from Serper Places data (already fetched — reused) plus AT
MOST ONE extra Serper reviews/search call per stop.

Fixtures only — NO live web. Two recorded Serper payloads: a spa (Ben Thanh
Market) and a café (Jamaica Plain). The one extra Serper call is exercised by
INJECTING recorded review snippets (``review_snippets=``) — no transport is hit.

What it proves (the LOCAL-800 contract):
  * The customer-voice fields (rating, review count, price band, website) survive
    places_search._normalize_serper_place so they are reused with NO extra call.
  * collect_facts + build_paragraph produce a paragraph containing ONLY sourced
    facts, attributed ("Visitors on Google give it 4.8 from about 2,300 reviews…").
  * NO paragraph when rating AND review count are both missing.
  * A complaint is surfaced ONLY when >= 2 snippets agree; one grumble is dropped.
  * Signature items need >= 2 agreeing snippets too; a one-off mention is dropped.
  * No invented numbers: the rating/count/price spoken are exactly the sourced
    values; nothing the sources did not state appears.
  * The [LOCAL-800] log line is emitted with the title, rating, n and items.
  * At most one Serper call: allow_search=False makes none; a single search call
    is made otherwise (asserted by counting a fake transport).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import customer_voice as cv
import places_search as ps


# ───────────────── recorded Serper Places JSON (captured shape) ─────────────
# Spa near Ben Thanh Market, HCMC — the ticket's worked example (rating 4.8,
# ~2,300 reviews, hot-stone massage).
_SERPER_SPA = {
    "places": [
        {"position": 1, "title": "An Spa - Healing & Relax",
         "address": "26 Thu Khoa Huan, Ben Thanh, District 1",
         "latitude": 10.7725, "longitude": 106.6980,
         "rating": 4.8, "ratingCount": 2300, "priceLevel": "$30\u201350",
         "category": "Spa", "website": "https://anspa.vn/",
         "cid": "800000000000000001"},
    ]
}

# Café in Jamaica Plain, Boston (rating 4.6, 512 reviews, $).
_SERPER_CAFE = {
    "places": [
        {"position": 1, "title": "Blue Frog Bakery",
         "address": "3 Green St", "latitude": 42.3101, "longitude": -71.1142,
         "rating": 4.6, "ratingCount": 512, "priceLevel": "$",
         "category": "Bakery", "website": "https://bluefrogbakery.com/",
         "cid": "800000000000000002"},
    ]
}

# Recorded review SNIPPETS (what the single Serper organic "reviews" call returns).
_SPA_SNIPPETS = [
    "Amazing hot stone massage, incredibly relaxing. The staff were friendly and "
    "the rooms spotless.",
    "The hot stone massage is the one to get — so relaxing. A bit expensive but "
    "worth it.",
    "Lovely foot massage and a great hot stone treatment. Very relaxing spot, "
    "family-owned since 2015.",
    "Relaxing spa with clean rooms. Prices are a little expensive for the area, "
    "but the massage was excellent.",
]
_CAFE_SNIPPETS = [
    "Best croissant in JP and a lovely latte. Friendly staff.",
    "Their croissant is buttery and fresh; the latte is great too.",
    "Delicious croissant and a solid latte. Can get crowded on weekends.",
]


# ─────────────────── normalise preserves customer-voice fields ──────────────
class TestNormalizePreservesFields:
    def test_spa_record_carries_rating_count_price_website(self):
        rec = ps._normalize_serper_place(_SERPER_SPA["places"][0])
        assert rec is not None
        assert rec["_serper_rating"] == 4.8
        assert rec["_serper_rating_count"] == 2300
        assert rec["_serper_price_level"] == "$30\u201350"
        assert rec["_serper_website"] == "https://anspa.vn/"

    def test_cafe_record_carries_fields(self):
        rec = ps._normalize_serper_place(_SERPER_CAFE["places"][0])
        assert rec["_serper_rating"] == 4.6
        assert rec["_serper_rating_count"] == 512
        assert rec["_serper_price_level"] == "$"


# ─────────────────────── collect + paragraph: spa ──────────────────────────
class TestSpaParagraph:
    def _facts(self):
        rec = ps._normalize_serper_place(_SERPER_SPA["places"][0])
        return cv.collect_facts(rec, rec["name"], "Ben Thanh Market, Ho Chi Minh City",
                                review_snippets=_SPA_SNIPPETS)

    def test_usable(self):
        assert self._facts()["usable"] is True

    def test_paragraph_has_rating_and_count_attributed(self):
        para = cv.build_paragraph(self._facts())
        assert "Visitors on Google give it 4.8" in para
        assert "2,300" in para  # rounded human figure of 2300
        assert "reviews" in para

    def test_paragraph_names_the_hot_stone_massage(self):
        # Both "hot stone" and "massage" recur in >= 2 snippets.
        para = cv.build_paragraph(self._facts())
        assert "hot stone" in para
        assert "many mention" in para

    def test_paragraph_states_price_band_verbatim(self):
        para = cv.build_paragraph(self._facts())
        assert "$30\u201350" in para

    def test_paragraph_states_since_year(self):
        para = cv.build_paragraph(self._facts())
        assert "2015" in para

    def test_complaint_surfaced_only_because_two_snippets_agree(self):
        # "expensive" appears in 2 snippets → allowed to surface.
        facts = self._facts()
        assert facts["top_complaint"] == "expensive"
        assert "though some find it expensive" in cv.build_paragraph(facts)

    def test_no_invented_numbers(self):
        # Only the sourced numbers appear: 4.8, 2,300, $30–50, 2015 — and nothing
        # like a fabricated "5 stars" or a different review count.
        para = cv.build_paragraph(self._facts())
        assert "4.9" not in para and "4.7" not in para
        assert "3,000" not in para and "1,000" not in para

    def test_log_line_shape(self):
        line = cv.log_line(self._facts())
        assert line.startswith("[LOCAL-800] customer-voice ")
        assert "rating=4.8" in line
        assert "n=2300" in line
        assert "items=" in line


# ─────────────────────── collect + paragraph: cafe ─────────────────────────
class TestCafeParagraph:
    def _facts(self):
        rec = ps._normalize_serper_place(_SERPER_CAFE["places"][0])
        return cv.collect_facts(rec, rec["name"], "Jamaica Plain, Boston",
                                review_snippets=_CAFE_SNIPPETS)

    def test_paragraph_has_rating_and_count(self):
        para = cv.build_paragraph(self._facts())
        assert "Visitors on Google give it 4.6" in para
        assert "510" in para  # 512 rounded to the nearest 10

    def test_names_the_croissant_and_latte(self):
        facts = self._facts()
        assert "croissant" in facts["items"]
        assert "latte" in facts["items"]

    def test_single_complaint_is_suppressed(self):
        # "crowded" appears in ONLY ONE snippet → must NOT surface (ticket: >= 2).
        facts = self._facts()
        assert facts["top_complaint"] == ""
        assert "crowded" not in cv.build_paragraph(facts)


# ─────────────────── no paragraph when rating/count missing ─────────────────
class TestNoParagraphWithoutRatingOrCount:
    def test_record_with_no_rating_or_count_is_not_usable(self):
        rec = {"name": "Mystery Shop", "_serper_category": "Shop"}
        facts = cv.collect_facts(rec, "Mystery Shop", "Boston", allow_search=False)
        assert facts["usable"] is False
        assert cv.build_paragraph(facts) == ""
        assert cv.log_line(facts) == ""

    def test_rating_only_still_makes_a_paragraph(self):
        rec = {"name": "Rated Only", "_serper_rating": 4.5}
        facts = cv.collect_facts(rec, "Rated Only", "Boston", allow_search=False)
        assert facts["usable"] is True
        para = cv.build_paragraph(facts)
        assert "4.5" in para

    def test_count_only_still_makes_a_paragraph(self):
        rec = {"name": "Counted Only", "_serper_rating_count": 180}
        facts = cv.collect_facts(rec, "Counted Only", "Boston", allow_search=False)
        assert facts["usable"] is True
        assert "180" in cv.build_paragraph(facts)


# ───────────────────── complaint threshold (>= 2 snippets) ──────────────────
class TestComplaintThreshold:
    _REC = {"name": "X", "_serper_rating": 4.0, "_serper_rating_count": 100}

    def test_one_complaint_snippet_dropped(self):
        facts = cv.collect_facts(self._REC, "X", "Boston",
                                 review_snippets=["Great place.", "Lovely.",
                                                  "A bit noisy."])
        assert facts["top_complaint"] == ""

    def test_two_complaint_snippets_surface(self):
        facts = cv.collect_facts(self._REC, "X", "Boston",
                                 review_snippets=["A bit noisy.", "Quite noisy inside.",
                                                  "Lovely otherwise."])
        assert facts["top_complaint"] == "noisy"


# ───────────────────── item threshold (>= 2 snippets) ───────────────────────
class TestItemThreshold:
    _REC = {"name": "Y", "_serper_rating": 4.2, "_serper_rating_count": 90}

    def test_one_item_mention_dropped(self):
        facts = cv.collect_facts(self._REC, "Y", "Boston",
                                 review_snippets=["Loved the pho.", "Nice spot.",
                                                  "Friendly service."])
        assert "pho" not in facts["items"]

    def test_two_item_mentions_kept(self):
        facts = cv.collect_facts(self._REC, "Y", "Boston",
                                 review_snippets=["Loved the pho.", "The pho is great.",
                                                  "Good pho and friendly."])
        assert "pho" in facts["items"]


# ───────────────────── at most ONE extra Serper call ───────────────────────
class TestAtMostOneSerperCall:
    def test_allow_search_false_makes_no_call(self, monkeypatch):
        calls = {"n": 0}

        def _boom(url, payload, api_key=None, timeout=12, extra_headers=None):
            calls["n"] += 1
            return 200, b'{"organic":[]}'
        import serper_meter
        monkeypatch.setattr(serper_meter, "serper_post", _boom)
        rec = {"name": "Z", "_serper_rating": 4.0, "_serper_rating_count": 50}
        cv.collect_facts(rec, "Z", "Boston", allow_search=False, api_key="k")
        assert calls["n"] == 0

    def test_allow_search_true_makes_exactly_one_call(self, monkeypatch):
        calls = {"n": 0}
        import json

        def _one(url, payload, api_key=None, timeout=12, extra_headers=None):
            calls["n"] += 1
            body = json.dumps({"organic": [
                {"snippet": "Great latte. Friendly."},
                {"snippet": "Lovely latte and croissant."},
            ]}).encode()
            return 200, body
        import serper_meter
        monkeypatch.setattr(serper_meter, "serper_post", _one)
        monkeypatch.setenv("SERP_API_KEY", "k")
        rec = {"name": "Café Z", "_serper_rating": 4.3, "_serper_rating_count": 77}
        facts = cv.collect_facts(rec, "Café Z", "Boston", allow_search=True)
        assert calls["n"] == 1
        assert facts["searched"] is True

    def test_no_key_makes_no_call(self, monkeypatch):
        calls = {"n": 0}

        def _boom(url, payload, api_key=None, timeout=12, extra_headers=None):
            calls["n"] += 1
            return 200, b'{"organic":[]}'
        import serper_meter
        monkeypatch.setattr(serper_meter, "serper_post", _boom)
        monkeypatch.delenv("SERP_API_KEY", raising=False)
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        rec = {"name": "No Key", "_serper_rating": 4.0, "_serper_rating_count": 20}
        cv.collect_facts(rec, "No Key", "Boston", allow_search=True)
        assert calls["n"] == 0


# ───────────── the ONE call is a Places lookup when rating is missing ────────
class TestPlacesLookupFallback:
    """When a place-type stop was verified on the map by NAME (so it carries no
    rating/count yet), the single allowed call is a Serper Places lookup that GETS
    the rating/count/price — and the organic reviews search is then skipped, so
    total extra calls stay <= 1."""

    def test_places_lookup_supplies_rating_and_skips_review_search(self, monkeypatch):
        places_calls = {"n": 0}
        search_calls = {"n": 0}

        # Fake the Places lookup to return a record with a rating/count/price.
        def _fake_lookup(name, scope):
            places_calls["n"] += 1
            return {"name": name, "_serper_rating": 4.7, "_serper_rating_count": 640,
                    "_serper_price_level": "$$", "_serper_website": "https://x.test/",
                    "_serper_category": "Coffee shop", "_serper_cid": "c1"}
        monkeypatch.setattr(cv, "_serper_places_lookup", _fake_lookup)

        # Any organic reviews search must NOT be made (would exceed the 1-call cap).
        def _count_search(name, scope, api_key=None, timeout=12):
            search_calls["n"] += 1
            return ["Great latte.", "Lovely latte."]
        monkeypatch.setattr(cv, "_serper_review_snippets", _count_search)

        # The stop carries NO rating — only a name.
        facts = cv.collect_facts({"name": "Verified By Name"}, "Verified By Name",
                                 "Jamaica Plain, Boston", allow_search=True)
        assert places_calls["n"] == 1
        assert search_calls["n"] == 0            # <= 1 total extra call
        assert facts["rating"] == 4.7
        assert facts["rating_count"] == 640
        assert facts["usable"] is True
        assert "Visitors on Google give it 4.7" in cv.build_paragraph(facts)

    def test_reused_rating_uses_review_search_not_places_lookup(self, monkeypatch):
        places_calls = {"n": 0}
        search_calls = {"n": 0}

        def _fake_lookup(name, scope):
            places_calls["n"] += 1
            return None
        monkeypatch.setattr(cv, "_serper_places_lookup", _fake_lookup)

        def _count_search(name, scope, api_key=None, timeout=12):
            search_calls["n"] += 1
            return ["Great latte and croissant.", "Lovely latte, fresh croissant."]
        monkeypatch.setattr(cv, "_serper_review_snippets", _count_search)

        # The stop ALREADY carries a rating (reused from the maps path) → no Places
        # lookup; the one call is the reviews search for items/praise.
        rec = {"name": "Has Rating", "_serper_rating": 4.5, "_serper_rating_count": 300}
        facts = cv.collect_facts(rec, "Has Rating", "Jamaica Plain, Boston",
                                 allow_search=True)
        assert places_calls["n"] == 0
        assert search_calls["n"] == 1            # <= 1 total extra call
        assert "latte" in facts["items"]

    def test_places_lookup_not_made_when_search_disallowed(self, monkeypatch):
        places_calls = {"n": 0}

        def _fake_lookup(name, scope):
            places_calls["n"] += 1
            return {"name": name, "_serper_rating": 4.0}
        monkeypatch.setattr(cv, "_serper_places_lookup", _fake_lookup)
        facts = cv.collect_facts({"name": "X"}, "X", "Boston", allow_search=False)
        assert places_calls["n"] == 0
        assert facts["usable"] is False


# ───────────────────────── prompt block + sources ──────────────────────────
class TestPromptBlockAndSources:
    def _facts(self):
        rec = ps._normalize_serper_place(_SERPER_SPA["places"][0])
        return cv.collect_facts(rec, rec["name"], "Ben Thanh Market, HCMC",
                                review_snippets=_SPA_SNIPPETS)

    def test_prompt_block_contains_the_paragraph_and_the_rule(self):
        block = cv.customer_voice_prompt_block(self._facts())
        assert "WHAT PEOPLE SAY" in block
        assert "Visitors on Google give it 4.8" in block
        # The anti-invention rule must be present.
        assert "Do NOT invent" in block

    def test_prompt_block_empty_when_not_usable(self):
        assert cv.customer_voice_prompt_block({"usable": False}) == ""
        assert cv.customer_voice_prompt_block(None) == ""

    def test_facts_for_sources_roundtrip(self):
        src = cv.facts_for_sources(self._facts())
        assert "customer_voice" in src
        cvd = src["customer_voice"]
        assert cvd["rating"] == 4.8
        assert cvd["rating_count"] == 2300
        assert cvd["paragraph"].startswith("Visitors on Google give it 4.8")
        assert any("anspa" in s for s in cvd["sources"])


# ───────────────────────── generator wiring ────────────────────────────────
class TestGeneratorWiring:
    """Prove generate_tour_text.py wires the LOCAL-800 pass + prompt block without
    running a full generation (which needs the network / OpenAI)."""

    def _src(self):
        import inspect
        import generate_tour_text as gtt
        return inspect.getsource(gtt)

    def test_acquisition_pass_present(self):
        src = self._src()
        assert "[LOCAL-800] CUSTOMER VOICE" in src
        assert "import customer_voice as _cv800" in src
        assert "collect_facts(" in src

    def test_prompt_block_injected(self):
        src = self._src()
        assert "customer_voice_prompt_block(" in src
        assert "poi.get('_customer_voice')" in src

    def test_carry_helper_and_fields_present(self):
        src = self._src()
        assert "_carry_customer_voice_fields" in src
        assert "_serper_rating_count" in src

    def test_disable_env_flag_present(self):
        assert "LOCAL800_DISABLE_REVIEW_SEARCH" in self._src()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
