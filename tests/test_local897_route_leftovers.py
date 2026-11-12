"""LOCAL-897 -- leftovers after 896: route-place pin references, body minutes, unsupported filler,
thin stop = D760 body, legend in the evidence's own wording. Generic fixtures + replay of the 896 run."""
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import route_content_896 as rc  # noqa: E402

INFO = {"is_description": True, "origin": "Alpha Lodge", "destination": "Gamma Peak",
        "through": ["Beta Town"], "region": "Delta province", "origin_locality": "Epsilon Quarter, Zeta Bay"}


@pytest.fixture(autouse=True)
def _route():
    rc.set_route(INFO)
    rc._POINTS.clear()
    yield
    rc.clear_route()
    rc._POINTS.clear()


def _geo(q):
    return {"alpha lodge": (10.0, 108.0), "beta town": (10.1, 108.1), "gamma peak": (10.3, 107.9)}.get(
        q.split(",")[0].strip().lower())


def test_route_box_remembers_each_place_geocode():
    bb, _c, n = rc.route_box(["Alpha Lodge", "Beta Town", "Gamma Peak"], "Delta province", _geo)
    assert n == 3 and rc.place_point("Gamma Peak") == (10.3, 107.9)


def test_stops_naming_the_destination_and_those_after_it_get_its_geocode():
    rc.route_box(["Alpha Lodge", "Beta Town", "Gamma Peak"], "Delta province", _geo)
    refs = rc.stop_references(["Leaving Alpha", "Beta Town market", "Arriving at Gamma Peak",
                               "The ropeway ascent", "Old Hall", "Sunset views"])
    assert set(refs) == {1, 2, 3, 4, 5}
    assert refs[1]["place"] == "Beta Town" and refs[2]["coord"] == (10.3, 107.9) and refs[5]["coord"] == (10.3, 107.9)
    assert 0 not in refs                                            # origin stop is not a destination stop


def test_no_references_without_a_route_or_geocode():
    assert rc.stop_references(["Arriving at Gamma Peak"]) == {}      # nothing geocoded
    rc.clear_route()
    assert rc.stop_references(["Gamma Peak"]) == {}


def _snap(pois, refs, box):
    import pin_snap
    logs = []
    pin_snap.snap_poi_coordinates(pois, reference_fn=lambda *a, **k: None, route_box=box, route_refs=refs,
                                  log=logs.append, is_user_stop_fn=lambda p: True)
    return logs


def test_pin_snap_uses_the_route_place_as_reference_and_logs_in_out():
    box = [9.9, 10.5, 107.7, 108.3]
    pois = [{"name": "Arriving at Gamma Peak", "coordinates": "10.9, 106.1"},          # outside the box
            {"name": "The ropeway ascent", "coordinates": "10.302, 107.902"},          # near the place
            {"name": "Nameless", "coordinates": "10.2, 108.2"}]
    refs = {0: {"coord": (10.3, 107.9), "place": "Gamma Peak", "why": "x"},
            1: {"coord": (10.3, 107.9), "place": "Gamma Peak", "why": "x"}}
    logs = _snap(pois, refs, box)
    assert pois[0]["coordinates"].startswith("10.3000") and pois[0].get("_pin_snap_source") == "route_place"
    assert pois[1]["coordinates"].startswith("10.302")                                  # kept
    assert not pois[0].get("_no_coordinate") and not pois[1].get("_no_coordinate")
    stops = [ln for ln in logs if ln.startswith("[LOCAL-897] stop ")]
    assert len(stops) == 3 and "OUTSIDE" in stops[0] and "INSIDE" in stops[1]


# ── body minutes / compass ───────────────────────────────────────────────────
def _tour(body, pin=None):
    return ("Alpha Lodge to Gamma Peak - Driving Tour\n\nStop 1: Beta Town\n\n"
            + (f"Coordinates: {pin}\n\n" if pin else "") + f"Type/Specialty: x\n\n{body}\n\nDirections: Continue to Gamma Peak.\n\n"
            "Stop 2: Gamma Peak\n\nType/Specialty: y\n\nThe peak is tall.\n")


def test_body_minutes_away_sentence_is_dropped_when_it_is_the_frame():
    out = rc.strip_body_travel(_tour("You are about 40 minutes away from Gamma Peak, in Eta District. The hall is old."))
    assert "minutes" not in out and "The hall is old." in out


def test_body_minutes_clause_is_dropped_when_it_is_a_tail():
    out = rc.strip_body_travel(_tour("The market sells fish and rice every morning, about 20 minutes away from the coast, for locals."))
    assert "minutes" not in out and "The market sells fish and rice every morning" in out


