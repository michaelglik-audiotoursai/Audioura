"""LOCAL-906D -- proof of 906C, offline, $0, generic fixtures (D769). Every lookup is mocked.

1  place reference retried by local name / alias / the province-scoped geocoder (inside the province only)
2  the province BOUNDING BOX (admin boundary, not the same-named station; Wikidata P625 + area fallback);
   an unverified model pin outside it is "far"
3  a facility named after a natural-feature stop is an approximate reference, only inside the box
   (the City Hall shape stays refused)
4  last resort: a far pin moves to another stop's in-province reference, else the province centre (flagged)
5  the address follows the moved pin
6  the same event twice in one stop (same year + person + place token) is one fact
+  full replay of the logged pin chain
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SERPER_API_KEY", None)
os.environ["THIN_STOP_SEARCH"] = "0"

import pin_fallback_906d as pf  # noqa: E402
import pin_snap  # noqa: E402
import route_content_896 as rc  # noqa: E402
import single_place_903 as sp  # noqa: E402

PROVINCE = "Beta Province"
COUNTRY = "Gamma"
BOX = [10.60, 11.45, 107.75, 108.75]           # south, north, west, east
CENTRE = (11.08, 108.08)
SITE = (11.00, 108.30)                         # the real mountain: inside the box
FACILITY = (11.0021, 108.3012)                 # "<Mountain> Cable Car Station": inside the box
MODEL_PIN_1 = (11.4633, 107.5291)              # the logged model coordinate: 82 km off, outside the province
MODEL_PIN_2 = (11.4700, 107.5200)


def _out_of(pt, box):
    return not pf.in_box(pt, box)


# ── 1. the place reference, retried ──────────────────────────────────────────────────────────────────────
def test_wikidata_miss_then_local_language_alias_hit():
    calls = []

    def wd(label, lang):
        calls.append((label, lang))
        if lang == "en":
            return []                                          # the logged miss
        return [{"qid": "Q1", "labels": ["N\u00fai Alpha"], "aliases": ["Alpha Mountain"],
                 "lat": SITE[0], "lng": SITE[1]}]

    logs = []
    got = pf.place_reference_retry("Alpha Mountain", PROVINCE, COUNTRY, box=BOX, languages=["vi"],
                                   wd_search_fn=wd, candidates_fn=lambda q, h="": [], log=logs.append)
    assert got and (got["lat"], got["lng"]) == SITE and got["precision"] == "place"
    assert any("[LOCAL-906D] place reference 'Alpha Mountain' -> 11.0000,108.3000 via wikidata_local_language:vi"
               in x for x in logs), logs
    assert calls[0][1] == "vi"                                  # the local language is tried first


def test_alias_match_is_diacritic_insensitive_and_wrong_province_hit_is_refused():
    far = {"qid": "Q2", "labels": ["Alpha Mountain"], "aliases": [], "lat": 20.0, "lng": 105.0}   # same name, elsewhere
    got = pf.place_reference_retry("Alpha Mountain", PROVINCE, box=BOX, languages=["vi"],
                                   wd_search_fn=lambda l, g: [far], candidates_fn=lambda q, h="": [], log=lambda m: None)
    assert got is None
    near = {"qid": "Q3", "labels": ["\u00c1lpha"], "aliases": ["N\u00fai \u00c1lpha"], "lat": SITE[0], "lng": SITE[1]}
    got = pf.place_reference_retry("Alpha Mountain", PROVINCE, box=BOX, languages=["vi"],
                                   wd_search_fn=lambda l, g: [near], candidates_fn=lambda q, h="": [], log=lambda m: None)
    assert got and (got["lat"], got["lng"]) == SITE


def test_geocoder_retry_uses_core_name_province_and_peak_type():
    queries = []

    def cands(q, hint=""):
        queries.append((q, hint))
        return [{"lat": 20.0, "lng": 105.0, "class": "natural", "type": "peak", "display_name": "Alpha, Elsewhere"},
                {"lat": SITE[0], "lng": SITE[1], "class": "natural", "type": "peak",
                 "display_name": "Alpha, Beta Province, Gamma"}]

    logs = []
    got = pf.place_reference_retry("Alpha Mountain", PROVINCE, COUNTRY, stop_type="mountain", box=BOX,
                                   wd_search_fn=lambda l, g: [], candidates_fn=cands, log=logs.append)
    assert got and (got["lat"], got["lng"]) == SITE            # the out-of-province peak is skipped
    assert queries[0] == ("alpha, Beta Province", "peak")
    assert any("via geocoder_province:peak" in x for x in logs), logs


def test_retry_with_no_box_or_no_hit_returns_none():
    assert pf.place_reference_retry("Alpha Mountain", PROVINCE, box=None, wd_search_fn=lambda *a: [],
                                    candidates_fn=lambda *a: []) is None
    logs = []
    assert pf.place_reference_retry("Alpha Mountain", PROVINCE, box=BOX, wd_search_fn=lambda *a: [],
                                    candidates_fn=lambda *a: [], log=logs.append) is None
    assert any("-> none" in x for x in logs)


def test_area_resolver_901_miss_retries_906d(monkeypatch, capsys):
    import area_resolver as ar
    monkeypatch.setattr(ar, "_wikidata_name_lookup", lambda *a, **k: None)
    got = ar.first_named_place_reference(
        "Alpha Mountain, Beta Province", "Beta Province", CENTRE, candidates_fn=lambda q: [],
        province_box_fn=lambda c, k: {"box": BOX},
        wd_search_fn=lambda l, g: [] if g == "en" else [
            {"labels": ["Alpha Mountain"], "aliases": [], "lat": SITE[0], "lng": SITE[1]}],
        language="vi")
    out = capsys.readouterr().out
    assert "[LOCAL-901] place reference 'Alpha Mountain' \u2192 none" in out
    assert got and (got["lat"], got["lng"]) == SITE and got["source"] == "first_named_place_906d"


# ── 2. the province box and far pins ─────────────────────────────────────────────────────────────────────
def test_province_box_prefers_the_admin_boundary_over_a_same_named_station():
    rows = [{"class": "railway", "type": "station", "lat": "11.9", "lon": "109.9",
             "boundingbox": ["11.89", "11.91", "109.89", "109.91"]},
            {"class": "boundary", "type": "administrative", "lat": "11.08", "lon": "108.08",
             "boundingbox": [str(b) for b in BOX]}]
    pb = pf.province_box(PROVINCE, COUNTRY, search_fn=lambda q: rows)
    assert pb["box"] == BOX and pb["source"] == "geocoder_admin_boundary" and pb["center"] == (11.08, 108.08)


def test_province_box_wikidata_fallback_is_a_square_around_p625():
    pb = pf.province_box(PROVINCE, COUNTRY, search_fn=lambda q: [{"class": "railway", "type": "station"}],
                         wikidata_fn=lambda n: (11.08, 108.08, 7800.0))
    s, n, w, e = pb["box"]
    assert pb["source"] == "wikidata_p625_area" and s < 11.08 < n and w < 108.08 < e
    assert 60 < (n - s) * 111 < 100                             # sqrt(7800) = 88 km
    assert pf.province_box(PROVINCE, search_fn=lambda q: [], wikidata_fn=lambda n: None) is None


def test_far_pin_is_logged_only_for_an_unverified_pin_outside_the_box():
    pois = [{"name": "Alpha Mountain", "coordinates": "11.4633, 107.5291"},
            {"name": "Delta", "coordinates": "11.0, 108.2"},
            {"name": "Eps", "coordinates": "11.47, 107.52", "coord_source": "user_share_link"},
            {"name": "Zeta", "coordinates": "11.47, 107.52", "wikidata_lat": 11.47, "wikidata_lng": 107.52}]
    logs = []
    far = pf.flag_far_pins(pois, BOX, PROVINCE, log=logs.append)
    assert far == [0]
    assert len(logs) == 1 and logs[0].startswith("  [LOCAL-906D] stop=1 model pin outside Beta Province (")
    assert logs[0].endswith(" km)")


# ── 3. a facility named after the stop ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("title,ref,typ,ok", [
    ("Alpha Mountain", "Alpha Mountain Cable Car Station", "", True),
    ("Alpha Mountain", "Alpha Cable Car Station", "", True),        # the shape 791E refused
    ("Alpha Mountain", "Alpha Mountain Tourist Area", "", True),
    ("Alpha", "Alpha Parking", "mountain", True),
    ("Alpha Lake", "Alpha Lake Visitor Centre", "", True),
    ("Alpha Beach", "Alpha Beach Entrance", "", True),
    ("City Hall", "Old Tax Office", "", False),                 # the 791E shape
    ("City Hall", "City Hall Station", "", False),              # a building is not a natural feature
    ("Alpha Mountain", "Beta Mountain Cable Car Station", "", False),
    ("Alpha Mountain", "Alpha Mountain Pagoda", "", False),     # no facility word
])
def test_facility_of_same_place(title, ref, typ, ok):
    assert pf.facility_of_same_place(title, ref, typ) is ok


def _live_reference(monkeypatch, table):
    """Make the live generic geocoder path return ``table[title]`` = (lat, lng, source, ref_name)."""
    monkeypatch.setattr(pin_snap, "_landmark_reference", lambda *a, **k: None)
    monkeypatch.setattr(pin_snap, "_default_reference", lambda name, scope, ctr: table.get(name))


def test_city_hall_shape_is_still_refused_even_with_a_province_box(monkeypatch):
    _live_reference(monkeypatch, {"City Hall": (10.9, 108.1, "serper", "Old Tax Office")})
    row = pin_snap.snap_pin("City Hall", (10.95, 108.12), scope=PROVINCE, scope_center=None,
                            province_box=BOX, stop_type="Landmark")
    assert not row["snapped"] and "does not match stop" in row["reason"]
    # and without the box the facility case is refused too (the 791E behaviour is unchanged)
    _live_reference(monkeypatch, {"Alpha Mountain": (*FACILITY, "serper", "Alpha Cable Car Station")})
    row = pin_snap.snap_pin("Alpha Mountain", MODEL_PIN_1, scope=PROVINCE, scope_center=None)
    assert not row["snapped"] and "does not match stop" in row["reason"]


def test_facility_reference_outside_the_box_is_refused(monkeypatch):
    _live_reference(monkeypatch, {"Alpha Mountain": (12.5, 109.5, "serper", "Alpha Cable Car Station")})
    row = pin_snap.snap_pin("Alpha Mountain", MODEL_PIN_1, scope=PROVINCE, scope_center=None,
                            province_box=BOX, stop_type="Mountain")
    assert not row["snapped"] and "does not match stop" in row["reason"]


# ── 4/5. the pin chain replay ────────────────────────────────────────────────────────────────────────────
def _tour():
    return [{"name": "Alpha Mountain", "coordinates": f"{MODEL_PIN_1[0]}, {MODEL_PIN_1[1]}", "type": "Mountain",
             "address": "Alpha Mountain, Wrong District, Beta Province, Gamma"},
            {"name": "Beta Statue", "coordinates": f"{MODEL_PIN_2[0]}, {MODEL_PIN_2[1]}", "type": "Statue",
             "address": "Beta Statue, Wrong District, Beta Province, Gamma"}]


def test_pin_chain_replay_facility_accepted_both_pins_inside_tour_pin_follows(monkeypatch, capsys):
    _live_reference(monkeypatch, {"Alpha Mountain": (*FACILITY, "serper", "Alpha Cable Car Station")})
    pois, logs = _tour(), []
    pf.flag_far_pins(pois, BOX, PROVINCE, log=logs.append)
    assert [x for x in logs if "stop=1 model pin outside" in x] and [x for x in logs if "stop=2 model pin outside" in x]
    pois, rows = pin_snap.snap_poi_coordinates(pois, scope=PROVINCE, scope_center=None, scope_bbox=BOX,
                                               coarse_center=CENTRE, province_box=BOX, log=logs.append)
    logs += capsys.readouterr().out.splitlines()
    assert any("[LOCAL-906D] approximate reference 'Alpha Cable Car Station' accepted for "
               "'Alpha Mountain' (facility of the same place)" in x for x in logs), logs
    assert pin_snap._poi_coord(pois[0]) == pytest.approx(FACILITY, abs=1e-5)
    assert pois[0]["coordinates_approximate"] and pois[0]["_pin_approx_facility_906d"]
    assert pf.in_box(pin_snap._poi_coord(pois[1]), BOX) is False    # stop 2 has no reference: still far
    moved = pf.last_resort_pins(pois, rows, BOX, CENTRE, PROVINCE, log=logs.append)
    assert moved == [1]
    assert pin_snap._poi_coord(pois[1]) == pytest.approx(FACILITY, abs=1e-5)   # the other stop's in-province reference
    assert all(pf.in_box(pin_snap._poi_coord(p), BOX) for p in pois)
    assert sp.tour_pin(pois, (None, None)) == pytest.approx(FACILITY, abs=1e-5)  # the tour pin follows stop 1
    # item 5: the district the box cannot confirm is dropped, the province and country stay
    for p in pois:
        pf.address_follows_pin(p, PROVINCE, COUNTRY, log=logs.append)
    assert pois[0]["address"] == "Alpha Mountain, Beta Province, Gamma"
    assert pois[1]["address"] == "Beta Statue, Beta Province, Gamma"


def test_last_resort_with_no_reference_at_all_moves_to_the_province_centre_flagged():
    pois, logs = _tour(), []
    rows = [{"snapped": False, "reference": None}, {"snapped": False, "reference": None}]
    moved = pf.last_resort_pins(pois, rows, BOX, CENTRE, PROVINCE, log=logs.append)
    assert moved == [0, 1]
    for p in pois:
        assert pin_snap._poi_coord(p) == pytest.approx(CENTRE, abs=1e-5)
        assert p["coordinates_approximate"] and p["_pin_province_centre_906d"]
    assert any("moved to the Beta Province centre" in x and "(approximate)" in x for x in logs)
    assert sp.tour_pin(pois, (None, None)) == pytest.approx(CENTRE, abs=1e-5)


def test_last_resort_leaves_verified_and_in_province_pins_alone():
    pois = [{"name": "A", "coordinates": "11.0, 108.2"},
            {"name": "B", "coordinates": "11.47, 107.52", "coord_source": "user_share_link"},
            {"name": "C", "coordinates": "11.47, 107.52", "wikidata_lat": 11.47, "wikidata_lng": 107.52}]
    assert pf.last_resort_pins(pois, [{}, {}, {}], BOX, CENTRE, PROVINCE, log=lambda m: None) == []


def test_address_keeps_a_part_the_reverse_geocode_of_the_new_pin_confirms():
    p = {"name": "Alpha Mountain", "address": "Alpha Mountain, Right District, Beta Province, Gamma",
         "coordinates": "11.0, 108.3", "_pin_moved_906d": True}
    changed = pf.address_follows_pin(p, PROVINCE, COUNTRY, reverse_fn=lambda la, lo: "Right District, Beta Province, Gamma")
    assert not changed and p["address"] == "Alpha Mountain, Right District, Beta Province, Gamma"


def test_address_untouched_when_the_pin_did_not_move():
    p = {"name": "Alpha Mountain", "address": "Alpha Mountain, Wrong District, Beta Province, Gamma",
         "coordinates": "11.0, 108.3"}
    assert not pf.address_follows_pin(p, PROVINCE, COUNTRY)
    assert "Wrong District" in p["address"]


# ── 6. the same event twice ──────────────────────────────────────────────────────────────────────────────
A = ("In 1872, Master Thien Tam, a revered Zen sage with the Dharma name Tue Quang, chose Mount Alpha for "
     "seclusion.")
B = ("In 1872, Master Thien Tam quietly made his way up Mount Alpha, which at that time was an untouched, "
     "wild forest.")
TITLE = "Mount Alpha"


def test_same_event_with_few_shared_words_is_one_fact():
    assert rc.same_event(A, B, TITLE)
    assert rc.same_fact(A, B, TITLE)


def test_two_different_events_in_the_same_year_are_not_one_fact():
    other_person = "In 1872, French engineers cut a road across Mount Alpha for the colonial administration."
    other_event_no_place = "In 1872, Master Thien Tam founded a school in a distant valley."
    other_year = "In 1901, Master Thien Tam returned to Mount Alpha and built a small hermitage."
    for x in (other_person, other_event_no_place, other_year):
        assert not rc.same_fact(A, x, TITLE), x


def test_duplicate_pass_keeps_the_more_specific_sentence():
    text = ("TOUR\n\nStop 1: Mount Alpha\n" + A + " " + B + " The summit is 600 metres high.\n")
    out = rc.drop_within_stop_duplicates(text, log=lambda m: None, evidence_by_title={})
    assert (A in out) != (B in out), out                          # exactly one of the pair stays
    assert B not in out or rc.specificity(B) >= rc.specificity(A)
    assert "The summit is 600 metres high." in out


def test_refill_ok_never_appends_the_same_event():
    # the refill's ok() uses same_fact(x, h, title) for every kept sentence: the premise is the predicate itself
    kept = [A]
    assert any(rc.same_fact(B, h, TITLE) for h in kept)
