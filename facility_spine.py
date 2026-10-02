"""facility_spine.py — LOCAL-480: the stop list for a *facility* tour is a
need-spine, not an interest ranking.

WHY THIS EXISTS
Michael's verdict on tour 423 (Logan Airport, 2026-09-15):

    "…most people would want something related to airport itself: airlines,
     counters, terminals, lost and found, children playgrounds, app such as
     Lyft and Uber pickup locations, parkings, museum exhibits, WiFi, electric
     outlets, etc. But stories are good, funny."

The story engine is working. It was aimed at a sightseer's stop list —
including "Boston Logan Airport Virtual Tour", a thing you cannot stand next
to — because `tour_category == 'walking'` means "sightseeing on foot". A
traveller in Terminal E has an errand, not an afternoon.

THE MODEL
`walking` and `museum` rank candidate stops by how interesting they are.
`facility` fills an ordered checklist of traveller NEEDS, in the sequence a
person actually hits them:

    orient → your terminal & gates → security → food and water → rest
    (seating, outlets, WiFi, quiet) → kids → art and exhibits → lost and found
    → baggage → ground transport (rideshare, taxi, rental, transit, parking)

When the user asks for N stops, we take the N highest-value UNMET needs, not
the N most interesting facts.

FINDABLE OR CUT
For a story, failing verification costs a sentence. For a facility it costs the
stop (Yury, LOCAL-471: "you may lose a couple of hours if you follow these
directions"). Every need slot here is filled from a mapped OSM object that
carries a real coordinate — so the LOCAL-471 `_geo_confidence` signal can drop
a stop that does not verify, rather than downgrade it. The confidence check and
the drop happen in generate_tour_text.py; this module's job is to produce
coordinate-bearing candidates in need order.

THE DATA IS ALREADY THERE, FREE
LEAD measured 331 coordinate-bearing OSM objects at Logan (42.3656, -71.0096)
on 2026-09-15 — 113 gates, 46 parking areas incl. the rideshare pickup,
transit, food, water, art — no API key, no bill. Ten of Michael's fourteen
categories are in open data today; the other four (lost & found, kids' play,
airline check-in counters, charging/WiFi as stops) come from the venue's own
site (`venue_site_source`, the Tier-1 source LOCAL-23 established co-equal with
Wikipedia). We NEVER fabricate a stop for a missing category — a category with
no mapped object and no venue-site entry simply does not fill.

NO SECOND OVERPASS CLIENT
The task is explicit: reuse the existing Overpass path. `osm_venue_facts.py`
already holds `_overpass_request` with the rate-limit lock and retry/backoff.
We import and reuse it. We do NOT open a second client.
"""
import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# The break-the-spine seam (Acceptance criterion 6)
# ---------------------------------------------------------------------------
#
# "Break the spine and show a test go red — with need-slot filling disabled, the
#  airport request must fall back to the old sightseeing list."
#
# fill_need_spine() returns [] the moment this is false, which makes the caller
# in generate_tour_text.py fall through to the normal walking Phase-3A GPT list.
# A test flips this to False and asserts the fallback fires.
def spine_filling_enabled() -> bool:
    """True unless need-slot filling has been explicitly disabled.

    Env override FACILITY_SPINE_DISABLED=1 or setting the module attribute
    SPINE_FILLING_ENABLED=False both disable it. The env read happens every call
    so a test can toggle it without reimporting.
    """
    if os.environ.get("FACILITY_SPINE_DISABLED", "").strip() in ("1", "true", "True"):
        return False
    return SPINE_FILLING_ENABLED


SPINE_FILLING_ENABLED = True


# ---------------------------------------------------------------------------
# The need-spine
# ---------------------------------------------------------------------------
#
# Ordered by the sequence a traveller actually hits each need. `value` is the
# tie-breaker when two needs are both unmet: lower rank = hit sooner = higher
# priority. `radius_m` is how far from the anchor we look for that need's mapped
# object. `osm_filters` are Overpass tag selectors; `[]` means OSM does not map
# this need as a standalone object — it comes from the venue's own site instead.

@dataclass
class NeedSlot:
    key: str
    label: str                       # spoken/stop-facing name of the need
    osm_filters: List[str] = field(default_factory=list)
    radius_m: int = 1500
    venue_site_only: bool = False    # OSM misses this; venue site fills it


