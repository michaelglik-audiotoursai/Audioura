"""LOCAL-900 -- wave 46 leftovers: short Directions names, filler tail, kind-aware honest body, superlative
conflicts, unsupported measurements, mood filler, pin check on short tours. Generic fixtures, offline, $0."""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import place_names_900 as pn  # noqa: E402
import route_content_896 as rc  # noqa: E402

INFO = {"is_description": True, "origin": "Alpha Lodge", "destination": "Gamma Mountain",
        "through": ["Sigma Town"], "region": "Kappa province", "origin_locality": "Alpha Quarter"}


@pytest.fixture(autouse=True)
def _route():
    rc.set_route(INFO)
    rc._POINTS.clear()
    yield
    rc.clear_route()
    rc._POINTS.clear()


def _stops(*specs):
    out = []
    for i, (title, pin, typ, body, dirs) in enumerate(specs, 1):
        out.append(f"Stop {i}: {title}\nCoordinates: {pin}\nType/Specialty: {typ}\n{body}\n"
                   + (f"Directions: {dirs}\n" if dirs else ""))
    return "\n".join(out)


# ── 1 short names ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,short", [
    ("Arriving at Gamma – the mountain and its legends", "Gamma"),
    ("The summit views and the drive home", "the summit views"),
    ("Leaving Alpha Bay - the fishing coast", "Alpha Bay"),
    ("Driving to Foo Lake: a quiet start", "Foo Lake"),
    ("The old market and back", "the old market"),
    ("Omega Pagoda", "Omega Pagoda"),
])
def test_short_place_name(raw, short):
    assert pn.short_place_name(raw) == short


def test_directions_use_short_names():
    t = _stops(("Alpha Lodge", "1.0, 1.0", "Hotel", "Body of the first stop is here.", "Continue to Arriving at Gamma. Lovely!"),
               ("Arriving at Gamma – the mountain and its legends", "1.5, 1.5", "Mountain", "Body two is here for sure.",
                "Walk on to whatever."),
               ("The summit views and the drive home", "1.5, 1.5", "Viewpoint", "Body three is here.", None))
    out = rc.normalize_directions(t)
    assert "Directions: Continue to Gamma. It is roughly" in out
    assert "Directions: Walk on to the summit views." in out


# ── 2 filler tail ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("tail", ["It's a lovely spot to explore!", "A beautiful place, worth exploring.",
                                  "What a great spot!", "Enjoy the stop!"])
def test_filler_tail_dropped(tail):
    t = _stops(("Omega Pagoda", "1.0, 1.0", "Temple", "Body one is long enough.", f"Walk on to Delta Hall. {tail}"),
               ("Delta Hall", "1.0, 1.0", "Hall", "Body two is long enough.", None))
    out = rc.normalize_directions(t)
    assert "Directions: Walk on to Delta Hall.\n" in out and "!" not in out and "lovely" not in out


def test_scenery_clause_is_dropped_wayfinding_survives():
    # [LOCAL-906] item 3: a scenery sentence is no longer kept; a wayfinding one (a landmark to look for) is
    t = _stops(("A", "1.0, 1.0", "x", "Body one is long enough.", "Continue to Beta Hall. Notice the rice paddies along the way."),
               ("Beta Hall", "1.0, 1.0", "Hall", "Body two is long enough.", None))
    assert "rice paddies" not in rc.normalize_directions(t)
    t2 = t.replace("Notice the rice paddies along the way.", "Look for the red gate.")
    assert "Look for the red gate." in rc.normalize_directions(t2)


# ── 3 honest body ───────────────────────────────────────────────────────────
def test_kinds():
    assert pn.stop_kind("The cable car ascent", "Cable car ride") == "height"
    assert pn.stop_kind("Beta Pagoda", "Buddhist temple") == "worship"
    assert pn.stop_kind("Plantations along the road", "Agricultural area") == "road"
    assert pn.stop_kind("Alpha Bay", "Coastal area") == "neutral"


def test_sensory_body_no_road_on_summit_and_short_name():
    import strict_grounding_gate as sgg
    out = " ".join(sgg.sensory_body("The summit views and the drive home", [sgg.NO_HISTORY_DISCLOSURE], 3,
                                    register="driving", kind_text="Scenic viewpoint"))
    assert "road" not in out and "fields" not in out and "drive home" not in out and "the summit views" in out
    road = " ".join(sgg.sensory_body("Fruit plantations along the road", [sgg.NO_HISTORY_DISCLOSURE], 4,
                                     register="driving", kind_text="Agricultural area"))
    assert "road and the fields" in road


