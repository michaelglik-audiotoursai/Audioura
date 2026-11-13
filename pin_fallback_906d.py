"""[LOCAL-906D] A pin that no reference verified must still be inside the scope province.

Tour 552 (proof of 906C): the place reference for the mountain was not found (Wikidata miss in English, geocoder
miss), the city-level scope bbox was rejected ("attraction is not a city"), so the 791C snap had no bbox, refused
the only reference ("<Mountain> Cable Car Station" does not match the stop) and left both model pins 82 km from the
site, outside the province, with a wrong-district address.

Everything here is generic (no place names) and offline-testable: every lookup is an injected callable; the default
callables are best-effort network calls that never raise.

  province_box          the scope province's BOUNDING BOX (geocoder admin boundary, else Wikidata P625 + area)
  place_reference_retry the 901 lookup retried by local name / aliases / province-scoped geocode, accepted only
                        inside the province box
  facility_of_same_place a reference named "<stop core name> + facility word" for a natural-feature stop
  flag_far_pins         an unverified model pin outside the box is "far" (logged)
  last_resort_pins      a far pin still outside the box after the snap moves to the best in-province reference of
                        another stop, else to the province centre (approximate)
  address_follows_pin   a district/commune the province box cannot confirm is dropped from a moved stop's address
"""
import math
import re
import unicodedata
from typing import Callable, Dict, List, Optional, Sequence, Tuple

Box = Sequence[float]          # [south, north, west, east]

# ── generic vocabulary ───────────────────────────────────────────────────────────────────────────────────
FACILITY_WORDS = (
    "cable car station", "cable car", "cablecar", "ticket office", "ticket booth", "visitor centre", "visitor center",
    "tourist area", "tourist zone", "tourist site", "tourist attraction", "car park", "parking", "entrance", "gate",
    "station",
)
NATURAL_WORDS = ("mountain", "mount", "mt", "hill", "peak", "lake", "beach", "park", "tourist area", "island",
                 "nui", "doi", "monte", "mont", "berg", "lago", "bay", "valley")
_PEAK_WORDS = ("mountain", "mount", "mt", "hill", "peak", "nui", "doi", "monte", "mont", "berg")
_ADMIN_TYPES = {"administrative", "state", "province", "region", "county", "state_district", "city", "municipality"}
_DISTRICT_PREFIX = re.compile(
    r"^(?:huyen|district|quan|thi xa|thi tran|xa|phuong|ward|commune|county|town|village|hamlet|thon|ap)\b")
_PROVINCE_PREFIX = re.compile(r"^(?:province|tinh|thanh pho|city|state)\s+")

# official-language QID -> ISO code, wider than area_resolver._detect_language (which stays unchanged)
_LANG_QIDS = {
    "Q150": "fr", "Q652": "it", "Q1860": "en", "Q188": "de", "Q1321": "es", "Q7737": "ru", "Q5146": "pt",
    "Q9176": "ko", "Q5287": "ja", "Q7850": "zh", "Q9199": "vi", "Q9217": "th", "Q9240": "id", "Q256": "tr",
    "Q9129": "el", "Q7411": "nl", "Q809": "pl", "Q9056": "cs", "Q9067": "hu", "Q13955": "ar", "Q1568": "hi",
    "Q9237": "ms", "Q9205": "km", "Q9211": "lo", "Q9027": "sv", "Q9043": "no", "Q1412": "fi", "Q8798": "uk",
}


def _log(log: Optional[Callable], msg: str) -> None:
    (log or print)(msg)


def fold(text: str) -> str:
    """Lower-case, diacritics removed (including the stroked d), punctuation to single spaces."""
    t = (text or "").replace("\u0111", "d").replace("\u0110", "D")
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def hav_km(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))


# ── the province box ─────────────────────────────────────────────────────────────────────────────────────
def in_box(pt, box: Optional[Box], margin_km: float = 0.0) -> bool:
    if pt is None or not box or len(box) < 4:
        return False
    m_lat = margin_km / 111.0
    m_lng = margin_km / (111.0 * max(0.2, math.cos(math.radians((box[0] + box[1]) / 2.0))))
    return box[0] - m_lat <= pt[0] <= box[1] + m_lat and box[2] - m_lng <= pt[1] <= box[3] + m_lng


def km_outside_box(pt, box: Box) -> float:
    """Distance from ``pt`` to the nearest point of the box (0 when inside)."""
    lat = min(max(pt[0], box[0]), box[1])
    lng = min(max(pt[1], box[2]), box[3])
    return 0.0 if (lat, lng) == (pt[0], pt[1]) else hav_km(pt, (lat, lng))


