#!/usr/bin/env python3
"""test_local852_user_stops_safe.py — LOCAL-852.

The listener (Michael, gen 00027-6sb, tour 523) asked for "Sophia's biking tour
in Ho Chi Minh City, Vietnam" and PASTED seven stops as a display name + a Google
share link. Two were delivered of seven. This file proves, OFFLINE and
deterministically, the three fixes from the ticket:

  1. PROVIDER GUARD MISFIRE. "Sophia's biking tour" (a person's tour, by a
     transport mode) must NOT be read as an activity-provider request — so no
     guard drops the listener's own stops. "Kitesurf lessons in Mui Ne" is a real
     provider request and is STILL guarded (control, LOCAL-835/843).

  2. USER-STOP INPUT PARSING. Each "Name + URL" item parses to a CLEAN display
     name (URL removed, incl. the "https___" underscore-mangled form); a Google
     share link resolves (injected fetcher, no network) to a place + @lat,lng; a
     plain website URL keeps the name and geocodes by name.

  3. CENTROID-COLLAPSE DEDUPE. Two user stops that fell to the SAME fallback /
     centroid coordinate are NOT the same place — they must not be collapsed. A
     textually identical pair still collapses; a genuine non-user nearby pair
     still collapses.

Run:
    python3 -m pytest tests/test_local852_user_stops_safe.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# The EXACT seven stop strings from the evidence log (share-link suffixes are the
# realistic share.google / an-spa.vn forms the listener pasted).
SEVEN_RAW = [
    "Rambutan https___share.google_1v4x",
    "Longan https___share.google_z20B",
    "The Crazy street",
    "The LGBT bar 🌈Thi Bar Saigon",
    "A Star is Born",
    "Acoustic Bar - Ngô Thời Nhiệm, Quận 3",
    "An Spa at https___an-spa.vn_en",
]

# An offline stub resolver: a share link -> a canonical Maps place URL with a
# distinct HCMC coordinate. No network.
_STUB_RESOLVE = {
    "https://share.google/1v4x":
        "https://www.google.com/maps/place/Rambutan+Saigon/@10.7725,106.6985,17z",
    "https://share.google/z20B":
        "https://www.google.com/maps/place/Longan+Bar/@10.7801,106.6922,17z",
}


def _stub(url):
    return _STUB_RESOLVE.get(url)


# ───────────────────── 1. provider-guard misfire ─────────────────────────────
class TestProviderGuardMisfire:
    def test_persons_biking_tour_is_not_a_provider_request(self):
        from category_match_guard import requested_activity
        assert requested_activity(
            "Sophia's biking tour Ho Chi Minh City, Vietnam") is None

    def test_persons_tour_via_tour_type_param_is_suppressed(self):
        from category_match_guard import requested_activity
        # The request string the guard sees is just the city; the tell-tale words
        # arrive as tour_type.
        assert requested_activity("Ho Chi Minh City, Vietnam",
                                  tour_type="Sophia's biking tour") is None

    def test_transport_mode_tours_are_not_provider_requests(self):
        from category_match_guard import requested_activity
        for req in ("walking tour of District 1, Ho Chi Minh City",
                    "biking tour of Ho Chi Minh City",
                    "boat tour in Ha Long Bay",
                    "driving tour of the coast",
                    "cycling tour, Hoi An"):
            assert requested_activity(req) is None, req

    def test_real_provider_requests_still_detected(self):
        # CONTROL: the ticket's "still guarded" case and its family must survive.
        from category_match_guard import requested_activity
        for req in ("Kitesurf lessons in Mui Ne, Vietnam",
                    "Kiteboarding lessons in Mui Ne, Vietnam",
                    "Scuba diving courses in Nha Trang",
                    "bike rental in Hoi An",
                    "kayak hire in Nha Trang",
                    "surf school in Da Nang"):
            assert requested_activity(req) is not None, req

    def test_kitesurf_lessons_still_drops_off_category(self):
        # The guard still removes a restaurant / fishing village for a real
        # provider request (LOCAL-835/843 behaviour unchanged).
        from category_match_guard import filter_off_category_activity
        cands = [
            {"name": "Source Kiteboarding"},
            {"name": "Deja Vu Restaurant", "_serper_category": "Restaurant"},
            {"name": "Mui Ne Fishing Village"},
        ]
        kept, dropped = filter_off_category_activity(
            cands, "Kitesurf lessons in Mui Ne, Vietnam", log=lambda *_a: None)
        names = {c["name"] for c in kept}
        assert "Source Kiteboarding" in names
        assert "Deja Vu Restaurant" not in names
        assert "Mui Ne Fishing Village" not in names
        assert dropped == 2


# ───────────────────── 2. user-stop input parsing ────────────────────────────
class TestUserStopParsing:
    def test_all_seven_names_are_clean(self):
        import user_stop_input as u
        parsed = u.parse_user_stops(SEVEN_RAW, resolve=_stub, log=lambda *_a: None)
        assert len(parsed) == 7
        for p in parsed:
            assert p["name"]
            assert "http" not in p["name"].lower()
            assert "___" not in p["name"]

    def test_share_links_resolve_to_distinct_coords(self):
        import user_stop_input as u
        parsed = u.parse_user_stops(SEVEN_RAW, resolve=_stub, log=lambda *_a: None)
        ram, lon = parsed[0], parsed[1]
        assert ram["name"] == "Rambutan" and ram["lat"] is not None
        assert lon["name"] == "Longan" and lon["lng"] is not None
        assert (ram["lat"], ram["lng"]) != (lon["lat"], lon["lng"])
        assert ram["how"] == "share_redirect" and lon["how"] == "share_redirect"
        assert ram["needs_geocode"] is False and lon["needs_geocode"] is False

    def test_website_url_keeps_name_and_geocodes_by_name(self):
        import user_stop_input as u
        p = u.parse_user_stop("An Spa at https___an-spa.vn_en",
                              resolve=_stub, log=lambda *_a: None)
        assert p["name"] == "An Spa"
        assert p["how"] == "website"
        assert p["needs_geocode"] is True
        assert p["lat"] is None

    def test_name_only_stops_unchanged(self):
        import user_stop_input as u
        for raw in ("The Crazy street", "A Star is Born",
                    "The LGBT bar 🌈Thi Bar Saigon",
                    "Acoustic Bar - Ngô Thời Nhiệm, Quận 3"):
            p = u.parse_user_stop(raw, resolve=_stub, log=lambda *_a: None)
            assert p["how"] == "name_only"
            assert p["needs_geocode"] is True
            assert p["name"]  # keeps emoji / accents / commas

    def test_unmangle_url_forms(self):
        import user_stop_input as u
        assert u.unmangle_url("https___share.google_1v4x") == "https://share.google/1v4x"
        assert u.unmangle_url("https___an-spa.vn_en") == "https://an-spa.vn/en"
        assert u.unmangle_url("https://already.valid/x") == "https://already.valid/x"

    def test_mandated_log_line_emitted(self):
        import user_stop_input as u
        logs = []
        u.parse_user_stop("Rambutan https___share.google_1v4x",
                          resolve=_stub, log=logs.append)
        assert any(l.startswith("[LOCAL-852] user stop resolved") for l in logs)
        assert any("via share_redirect" in l for l in logs)


# ───────────────────── 3. centroid-collapse dedupe ───────────────────────────
class TestCentroidCollapseDedupe:
    # The four name-only stops geocoded to the SAME fallback centroid ≈ the field
    # value 10.7769,106.6955 (CENTROID COLLAPSE).
    _CENTROID = "10.7769, 106.6955"

    def _user_stops_on_centroid(self):
        return [
            {"name": n, "coordinates": self._CENTROID,
             "user_explicit": True, "_anchor": True,
             "coord_source": "fallback"}
            for n in ("Rambutan", "The Crazy street",
                      "A Star is Born", "Longan")
        ]

    def test_identity_dedup_does_not_collapse_user_centroid_stops(self):
        import identity_dedup as idd
        stops = self._user_stops_on_centroid()
        kept, dropped = idd.dedupe_by_location_or_qid(stops)
        assert len(kept) == 4, (len(kept), dropped)
        assert dropped == []

    def test_same_building_is_false_for_two_user_centroid_stops(self):
        import local802_relevance_gate as l802
        stops = self._user_stops_on_centroid()
        assert l802.same_building(stops[0], stops[1]) is False
        kept, removed = l802.dedupe_same_building_stops(
            stops, log=lambda *_a: None)
        assert len(kept) == 4, removed

    def test_textually_identical_user_stops_still_collapse(self):
        import identity_dedup as idd
        dup = [{"name": "Rambutan", "user_explicit": True},
               {"name": "Rambutan", "user_explicit": True}]
        kept, dropped = idd.dedupe_by_location_or_qid(dup)
        assert len(kept) == 1

    def test_genuine_nonuser_nearby_pair_still_collapses(self):
        import identity_dedup as idd
        near = [{"name": "Cafe A", "coordinates": "10.100000, 106.100000"},
                {"name": "Cafe A Annex", "coordinates": "10.100000, 106.100000"}]
        kept, dropped = idd.dedupe_by_location_or_qid(near)
        assert len(kept) == 1, (len(kept), dropped)

    def test_resolved_share_link_stops_have_distinct_pins(self):
        # Rambutan and Longan resolved to DISTINCT coords, so even without the
        # user-explicit exemption they are two pins.
        import user_stop_input as u
        import identity_dedup as idd
        parsed = u.parse_user_stops(SEVEN_RAW, resolve=_stub, log=lambda *_a: None)
        stops = []
        for p in parsed:
            s = {"name": p["name"], "user_explicit": True, "_anchor": True}
            if p["lat"] is not None:
                s["coordinates"] = f"{p['lat']:.6f}, {p['lng']:.6f}"
            else:
                s["coordinates"] = TestCentroidCollapseDedupe._CENTROID
                s["coord_source"] = "fallback"
            stops.append(s)
        kept, dropped = idd.dedupe_by_location_or_qid(stops)
        assert len(kept) == 7, (len(kept), dropped)


# ───────────────────── 4. fallback-coord marker recognition ──────────────────
class TestFallbackCoordMarker:
    def test_markers_recognised(self):
        import identity_dedup as idd
        for marker in ({"_coord_fallback": True},
                       {"coord_source": "centroid"},
                       {"coord_source": "city_centroid"},
                       {"coord_confidence": "fallback"},
                       {"centroid_fallback": True}):
            assert idd._is_fallback_coord_stop(marker) is True, marker

    def test_resolved_coord_is_not_fallback(self):
        import identity_dedup as idd
        assert idd._is_fallback_coord_stop(
            {"coord_source": "user_share_link",
             "coord_confidence": "resolved"}) is False
