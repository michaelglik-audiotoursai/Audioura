"""LOCAL-900B -- wave 47 cloud failures. Generic fixtures (place names replaced), offline, $0.

A  pin check: a province-centroid reference must never replace a place pin; a place-level one may.
A  791C snap: a same-named place far away (876 km) is rejected; an in-scope snap still lands.
A  single-place Directions: normalized, a leg over 100 km is a pin bug (no distance), filler closer dropped.
B  superlative / comparative drop removes the WHOLE sentence; no body sentence is a fragment.
B  honest body: the neighbour-supported sentence survives finalize_898 + the gate's sensory_body, any number of times.
B  unsupported years / creators / measurements on user-list stops are capped.
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pin_snap  # noqa: E402
import place_names_900 as pn  # noqa: E402
import route_content_896 as rc  # noqa: E402
import strict_grounding_gate as sgg  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
INFO = {"is_description": True, "origin": "Alpha Lodge", "destination": "Gamma Mountain",
        "through": ["Sigma Town"], "region": "Kappa province", "origin_locality": "Alpha Bay"}


def _fx(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def route():
    rc.set_route(INFO)
    rc._POINTS.clear()
    rc._HONEST_DONE.clear()
    yield
    rc.clear_route()
    rc._POINTS.clear()


def _titles(t):
    return [m.group(1) for m in re.finditer(r"(?m)^Stop \d+: (.+)$", t)]


def _evidence(t):
    ti = _titles(t)
    return {ti[3]: "Gamma Mountain is an extinct volcano. You can take a modern cable car designed to transport "
                   "visitors up the mountain. Omega Pagoda and Lambda pagoda stand at the top.",
            ti[5]: "Omega Pagoda sits on Gamma Mountain.",
            ti[6]: "The Reclining Buddha at Omega Pagoda is 49 meters long, the largest reclining Buddha in Zedland.",
            **{ti[i]: "" for i in (0, 1, 2, 4, 7)}}


# ── A. pin check reference ──────────────────────────────────────────────────
SITE = (10.81, 107.89)
PROVINCE = (11.083333, 108.083333)          # ~35 km from the site


def _two_stops():
    # the model's own pins: ~44 km and ~31 km from the province centroid, i.e. at the real site area
    return [{"name": "Gamma Mountain", "coordinates": "10.8133, 107.8941"},
            {"name": "Reclining Statue", "coordinates": "10.8130, 107.8940"}]


@pytest.mark.parametrize("prec", ["region", "province", "city", "district", "country", "unknown", ""])
def test_coarse_reference_keeps_pins(prec):
    logs = []
    stops = _two_stops()
    n = pn.check_pins_against_scope(stops, PROVINCE, "DISTRICT", log=logs.append, ref_precision=prec,
                                    ref_source="area_resolver")
    assert n == 0
    assert stops[0]["coordinates"] == "10.8133, 107.8941" and "coordinates_approximate" not in stops[0]
    assert sum("action=skipped_coarse_ref" in x for x in logs) == 2
    assert not any("action=replaced" in x for x in logs)
    ref_line = logs[-1]
    assert "pin check reference" in ref_line
    assert f"precision={prec or 'unknown'}" in ref_line and "source=area_resolver" in ref_line


def test_place_level_reference_44km_away_replaces():
    logs = []
    stops = [{"name": "A", "coordinates": "11.2000, 108.2000"}]            # far from the place
    n = pn.check_pins_against_scope(stops, SITE, "DISTRICT", log=logs.append, ref_precision="place",
                                    ref_source="destination_geocode")
    assert n == 1 and stops[0]["coordinates"] == "10.810000, 107.890000" and stops[0]["coordinates_approximate"]
    assert any(re.search(r"dist_km=\d+\.\d action=replaced", x) for x in logs)


def test_stop_verified_coordinate_is_a_place_level_reference_even_with_a_coarse_centre():
    stops = [{"name": "A", "coordinates": "11.2000, 108.2000", "wikidata_lat": 10.81, "wikidata_lng": 107.89},
             {"name": "B", "coordinates": "11.2000, 108.2000"}]
    n = pn.check_pins_against_scope(stops, PROVINCE, "DISTRICT", ref_precision="region")
    assert n == 1
    assert stops[0]["coordinates"] == "10.810000, 107.890000"
    assert stops[1]["coordinates"] == "11.2000, 108.2000"                   # no verified reference of its own


def test_552_replay_pin_log_shape():
    """The wave 47 log: both pins 44.0 / 31.6 km from a province centroid -> kept, not moved to it."""
    stops = [{"name": "Gamma Mountain", "coordinates": "10.8133, 107.5000"},
             {"name": "Reclining Statue", "coordinates": "10.8130, 107.6100"}]
    logs = []
    pn.check_pins_against_scope(stops, PROVINCE, "DISTRICT", log=logs.append, ref_precision="region",
                                ref_source="area_resolver('Kappa')")
    assert all(s["coordinates"] != "11.083333, 108.083333" for s in stops)
    assert sum("skipped_coarse_ref" in x for x in logs) == 2


# ── A. 791C snap guard ──────────────────────────────────────────────────────
def _snap(stops, ref, **kw):
    logs = []
    # no scope centre: the older centre-based bounds are dark (as in the cloud run), only the 900B guard is left
    rows = pin_snap.snap_poi_coordinates(stops, scope="Kappa", scope_center=None, reference_fn=lambda n: ref,
                                         log=logs.append, **kw)[1]
    return rows, logs


def test_snap_876km_away_is_rejected():
    stop = {"name": "Reclining Statue", "coordinates": "10.8133, 107.8941"}
    rows, logs = _snap([stop], (13.748056, 100.491111, "wikidata_p625"), scope_precision="DISTRICT")
    assert stop["coordinates"] == "10.8133, 107.8941" and not rows[0]["snapped"]
    assert any(re.search(r"\[LOCAL-900B\] snap rejected Reclining Statue \d+m \(outside scope\)", x) for x in logs)
    assert not any("pin snap Reclining Statue" in x and "→" in x for x in logs)


def test_snap_to_the_stops_own_wikidata_p625_in_another_country_is_rejected():
    stop = {"name": "Reclining Statue", "coordinates": "10.8133, 107.8941",
            "wikidata_lat": 13.748056, "wikidata_lng": 100.491111}
    logs = []
    rows = pin_snap.snap_poi_coordinates([stop], scope="Kappa", scope_center=None, log=logs.append,
                                         scope_precision="DISTRICT")[1]
    assert not rows[0]["snapped"] and stop["coordinates"] == "10.8133, 107.8941"
    assert any("[LOCAL-900B] snap rejected Reclining Statue 8" in x and "(outside scope)" in x for x in logs)


def test_snap_inside_scope_still_lands():
    stop = {"name": "Reclining Statue", "coordinates": "10.8133, 107.8941"}
    rows, logs = _snap([stop], (10.8150, 107.8960, "serper"), scope_precision="DISTRICT")
    assert rows[0]["snapped"] and stop["coordinates"] == "10.815000, 107.896000"


@pytest.mark.parametrize("prec,km,ok", [("DISTRICT", 14, True), ("DISTRICT", 16, False), ("CITY", 24, True),
                                        ("CITY", 26, False)])
def test_snap_radius_by_scope(prec, km, ok):
    d = km / 111.0
    stop = {"name": "Foo Shrine", "coordinates": "10.0, 10.0"}
    rows, _ = _snap([stop], (10.0 + d, 10.0, "wikidata_p625"), scope_precision=prec)
    assert bool(rows[0]["snapped"]) is ok


def test_snap_on_a_route_is_bounded_by_the_route_box_plus_10km():
    box = [10.0, 11.0, 107.0, 108.0]
    s_in = {"name": "Foo Shrine", "coordinates": "10.5, 107.5"}
    rows, _ = _snap([s_in], (10.5, 108.05, "wikidata_p625"), route_box=box, scope_precision="CITY")   # 5 km out
    assert rows[0]["snapped"]
    s_out = {"name": "Foo Shrine", "coordinates": "10.5, 107.5"}
    rows, logs = _snap([s_out], (10.5, 108.30, "wikidata_p625"), route_box=box, scope_precision="CITY")   # ~30 km
    assert not rows[0]["snapped"] and s_out["coordinates"] == "10.5, 107.5"
    assert any("[LOCAL-900B] snap rejected Foo Shrine" in x for x in logs)


# ── A. single-place Directions, filler closer, orientation fragment ─────────
def test_552_replay_single_place_path():
    t = _fx("local900b_tour552.txt")
    logs = []
    out = rc.apply_single_place_guards(t, logs.append)
    d1 = re.search(r"(?m)^Directions:.*$", out).group(0)
    assert d1 == "Directions: Continue to Reclining Buddha Statue."
    assert "leisurely" not in out and "hard to miss" not in out and "876" not in out
    assert any("BUG SIGNAL" in x and "100 km" in x for x in logs)
    assert "carry with you" not in out
    assert "covers of" not in out
    # [LOCAL-906] item 7: the template closing filler goes; the count line stays
    assert "That's 2 stops in all." in out and "Across these stops, one thread runs through" not in out
    # the orientation line keeps its first sentence part? it is ONE fragment sentence -> the line is removed
    assert "Orientation:" not in out


def test_short_leg_on_single_place_tour_is_walk_on():
    t = _fx("local900b_tour552.txt").replace("13.748056, 100.491111", "11.084000, 108.084000")
    out = rc.apply_single_place_guards(t)
    assert "Directions: Walk on to Reclining Buddha Statue." in out


def test_long_tour_directions_are_left_alone_off_route():
    t = ("Stop 1: Foo\nCoordinates: 1.0, 1.0\nDirections: Head north for ten minutes along the lake.\n\n"
         "Stop 2: Bar\nCoordinates: 1.1, 1.1\nDirections: Turn left.\n\n"
         "Stop 3: Baz\nCoordinates: 1.2, 1.2\nBody three is a whole sentence here.\n")
    assert rc.apply_single_place_guards(t) == t


# ── B. fragments ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("x", ["Gamma Mountain is home to.", "This pagoda is home to, measuring 49 meters in length.",
                               "The statue stretches 49 meters in", ", measuring 49 meters in length.",
                               "Measuring 49 meters in length.", "It sits at the edge of the,, lake.",
                               "You arrive by the tram that covers of the ascent."])
def test_is_fragment(x):
    assert rc.is_fragment(x)


@pytest.mark.parametrize("x", ["Gamma Mountain is an extinct volcano near the coast.",
                               "The tram covers most of the ascent.",
                               "Visitors come from near and far, drawn by the legend.",
                               "The pagoda was restored in 1998."])
def test_whole_sentences_are_kept(x):
    assert not rc.is_fragment(x)


def _no_fragments(out):
    for s, e, n, title in rc._stop_blocks(out):
        for ln in out[s:e].split("\n")[1:]:
            if not ln.strip() or rc._KEYED.match(ln):
                continue
            for sent in rc.split_sentences(ln):
                assert not rc.is_fragment(sent), (n, sent)
                assert not re.search(r"(?i)\b(?:to|in|of|at)\.$", sent), (n, sent)
                assert not sent.startswith(","), (n, sent)


def test_replay_local900_tour_has_no_fragments(route):
    t = _fx("local900_tour.txt")
    ti = _titles(t)
    ev = {ti[1]: "The Delta River, about 7.2 kilometers long, was once called the Sigma River.",
          ti[3]: "Gamma Mountain stands 649 meters above sea level and has the longest reclining Buddha statue in "
                 "Southeast Asia.", ti[5]: "Omega Pagoda sits at an elevation of 400 meters on the mountain.",
          ti[6]: "The Reclining Buddha is 49 meters long, the biggest reclining Buddha in Zedland.",
          ti[0]: "", ti[2]: "", ti[4]: "", ti[7]: ""}
    _no_fragments(rc.finalize_898(rc.cap_unsupported(t, ev), ev))


def test_wave47_superlative_sentences_are_dropped_whole(route):
    t = _fx("local900b_tour551_input.txt")
    assert "home to the longest reclining Buddha statue in Southeast Asia." in t
    logs = []
    out = rc.finalize_898(t, _evidence(t), logs.append)
    _no_fragments(out)
    assert "home to" not in out
    assert not re.search(r"(?i)\b(?:to|in)\.\s", out)
    assert sum("conflicting superlative -> sentence dropped" in x for x in logs) >= 2
    assert not any("clause dropped: \"Gamma Mountain is home to" in x for x in logs)


def test_the_fragments_in_the_cloud_output_are_caught_by_the_final_guard(route):
    t = _fx("local900b_tour551.txt")               # verbatim wave 47 output, fragments included
    assert "is home to." in t
    out = rc.drop_fragments(t)
    assert "is home to" not in out
    _no_fragments(out)
    assert "Omega Pagoda is one of two pagodas" in out        # the whole sentences around them stay


def test_a_fragment_guard_never_empties_a_stop(route):
    t = "Stop 1: Foo\nCoordinates: 1.0, 1.0\nFoo is home to.\n\nStop 2: Bar\nCoordinates: 2.0, 2.0\nA whole sentence about Bar.\n"
    assert "Foo is home to." in rc.drop_fragments(t)


# ── B. comparatives ─────────────────────────────────────────────────────────
def test_unsupported_comparative_with_other_places_is_dropped_whole(route):
    t = _fx("local900b_tour551_input.txt")
    ev = _evidence(t)
    out = rc.finalize_898(t, ev)
    assert "larger than" not in out and "Rho Temple" not in out and "Epsilon Temple" not in out
    # supported when the evidence names them
    ti = _titles(t)
    ev2 = dict(ev)
    ev2[ti[6]] += " It is larger than the statues at Rho Temple and Epsilon Temple in Zedland."
    out2 = rc.drop_unsupported_comparatives(t, ev2)
    assert "larger than the reclining Buddha statues at Rho Temple" in out2


# ── B. honest body idempotence ──────────────────────────────────────────────
def _stop_body(out, n):
    s, e, _, _ = next(b for b in rc._stop_blocks(out) if b[2] == n)
    return out[s:e]


def test_neighbour_sentence_survives_every_pass(route):
    t = _fx("local900b_tour551_input.txt")
    ev = _evidence(t)
    # the gate's own honest body for stop 5 first (as the cloud chain builds it)
    gate = " ".join(sgg.sensory_body(_titles(t)[4], [sgg.NO_HISTORY_DISCLOSURE], sgg.MIN_NO_EVIDENCE_SENTENCES - 1,
                                     register="driving"))
    assert gate
    logs = []
    o1 = rc.finalize_898(t, ev, logs.append)
    # [LOCAL-906] item 5: the neighbour sentence is delivered ONCE (in its own stop); Stop 5 keeps its honest body
    assert "You can take a modern cable car to explore the mountain" in _stop_body(o1, 4)
    assert "You can take a modern cable car to explore the mountain" not in _stop_body(o1, 5)
    o2 = rc.finalize_898(o1, None, logs.append)                    # the delivery pass runs without the evidence
    o3 = rc.finalize_898(o2, ev, logs.append)
    assert o1 == o2 == o3
    # [LOCAL-906] item 5: the neighbour sentence is not borrowed (it is Stop 4's), so no pass rebuilds Stop 5 again
    assert sum("Stop 5" in x and "honest body rebuilt" in x for x in logs) <= 1
    assert not any("Stop 5" in x and "neighbour sentence=yes" in x for x in logs)


def test_honest_body_built_without_evidence_gets_the_neighbour_sentence_later(route):
    t = _fx("local900b_tour551_input.txt")
    # [LOCAL-902] the neighbour sentence comes from the neighbour's DELIVERED BODY, so it no longer needs the evidence
    o1 = rc.finalize_898(t, None)
    # [LOCAL-906] item 5: delivered once, in the neighbour's own stop; the later stop keeps its honest body
    assert "You can take a modern cable car to explore the mountain" not in _stop_body(o1, 5)
    o2 = rc.finalize_898(o1, _evidence(t))
    assert "You can take a modern cable car to explore the mountain" not in _stop_body(o2, 5)
    assert _stop_body(o2, 5) and "We could not confirm" in _stop_body(o2, 5)


# ── B. unsupported facts on user-list stops ─────────────────────────────────
def test_year_creator_and_measurement_not_in_the_evidence_are_capped(route):
    t = _fx("local900b_tour551_input.txt")
    logs = []
    ev = _evidence(t)
    out = rc.cap_unsupported_facts(rc.cap_unsupported_numbers(t, ev, logs.append), ev, logs.append)
    b7 = _stop_body(out, 7)
    assert "1963" not in b7 and "Tau Upsilon" not in b7 and "11 meters" not in b7
    assert "You see the Reclining Buddha statue here at Omega Pagoda." in b7
    assert "1963" not in rc.finalize_898(t, ev)
    assert any("'1963' not in the evidence" in x for x in logs)
    assert any("measurement '11 meters' not in the evidence" in x for x in logs)


def test_year_and_creator_in_the_evidence_are_kept(route):
    t = _fx("local900b_tour551_input.txt")
    ev = _evidence(t)
    ev[_titles(t)[6]] += " It was built in 1963 by sculptor Tau Upsilon. It is 11 meters high."
    b7 = _stop_body(rc.cap_unsupported_facts(rc.cap_unsupported_numbers(t, ev), ev), 7)
    assert "built in 1963 by sculptor Tau Upsilon" in b7 and "11 meters high" in b7


def test_missing_evidence_entry_is_logged_not_silent(route):
    t = _fx("local900b_tour551_input.txt")
    logs = []
    rc.finalize_898(t, {"Some Other Title": "x"}, logs.append)
    assert any("no evidence entry under this title" in x for x in logs)


def test_lead_own_reference_abroad_is_ignored():
    """[LOCAL-900B/LEAD] a stop's Wikidata point 870 km from the (even coarse) scope centre never becomes the pin."""
    import place_names_900 as pn
    stops = [{"coordinates": "10.8665, 107.2872", "wikidata_lat": 13.748056, "wikidata_lng": 100.491111}]
    logs = []
    n = pn.check_pins_against_scope(stops, (11.083333, 108.083333), "DISTRICT", log=logs.append,
                                    ref_precision="region", ref_source="area_resolver")
    assert n == 0
    assert stops[0]["coordinates"] == "10.8665, 107.2872"
    assert any("ignored" in l for l in logs)


def test_lead_own_reference_near_scope_still_used():
    import place_names_900 as pn
    stops = [{"coordinates": "10.8784, 107.3067", "wikidata_lat": 10.8133, "wikidata_lng": 107.8941}]
    n = pn.check_pins_against_scope(stops, (11.083333, 108.083333), "DISTRICT", log=None,
                                    ref_precision="region", ref_source="area_resolver")
    assert n == 1 and stops[0]["coordinates"].startswith("10.813")
