"""pin_snap.py — LOCAL-791C item 2.

Walking-stop coordinates are LLM-written and the 791B pin_proof table measured
them 0.5–6 km from the real place (Giac Lam Pagoda 2304 m, Xa Loi Pagoda 5956 m).
pin_proof PROVES the distance; this module FIXES it.

WHAT (ticket): for EVERY stop that has an IN-SCOPE reference — the same
Serper-Places / Nominatim / Wikidata P625 lookups pin_proof uses — snap the stop's
coordinate to that reference when the shipped pin is more than ``SNAP_THRESHOLD_M``
(150 m) away, and log ``[LOCAL-791C] pin snap <title> <m>``. A stop is left
unsnapped ONLY when no in-scope reference exists; that too is logged. After the
snap, a re-run of pin_proof should report ≤ 100 m for every referenced stop.

WHY a 150 m threshold and a 100 m target: 150 m is the shipped-pin error we act
on (anything closer is already a good pin and not worth a reference that may itself
sit on a different door of the same building); the reference we snap TO is the
authority pin_proof measures against, so a snapped stop lands ON it (0 m) and
clears the 100 m target. We never REPLACE a good pin with a worse one: the snap is
applied only when the measured error exceeds the threshold.

The reference lookup is INJECTABLE (``reference_fn``) so the snapper is unit-tested
offline; the live default calls ``pin_proof.reference_for_name`` (Serper Places
first, then Nominatim), with the SAME scope-sanity bound and bare-name stripping,
so the door the snap uses is the door the proof uses.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "snap_pin",
    "snap_poi_coordinates",
    "SNAP_THRESHOLD_M",
    "PIN_TARGET_M",
]

SNAP_THRESHOLD_M = 150.0
PIN_TARGET_M = 100.0

_COORD_PAIR_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*[,/ ]\s*(-?\d+(?:\.\d+)?)")


def _parse_coord(s) -> Optional[Tuple[float, float]]:
    if isinstance(s, (tuple, list)) and len(s) == 2:
        try:
            lat, lng = float(s[0]), float(s[1])
        except (TypeError, ValueError):
            return None
        if abs(lat) > 90 or abs(lng) > 180:
            return None
        return (lat, lng)
    m = _COORD_PAIR_RE.search(str(s or ""))
    if not m:
        return None
    try:
        lat, lng = float(m.group(1)), float(m.group(2))
    except (TypeError, ValueError):
        return None
    if abs(lat) > 90 or abs(lng) > 180:
        return None
    return (lat, lng)


def _haversine_m(a, b) -> float:
    try:
        from geocode_stops import haversine_m as _hm
        return _hm(a, b)
    except Exception:
        import math
        R = 6371000.0
        lat1, lng1 = math.radians(a[0]), math.radians(a[1])
        lat2, lng2 = math.radians(b[0]), math.radians(b[1])
        h = (math.sin((lat2 - lat1) / 2) ** 2
             + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2)
        return 2 * R * math.asin(math.sqrt(h))


# [LOCAL-858] Two pins this close are treated as THE SAME point for the
# shared-fallback test — a city-centroid guess the LLM stamped on several stops
# lands them within a few metres of one another (tour 527's three stops were all
# 10.776,106.695). 30 m is far tighter than the 150 m snap threshold, so two
# genuinely distinct stops that merely sit near each other are never mistaken
# for a shared centroid.
_SHARED_FALLBACK_M = 30.0

# [LOCAL-858B] CLUSTER-COLLAPSE radius. The cloud tour-532 pins were NOT ≤30 m
# apart (so the equality test above missed them) yet all three stops sat within
# ~150 m of one another and ~700 m from the area_resolver centre — a city-centre
# guess the model spread across the stops, just not to the metre. Two or more
# UNSNAPPED stops with DIFFERENT, non-same-building names whose shipped pins all
# fall inside this radius is a COLLAPSE: distinct named places cannot genuinely
# occupy one 250 m disc with no reference. They are cleared + announced, exactly
# like the ≤30 m case. Genuinely adjacent same-building stops (two stalls in Ben
# Thanh Market) are exempt via same_building, and user pins are exempt entirely.
_CLUSTER_COLLAPSE_M = float(__import__("os").environ.get(
    "PIN_CLUSTER_COLLAPSE_M", "250.0"))


def _coord_is_marked_fallback(poi: Dict) -> bool:
    """[LOCAL-858] True when the pipeline already STAMPED this coordinate as a
    fallback / centroid (not an independently resolved point). Mirrors
    identity_dedup._is_fallback_coord_stop so the two agree on what 'unknown
    coordinate' means. Deterministic, offline, never raises."""
    if not isinstance(poi, dict):
        return False
    for k in ("_coord_fallback", "coord_is_fallback", "_centroid_fallback",
              "centroid_fallback", "is_fallback_coord", "coord_fallback"):
        if poi.get(k):
            return True
    src = str(poi.get("coord_source") or poi.get("_coord_source")
              or poi.get("coordinate_source") or "").strip().lower()
    if src in ("fallback", "centroid", "city_centroid", "area_centroid",
               "scope_centroid", "scope_center", "unknown"):
        return True
    conf = str(poi.get("coord_confidence") or poi.get("_coord_confidence")
               or "").strip().lower()
    if conf in ("fallback", "centroid", "none", "unknown"):
        return True
    return False


#  A coordinate is a genuine user pin ONLY when it came from a real user
# source: a share link, a share link resolved via the Knowledge Graph, or a
# name lookup the user supplied. 'user_explicit' alone (set whenever a
# listener typed/selected a stop) says nothing about where the COORDINATE
# came from — a model-invented Phase-3B guess can carry user_explicit=True
# too. Checking user_explicit + "not literally tagged fallback" let those
# model guesses through as if the user had placed the pin (LOCAL-863 wave 27:
# every one of 7 Phase-3B guesses was kept as a "user pin" and never
# snapped/cleared). Gate strictly on coord_source instead.
_USER_PIN_COORD_SOURCES = (
    "user_share_link", "user_share_link_kg", "user_name_lookup",
)