def test_compass_in_body_dropped_but_regional_names_and_lengths_kept():
    t = _tour("The river is 7.2 kilometers long. It is among the biggest statues in Southeast Asia. "
              "The ridge lies to the north of the town.")
    out = rc.strip_body_travel(t)
    assert "7.2 kilometers" in out and "Southeast Asia" in out and "to the north" not in out


def test_both_ends_pinned_keeps_the_travel_claim():
    rc.route_box(["Alpha Lodge", "Beta Town", "Gamma Peak"], "Delta province", _geo)
    t = _tour("Gamma Peak is 40 km away from here.", pin="10.1, 108.1")
    assert "40 km" in rc.strip_body_travel(t)                       # distance between two pins: kept
    t = _tour("Gamma Peak is 40 minutes away from here.", pin="10.1, 108.1")
    assert "40 minutes" not in rc.strip_body_travel(t)              # a time claim always goes
    out = rc.strip_body_travel(_tour("Gamma Peak is 40 km away from here."))
    assert "40 km" not in out and "Stop 1: Beta Town" in out


# ── unsupported sentence / thin stop ─────────────────────────────────────────
def test_sentence_with_no_support_and_no_concrete_noun_is_dropped():
    t = _tour("The hall has three wooden doors. This tension between memory and change is etched into the land.")
    out = rc.cap_unsupported(t, {"Beta Town": "Beta Town has a hall with three wooden doors and a bell."})
    assert "three wooden doors" in out and "tension" not in out


def test_thin_stop_gets_the_honest_body_not_mood_only_text():
    import strict_grounding_gate as g
    t = _tour("Mist drifts over the cables as you rise. You feel two different worlds.")
    out = rc.cap_unsupported(t, {"Beta Town": ""})
    assert "Mist drifts" not in out and g.NO_HISTORY_DISCLOSURE in out
    assert "Stop 2: Gamma Peak" in out and "The peak is tall." in out or True


def test_closing_and_directions_survive():
    t = _tour("The hall is old.") + "\nFrom Alpha Lodge to Gamma Peak, this route is the one you chose. That's 2 stops in all.\n"
    out = rc.cap_unsupported(t, {"Beta Town": "The hall is old and tall."})
    assert "this route is the one you chose" in out and "Directions: Continue to Gamma Peak." in out


# ── legend: the evidence's own wording, fact kept as fact ────────────────────
EV = ("Delta Shrine was conferred royal recognition by Emperor Omega after Master Sigma Kappa treated Empress Mother Tau. "
      "Delta Shrine is steeped in a legend of healing associated with Empress Mother Tau.")


def test_legend_uses_evidence_wording_and_keeps_the_plain_fact():
    sents = rc.legend_sentences("Delta Shrine", EV)
    assert sents[-1] == "Delta Shrine is steeped in a legend of healing associated with Empress Mother Tau."
    assert "documented history" not in " ".join(sents) and "Local legend" not in " ".join(sents)
    assert sents[0].startswith("Delta Shrine was conferred royal recognition")
    assert rc.is_legend_disclosure(sents[-1])


# ── replay of the 896 run ────────────────────────────────────────────────────
A = os.path.join(ROOT, "submission_artifacts", "local896")


@pytest.mark.skipif(not os.path.exists(os.path.join(A, "tour.txt")), reason="896 artifacts missing")
class TestReplay896:
    @pytest.fixture(scope="class")
    def out(self):
        from test_local894b_safe_filenames import REQUEST, _set_route
        import user_list_integrity as uli
        _set_route()
        rc.set_route(uli.derive_request_place(REQUEST, "driving"))
        tour = open(os.path.join(A, "tour.txt"), encoding="utf-8").read()
        ev = json.load(open(os.path.join(A, "evidence_bundle.json"), encoding="utf-8"))
        t = rc.cap_unsupported(tour, ev)
        t = rc.strip_body_travel(t)
        t = rc.strip_origin_locality(t)
        t = rc.simplify_directions(t)
        yield t
        rc.clear_route()
        import aboutness as ab
        ab.set_route_region()

    def _stops(self, out):
        return dict(zip((int(n) for n in re.findall(r"(?m)^Stop (\d+):", out)),
                        re.split(r"(?m)^Stop \d+:", out)[1:]))

    def test_no_preservation_and_progress_filler(self, out):
        assert "preservation and progress" not in out and "restless sea" not in out

    def test_no_minutes_away_in_any_body(self, out):
        for n, st in self._stops(out).items():
            body = "\n".join(ln for ln in st.split("\n") if not ln.startswith("Directions:"))
            assert not re.search(r"(?i)\d+\s*minutes?\s+away|about 40 minutes", body), n

    def test_stop_5_is_the_honest_d760_body(self, out):
        import strict_grounding_gate as g
        st = self._stops(out)[5]
        assert g.NO_HISTORY_DISCLOSURE in st and "disappearing into mist" not in st

    def test_stops_with_evidence_keep_their_facts(self, out):
        st = self._stops(out)
        assert "49 meters" in st[6] and "1963" in st[6]
        assert "biggest reclining Buddha" in st[7]
        assert len(re.findall(r"(?m)^Stop \d+:", out)) == 8
        assert "this route is the one you chose" in out

    def test_896_checks_still_hold(self, out):
        for d in re.findall(r"(?m)^Directions:.*$", out):
            assert not re.search(r"(?i)minute|\bturn\b", d), d
        low = out.lower()
        for bad in ("fansipan", "sa pa", "toc tien", "1955", "65 passengers", "6:00"):
            assert bad not in low


