"""LOCAL-867 — pasted-itinerary parser + /preview-stops resolver. Fully offline."""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import itinerary_import as ii  # noqa: E402

MICHAEL = ("Cathedral → Post Office → Book Street → Independence Palace → "
           "War Remnants Museum → Opera House/Đồng Khởi → City Hall & Nguyễn Huệ → "
           "Café Apartments 42 → Bạch Đằng Pier (tour-bus + waterbus) → Thi Bar")


def names(items):
    return [i["name"] for i in items]


# ── parser ──────────────────────────────────────────────────────────────────

def test_exact_string_ten_stops_in_order():
    got = ii.parse_itinerary(MICHAEL, "Ho Chi Minh City")
    assert names(got) == [
        "Cathedral", "Post Office", "Book Street", "Independence Palace",
        "War Remnants Museum", "Opera House", "City Hall", "Café Apartments 42",
        "Bạch Đằng Pier", "Thi Bar"]


def test_exact_string_combined_stops_and_note():
    got = ii.parse_itinerary(MICHAEL)
    assert got[5]["alt_names"] == ["Đồng Khởi"]          # A/B
    assert got[6]["alt_names"] == ["Nguyễn Huệ"]         # A & B
    assert got[7]["name"] == "Café Apartments 42"        # number is part of the name
    assert got[7]["alt_names"] == []
    assert got[8]["name"] == "Bạch Đằng Pier"
    assert got[8]["note"] == "tour-bus + waterbus"       # parenthetical -> note
    assert "(" not in got[8]["name"]
    assert all(set(i) == {"name", "alt_names", "note", "url"} for i in got)


def test_numbered_list():
    text = "1. Cathedral\n2) Post Office\n3 - Book Street\n(4) Opera House"
    # "3 - Book Street" has no bullet punctuation after the digit: it is kept
    # verbatim rather than guessed at.
    got = names(ii.parse_itinerary(text))
    assert got[:2] == ["Cathedral", "Post Office"]
    assert got[3] == "Opera House"
    assert len(got) == 4


def test_numbered_and_bulleted_and_stop_prefix_and_emoji():
    text = ("Itinerary:\n- 🏛 Cathedral\n• Stop 2: Post Office\n"
            "3. 🌈Thi Bar Saigon\n1️⃣ Opera House")
    assert names(ii.parse_itinerary(text)) == [
        "Cathedral", "Post Office", "Thi Bar Saigon", "Opera House"]


def test_inline_numbering_one_line():
    assert names(ii.parse_itinerary("1) Cathedral 2) Post Office 3) Opera House")) \
        == ["Cathedral", "Post Office", "Opera House"]


def test_comma_semicolon_pipe_and_arrow_variants():
    assert names(ii.parse_itinerary("Cathedral, Post Office; Book Street | Opera")) \
        == ["Cathedral", "Post Office", "Book Street", "Opera"]
    assert names(ii.parse_itinerary("A -> B => C > D ⇒ E → F")) \
        == list("ABCDEF")


def test_comma_inside_parentheses_does_not_split():
    got = ii.parse_itinerary("Pier (bus, boat) → Bar")
    assert names(got) == ["Pier", "Bar"]
    assert got[0]["note"] == "bus, boat"


def test_numbers_stay_in_names():
    got = ii.parse_itinerary("Café Apartments 42, 24/7 Diner, Pho 2000")
    assert names(got) == ["Café Apartments 42", "24/7 Diner", "Pho 2000"]


def test_mixed_list_with_links():
    text = ("Rambutan https___share.google_1v4x\n"
            "The Crazy street https://maps.app.goo.gl/abc123, "
            "An Spa + https://an-spa.vn/en\n"
            "→ Thi Bar Saigon (https://www.google.com/maps/place/X/@10.7676,106.6939,17z)\n"
            "Cathedral")
    got = ii.parse_itinerary(text)
    assert names(got) == ["Rambutan", "The Crazy street", "An Spa",
                          "Thi Bar Saigon", "Cathedral"]
    assert got[0]["url"] == "https://share.google/1v4x"
    assert got[1]["url"] == "https://maps.app.goo.gl/abc123"
    assert got[2]["url"] == "https://an-spa.vn/en"
    # the @lat,lng commas inside the URL did not split it
    assert got[3]["url"].endswith("@10.7676,106.6939,17z")
    assert got[3]["note"] == ""
    assert got[4]["url"] is None


def test_bare_latlng_not_split():
    got = ii.parse_itinerary("10.776600, 106.700900 → Cathedral")
    assert len(got) == 2 and got[1]["name"] == "Cathedral"