def _box_from_row(row: Dict) -> Optional[List[float]]:
    bb = row.get("boundingbox")
    if not bb or len(bb) < 4:
        return None
    try:
        return [float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])]
    except (TypeError, ValueError):
        return None


def _is_admin_row(row: Dict) -> bool:
    cls = str(row.get("category") or row.get("class") or "").lower()
    typ = str(row.get("type") or "").lower()
    addr = str(row.get("addresstype") or "").lower()
    return (cls == "boundary" and typ == "administrative") or typ in _ADMIN_TYPES or addr in _ADMIN_TYPES \
        or (cls == "place" and typ in _ADMIN_TYPES)


def _default_search_rows(query: str) -> List[Dict]:
    """Nominatim, several rows, administrative areas preferred (featuretype=state). Never raises."""
    try:
        import requests
        resp = requests.get("https://nominatim.openstreetmap.org/search",
                            params={"q": query, "format": "jsonv2", "limit": "5", "featuretype": "state",
                                    "accept-language": "en"},
                            headers={"User-Agent": "Audioura/2.2 (tour-generation; contact: support@audioura.com)"},
                            timeout=8)
        return resp.json() if resp.status_code == 200 else []
    except Exception:
        return []


def _default_wikidata_area(name: str) -> Optional[Tuple[float, float, float]]:
    """(lat, lng, area_km2) of the best Wikidata item for ``name`` that has P625 and P2046. Never raises."""
    try:
        import requests
        ua = {"User-Agent": "Audioura/2.2 (tour-generation; contact: support@audioura.com)"}
        s = requests.get("https://www.wikidata.org/w/api.php",
                         params={"action": "wbsearchentities", "search": name, "language": "en", "type": "item",
                                 "limit": 5, "format": "json"}, headers=ua, timeout=10).json().get("search", [])
        for item in s:
            ent = requests.get("https://www.wikidata.org/w/api.php",
                               params={"action": "wbgetentities", "ids": item["id"], "props": "claims",
                                       "format": "json"}, headers=ua, timeout=10
                               ).json().get("entities", {}).get(item["id"], {})
            cl = ent.get("claims", {})
            p625 = (cl.get("P625") or [{}])[0].get("mainsnak", {}).get("datavalue", {}).get("value", {})
            p2046 = (cl.get("P2046") or [{}])[0].get("mainsnak", {}).get("datavalue", {}).get("value", {})
            if p625.get("latitude") is not None and p2046.get("amount"):
                return float(p625["latitude"]), float(p625["longitude"]), abs(float(p2046["amount"]))
    except Exception:
        pass
    return None


def province_box(province: str, country: str = "", search_fn: Optional[Callable] = None,
                 wikidata_fn: Optional[Callable] = None, log: Optional[Callable] = None) -> Optional[Dict]:
    """The province/state's bounding box and centre: ``{"box": [s, n, w, e], "center": (lat, lng), "source": str,
    "name": province}`` or None. The geocoder's ADMINISTRATIVE row (a railway station or a mountain of the same
    name is not the province); fallback: Wikidata P625 + area (P2046) as a square. Never raises."""
    prov = (province or "").strip()
    if not prov:
        return None
    try:
        q = f"{prov}, {country}".strip(", ") if country else prov
        rows = (search_fn or _default_search_rows)(q) or []
        for row in rows:
            if isinstance(row, dict) and _is_admin_row(row):
                box = _box_from_row(row)
                if box:
                    try:
                        ctr = (float(row["lat"]), float(row["lon"] if "lon" in row else row["lng"]))
                    except (KeyError, TypeError, ValueError):
                        ctr = ((box[0] + box[1]) / 2.0, (box[2] + box[3]) / 2.0)
                    return {"box": box, "center": ctr, "source": "geocoder_admin_boundary", "name": prov}
        hit = (wikidata_fn or _default_wikidata_area)(prov)
        if hit:
            lat, lng, area = float(hit[0]), float(hit[1]), float(hit[2])
            half = max(5.0, math.sqrt(max(area, 1.0)) / 2.0)
            d_lat = half / 111.0
            d_lng = half / (111.0 * max(0.2, math.cos(math.radians(lat))))
            return {"box": [lat - d_lat, lat + d_lat, lng - d_lng, lng + d_lng], "center": (lat, lng),
                    "source": "wikidata_p625_area", "name": prov}
    except Exception as e:
        _log(log, f"  [LOCAL-906D] province box for {prov!r} skipped (non-fatal): {e}")
    return None


