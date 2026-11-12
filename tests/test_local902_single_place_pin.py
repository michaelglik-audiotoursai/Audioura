"""LOCAL-902 -- wave 49 rollback on the single-place tour. Generic fixtures, offline, $0, network mocked.

1  a model-only tour: the in-scope reference replaces the model pins ([LOCAL-902] snap accepted); the
   same-name candidate outside the scope is still rejected; verified-to-verified moves keep the 15 km cap.
2  Wikidata miss -> logged, then the free geocoder with name variants (generic word dropped, diacritics folded).
3  "A and the B" -> two stops titled A and B.
4  neighbour sentence: one clean sentence from the neighbour's delivered body.
5  superlative family; comparative naming places outside the tour.
6  body route sentence, Address check, closing mood filler; replay of the 552 w49 fixture.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import area_resolver as ar  # noqa: E402
import pin_snap  # noqa: E402
import place_names_900 as pn  # noqa: E402
import required_places_902 as rp  # noqa: E402
import route_content_896 as rc  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "local902_tour_generic.txt")
REF = (10.8100, 107.8900)          # the real site (mocked reference)
MODEL_A, MODEL_B = (10.8271, 107.5903), (10.8265, 107.5901)   # ~33 km west: the model's own pins
CENTRE = (11.0833, 108.0833)       # coarse province centre
BBOX = [10.3, 11.5, 107.3, 108.9]  # province bbox


def _pois():
    return [{"name": "Alpha Mountain", "coordinates": "10.8271, 107.5903"},
            {"name": "Beta Pagoda", "coordinates": "10.8265, 107.5901"}]


# ── 1 ───────────────────────────────────────────────────────────────────────
def test_model_only_tour_accepts_in_scope_reference():
    logs = []
    pois = _pois()
    pin_snap_ref = lambda name, scope, c: (REF[0], REF[1], "nominatim", name)
    out, rows = pin_snap.snap_poi_coordinates(
        pois, scope="Alpha Mountain, Zed Province", scope_center=None, scope_bbox=BBOX, coarse_center=CENTRE,
        reference_fn=lambda *a, **k: (REF[0], REF[1], "nominatim"), log=logs.append, scope_precision="DISTRICT")
    # an INJECTED reference_fn bypasses the live guards: the 900B 15 km cap must still not block a model pin
    for p in out:
        lat, lng = [float(x) for x in p["coordinates"].split(",")]
        assert pin_snap._haversine_m((lat, lng), REF) < 15000
    assert any("[LOCAL-902] snap accepted" in l and "model pins unverified, reference in scope" in l for l in logs)


def _live_guards_snap(ref, pois=None, **kw):
    """Run the LIVE guard path (no injected reference_fn): the reference comes through snap_pin's lookups."""
    logs = []
    pois = pois or _pois()
    orig = pin_snap._default_reference
    pin_snap._default_reference = lambda name, scope, c: (ref[0], ref[1], "nominatim")
    try:
        out, rows = pin_snap.snap_poi_coordinates(
            pois, scope="Alpha Mountain, Zed Province", scope_center=None, scope_bbox=kw.pop("bbox", BBOX),
            coarse_center=CENTRE, log=logs.append, require_name_match=False, scope_precision="DISTRICT", **kw)
    finally:
        pin_snap._default_reference = orig
    return out, rows, logs


def test_live_path_in_scope_reference_replaces_unverified_model_pins():
    out, rows, logs = _live_guards_snap(REF)
    assert all(pin_snap._haversine_m(tuple(float(x) for x in p["coordinates"].split(",")), REF) < 15000 for p in out)
    assert any("[LOCAL-902] snap accepted" in l for l in logs)
    assert not any("snap refused" in l for l in logs)


def test_same_name_candidate_outside_scope_is_still_rejected():
    far = (11.9, 109.5)               # ~155+ km away, outside the bbox
    out, rows, logs = _live_guards_snap(far)
    assert [p["coordinates"] for p in out] == ["10.8271, 107.5903", "10.8265, 107.5901"]
    assert not any("[LOCAL-902] snap accepted" in l for l in logs)


def test_verified_to_verified_move_keeps_the_15km_cap():
    pois = [{"name": "Alpha Mountain", "coordinates": "10.8271, 107.5903", "coord_source": "geocoded",
             "wikidata_lat": 10.8271, "wikidata_lng": 107.5903}]
    out, rows, logs = _live_guards_snap(REF, pois=pois)
    assert out[0]["coordinates"] == "10.8271, 107.5903"      # a verified pin 33 km away is not replaced by 900B's rule
    assert not any("[LOCAL-902] snap accepted" in l for l in logs)


