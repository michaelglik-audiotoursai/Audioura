#!/usr/bin/env python3
"""user_stop_input.py — LOCAL-852. Parse a listener's pasted "Name + URL" stops.

WHY THIS EXISTS (LEAD, GCloud_Storied_1, Michael's own request, gen 00027-6sb,
orch ef0cee57, tour 523): the listener pasted seven stops as a display NAME plus
a Google share link:

    "Rambutan https___share.google_1v4x…"
    "Longan https___share.google_z20B…"
    "The Crazy street …"
    "The LGBT bar 🌈Thi Bar Saigon …"
    "A Star is Born …"
    "Acoustic Bar - Ngô Thời Nhiệm …"
    "An Spa at https___an-spa.vn_en"

Two things went wrong with the raw strings:
  * the URL junk stayed in the DISPLAY NAME ("Rambutan https___share.google_1v4x")
    so the stop title read as garbage and geocoded to nothing;
  * the share links were never RESOLVED to a place, so four stops fell back to the
    same city centroid and the dedupe then collapsed them.

This module turns ONE raw "Name + URL" item into a clean stop:

  parse_user_stop(raw, *, resolve=..., log=...) -> {
      "name":   the display name with the URL removed (and the "https___"
                underscore-mangled form un-mangled / stripped),
      "url":    the extracted URL (un-mangled), or None,
      "lat", "lng":  a resolved coordinate when a Google-Maps share link resolved,
                else None,
      "resolved_name": a place name parsed from the resolved Maps URL, when better
                than the typed display name, else None,
      "how":    one of "share_redirect" | "maps_url" | "website" | "name_only",
      "needs_geocode": True when the stop has no coordinate and must be geocoded
                by NAME within the city (a plain website URL, or an unresolved
                link),
  }

parse_user_stops(raw_list, ...) maps it over a list.

NO PAID API for the share link itself. A Google share link (share.google /
maps.app.goo.gl / goo.gl/maps) is resolved by following the HTTP redirect to the
canonical Maps place URL and parsing the place name + ``@lat,lng`` (or
``?q=lat,lng``) out of it. The network fetch is INJECTED (``resolve``) so the
deterministic core and every unit test run offline; the default fetcher uses
``requests`` with a browser User-Agent, consent cookies and redirects, a short
timeout, and NEVER raises (a failed resolve degrades to name lookup, never a
drop).

[LOCAL-859] Google changed the share.google flow: ``https://share.google/<id>``
now 302s to ``https://www.google.com/share.google?q=<id>``, a JS-rendered page
with NO coordinate in the HTTP response — the old redirect-to-``/maps/place``
chain is gone, so every share.google link logged "unresolved" and user pins fell
back to the city centroid (tour 529, Sophia rerun). The fixes here:
  * ``default_resolver`` follows the full chain, reads the final page body for an
    embedded ``/maps/place`` / ``@lat,lng`` / ``!3d!4d`` / ``?q=lat,lng`` URL or a
    meta-refresh/canonical, and tries the ``maps?q=<id>`` / ``maps.google`` id
    endpoints as fallbacks;
  * ``parse_maps_place_url`` also reads ``?q=lat,lng`` query forms, and
    ``parse_plain_latlng`` accepts a bare ``lat,lng`` the listener pasted;
  * ``name_lookup_in_bbox`` is the fallback when a link cannot be resolved: look
    the venue up by NAME inside the tour city's bounding box (Serper ``/places``
    ≈$0.001, else Nominatim), pick the best name match INSIDE the box. The caller
    marks it ``coord_source='user_name_lookup'`` (weaker than ``user_share_link``).
    If nothing matches in the box, the stop has NO coordinate and is announced —
    it is NEVER the city centroid.

A plain WEBSITE URL (an-spa.vn) is NOT a maps link: we keep the name and look it
up by name within the city — the website is not a coordinate source.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, Dict, List, Optional
from urllib.parse import unquote

__all__ = [
    "parse_user_stop",
    "parse_user_stops",
    "unmangle_url",
    "strip_url_from_name",
    "is_google_maps_link",
    "parse_maps_place_url",
    "parse_plain_latlng",
    "default_resolver",
    "name_lookup_in_bbox",
]

# ── URL recognition ───────────────────────────────────────────────────────────
# A real URL, OR the "https___host_path" underscore-mangled form a copy/paste
# through a field that escaped the string produced ("https___share.google_1v4x",
# "https___an-spa.vn_en"). Matched anywhere in the raw item.
_URL_RE = re.compile(
    r"(https?://\S+|https?___\S+|www\.\S+)",
    re.IGNORECASE)

# Google-Maps share / place hosts. A link on one of these is a MAPS link whose
# redirect (share links) or path (place URLs) yields a coordinate.
# [LOCAL-859] Accept goo.gl/maps (bare) and maps.app.goo.gl short links, every
# google.<tld>/maps place URL, and maps.google.<tld>. share.google is the new
# flow (LOCAL-859): share.google/<id> now 302s to
# www.google.com/share.google?q=<id>.
_MAPS_HOST_RE = re.compile(
    r"(?:share\.google|maps\.app\.goo\.gl|(?:www\.)?goo\.gl/maps|"
    r"(?:www\.)?google\.[a-z.]+/maps|maps\.google\.[a-z.]+)",
    re.IGNORECASE)

# ``@lat,lng`` or ``!3dLAT!4dLNG`` inside a resolved Maps URL.
_AT_LATLNG_RE = re.compile(r"@(-?\d{1,3}\.\d+),(-?\d{1,3}\.\d+)")
_BANG_LATLNG_RE = re.compile(r"!3d(-?\d{1,3}\.\d+)!4d(-?\d{1,3}\.\d+)")
# [LOCAL-859] ``/maps?q=lat,lng`` or ``…?q=lat,lng`` / ``&query=lat,lng`` /
# ``!8m2!3d…`` — the query-parameter coordinate forms a plain Maps URL carries
# when it is not a ``/place/`` URL (``google.com/maps?q=10.77,106.70``). Parsed
# from the URL STRING only.
_Q_LATLNG_RE = re.compile(
    r"[?&](?:q|query|ll|center|daddr|destination)=(-?\d{1,3}\.\d+)"
    r"(?:,|%2C|%2c)(-?\d{1,3}\.\d+)",
    re.IGNORECASE)
# A plain ``lat,lng`` string a listener may paste directly (no URL at all).
_PLAIN_LATLNG_RE = re.compile(
    r"^\s*(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)\s*$")
# ``/maps/place/<Name>/…`` — the place name segment.
_PLACE_NAME_RE = re.compile(r"/maps/place/([^/@?]+)")


def unmangle_url(url: str) -> str:
    """Turn the underscore-mangled ``https___host_path`` form back into a real
    URL, and leave an already-valid URL unchanged.

    "https___share.google_1v4x"  -> "https://share.google/1v4x"
    "https___an-spa.vn_en"        -> "https://an-spa.vn/en"
    A string with no scheme marker is returned unchanged.

    The mangling replaces "://" with "___" and each "/" with "_". We restore the
    scheme separator, then restore path slashes AFTER the host (the first
    underscore following the host boundary and every one after it), leaving the
    host's own dots intact. Best-effort and deterministic."""
    if not url:
        return url
    s = url.strip()
    m = re.match(r"(?i)^(https?)___(.+)$", s)
    if not m:
        return s
    scheme, rest = m.group(1), m.group(2)
    # The host is the leading run up to the first underscore; everything after is
    # the path, whose "/" separators were turned into "_".
    host, sep, tail = rest.partition("_")
    path = tail.replace("_", "/") if sep else ""
    out = f"{scheme}://{host}"
    if path:
        out += "/" + path
    return out