def test_header_and_city_only_items_dropped():
    got = ii.parse_itinerary("Route:\nHo Chi Minh City\nCathedral → Post Office",
                             "Ho Chi Minh City")
    assert names(got) == ["Cathedral", "Post Office"]


def test_garbage_returns_empty():
    assert ii.parse_itinerary("") == []
    assert ii.parse_itinerary("  →  ,  ; ") == []
    assert ii.parse_itinerary(None) == []


def test_three_way_combined():
    got = ii.parse_itinerary("Opera House / Đồng Khởi / Lam Sơn Square")
    assert got == [{"name": "Opera House",
                    "alt_names": ["Đồng Khởi", "Lam Sơn Square"],
                    "note": "", "url": None}]


# ── resolver (offline, injected) ────────────────────────────────────────────

HCMC = (10.7769, 106.7009)


class Fake:
    """Records every call so cost / ordering can be asserted."""

    def __init__(self, wikidata=None, nominatim=None, serper=None, link=None):
        self.calls = {"wd": [], "nom": [], "serper": [], "link": []}
        self._wd, self._nom, self._sp, self._ln = wikidata, nominatim, serper, link

    def resolvers(self):
        def wd(name, scope, center, bbox):
            self.calls["wd"].append(name)
            return self._wd(name) if self._wd else None

        def nom(params):
            self.calls["nom"].append(params.get("q"))
            if "featuretype" in params:  # city lookup
                return []
            return self._nom(params["q"]) if self._nom else []

        def sp(q, ll, loc):
            self.calls["serper"].append(q)
            return self._sp(q) if self._sp else []

        def ln(raw):
            self.calls["link"].append(raw)
            return self._ln(raw) if self._ln else {}
        return ii.Resolvers(wikidata=wd, nominatim=nom, serper=sp, link=ln,
                            city_fetch=nom)


def test_city_required_never_guessed():
    out = ii.preview_stops("Cathedral → Post Office", "", resolvers=Fake().resolvers(),
                           log=lambda *_: None)
    assert out["ok"] is False and "city" in out["error"]


def test_city_from_text_when_not_passed():
    f = Fake()
    out = ii.preview_stops("Ho Chi Minh City walk: Cathedral → Post Office", "",
                           resolvers=f.resolvers(), log=lambda *_: None)
    assert out["ok"] and out["city"]["name"] == "Ho Chi Minh City"


def test_landmark_table_resolves_post_office_and_cathedral_offline():
    f = Fake()
    out = ii.preview_stops("Cathedral → Post Office → Opera House/Đồng Khởi",
                           "Ho Chi Minh City", resolvers=f.resolvers(),
                           log=lambda *_: None)
    s = out["stops"]
    assert [x["name"] for x in s] == ["Cathedral", "Post Office", "Opera House"]
    assert s[0]["resolved_name"] == "Notre-Dame Cathedral Basilica of Saigon"
    assert s[0]["source"] == "landmark_table" and s[0]["confidence"] == "high"
    assert s[1]["resolved_name"] == "Saigon Central Post Office"
    assert abs(s[1]["lat"] - 10.78) < 0.001
    assert all(x["unresolved"] is False for x in s)
    assert f.calls["serper"] == [] and f.calls["wd"] == []     # free + offline
    assert out["cost"]["usd"] == 0 and out["cost"]["llm_calls"] == 0


def test_chain_order_wikidata_then_nominatim_then_one_serper():
    f = Fake(
        wikidata=lambda n: (10.7770, 106.6954, "Q1") if "Independence" in n else None,
        nominatim=lambda q: ([{"lat": "10.7799", "lon": "106.6997",
                               "display_name": "Nguyễn Văn Bình, Quận 1"}]
                             if "Nguyễn Văn Bình" in q else []),
        serper=lambda q: [{"name": "Thi Bar Saigon", "lat": 10.76766,
                           "lon": 106.69396}])
    out = ii.preview_stops("Independence Palace → Book Street → Thi Bar",
                           "Ho Chi Minh City", resolvers=f.resolvers(),
                           log=lambda *_: None)
    a, b, c = out["stops"]
    assert (a["source"], a["confidence"]) == ("wikidata_p625", "high")
    assert (b["source"], b["confidence"]) == ("nominatim", "medium")
    assert b["resolved_name"].startswith("Nguyễn Văn Bình")
    assert (c["source"], c["confidence"]) == ("serper_places", "medium")
    assert f.calls["serper"] == ["Thi Bar Saigon"]              # only the third
    assert out["cost"]["serper_places_calls"] == 1
    assert out["cost"]["usd"] == pytest.approx(0.002)


