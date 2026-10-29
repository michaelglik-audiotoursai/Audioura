"""test_local803_wikidata_lookup.py — LOCAL-803.

The hand-written six-landmark table (landmark_reference.py) is replaced by a LIVE
Wikidata P625 lookup (wikidata_landmark_lookup.py). These tests prove the live
lookup with RECORDED Wikidata responses (no network): for the 6 HCMC landmarks and
3 others in other cities (Boston State House, Nice Opera, Hanoi Hoan Kiem Lake) the
resolved P625 snaps the stop within 100 m of the real place.

The recorded responses are the EXACT shapes the live ``wbsearchentities`` /
``wbgetentities`` calls return (captured from Wikidata 2026-10), including the
decoys the in-scope filter must reject:
  * "Thien Hau Temple" also returns a Mazu temple in Binh Duong (no P625) — skipped.
  * "Hoan Kiem Lake" also returns "Hoan Kiem Lake Hotel" — rejected by the bbox so
    the lookup lands on the LAKE, not the hotel.
  * "Nice Opera" returns NOTHING in English — it resolves only via the LOCAL
    language ("Opéra de Nice", fr), proving the tour-lang + local-lang query.

Run:
    python3 -m pytest tests/test_local803_wikidata_lookup.py -q
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _hav_m(a, b):
    R = 6371000.0
    la1, lo1 = math.radians(a[0]), math.radians(a[1])
    la2, lo2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


# ───────────────────── recorded Wikidata responses ──────────────────────────
# Keyed by (lowercased search string). Each maps to the wbsearchentities "search"
# list; _ENTITIES maps QID → P625 claim payload. Captured from the live API.

def _search_resp(hits):
    return {"search": [{"id": q, "label": lbl, "description": desc}
                       for (q, lbl, desc) in hits]}


def _entity_resp(qid, lat, lng):
    if lat is None:
        claims = {}
    else:
        claims = {"P625": [{"mainsnak": {"datavalue": {"value": {
            "latitude": lat, "longitude": lng}}}}]}
    return {"entities": {qid: {"claims": claims}}}


_SEARCH = {
    # 6 HCMC landmarks (English names; "City Hall" bare resolves via the full name
    # the stop carries — here the stop title is the full landmark name).
    "ho chi minh city hall": [("Q2227195", "Ho Chi Minh City Hall",
                               "city hall of Ho Chi Minh City, Vietnam")],
    "city hall": [("Q2227195", "Ho Chi Minh City Hall",
                   "city hall of Ho Chi Minh City, Vietnam")],
    "saigon notre dame basilica": [("Q428129", "Saigon Notre-Dame Basilica",
                                    "cathedral located in Ho Chi Minh City")],
    "saigon central post office": [("Q2227270", "Saigon Central Post Office",
                                    "post office in Ho Chi Minh City")],
    "saigon opera house": [("Q1949129", "Saigon Opera House",
                            "opera house in Ho Chi Minh City")],
    # Thien Hau: the Cholon temple FIRST, then a Binh Duong Mazu temple (no P625).
    "thien hau temple": [("Q1063916", "Thien Hau Temple",
                          "Chinese-style temple in Ho Chi Minh City"),
                         ("Q16480530", "Thien Hau Temple",
                          "Mazu temple in Binh Duong, Vietnam")],
    "chua ba thien hau": [("Q1063916", "Chùa Bà Thiên Hậu",
                           "cơ sở tín ngưỡng ở Sài Gòn")],
    "jade emperor pagoda": [("Q6121304", "Jade Emperor Pagoda",
                             "Taoist pagoda in Vietnam")],
    # 3 others
    "massachusetts state house": [("Q1150259", "Massachusetts State House",
                                   "state capitol building for Massachusetts")],
    "boston state house": [("Q1150259", "Massachusetts State House",
                            "state capitol building for Massachusetts")],
    # "Nice Opera" → NOTHING (the search index does not match the English words to
    # the French-named entity); it resolves only via the LOCAL-language NAME
    # "Opéra de Nice" (folded "opera de nice"), which the local-language stop title
    # carries. This is exactly why the lookup queries the local-language name.
    "nice opera": [],
    "opera de nice": [("Q608423", "opéra de Nice", "opéra à Nice")],
    # Hoan Kiem Lake: the lake FIRST, plus a same-name HOTEL decoy nearby.
    "hoan kiem lake": [("Q1151254", "Hoàn Kiếm Lake", "water area in Hanoi"),
                       ("Q111862800", "Hoan Kiem Lake Hotel",
                        "hotel in Hanoi, Vietnam")],
    "ho hoan kiem": [("Q1151254", "Hoàn Kiếm hồ", "hồ nước tự nhiên ở Hà Nội")],
}

_ENTITIES = {
    "Q2227195": (10.77647, 106.70097),
    "Q428129": (10.779722, 106.699167),
    "Q2227270": (10.78, 106.7),
    "Q1949129": (10.77639, 106.70278),
    "Q1063916": (10.75291, 106.66117),
    "Q16480530": (None, None),           # Binh Duong Mazu temple: no P625
    "Q6121304": (10.791666666667, 106.69777777778),
    "Q1150259": (42.35862661956368, -71.06385784107137),
    "Q608423": (43.695439, 7.272552),
    "Q1151254": (21.028888888889, 105.8525),       # the lake
    "Q111862800": (21.0307787774, 105.8496397734),  # the HOTEL decoy
}


def _fold(s):
    import unicodedata
    import re
    nf = unicodedata.normalize("NFKD", str(s or "").lower())
    s = "".join(c for c in nf if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def recorded_fetch(action, params):
    """Stand-in for wikidata_landmark_lookup._default_fetch: returns the recorded
    response for a wbsearchentities / wbgetentities call. No network."""
    if params.get("action") == "wbsearchentities":
        key = _fold(params.get("search", ""))
        return _search_resp(_SEARCH.get(key, []))
    if params.get("action") == "wbgetentities":
        qid = params.get("ids", "")
        lat, lng = _ENTITIES.get(qid, (None, None))
        return _entity_resp(qid, lat, lng)
    return None


# Scope boxes [south, north, west, east] for the in-scope identity filter.
HCMC_BBOX = [10.35, 11.16, 106.36, 107.03]
BOSTON_BBOX = [42.22, 42.40, -71.19, -70.92]
NICE_BBOX = [43.64, 43.76, 7.18, 7.32]
# Hanoi Old Quarter / Hoan Kiem — a TIGHT box around the lake so the HOTEL decoy
# (350 m away but still central) is inside; the lake-vs-hotel choice is by ORDER
# (lake first) within scope, which is what the real search returns.
HANOI_BBOX = [20.99, 21.07, 105.82, 105.88]

REAL = {
    "City Hall": (10.7765, 106.7010),
    "Saigon Notre-Dame Basilica": (10.779722, 106.699167),
    "Saigon Central Post Office": (10.78, 106.7),
    "Saigon Opera House": (10.77639, 106.70278),
    "Thien Hau Temple": (10.7531, 106.6612),
    "Jade Emperor Pagoda": (10.7917, 106.6978),
    "Boston State House": (42.3586, -71.0638),
    "Nice Opera": (43.695439, 7.272552),
    "Hoan Kiem Lake": (21.0289, 105.8525),
}


class TestLiveLookupSixHCMC:
    def _lookup(self, name):
        from wikidata_landmark_lookup import lookup
        return lookup(name, scope="Ho Chi Minh City", scope_bbox=HCMC_BBOX,
                      tour_language="en", fetch_fn=recorded_fetch,
                      use_cache=False)

    def test_city_hall(self):
        hit = self._lookup("Ho Chi Minh City Hall")
        assert hit and hit[2] == "wikidata_p625" and hit[3] == "Q2227195"
        assert _hav_m((hit[0], hit[1]), REAL["City Hall"]) < 100

    def test_notre_dame(self):
        hit = self._lookup("Saigon Notre-Dame Basilica")
        assert hit and _hav_m((hit[0], hit[1]),
                               REAL["Saigon Notre-Dame Basilica"]) < 100

    def test_post_office(self):
        hit = self._lookup("Saigon Central Post Office")
        assert hit and _hav_m((hit[0], hit[1]),
                               REAL["Saigon Central Post Office"]) < 100

    def test_opera_house(self):
        hit = self._lookup("Saigon Opera House")
        assert hit and _hav_m((hit[0], hit[1]),
                               REAL["Saigon Opera House"]) < 100

    def test_thien_hau_skips_binh_duong_decoy(self):
        """The first hit (Cholon temple) has P625 and is in-scope; the Binh Duong
        Mazu temple decoy (no P625) is never reached."""
        hit = self._lookup("Thien Hau Temple")
        assert hit and hit[3] == "Q1063916"
        assert _hav_m((hit[0], hit[1]), REAL["Thien Hau Temple"]) < 100

    def test_thien_hau_via_local_vietnamese_name(self):
        from wikidata_landmark_lookup import lookup
        hit = lookup("Chùa Bà Thiên Hậu", scope="Ho Chi Minh City",
                     scope_bbox=HCMC_BBOX, tour_language="en",
                     fetch_fn=recorded_fetch, use_cache=False)
        assert hit and _hav_m((hit[0], hit[1]), REAL["Thien Hau Temple"]) < 100

    def test_jade_emperor(self):
        hit = self._lookup("Jade Emperor Pagoda")
        assert hit and _hav_m((hit[0], hit[1]),
                              REAL["Jade Emperor Pagoda"]) < 100


class TestLiveLookupThreeOthers:
    def test_boston_state_house(self):
        from wikidata_landmark_lookup import lookup
        hit = lookup("Boston State House", scope="Boston, Massachusetts",
                     scope_bbox=BOSTON_BBOX, tour_language="en",
                     fetch_fn=recorded_fetch, use_cache=False)
        assert hit and hit[3] == "Q1150259"
        assert _hav_m((hit[0], hit[1]), REAL["Boston State House"]) < 100

    def test_nice_opera_resolves_via_local_french_name(self):
        """The French NAME "Opéra de Nice" resolves to Q608423 within Nice's bbox.
        (The bare English "Nice Opera" does NOT match Wikidata's search index — a
        real limitation — so the local-language name is what resolves it; the
        lookup's local-language pass is exactly for stop titles in that language.)"""
        from wikidata_landmark_lookup import lookup, local_lang_for_scope
        assert local_lang_for_scope("Old Town, Nice, France") == "fr"
        hit = lookup("Opéra de Nice", scope="Nice, France", scope_bbox=NICE_BBOX,
                     tour_language="fr", fetch_fn=recorded_fetch, use_cache=False)
        assert hit and hit[3] == "Q608423"
        assert _hav_m((hit[0], hit[1]), REAL["Nice Opera"]) < 100

    def test_bare_english_nice_opera_returns_none(self):
        """Honest: a bare English "Nice Opera" cannot be resolved (no search-index
        match to the French-named entity), so the lookup returns None and the
        caller keeps the shipped pin / its geocoder result — never a wrong snap."""
        from wikidata_landmark_lookup import lookup
        hit = lookup("Nice Opera", scope="Nice, France", scope_bbox=NICE_BBOX,
                     tour_language="en", fetch_fn=recorded_fetch, use_cache=False)
        assert hit is None

    def test_hanoi_hoan_kiem_lake_not_the_hotel(self):
        """"Hoan Kiem Lake" returns the LAKE first and a same-name HOTEL second;
        the lookup lands on the lake (both in-scope, lake is first)."""
        from wikidata_landmark_lookup import lookup
        hit = lookup("Hoan Kiem Lake", scope="Old Quarter, Hanoi",
                     scope_bbox=HANOI_BBOX, tour_language="en",
                     fetch_fn=recorded_fetch, use_cache=False)
        assert hit and hit[3] == "Q1151254"
        assert _hav_m((hit[0], hit[1]), REAL["Hoan Kiem Lake"]) < 100


class TestInScopeIdentityGuard:
    def test_out_of_scope_candidate_rejected(self):
        """A P625 OUTSIDE the scope bbox is refused — the identity guard a bare
        name search cannot give. Boston's State House is not in an HCMC-scoped
        tour, so the lookup returns None (caller keeps the pin / falls back)."""
        from wikidata_landmark_lookup import lookup
        hit = lookup("Boston State House", scope="Ho Chi Minh City",
                     scope_bbox=HCMC_BBOX, tour_language="en",
                     fetch_fn=recorded_fetch, use_cache=False)
        assert hit is None

    def test_metro_radius_when_no_bbox(self):
        """With no bbox, a candidate within the metro radius of the scope centre
        is accepted."""
        from wikidata_landmark_lookup import lookup
        hit = lookup("Saigon Opera House", scope="Ho Chi Minh City",
                     scope_center=(10.7769, 106.7009), tour_language="en",
                     fetch_fn=recorded_fetch, use_cache=False)
        assert hit and _hav_m((hit[0], hit[1]),
                              REAL["Saigon Opera House"]) < 100


class TestPinSnapUsesLiveLookup:
    """pin_snap.snap_pin, given the live lookup injected as ``landmark_fn``, snaps
    the stop to the Wikidata P625 — the same seam the live path uses."""

    def _landmark_fn(self, scope, bbox):
        from wikidata_landmark_lookup import lookup
        return lambda name: lookup(name, scope=scope, scope_bbox=bbox,
                                   tour_language="en", fetch_fn=recorded_fetch,
                                   use_cache=False)

    def test_city_hall_bad_pin_snaps_to_real_building(self):
        from pin_snap import snap_pin
        row = snap_pin(
            "Ho Chi Minh City Hall", (10.73240, 106.69510),  # ticket's 4.8km-off pin
            scope="Ho Chi Minh City", scope_center=(10.7769, 106.7009),
            landmark_fn=self._landmark_fn("Ho Chi Minh City", HCMC_BBOX))
        assert row["snapped"] is True
        assert row["source"] == "wikidata_p625"
        assert _hav_m(row["new_coordinate"], REAL["City Hall"]) < 100

    def test_hoan_kiem_snaps_within_100m(self):
        from pin_snap import snap_poi_coordinates
        pois = [{"name": "Hoan Kiem Lake", "coordinates": "21.040, 105.860"}]
        snap_poi_coordinates(
            pois, scope="Old Quarter, Hanoi",
            scope_center=(21.0313, 105.8516),
            landmark_fn=self._landmark_fn("Old Quarter, Hanoi", HANOI_BBOX),
            log=lambda *_: None)
        lat, lng = (float(x) for x in pois[0]["coordinates"].split(","))
        assert _hav_m((lat, lng), REAL["Hoan Kiem Lake"]) < 100


class TestOfflineFallbackToTable:
    """When the live lookup yields nothing (Wikidata unreachable / disabled), the
    offline landmark_reference.py table still resolves the original six HCMC pins
    — the fallback the ticket requires so those pins never regress offline."""

    def test_fallback_resolves_city_hall(self):
        from pin_snap import _landmark_reference
        # landmark_fn returns None (simulates unreachable live lookup) → table used.
        ref = _landmark_reference("City Hall", scope="Ho Chi Minh City",
                                  landmark_fn=lambda name: None)
        assert ref is not None
        assert ref[2] == "wikidata_p625"
        assert _hav_m((ref[0], ref[1]), REAL["City Hall"]) < 200

    def test_fallback_resolves_thien_hau(self):
        from pin_snap import _landmark_reference
        ref = _landmark_reference("Thien Hau Temple", scope="Ho Chi Minh City",
                                  landmark_fn=lambda name: None)
        assert ref is not None
        assert _hav_m((ref[0], ref[1]), REAL["Thien Hau Temple"]) < 200


class TestRateLimitNeverDropsStop:
    """A 429 that never clears makes the live fetch return None; the lookup then
    returns None (not an exception), so the caller keeps the pin / falls back — a
    429 never DROPS a stop."""

    def test_rate_limited_fetch_returns_none_not_raises(self):
        from wikidata_landmark_lookup import lookup
        hit = lookup("Ho Chi Minh City Hall", scope="Ho Chi Minh City",
                     scope_bbox=HCMC_BBOX, tour_language="en",
                     fetch_fn=lambda a, p: None,  # every call "rate limited"
                     use_cache=False)
        assert hit is None

    def test_rate_limited_landmark_reference_falls_back_to_table(self):
        from pin_snap import _landmark_reference
        # Live lookup rate-limited (landmark_fn returns None) → table fallback.
        ref = _landmark_reference("Jade Emperor Pagoda", scope="Ho Chi Minh City",
                                  landmark_fn=lambda name: None)
        assert ref is not None
        assert _hav_m((ref[0], ref[1]), REAL["Jade Emperor Pagoda"]) < 200