# ── 2 ───────────────────────────────────────────────────────────────────────
def test_place_name_variants_generic_and_diacritics():
    v = ar.place_name_variants("Núi Bà Mountain")
    assert "Nui Ba Mountain" in v and "Bà" not in [] and "Ba" in v and "Mount Ba" in v
    v = ar.place_name_variants("Alpha Mountain")
    assert v[0] == "Alpha Mountain" and "Alpha" in v and "Mount Alpha" in v and "N\u00fai Alpha" in v
    assert not any("Sigma" in x for x in v)


def test_wikidata_miss_logs_then_falls_back_to_geocoder(monkeypatch, capsys):
    monkeypatch.setattr(ar, "_wikidata_name_lookup", lambda n, c="": None)
    monkeypatch.setattr(ar, "_nominatim_bbox", lambda c: None)
    calls = []

    def geo(q):
        calls.append(q)
        return REF if q == "Alpha, Zed Province" else None
    got = ar.first_named_place_reference("Alpha Mountain and the Reclining Buddha, Zed Province", "Zed Province",
                                         CENTRE, geocode_fn=geo)
    assert got and (got["lat"], got["lng"]) == REF and got["source"] == "first_named_place_geocoder"
    assert calls[0] == "Alpha Mountain, Zed Province" and "Alpha, Zed Province" in calls


def test_wikidata_and_geocoder_miss_is_always_logged(monkeypatch, capsys):
    monkeypatch.setattr(ar, "_wikidata_name_lookup", lambda n, c="": None)
    monkeypatch.setattr(ar, "_nominatim_bbox", lambda c: None)
    assert ar.first_named_place_reference("Alpha Mountain and the Statue, Zed Province", "Zed Province", CENTRE,
                                          geocode_fn=lambda q: None) is None
    assert "[LOCAL-901] place reference 'Alpha Mountain' \u2192 none (wikidata miss" in capsys.readouterr().out


def test_geocoder_hit_outside_the_province_is_refused(monkeypatch, capsys):
    monkeypatch.setattr(ar, "_wikidata_name_lookup", lambda n, c="": None)
    monkeypatch.setattr(ar, "_nominatim_bbox", lambda c: None)
    assert ar.first_named_place_reference("Alpha Mountain and the Statue, Zed Province", "Zed Province", CENTRE,
                                          geocode_fn=lambda q: (14.5, 109.9)) is None


# ── 3 ───────────────────────────────────────────────────────────────────────
def _mk(name, addr=""):
    return {"name": name, "address": addr, "coordinates": ""}


def test_required_places_split():
    assert rp.required_places("Alpha Mountain and the Reclining Buddha, Zed Province, Zedland") == \
        ["Alpha Mountain", "Reclining Buddha"]
    assert rp.required_places("Alpha Hill and Beta Quarter, Zed City") == []     # two districts: an area request
    assert rp.required_places("Alpha Mountain, Zed Province") == []


def test_a_and_the_b_gives_two_stops_titled_a_and_b():
    logs = []
    names = rp.required_places("Alpha Mountain and the Reclining Buddha, Zed Province")
    out = rp.ensure_required_stops([_mk("Alpha Mountain"), _mk("Beta Pagoda")], names, _mk, max_stops=2,
                                   log=logs.append)
    assert [p["name"] for p in out] == ["Alpha Mountain", "Reclining Buddha"]
    assert all(p["user_explicit"] for p in out)
    assert any("required place 'Reclining Buddha' was not a stop" in l for l in logs)


def test_covered_names_are_left_alone():
    names = ["Alpha Mountain", "Reclining Buddha"]
    out = rp.ensure_required_stops([_mk("Alpha Mountain"), _mk("The Reclining Buddha Statue")], names, _mk, 2)
    assert [p["name"] for p in out] == ["Alpha Mountain", "The Reclining Buddha Statue"]


def test_room_in_the_tour_appends_instead_of_replacing():
    names = ["Alpha Mountain", "Reclining Buddha"]
    out = rp.ensure_required_stops([_mk("Alpha Mountain"), _mk("Beta Pagoda")], names, _mk, max_stops=3)
    assert [p["name"] for p in out] == ["Alpha Mountain", "Reclining Buddha", "Beta Pagoda"] or \
        {p["name"] for p in out} == {"Alpha Mountain", "Reclining Buddha", "Beta Pagoda"}


# ── 4 ───────────────────────────────────────────────────────────────────────
def _split(t):
    return rc.split_sentences(t)