def _is_user_pin(poi: Dict) -> bool:
    """[LOCAL-863] True only for a stop whose COORDINATE came from a real
    user source: coord_source in {user_share_link, user_share_link_kg,
    user_name_lookup}. A stop the user typed but whose coordinate the model
    guessed (user_explicit=True, coord_source unset/model/llm/...) is NOT a
    user pin: it must be snapped/looked up like any other stop."""
    if not isinstance(poi, dict):
        return False
    src = str(poi.get("coord_source") or "").strip().lower()
    return src in _USER_PIN_COORD_SOURCES


_MODEL_COORD_SOURCES = ("", "model", "llm", "ai", "gpt", "guess", "llm_guess",
                        "phase3b", "phase_3b", "model_guess", "unknown_model")


def _is_model_sourced_coord(poi: Dict) -> bool:
    """[LOCAL-870] True when the poi's coordinate came from the language model
    (or has no recorded source), NOT from a user source or a resolver (Serper /
    Nominatim / Wikidata / landmark table). A landmark pin established by an
    authority is never model-sourced."""
    if not isinstance(poi, dict):
        return False
    if poi.get("_landmark_coord") or poi.get("wikidata_lat") is not None:
        return False
    src = str(poi.get("coord_source") or poi.get("_coord_source")
              or poi.get("coordinate_source") or "").strip().lower()
    return src in _MODEL_COORD_SOURCES or src.startswith(("model", "llm"))


def _default_is_user_stop(poi: Dict) -> bool:
    return bool(isinstance(poi, dict)
                and (poi.get("user_explicit") or poi.get("_anchor")))


def _poi_coord(poi: Dict) -> Optional[Tuple[float, float]]:
    """A poi's current coordinate, from the 'coordinates' string or lat/lng."""
    c = _parse_coord(poi.get("coordinates"))
    if c:
        return c
    lat = poi.get("latitude", poi.get("lat"))
    lng = poi.get("longitude", poi.get("lng", poi.get("lon")))
    if lat is not None and lng is not None:
        return _parse_coord((lat, lng))
    return None


def _wikidata_coord(poi: Dict) -> Optional[Tuple[float, float]]:
    """A Wikidata P625 coordinate already on the poi (the strongest reference —
    it needs no network). Returns (lat, lng) or None."""
    lat = poi.get("wikidata_lat")
    lng = poi.get("wikidata_lng")
    if lat is not None and lng is not None:
        return _parse_coord((lat, lng))
    return None


def _default_reference(name: str, scope: str,
                       scope_center: Optional[Tuple[float, float]]
                       ) -> Optional[Tuple[float, float, str]]:
    """Live reference lookup: pin_proof.reference_for_name (Serper → Nominatim),
    the SAME door the proof uses."""
    try:
        from pin_proof import reference_for_name
        return reference_for_name(name, scope=scope, scope_center=scope_center)
    except Exception:
        return None


def _landmark_reference(name: str,
                        scope: str = "",
                        scope_center: Optional[Tuple[float, float]] = None,
                        scope_bbox: Optional[Sequence[float]] = None,
                        tour_language: str = "en",
                        landmark_fn: Optional[Callable] = None,
                        ) -> Optional[Tuple[float, float, str]]:
    """[LOCAL-803] A Wikidata-P625 landmark reference, consulted BEFORE the generic
    geocoders. Returns (lat, lng, source) or None.

    [LOCAL-803] PREFER a LIVE Wikidata P625 lookup (``wikidata_landmark_lookup``):
    wbsearchentities in the tour + local language, P625, filtered to the tour's
    scope (bbox / metro radius), cached with a TTL. This generalises the fix
    beyond the six HCMC landmarks to ANY city. It resolves "City Hall" → the real
    People's Committee Building and "Thien Hau Temple" → the Cholon temple by the
    place's OWN authority, exactly as the hand-written table did, and now also
    "Boston State House", "Nice Opera", "Hanoi Hoan Kiem Lake", etc.

    FALLBACK: when the live lookup returns nothing — Wikidata unreachable, a 429
    that never cleared, or no in-scope match — fall back to the offline
    ``landmark_reference`` table so the original six HCMC pins never regress when
    the network is down. (``landmark_fn`` injects the live lookup for tests.)
    """
    # 1) Live Wikidata P625 lookup (general, cached, rate-limited).
    try:
        if landmark_fn is not None:
            hit = landmark_fn(name)
        else:
            from wikidata_landmark_lookup import lookup as _wd_lookup
            hit = _wd_lookup(
                name, scope=scope, scope_center=scope_center,
                scope_bbox=list(scope_bbox) if scope_bbox else None,
                tour_language=tour_language or "en")
        if hit:
            return (float(hit[0]), float(hit[1]), str(hit[2]))
    except Exception:
        # Any failure in the live path must not drop the stop — fall through to
        # the second authority / offline table below.
        pass
    # 1b) Offline curated table (the original HCMC landmarks) — [LEAD 858B review]
    # consulted BEFORE the live second authority: a curated pin beats a name search.
    try:
        from landmark_reference import lookup as _lm_lookup
        tbl = _lm_lookup(name)
        if tbl:
            return (float(tbl[0]), float(tbl[1]), str(tbl[2]))
    except Exception:
        pass
    # 2) [LOCAL-858B] SECOND AUTHORITY. Wikidata returned nothing (unreachable
    # from Cloud Run egress, a 429 that never cleared, or no in-scope P625). Ask
    # Serper /places by name inside the city box, then Nominatim — name-matched
    # and in-scope, cached like P625. An INJECTED landmark_fn (unit tests / offline
    # replays) is a vouched-for authority and takes precedence, so the live second
    # authority is skipped for it.
    if landmark_fn is None:
        try:
            from landmark_second_authority import lookup_second_authority as _2nd
            hit2 = _2nd(name, scope=scope, scope_center=scope_center,
                        scope_bbox=list(scope_bbox) if scope_bbox else None)
            if hit2:
                return (float(hit2[0]), float(hit2[1]), str(hit2[2]))
        except Exception:
            pass
    return None


