"""LOCAL-909 -- an "A to B" driving tour: A first, B last, no pin in the sea, a pin for every stop, no transit /
schedule advice on a driving tour, realistic leg minutes. Offline, $0, generic fixtures (D769); every lookup mocked."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SERPER_API_KEY", None)
os.environ["THIN_STOP_SEARCH"] = "0"

import fillings_payload as fp  # noqa: E402
import leftovers_906f as l906f  # noqa: E402
import route_order_909 as r909  # noqa: E402
import topic_library as tl  # noqa: E402
import topic_picker as tp  # noqa: E402

REQUEST = "Origin Town to Peak Mountain, Beta Province, Gamma"
ORIGIN = (10.9333, 108.2833)
DEST = (10.9763, 107.7114)                  # the destination's own geocode
OFFSHORE = (10.5235, 108.4051)              # the logged model pin: open water
LIGHTHOUSE_REAL = (10.80, 107.95)           # the real site, between the origin and the destination
STREAM = (10.9261, 108.1731)
BOX = [10.50, 11.67, 107.49, 108.68]


@pytest.fixture(autouse=True)
def _state():
    r909.clear()
    yield
    r909.clear()


def poi(name, coords=None, **kw):
    p = {"name": name, "coordinates": f"{coords[0]}, {coords[1]}" if coords else "", "type_specialty": "Landmark"}
    if not coords:
        p["_no_coordinate"] = True
    p.update(kw)
    return p


def land(lat, lng):                          # the sea is south of 10.6
    return lat > 10.6


def geocode(q):
    q = q.lower()
    if q.startswith("origin town"):
        return ORIGIN
    if q.startswith("peak mountain") or q.startswith("peak"):
        return DEST
    return None


def logged_list():
    return [poi("Lighthouse", OFFSHORE), poi("Stream", STREAM), poi("Peak Mountain", DEST)]


# ───────────────────────── request / order ─────────────────────────
def test_parse_request_shapes():
    assert r909.parse_route_request(REQUEST) == {"origin": "Origin Town", "destination": "Peak Mountain",
                                                 "region": "Beta Province, Gamma"}
    assert r909.parse_route_request("from Origin Town to Peak Mountain")["origin"] == "Origin Town"
    assert r909.parse_route_request("Old Town walking tour, Beta Province") is None
    assert r909.parse_route_request("Walking tour to the old market") is None


def test_order_is_a_to_b_and_never_doubles_back():
    a, b = ORIGIN, DEST
    pins = [LIGHTHOUSE_REAL, STREAM, DEST, (10.95, 108.05)]
    order = r909.order_stops(pins, a, b, dest_idx=2)
    assert order == [1, 3, 0, 2]
    ts = [r909.along(pins[i], a, b) for i in order]
    assert r909.max_backtrack(ts) <= r909.MAX_BACKTRACK


def test_a_stop_without_a_pin_keeps_its_place_and_the_destination_stays_last():
    order = r909.order_stops([None, STREAM, DEST, None], ORIGIN, DEST, dest_idx=2)
    assert order[-2:] == [3, 2] or order[-1] == 2
    assert sorted(order) == [0, 1, 2, 3]


def test_first_pass_ignores_a_pin_in_the_sea_and_logs_it():
    logs = []
    out = r909.order_poi_list(_prep(logged_list()), geocode, land, log=logs.append)
    assert [p["name"] for p in out][-1] == "Peak Mountain"
    assert any("open water" in m and "[LOCAL-909]" in m for m in logs)


def _prep(lst):
    r909.set_request(REQUEST, "vehicle")
    return lst


# ───────────────────────── the full replay ─────────────────────────
def _final_list():
    r909.set_request(REQUEST, "vehicle")
    lst = logged_list()
    lst[2] = poi("Peak Mountain")                                  # the 870 rule cleared its model pin
    rows = [{"reference": LIGHTHOUSE_REAL, "snapped": False}, {}, {}]
    logs = []
    a, b = r909.endpoints_pts(geocode, logs.append)
    out = r909.finalize_route_pins(lst, rows, r909.route(), a, b, box=BOX, land_fn=land, log=logs.append)
    return out, logs


def test_replay_order_pins_and_coordinates():
    out, logs = _final_list()
    assert [p["name"] for p in out] == ["Stream", "Lighthouse", "Peak Mountain"]
    pins = [r909._poi_pin(p) for p in out]
    assert all(pins), "every stop carries a pin"
    assert pins[1] == pytest.approx(LIGHTHOUSE_REAL)                      # the offshore pin was replaced
    assert pins[2] == pytest.approx(DEST)                                  # the last stop's pin restored
    assert out[2].get("coordinates_approximate") is True
    ts = [r909.along(pt, ORIGIN, DEST) for pt in pins]
    assert r909.max_backtrack(ts) <= 0.2
    assert any("Stop 3 delivered without coordinates ->" in m and "[LOCAL-909]" in m for m in logs)
    assert any("offshore pin" in m and "replaced" in m for m in logs)


def test_a_failed_land_lookup_is_not_water():
    r909.set_request(REQUEST, "vehicle")
    lst = logged_list()
    assert r909.water_pins(lst, lambda la, ln: None) == []
    assert r909.water_pins(lst, land) == [0]


def test_a_last_stop_with_no_reference_is_placed_between_its_neighbours():
    r909.set_request(REQUEST, "vehicle")
    lst = [poi("Stream", STREAM), poi("Peak Mountain")]
    logs = []
    fixed = r909.restore_pins(lst, [{}, {}], ORIGIN, DEST, "Other Place", None, log=logs.append)
    assert fixed == [1] and r909._poi_pin(lst[1]) is not None
    assert any("between its neighbours" in m for m in logs)


TEXT = """Step-by-step audio guided tour from Origin Town to Peak Mountain is a driving tour.