def test_at_most_one_serper_per_item_and_cap():
    f = Fake(serper=lambda q: [])
    text = " → ".join(f"Nowhere Place {i}" for i in range(6))
    out = ii.preview_stops(text, "Ho Chi Minh City", resolvers=f.resolvers(),
                           max_serper_calls=4, log=lambda *_: None)
    assert len(f.calls["serper"]) == 4                         # cap honoured
    assert out["unresolved_count"] == 6
    assert all(x["lat"] is None and x["unresolved"] for x in out["stops"])
    assert all(x["reason"] for x in out["stops"])


def test_unresolved_is_never_a_centroid():
    f = Fake()
    out = ii.preview_stops("Zzyzx Qwerty", "Ho Chi Minh City", resolvers=f.resolvers(),
                           log=lambda *_: None)
    x = out["stops"][0]
    assert x["unresolved"] and x["lat"] is None and x["lng"] is None


def test_hit_outside_the_city_is_rejected():
    far = [{"name": "Thi Bar", "lat": 21.03, "lon": 105.85}]      # Hanoi
    f = Fake(serper=lambda q: far, nominatim=lambda q: far,
             wikidata=lambda n: (21.03, 105.85, "Q9"))
    out = ii.preview_stops("Thi Bar", "Ho Chi Minh City", resolvers=f.resolvers(),
                           log=lambda *_: None)
    assert out["stops"][0]["unresolved"]


def test_name_mismatch_hit_is_rejected():
    f = Fake(serper=lambda q: [{"name": "Totally Different Cafe",
                                "lat": 10.777, "lon": 106.70}])
    out = ii.preview_stops("Thi Bar", "Ho Chi Minh City", resolvers=f.resolvers(),
                           log=lambda *_: None)
    assert out["stops"][0]["unresolved"]


def test_generic_word_without_alias_does_not_trust_first_wikidata_hit():
    f = Fake(wikidata=lambda n: (10.78, 106.70, "Q5"))
    out = ii.preview_stops("Museum", "Ho Chi Minh City", resolvers=f.resolvers(),
                           log=lambda *_: None)
    assert out["stops"][0]["source"] != "wikidata_p625"


def test_link_item_uses_link_pin_for_free():
    f = Fake(link=lambda raw: {"lat": 10.76766, "lng": 106.69396,
                               "resolved_name": "Thi Bar Saigon"})
    out = ii.preview_stops("Thi Bar https://www.google.com/maps/@10.76766,106.69396,17z",
                           "Ho Chi Minh City", resolvers=f.resolvers(),
                           log=lambda *_: None)
    x = out["stops"][0]
    assert (x["source"], x["confidence"]) == ("user_link", "high")
    assert f.calls["serper"] == [] and f.calls["nom"] == []


def test_order_and_count_preserved_with_unresolved_in_middle():
    f = Fake()
    out = ii.preview_stops("Cathedral → Zzyzx → Post Office", "Ho Chi Minh City",
                           resolvers=f.resolvers(), max_serper_calls=0,
                           log=lambda *_: None)
    assert [x["name"] for x in out["stops"]] == ["Cathedral", "Zzyzx", "Post Office"]
    assert [x["index"] for x in out["stops"]] == [0, 1, 2]
    assert [x["unresolved"] for x in out["stops"]] == [False, True, False]


# ── preview -> generation ───────────────────────────────────────────────────

def test_generation_string_carries_pin_and_survives_orchestrator_sanitising():
    import user_stop_input as usi
    s = ii.stop_to_generation_string(
        {"stop_name": "Thi Bar Saigon", "name": "Thi Bar", "lat": 10.76766,
         "lng": 106.69396})
    # the orchestrator's sanitize_input rewrites : and / to _
    mangled = re.sub(r'[<>:"/\\|?*]', '_', s)
    p = usi.parse_user_stop(mangled)
    assert p["name"] == "Thi Bar Saigon"
    assert (p["lat"], p["lng"]) == (10.76766, 106.69396)
    assert p["needs_geocode"] is False


def test_generation_string_unresolved_is_just_the_name():
    assert ii.stop_to_generation_string(
        {"name": "Zzyzx", "lat": None, "lng": None, "unresolved": True}) == "Zzyzx"
    assert ii.stop_to_generation_string("Cathedral") == "Cathedral"


def test_stops_for_generation_keeps_order_and_counts_pins():
    items = [{"name": "A", "lat": 10.77, "lng": 106.7}, "B",
             {"name": "C", "lat": None, "lng": None}]
    strings, pins = ii.stops_for_generation(items)
    assert [s.split(" ")[0] for s in strings] == ["A", "B", "C"]
    assert pins == 1