def _name_distinctive_tokens(name: str):
    """Distinctive (proper-noun) tokens of a place name, class-folded, honorifics /
    city-district qualifiers dropped — the shared identity core for a name match.
    Delegates to identity_dedup when available."""
    try:
        from identity_dedup import _distinctive_tokens as _dt
        core = set(_dt(name))
    except Exception:
        import re as _re
        import unicodedata as _ud
        nfkd = _ud.normalize("NFKD", (name or "").lower())
        s = "".join(c for c in nfkd if not _ud.combining(c))
        s = _re.sub(r"[^\w\s]", " ", s)
        core = {w for w in s.split() if len(w) >= 2}
    _drop = {"saigon", "hcmc", "ho", "chi", "minh", "city", "vietnam", "old",
             "new", "central", "district", "downtown", "sai", "gon", "the", "of"}
    return {t for t in core if t not in _drop}


def _name_matches_reference(title: str, ref_name: str) -> bool:
    """[LOCAL-791E item 1] True when a reference NAME strongly matches the stop
    title — they share the distinctive proper-noun core (one token-set is a subset
    of the other, both non-empty). A generic "City Hall" vs a reference listing
    named for a DIFFERENT building shares no distinctive core and is rejected, so a
    wrong same-class snap (the 4.8 km City Hall bug) is refused. When the reference
    carries no usable name we cannot verify a match → treated as NOT matched (the
    caller only requires a match for generic geocoder references, not for the
    authority table / Wikidata)."""
    a = _name_distinctive_tokens(title)
    b = _name_distinctive_tokens(ref_name)
    if not a or not b:
        return False
    return a <= b or b <= a