# ── item 1: the place reference, retried ─────────────────────────────────────────────────────────────────
def _variants(name: str) -> List[str]:
    try:
        import area_resolver as ar
        return ar.place_name_variants(name)
    except Exception:
        return [name]


def _name_forms(name: str) -> set:
    return {fold(v) for v in _variants(name) if fold(v)}


def _feature_hint(name: str, stop_type: str = "") -> str:
    """'peak' for a mountain / hill / peak, '' otherwise (the geocoder's natural=peak)."""
    words = set(fold(f"{name} {stop_type}").split())
    return "peak" if words & set(_PEAK_WORDS) else ""


def _default_wd_search(label: str, lang: str) -> List[Dict]:
    """wbsearchentities in ``lang`` (labels AND aliases) + P625: [{qid, labels, aliases, lat, lng}]. Never raises."""
    try:
        import requests
        ua = {"User-Agent": "Audioura/2.2 (tour-generation; contact: support@audioura.com)"}
        api = "https://www.wikidata.org/w/api.php"
        found = requests.get(api, params={"action": "wbsearchentities", "search": label, "language": lang,
                                          "uselang": lang, "type": "item", "limit": 10, "format": "json"},
                             headers=ua, timeout=10).json().get("search", [])
        ids = [x["id"] for x in found if x.get("id")]
        if not ids:
            return []
        ents = requests.get(api, params={"action": "wbgetentities", "ids": "|".join(ids[:10]),
                                         "props": "labels|aliases|claims", "languages": f"{lang}|en",
                                         "format": "json"}, headers=ua, timeout=10).json().get("entities", {})
        out = []
        for qid, ent in ents.items():
            labels = [v.get("value", "") for v in (ent.get("labels") or {}).values()]
            aliases = [a.get("value", "") for lst in (ent.get("aliases") or {}).values() for a in lst]
            lat = lng = None
            for c in (ent.get("claims") or {}).get("P625", []):
                v = c.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                if v.get("latitude") is not None:
                    lat, lng = float(v["latitude"]), float(v["longitude"])
                    break
            out.append({"qid": qid, "labels": labels, "aliases": aliases, "lat": lat, "lng": lng})
        return out
    except Exception:
        return []


def local_language(city_qid: str) -> str:
    """ISO code of the country's official language (P17 -> P37) with the wider map; '' when unknown. Never raises."""
    try:
        import requests
        ua = {"User-Agent": "Audioura/2.2 (tour-generation; contact: support@audioura.com)"}
        api = "https://www.wikidata.org/w/api.php"

        def claims(qid):
            return requests.get(api, params={"action": "wbgetentities", "ids": qid, "props": "claims",
                                             "format": "json"}, headers=ua, timeout=10
                                ).json().get("entities", {}).get(qid, {}).get("claims", {})

        for c in claims(city_qid).get("P17", []):
            cq = c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id", "")
            for lc in claims(cq).get("P37", []) if cq else []:
                lq = lc.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id", "")
                if lq in _LANG_QIDS:
                    return _LANG_QIDS[lq]
    except Exception:
        pass
    return ""


def _wikidata_alias_hit(name: str, languages: Sequence[str], box: Optional[Box], wd_search_fn: Callable
                        ) -> Optional[Tuple[float, float, str]]:
    forms = _name_forms(name)
    for lang in languages:
        for variant in _variants(name)[:4]:
            try:
                items = wd_search_fn(variant, lang) or []
            except Exception:
                items = []
            for it in items:
                names = {fold(x) for x in list(it.get("labels") or []) + list(it.get("aliases") or []) if x}
                if not (names & forms):
                    continue
                if it.get("lat") is None or it.get("lng") is None:
                    continue
                pt = (float(it["lat"]), float(it["lng"]))
                if box and not in_box(pt, box):
                    continue
                return pt[0], pt[1], f"wikidata_{'local_language' if lang != 'en' else 'alias'}:{lang}"
    return None