def test_honest_body_does_not_borrow_a_sentence_the_tour_already_delivers():
    # [LOCAL-906] item 5: the same-site neighbour sentence IS a repeat of the neighbour's delivered body (wave 51 heard
    # it in Stops 4 and 5), so the honest body no longer borrows it.
    import strict_grounding_gate as sgg
    honest = " ".join(sgg.sensory_body("x", [sgg.NO_HISTORY_DISCLOSURE], 3, register="driving"))
    t = _stops(("Gamma Peak", "5.0, 5.0", "Mountain", "A modern cable car carries visitors up to the top of the peak. Hiking is possible too.", "Continue to The cable car ascent."),
               ("The cable car ascent", "5.0, 5.0", "Cable car ride",
                "As you pass the cable car ascent, look out at the road. " + sgg.NO_HISTORY_DISCLOSURE, "Walk on to Far Place."),
               ("Far Place", "6.0, 6.0", "Hall", "Body of the far place is here.", None))
    ev = {"Gamma Peak": "A modern cable car carries visitors up to the top of the peak. Hiking is possible too.",
          "The cable car ascent": "", "Far Place": ""}
    out = rc.rebuild_honest_bodies(t, ev)
    blk = out.split("Stop 3")[0].split("Stop 2")[1]
    assert "A modern cable car carries visitors up to the top of the peak." not in blk and "road" not in blk
    assert "We could not confirm" in blk
    # a stop at another site does not borrow
    t2 = t.replace("5.0, 5.0\nType/Specialty: Cable", "9.0, 9.0\nType/Specialty: Cable")
    assert "modern cable car carries" not in rc.rebuild_honest_bodies(t2, ev).split("Stop 2")[1]
    assert honest


# ── 4 superlatives, measurements ────────────────────────────────────────────
SUP = _stops(
    ("Gamma Mountain", "1.0, 1.0", "Mountain",
     "The statue is 20 meters long and the longest reclining Buddha statue in Asia. A stair climbs the slope.", None),
    ("The Reclining Buddha", "1.0, 1.0", "Statue",
     "It is the biggest reclining Buddha statue in Zedland. Pilgrims walk around it.", None))


def test_superlative_both_supported_keeps_titled_stop():
    ev = {"Gamma Mountain": "Gamma has the longest reclining Buddha statue in Southeast Asia and a stair.",
          "The Reclining Buddha": "the biggest reclining Buddha in Zedland"}
    out = rc.consistent_superlatives(SUP, ev)
    assert "longest" not in out and "biggest reclining Buddha statue in Zedland" in out
    # [LOCAL-900B] the whole sentence goes, never a clause ("The statue is 20 meters long and ..." leaves no stub)
    assert "20 meters long" not in out and "A stair climbs the slope." in out


def test_superlative_only_one_supported():
    ev = {"Gamma Mountain": "a stair", "The Reclining Buddha": "the biggest reclining Buddha in Zedland"}
    out = rc.consistent_superlatives(SUP, ev)
    assert "longest" not in out and "biggest" in out
    ev = {"Gamma Mountain": "Gamma has the longest reclining Buddha statue in Southeast Asia", "The Reclining Buddha": "x"}
    out = rc.consistent_superlatives(SUP, ev)
    assert "longest" in out and "biggest" not in out


def test_superlative_neither_supported_drops_both():
    out = rc.consistent_superlatives(SUP, {"Gamma Mountain": "a stair", "The Reclining Buddha": "pilgrims"})
    assert "longest" not in out and "biggest" not in out and "Pilgrims walk around it." in out


def test_same_superlative_twice_is_not_a_conflict():
    t = SUP.replace("biggest", "largest").replace("longest", "largest").replace("in Zedland", "in Asia")
    assert rc.consistent_superlatives(t, {"Gamma Mountain": "", "The Reclining Buddha": ""}) == t