def strip_url_from_name(raw: str) -> str:
    """Remove every URL (real or mangled) and trailing connector junk from a
    display name, returning the clean human name.

    "Rambutan https___share.google_1v4x"        -> "Rambutan"
    "An Spa at https___an-spa.vn_en"             -> "An Spa"
    "Acoustic Bar - Ngô Thời Nhiệm, Quận 3"      -> "Acoustic Bar - Ngô Thời Nhiệm, Quận 3"
    Keeps all non-URL text, including emoji and accents."""
    if not raw:
        return raw
    s = _URL_RE.sub(" ", raw)
    # A dangling locative/possessive connector left where the URL was removed
    # ("An Spa at " -> "An Spa", "Rambutan @ " -> "Rambutan").
    s = re.sub(r"\s*(?:\bat\b|\bon\b|\bvia\b|@|[-–—:|])\s*$", "", s.strip(),
               flags=re.IGNORECASE)
    # Collapse whitespace.
    return re.sub(r"\s+", " ", s).strip(" ,;")


def _extract_url(raw: str) -> Optional[str]:
    """The first URL in ``raw``, un-mangled, or None."""
    m = _URL_RE.search(raw or "")
    if not m:
        return None
    return unmangle_url(m.group(1))


def is_google_maps_link(url: str) -> bool:
    """True when ``url`` is a Google-Maps share or place link (share.google,
    maps.app.goo.gl, goo.gl/maps, google.com/maps, maps.google.*)."""
    if not url:
        return False
    return bool(_MAPS_HOST_RE.search(url))