def test_neighbour_sentence_must_be_one_clean_sentence():
    bad = "Will take a modern cable car to discover Alpha Mountain Alpha Mountain is an extinct volcano located not far from here."
    assert pn.neighbour_sentence("Alpha Mountain", [bad], _split) is None
    good = "Alpha Mountain is an extinct volcano that rises above the coastal plain."
    assert pn.neighbour_sentence("Alpha Mountain", [bad + " " + good], _split) == good
    assert pn.neighbour_sentence("Alpha Mountain", ["alpha mountain is an extinct volcano on the plain"], _split) is None
    long_ = "Alpha Mountain " + " ".join(["is"] + ["very"] * 31) + " old."
    assert pn.neighbour_sentence("Alpha Mountain", [long_], _split) is None
    rep = "Alpha Mountain is the quiet peak and the quiet peak is the old volcano."
    assert pn.neighbour_sentence("Alpha Mountain", [rep], _split) is None


def test_neighbour_evidence_is_the_delivered_body_not_raw_evidence():
    rc.set_route({"is_description": True, "origin": "Alpha Lodge", "destination": "Gamma Mountain", "through": [],
                  "region": "Kappa", "origin_locality": "Alpha Quarter"})
    try:
        t = ("Stop 1: Alpha Mountain\nCoordinates: 1.0, 1.0\nType/Specialty: Mountain\nBody one.\n\n"
             "Stop 2: Beta Station\nCoordinates: 1.0, 1.0\nType/Specialty: Station\n"
             "Alpha Mountain is an extinct volcano above the coastal plain. Nobody here sells tickets.\n")
        blocks = rc._stop_blocks(t)
        ev = rc._neighbour_evidence(blocks, 0, {"beta station": "Will take a cable car to discover Alpha Mountain"}, t)
        assert len(ev) == 1 and ev[0].startswith("Alpha Mountain is an extinct volcano")
        assert "Will take" not in ev[0]
    finally:
        rc.clear_route()


# ── 5 ───────────────────────────────────────────────────────────────────────
SUP = ("Stop 4: Alpha Mountain\nCoordinates: 1.0, 1.0\nType/Specialty: Mountain\n"
       "Alpha Mountain is home to the longest reclining Buddha statue in Asia. A stair climbs the slope.\n\n"
       "Stop 7: Reclining Buddha\nCoordinates: 1.0, 1.0\nType/Specialty: Statue\n"
       "This reclining Buddha is the biggest in Zedland and is bigger than the reclining Buddha statues at Wat Pho "
       "and Wat Lokay. Pilgrims walk around it.\n")


@pytest.fixture
def route():
    rc.set_route({"is_description": True, "origin": "Alpha Lodge", "destination": "Gamma Mountain", "through": [],
                  "region": "Kappa", "origin_locality": "Alpha Quarter"})
    yield
    rc.clear_route()


def test_superlative_family_longest_vs_biggest_same_object(route):
    cl = rc._superlatives("This reclining Buddha is the biggest in Zedland.")
    assert cl and cl[0]["grp"] == "size"          # implicit object: no noun after the superlative
    assert rc._SUP_GROUP["longest"] == rc._SUP_GROUP["biggest"] == rc._SUP_GROUP["largest"] == rc._SUP_GROUP["tallest"]
    out = rc.consistent_superlatives(SUP, {"Alpha Mountain": "a stair", "Reclining Buddha": "pilgrims"})
    assert "longest" not in out and "biggest" not in out and "Pilgrims walk around it." in out


def test_comparative_naming_places_outside_the_tour_is_dropped(route):
    out = rc.drop_unsupported_comparatives(SUP, {"Alpha Mountain": "x", "Reclining Buddha": "pilgrims"})
    assert "Wat Pho" not in out
    ok = rc.drop_unsupported_comparatives(SUP, {"Alpha Mountain": "x",
                                                "Reclining Buddha": "bigger than the statues at Wat Pho and Wat Lokay"})
    assert "Wat Pho" in ok
    assert rc.drop_unsupported_comparatives(SUP, None) == SUP     # the delivery pass has no evidence: unchanged


def test_thin_body_report(route):
    logs = []
    before = "Stop 6: X\nCoordinates: 1.0, 1.0\nOne. Two. Three. Four.\n"
    after = "Stop 6: X\nCoordinates: 1.0, 1.0\nOne. Two.\n"
    rc.report_thin_bodies(before, after, logs.append)
    assert logs and "Stop 6" in logs[0] and "4 to 2" in logs[0]


# ── 6 ───────────────────────────────────────────────────────────────────────
def _fixture():
    with open(FIX, encoding="utf-8") as f:
        return f.read()


def test_invented_route_sentence_detection():
    assert rc.is_invented_route_sentence("From the main street in Xi Commune, head south on ĐT 719 for about 5 "
                                         "kilometers until you see the entrance on your right.")
    assert rc.is_invented_route_sentence("Follow QL 55 for ten minutes.")
    assert not rc.is_invented_route_sentence("The mountain lies 28 kilometers west of the coastal city.")
    assert not rc.is_invented_route_sentence("The site is reached from National Route 1.")