def snap_pin(title: str,
             coordinate: Optional[Tuple[float, float]],
             scope: str = "",
             scope_center: Optional[Tuple[float, float]] = None,
             wikidata_coord: Optional[Tuple[float, float]] = None,
             threshold_m: float = SNAP_THRESHOLD_M,
             reference_fn: Optional[Callable] = None,
             max_snap_km: float = 15.0,
             stops_centroid: Optional[Tuple[float, float]] = None,
             max_centroid_km: float = 2.0,
             require_name_match: bool = True,
             use_landmark_table: bool = True,
             scope_bbox: Optional[Sequence[float]] = None,
             tour_language: str = "en",
             landmark_fn: Optional[Callable] = None,
             venue_fallback_coordinate: Optional[Tuple[float, float]] = None,
             ) -> Dict:
    """Decide the snap for ONE stop.

    Returns a dict::

        {"title", "shipped", "reference", "source", "distance_m",
         "snapped": bool, "new_coordinate": (lat,lng)|None, "reason": str}

    * A Wikidata P625 coordinate already on the stop is the reference when present
      (``source='wikidata'``), with no network call.
    * Otherwise the reference is the injected / default Serper→Nominatim lookup.
    * ``snapped`` is True when a reference exists AND the shipped pin is more than
      ``threshold_m`` from it; ``new_coordinate`` is then the reference.
    * No reference → ``snapped`` False, ``reason`` says the stop is left unsnapped.

    SCOPE SANITY: a reference more than ``max_snap_km`` from ``scope_center`` is a
    same-name place in another city (Nominatim's bare-name match for a HCMC pagoda
    returned a shrine 40 km away). We do NOT snap to it — moving a pin tens of km
    across the region is worse than the shipped error — and leave the stop as-is,
    saying so in the reason. Disabled when scope_center is unknown.
    """
    out: Dict = {
        "title": title,
        "shipped": coordinate,
        "reference": None,
        "source": None,
        "distance_m": None,
        "snapped": False,
        "new_coordinate": None,
        "reason": "",
    }

    ref_pt: Optional[Tuple[float, float]] = None
    source: Optional[str] = None
    ref_name: str = ""
    # "authority" references (the stop's own Wikidata P625, or the P625 landmark
    # table) are the place's own identity, not a bare-name geocode — they are
    # exempt from the name-match requirement and the off-scope / centroid bounds.
    authority = False

    wd = wikidata_coord
    if wd:
        ref_pt, source, authority = wd, "wikidata", True
    else:
        # [LOCAL-791E items 1 & 5] Consult the Wikidata-P625 landmark table FIRST
        # on the LIVE path (no injected reference_fn). It resolves "City Hall" to
        # the real People's Committee Building and "Thien Hau Temple" to the Cholon
        # temple (by the place's own name / local-language name), where the generic
        # geocoder returned a wrong same-class place (item 1) or nothing (item 5).
        # An injected reference_fn (unit tests / offline replays) is a vouched-for
        # door and takes precedence, so the table is skipped for it.
        if use_landmark_table and reference_fn is None:
            lm = _landmark_reference(
                title, scope=scope, scope_center=scope_center,
                scope_bbox=scope_bbox, tour_language=tour_language,
                landmark_fn=landmark_fn)
            if lm:
                ref_pt = (float(lm[0]), float(lm[1]))
                source = lm[2] if len(lm) > 2 else "wikidata_p625"
                authority = True
        if ref_pt is None:
            rfn = reference_fn or (
                lambda n: _default_reference(n, scope, scope_center))
            try:
                ref = rfn(title)
            except Exception:
                ref = None
            if ref:
                try:
                    ref_pt = (float(ref[0]), float(ref[1]))
                    source = ref[2] if len(ref) > 2 else "reference"
                    ref_name = ref[3] if len(ref) > 3 else ""
                except (TypeError, ValueError, IndexError):
                    ref_pt = None

    # [LOCAL-813 Cause C] MUSEUM BUILDING FALLBACK. A museum/gallery tour's stops
    # are often ARTWORK titles ("Judith I", "The Evil Mothers") with no place
    # identity of their own — no Wikidata P625, and the generic geocoder either
    # fails or returns a WRONG same-name building (Belvedere → "Lower Belvedere",
    # refused above). Such a stop shares the ONE building-level pin of the museum.
    # When the caller supplies the museum building's authoritative coordinate
    # (``venue_fallback_coordinate`` — the museum's own Wikidata P625, resolved
    # once from the tour venue/scope), adopt it: it is the correct single pin for
    # an indoor exhibit, far better than an LLM-written guess (Belvedere shipped
    # 1,379 m off the palace). Treated as an authority (the museum's own identity),
    # so the name-match / centroid guards do not apply to it.
    def _apply_venue_fallback(reason_prefix: str) -> Optional[Dict]:
        if not venue_fallback_coordinate:
            return None
        vf = _parse_coord(venue_fallback_coordinate)
        if not vf:
            return None
        out["reference"] = vf
        out["source"] = "venue_building"
        if not coordinate:
            out["snapped"] = True
            out["new_coordinate"] = vf
            out["reason"] = f"{reason_prefix}; adopted museum building pin"
            return out
        d = _haversine_m(coordinate, vf)
        out["distance_m"] = round(d, 1)
        if d > threshold_m:
            out["snapped"] = True
            out["new_coordinate"] = vf
            out["reason"] = (f"{reason_prefix}; museum building pin {d:.0f} m "
                             f"> {threshold_m:.0f} m — snapped to building")
        else:
            out["reason"] = (f"{reason_prefix}; museum building pin {d:.0f} m "
                             f"within {threshold_m:.0f} m — kept")
        return out

    if not ref_pt:
        vf_out = _apply_venue_fallback("no in-scope reference")
        if vf_out is not None:
            return vf_out
        out["reason"] = "no in-scope reference — left unsnapped"
        return out

    # [LOCAL-858] AUTHORITY OFF-SCOPE GUARD. A Wikidata P625 reference is the
    # place's own identity and is otherwise exempt from the scope bounds — but a
    # BARE-NAME wbsearchentities hit can still resolve a SAME-NAME place in another
    # country when the lookup had no scope centre to filter by. The live Hanoi run
    # snapped "St. Joseph's Cathedral" to the cathedral in BAGHDAD (6,144 km away),
    # shipped as an authority pin. When a scope centre IS known here, no real stop
    # on a city walking tour is hundreds of km from it: refuse a reference beyond
    # ``max_authority_km`` (a generous cross-region bound) even when it is an
    # authority, keeping the shipped pin rather than teleporting the stop.
    _MAX_AUTHORITY_KM = 150.0
    if authority and scope_center and ref_pt:
        _auth_km = _haversine_m(ref_pt, scope_center) / 1000.0
        if _auth_km > _MAX_AUTHORITY_KM:
            vf_out = _apply_venue_fallback(
                f"authority reference {_auth_km:.0f} km from centre — off-scope "
                f"same-name place")
            if vf_out is not None:
                return vf_out
            out["reference"] = ref_pt
            out["source"] = source
            out["reason"] = (
                f"authority reference {_auth_km:.0f} km from centre "
                f"> {_MAX_AUTHORITY_KM:.0f} km — refused (same-name place in "
                f"another region)")
            return out

    # [LOCAL-791E item 1] NAME-MATCH REQUIREMENT for a GENERIC geocoder reference.
    # A bare-name geocode ("City Hall") can land on a DIFFERENT same-class building
    # anywhere in the city — a wrong snap is worse than none. When the generic
    # reference carries a NAME, snap only if it strongly matches the stop (shared
    # distinctive proper-noun core); a mismatch is refused (kept pin). Authority
    # references (Wikidata P625 / the landmark table) are the place's own identity
    # and skip this check. When no name is available we cannot verify by name and
    # defer to the stops-centroid bound below.
    if require_name_match and not authority and ref_name:
        if not _name_matches_reference(title, ref_name):
            # [LOCAL-813 Cause C] A refused generic reference (e.g. Belvedere →
            # "Lower Belvedere") leaves an artwork stop with no identity. Prefer
            # the museum building pin, when known, over keeping the wrong shipped
            # pin.
            vf_out = _apply_venue_fallback(
                f"reference name {ref_name!r} does not match stop — refused")
            if vf_out is not None:
                return vf_out
            out["reference"] = ref_pt
            out["source"] = source
            out["reason"] = (
                f"reference name {ref_name!r} does not match stop — refused "
                f"(generic same-name/same-class match)")
            return out

    # [LOCAL-791E item 1] STOPS-CENTROID BOUND. The reference must sit within
    # ``max_centroid_km`` of the OTHER stops' centroid (not just the city centre):
    # the Old Saigon landmarks cluster in District 1, so a "City Hall" reference
    # 4.8 km south of that cluster is a wrong building — refuse and keep the pin.
    # Authority references are trusted (the place's own P625). Disabled when no
    # stops_centroid is supplied (unit tests that exercise only scope_center).
    if (not authority and stops_centroid and max_centroid_km):
        _cd = _haversine_m(ref_pt, stops_centroid) / 1000.0
        if _cd > max_centroid_km:
            vf_out = _apply_venue_fallback(
                f"reference {_cd:.1f} km from stops' centroid — refused")
            if vf_out is not None:
                return vf_out
            out["reference"] = ref_pt
            out["source"] = source
            out["reason"] = (
                f"reference {_cd:.1f} km from stops' centroid "
                f"> {max_centroid_km:.1f} km — refused (wrong same-name place)")
            return out

    # SCOPE SANITY: refuse a reference implausibly far from the tour's centre — a
    # bare-name geocode that resolved to another city. Wikidata P625 / the landmark
    # table are trusted as-is (the place's own authority, not a name search).
    if (not authority and scope_center and max_snap_km
            and _haversine_m(ref_pt, scope_center) / 1000.0 > max_snap_km):
        vf_out = _apply_venue_fallback(
            f"reference {_haversine_m(ref_pt, scope_center)/1000.0:.0f} km from "
            f"centre — off-scope")
        if vf_out is not None:
            return vf_out
        out["reason"] = (f"reference {_haversine_m(ref_pt, scope_center)/1000.0:.0f} km "
                         f"from centre > {max_snap_km:.0f} km — left unsnapped "
                         f"(off-scope same-name match)")
        return out

    out["reference"] = ref_pt
    out["source"] = source

    if not coordinate:
        # No shipped pin at all: adopt the reference (better than nothing).
        out["snapped"] = True
        out["new_coordinate"] = ref_pt
        out["distance_m"] = None
        out["reason"] = "no shipped pin — adopted reference"
        return out

    dist = _haversine_m(coordinate, ref_pt)
    out["distance_m"] = round(dist, 1)

    # DON'T MAKE A GOOD PIN WORSE (LOCAL-791C live run, Thien Hau Temple): the
    # shipped pin sat in District 5 (~2 km from the HCMC centre, correct), but
    # Nominatim's bare-name match returned a same-name shrine 23 km north — inside
    # the loose 25 km bound, so it snapped and blew the walking route to 11 km.
    # A reference is only trustworthy when it is at least as central as the pin it
    # would replace: if the shipped pin is itself in-scope (close to centre) AND
    # the reference is markedly farther from centre than the shipped pin, the
    # reference is a wrong same-name place in another district/city — keep the
    # shipped pin. Wikidata P625 / the landmark table (the place's own authority)
    # are exempt.
    if (not authority and scope_center and coordinate):
        _ship_km = _haversine_m(coordinate, scope_center) / 1000.0
        _ref_km = _haversine_m(ref_pt, scope_center) / 1000.0
        if _ship_km <= 10.0 and _ref_km > _ship_km + 5.0:
            out["reason"] = (f"shipped pin {_ship_km:.0f} km from centre is in-scope; "
                             f"reference {_ref_km:.0f} km from centre is farther out "
                             f"— kept shipped pin (reference is an off-scope same-name "
                             f"match)")
            return out

    if dist > threshold_m:
        out["snapped"] = True
        out["new_coordinate"] = ref_pt
        out["reason"] = f"shipped pin {dist:.0f} m > {threshold_m:.0f} m threshold"
    else:
        out["reason"] = f"shipped pin {dist:.0f} m within {threshold_m:.0f} m — kept"
    return out