def _geocoder_hit(name: str, province: str, country: str, hint: str, box: Optional[Box],
                  candidates_fn: Callable) -> Optional[Tuple[float, float, str]]:
    try:
        import area_resolver as ar
    except Exception:
        ar = None
    cores = []
    for v in _variants(name):
        core = " ".join(ar.name_core_tokens(v)) if ar else v
        if core and core not in cores:
            cores.append(core)
    queries = []
    for core in cores[:3]:
        queries.append(f"{core}, {province}" if province else core)
        if country:
            queries.append(f"{core}, {province}, {country}" if province else f"{core}, {country}")
    seen = set()
    for q in queries:
        if q in seen:
            continue
        seen.add(q)
        try:
            cands = candidates_fn(q, hint) or []
        except TypeError:
            cands = candidates_fn(q) or []
        except Exception:
            cands = []
        pool = [c for c in cands if isinstance(c, dict)]
        if hint:      # natural=peak first
            pool.sort(key=lambda c: 0 if str(c.get("class") or "").lower() == "natural"
                      and str(c.get("type") or "").lower() in ("peak", "hill", "volcano", "ridge") else 1)
        ordered = [c for c in pool if not ar or ar.geocoder_hit_verdict(name, c)[0]]   # class/type fits the name
        for c in ordered:
            try:
                pt = (float(c["lat"]), float(c.get("lng", c.get("lon"))))
            except (KeyError, TypeError, ValueError):
                continue
            if box and not in_box(pt, box):
                continue
            return pt[0], pt[1], f"geocoder_province{':' + hint if hint else ''}"
    return None


def place_reference_retry(name: str, province: str, country: str = "", stop_type: str = "",
                          box: Optional[Box] = None, languages: Sequence[str] = ("en",),
                          wd_search_fn: Optional[Callable] = None, candidates_fn: Optional[Callable] = None,
                          log: Optional[Callable] = None) -> Optional[Dict]:
    """After the 901 lookup missed: (a) Wikidata in the country's language as well as English, matching labels AND
    aliases, folded; (b) the geocoder with the core name plus the province and the feature type. Accepts only a
    hit INSIDE the province box. Logs ``[LOCAL-906D] place reference '<name>' -> <lat,lng> via <path>``.
    Returns ``{"name","lat","lng","precision":"place","source"}`` or None. Never raises."""
    try:
        if not name or not box:
            return None
        # local language first, English last (plain English was already tried by 901; the alias match is new)
        langs = []
        for lg in languages:
            if lg and lg != "en" and lg not in langs:
                langs.append(lg)
        langs.append("en")
        hit = _wikidata_alias_hit(name, langs, box, wd_search_fn or _default_wd_search)
        if hit is None:
            hint = _feature_hint(name, stop_type)
            cfn = candidates_fn
            if cfn is None:
                def cfn(q, _hint=""):
                    import geocode_stops as _gs
                    return _gs.geocode_candidates(q, 5)
            hit = _geocoder_hit(name, province, country, hint, box, cfn)
        if hit is None:
            _log(log, f"  [LOCAL-906D] place reference '{name}' -> none (retry: local-language/alias and "
                      f"province-scoped geocoder found nothing inside {province!r})")
            return None
        _log(log, f"  [LOCAL-906D] place reference '{name}' -> {hit[0]:.4f},{hit[1]:.4f} via {hit[2]}")
        return {"name": name, "lat": hit[0], "lng": hit[1], "precision": "place",
                "source": "first_named_place_906d"}
    except Exception as e:
        _log(log, f"  [LOCAL-906D] place reference retry for '{name}' skipped (non-fatal): {e}")
        return None


# ── item 3: a facility named after the stop ──────────────────────────────────────────────────────────────
def is_natural_stop(title: str, stop_type: str = "") -> bool:
    f = f" {fold(title)} {fold(stop_type)} "
    return any(f" {w} " in f for w in NATURAL_WORDS)


def _core_tokens(text: str) -> List[str]:
    try:
        import area_resolver as ar
        return [t for t in ar.name_core_tokens(text) if t]
    except Exception:
        return [t for t in fold(text).split() if t not in NATURAL_WORDS]


def facility_of_same_place(stop_title: str, ref_name: str, stop_type: str = "") -> bool:
    """True when the stop is a natural feature / area (mountain, hill, lake, beach, park, tourist area) and the
    reference's name is the stop's core name plus a facility word (station, cable car, gate, entrance, parking,
    visitor centre, ticket office, tourist area). A building named for another thing ("City Hall" vs a different
    building) is never this."""
    try:
        if not stop_title or not ref_name or not is_natural_stop(stop_title, stop_type):
            return False
        ref = f" {fold(ref_name)} "
        stripped, has_facility = ref, False
        for w in sorted(FACILITY_WORDS, key=len, reverse=True):
            if f" {w} " in stripped:
                stripped = stripped.replace(f" {w} ", " ", 1)
                has_facility = True
        if not has_facility:
            return False
        want = set(_core_tokens(stop_title))
        got = set(_core_tokens(stripped))
        return bool(want) and want == got
    except Exception:
        return False


