"""[LOCAL-906Q] A-to-B scope is the corridor, hollow refill up to N, first leg from the origin, copy patterns. $0, generic names (D769)."""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SERPER_API_KEY", None)
os.environ["THIN_STOP_SEARCH"] = "0"

import route_content_896 as rc  # noqa: E402
import route_copy_906q as cp  # noqa: E402
import route_order_909 as r909  # noqa: E402
import route_scope_906q as rs  # noqa: E402

SRC = open(os.path.join(ROOT, "generate_tour_text.py"), encoding="utf-8").read()
BOX = [10.0, 12.0, 105.0, 107.0]            # [south, north, west, east]


@pytest.fixture(autouse=True)
def _job():
    r909.clear()
    with rc.job_scope("t906q"):
        r909.set_request("Origin Town to Alpha Peak, Beta Province, Gamma", "vehicle")
        r909._STATE["corridor_box_906q"] = list(BOX)
        yield
    r909.clear()


# ── 1. scope ──────────────────────────────────────────────────────────────────────────────────────────────
def test_corridor_has_origin_destination_region_box():
    c = rs.corridor(compute_box=False)
    assert (c["origin"], c["destination"], c["region"]) == ("Origin Town", "Alpha Peak", "Beta Province, Gamma")
    assert c["box"] == BOX
    assert "Origin Town" in rs.label(c) and "Alpha Peak" in rs.label(c)


def test_stop_inside_box_or_naming_region_is_in_scope_outside_is_not():
    c = rs.corridor()
    assert rs.stop_in_corridor({"name": "Stream", "coordinates": "10.5, 105.5"}, c)
    assert rs.stop_in_corridor({"name": "Stream", "address": "Road 1, Beta Province, Gamma"}, c)
    assert not rs.stop_in_corridor({"name": "Far", "coordinates": "20.0, 120.0", "address": "Elsewhere City"}, c)


def test_not_a_route_has_no_corridor_and_records():
    r909.clear()
    assert rs.corridor(compute_box=False) is None
    assert rs.may_record(None) and not rs.may_record({"origin": "A"})


def _validate(monkeypatch, pois, verdict):
    import generate_tour_text as g
    recorded = []
    import scope_memory as sm
    monkeypatch.setattr(sm, "record_out_of_scope", lambda *a, **k: recorded.append(a) or (True, {}))
    monkeypatch.setattr(sm, "known_out_of_scope", lambda n, s: (True, "stored: outside"))

    class R:
        status_code = 200

        def json(self):
            import json
            return {"choices": [{"message": {"content": json.dumps(verdict)}}]}
    monkeypatch.setattr(g.requests, "post", lambda *a, **k: R())
    out = g._validate_stops_within_scope(pois, "Alpha Peak, Beta Province, Gamma", {}, protect_first=False)
    return [p["name"] for p in out], recorded


def test_on_route_stop_stays_despite_stored_entry_and_outside_stop_removed_without_memory(monkeypatch):
    pois = [{"name": "Stream", "address": "x", "coordinates": "10.5, 105.5"},
            {"name": "Far Place", "address": "Elsewhere", "coordinates": "20.0, 120.0"}]
    kept, recorded = _validate(monkeypatch, pois,
                               {"inside_scope": False, "confidence": "high", "reason": "outside the route"})
    assert kept == ["Stream"]
    assert recorded == []                       # a route rejection is never written to scope memory


# ── 2. hollow refill ──────────────────────────────────────────────────────────────────────────────────────
def test_hollow_refill_is_wired_before_all_hollow_fallback():
    i = SRC.index("[LOCAL-906Q] Fewer than the requested count survived")
    blk = SRC[i:i + 1400]
    assert "0 < len(poi_list) < _n906q" in blk and "hollow refill: {_k906q}" in blk and "_q906_norm" in blk
    assert i < SRC.index("if len(poi_list) == 0 and _hollow_fallback_lead910:")


