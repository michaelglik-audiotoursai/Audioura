"""[LOCAL-906P] Elevation is not a height, the owner of a fact, the hedge as the last word, junk, a glued sentence, a sea pin and a
detour, route copy, the cable car's numbers. $0: no network, no key. Generic names only (D769)."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SERPER_API_KEY", None)
os.environ["THIN_STOP_SEARCH"] = "0"

import delivery_evidence_906h as de  # noqa: E402
import leftovers_906f as f906  # noqa: E402
import owner_junk_906p as o  # noqa: E402
import refill_quality_906k as k  # noqa: E402
import route_content_896 as rc  # noqa: E402
import route_leftovers_906 as l906  # noqa: E402
import route_order_909 as r909  # noqa: E402
import scope_906o as s906o  # noqa: E402


@pytest.fixture(autouse=True)
def _job():
    r909.clear()
    with rc.job_scope("t906p"):
        rc.set_evidence_904({})
        de.clear()
        yield
    r909.clear()


def tour(stops, closing="That's 2 stops in all."):
    out = "Step-by-step audio guided tour of Alpha Peak is a walking tour.\n\n"
    for n, (title, body) in enumerate(stops, 1):
        out += f"Stop {n}: {title}\n\nCoordinates: 10.{n}, 100.{n}\n\nType/Specialty: Landmark\n\n{body}\n\nDirections: Walk on.\n\n"
    return out + closing + "\n"


def stop_body(text, n):
    blocks = rc._stop_blocks(text)
    s, e, _n, _t = blocks[n - 1]
    return text[s:e]


# ── 1. elevation is never a structure's height ───────────────────────────────────────────────────────────
ART_STATUE = "The statue is 49 meters long and 7 meters high."
ART_MOUNTAIN = "At the summit, 563 meters above sea level, two pagodas stand. The mountain is 563 meters high."


def test_elevation_is_not_a_measure():
    assert k.measures("At the summit, the height of 563 meters above sea level is reached.") == []
    assert k.measures("The mountain rises 563 meters high.") == []
    assert k.measures("The peak is 563 m high a.s.l.") == []
    assert [m["raw"] for m in k.measures("The statue is 7 meters high.")] == ["7 meters high"]


def test_measure_swap_never_takes_the_mountains_value_nor_splices_raw_text():
    de.add({"Alpha Peak": [{"text": ART_MOUNTAIN + " " + ART_STATUE, "kind": "article"}]}, "889")
    body = ("You are standing near the 49-meter-long Reclining Buddha statue, which is 11 meters high and one of the largest "
            "in the region.")
    t = tour([("Alpha Peak", body), ("Reclining Buddha", "The statue is a place of pilgrimage.")])
    logs = []
    out = k.resolve_measure_conflicts(t, None, logs.append)
    assert "563" not in out and "height of" not in out
    assert "which is 7 meters high and one of the largest" in out
    assert any("conflicting height (11 meters high vs 7 meters high)" in x for x in logs)


def test_a_value_not_tied_to_the_object_is_not_used():
    # the evidence's only height belongs to the MOUNTAIN, not the statue: the body keeps what it has
    de.add({"Alpha Peak": [{"text": "The mountain is 650 meters high.", "kind": "article"}]}, "889")
    t = tour([("Alpha Peak", "The statue here is 11 meters high."), ("Beta", "A quiet place with a long history.")])
    out = k.resolve_measure_conflicts(t, None)
    assert "11 meters high" in out and "650" not in out


def test_raw_splice_clause_is_cut_and_stays_grammatical():
    x = "You see the 49-meter-long Buddha statue, which is height of 563 meters and one of the largest in Asia."
    new, did = k.fix_bad_splice(x)
    assert did and "height of" not in new and "which is one of the largest in Asia." in new
    new2, did2 = k.fix_bad_splice("The statue stands here, which is height of 563 meters.")
    assert did2 and new2 == "The statue stands here."


def test_rewrite_keeps_the_bodys_own_wording():
    a = k.measures("a 7-meter-high statue")[0]
    b = k.measures("it is 11 meters high")[0]
    assert k.rewrite_measure(a, b) == "11-meter-high" and k.rewrite_measure(b, a) == "7 meters high"


# ── 2. a statue fact stays with the statue stop even when it names the mountain ─────────────────────────
def test_owner_prefers_the_object_over_its_enclosing_place():
    titles = ["Alpha Mountain", "Reclining Buddha"]
    s = "The Reclining Buddha statue here on Alpha Mountain is 49 meters long."
    assert f906._owner(s, titles) == 1
    assert f906._owner("Alpha Mountain is 28 kilometers west of town.", titles) == 0


def test_statue_facts_are_not_cut_from_the_statue_stop():
    stat = "The Reclining Buddha statue here on Alpha Mountain is 49 meters long."
    t = tour([("Alpha Mountain", "The mountain draws walkers. " + stat + " Pagodas stand at the summit."),
              ("Reclining Buddha", stat + " It was begun in 1958. The site is peaceful.")])
    logs = []
    out = f906.drop_cross_stop_fact(t, None, logs.append)
    assert stat in stop_body(out, 2)                      # the statue stop keeps its measure
    assert stat not in stop_body(out, 1)                  # and the mountain stop does not carry it
    assert not any("belongs to stop 1" in x for x in logs)


# ── 3. record claims: hedged as the last word ───────────────────────────────────────────────────────────
HEDGE_EV = "The statue was the longest reclining Buddha in Vietnam until 2020 and remains one of the largest in Southeast Asia."


def test_unhedged_record_is_hedged_by_the_evidence():
    de.add({"Reclining Buddha": [{"text": HEDGE_EV, "kind": "article"}]}, "889")
    t = tour([("Reclining Buddha", "This statue is the longest Reclining Buddha in Vietnam. It was begun in 1958."),
              ("Beta", "A quiet place.")])
    logs = []
    out = o.hedge_guard(t, None, logs.append)
    assert "one of the longest Reclining Buddhas in Vietnam" in out and "is the longest" not in out
    assert any("[LOCAL-906P]" in x and "hedged" in x for x in logs)


def test_one_stop_never_says_both_one_of_the_largest_and_the_biggest():
    t = tour([("Reclining Buddha", "The statue is one of the largest in Southeast Asia. "
                                   "The statue is the biggest Reclining Buddha in Vietnam."), ("Beta", "A quiet place.")])
    out = o.hedge_guard(t, None)
    assert "is the biggest" not in out and "one of the biggest Reclining Buddhas in Vietnam" in out


def test_late_added_sentence_is_caught_by_the_final_pass():
    de.add({"Reclining Buddha": [{"text": HEDGE_EV, "kind": "article"}]}, "889")
    t = tour([("Reclining Buddha", "The statue is on a hill. It is calm here."), ("Beta", "A quiet place.")])
    # a refill / key-fact injection adds the unhedged sentence AFTER the scope pass ran
    late = t.replace("It is calm here.", "It is calm here. The statue is the longest Reclining Buddha in Vietnam.")
    out = o.final_pass(late, None)
    assert "is the longest" not in out and "one of the longest" in out


def test_hedge_guard_leaves_a_supported_stop_alone():
    t = tour([("Reclining Buddha", "The statue is on a hill. It is calm here."), ("Beta", "A quiet place.")])
    assert o.hedge_guard(t, None) == t


# ── 4. junk ──────────────────────────────────────────────────────────────────────────────────────────────
def test_caption_and_list_stub_dropped_normal_sentence_kept():
    body = ("The ward borders the sea and has two beaches. A person observes a polluted beach with trash washed ashore. "
            "The ward is geographically located as follows: - To the east and south, it borders the Sea. "
            "The old market sells fresh fish every morning.")
    t = tour([("Alpha Ward", body), ("Beta", "A quiet place.")])
    logs = []
    out = o.drop_junk(t, logs.append)
    b = stop_body(out, 1)
    assert "A person observes" not in b and "located as follows" not in b and "- To the east" not in b
    assert "The ward borders the sea and has two beaches." in b and "The old market sells fresh fish" in b
    assert sum("[LOCAL-906P]" in x for x in logs) == 2


@pytest.mark.parametrize("x,why", [
    ("A person observes a polluted beach with trash washed ashore.", "photo caption"),
    ("Visitors pictured at the temple gate.", "photo caption"),
    ("Photo of the harbor at dawn.", "photo caption"),
    ("The border runs as follows:", "list stub"),
    ("It borders: - the sea - the river.", "list stub"),
    ("The ward is located as follows.", "list stub"),
])
def test_junk_reasons(x, why):
    assert o.junk_reason(x) == why


@pytest.mark.parametrize("x", [
    "A monk named Tran built the first pagoda here in 1887.",
    "The harbor was busy in the morning - boats came in early.",
    "The museum holds a photograph of the founder.",
])
def test_normal_sentences_are_not_junk(x):
    assert o.junk_reason(x) is None


def test_refill_bar_refuses_junk():
    assert k.refill_reject("A person observes a polluted beach with trash washed ashore.", "Alpha Ward") is not None


# ── 5. the glued sentence ───────────────────────────────────────────────────────────────────────────────
GLUED = ("Over time, Vietnamese pronunciation transformed the name of this stronghold into Beta Town, a linguistic testimony to "
         "the region's origins and the complex cultural shifts that shaped The Gamma River, once known as the Delta River when "
         "the town was first established, runs some 7.2 kilometers through the city.")


def test_glued_fragment_is_dropped():
    right = o.glued_split(GLUED)
    assert right.startswith("The Gamma River, once known as") and right.endswith("through the city.")
    t = tour([("Beta Town", GLUED + " The market is lively."), ("Beta", "A quiet place.")])
    out = o.fix_glued(t)
    assert "shaped The" not in out and "Over time" not in out and "The Gamma River, once known as" in out


@pytest.mark.parametrize("x", [
    "The article was first published in The New York Times Magazine, once known for its long features.",
    "Over the centuries the district became known as The Hague, once a hunting ground for the counts of the region.",
    "The tower stands near the river, and The Gamma River runs through the city every year in spring.",
])
def test_legitimate_capital_the_is_kept(x):
    assert o.glued_split(x) is None


# ── 6. a sea pin is re-resolved; a detour is replaced ───────────────────────────────────────────────────
def test_sea_pin_is_re_resolved_by_the_place_reference_chain():
    pois = [{"name": "Gamma Lighthouse", "coordinates": "10.5556, 108.2600", "latitude": 10.5556, "longitude": 108.26},
            {"name": "Alpha Peak", "coordinates": "10.8167, 107.8833", "latitude": 10.8167, "longitude": 107.8833}]
    seen = []

    def resolve(name):
        seen.append(name)
        return {"lat": 10.9, "lng": 108.0} if name == "Gamma Lighthouse" else None
    logs = []
    ch = r909.rereference_pins(pois, resolve, lambda la, ln: False if la < 10.6 else True, "Alpha Peak", log=logs.append)
    assert ch == [0] and seen == ["Gamma Lighthouse"]          # the destination keeps its own handling
    assert r909._poi_pin(pois[0]) == (10.9, 108.0) and not pois[0].get("_pin_water_909")
    assert any("[LOCAL-906P]" in x and "over water" in x for x in logs)


def test_pin_far_from_its_reference_is_re_resolved_but_a_near_one_is_kept():
    pois = [{"name": "Gamma Lighthouse", "coordinates": "10.60, 108.30", "latitude": 10.60, "longitude": 108.30},
            {"name": "Delta Falls", "coordinates": "10.90, 108.00", "latitude": 10.90, "longitude": 108.00}]
    refs = {"Gamma Lighthouse": (10.80, 108.10), "Delta Falls": (10.905, 108.002)}
    ch = r909.rereference_pins(pois, lambda n: refs[n], lambda la, ln: True)
    assert ch == [0] and r909._poi_pin(pois[1]) == (10.90, 108.00)


def test_water_pin_with_no_reference_is_flagged_not_trusted():
    pois = [{"name": "Gamma Lighthouse", "coordinates": "10.5556, 108.2600", "latitude": 10.5556, "longitude": 108.26}]
    r909.rereference_pins(pois, lambda n: None, lambda la, ln: False)
    assert pois[0].get("_pin_water_909") is True


A, B = (10.93, 108.10), (10.81, 107.88)


def poi(name, lat, lng):
    return {"name": name, "coordinates": f"{lat}, {lng}", "latitude": lat, "longitude": lng}


def test_detour_over_60_percent_is_replaced_from_the_pool():
    far = poi("Gamma Lighthouse", 10.50, 108.30)                  # ~50 km off a ~28 km drive
    ok = poi("Delta Falls", 10.88, 108.00)
    pool = [poi("Far Cape", 10.40, 108.40), poi("Epsilon Pagoda", 10.87, 107.98)]
    logs = []
    out = r909.replace_detours([far, ok], A, B, pool, "Alpha Peak", log=logs.append)
    assert [p["name"] for p in out] == ["Epsilon Pagoda", "Delta Falls"]
    assert r909.detour_ratio(r909._poi_pin(far), A, B) > 0.6 and r909.detour_ratio(r909._poi_pin(out[0]), A, B) < 0.6
    assert any("detour" in x and "replaced" in x for x in logs)


def test_detour_stays_when_the_pool_has_nothing_better_and_the_destination_is_never_replaced():
    far = poi("Gamma Lighthouse", 10.50, 108.30)
    dest = poi("Alpha Peak", 10.40, 108.50)
    out = r909.replace_detours([far, dest], A, B, [poi("Far Cape", 10.40, 108.40)], "Alpha Peak")
    assert [p["name"] for p in out] == ["Gamma Lighthouse", "Alpha Peak"]


# ── 6b. route copy and the closing ──────────────────────────────────────────────────────────────────────
def test_tours_from_x_often_include_is_operator_copy():
    for x in ("Tours from Origin City often include the Fairy Stream as part of day trips to Beta Town.",
              "Tours from Origin City often include the Fairy Stream.",
              "The stream is often visited as part of day trips to Beta Town."):
        assert s906o.is_practical(x), x
    assert not s906o.is_practical("The stream runs between red clay cliffs.")
    t = tour([("Fairy Stream", "The stream runs between cliffs. Tours from Origin City often include the Fairy Stream as part of "
                               "day trips to Beta Town. You can walk barefoot."), ("Beta", "A quiet place.")])
    assert "Tours from" not in s906o.drop_practical(t)


CLOSE = ("Exploring these remarkable landmarks, like the tallest lighthouse and the longest reclining Buddha statue, highlights "
         "the unique charm and allure of this destination.")


def test_exploring_these_highlights_closing_is_template_filler():
    assert l906._FILLER_CLOSING.match(CLOSE)
    t = tour([("Alpha", "A quiet place on a hill."), ("Beta", "A harbor with boats.\n\n" + CLOSE)], "That's 2 stops in all.")
    out = l906.drop_template_closing(t)
    assert "Exploring these" not in out and "That's 2 stops in all." in out


def test_unsupported_superlative_never_appears_in_the_closing():
    t = tour([("Alpha", "A quiet place on a hill with a lighthouse."), ("Beta", "A harbor with boats.")],
             "A wonderful drive, with the tallest lighthouse in the country along the way. That's 2 stops in all.")
    logs = []
    out = o.closing_claims(t, logs.append)
    assert "tallest lighthouse" not in out and "That's 2 stops in all." in out
    assert any("closing: superlative" in x for x in logs)
    # a superlative that a stop states stays
    t2 = tour([("Alpha", "It is the tallest lighthouse on the coast."), ("Beta", "A harbor.")],
              "Enjoy the tallest lighthouse once more. That's 2 stops in all.")
    assert "tallest lighthouse once more" in o.closing_claims(t2)


# ── 7. the cable car's numbers ─────────────────────────────────────────────────────────────────────────────
CABLE_EV = ("The mountain is 650 meters high. The cable car covers a total length of 7,455 meters. "
            "A modern cable car system designed in Austria carries visitors to the pagodas.")
CABLE = ("You are about to take a cable car ride on Alpha Peak. The cable car covers a total length of 7,455 meters. "
         "It ascends 1,279 meters from the base to the peak. The system is modern and designed in Austria.")


def test_rise_above_the_known_elevation_is_dropped_and_logged():
    de.add({"Alpha Peak": [{"text": CABLE_EV, "kind": "article"}]}, "889")
    t = tour([("Alpha Peak", CABLE), ("Beta", "A quiet place.")])
    logs = []
    out = o.cable_car_numbers(t, None, logs.append)
    b = stop_body(out, 1)
    assert "1,279" not in b and "7,455 meters" in b and "designed in Austria" in b
    assert any("[LOCAL-906P]" in x and "exceeds the place's known elevation" in x for x in logs)


def test_an_untraceable_cable_number_is_dropped_and_a_traceable_one_kept():
    de.add({"Alpha Peak": [{"text": "The cable car covers a total length of 7,455 meters. It climbs to the summit.", "kind": "article"}]},
           "889")
    t = tour([("Alpha Peak", "The cable car covers a total length of 7,455 meters. It ascends 900 meters from the base to the peak. "
                             "The ride is smooth."), ("Beta", "A quiet place.")])
    logs = []
    out = o.cable_car_numbers(t, None, logs.append)
    b = stop_body(out, 1)
    assert "900 meters" not in b and "7,455 meters" in b
    assert any("in no evidence of the stop" in x for x in logs)


def test_non_cable_sentences_with_numbers_are_untouched():
    de.add({"Alpha Peak": [{"text": CABLE_EV, "kind": "article"}]}, "889")
    t = tour([("Alpha Peak", "The pagoda was built 500 meters from the gate. The tower rises 40 meters above the square."),
              ("Beta", "A quiet place.")])
    assert o.cable_car_numbers(t, None) == t


def test_place_elevations():
    assert o.place_elevations("At the summit, 563 meters above sea level.") == [563.0]
    assert o.place_elevations("It has an elevation of 1,200 m.") == [1200.0]
    assert o.place_elevations("The cable car is 7,455 meters long.") == []


# ── the whole pass: nothing raises, a clean tour is unchanged ──────────────────────────────────────────────
def test_run_pass_leaves_a_clean_tour_alone():
    t = tour([("Alpha", "A quiet place on a hill. The view is wide."), ("Beta", "A harbor with boats. The market is busy.")])
    assert o.run_pass(t, None) == t and o.final_pass(t, None) == t