def test_replay_552_w49_no_road_no_head_south_no_mood_closing():
    logs = []
    out = rc.apply_single_place_guards(_fixture(), log=logs.append)
    assert "ĐT" not in out and "head south" not in out
    assert "profound connection" not in out and "invites you to reflect" not in out
    assert "That's 2 stops in all." in out and "Alpha Mountain" in out and "longest in Zedland" in out
    assert any("[LOCAL-902]" in l and "invented route" in l for l in logs)


def test_address_agreement_uses_district_tokens():
    rev = "Tan Thanh, Ham Thuan Nam, Zed Province, Zedland"
    assert not pin_snap.address_agrees("Thôn 3, Xi Commune, Pi District, Zed Province, Zedland", rev,
                                       "Alpha Mountain, Zed Province, Zedland")
    assert pin_snap.address_agrees("Tan Thanh, Ham Thuan Nam, Zed Province, Zedland", rev, "Zed Province")
    assert pin_snap.address_agrees("Zed Province, Zedland", rev, "Zed Province, Zedland")   # nothing to contradict


def test_verify_addresses_drops_the_wrong_district_only_with_a_reference():
    pois = [{"name": "Alpha Mountain", "address": "Thôn 3, Xi Commune, Pi District, Zed Province"},
            {"name": "Beta Pagoda", "address": "Thôn 3, Xi Commune, Pi District, Zed Province"}]
    rows = [{"snapped": True, "new_coordinate": REF, "reference": REF}, {"snapped": False, "reference": None}]
    logs = []
    n = pin_snap.verify_addresses(pois, rows, scope="Alpha Mountain, Zed Province",
                                  reverse_fn=lambda a, b: "Tan Thanh, Ham Thuan Nam, Zed Province", log=logs.append)
    assert n == 1 and pois[0]["address"] == "" and pois[1]["address"].startswith("Thôn 3")
    assert any("[LOCAL-902] address dropped" in l for l in logs)
    # no reference at all -> nothing is judged
    pois = [{"name": "A", "address": "x, y"}]
    assert pin_snap.verify_addresses(pois, [{"snapped": False, "reference": None}], reverse_fn=lambda a, b: "q") == 0


def test_more_than_two_stops_is_not_the_single_place_path():
    pois = [{"name": str(i), "address": "x, y, z"} for i in range(3)]
    rows = [{"snapped": True, "new_coordinate": REF, "reference": REF}] * 3
    assert pin_snap.verify_addresses(pois, rows, reverse_fn=lambda a, b: "q") == 0


def test_lead_large_tour_model_pin_keeps_900b_radius():
    """[LOCAL-902/LEAD] on a >2-stop tour a model pin may not jump ~33 km just because the reference is in scope."""
    pois = _pois() + [{"name": "Gamma Hall", "coordinates": "10.8300, 107.5950"},
                      {"name": "Delta Gate", "coordinates": "10.8290, 107.5960",
                       "wikidata_lat": 10.8290, "wikidata_lng": 107.5960}]   # one VERIFIED pin
    pois = [dict(p, coord_source=p.get("coord_source", "model")) if "wikidata_lat" not in p else p for p in pois]
    out, rows, logs = _live_guards_snap(REF, pois=pois)
    assert not any("[LOCAL-902] snap accepted" in l for l in logs)
    for p in out:
        lat, lng = [float(x) for x in p["coordinates"].split(",")]
        assert pin_snap._haversine_m((lat, lng), REF) > 15000      # 900B DISTRICT cap still held them


def test_lead905_far_model_pin_snaps_to_in_scope_reference():
    """[LEAD-905] both model pins ~86 km from the coarse centre (offshore) and ~108 km from the in-scope
    reference: the reference is in scope, so the move is accepted however far the unverified pin was."""
    far = [{"name": "Alpha Mountain", "coordinates": "10.9794, 108.8656"},
           {"name": "Beta Statue", "coordinates": "10.9795, 108.8657"}]
    out, rows, logs = _live_guards_snap(REF, pois=far, bbox=None)
    assert any("[LOCAL-902] snap accepted" in l for l in logs)
    for p in out:
        lat, lng = [float(x) for x in p["coordinates"].split(",")]
        assert pin_snap._haversine_m((lat, lng), REF) < 3000


def test_lead905_out_of_scope_reference_still_refused_for_far_model_pin():
    far = [{"name": "Alpha Mountain", "coordinates": "10.9794, 108.8656"},
           {"name": "Beta Statue", "coordinates": "10.9795, 108.8657"}]
    abroad = (13.748056, 100.491111)
    out, rows, logs = _live_guards_snap(abroad, pois=far, bbox=None)
    assert not any("[LOCAL-902] snap accepted" in l for l in logs)
    for p in out:
        lat, lng = [float(x) for x in p["coordinates"].split(",")]
        assert pin_snap._haversine_m((lat, lng), abroad) > 500000