# ── 3. first leg ──────────────────────────────────────────────────────────────────────────────────────────
TOUR = ("Stop 1: Lighthouse\n\nOrientation: Your first stop is Lighthouse. From Alpha Peak, head northeast on DT719 for, "
        "then turn left at the gate.\n\nCoordinates: 10.5, 105.5\n\nBody sentence one is here.\n\n"
        "Directions: From Alpha Peak, head northeast on DT719 for, then turn left.\n\n"
        "Stop 2: Alpha Peak\n\nOrientation: Arrive.\n\nCoordinates: 11.5, 106.5\n\nBody.\n\nDirections: Drive on for 3 km.\n\n")


def test_first_orientation_and_directions_start_at_origin_and_for_comma_dropped():
    out = r909.first_leg_from_origin(TOUR, "Origin Town", "Alpha Peak", (10.0, 105.0))
    out = r909.origin_directions(out, "Origin Town", (10.0, 105.0))
    s1 = out[:out.index("Stop 2")]
    assert "From Alpha Peak" not in s1 and "for, then" not in s1
    ori = re.search(r"Orientation:[^\n]*", s1).group(0)
    dire = re.search(r"Directions:[^\n]*", s1).group(0)
    assert "Origin Town" in ori and "Origin Town" in dire
    assert "Drive on for 3 km" in out                  # a good direction sentence is kept


def test_finalize_text_runs_it():
    out = r909.finalize_text(TOUR)
    assert "for, then" not in out and "From Alpha Peak, head" not in out


def test_dangling_for_dropped_elsewhere_good_for_kept():
    t = "Stop 1: X\n\nOrientation: Go.\n\nDirections: Drive for, then turn. Continue for 5 km.\n\n"
    out = cp.drop_dangling_for(t)
    assert "for, then" not in out and "Continue for 5 km." in out


# ── 4. copy ───────────────────────────────────────────────────────────────────────────────────────────────
def one(sentence, title="Alpha Pagoda", keep="The pagoda was built in 1950."):
    return f"Stop 1: {title}\n\nOrientation: Here.\n\nCoordinates: 1, 1\n\n{keep} {sentence} Another fact stands here.\n\nDirections: Go.\n\n"


@pytest.mark.parametrize("sentence", [
    "You can find some of the best seafood in Gamma here at Blue Fin restaurant, right on the banks of the Long River.",
    "Try the noodles at Golden Bowl café, just down the road.",
    "Alpha Pagoda is part of a popular full-day trip that also includes the lake and the market.",
    "Many visitors come here in the morning and then take the cable car to the summit.",
    "Tours from Origin Town often include a stop at the pagoda.",
    "Beta Beach is considered a resort paradise along with Delta Bay and attracts tourists from all over the world.",
    "The mountain's presence extends beyond its spiritual and artistic significance.",
])
def test_each_copy_pattern_dropped_and_fact_kept(sentence):
    out = cp.run_pass(one(sentence))
    assert sentence not in out
    assert "The pagoda was built in 1950." in out and "Another fact stands here." in out


def test_restaurant_plug_kept_when_stop_is_that_venue():
    s = "You can find some of the best seafood here at Blue Fin restaurant."
    assert s in cp.run_pass(one(s, title="Blue Fin Restaurant"))


def test_filler_with_a_fact_is_kept():
    s = "The mountain's presence extends beyond its spiritual significance, supplying 2 million liters of water a year."
    assert s in cp.run_pass(one(s))


def test_two_communes_keeps_the_one_in_evidence():
    near = "The site lies near Aville on a hill."
    loc = "It is located in Bville commune."
    t = one(near + " " + loc)
    out = cp.two_communes(t, {"Alpha Pagoda": "The Alpha Pagoda is in Bville commune, built in 1950."})
    assert loc in out and near not in out
    out2 = cp.two_communes(t, {"Alpha Pagoda": "Aville is where the site stands."})
    assert near in out2 and loc not in out2
    assert cp.two_communes(t, {"Alpha Pagoda": "Nothing relevant."}) == t


def test_wired_in_leftovers():
    assert "route_copy_906q" in open(os.path.join(ROOT, "leftovers_906f.py")).read()
