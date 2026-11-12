"""LOCAL-896 -- content rules for a described ROUTE (origin != destination).

Part 1: generic fixtures ("Alpha", "Beta" ...; D769: no place names in code under test).
Part 2: replay of the LOCAL-894B live run (its tour + evidence bundle) through the same passes.
"""
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
    yield
    rc.clear_route()


def _tour(stops, tail=""):
    out = ["Alpha Lodge to Gamma Peak - Driving Tour", "Tour-Category: driving", ""]
    for i, (title, body, directions, pin) in enumerate(stops, 1):
        out += [f"Stop {i}: {title}", ""]
        if pin:
            out += [f"Coordinates: {pin}", ""]
        out += ["Type/Specialty: Thing", "", body, ""]
        if directions:
            out += [f"Directions: {directions}", ""]
    return "\n".join(out) + tail


# ── state ────────────────────────────────────────────────────────────────────
def test_active_only_for_a_route():
    assert rc.active() and rc.endpoints() == ("Alpha Lodge", "Gamma Peak")
    rc.set_route(dict(INFO, destination="Alpha Lodge"))
    assert not rc.active()
    rc.set_route({"is_description": False})
    assert not rc.active()


def test_localities_exclude_places_the_route_itself_names():
    rc.set_route(dict(INFO, origin_locality="Epsilon Quarter, Beta Town"))
    assert rc._STATE["localities"] == ["epsilon quarter"]


# ── 2. locality ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("src,want", [
    ("You stand on Gamma Peak in Epsilon Quarter, Zeta Bay, Country.", "You stand on Gamma Peak, Country."),
    ("It is known beyond this quiet corner of Epsilon Quarter for one feature.",
     "It is known beyond this quiet corner for one feature."),
    ("The hall near Zeta Bay is old.", "The hall is old."),
    ("Nothing to change here.", "Nothing to change here."),
])
def test_locality_phrase_removed(src, want):
    assert rc.strip_origin_locality_sentence(src) == want


def test_unrepairable_locality_sentence_is_dropped():
    assert rc.strip_origin_locality_sentence("In Epsilon Quarter the hall is old.") is None
    assert rc.strip_origin_locality_sentence("Epsilon Quarter's coast is long.") is None


def test_locality_only_on_stops_after_the_first_and_not_naming_it():
    t = _tour([("Leaving Epsilon Quarter", "The lodge is in Epsilon Quarter, Zeta Bay.", "Go.", None),
               ("Beta Town", "A market in Epsilon Quarter sells fish. Boats are old.", "Go.", None),
               ("Gamma Peak", "The peak stands in Epsilon Quarter, Zeta Bay, Country.", None, None)])
    out = rc.strip_origin_locality(t)
    b = out.split("Stop 2:")[1]
    assert "Epsilon" not in b and "Zeta" not in b
    assert "The lodge is in Epsilon Quarter, Zeta Bay." in out          # first stop untouched
    assert "Boats are old." in out


def test_a_stop_titled_with_the_locality_keeps_it():
    t = _tour([("Start", "Hello there you.", "Go.", None),
               ("Epsilon Quarter market", "The market is in Epsilon Quarter.", "Go.", None),
               ("End", "Bye you all.", None, None)])
    assert "in Epsilon Quarter." in rc.strip_origin_locality(t)


# ── 3. directions ────────────────────────────────────────────────────────────
def test_directions_without_pins_are_continue_to_next_only():
    t = _tour([("One", "Body one here.", "Drive northwest for about 15 minutes, turn left.", None),
               ("Two", "Body two here.", "Continue driving 10 minutes to reach Three.", None),
               ("Three", "Body three here.", None, None)])
    out = rc.simplify_directions(t)
    assert "Directions: Continue to Two." in out and "Directions: Continue to Three." in out
    assert not re.search(r"minute|northwest", out)


def test_directions_with_pins_on_both_ends_are_kept():
    t = _tour([("One", "Body one here.", "Drive northwest for about 15 minutes.", "1.0, 2.0"),
               ("Two", "Body two here.", "Drive on.", "1.1, 2.1"),
               ("Three", "Body three here.", None, None)])
    out = rc.simplify_directions(t)
    assert "Directions: Continue to Two, about 16 km away." in out    # pinned both ends: measured, not guessed
    assert "Directions: Continue to Three." in out          # Two -> Three: Three has no pin


def test_not_a_route_changes_nothing():
    rc.clear_route()
    t = _tour([("One", "Body in Epsilon Quarter.", "Drive 15 minutes.", None), ("Two", "Body two.", None, None)])
    assert rc.simplify_directions(t) == t and rc.strip_origin_locality(t) == t


