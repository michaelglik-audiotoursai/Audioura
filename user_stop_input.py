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

NO PAID API. A Google share link (share.google / maps.app.goo.gl / goo.gl/maps)
is resolved by following the HTTP redirect to the canonical Maps place URL and
parsing the place name + ``@lat,lng`` out of it. The network fetch is INJECTED
(``resolve``) so the deterministic core and every unit test run offline; the
default fetcher uses ``requests`` with redirects and a short timeout and NEVER
raises (a failed resolve degrades to geocode-by-name, never a drop).

A plain WEBSITE URL (an-spa.vn) is NOT a maps link: we keep the name and geocode
it within the city — the website is not a coordinate source.
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
    "default_resolver",
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
_MAPS_HOST_RE = re.compile(
    r"(?:share\.google|maps\.app\.goo\.gl|goo\.gl/maps|"
    r"(?:www\.)?google\.[a-z.]+/maps|maps\.google\.[a-z.]+)",
    re.IGNORECASE)

# ``@lat,lng`` or ``!3dLAT!4dLNG`` inside a resolved Maps URL.
_AT_LATLNG_RE = re.compile(r"@(-?\d{1,3}\.\d+),(-?\d{1,3}\.\d+)")
_BANG_LATLNG_RE = re.compile(r"!3d(-?\d{1,3}\.\d+)!4d(-?\d{1,3}\.\d+)")
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
    m = _AT_LATLNG_RE.search(url) or _BANG_LATLNG_RE.search(url)
    if m:
        try:
            lat, lng = float(m.group(1)), float(m.group(2))
        except (TypeError, ValueError):
            lat = lng = None
    return place_name, lat, lng


def default_resolver(url: str) -> Optional[str]:
    """Follow a share link's HTTP redirect to the canonical Maps URL and return
    the FINAL url string. No paid API — a plain GET with redirects. Never raises;
    returns None on any failure so the caller degrades to geocode-by-name."""
    try:
        import requests
    except Exception:
        return None
    try:
        headers = {
            "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120 Safari/537.36")
        }
        resp = requests.get(url, headers=headers, timeout=10,
                            allow_redirects=True)
        final = resp.url or ""
        # Some share links land on an interstitial whose canonical Maps URL is in
        # the body (a <meta>/<link> or a window.location). Pull the first
        # /maps/place or @lat,lng URL out of the HTML as a fallback.
        if not is_google_maps_link(final) or not _AT_LATLNG_RE.search(final):
            body = resp.text or ""
            m = re.search(r"https?://[^\"'\s]*/maps/place/[^\"'\s]+", body)
            if not m:
                m = re.search(r"https?://[^\"'\s]*@-?\d{1,3}\.\d+,-?\d{1,3}\.\d+[^\"'\s]*",
                              body)
            if m:
                return m.group(0)
        return final or None
    except Exception:
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
    ``[LOCAL-852] user stop resolved <name> <lat,lng> via <how>`` line."""
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
        out["how"] = "name_only"
        emit(f"[LOCAL-852] user stop resolved {name!r} (no coord — geocode by "
             f"name) via name_only")
        return out

    if is_google_maps_link(url):
        # A place URL that already carries @lat,lng needs no network.
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
        return out

    # A plain website URL (an-spa.vn): keep the name, geocode by name in the city.
    out["how"] = "website"
    out["needs_geocode"] = True
    emit(f"[LOCAL-852] user stop resolved {name!r} (website {url} — geocode by "
         f"name) via website")
    return out


def parse_user_stops(
    raw_list,
    *,
    resolve: Optional[Callable[[str], Optional[str]]] = None,
    log: Optional[Callable[[str], None]] = None,
) -> List[Dict]:
    """Map ``parse_user_stop`` over a list of raw "Name + URL" items, in order."""
    return [parse_user_stop(r, resolve=resolve, log=log) for r in (raw_list or [])]