def _clean_place_name(seg: str) -> str:
    """Turn a ``/maps/place/<seg>`` URL segment into a readable place name."""
    name = unquote(seg or "").replace("+", " ")
    name = name.replace("_", " ")
    return re.sub(r"\s+", " ", name).strip()


def parse_maps_place_url(url: str):
    """Parse a resolved Google-Maps URL for ``(place_name, lat, lng)``.

    Any of the three may be None. Reads ``/maps/place/<Name>`` for the name and
    ``@lat,lng`` (or ``!3dLAT!4dLNG``) for the coordinate. Deterministic,
    offline — operates on the URL STRING only."""
    if not url:
        return None, None, None
    place_name = None
    m = _PLACE_NAME_RE.search(url)
    if m:
        cand = _clean_place_name(m.group(1))
        # "Unnamed+Road" / a bare coordinate are not real names.
        if cand and not re.fullmatch(r"-?\d[\d.,\s]*", cand):
            place_name = cand
    lat = lng = None
    m = (_AT_LATLNG_RE.search(url) or _BANG_LATLNG_RE.search(url)
         or _Q_LATLNG_RE.search(url))
    if m:
        try:
            lat, lng = float(m.group(1)), float(m.group(2))
        except (TypeError, ValueError):
            lat = lng = None
    # Out-of-range pair is not a coordinate.
    if lat is not None and (abs(lat) > 90 or abs(lng) > 180):
        lat = lng = None
    return place_name, lat, lng


def parse_plain_latlng(text: str):
    """[LOCAL-859] Parse a bare ``lat,lng`` string a listener pasted with no URL
    ("10.7725, 106.6985") into ``(lat, lng)``, or ``(None, None)``. Rejects an
    out-of-range pair so a stray number pair is not read as a coordinate."""
    if not text:
        return None, None
    m = _PLAIN_LATLNG_RE.match(text)
    if not m:
        return None, None
    try:
        lat, lng = float(m.group(1)), float(m.group(2))
    except (TypeError, ValueError):
        return None, None
    if abs(lat) > 90 or abs(lng) > 180:
        return None, None
    return lat, lng