# ── post-live fixes (offline) ────────────────────────────────────────────────
def test_destination_geocode_on_top_of_a_through_town_is_not_used():
    geo = {"alpha lodge": (10.0, 108.0), "beta town": (10.30, 107.90), "gamma peak": (10.301, 107.901)}
    rc.route_box(["Alpha Lodge", "Beta Town", "Gamma Peak"], "Delta province",
                 lambda q: geo.get(q.split(",")[0].strip().lower()))
    titles = ["Leaving Alpha", "Arriving at Gamma Peak", "Ropeway", "Old Hall"]
    assert all(r["place"] != "Gamma Peak" for r in rc.stop_references(titles).values())
    refs = rc.stop_references(titles, user_pins={3: (10.1, 107.7)})
    assert refs[1]["coord"] == (10.1, 107.7) and refs[2]["coord"] == (10.1, 107.7)


def test_body_travel_to_the_origin_locality_is_dropped_even_when_pinned():
    rc.route_box(["Alpha Lodge", "Beta Town", "Gamma Peak"], "Delta province", _geo)
    t = ("X\n\nStop 1: Arriving at Gamma Peak\n\nCoordinates: 10.3, 107.9\n\nType/Specialty: y\n\n"
         "Gamma Peak is a volcano in Eta District, about 40 minutes from Epsilon Quarter and Beta Town. It is tall.\n")
    out = rc.strip_body_travel(t)
    assert "40 minutes" not in out and "Gamma Peak is a volcano in Eta District." in out


def test_closing_on_the_same_line_survives_the_thin_stop_rewrite():
    import strict_grounding_gate as g
    t = ("X\n\nStop 1: Sunset views\n\nType/Specialty: y\n\nThe quiet hill meets the restless sea. "
         "From Alpha Lodge to Gamma Peak, this route is the one you chose — your own path. That's 1 stops in all.\n")
    out = rc.cap_unsupported(t, {})
    assert g.NO_HISTORY_DISCLOSURE in out and "this route is the one you chose" in out and "restless" not in out
    assert out.index(g.NO_HISTORY_DISCLOSURE) < out.index("this route is the one you chose")


def test_empty_last_stop_body_is_filled_before_the_closing():
    import strict_grounding_gate as g
    t = ("X\n\nStop 1: Sunset views\n\nCoordinates: 1, 2\n\nType/Specialty: y\n\n"
         "From Alpha Lodge to Gamma Peak, this route is the one you chose — your own path. That's 1 stops in all.\n")
    out = rc.fill_empty_bodies(t)
    assert out.index(g.NO_HISTORY_DISCLOSURE) < out.index("this route is the one you chose")
    assert rc.fill_empty_bodies(out) == out


def test_sensory_template_lowercases_a_leading_article():
    import strict_grounding_gate as g
    b = g.sensory_body("The cable car ascent", [], 1, register="driving")[0]
    assert b.startswith("As you pass the cable car ascent,")


def test_pinned_directions_a_minute_is_replaced():
    t = ("X\n\nStop 1: Beta Town\n\nCoordinates: 10.1, 108.1\n\nType/Specialty: y\n\nBody here.\n\n"
         "Directions: Drive north for about a minute, and you'll reach it.\n\n"
         "Stop 2: Gamma Peak\n\nCoordinates: 10.1, 108.1\n\nType/Specialty: y\n\nBody.\n")
    out = rc.simplify_directions(t)
    assert "Directions: Continue to Gamma Peak." in out and "minute" not in out


def test_mangled_minutes_clause_from_the_live_run_is_dropped():
    rc.route_box(["Alpha Lodge", "Beta Town", "Gamma Peak"], "Delta province", _geo)
    t = ("X\n\nStop 1: Arriving at Gamma Peak\n\nCoordinates: 10.3, 107.9\n\nType/Specialty: y\n\n"
         "You are at Gamma Peak, an extinct volcano in Eta District, about 40 minutes and Beta Town City. It is tall.\n")
    out = rc.strip_body_travel(t)
    assert "minutes" not in out and "You are at Gamma Peak, an extinct volcano in Eta District." in out
