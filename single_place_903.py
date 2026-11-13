"""[LOCAL-903] A snapped, verified point supersedes the place reference, and a single-place tour is one place.

Tour 552 (a mountain with a statue on it): the 791C snap put Stop 1 on the real site, but Stop 2 stayed on the
wrong geocoder place reference 25 km away. Offline, no network, no geocoder: pure functions over the poi list
and the snap rows (``pin_snap.snap_poi_coordinates``).
"""
import re
from typing import Callable, Dict, List, Optional, Tuple

_VERIFIED_SOURCES = ("serper", "wikidata", "nominatim", "landmark")
SAME_PLACE_KM = 15.0
_REF_MATCH_KM = 1.0          # a stop is "on the old place reference" when its pin is this close to it
_SINGLE_SCOPES = ("DISTRICT", "BUILDING")


def _hav_km(a, b) -> float:
    import pin_snap
    return pin_snap._haversine_m(a, b) / 1000.0


def _coord(poi: Dict) -> Optional[Tuple[float, float]]:
    import pin_snap
    return pin_snap._poi_coord(poi)


def _set_coord(poi: Dict, pt: Tuple[float, float], donor: Optional[int] = None) -> None:
    """Write ``pt`` as the stop's pin. ``donor`` is the index of the stop whose verified pin it was moved to
    ([LOCAL-906B]: a moved stop inherits that stop's address verdict, see ``pin_snap.verify_addresses``)."""
    if donor is not None:
        poi["_pin_moved_to_stop"] = int(donor)
    poi["coordinates"] = f"{pt[0]:.6f}, {pt[1]:.6f}"
    if "latitude" in poi or "longitude" in poi:
        poi["latitude"], poi["longitude"] = pt[0], pt[1]
    poi["coordinates_approximate"] = True


def _fold(text: str) -> str:
    import area_resolver
    return re.sub(r"[^a-z0-9]+", " ", area_resolver._fold_diacritics(text or "").lower()).strip()


def _is_the_place(title: str, place_name: str) -> bool:
    """The stop's title IS the first named place (folded; one contains the other as whole words)."""
    t, p = f" {_fold(title)} ", f" {_fold(place_name)} "
    return bool(t.strip() and p.strip() and (p in t or t in p))


def _verified_snap(row: Dict) -> bool:
    return bool(row and row.get("snapped") and row.get("new_coordinate")
                and str(row.get("source") or "").lower().startswith(_VERIFIED_SOURCES)
                and not row.get("rejected_900b"))


def tour_pin(poi_list: List[Dict], fallback=(None, None)):
    """[LOCAL-903] The stored tour pin = the first stop's FINAL pin (after the snap and the re-pin)."""
    if poi_list:
        c = _coord(poi_list[0])
        if c and not poi_list[0].get("_no_coordinate"):
            return (c[0], c[1])
    return fallback


def repin_to_snapped_place(poi_list: List[Dict], rows: List[Dict], place_name: str,
                           place_ref: Optional[Tuple[float, float]] = None,
                           log: Optional[Callable[[str], None]] = None) -> int:
    """Item 2. The stop whose title is the first named place was pinned by the 791C snap to a verified point.
    Any OTHER stop whose pin is the old place reference (flagged ``coordinates_approximate`` by the 900 pin
    check, and within ~1 km of ``place_ref`` when that is known) moves to the snapped point. Returns the number
    moved. Never raises."""
    emit = log or (lambda _m: None)
    moved = 0
    try:
        if not place_name or not poi_list:
            return 0
        anchor = None
        for i, (p, r) in enumerate(zip(poi_list, rows)):
            if _is_the_place(p.get("name", ""), place_name) and _verified_snap(r):
                anchor = (i, tuple(r["new_coordinate"]))
                break
        if anchor is None:
            return 0
        ai, apt = anchor
        for j, (p, r) in enumerate(zip(poi_list, rows)):
            if j == ai or _verified_snap(r) or not p.get("coordinates_approximate"):
                continue
            c = _coord(p)
            if c is None:
                continue
            if place_ref is not None and _hav_km(c, place_ref) > _REF_MATCH_KM:
                continue
            km = _hav_km(c, apt)
            if km < 0.05:
                continue
            _set_coord(p, apt, donor=ai)
            moved += 1
            emit(f"  [LOCAL-903] stop={j + 1} re-pinned to the snapped place '{place_name}' "
                 f"(was the place reference, {km:.1f} km off)")
    except Exception as e:
        emit(f"  [LOCAL-903] re-pin skipped (non-fatal): {e}")
    return moved


def agree_single_place(poi_list: List[Dict], rows: List[Dict], scope_precision: str = "",
                       log: Optional[Callable[[str], None]] = None) -> int:
    """Item 3. On a single-place tour (<= 2 stops, DISTRICT / BUILDING scope) two stops more than 15 km apart
    cannot both be right: keep the verified (snapped) one and move the unverified one to it, flagged
    approximate. Returns the number moved. Never raises."""
    emit = log or (lambda _m: None)
    try:
        if len(poi_list or []) != 2 or (scope_precision or "").upper() not in _SINGLE_SCOPES:
            return 0
        a, b = _coord(poi_list[0]), _coord(poi_list[1])
        if a is None or b is None:
            return 0
        km = _hav_km(a, b)
        if km <= SAME_PLACE_KM:
            return 0
        va, vb = _verified_snap(rows[0] if len(rows) > 0 else {}), _verified_snap(rows[1] if len(rows) > 1 else {})
        if va == vb:
            emit(f"  [LOCAL-903] single-place stops are {km:.1f} km apart; "
                 f"{'both' if va else 'neither'} verified -- left as is")
            return 0
        keep, move = (0, 1) if va else (1, 0)
        _set_coord(poi_list[move], (a, b)[keep], donor=keep)
        emit(f"  [LOCAL-903] single-place agreement: stops {km:.1f} km apart; stop={move + 1} "
             f"moved to the verified stop={keep + 1} pin")
        return 1
    except Exception as e:
        emit(f"  [LOCAL-903] single-place agreement skipped (non-fatal): {e}")
        return 0


def reconcile_after_snap(poi_list: List[Dict], rows: List[Dict], place_name: str,
                         place_ref: Optional[Tuple[float, float]] = None, scope_precision: str = "",
                         log: Optional[Callable[[str], None]] = None) -> int:
    """Items 2 + 3 in order (the agreement is the re-run of the pin agreement after the snap)."""
    return (repin_to_snapped_place(poi_list, rows, place_name, place_ref, log)
            + agree_single_place(poi_list, rows, scope_precision, log))