# ── item 2: far pins ─────────────────────────────────────────────────────────────────────────────────────
def _pin(poi: Dict):
    import pin_snap
    return pin_snap._poi_coord(poi)


def _unverified(poi: Dict) -> bool:
    """A model-written pin: not the listener's own, not a Wikidata P625."""
    import pin_snap
    if pin_snap._is_user_pin(poi):
        return False
    if pin_snap._wikidata_coord(poi) is not None:
        return False
    return pin_snap._is_model_sourced_coord(poi)


def flag_far_pins(poi_list: List[Dict], box: Optional[Box], province: str,
                  log: Optional[Callable] = None) -> List[int]:
    """Indices (0-based) of stops whose UNVERIFIED model pin is outside the province box; each is logged
    ``[LOCAL-906D] stop=N model pin outside <province> (<km> km)``."""
    out: List[int] = []
    if not box:
        return out
    for i, p in enumerate(poi_list or []):
        try:
            c = _pin(p)
            if c is None or p.get("_no_coordinate") or not _unverified(p) or in_box(c, box):
                continue
            out.append(i)
            p["_pin_far_906d"] = True
            _log(log, f"  [LOCAL-906D] stop={i + 1} model pin outside {province} ({km_outside_box(c, box):.0f} km)")
        except Exception:
            continue
    return out


# ── item 4: the last resort ──────────────────────────────────────────────────────────────────────────────
def _set_pin(poi: Dict, pt: Tuple[float, float], donor: Optional[int] = None) -> None:
    if donor is not None:
        poi["_pin_moved_to_stop"] = int(donor)
    poi["coordinates"] = f"{pt[0]:.6f}, {pt[1]:.6f}"
    if "latitude" in poi or "longitude" in poi:
        poi["latitude"], poi["longitude"] = pt[0], pt[1]
    poi["coordinates_approximate"] = True
    poi["_pin_moved_906d"] = True
    poi.pop("_no_coordinate", None)


def _in_province_reference(rows: List[Dict], poi_list: List[Dict], box: Box, skip: int):
    """(index, point) of the best in-province reference any OTHER stop has: a verified snap first, then a
    stop's accepted approximate reference, then any reference inside the box."""
    import single_place_903 as sp
    best = None
    for j, r in enumerate(rows or []):
        if j == skip or not isinstance(r, dict):
            continue
        pt = tuple(r["new_coordinate"]) if r.get("snapped") and r.get("new_coordinate") else \
            (tuple(r["reference"]) if r.get("reference") else None)
        if pt is None or r.get("rejected_900b") or not in_box(pt, box):
            continue
        rank = 0 if sp._verified_snap(r) else (1 if r.get("approx_facility_906d") and r.get("snapped") else 2)
        if best is None or rank < best[0]:
            best = (rank, j, pt)
    if best is None:                  # a verified pin another stop already stands on
        for j, p in enumerate(poi_list or []):
            if j == skip:
                continue
            c = _pin(p)
            if c is not None and in_box(c, box) and not _unverified(p) and not p.get("_no_coordinate"):
                return j, c
        return None
    return best[1], best[2]


