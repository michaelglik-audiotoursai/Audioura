"""[LOCAL-556] A restaurant request that names ONE restaurant gets that restaurant.

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