# ── 4. closing ───────────────────────────────────────────────────────────────
def test_closing_names_origin_and_destination_never_the_city():
    import tour_conclusion as tc
    t = _tour([("One", "Body one is here now.", "Go.", None), ("Two", "Body two is here now.", "Go.", None),
               ("Three", "Body three is here now.", None, None)])
    out = tc.rebuild_conclusion(t, venue_name="Epsilon Quarter, Zeta Bay", user_stops=True)
    tail = out[out.index("Stop 3:"):]
    assert "Alpha Lodge" in tail and "Gamma Peak" in tail
    assert "city" not in tail.lower() and "That's 3 stops in all." in tail


def test_closing_unchanged_for_a_plain_user_list():
    import tour_conclusion as tc
    rc.clear_route()
    t = _tour([("One", "Body one is here now.", "Go.", None), ("Two", "Body two is here now.", "Go.", None)])
    out = tc.rebuild_conclusion(t, venue_name="Somewhere City", user_stops=True)
    assert "through the city" in out


# ── 5. legend ────────────────────────────────────────────────────────────────
EV_LEGEND = ("Delta Shrine is steeped in a legend of healing that is still passed down among the locals. "
             "Delta Shrine is associated with the legend of healing Queen Mother Omega. Entry is free.")


def test_legend_is_disclosed_as_a_legend_with_one_sentence():
    s = rc.legend_disclosure("Delta Shrine", EV_LEGEND)
    assert s and s.startswith("Delta Shrine is steeped in a legend of ")   # [897]
    assert len(rc.split_sentences(s)) == 1
    assert rc.is_legend_disclosure(s)


def test_no_legend_in_evidence_no_sentence():
    assert rc.legend_disclosure("Delta Shrine", "Delta Shrine was built in 1900. Entry is free.") is None
    assert rc.legend_disclosure("Other Place", EV_LEGEND) is None        # sentence must name the stop


def test_gate_adds_the_legend_once_and_only_on_a_route():
    import strict_grounding_gate as g
    t = _tour([("Delta Shrine", "The shrine stands on a hill. Pilgrims climb the stairs each morning. "
                "It has three halls.", "Go.", None), ("Gamma Peak", "A peak you can see far.", None, None)])
    ev = {"Delta Shrine": EV_LEGEND}
    nop = lambda *a, **k: (None, 0, 0)  # noqa: E731
    out, rep = g.ground_tour_text(t, ev, location="x", classify_fn=nop, register="driving")
    assert out.count("Delta Shrine is steeped in a legend of") == 1
    out2, _ = g.ground_tour_text(out, ev, location="x", classify_fn=nop, register="driving")
    assert out2.count("Delta Shrine is steeped in a legend of") == 1             # idempotent
    rc.clear_route()
    out3, _ = g.ground_tour_text(t, ev, location="x", classify_fn=nop, register="driving")
    assert "steeped in a legend" not in out3


def test_a_disclosed_legend_survives_the_855b_legend_gate():
    import user_stop_narration as usn
    s = rc.legend_disclosure("Delta Shrine", EV_LEGEND)
    assert rc.is_legend_disclosure(s)
    assert usn._LEGEND_MARKER_RE.search(s)                                # the gate would flag it...
    assert not rc.is_legend_disclosure("The dragon legend says the river was born here.")   # ... others still go


# ── 1. other-place evidence: sentences only it backed ───────────────────────
def test_sentences_only_the_dropped_evidence_backs_are_removed():
    dropped = ("The tram was built in 1955 and carries 65 passengers. The ticket office opens at 6:00 a.m. "
               "The climate changes rapidly during the ascent.")
    sents = ["You are on the tram.", "It was built in 1955.", "Go to the ticket office early to get tickets.",
             "The climate changes rapidly as you climb.", "Pilgrims light incense here."]
    gone = rc.sentences_backed_by(sents, dropped, "", "The tram")
    assert "It was built in 1955." in gone
    assert "Go to the ticket office early to get tickets." in gone
    assert "The climate changes rapidly as you climb." in gone
    assert "Pilgrims light incense here." not in gone and "You are on the tram." not in gone


def test_a_sentence_the_kept_evidence_also_backs_stays():
    dropped = "The tram opens at 6:00 a.m. The ticket office is busy."
    kept = "The ticket office is busy at weekends."
    assert rc.sentences_backed_by(["The ticket office is busy."], dropped, kept, "The tram") == []


# ── pins: route box ──────────────────────────────────────────────────────────
class _Geo:
    def __init__(self, table):
        self.table, self.calls = table, []

    def __call__(self, q):
        self.calls.append(q)
        for k, v in self.table.items():
            if k in q:
                return v
        return None


