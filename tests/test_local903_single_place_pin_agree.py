"""LOCAL-903 -- the wrong geocoder hit, the snapped place superseding it, single-place agreement, tour pin,
address check. Generic names, offline, $0, every network lookup mocked."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import area_resolver as ar  # noqa: E402
import pin_snap  # noqa: E402
import route_content_896 as rc  # noqa: E402
import single_place_903 as sp  # noqa: E402

SITE = (10.8130, 107.8940)          # the real site (generic)
SNAP = (10.8281, 107.8828)          # the mocked verified snap point, ~2 km from the site
WRONG = (10.9286, 108.0885)         # the wrong geocoder place reference (~25 km off)
CENTRE = (11.0833, 108.0833)


def _km(a, b):
    return pin_snap._haversine_m(a, b) / 1000.0


# ── 1 geocoder validation ───────────────────────────────────────────────────────────────────────────────
CITY = {"lat": WRONG[0], "lng": WRONG[1], "class": "boundary", "type": "administrative",
        "display_name": "Zed City, Zed Province, Zedland"}
TOWN = {"lat": 10.95, "lng": 108.1, "class": "place", "type": "town", "display_name": "Alpha Town, Zed Province"}
PEAK = {"lat": SITE[0], "lng": SITE[1], "class": "natural", "type": "peak",
        "display_name": "Núi Alpha, Xã Pi, Zed Province, Zedland"}


def test_city_result_rejected_peak_accepted():
    logs = []
    assert ar.geocoder_hit_verdict("Alpha Mountain", CITY) == (False, "boundary/administrative")
    assert ar.geocoder_hit_verdict("Alpha Mountain", TOWN)[0] is False
    assert ar.geocoder_hit_verdict("Alpha Mountain", PEAK)[0] is True
    best = ar.pick_geocoder_hit("Alpha Mountain", "Alpha Mountain", [CITY, TOWN, PEAK], log=logs.append)
    assert best is PEAK
    assert any("[LOCAL-903] geocoder hit" in l and "rejected: boundary/administrative" in l for l in logs)


def test_pagoda_needs_worship_and_default_rejects_only_admin():
    wor = {"class": "amenity", "type": "place_of_worship", "display_name": "Chùa Beta"}
    assert ar.geocoder_hit_verdict("Beta Pagoda", wor)[0] is True
    assert ar.geocoder_hit_verdict("Beta Pagoda", {"class": "highway", "type": "residential"})[0] is False
    assert ar.geocoder_hit_verdict("Gamma Hall", {"class": "building", "type": "yes"})[0] is True
    assert ar.geocoder_hit_verdict("Gamma Hall", CITY)[0] is False


def test_prefers_display_name_with_core_token_diacritics_folded():
    other = {"lat": 1.0, "lng": 1.0, "class": "natural", "type": "peak", "display_name": "Núi Khác, Zed"}
    assert ar.pick_geocoder_hit("Núi Alpha", "Núi Alpha", [other, PEAK], log=None) is PEAK
    # no core match anywhere -> the top acceptable one
    assert ar.pick_geocoder_hit("Núi Omega", "Núi Omega", [other, PEAK], log=None) is other


def test_place_reference_uses_validated_candidates_and_refuses_city():
    ar_wd = ar._wikidata_name_lookup
    ar._wikidata_name_lookup = lambda *a, **k: None
    try:
        calls = []
        def cands(q):
            calls.append(q)
            return [CITY, TOWN]
        ref = ar.first_named_place_reference("Alpha Mountain and the Big Statue, Zed Province", "Zed Province",
                                             CENTRE, candidates_fn=cands)
        assert ref is None and calls
        ref = ar.first_named_place_reference("Alpha Mountain and the Big Statue, Zed Province", "Zed Province",
                                             CENTRE, candidates_fn=lambda q: [CITY, PEAK])
        assert ref and ref["source"] == "first_named_place_geocoder"
        assert _km((ref["lat"], ref["lng"]), SITE) < 0.1
    finally:
        ar._wikidata_name_lookup = ar_wd


# ── 2 snapped place re-pins its sibling ─────────────────────────────────────────────────────────────────────
def _two(first_snapped=True):
    pois = [{"name": "Alpha Mountain", "coordinates": f"{SNAP[0]:.6f}, {SNAP[1]:.6f}"},
            {"name": "Big Statue", "coordinates": f"{WRONG[0]:.6f}, {WRONG[1]:.6f}", "coordinates_approximate": True}]
    rows = [{"snapped": first_snapped, "new_coordinate": SNAP if first_snapped else None, "source": "serper"},
            {"snapped": False, "new_coordinate": None, "reference": WRONG, "rejected_900b": True}]
    return pois, rows


def test_snapped_place_repins_sibling():
    pois, rows = _two()
    logs = []
    n = sp.repin_to_snapped_place(pois, rows, "Alpha Mountain", WRONG, log=logs.append)
    assert n == 1 and _km(pin_snap._poi_coord(pois[1]), SNAP) < 0.01 and pois[1]["coordinates_approximate"]
    assert any("[LOCAL-903] stop=2 re-pinned to the snapped place 'Alpha Mountain'" in l and "km off)" in l
               for l in logs)


def test_unverified_or_unrelated_sibling_not_moved():
    pois, rows = _two(first_snapped=False)
    assert sp.repin_to_snapped_place(pois, rows, "Alpha Mountain", WRONG) == 0
    pois, rows = _two()
    pois[1]["coordinates"] = "10.5000, 107.5000"        # not on the old reference
    assert sp.repin_to_snapped_place(pois, rows, "Alpha Mountain", WRONG) == 0
    pois, rows = _two()
    pois[1].pop("coordinates_approximate")
    assert sp.repin_to_snapped_place(pois, rows, "Alpha Mountain", WRONG) == 0


# ── 3 single-place agreement and "Walk on to" ─────────────────────────────────────────────────────────────
def test_agreement_moves_unverified_and_directions_walk_on():
    pois, rows = _two()
    logs = []
    assert sp.agree_single_place(pois, rows, "DISTRICT", log=logs.append) == 1
    assert _km(pin_snap._poi_coord(pois[1]), SNAP) < 0.01 and pois[1]["coordinates_approximate"]
    assert any("single-place agreement" in l and "stop=2" in l for l in logs)
    text = ("Stop 1: Alpha Mountain\nCoordinates: %s\nDirections: Continue to Big Statue.\n\n"
            "Stop 2: Big Statue\nCoordinates: %s\nbody\n") % (pois[0]["coordinates"], pois[1]["coordinates"])
    out = rc.normalize_directions(text, force=True)
    assert "Directions: Walk on to Big Statue." in out


def test_agreement_only_on_two_stop_district_building_and_far_apart():
    pois, rows = _two()
    assert sp.agree_single_place(pois, rows, "CITY") == 0
    pois[1]["coordinates"] = "10.8290, 107.8830"
    assert sp.agree_single_place(pois, rows, "DISTRICT") == 0
    pois, rows = _two()
    assert sp.agree_single_place(pois + [dict(pois[0])], rows, "DISTRICT") == 0
    pois, rows = _two(first_snapped=False)           # neither verified -> unchanged
    assert sp.agree_single_place(pois, rows, "DISTRICT") == 0


# ── 4 tour pin after the snap ─────────────────────────────────────────────────────────────────────────────
def test_tour_pin_is_first_stops_final_pin():
    pois, rows = _two()
    pois[0]["coordinates"] = f"{SNAP[0]:.6f}, {SNAP[1]:.6f}"
    pre = WRONG
    got = sp.tour_pin(pois, pre)
    assert _km(got, SNAP) < 0.01
    assert sp.tour_pin([{"name": "x", "coordinates": ""}], pre) == pre
    assert sp.tour_pin([], (None, None)) == (None, None)


# ── 5 address check ───────────────────────────────────────────────────────────────────────────────────────
def test_address_keeps_on_district_token_despite_province_rename():
    addr = "Thôn 1, Thị Trấn Beta Town, Huyện Gamma Delta, Old Province, Vietnam"
    rev = "Hamlet, Xã Gamma Delta, Tỉnh New Province, 77706, Việt Nam"
    assert pin_snap.address_agrees(addr, rev, "Alpha Mountain, Old Province") is True
    assert pin_snap.address_agrees("Hamlet, Xã Gamma Delta, Old Province", rev) is True


def test_address_dropped_when_district_differs():
    addr = "Thị Trấn Beta Town, Huyện Epsilon, Old Province, Vietnam"
    rev = "Hamlet, Xã Gamma Delta, Tỉnh New Province, 77706, Việt Nam"
    assert pin_snap.address_agrees(addr, rev, "") is False


# ── 6 replay: generic fixture from the proof text and log lines ──────────────────────────────────────────
def test_replay_both_pins_within_3km_of_snap_point():
    logs = []
    # after the 900 pin check both stops sit on the wrong geocoder point (first_named_place_geocoder)
    pois = [{"name": "Alpha Mountain", "coordinates": f"{WRONG[0]:.6f}, {WRONG[1]:.6f}", "coordinates_approximate": True,
             "address": "Thị Trấn Beta Town, Huyện Gamma Delta, Old Province, Vietnam"},
            {"name": "Big Statue", "coordinates": f"{WRONG[0]:.6f}, {WRONG[1]:.6f}", "coordinates_approximate": True}]
    # the 791C snap (mocked serper) pins the mountain; the statue's snap is rejected 900B (outside scope)
    pois[0]["coordinates"] = f"{SNAP[0]:.6f}, {SNAP[1]:.6f}"
    rows = [{"snapped": True, "new_coordinate": SNAP, "source": "serper", "reference": SNAP},
            {"snapped": False, "new_coordinate": None, "reference": (0.0, 0.0), "rejected_900b": True}]
    sp.reconcile_after_snap(pois, rows, "Alpha Mountain", WRONG, "DISTRICT", log=logs.append)
    for p in pois:
        assert _km(pin_snap._poi_coord(p), SNAP) < 3.0
        assert _km(pin_snap._poi_coord(p), SITE) < 3.0
    assert _km(sp.tour_pin(pois), SITE) < 3.0
    # address kept (same district, renamed province)
    n = pin_snap.verify_addresses(pois[:1], rows[:1], scope="Alpha Mountain, Old Province",
                                  reverse_fn=lambda a, b: "Lập Nghĩa, Xã Gamma Delta, Tỉnh New Province, Việt Nam")
    assert n == 0 and pois[0]["address"]
