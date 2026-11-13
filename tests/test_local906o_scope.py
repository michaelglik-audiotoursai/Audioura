"""[LOCAL-906O] Anchors are place names, the destination reference chain, another-city stops, sub-stop order, practical copy,
the closing on the route path, the measure fallback. $0: no network, no key. Generic names only (D769)."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SERPER_API_KEY", None)
os.environ["THIN_STOP_SEARCH"] = "0"

import anchor_evidence_906m as a  # noqa: E402
import delivery_evidence_906h as de  # noqa: E402
import leftovers_906f as f906  # noqa: E402
import refill_quality_906k as k  # noqa: E402
import route_content_896 as rc  # noqa: E402
import route_order_909 as r909  # noqa: E402
import scope_906o as s  # noqa: E402


@pytest.fixture(autouse=True)
def _job():
    r909.clear()
    with rc.job_scope("t906o"):
        rc.set_evidence_904({})
        de.clear()
        yield
    r909.clear()


def tour(stops, closing="That's 3 stops in all."):
    out = "Step-by-step audio guided tour of Alpha Peak is a driving tour.\n\n"
    for n, (title, body, directions) in enumerate(stops, 1):
        out += (f"Stop {n}: {title}\n\nCoordinates: 10.{n}, 100.{n}\n\nType/Specialty: Landmark\n\n{body}\n\n"
                f"Directions: {directions}\n\n")
    return out + closing + "\n"


# ── 1. anchors are place names ───────────────────────────────────────────────────────────────────────────
TITLES = ["Leaving Origin Strand – the fishing coast", "Beta Town and the Gamma River",
          "Dragon fruit country – the plantations along the road", "The cable car ascent", "Alpha Peak"]


def test_topic_like_title_is_anchored_by_province_and_country_never_a_whole_title():
    got = a.anchors_for("Dragon fruit country – the plantations along the road", TITLES, destination="Alpha Peak",
                        region="Delta Province, Vietnam")
    assert got[0] == "Delta Province" and "Vietnam" in got
    assert "Beta Town and the Gamma River" not in got and "Beta Town" in got and "Gamma River" in got
    assert all(len(x.split()) <= 4 for x in got)


def test_dragon_fruit_page_naming_the_province_is_accepted():
    anchors = a.anchors_for("Dragon fruit country – the plantations along the road", TITLES, destination="Alpha Peak",
                            region="Delta Province, Vietnam")
    page = "An overview of dragon fruit. Dragon fruit is grown widely in Delta province, in southern Vietnam."
    assert a.reject_evidence(3, anchors, page, "https://example.test/dragon-fruit") is False
    assert a.reject_evidence(3, anchors, "Dragon fruit grows in Brazil.", "https://example.test/x") is True


def test_landmark_title_keeps_destination_first():
    got = a.anchors_for("The cable car ascent", TITLES, destination="Alpha Peak", region="Delta Province, Vietnam")
    assert got[0] == "Alpha Peak" and "Delta Province" not in got


def test_name_cores():
    assert a.name_cores("Beta Town and the Gamma River") == ["Beta Town", "Gamma River"]
    assert a.name_cores("Leaving Origin Strand – the fishing coast") == ["Origin Strand"]


# ── 2. destination reference chain, logged ───────────────────────────────────────────────────────────────
def test_destination_uses_the_place_reference_chain_and_logs_it():
    seen = {}

    def chain(dest):
        seen["dest"] = dest
        return {"name": dest, "lat": 10.8167, "lng": 107.8833, "source": "906D local-language wikidata"}
    r909.set_request("Origin Strand to Alpha Peak, Delta Province, Vietnam", "vehicle")
    r909._STATE["endpoints"] = ((10.93, 108.28), (10.9286, 108.0885))      # cached BEFORE the reference existed
    logs = []
    pt = r909.destination_reference(None, "Alpha Peak", chain, logs.append)
    assert pt == (10.8167, 107.8833) and seen["dest"] == "Alpha Peak"
    assert any("[LOCAL-906O] destination 'Alpha Peak' -> 10.8167,107.8833 via 906D local-language wikidata" in x
               for x in logs)
    assert r909._STATE["endpoints"][1] == (10.8167, 107.8833)              # the far end follows the reference


def test_destination_reference_miss_is_logged():
    r909.set_request("Origin Strand to Alpha Peak, Delta Province, Vietnam", "vehicle")
    logs = []
    assert r909.destination_reference(None, "Alpha Peak", lambda d: None, logs.append) is None
    assert any("[LOCAL-906O] destination 'Alpha Peak' -> no place reference" in x for x in logs)


def test_destination_stop_pin_is_the_reference():
    r909.set_request("Origin Strand to Alpha Peak, Delta Province, Vietnam", "vehicle")
    r909.set_dest_reference((10.8167, 107.8833), "Alpha Peak")
    pts = [{"name": "Alpha Peak", "coordinates": ""}]
    r909.restore_pins(pts, [{}], (10.93, 108.28), (10.8167, 107.8833), "Alpha Peak", (10.9286, 108.0885))
    assert pts[0]["coordinates"].startswith("10.816700")


def test_area_resolver_gets_the_province_qid_and_country(monkeypatch):
    import area_resolver as ar
    got = {}
    monkeypatch.setattr(ar, "first_named_place_reference", lambda *a_, **kw: got.update(kw) or None)
    ar.first_named_place_reference("Alpha Peak, Delta Province", "Delta Province", (1, 1), city_qid="Q1", country="Vietnam")
    assert got["city_qid"] == "Q1" and got["country"] == "Vietnam"


# ── 3. another city; sub-stop order ──────────────────────────────────────────────────────────────────────
HOME = s.home_terms("Origin Strand", "Alpha Peak", "Delta Province, Vietnam", [])


def test_actually_located_in_another_city_is_not_delivered():
    body = ("The museum preserves the story of an old military route. This museum is actually located in the Ward area "
            "of Far District, west of central Capital City. Visitors walk a path of 1,000 steps.")
    t = tour([("Origin Strand", "A quiet beach.", "Drive on."), ("Museum Hall", body, "Drive to Alpha Peak."),
              ("Alpha Peak", "A mountain with a cable car.", "")])
    logs = []
    out = s.drop_other_city_sentences(t, HOME, logs.append)
    assert "actually located" not in out and "Capital City" not in out
    assert "preserves the story" in out and "1,000 steps" in out
    assert any("[LOCAL-906O] Stop 2" in x for x in logs)


def test_actually_located_in_the_tour_region_is_kept():
    t = tour([("Origin Strand", "It is actually located in Delta Province, near the coast.", "Go.")])
    assert s.drop_other_city_sentences(t, HOME) == t


def test_stop_whose_text_places_it_in_another_city_outside_the_box_is_rejected_or_replaced():
    box = [10.5, 11.6, 107.5, 108.7]
    pois = [{"name": "Origin Strand", "coordinates": "10.93, 108.28"},
            {"name": "Museum Hall", "coordinates": "", "description": "This museum is in fact located in Ward, Far District, west of Capital City."},
            {"name": "Alpha Peak", "coordinates": "10.9, 108.1"}]
    logs = []
    out = s.reject_stops(pois, box, HOME, log=logs.append)
    assert [p["name"] for p in out] == ["Origin Strand", "Alpha Peak"]
    rep = s.reject_stops(pois, box, HOME, replace_fn=lambda p: {"name": "Pool Pagoda", "coordinates": "10.8, 108.0"})
    assert [p["name"] for p in rep] == ["Origin Strand", "Pool Pagoda", "Alpha Peak"]
    # a user stop and an in-box real pin are kept
    kept = s.reject_stops(pois, box, HOME, protect=lambda p: p["name"] == "Museum Hall")
    assert len(kept) == 3
    pois[1]["coordinates"] = "10.8, 108.0"
    assert len(s.reject_stops(pois, box, HOME)) == 3


def test_sub_stop_of_the_destination_is_ordered_last_but_one():
    a_, b_ = (10.93, 108.28), (10.8, 107.9)
    pois = [{"name": "Hill Pagoda", "address": "Alpha Peak, Delta Province", "coordinates": "10.93, 108.2"},   # bad pin: nearest A
            {"name": "Beta Town", "coordinates": "10.9, 108.1"},
            {"name": "Alpha Peak", "coordinates": "10.8, 107.9"}]
    subs = r909.dest_substops(pois, "Alpha Peak")
    assert subs == [0]
    order = r909.order_stops([(10.93, 108.2), (10.9, 108.1), (10.8, 107.9)], a_, b_, 2, subs)
    assert order == [1, 0, 2]
    assert order == r909.order_stops([(10.93, 108.2), (10.9, 108.1), (10.8, 107.9)], a_, b_, 2, subs)
    r909.set_request("Origin Strand to Alpha Peak, Delta Province", "vehicle")
    out = r909.reorder_on_pins(pois, a_, b_, "Alpha Peak", only_if_backtrack=True)
    assert [p["name"] for p in out] == ["Beta Town", "Hill Pagoda", "Alpha Peak"]


# ── 4. practical / ticket copy ───────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sentence", [
    "Tickets to visit the mountain cost about $1.95, and the site is open daily from 6:00 AM to 5:00 PM.",
    "If you come during popular times, expect lines or waiting periods that might slow down your visit.",
    "You can reach the top by a cable car ride up the mountain as part of a half-day tour.",
    "The site is open daily from 6:00 AM to 5:00 PM.",
])
def test_practical_sentences_are_practical(sentence):
    assert s.is_practical(sentence)


@pytest.mark.parametrize("sentence", ["The pagoda was founded in 1850.", "The cable car climbs for fifteen minutes.",
                                      "A long line of monks walks the path at dawn."])
def test_historic_sentences_are_not_practical(sentence):
    assert not s.is_practical(sentence)


def test_practical_copy_is_dropped_on_a_route():
    body = ("The pagoda was founded in 1850. Tickets to visit the mountain cost about $1.95, and the site is open daily "
            "from 6:00 AM to 5:00 PM. If you come during popular times, expect lines or waiting periods that might slow "
            "down your visit. The hall holds a bronze bell.")
    t = tour([("Alpha Peak", body, "")])
    out = s.run_pass(t, None, force=True)
    for bad in ("Tickets", "6:00", "waiting periods"):
        assert bad not in out
    assert "founded in 1850" in out and "bronze bell" in out


# ── 5. the closing variant on the route path ─────────────────────────────────────────────────────────────
CLOSING = ("Together, these stops highlight the rich cultural and historical significance of Alpha Peak and its "
           "surroundings. That's 3 stops in all.")


def test_closing_variant_is_dropped_on_the_route_path_not_only_in_content_pass():
    r909.set_request("Origin Strand to Alpha Peak, Delta Province", "vehicle")
    t = tour([("Origin Strand", "A quiet beach.", "Drive on."), ("Beta Town", "A market town.", "Go to Alpha Peak."),
              ("Alpha Peak", "A mountain with a cable car.", "")], closing=CLOSING)
    assert len(rc._stop_blocks(t)) == 3 and not rc.active()          # the 906 content_pass scope test is False here
    out = f906.run_pass(t, None)
    assert "Together, these stops" not in out and "That's 3 stops in all." in out


# ── 6. measure fallback ──────────────────────────────────────────────────────────────────────────────────
def test_measure_conflict_falls_back_to_the_other_stops_article_value():
    art = "The reclining Buddha statue is 69 meters long and 18 meters high."
    de.add({"<Pagoda>": [{"text": "The pagoda stands on the slope.", "kind": "article"}],
            "<Statue>": [{"text": art, "kind": "article"}]}, "889")
    ev = {"<Pagoda>": "The pagoda stands on the slope.", "<Statue>": art}
    t = tour([("<Pagoda>", "Behind the main hall you see a reclining Buddha statue that is 49 meters long and 11 meters "
                           "high. Pilgrims climb the stairs.", "Go on."),
              ("<Statue>", art + " It faces east.", "")])
    logs = []
    out = k.resolve_measure_conflicts(t, ev, logs.append)
    assert "69 meters long" in out and "18 meters high" in out and "49 meters" not in out
    assert any("[LOCAL-906O]" in x for x in logs)