def test_bad_stop_object_raises():
    with pytest.raises(ValueError):
        ii.stop_to_generation_string({"lat": 1, "lng": 2})
    with pytest.raises(ValueError):
        ii.stop_to_generation_string(7)


# ── regressions found in the first live preview ─────────────────────────────

def test_name_ok_class_words_do_not_identify_a_place():
    assert not ii.name_ok("Book Street", "Phương Nam Book City")
    assert not ii.name_ok("Bạch Đằng Pier", "Đường Tôn Đức Thắng")
    assert ii.name_ok("Thi Bar", "Quán Thi Bar")
    assert ii.name_ok("Café Apartments 42", "The Cafe Apartment")
    assert ii.name_ok("Opera House", "Saigon Opera House")
    assert ii.name_ok("Đường sách Nguyễn Văn Bình", "Đường Sách")
    assert not ii.name_ok("Thi Bar", "Totally Different Bar")


def test_book_street_is_not_pinned_on_a_bookshop():
    shop = {"lat": "10.7669", "lon": "106.6882", "category": "shop",
            "display_name": "Phương Nam Book City, Quận 1"}
    f = Fake(nominatim=lambda q: [shop])
    out = ii.preview_stops("Book Street", "Ho Chi Minh City", resolvers=f.resolvers(),
                           max_serper_calls=0, log=lambda *_: None)
    assert out["stops"][0]["unresolved"]               # not the bookshop


def test_book_street_resolves_to_nguyen_van_binh_via_alias_query():
    book = {"lat": "10.78057", "lon": "106.69969", "category": "tourism",
            "display_name": "Đường Sách, Đường Nguyễn Văn Bình, Quận 1"}
    f = Fake(nominatim=lambda q: [book] if q == "Đường sách Nguyễn Văn Bình" else [])
    out = ii.preview_stops("Book Street", "Ho Chi Minh City", resolvers=f.resolvers(),
                           log=lambda *_: None)
    x = out["stops"][0]
    assert x["unresolved"] is False and x["source"] == "nominatim"
    assert "Nguyễn Văn Bình" in x["resolved_name"]
    assert (x["lat"], x["lng"]) == (10.78057, 106.69969)


def test_pier_is_not_pinned_on_the_road_that_carries_its_old_name():
    road = {"lat": "10.7797", "lon": "106.7078", "category": "highway",
            "display_name": "Đường Tôn Đức Thắng", "name": "Bến Bạch Đằng"}
    marina = {"lat": "10.77524", "lon": "106.70700", "category": "leisure",
              "display_name": "Bến tàu Bạch Đằng, Đường Tôn Đức Thắng"}
    f = Fake(nominatim=lambda q: [road, marina])
    out = ii.preview_stops("Bạch Đằng Pier (tour-bus + waterbus)", "Ho Chi Minh City",
                           resolvers=f.resolvers(), log=lambda *_: None)
    x = out["stops"][0]
    assert (x["lat"], x["lng"]) == (10.77524, 106.707)
    assert x["note"] == "tour-bus + waterbus"


def test_matched_name_rides_in_place_segment_and_survives_sanitising():
    import user_stop_input as usi
    s = ii.stop_to_generation_string(
        {"stop_name": "Bạch Đằng Pier", "matched_name": "Bến tàu Bạch Đằng",
         "lat": 10.77524, "lng": 106.707002})
    p = usi.parse_user_stop(re.sub(r'[<>:"/\\|?*]', '_', s))
    assert p["name"] == "Bạch Đằng Pier"
    assert p["resolved_name"] == "Bến tàu Bạch Đằng"
    assert (p["lat"], p["lng"]) == (10.77524, 106.707002)


def test_matched_name_equal_to_title_is_not_repeated():
    s = ii.stop_to_generation_string({"stop_name": "Thi Bar Saigon",
                                      "matched_name": "Thi Bar Saigon",
                                      "lat": 10.76766, "lng": 106.69396})
    assert "/maps/@10.767660,106.693960" in s and "/place/" not in s


def test_preview_carries_matched_name():
    marina = {"lat": "10.77524", "lon": "106.70700", "category": "leisure",
              "name": "Bến tàu Bạch Đằng", "display_name": "Bến tàu Bạch Đằng, Q1"}
    f = Fake(nominatim=lambda q: [marina])
    x = ii.preview_stops("Bạch Đằng Pier", "Ho Chi Minh City", resolvers=f.resolvers(),
                         log=lambda *_: None)["stops"][0]
    assert x["matched_name"] == "Bến tàu Bạch Đằng"
    assert x["stop_name"] == "Bạch Đằng Pier"