Stop 1: Stream

Address: Road One, Origin Town, Beta Province, Gamma

Coordinates: 10.9261, 108.1731

Type/Specialty: Natural Attraction

The stream runs between steep red cliffs and is a short stop beside the road. The banks are shallow and sandy.

Directions: From Stream, head west along the coast road. Continue to Lighthouse — it is roughly 40.0 km away.

Stop 2: Lighthouse

Address: Cape Road, Beta Province, Gamma

Coordinates: 10.8, 107.95

Type/Specialty: Historical Landmark

The lighthouse stands on a headland above the sea. It was built to guide ships along the coast.

Directions: From Lighthouse, take the road inland. Continue to Peak Mountain — it is roughly 30.0 km away.

Stop 3: Peak Mountain

Type/Specialty: Natural Attraction

You are at the foot of Peak Mountain. To get here, you might take bus 4 from the mall, making sure you are heading in the right direction. You can choose to visit Peak Mountain in the morning or afternoon depending on your schedule. You can take a modern cable car or walk through the jungle to reach the top. At the top, you find two pagodas.

That's 3 stops in all.
"""


def test_delivery_text_has_coordinates_origin_directions_and_no_transit_advice():
    out, _ = _final_list()
    r909._STATE["mode"] = "vehicle"
    r909.set_final_pins({p["name"]: r909._poi_pin(p) for p in out})
    logs = []
    text = r909.finalize_text(TEXT, log=logs.append)
    text = l906f.drop_driving_practical(text, logs.append)
    blocks = text.split("Stop ")[1:]
    assert len(blocks) == 3 and all("Coordinates:" in b for b in blocks)
    assert "Coordinates: 10.9763, 107.7114" in blocks[2]
    first_dir = [ln for ln in text.splitlines() if ln.startswith("Directions:")][0]
    assert first_dir.startswith("Directions: From Origin Town, head")
    low = text.lower()
    assert "bus 4" not in low and "from the mall" not in low and "morning or afternoon" not in low
    assert "walk through the jungle" not in low
    assert "At the top, you find two pagodas." in text and "You are at the foot of Peak Mountain." in text
    assert any("Stop 3 delivered without coordinates" in m for m in logs)


def test_walking_tour_keeps_a_bus_sentence_its_evidence_states():
    r909.set_request("Old Town to Peak Mountain, Beta Province, Gamma", "on_foot")
    text = ("Stop 1: Stream\n\nCoordinates: 10.9, 108.1\n\nTake bus 4 from the station to reach the stream. "
            "The banks are sandy.\n\n")
    assert l906f.drop_driving_practical(text) == text
    r909.set_request(REQUEST, "vehicle")
    assert "bus 4" not in l906f.drop_driving_practical(text)


# ───────────────────────── fillings / leg minutes ─────────────────────────
def _segs():
    return [{"id": i, "region_key": "r", "theme": th, "title": f"Seg {i}", "language": "en", "est_minutes": m,
             "status": "ready", "centroid_lat": 10.9, "centroid_lng": 108.0, "radius_km": 200,
             "audio_path": f"a{i}.mp3", "credit_line": tl.CREDIT_LINE}
            for i, (th, m) in enumerate([("history", 10), ("food", 12), ("nature", 9), ("arts", 11),
                                         ("transport", 13), ("legends", 10), ("religion_customs", 12)], 1)]


def test_every_leg_gets_fillings_and_minutes_are_realistic():
    out, _ = _final_list()
    r909._STATE["mode"] = "vehicle"
    r909.set_final_pins({p["name"]: r909._poi_pin(p) for p in out})
    text = r909.finalize_text(TEXT)
    stops = fp.stops_from_tour_text(text)
    assert len(stops) == 3 and all("lat" in s and "lng" in s for s in stops)
    assert stops[0]["leg_distance_km"] == 40.0                               # the road km the Directions state
    tour = {"stops": stops, "tour_type": "driving tour", "language": "en"}
    for i, km in enumerate((40.0, 30.0)):
        m, src = tp.leg_minutes_source(tour, i)
        assert m == pytest.approx(km / 45 * 60, abs=0.1) and src == "stated km"
    assert tp.leg_minutes(tour, 0) == pytest.approx(40.0 / 45 * 60, abs=0.1)
    fillings = fp.build_fillings(tour, segments=_segs())
    assert [f["leg"] for f in fillings] == [0, 1]
    assert all(f["minutes"] >= tp.MIN_LEG_MINUTES and f["items"] for f in fillings)


def test_logged_leg_51_km_is_about_an_hour_not_two():
    tour = {"mode": "car", "stops": [{"title": "A", "lat": 10.9, "lng": 108.2, "leg_distance_km": 51.4},
                                     {"title": "B", "lat": 10.9, "lng": 107.7}]}
    m, src = tp.leg_minutes_source(tour, 0)
    assert 60 <= m <= 75 and src == "stated km"
    est = {"mode": "car", "stops": [{"title": "A", "lat": 10.5, "lng": 108.4}, {"title": "B", "lat": 10.93, "lng": 108.17}]}
    assert tp.leg_minutes_source(est, 0)[1] == "pin distance"
    assert tp.SPEEDS_KMH["car_rural"] in (40.0, 45.0, 50.0)
    assert tp.leg_minutes_source({"mode": "car", "stops": [{"title": "A"}, {"title": "B"}]}, 0) == (None, "no pins")


def test_lead_not_routes():
    """[LEAD review] title-like requests with 'to' are not A-to-B routes."""
    import route_order_909 as r
    for q in ["Introduction to Boston history", "Back to the Future filming locations, Los Angeles",
              "Welcome to Saigon street food", "Ode to Joy concert halls, Vienna"]:
        assert r.parse_route_request(q) is None, q
    assert r.parse_route_request("Mui Ne to Ta Cu Mountain, Binh Thuan, Vietnam")["destination"] == "Ta Cu Mountain"
    assert r.parse_route_request("From Nice to Monte Carlo")["origin"] == "Nice"
    assert r.parse_route_request("Port of Spain to San Fernando, Trinidad")["origin"] == "Port of Spain"