def _coord_url_in_body(body: str):
    """[LOCAL-859] Pull the first Maps URL carrying a coordinate out of an HTML
    body — a ``/maps/place/…`` URL, an ``@lat,lng`` URL, a ``!3d…!4d…`` blob, or a
    ``?q=lat,lng`` / ``?query=lat,lng`` URL. Returns the matched URL/string or
    None. Operates on the body STRING only (no network)."""
    if not body:
        return None
    # A full /maps/place URL is the richest (name + coord); prefer it.
    m = re.search(r"https?://[^\"'\\\s]*/maps/place/[^\"'\\\s]+", body)
    if m:
        return m.group(0)
    # A maps URL (or any URL) carrying @lat,lng.
    m = re.search(r"https?://[^\"'\\\s]*@-?\d{1,3}\.\d+,-?\d{1,3}\.\d+[^\"'\\\s]*",
                  body)
    if m:
        return m.group(0)
    # A !3dLAT!4dLNG blob (APP_INITIALIZATION_STATE / embedded JSON).
    m = _BANG_LATLNG_RE.search(body)
    if m:
        return m.group(0)
    # A ?q=lat,lng / ?query=lat,lng URL (maps?q=… form).
    m = re.search(r"https?://[^\"'\\\s]*[?&](?:q|query|ll|destination)="
                  r"-?\d{1,3}\.\d+(?:,|%2[Cc])-?\d{1,3}\.\d+[^\"'\\\s]*", body)
    if m:
        return m.group(0)
    # A meta-refresh / canonical / og:url pointing at a maps URL.
    m = re.search(r'(?:url=|href=|content=)["\']?'
                  r'(https?://[^"\'\s>]*(?:/maps/place/|/maps\?|@-?\d)[^"\'\s>]*)',
                  body, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _share_id(url: str):
    """[LOCAL-859] The opaque id of a share.google link — the last path segment of
    ``share.google/<id>`` or the ``q`` parameter of
    ``www.google.com/share.google?q=<id>``. None when ``url`` is not a
    share.google link."""
    if not url:
        return None
    m = re.search(r"(?i)share\.google(?:/|\?q=)([^/?&#\s]+)", url)
    if m and m.group(1).lower() not in ("error", ""):
        return m.group(1)
    return None


def default_resolver(url: str) -> Optional[str]:
    """[LOCAL-859] Follow a Google share link to a canonical Maps URL and return
    the FINAL url string (or an extracted coordinate URL). No paid API — a plain
    GET with a browser User-Agent and consent cookies, redirects followed. Never
    raises; returns None on any failure so the caller degrades to name lookup.

    The new share.google flow (LOCAL-859): ``https://share.google/<id>`` now 302s
    to ``https://www.google.com/share.google?q=<id>``, a JS-rendered page with no
    coordinate in the HTTP response — the old redirect-to-/maps/place chain is
    gone. We therefore try, in order, until one yields a coordinate:
      1. the full redirect chain (a maps.app.goo.gl / goo.gl/maps / older
         share.google link still lands on a /maps/place URL);
      2. the FINAL page body (a /maps/place, @lat,lng, !3d!4d or ?q=lat,lng URL
         embedded in the HTML, a meta-refresh, or og:url/canonical);
      3. for a share.google id, the equivalent ``www.google.com/maps?q=<id>`` and
         ``maps.google.com/?q=<id>`` endpoints, whose body often carries the place
         when the share page does not.
    Returns the first URL that ``parse_maps_place_url`` can read a coordinate
    from, else the final URL (so a place NAME may still be recovered), else None.
    """
    try:
        import requests
    except Exception:
        return None

    headers = {
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120 Safari/537.36"),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "image/avif,image/webp,*/*;q=0.8"),
    }

    def _has_coord(u):
        if not u:
            return False
        _n, _la, _ln = parse_maps_place_url(u)
        return _la is not None and _ln is not None

    try:
        sess = requests.Session()
        sess.headers.update(headers)
        # Consent cookies so an EU consent interstitial does not swallow the body.
        try:
            sess.cookies.set("CONSENT", "YES+cb", domain=".google.com")
            sess.cookies.set("SOCS", "CAI", domain=".google.com")
        except Exception:
            pass

        def _fetch(u):
            try:
                return sess.get(u, timeout=12, allow_redirects=True)
            except Exception:
                return None

        resp = _fetch(url)
        candidates = []
        if resp is not None:
            final = resp.url or ""
            if _has_coord(final):
                return final
            candidates.append(final)
            body = resp.text or ""
            found = _coord_url_in_body(body)
            if found and _has_coord(found):
                return found
            if found:
                candidates.append(found)

        # [LOCAL-859] share.google new-flow fallback endpoints: resolve the id
        # through maps?q / maps.google so the place is recovered when the share
        # page is JS-only.
        sid = _share_id(resp.url if resp is not None else url) or _share_id(url)
        if sid:
            for alt in (f"https://www.google.com/maps?q={sid}",
                        f"https://maps.google.com/?q={sid}",
                        f"https://www.google.com/maps/search/{sid}"):
                r2 = _fetch(alt)
                if r2 is None:
                    continue
                if _has_coord(r2.url):
                    return r2.url
                found = _coord_url_in_body(r2.text or "")
                if found and _has_coord(found):
                    return found

        # Nothing carried a coordinate. Return the best non-empty candidate (a
        # place NAME may still be parseable) so the caller can name-lookup it.
        for c in candidates:
            if c:
                return c
        return None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# [LOCAL-859] NAME-LOOKUP FALLBACK — venue by NAME inside the city bounding box
# ─────────────────────────────────────────────────────────────────────────────
#
# When a share link cannot be resolved to a coordinate, look the venue up by its
# NAME inside the tour city's bounding box. Serper /places first (≈$0.001/query,
# metered), else free Nominatim. Pick the best name match INSIDE the box. The
# result is marked weaker than a resolved share link (coord_source handled by the
# caller). If nothing matches in the box, the stop has NO coordinate — it is
# announced, NEVER placed on the city centroid.

def _fold_name(s: str) -> str:
    """Accent-stripped, lowercase, whitespace-collapsed name for matching."""
    if not s:
        return ""
    folded = "".join(c for c in unicodedata.normalize("NFKD", s)
                     if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", folded.lower()).strip()


def _in_bbox(lat, lng, bbox, margin_km: float = 0.5) -> bool:
    """True when (lat,lng) is inside ``bbox`` = (south, north, west, east),
    expanded by ``margin_km`` on every side. Longitude margin widens with
    latitude. A missing/malformed bbox returns True (cannot prove outside)."""
    if not bbox:
        return True
    import math
    try:
        south, north, west, east = (float(bbox[0]), float(bbox[1]),
                                    float(bbox[2]), float(bbox[3]))
    except (TypeError, ValueError, IndexError):
        return True
    if south > north:
        south, north = north, south
    if west > east:
        west, east = east, west
    dlat = margin_km / 111.0
    coslat = max(0.01, math.cos(math.radians((south + north) / 2.0)))
    dlon = margin_km / (111.0 * coslat)
    return (south - dlat) <= lat <= (north + dlat) and \
           (west - dlon) <= lng <= (east + dlon)


def _haversine_km(a, b) -> float:
    """Great-circle km between two (lat, lng) pairs; inf if either is missing."""
    if not a or not b:
        return float("inf")
    import math
    try:
        lat1, lon1 = float(a[0]), float(a[1])
        lat2, lon2 = float(b[0]), float(b[1])
    except (TypeError, ValueError, IndexError):
        return float("inf")
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def _name_match_score(query_name: str, result_name: str) -> float:
    """A 0..1 name-match score between the listener's typed name and a candidate
    result name — folded token overlap (Jaccard), with a boost for an exact or
    containment match. Used to pick the BEST match among in-box candidates."""
    q = _fold_name(query_name)
    r = _fold_name(result_name)
    if not q or not r:
        return 0.0
    if q == r:
        return 1.0
    if q in r or r in q:
        return 0.9
    qt = set(q.split())
    rt = set(r.split())
    if not qt or not rt:
        return 0.0
    inter = len(qt & rt)
    union = len(qt | rt)
    return inter / union if union else 0.0


def name_lookup_in_bbox(
    name: str,
    city: str,
    bbox=None,
    center=None,
    *,
    serper_fn: Optional[Callable] = None,
    nominatim_fn: Optional[Callable] = None,
    min_score: float = 0.34,
    max_radius_km: float = 25.0,
    log: Optional[Callable[[str], None]] = None,
):
    """[LOCAL-859] Look a venue up by NAME inside the tour city's bounding box.

    Tries Serper /places first (≈$0.001/query, metered), else Nominatim. Returns
    ``(lat, lng, source, matched_name)`` for the best name match that falls INSIDE
    the city — the ``bbox`` (when given) AND within ``max_radius_km`` of
    ``center`` (when given) — with a name-match score ≥ ``min_score``. Returns
    ``None`` when nothing in the city matches, in which case the caller leaves the
    stop WITHOUT a coordinate (announced), NEVER the city centroid.

    ``source`` is ``"serper"`` or ``"nominatim"``. ``serper_fn(name, city, center)
    -> [{name/title, lat, lon/lng}, …]`` and ``nominatim_fn(name, city) ->
    [{name/display_name, lat, lon, boundingbox?}, …]`` are injected for offline
    tests; the defaults call the project's metered Serper caller
    (``places_search``) and ``geocode_stops``.

    ``bbox`` is (south, north, west, east); ``center`` is (lat, lng). A candidate
    OUTSIDE the box OR more than ``max_radius_km`` from ``center`` is rejected even
    when its name matches — a same-named venue in London/Miami, or a correct-named
    one in a far suburb, is never kept. The radius guard is the backstop that
    holds even when a city's administrative bbox is huge (HCMC's spans ~350 km) or
    unavailable, so the fallback cannot fail open to another continent."""
    emit = log or (lambda *_a, **_k: None)
    name = (name or "").strip()
    if not name:
        return None

    def _default_serper(nm, cty, ctr):
        try:
            import places_search as _ps
            if not _ps.serper_places_enabled():
                return []
            ll = None
            if ctr:
                try:
                    ll = f"@{float(ctr[0])},{float(ctr[1])},12z"
                except (TypeError, ValueError, IndexError):
                    ll = None
            raw = _ps._serper_places_call(nm, ll, location=cty or None)
            if not raw and cty:
                raw = _ps._serper_places_call(f"{nm}, {cty}", ll, location=cty)
            return raw or []
        except Exception:
            return []

    def _default_nominatim(nm, cty):
        # Free Nominatim via geocode_stops; return a single-record list.
        try:
            import geocode_stops as _gs
            q = f"{nm}, {cty}" if cty and cty.lower() not in nm.lower() else nm
            pt = _gs.geocode(q)
            if pt:
                return [{"name": nm, "lat": pt[0], "lon": pt[1]}]
        except Exception:
            pass
        return []

    sfn = serper_fn or _default_serper
    nfn = nominatim_fn or _default_nominatim

    def _coord_of(rec):
        try:
            lat = float(rec.get("lat") if rec.get("lat") is not None
                        else rec.get("latitude"))
            lng = float(rec.get("lon") if rec.get("lon") is not None
                        else (rec.get("lng") if rec.get("lng") is not None
                              else rec.get("longitude")))
        except (TypeError, ValueError):
            return None
        if abs(lat) > 90 or abs(lng) > 180:
            return None
        return (lat, lng)

    def _name_of(rec):
        return (rec.get("name") or rec.get("title")
                or rec.get("display_name") or "")

    def _best_in_box(records, source):
        best = None
        best_score = -1.0
        for rec in records or []:
            if not isinstance(rec, dict):
                continue
            pt = _coord_of(rec)
            if pt is None:
                continue
            # Containment: inside the bbox (when given) AND within max_radius_km
            # of the city centre (when given). The radius backstop holds even
            # when the bbox is a huge administrative extent or absent, so a
            # same-named venue on another continent — or in a far suburb — is
            # rejected rather than let the fallback fail open.
            if not _in_bbox(pt[0], pt[1], bbox):
                continue
            if center is not None:
                try:
                    if _haversine_km((pt[0], pt[1]), center) > float(max_radius_km):
                        continue
                except Exception:
                    pass
            score = _name_match_score(name, _name_of(rec))
            if score >= min_score and score > best_score:
                best_score = score
                best = (pt[0], pt[1], source, _name_of(rec).strip())
        return best, best_score

    # 1) Serper /places (metered). Best in-box match wins.
    try:
        serp_records = sfn(name, city, center)
    except Exception:
        serp_records = []
    best, score = _best_in_box(serp_records, "serper")
    if best:
        emit(f"[LOCAL-859] user link unresolved {name!r} → name lookup "
             f"{best[0]:.6f},{best[1]:.6f} via serper (match {best[3]!r} "
             f"score {score:.2f})")
        return best

    # 2) Nominatim (free) fallback.
    try:
        nom_records = nfn(name, city)
    except Exception:
        nom_records = []
    best, score = _best_in_box(nom_records, "nominatim")
    if best:
        emit(f"[LOCAL-859] user link unresolved {name!r} → name lookup "
             f"{best[0]:.6f},{best[1]:.6f} via nominatim (match {best[3]!r} "
             f"score {score:.2f})")
        return best

    emit(f"[LOCAL-859] user link unresolved {name!r} → name lookup NO MATCH in "
         f"box (stop announced, no coordinate — never centroid)")
    return None


def parse_user_stop(
    raw: str,
    *,
    resolve: Optional[Callable[[str], Optional[str]]] = None,
    log: Optional[Callable[[str], None]] = None,
) -> Dict:
    """Parse ONE raw "Name + URL" stop item into a clean stop dict (see module
    docstring for the shape).

    ``resolve`` is an injected ``url -> final_url`` fetcher for Google-Maps share
    links (defaults to ``default_resolver``; pass a stub offline). It is called
    ONLY for a Google-Maps link, at most once. ``log`` receives the mandated
    ``[LOCAL-852] user stop resolved <name> <lat,lng> via <how>`` line and, for a
    link, the ``[LOCAL-859] user link resolved/unresolved …`` line.

    [LOCAL-859] A plain ``lat,lng`` the listener pasted (no URL) is taken as the
    coordinate directly. A Google-Maps link is resolved through the new
    share.google 302 flow; when it still cannot be resolved the stop is marked
    ``needs_geocode`` so the caller can look it up by NAME in the city box — it is
    NEVER placed on the city centroid."""
    emit = log or (lambda *_a, **_k: None)
    resolve = resolve if resolve is not None else default_resolver

    text = (raw or "").strip()
    url = _extract_url(text)
    name = strip_url_from_name(text)

    out: Dict = {
        "raw": raw, "name": name, "url": url,
        "lat": None, "lng": None, "resolved_name": None,
        "how": "name_only", "needs_geocode": True,
    }

    if not url:
        # [LOCAL-859] A bare "lat,lng" string is a direct coordinate.
        plat, plng = parse_plain_latlng(text)
        if plat is not None and plng is not None:
            out["lat"], out["lng"] = plat, plng
            out["needs_geocode"] = False
            out["how"] = "latlng"
            # The name is just the coordinate text; leave it, the caller titles it.
            emit(f"[LOCAL-852] user stop resolved {name!r} "
                 f"{plat:.6f},{plng:.6f} via latlng")
            emit(f"[LOCAL-859] user link resolved {name!r} {plat:.6f},{plng:.6f} "
                 f"via plain_latlng")
            return out
        out["how"] = "name_only"
        emit(f"[LOCAL-852] user stop resolved {name!r} (no coord — geocode by "
             f"name) via name_only")
        return out

    if is_google_maps_link(url):
        # A place URL that already carries @lat,lng (or ?q=lat,lng) needs no
        # network.
        pname, lat, lng = parse_maps_place_url(url)
        how = "maps_url"
        if lat is None or lng is None:
            final = None
            try:
                final = resolve(url)
            except Exception:
                final = None
            if final:
                pname2, lat2, lng2 = parse_maps_place_url(final)
                pname = pname2 or pname
                if lat2 is not None and lng2 is not None:
                    lat, lng = lat2, lng2
                    how = "share_redirect"
        if lat is not None and lng is not None:
            out["lat"], out["lng"] = lat, lng
            out["needs_geocode"] = False
        if pname:
            out["resolved_name"] = pname
            # Prefer the resolved place name only when the typed name is empty or
            # was pure URL junk; otherwise keep what the listener typed.
            if not name:
                out["name"] = pname
        out["how"] = how
        _coord = (f"{out['lat']:.6f},{out['lng']:.6f}"
                  if out["lat"] is not None else "unresolved")
        emit(f"[LOCAL-852] user stop resolved {out['name']!r} {_coord} via {how}")
        # [LOCAL-859] The mandated resolution line: resolved <name> <lat,lng> via
        # <how>, or unresolved so the caller name-looks it up in the city box.
        if out["lat"] is not None:
            emit(f"[LOCAL-859] user link resolved {out['name']!r} {_coord} "
                 f"via {how}")
        else:
            emit(f"[LOCAL-859] user link unresolved {out['name']!r} ({url}) "
                 f"→ name lookup pending (never centroid)")
        return out

    # A plain website URL (an-spa.vn): keep the name, geocode by name in the city.
    out["how"] = "website"
    out["needs_geocode"] = True
    emit(f"[LOCAL-852] user stop resolved {name!r} (website {url} — geocode by "
         f"name) via website")
    emit(f"[LOCAL-859] user link unresolved {name!r} (website {url}) "
         f"→ name lookup pending (never centroid)")
    return out


def parse_user_stops(
    raw_list,
    *,
    resolve: Optional[Callable[[str], Optional[str]]] = None,
    log: Optional[Callable[[str], None]] = None,
) -> List[Dict]:
    """Map ``parse_user_stop`` over a list of raw "Name + URL" items, in order."""
    return [parse_user_stop(r, resolve=resolve, log=log) for r in (raw_list or [])]