# The spine. Order IS the priority. This mirrors the task's sequence exactly.
NEED_SPINE: List[NeedSlot] = [
    NeedSlot("orient", "Main terminal / arrivals hall",
             ['["aeroway"="terminal"]', '["public_transport"="station"]',
              '["building"="terminal"]', '["amenity"="terminal"]'],
             radius_m=2500),
    NeedSlot("terminal_gates", "Your terminal and gates",
             ['["aeroway"="gate"]', '["aeroway"="terminal"]'],
             radius_m=2500),
    NeedSlot("security", "Security checkpoint",
             ['["aeroway"="security_check"]', '["barrier"="security_control"]'],
             radius_m=2000),
    NeedSlot("food_water", "Food and water",
             ['["amenity"~"restaurant|cafe|fast_food|bar|food_court"]',
              '["amenity"="drinking_water"]'],
             radius_m=1500),
    NeedSlot("rest", "Rest — seating, outlets, WiFi, a quiet spot",
             ['["amenity"="lounge"]', '["room"="lounge"]',
              '["leisure"="lounge"]', '["amenity"="charging_station"]'],
             radius_m=1500),
    NeedSlot("kids", "Children's play area",
             ['["leisure"="playground"]', '["amenity"="childcare"]'],
             radius_m=1500, venue_site_only=True),
    NeedSlot("art_exhibits", "Art and exhibits",
             ['["tourism"="artwork"]', '["tourism"="gallery"]',
              '["historic"="memorial"]'],
             radius_m=2000),
    NeedSlot("lost_and_found", "Lost and found",
             ['["office"="lost_and_found"]', '["amenity"="lost_and_found"]'],
             radius_m=2500, venue_site_only=True),
    NeedSlot("baggage", "Baggage claim",
             ['["aeroway"="baggage_claim"]', '["room"="baggage_claim"]'],
             radius_m=2000),
    NeedSlot("ground_transport", "Ground transport — rideshare, taxi, rental, transit, parking",
             ['["amenity"="parking"]', '["amenity"="taxi"]',
              '["amenity"="car_rental"]', '["railway"="station"]',
              '["public_transport"="station"]', '["amenity"="bus_station"]',
              '["amenity"="ferry_terminal"]'],
             radius_m=3000),
]


# ---------------------------------------------------------------------------
# Overpass query per need slot — reuses osm_venue_facts._overpass_request
# ---------------------------------------------------------------------------

def _haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    import math
    R = 6371000.0
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def _build_around_query(slot: NeedSlot, lat: float, lng: float) -> str:
    """One Overpass query for a need slot, using the `around:` radius pattern
    already used by amenities_near_service.py. node+way+relation, tags out."""
    statements = []
    for filt in slot.osm_filters:
        for kind in ("node", "way", "relation"):
            statements.append(f'{kind}{filt}(around:{slot.radius_m},{lat},{lng});')
    union = "\n".join(statements)
    return f'[out:json][timeout:15];\n(\n{union}\n);\nout center tags;'


def _element_coords(el: dict) -> Optional[Tuple[float, float]]:
    """A coordinate for a node (lat/lon) or a way/relation (center)."""
    if el.get("lat") is not None and el.get("lon") is not None:
        return (float(el["lat"]), float(el["lon"]))
    center = el.get("center")
    if center and center.get("lat") is not None and center.get("lon") is not None:
        return (float(center["lat"]), float(center["lon"]))
    return None


def _pick_nearest_named(elements: List[dict], anchor: Tuple[float, float]
                        ) -> Optional[Tuple[dict, Tuple[float, float]]]:
    """The most relevant mapped instance for one need slot: the nearest element
    that carries a name (a nameless node is not a stop a person can be sent to).
    Falls back to the nearest named-or-not if nothing is named."""
    best_named = None
    best_named_d = float("inf")
    best_any = None
    best_any_d = float("inf")
    for el in elements:
        coords = _element_coords(el)
        if coords is None:
            continue
        d = _haversine_m(anchor, coords)
        tags = el.get("tags", {})
        if d < best_any_d:
            best_any_d, best_any = d, (el, coords)
        if tags.get("name") and d < best_named_d:
            best_named_d, best_named = d, (el, coords)
    return best_named or best_any


def _slot_display_name(slot: NeedSlot, el: dict) -> str:
    """A stop name a traveller can act on. Prefer the object's own name; fall
    back to a ref (gate number) or the need label."""
    tags = el.get("tags", {})
    name = tags.get("name")
    if name:
        return name
    ref = tags.get("ref")
    if ref and slot.key == "terminal_gates":
        return f"Gate {ref}"
    if ref:
        return f"{slot.label} ({ref})"
    return slot.label