def test_route_box_covers_origin_through_destination_with_margin():
    geo = _Geo({"Alpha": (10.00, 100.00), "Beta": (10.10, 100.10), "Gamma": (10.20, 100.30)})
    bb, ctr, n = rc.route_box(["Alpha Lodge", "Beta Town", "Gamma Peak"], "Delta province", geo)
    assert n == 3 and bb[0] < 10.00 and bb[1] > 10.20 and bb[2] < 100.00 and bb[3] > 100.30
    assert rc.in_box(bb, 10.15, 100.2) and not rc.in_box(bb, 11.5, 100.2)
    assert any("Delta province" in q for q in geo.calls)


def test_route_box_uses_the_origin_fallback_and_needs_two_places():
    geo = _Geo({"Epsilon": (10.0, 100.0), "Gamma": (10.2, 100.3)})
    bb, _c, n = rc.route_box(["Alpha Lodge", "Gamma Peak"], "", geo, fallbacks=["Epsilon Quarter"])
    assert bb and n == 2
    bb, _c, n = rc.route_box(["Alpha Lodge", "Gamma Peak"], "", _Geo({}))
    assert bb is None and n == 0


def test_preview_pins_a_stop_beyond_the_city_radius_when_given_the_route():
    import itinerary_import as ii
    from test_local867_itinerary_import import Fake
    far = (10.9, 107.3)                 # far from the city centre: outside the 25 km radius
    wd = lambda n: (far[0], far[1], "Q1") if "Hilltop" in n else None  # noqa: E731
    geo = _Geo({"Alpha": (10.8, 106.9), "Gamma": far})
    base = ii.preview_stops("Hilltop Shrine", "Ho Chi Minh City", resolvers=Fake(wikidata=wd).resolvers(),
                            log=lambda *_: None)
    assert base["stops"][0]["unresolved"] is True
    out = ii.preview_stops("Hilltop Shrine", "Ho Chi Minh City", resolvers=Fake(wikidata=wd).resolvers(),
                           log=lambda *_: None, route_places=["Alpha Lodge", "Gamma Peak"], route_geocode=geo)
    assert out["stops"][0]["unresolved"] is False
    assert abs(out["stops"][0]["lat"] - far[0]) < 1e-6


# ── pins: pin_snap does not collapse a model pin inside the route region ────
def _snap(box):
    import pin_snap
    pois = [{"name": "Stop Aa", "coordinates": "10.5000, 107.0000", "user_explicit": True,
             "coord_source": "llm"},
            {"name": "Stop Bb Different", "coordinates": "10.5010, 107.0010", "user_explicit": True,
             "coord_source": "llm"}]
    out, _rows = pin_snap.snap_poi_coordinates(
        pois, scope="x", scope_center=(10.5, 107.0), reference_fn=lambda *a, **k: None,
        landmark_fn=lambda *a, **k: None, log=lambda m: None, city_centroid=(10.0, 106.0),
        is_user_stop_fn=lambda p: True, route_box=box)
    return out


def test_pin_inside_the_route_region_is_kept_and_outside_is_not():
    cleared = _snap(None)
    assert any(p.get("_no_coordinate") for p in cleared)       # without a route: unchanged behaviour
    kept = _snap([10.0, 11.0, 106.5, 107.5])
    assert all(p["coordinates"] for p in kept) and not any(p.get("_no_coordinate") for p in kept)
    outside = _snap([20.0, 21.0, 106.5, 107.5])
    assert any(p.get("_no_coordinate") for p in outside)


# ═════ replay of the LOCAL-894B live run ═════════════════════════════════════
REPLAY_OK = os.path.exists(os.path.join(ROOT, "submission_artifacts", "local894b", "tour.txt"))