def test_unsupported_measurement_dropped_supported_kept():
    t = _stops(("Omega Pagoda", "1.0, 1.0", "Temple",
                "The pagoda sits 475 meters up on the hill, and you can reach it by cable car. The hall is 12 meters wide.", None))
    out = rc.cap_unsupported_numbers(t, {"Omega Pagoda": "The pagoda is at 400 meters. The hall is 12 meters wide."})
    assert "475" not in out and "You can reach it by cable car." in out and "12 meters wide" in out
    # no evidence entry -> untouched
    assert rc.cap_unsupported_numbers(t, {"Other": "x"}) == t


# ── 5 mood filler ───────────────────────────────────────────────────────────
def test_mood_filler_with_only_a_place_type_noun_in_common_is_dropped():
    t = _stops(("Sigma Town and the Delta River", "1.0, 1.0", "River",
                "The Delta River is about 7 kilometers long. This is where the pulse of the city meets the steady rhythm of the river.",
                None))
    ev = {"Sigma Town and the Delta River": "The Delta River is about 7 kilometers long and runs through the city."}
    out = rc.cap_unsupported(t, ev)
    assert "pulse of the city" not in out and "7 kilometers long" in out


# ── 6 pins ──────────────────────────────────────────────────────────────────
def test_pin_check_replaces_far_pin_keeps_near():
    logs = []
    stops = [{"name": "A", "coordinates": "10.8784, 107.3067"}, {"name": "B", "coordinates": "10.8130, 107.8940"}]
    n = pn.check_pins_against_scope(stops, (10.8133, 107.8941), "DISTRICT", log=logs.append)
    assert n == 1
    assert stops[0]["coordinates"] == "10.813300, 107.894100" and stops[0]["coordinates_approximate"]
    assert stops[1]["coordinates"] == "10.8130, 107.8940" and "coordinates_approximate" not in stops[1]
    assert re.search(r"\[LOCAL-900\] pin check stop=1 dist_km=\d+\.\d action=replaced", logs[0])
    assert "stop=2" in logs[1] and "action=kept" in logs[1]


def test_pin_check_city_radius_wider_than_district():
    near20 = {"coordinates": "10.0, 10.18"}                       # ~19.7 km east
    d, c = [dict(near20)], [dict(near20)]
    assert pn.check_pins_against_scope(d, (10.0, 10.0), "DISTRICT") == 1
    assert pn.check_pins_against_scope(c, (10.0, 10.0), "CITY") == 0


def test_pin_check_no_scope_center_is_noop():
    s = [{"coordinates": "1.0, 1.0"}]
    assert pn.check_pins_against_scope(s, None, "DISTRICT") == 0 and s[0]["coordinates"] == "1.0, 1.0"


# ── replay of the wave 46 cloud tour ────────────────────────────────────────
def test_replay_local900_tour():
    with open(os.path.join(ROOT, "tests", "fixtures", "local900_tour.txt"), encoding="utf-8") as f:
        t = f.read()
    titles = [m.group(1) for m in re.finditer(r"(?m)^Stop \d+: (.+)$", t)]
    ev = {titles[1]: "The Delta River, about 7.2 kilometers long, was once called the Sigma River. In 1825 Kappa became a province.",
          titles[3]: ("Gamma Mountain stands 649 meters above sea level and has the longest reclining Buddha statue in Southeast Asia. "
                      "A modern cable car designed to transport visitors runs up. You can hike through the forest."),
          titles[5]: "Omega Pagoda sits at an elevation of 400 meters on the mountain.",
          titles[6]: "The Reclining Buddha is 49 meters long, the biggest reclining Buddha in Zedland.",
          titles[0]: "", titles[2]: "", titles[4]: "", titles[7]: ""}
    out = rc.finalize_898(rc.cap_unsupported(t, ev), ev)
    for ln in re.findall(r"(?m)^Directions:.*$", out):
        assert "Arriving at" not in ln and " – " not in ln and "!" not in ln and "lovely" not in ln
    assert "Directions: Continue to Gamma." in out and "Walk on to the summit views." in out
    for s, e, n, title in rc._stop_blocks(out):
        body = out[s:e]
        if n in (1, 4, 5, 6, 7, 8):
            assert "road and the fields" not in body, n
    assert "pulse of the city" not in out
    assert len(re.findall(r"(?i)\b(?:longest|biggest|largest)\b[^.]*reclining Buddha", out)) <= 1
    assert "475" not in out