@dataclass
class FacilityStop:
    name: str
    need_key: str
    need_label: str
    coordinates: str                 # "lat, lng"
    address: str = ""
    source: str = "osm"              # "osm" | "venue_site"
    osm_type: str = ""
    osm_id: Optional[int] = None
    tags: Dict[str, str] = field(default_factory=dict)

    def source_line(self) -> str:
        """The log line that NAMES the source for this stop (AC2)."""
        if self.source == "osm" and self.osm_id is not None:
            return (f"[LOCAL-480] need '{self.need_key}' -> '{self.name}' "
                    f"source=OSM {self.osm_type}/{self.osm_id} "
                    f"({self.coordinates})")
        return (f"[LOCAL-480] need '{self.need_key}' -> '{self.name}' "
                f"source={self.source} ({self.coordinates})")


def _query_one_slot(slot: NeedSlot, lat: float, lng: float,
                    overpass_request: Callable) -> Optional[FacilityStop]:
    """Fill one need slot from OSM. Returns None when nothing is mapped for it
    (findable-or-cut: a need with no mapped object simply does not fill here)."""
    if not slot.osm_filters:
        return None
    query = _build_around_query(slot, lat, lng)
    data = overpass_request(query, context=f"facility:{slot.key}")
    if not data or not data.get("elements"):
        return None
    picked = _pick_nearest_named(data["elements"], (lat, lng))
    if not picked:
        return None
    el, coords = picked
    tags = el.get("tags", {})
    addr = _format_address(tags)
    return FacilityStop(
        name=_slot_display_name(slot, el),
        need_key=slot.key,
        need_label=slot.label,
        coordinates=f"{coords[0]:.6f}, {coords[1]:.6f}",
        address=addr,
        source="osm",
        osm_type=el.get("type", "node"),
        osm_id=el.get("id"),
        tags=tags,
    )


def _format_address(tags: Dict[str, str]) -> str:
    """Assemble a street address from OSM addr:* tags, if present."""
    parts = []
    if tags.get("addr:housenumber") and tags.get("addr:street"):
        parts.append(f"{tags['addr:housenumber']} {tags['addr:street']}")
    elif tags.get("addr:street"):
        parts.append(tags["addr:street"])
    if tags.get("addr:city"):
        parts.append(tags["addr:city"])
    if tags.get("addr:postcode"):
        parts.append(tags["addr:postcode"])
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fill_need_spine(
    lat: float,
    lng: float,
    want: int,
    overpass_request: Optional[Callable] = None,
    venue_site_lookup: Optional[Callable[[NeedSlot], Optional[FacilityStop]]] = None,
) -> List[FacilityStop]:
    """Return the N highest-value UNMET needs, filled with mapped objects.

    Args:
        lat, lng: the facility anchor (e.g. Logan at 42.3656, -71.0096).
        want: how many stops the listener asked for.
        overpass_request: the Overpass client. Defaults to
            osm_venue_facts._overpass_request — the EXISTING client, reused,
            never a second one. Injectable so tests can drive it offline.
        venue_site_lookup: optional callable that fills the four categories OSM
            misses (lost & found, kids, check-in counters, charging/WiFi) from
            the venue's own site. When absent, those slots simply do not fill —
            we never fabricate a stop.

    Returns [] when spine filling is disabled (the break-the-spine seam), which
    makes the caller fall back to the ordinary sightseeing list.
    """
    if not spine_filling_enabled():
        logger.info("[LOCAL-480] need-slot filling DISABLED — caller will fall "
                    "back to the sightseeing list")
        return []

    if overpass_request is None:
        # Reuse the EXISTING Overpass client. No second client (task rule).
        from osm_venue_facts import _overpass_request as overpass_request

    stops: List[FacilityStop] = []
    # Walk the spine in need order; each filled slot is one met need. We stop
    # once we have `want` stops — the N highest-value UNMET needs, by construction
    # (the spine is ordered by the sequence a traveller hits each need).
    for slot in NEED_SPINE:
        if len(stops) >= want:
            break
        stop = None
        if slot.osm_filters:
            try:
                stop = _query_one_slot(slot, lat, lng, overpass_request)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("[LOCAL-480] OSM query failed for need %r: %s",
                               slot.key, e)
                stop = None
        if stop is None and (slot.venue_site_only or slot.osm_filters) and venue_site_lookup:
            try:
                stop = venue_site_lookup(slot)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("[LOCAL-480] venue-site lookup failed for need %r: %s",
                               slot.key, e)
                stop = None
        if stop is not None:
            stops.append(stop)
            logger.info(stop.source_line())
        else:
            logger.info("[LOCAL-480] need '%s' unmet — no mapped object and no "
                        "venue-site entry; not filled", slot.key)
    return stops