@pytest.mark.skipif(not REPLAY_OK, reason="894B artifacts missing")
class TestReplay894B:
    @pytest.fixture(scope="class")
    def out(self):
        from test_local894b_safe_filenames import REQUEST, EV_LIVE, TOUR_LIVE, _set_route
        import key_fact_coverage as kfc
        import strict_grounding_gate as g
        import tour_conclusion as tc
        import user_list_integrity as uli
        _set_route()
        rc.set_route(uli.derive_request_place(REQUEST, "driving"))
        nop = lambda *a, **k: (None, 0, 0)  # noqa: E731
        t, _ = g.ground_tour_text(TOUR_LIVE, EV_LIVE, location="Ham Tien, Mui Ne", classify_fn=nop,
                                  register="driving")
        t = tc.rebuild_conclusion(t, venue_name="Ham Tien, Mui Ne", user_stops=True)
        t, _ = kfc.finalize_tour(t, EV_LIVE, classify_fn=nop, user_list=True)
        t = rc.strip_origin_locality(t)
        t = rc.simplify_directions(t)
        yield t
        rc.clear_route()
        import aboutness as ab
        ab.set_route_region()

    def _stops(self, out):
        return dict(zip((int(n) for n in re.findall(r"(?m)^Stop (\d+):", out)),
                        re.split(r"(?m)^Stop \d+:", out)[1:]))

    def test_nothing_from_the_other_cable_car(self, out):
        low = out.lower()
        for bad in ("fansipan", "sa pa", "toc tien", "1955", "65 passengers", "6:00", "ticket office"):
            assert bad not in low, bad
        assert len(re.findall(r"(?m)^Stop \d+:", out)) == 8

    def test_no_origin_locality_on_stops_4_to_7(self, out):
        st = self._stops(out)
        for n in (4, 5, 6, 7):
            assert "ham tien" not in st[n].lower(), n

    def test_no_minutes_or_compass_in_directions_without_pins(self, out):
        for d in re.findall(r"(?m)^Directions:.*$", out):
            assert not re.search(r"(?i)minute|north|south|east|west|\bturn\b", d), d
            assert d.startswith("Directions: Continue to ")

    def test_closing_names_origin_and_destination(self, out):
        tail = out[out.index("Stop 8:"):]
        assert "Caty Mui Ne Resort" in tail and "Ta Cu Mountain" in tail
        assert "city" not in tail.lower()

    def test_legend_disclosed_as_legend(self, out):
        st = self._stops(out)[6]
        assert re.search(r"(?i)Linh Son Truong Tho Pagoda is steeped in a legend of", st)   # [897] evidence wording

    def test_no_filler_stop_8(self, out):
        st = self._stops(out)[8].lower()
        assert "tides" not in st and "threshold" not in st and "converge" not in st

    def test_stop_5_is_an_honest_short_body_not_empty(self, out):
        st = self._stops(out)[5]
        body = [ln for ln in st.split("\n") if ln.strip() and not re.match(r"(?i)^(type/|directions:)", ln.strip())]
        assert body and "could not confirm" in " ".join(body)


def test_the_origin_name_and_a_return_to_the_locality_are_not_the_stamp():
    rc.set_route(dict(INFO, origin="Brand Epsilon Quarter Lodge"))
    s = "From Brand Epsilon Quarter Lodge to Gamma Peak, this route is yours."
    assert rc.strip_origin_locality_sentence(s) == s
    s = "The drive back to Epsilon Quarter takes an hour."
    assert rc.strip_origin_locality_sentence(s) == s


def test_preview_endpoint_passes_the_route_region_through(monkeypatch):
    import generate_tour_text_service as svc
    import itinerary_import as ii
    seen = {}

    def fake(text, city, **kw):
        seen.update(kw)
        return {"ok": True, "count": 1, "unresolved_count": 0, "city": {"name": "x"}, "cost": {}, "stops": []}
    monkeypatch.setattr(ii, "preview_stops", fake)
    monkeypatch.setenv("USER_STOPS_ENABLED", "true")
    c = svc.app.test_client()
    r = c.post("/preview-stops", json={"text": "Hilltop", "city": "X", "route_places": ["Alpha Lodge", "Gamma Peak"],
                                       "route_region": "Delta province", "route_fallbacks": ["Zeta Bay"]})
    assert r.status_code == 200, r.data
    assert seen["route_places"] == ["Alpha Lodge", "Gamma Peak"] and seen["route_region"] == "Delta province"
    seen.clear()
    c.post("/preview-stops", json={"text": "Hilltop", "city": "X", "route_places": "bad"})
    assert "route_places" not in seen


def test_orchestrator_sends_the_route_with_the_preview(monkeypatch):
    import tour_orchestrator_service as orch
    sent = {}

    class _R:
        status_code = 200

        def json(self):
            return {"ok": True}
    monkeypatch.setattr(orch, "_authenticated_request", lambda m, u, **kw: sent.update(kw) or _R())
    orch._d762_gen_preview("Hilltop", "X", {"route_places": ["A", "B"], "route_region": "R"})
    assert sent["json"]["route_places"] == ["A", "B"] and sent["json"]["city"] == "X"
    sent.clear()
    orch._d762_gen_preview("Hilltop", "X")
    assert sent["json"] == {"text": "Hilltop", "city": "X"}


def test_pinned_directions_lose_model_minutes_the_pins_contradict():
    t = _tour([("One", "Body one here.", "Continue driving west for about 10 minutes to the fields.", "10.000, 100.000"),
               ("Two", "Body two here.", "Drive on.", "10.005, 100.005"),
               ("Three", "Body three here.", None, "10.5, 100.5")])
    out = rc.simplify_directions(t)
    assert "Directions: Continue to Two." in out and "minutes" not in out.split("Stop 2:")[0]
    assert "Directions: Drive on." in out                       # no minutes claim: kept
    far = _tour([("One", "Body one here.", "Drive about 5 minutes.", "10.0, 100.0"),
                 ("Two", "Body two here.", None, "10.05, 100.0")])
    assert "about 6 km away" in rc.simplify_directions(far)
