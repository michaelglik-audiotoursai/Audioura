"""LOCAL-906E -- 906D's "province box" was a ward-sized box (a city that took the old province's name).
Offline, $0, generic fixtures (D769). Every lookup is mocked."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SERPER_API_KEY", None)
os.environ["THIN_STOP_SEARCH"] = "0"

import derepetition_guard as dg  # noqa: E402
import leftovers_906c as c906c  # noqa: E402
import pin_fallback_906d as pf  # noqa: E402
import pin_snap  # noqa: E402

PROVINCE, COUNTRY = "Beta Province", "Gamma"
WARD_BOX = [10.9208, 11.0331, 108.0054, 108.1035]          # ~12 x 11 km
WARD_CENTRE = (10.9375, 108.0878)
COARSE = (10.90, 107.90)                                   # the area resolver's centre, in the real province
SITE = (10.8281, 107.8828)                                 # the right reference, 2.1 km from the real site
MODEL_PIN = (11.0900, 108.2300)                            # the model's pin, ~28 km from the site
PROVINCE_BOX = [10.60, 11.45, 107.50, 108.40]              # a sane province-sized box (~95 x 100 km)


def _ward_row(**extra):
    row = {"category": "boundary", "type": "administrative", "addresstype": "city", "lat": "10.9375",
           "lon": "108.0878", "boundingbox": [str(b) for b in WARD_BOX], "extratags": {"admin_level": "6"}}
    row.update(extra)
    return row


def _province_row(**extra):
    row = {"category": "boundary", "type": "administrative", "addresstype": "state", "lat": "11.03",
           "lon": "107.95", "boundingbox": [str(b) for b in PROVINCE_BOX], "extratags": {"admin_level": "4"}}
    row.update(extra)
    return row


# ── 1. the sanity check ──────────────────────────────────────────────────────────────────────────────────
def test_ward_sized_box_is_rejected_and_logged_no_box():
    logs = []
    pb = pf.province_box(PROVINCE, COUNTRY, search_fn=lambda q: [_ward_row()], wikidata_fn=lambda n: None,
                         log=logs.append, coarse_center=COARSE)
    assert pb is None
    assert any("[LOCAL-906E] province box rejected:" in x for x in logs), logs


@pytest.mark.parametrize("extra", [{"addresstype": "suburb"}, {"addresstype": "municipality"},
                                   {"addresstype": "city_district"}])
def test_lower_admin_types_are_rejected_even_when_big_enough(extra):
    row = _province_row(extratags={}, **extra)
    assert pf.province_box(PROVINCE, search_fn=lambda q: [row], wikidata_fn=lambda n: None) is None


def test_admin_level_6_rejected_even_with_state_addresstype():
    row = _province_row(extratags={"admin_level": "6"})
    assert pf.province_box(PROVINCE, search_fn=lambda q: [row], wikidata_fn=lambda n: None) is None


def test_box_must_hold_the_coarse_centre():
    pb = pf.province_box(PROVINCE, search_fn=lambda q: [_province_row()], wikidata_fn=lambda n: None,
                         coarse_center=(20.0, 120.0))
    assert pb is None
    pb = pf.province_box(PROVINCE, search_fn=lambda q: [_province_row()], wikidata_fn=lambda n: None,
                         coarse_center=COARSE)
    assert pb and pb["box"] == PROVINCE_BOX


def test_sane_province_row_is_accepted_without_coarse_centre():
    pb = pf.province_box(PROVINCE, COUNTRY, search_fn=lambda q: [_province_row()])
    assert pb and pb["source"] == "geocoder_admin_boundary"


def test_dissolved_province_falls_back_to_wikidata_square():
    logs = []
    pb = pf.province_box(PROVINCE, COUNTRY, search_fn=lambda q: [_ward_row()],
                         wikidata_fn=lambda n: [(10.85, 107.95, 100.0), (11.0, 107.9, 7800.0)],
                         log=logs.append, coarse_center=COARSE)
    assert pb and pb["source"] == "wikidata_p625_area" and pb["center"] == (11.0, 107.9)
    assert pf.box_area_km2(pb["box"]) > 5000
    assert pf.in_box(COARSE, pb["box"])


def test_wikidata_tiny_area_or_far_from_coarse_centre_is_rejected():
    logs = []
    assert pf.province_box(PROVINCE, search_fn=lambda q: [], wikidata_fn=lambda n: (10.9, 108.0, 130.0),
                           log=logs.append) is None
    assert pf.province_box(PROVINCE, search_fn=lambda q: [], wikidata_fn=lambda n: (30.0, 108.0, 7800.0),
                           log=logs.append, coarse_center=COARSE) is None
    assert sum("province box rejected" in x for x in logs) == 2


# ── 2. the box is a fallback ─────────────────────────────────────────────────────────────────────────────
def _live_ref(monkeypatch, ref_name="Alpha Mountain"):
    def fake(title, scope, *a, **k):
        return {"lat": SITE[0], "lng": SITE[1], "source": "serper", "name": ref_name, "precision": "place"}
    monkeypatch.setattr(pin_snap, "reference_for", fake, raising=False)


def test_ward_box_never_refuses_the_reference_the_earlier_rules_accept():
    """The logged shape, even if a ward-sized box slipped through: the 2.1 km reference is accepted by the
    coarse-centre rule, no pin moves to the ward centre."""
    pois = [{"name": "Alpha Mountain", "coordinates": f"{MODEL_PIN[0]}, {MODEL_PIN[1]}"},
            {"name": "Alpha Statue", "coordinates": f"{MODEL_PIN[0] + .005}, {MODEL_PIN[1]}"}]
    ref = lambda title, *a, **k: (SITE[0], SITE[1], "serper", "Alpha Mountain")  # noqa: E731
    logs = []
    box = pf.pad_box(WARD_BOX)
    pois, rows = pin_snap.snap_poi_coordinates(
        pois, scope=PROVINCE, scope_center=None, scope_bbox=box, coarse_center=COARSE, province_box=box,
        scope_bbox_is_fallback=True, reference_fn=ref, log=logs.append)
    assert rows[0]["snapped"] and rows[0]["new_coordinate"] == pytest.approx(SITE, abs=1e-6), (rows, logs)
    assert not any("snap refused" in x and "outside the scope" in x for x in logs)
    moved = pf.last_resort_pins(pois, rows, WARD_BOX, WARD_CENTRE, PROVINCE, log=logs.append, pad_km=20.0)
    assert not [p for p in pois if p.get("_pin_province_centre_906d")]
    assert pin_snap._poi_coord(pois[0]) == pytest.approx(SITE, abs=1e-5)
    assert 0 not in moved


def test_padded_box_includes_a_pin_within_20_km():
    b = pf.pad_box(PROVINCE_BOX)
    assert pf.in_box((PROVINCE_BOX[1] + 0.15, 108.0), b)           # ~17 km north of the edge
    assert not pf.in_box((PROVINCE_BOX[1] + 0.30, 108.0), b)       # ~33 km


# ── 3. the last resort only moves a pin that is far from everything ──────────────────────────────────────
def test_sane_province_box_still_catches_a_far_pin():
    pois = [{"name": "A", "coordinates": "12.5, 105.0"}]
    moved = pf.last_resort_pins(pois, [{"snapped": False, "reference": None}], pf.pad_box(PROVINCE_BOX), (11.03, 107.95),
                                PROVINCE, log=lambda m: None)
    assert moved == [0] and pois[0]["_pin_province_centre_906d"]


def test_no_centre_move_when_another_stop_has_an_accepted_reference_outside_the_box():
    box = pf.pad_box(WARD_BOX)
    far_ref = (10.0, 107.0)                      # accepted by the earlier rules, outside the padded ward box
    pois = [{"name": "A", "coordinates": "11.4, 108.6"}, {"name": "B", "coordinates": f"{far_ref[0]}, {far_ref[1]}"}]
    rows = [{"snapped": False, "reference": None},
            {"snapped": True, "new_coordinate": far_ref, "reference": far_ref}]
    logs = []
    assert pf.last_resort_pins(pois, rows, box, WARD_CENTRE, PROVINCE, log=logs.append) == []
    assert pois[0]["coordinates"] == "11.4, 108.6"
    assert any("centre is not used" in x for x in logs)


def test_never_moves_onto_a_centre_farther_from_its_own_reference():
    pois = [{"name": "A", "coordinates": "12.0, 104.0"}]
    own = (12.01, 104.01)
    rows = [{"snapped": False, "reference": own}]
    logs = []
    assert pf.last_resort_pins(pois, rows, PROVINCE_BOX, (11.0, 108.0), PROVINCE, log=logs.append) == []
    assert any("farther from its own reference" in x for x in logs)


# ── 4. the address follows only a correct move ───────────────────────────────────────────────────────────
def test_approximate_centre_pin_never_adopts_a_street_from_the_reverse_geocode():
    p = {"name": "Alpha Mountain", "address": "Alpha Mountain, Some Street, Beta City, Beta Province, Gamma",
         "coordinates": "10.9375, 108.0878", "_pin_moved_906d": True, "_pin_province_centre_906d": True}
    changed = pf.address_follows_pin(p, PROVINCE, COUNTRY,
                                     reverse_fn=lambda la, lo: "Some Street, Beta City, Beta Province, Gamma")
    assert changed and p["address"] == "Alpha Mountain, Beta Province, Gamma"


def test_pin_moved_to_another_stop_gets_name_province_country_only():
    p = {"name": "Alpha Statue", "address": "Nguyen Street, Beta City, Beta Province, Gamma",
         "coordinates": "11.0, 108.3", "_pin_moved_906d": True, "_pin_moved_to_stop": 0}
    assert pf.address_follows_pin(p, PROVINCE, COUNTRY, reverse_fn=lambda la, lo: "Nguyen Street, Beta City")
    assert p["address"] == "Alpha Statue, Beta Province, Gamma"


# ── 5. a body that opens with a pronoun ──────────────────────────────────────────────────────────────────
def _tour(body):
    return (f"Stop 1: Alpha Mountain\n\nCoordinates: 1.0, 2.0\n\nIt rises above the plain and is climbed daily.\n\n"
            f"Directions: Walk on to Alpha Statue.\nStop 2: Alpha Statue\n\nCoordinates: 1.0, 2.0\n\n{body}\n\n"
            f"That's 2 stops in all.\n")


@pytest.mark.parametrize("body,expect", [
    ("Its white color stands out against the green backdrop. It was built in 1962.",
     "The Alpha Statue's white color stands out against the green backdrop. It was built in 1962."),
    ("It stands on a hill. A path leads up.", "The Alpha Statue stands on a hill. A path leads up."),
    ("They are made of stone. Visitors climb.", "The Alpha Statue are made of stone. Visitors climb."),
    ("This statue represents a seated figure. Visitors climb.",
     "The Alpha Statue represents a seated figure. Visitors climb."),
    ("This is the largest of its kind. Visitors climb.", "The Alpha Statue is the largest of its kind. Visitors climb."),
])
def test_pronoun_opener_is_repaired_with_the_title(body, expect):
    logs = []
    out = c906c.repair_pronoun_opener(_tour(body), logs.append)
    assert expect in out
    assert any("[LOCAL-906E]" in x for x in logs)


@pytest.mark.parametrize("body", [
    "The statue stands on a hill. It is white.",
    "This temple was founded in 1900. Visitors climb.",       # carries its own noun
    "Built in 1962, it is white. Visitors climb.",
])
def test_non_dangling_openers_are_untouched(body):
    t = _tour(body)
    assert c906c.repair_pronoun_opener(t, None).split("Stop 2:")[1] == t.split("Stop 2:")[1]


def test_pronoun_repair_is_part_of_the_final_pass():
    out = c906c.final_pass(_tour("Its white color stands out against the green backdrop. It was built in 1962."), {}, None)
    assert "The Alpha Statue's white color" in out


# ── 6. the 49 m fact (told at the mountain stop, dropped there as off-topic) ─────────────────────────────
FACT_TOUR = (
    "Welcome to the tour.\n"
    "Stop 1: Ta Mountain\nAddress: x\nCoordinates: 1.0, 2.0\n\n"
    "Visitors reach the summit by cable car or on foot through the forest. The path is lined with old trees and "
    "small shrines. Measuring 49 meters long and 7 meters high, this reclining Buddha is the longest of its kind "
    "in the region. Many people stop to rest at the viewpoints before going on.\n\n"
    "Directions: Walk on to Reclining Buddha Statue.\n"
    "Stop 2: Reclining Buddha Statue\nAddress: y\nCoordinates: 1.0, 2.0\n\n"
    "Here the figure lies along the slope facing the valley and the morning light. Measuring an imposing 49 meters "
    "in length and standing 7 meters high, this white figure is the longest of its kind. Pilgrims leave flowers "
    "at its feet during the festival season every year.\n\n"
    "That's 2 stops in all.\n")


def test_size_fact_stays_with_the_stop_it_names():
    out, acts = dg.strip_repeated_facts(FACT_TOUR, min_remaining_words=10)
    s1, s2 = out.split("Stop 2:")
    assert "49 meters" not in s1 and "49 meters" in s2
    assert any(a["removed"] and a.get("owner_swapped_906e") for a in acts)


def test_fact_told_first_at_its_own_stop_is_still_removed_from_the_later_stop():
    t = FACT_TOUR.replace("this reclining Buddha is the longest", "this peak is the longest")
    out, acts = dg.strip_repeated_facts(t, min_remaining_words=10)
    assert "49 meters" in out.split("Stop 2:")[0] and "49 meters" not in out.split("Stop 2:")[1]
