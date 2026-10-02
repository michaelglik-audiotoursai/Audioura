"""[LOCAL-557] A restaurant request that names ONE restaurant gets that restaurant.

2026-10-01, Preview: "restaurant tour of Boston Sail Loft, Boston, MA", 1 stop,
delivered Union Oyster House. Intent read "Sail Loft" as a theme ("sailing
locations"), left venue_name null, but said scope_precision BUILDING.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generate_tour_text import named_venue_stop, _apply_named_waypoints

# The intent the model actually returned for Michael's request.
SAIL_LOFT_INTENT = {
    "poi_type": "sailing locations", "location": "Boston, MA", "venue_name": None,
    "geographic_scope": "Boston Sail Loft, Boston, MA", "scope_precision": "BUILDING",
}
REQ = "Boston Sail Loft, Boston, MA"


def _poi(name):
    return {"name": name}


def test_named_restaurant_is_extracted():
    assert named_venue_stop(SAIL_LOFT_INTENT, "restaurant", REQ) == "Boston Sail Loft"


def test_named_restaurant_becomes_stop_one_when_absent_from_candidates():
    # Phase 3A's real candidates for this request.
    pois = [_poi("Union Oyster House"), _poi("Legal Sea Foods - Long Wharf"),
            _poi("The Chart House")]
    nv = named_venue_stop(SAIL_LOFT_INTENT, "restaurant", REQ)
    out, inserted = _apply_named_waypoints(pois, REQ, _poi, extra=[nv])
    assert inserted == ["Boston Sail Loft"]
    assert out[0]["name"] == "Boston Sail Loft" and out[0]["user_explicit"] is True


def test_existing_candidate_is_marked_not_duplicated():
    pois = [_poi("The Boston Sail Loft"), _poi("Union Oyster House")]
    out, inserted = _apply_named_waypoints(pois, REQ, _poi, extra=["Boston Sail Loft"])
    assert inserted == [] and len(out) == 2 and out[0].get("user_explicit") is True


def test_not_a_named_restaurant():
    base = dict(SAIL_LOFT_INTENT)
    assert named_venue_stop(base, "walking", REQ) is None                  # other category
    assert named_venue_stop(dict(base, scope_precision="DISTRICT"), "restaurant", REQ) is None
    assert named_venue_stop(dict(base, geographic_scope="Boston, MA"), "restaurant", REQ) is None
    assert named_venue_stop(dict(base, geographic_scope="Prudential Center"), "restaurant",
                            "Restaurant tour near the Prudential Center, Boston") is None
    assert named_venue_stop(None, "restaurant", REQ) is None


# The intent the model returned for Michael's second request, 2026-10-01: the
# restaurant was dropped and its branch label became the DISTRICT scope.
from generate_tour_text import named_restaurant_stops
BB_REQ = "restaurant tour of Buttermilk & Bourbon - Back Bay, Boston, Ma"
BB_INTENT = {"poi_type": "restaurants", "location": "Boston, MA", "venue_name": None,
             "geographic_scope": "Back Bay, Boston, Ma", "scope_precision": "DISTRICT",
             "named_places": ["Buttermilk & Bourbon"]}


def test_named_places_survive_a_district_scope():
    assert named_restaurant_stops(BB_INTENT, "restaurant", BB_REQ) == ["Buttermilk & Bourbon"]


def test_building_fallback_still_works_without_named_places():
    assert named_restaurant_stops(SAIL_LOFT_INTENT, "restaurant", REQ) == ["Boston Sail Loft"]


def test_both_sources_deduplicate():
    i = dict(SAIL_LOFT_INTENT, named_places=["Boston Sail Loft"])
    assert named_restaurant_stops(i, "restaurant", REQ) == ["Boston Sail Loft"]


def test_invented_name_is_refused():
    i = dict(BB_INTENT, named_places=["Grill 23 & Bar"])
    assert named_restaurant_stops(i, "restaurant", BB_REQ) == []


def test_several_named_keep_request_order():
    req = "Dinner at Sycamore and Little Big Diner in Newton Centre"
    i = {"named_places": ["Sycamore", "Little Big Diner"], "scope_precision": "DISTRICT",
         "geographic_scope": "Newton Centre", "location": "Newton, MA"}
    names = named_restaurant_stops(i, "restaurant", req)
    out, _ = _apply_named_waypoints([_poi("Farmstead Table")], req, _poi,
                                    extra=list(reversed(names)))
    assert [p["name"] for p in out][:2] == ["Sycamore", "Little Big Diner"]


def test_other_categories_ignore_named_places():
    assert named_restaurant_stops(BB_INTENT, "walking", BB_REQ) == []


def test_category_word_is_not_part_of_the_name():
    req = "chart house restaurant tour, Boston, MA"
    i = {"named_places": ["Chart House Restaurant"], "scope_precision": None,
         "geographic_scope": None, "location": "Boston, MA"}
    assert named_restaurant_stops(i, "restaurant", req) == ["Chart House"]