_ROUTE_PLACE_KEEP_M = 3000.0


def snap_poi_coordinates(poi_list: List[Dict],
                         scope: str = "",
                         scope_center: Optional[Tuple[float, float]] = None,
                         threshold_m: float = SNAP_THRESHOLD_M,
                         reference_fn: Optional[Callable] = None,
                         log: Optional[Callable[[str], None]] = None,
                         max_centroid_km: float = 2.0,
                         require_name_match: bool = True,
                         scope_bbox: Optional[Sequence[float]] = None,
                         tour_language: str = "en",
                         landmark_fn: Optional[Callable] = None,
                         venue_fallback_coordinate: Optional[Tuple[float, float]] = None,
                         city_centroid: Optional[Tuple[float, float]] = None,
                         is_user_stop_fn: Optional[Callable[[Dict], bool]] = None,
                         route_box: Optional[Sequence[float]] = None,
                         route_refs: Optional[Dict[int, Dict]] = None,
                         ) -> Tuple[List[Dict], List[Dict]]:
    """Snap every stop in ``poi_list`` to its reference when the shipped pin is
    more than ``threshold_m`` away AND the reference is trustworthy. Mutates each
    poi's ``coordinates`` (and latitude/longitude when present) in place and
    returns ``(poi_list, rows)`` where ``rows`` is the per-stop ``snap_pin``
    decision.

    [LOCAL-791E] A snap is only applied when the reference is the place's own
    authority (Wikidata P625 / the landmark table) OR a generic geocode whose NAME
    strongly matches the stop AND that sits within ``max_centroid_km`` of the OTHER
    stops' centroid. A reference that fails either test is REFUSED — the shipped
    pin is kept and ``[LOCAL-791E] snap refused <title> <reason>`` is logged — so a
    wrong same-name/same-class snap (the City Hall 4.8 km bug) never ships.

    Logs ``[LOCAL-791C] pin snap <title> <m>`` for each snapped stop, a
    ``[LOCAL-791E] snap refused …`` line for a reference rejected by the name /
    centroid guards, and a ``left unsnapped`` line for a stop with no reference.

    [LOCAL-858] A stop that is NOT snapped and whose shipped pin is a city-centroid
    guess (marked a fallback upstream, OR shared within ~30 m with another
    un-snapped stop, OR equal to the optional ``city_centroid``) has that pin
    CLEARED (``coordinates`` → ''), is marked ``_no_coordinate``, and is announced
    ``[LOCAL-858] no coordinate <title>``. A centroid is 'coordinates unknown', not
    a place, so it must never ship as a real pin (HCMC tour 527). The stop itself
    is kept — only the fake pin is dropped."""
    emit = log or (lambda _m: None)
    rows: List[Dict] = []

    # An INJECTED reference_fn is a vouched-for reference (unit tests / offline
    # replays supply the KNOWN-correct door), so the name-match and stops-centroid
    # guards — which defend against the LIVE geocoder's wrong same-name matches —
    # are not applied to it. The guards are active only on the live default path.
    _injected = reference_fn is not None
    _rnm = require_name_match and not _injected
    _max_centroid = None if _injected else max_centroid_km

    # Precompute each stop's current coordinate so the stops-centroid is the
    # LEAVE-ONE-OUT centroid of the OTHER stops (a stop is never bounded against
    # its own pin, and one wrong pin does not pull its own bound).
    coords_all: List[Optional[Tuple[float, float]]] = [_poi_coord(p) for p in poi_list]

    def _centroid_excluding(idx: int) -> Optional[Tuple[float, float]]:
        pts = [c for j, c in enumerate(coords_all) if j != idx and c]
        if not pts:
            return None
        return (sum(p[0] for p in pts) / len(pts),
                sum(p[1] for p in pts) / len(pts))

    # The centroid bound is ADAPTIVE to how spread the stops already are. For a
    # TIGHT cluster (an Old Saigon walking tour in District 1) it stays at
    # ``max_centroid_km`` (2 km), so a City Hall reference 4.8 km outside the
    # cluster is refused. For a city-SPANNING tour (pagodas across HCMC — the
    # named anchors alone are ~5 km apart) it widens to the stops' own radius + a
    # margin, so a genuinely far pagoda's correct reference is not refused. The
    # reference must still be no farther from the centroid than the stops
    # themselves reach, plus the base bound.
    def _adaptive_bound(idx: int, centroid: Optional[Tuple[float, float]]) -> float:
        if not centroid:
            return _max_centroid or 0.0
        other = [c for j, c in enumerate(coords_all) if j != idx and c]
        spread = max((_haversine_m(c, centroid) / 1000.0 for c in other),
                     default=0.0)
        return max(_max_centroid or 0.0, spread + (_max_centroid or 0.0))

    for i, poi in enumerate(poi_list):
        title = poi.get("name", "")
        coord = coords_all[i]
        if _is_user_pin(poi):
            # [LEAD 858 review] A listener's own pin (LOCAL-855E) is authoritative:
            # never snapped, never cleared. Recorded as snapped-in-place so the
            # centroid pass below skips it too.
            rows.append({"title": title, "snapped": True,
                         "new_coordinate": coord, "reference": coord,
                         "source": "user_share_link", "distance_m": 0.0,
                         "reason": "user pin kept"})
            emit(f"[LOCAL-855E] user pin kept {title!r} (pin snap skipped)")
            continue
        wd = _wikidata_coord(poi)
        _centroid_i = None if _injected else _centroid_excluding(i)
        _bound_i = 0.0 if _injected else _adaptive_bound(i, _centroid_i)
        row = snap_pin(title, coord, scope=scope, scope_center=scope_center,
                       wikidata_coord=wd, threshold_m=threshold_m,
                       reference_fn=reference_fn,
                       stops_centroid=_centroid_i,
                       max_centroid_km=_bound_i,
                       require_name_match=_rnm,
                       scope_bbox=scope_bbox,
                       tour_language=tour_language,
                       landmark_fn=landmark_fn,
                       venue_fallback_coordinate=venue_fallback_coordinate)
        # [LOCAL-897] A stop whose title names a route place (or that follows the arrival at the
        # destination) and found no authority of its own uses that place's geocode as its reference.
        _rr = (route_refs or {}).get(i)
        if _rr and row.get("reference") is None and not row.get("snapped"):
            _ref = tuple(_rr["coord"])
            if coord is not None and _haversine_m(coord, _ref) <= _ROUTE_PLACE_KEEP_M:
                row.update({"reference": _ref, "source": "route_place", "distance_m": _haversine_m(coord, _ref),
                            "reason": f"model pin within {_ROUTE_PLACE_KEEP_M/1000:.0f} km of route place"})
                emit(f"[LOCAL-897] {title!r}: model pin is near the route place {_rr['place']!r} -- kept")
            else:
                row.update({"snapped": True, "new_coordinate": _ref, "reference": _ref, "source": "route_place",
                            "distance_m": _haversine_m(coord, _ref) if coord is not None else None,
                            "reason": f"route place {_rr['place']!r} is the reference ({_rr['why']})"})
        rows.append(row)
        if row["snapped"] and row["new_coordinate"]:
            lat, lng = row["new_coordinate"]
            poi["coordinates"] = f"{lat:.6f}, {lng:.6f}"
            if "latitude" in poi or "longitude" in poi:
                poi["latitude"] = lat
                poi["longitude"] = lng
            poi["_pin_snapped"] = True
            poi["_pin_snap_source"] = row["source"]
            d = row["distance_m"]
            emit(f"[LOCAL-791C] pin snap {title} "
                 f"{('%.0f' % d) if d is not None else '?'}m "
                 f"→ {lat:.6f},{lng:.6f} ({row['source']})")
        elif row["reference"] is None:
            emit(f"[LOCAL-791C] pin snap {title} left unsnapped "
                 f"({row.get('reason') or 'no in-scope reference'})")
        elif "refused" in (row.get("reason") or ""):
            # A reference WAS found but the name-match / centroid guard rejected it.
            emit(f"[LOCAL-791E] snap refused {title} {row.get('reason')}")
        else:
            d = row["distance_m"]
            emit(f"[LOCAL-791C] pin ok {title} "
                 f"{('%.0f' % d) if d is not None else '?'}m within threshold")

    # ── [LOCAL-858] NEVER SHIP A CITY-CENTROID AS A REAL PIN ──────────────────
    # A stop that was NOT snapped keeps whatever coordinate it shipped with. When
    # that shipped coordinate is the LLM's city-centroid guess — the HCMC-tour-527
    # failure: three stops all stamped 10.776,106.695 because the model could not
    # place them and returned the city centre — keeping it ships the centroid as
    # if it were a real pin, indistinguishable downstream (the app plots whatever
    # number it is given). The ticket: log '[LOCAL-858] no coordinate <name>' and
    # NEVER silently keep the centroid. A stop is centroid-collapsed when its pin
    # is EITHER (a) already marked a fallback/centroid by an upstream phase, OR
    # (b) the SAME point (within _SHARED_FALLBACK_M) as ≥1 OTHER un-snapped stop
    # whose pin is equally uncorroborated — two stops cannot share one coordinate
    # and both be real places — OR (c) equal to the supplied ``city_centroid``.
    #
    # Snapped stops are authoritative (Wikidata P625 / a name-matched geocode) and
    # are never touched here. We CLEAR the collapsed coordinate (set it to '' so
    # route-order and the map treat the stop as unplaced), mark it, and announce
    # it — dropping the fake pin, not the stop.
    def _row_for(idx: int) -> Dict:
        return rows[idx] if idx < len(rows) else {}

    # Indices of stops that did NOT get an authoritative snap this pass.
    _unsnapped = [i for i, p in enumerate(poi_list)
                  if not (_row_for(i).get("snapped") and _row_for(i).get("new_coordinate"))]

    def _same_building_pair(ia: int, ib: int) -> bool:
        """[LOCAL-858B] Same-building exemption for the collapse pass, by EXPLICIT
        IDENTITY only — a shared Wikidata QID, an alias of one naming the other, or
        one located-in the other. The coords-based branch of
        local802_relevance_gate.same_building is deliberately NOT used here: two
        city-centroid guesses sit at the same point and often share a generic token
        ("Stop A"/"Stop B"), which that branch would read as one building and
        wrongly exempt from the collapse. Genuinely adjacent same-building stops
        (two stalls in one market) carry the explicit identity this checks."""
        a, b = poi_list[ia], poi_list[ib]
        if not isinstance(a, dict) or not isinstance(b, dict):
            return False
        qa = str(a.get("wikidata_qid") or a.get("qid") or "").strip()
        qb = str(b.get("wikidata_qid") or b.get("qid") or "").strip()
        if qa and qb and qa == qb:
            return True

        def _aliases(s):
            out = set()
            for v in (s.get("aliases") or []):
                if isinstance(v, str) and v.strip():
                    out.add(v.strip().lower())
            nm = (s.get("name") or s.get("title") or "").strip().lower()
            if nm:
                out.add(nm)
            return out

        aa, ab = _aliases(a), _aliases(b)
        na = (a.get("name") or a.get("title") or "").strip().lower()
        nb = (b.get("name") or b.get("title") or "").strip().lower()
        if (aa & ab) and (na != nb):
            # Alias overlap that is NOT just the two identical names.
            return True
        if na and na in ab and na != nb:
            return True
        if nb and nb in aa and nb != na:
            return True

        def _located(s):
            out = set()
            for key in ("located_in", "located_in_qid", "part_of", "part_of_qid"):
                v = s.get(key)
                if isinstance(v, str) and v.strip():
                    out.add(v.strip())
                elif isinstance(v, (list, tuple, set)):
                    out |= {str(x).strip() for x in v if x}
            return out

        if qb and qb in _located(a):
            return True
        if qa and qa in _located(b):
            return True
        return False

    # The SHARED-point test uses the ORIGINAL shipped coordinates (``coords_all``,
    # snapshotted at entry), NOT the post-snap positions: the collapse signal is
    # that the model stamped the SAME point on several stops, and that is true of
    # the SHIPPED pins even when some of those stops later snapped away to their
    # real place. A stop whose shipped pin coincided with ANY other stop's shipped
    # pin is a centroid guess — UNLESS that neighbour is the SAME BUILDING (two
    # stalls in one market legitimately share a point) [LOCAL-858B].
    def _shipped_shared(idx: int) -> bool:
        a = coords_all[idx]
        if not a:
            return False
        for j in range(len(coords_all)):
            if j == idx:
                continue
            b = coords_all[j]
            if b and _haversine_m(a, b) <= _SHARED_FALLBACK_M:
                # Same-building neighbours (two stalls in one market) legitimately
                # share a point and are NOT a centroid collapse. [LOCAL-858B]
                if _same_building_pair(idx, j):
                    continue
                return True
        return False

    # [LOCAL-858B] CLUSTER-COLLAPSE detection (not equality). Two or more UNSNAPPED
    # stops whose shipped pins all fall inside ``_CLUSTER_COLLAPSE_M`` (250 m) of
    # each other, and whose names are DIFFERENT and NOT the same building, is a
    # collapse — distinct named places cannot really share one 250 m disc with no
    # reference (cloud tour 532: Ben Thanh and the Opera House ~150 m apart, ~700 m
    # off, neither snapped). A stop is cluster-collapsed when it has ≥1 OTHER
    # unsnapped, non-same-building, differently-named neighbour inside the radius.
    # Same-building neighbours (two stalls in one market) and user pins are NOT a
    # collapse. Uses the ORIGINAL shipped positions so the signal is read before
    # any stop moved. For the CLUSTER test we require NO reference at all: a stop
    # that WAS within threshold of a real reference (snapped False only because it
    # was already close enough) is well-placed and must never be cleared — only
    # reference-less stops are collapse candidates.
    _noref_set = {i for i in _unsnapped
                  if _row_for(i).get("reference") is None}

    def _diff_names(ia: int, ib: int) -> bool:
        na = _name_distinctive_tokens(poi_list[ia].get("name", ""))
        nb = _name_distinctive_tokens(poi_list[ib].get("name", ""))
        # Different when neither distinctive core is a subset of the other. When
        # one has NO distinctive token (all generic class words), treat equal
        # folded names as same and anything else as different.
        if na and nb:
            return not (na <= nb or nb <= na)
        import re as _re2
        fa = " ".join(sorted(_re2.findall(r"\w+",
                      (poi_list[ia].get("name", "") or "").lower())))
        fb = " ".join(sorted(_re2.findall(r"\w+",
                      (poi_list[ib].get("name", "") or "").lower())))
        return fa != fb

    def _clustered(idx: int) -> bool:
        a = coords_all[idx]
        if not a or idx not in _noref_set:
            return False
        for j in _noref_set:
            if j == idx:
                continue
            b = coords_all[j]
            if not b:
                continue
            if _haversine_m(a, b) > _CLUSTER_COLLAPSE_M:
                continue
            if _same_building_pair(idx, j):
                continue
            if _diff_names(idx, j):
                return True
        return False

    for i in _unsnapped:
        poi = poi_list[i]
        title = poi.get("name", "")
        pt = coords_all[i]
        if pt is None:
            # No coordinate at all — already unplaced; announce it once (route
            # order / the map already treat it as having no marker).
            poi["_no_coordinate"] = True
            emit(f"[LOCAL-858] no coordinate {title}")
            continue
        # [LOCAL-858B] A stop that resolved to a real IN-SCOPE reference this pass
        # is corroborated — it was only left unsnapped because its shipped pin was
        # already within the threshold of that reference. It is a genuine place,
        # never a centroid: skip the collapse entirely (so a well-placed stop next
        # to an unplaceable neighbour is not swept up by the shared/cluster tests).
        if _row_for(i).get("reference") is not None:
            continue
        _cluster_hit = _clustered(i)
        # [LOCAL-870 item 3] A USER stop whose coordinate is the MODEL's (not a
        # user_* source) and that found no reference is announced with no pin,
        # regardless of clustering. Wave 28: "A Star is Born" shipped the model's
        # 10.7762,106.6956 because the rest of its cluster were user pins/snapped,
        # so _clustered found no unsnapped neighbour (859/863R rule).
        _user_model_pin = bool(
            (is_user_stop_fn or _default_is_user_stop)(poi)
            and not _is_user_pin(poi) and _is_model_sourced_coord(poi))
        # [LOCAL-896] A ROUTE's stops are spread over a region (a base station, a pagoda and a
        # statue on one mountain sit a few hundred metres apart). A model pin that lies INSIDE the
        # route region is not collapsed for having no reference or for sitting near a differently
        # named stop; the identical-point and marked-fallback tests below still apply.
        _in_route = False
        if route_box and len(route_box) >= 4:
            try:
                _in_route = (route_box[0] <= pt[0] <= route_box[1]
                             and route_box[2] <= pt[1] <= route_box[3])
            except Exception:
                _in_route = False
        if _in_route and (_user_model_pin or _cluster_hit):
            emit(f"[LOCAL-896] {title!r}: model pin lies inside the route region -- kept "
                 f"(no reference/cluster collapse)")
            _user_model_pin = _cluster_hit = False
        if _user_model_pin:
            emit(f"[LOCAL-870] user stop {title!r} has only a model coordinate "
                 f"and no reference — announced with no pin")
        _collapsed = (
            _user_model_pin
            or _coord_is_marked_fallback(poi)
            or _shipped_shared(i)
            or _cluster_hit
            or (city_centroid is not None
                and _haversine_m(pt, city_centroid) <= _SHARED_FALLBACK_M))
        if _collapsed:
            # Drop the fake pin — a centroid is 'coordinates unknown', not a place.
            poi["coordinates"] = ""
            for _k in ("latitude", "longitude", "lat", "lng", "lon",
                       "wikidata_lat", "wikidata_lng"):
                if _k in poi:
                    poi[_k] = None
            poi["_no_coordinate"] = True
            poi["_coord_fallback"] = True
            _r = _row_for(i)
            if isinstance(_r, dict):
                _r["centroid_cleared"] = True
                if _cluster_hit:
                    _r["cluster_collapsed"] = True
            if _cluster_hit:
                emit(f"[LOCAL-858B] cluster collapse {title} — within "
                     f"{_CLUSTER_COLLAPSE_M:.0f} m of another unsnapped stop with "
                     f"a different name and no reference; pin cleared")
            emit(f"[LOCAL-858] no coordinate {title}")

    if route_box and len(route_box) >= 4:        # [LOCAL-897] one line per stop: model pin vs route box
        for _i, _p in enumerate(poi_list):
            _c0 = coords_all[_i]
            _where = ("none" if _c0 is None else
                      ("INSIDE" if (route_box[0] <= _c0[0] <= route_box[1] and route_box[2] <= _c0[1] <= route_box[3])
                       else "OUTSIDE"))
            _fin = _poi_coord(_p)
            emit(f"[LOCAL-897] stop {_i + 1} {_p.get('name', '')!r}: model pin {_c0} {_where} the route box; "
                 f"final pin {_fin if not _p.get('_no_coordinate') else None} "
                 f"({_row_for(_i).get('source') or 'no reference'})")
    return poi_list, rows