def last_resort_pins(poi_list: List[Dict], rows: List[Dict], box: Optional[Box], center,
                     province: str, log: Optional[Callable] = None) -> List[int]:
    """After the snap: a stop whose unverified pin is still outside the province box moves to the best in-province
    reference another stop has, else to the province centre (flagged approximate). Returns the moved indices.
    Never leaves a pin outside the scope province."""
    moved: List[int] = []
    if not box:
        return moved
    for i, p in enumerate(poi_list or []):
        try:
            c = _pin(p)
            if c is None or p.get("_no_coordinate") or in_box(c, box) or not _unverified(p):
                continue
            row = rows[i] if i < len(rows or []) else {}
            if row.get("snapped") and row.get("new_coordinate"):
                continue                               # a reference placed it (not a model pin any more)
            own = tuple(row["reference"]) if row.get("approx_facility_906d") and row.get("reference") else None
            if own is not None and in_box(own, box):          # its own approximate facility reference
                _set_pin(p, own)
                p["_pin_approx_facility_906d"] = True
                _log(log, f"  [LOCAL-906D] stop={i + 1} pin {c[0]:.4f},{c[1]:.4f} outside {province}: moved to its "
                          f"own approximate facility reference {own[0]:.4f},{own[1]:.4f}")
                moved.append(i)
                continue
            found = _in_province_reference(rows, poi_list, box, i)
            if found:
                j, pt = found
                _set_pin(p, pt, donor=j)
                _log(log, f"  [LOCAL-906D] stop={i + 1} pin {c[0]:.4f},{c[1]:.4f} outside {province}: moved to "
                          f"stop={j + 1}'s in-province reference {pt[0]:.4f},{pt[1]:.4f} (approximate)")
            else:
                ctr = tuple(center) if center else ((box[0] + box[1]) / 2.0, (box[2] + box[3]) / 2.0)
                if not in_box(ctr, box):
                    ctr = ((box[0] + box[1]) / 2.0, (box[2] + box[3]) / 2.0)
                _set_pin(p, ctr)
                p["_pin_province_centre_906d"] = True
                _log(log, f"  [LOCAL-906D] stop={i + 1} pin {c[0]:.4f},{c[1]:.4f} outside {province} and no "
                          f"in-province reference: moved to the {province} centre {ctr[0]:.4f},{ctr[1]:.4f} "
                          f"(approximate)")
            moved.append(i)
        except Exception as e:
            _log(log, f"  [LOCAL-906D] last-resort pin for stop={i + 1} skipped (non-fatal): {e}")
    return moved


# ── item 5: the address follows the pin ──────────────────────────────────────────────────────────────────
def address_follows_pin(poi: Dict, province: str, country: str = "", reverse_fn: Optional[Callable] = None,
                        log: Optional[Callable] = None) -> bool:
    """A stop whose pin was moved (last resort) or set to an approximate facility reference keeps no district /
    commune that the new pin cannot confirm. A part the reverse geocode of the new pin names is confirmed and
    kept; every other part except the stop's own name, the province and the country is dropped, so
    "<Stop>, <Wrong District>, <Province>, <Country>" becomes "<Stop>, <Province>, <Country>". Returns True when the
    address changed. Never raises."""
    try:
        addr = str(poi.get("address") or "").strip()
        if not addr or not (poi.get("_pin_moved_906d") or poi.get("_pin_approx_facility_906d")):
            return False
        parts = [x.strip() for x in addr.split(",") if x.strip()]
        rev = ""
        c = _pin(poi)
        if reverse_fn is not None and c is not None:
            try:
                rev = reverse_fn(c[0], c[1]) or ""
            except Exception:
                rev = ""
        rev_f = f" {fold(rev)} "
        prov_f, country_f = fold(province), fold(country)
        title_toks = set(_core_tokens(poi.get("name", "")))
        kept, dropped = [], []
        for i, part in enumerate(parts):
            f = fold(part)
            core = _PROVINCE_PREFIX.sub("", f)
            if not f or core == prov_f or f == prov_f or f == country_f or \
                    (i == len(parts) - 1 and len(parts) > 1 and f == country_f):
                kept.append(part)
            elif i == 0 or (title_toks and set(_core_tokens(part)) == title_toks):
                kept.append(part)                              # the stop's own name part
            elif rev and f" {_DISTRICT_PREFIX.sub('', f).strip()} " in rev_f and re.search(r"[a-z]", f):
                kept.append(part)                              # confirmed by the reverse geocode of the new pin
            else:
                dropped.append(part)
        if not dropped:
            return False
        has_prov = any(_PROVINCE_PREFIX.sub("", fold(x)) == prov_f for x in kept) if prov_f else True
        if not has_prov and province:
            kept.insert(min(1, len(kept)), province)
        if country and not any(fold(x) == country_f for x in kept):
            kept.append(country)
        poi["address"] = ", ".join(kept)
        _log(log, f"  [LOCAL-906D] address of {poi.get('name')!r} follows the moved pin: dropped "
                  f"{', '.join(dropped)!r} (not confirmed by the {province} box) -> {poi['address']!r}")
        return True
    except Exception as e:
        _log(log, f"  [LOCAL-906D] address check for {poi.get('name')!r} skipped (non-fatal): {e}")
        return False


def stop_type_text(poi: Dict) -> str:
    """The stop's Type as the poi dict carries it (several spellings across the pipeline)."""
    for k in ("type", "poi_type", "specialty", "type_specialty", "category", "kind"):
        v = poi.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""
