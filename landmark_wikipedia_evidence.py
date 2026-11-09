#!/usr/bin/env python3
"""landmark_wikipedia_evidence.py -- LOCAL-872B: the stop's own Wikipedia article
as claim-gate evidence.

LOCAL-872's claim gate dropped TRUE, important facts (Notre-Dame Cathedral built
1863-1880 and consecrated 1959, Independence Palace's architect) only because the
stop's research snippets lacked them.  A landmark's Wikipedia article (lead +
infobox: built, architect, opened, style, capacity...) is the authority for exactly
those facts, so the gate must be handed it.

  fetch_article(name, lang)  -> {'title','lead','infobox'} | None  (free MediaWiki API)
  evidence_for(name, ...)    -> [str, ...]  one item per language: lead + infobox facts

Languages: English always, plus the local language of the tour's country (vi for
Vietnam).  Results (hits AND misses) are CACHED in the venue-cache database, the same
connection and TTL discipline as the P625 lookup (``landmark_coord_cache``), in table
``landmark_wiki_cache``.  Silent no-op when no DB is configured.

The article must NAME-MATCH the stop (``landmark_second_authority.name_matches``) so a
search for "Notre-Dame Cathedral Basilica of Saigon" never feeds the gate an unrelated
page.  ``fetch_fn`` is injectable so the module is unit-tested offline.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

__all__ = ["fetch_article", "evidence_for", "local_languages", "parse_infobox"]

CACHE_TTL_DAYS = int(os.environ.get("LANDMARK_WIKI_CACHE_TTL_DAYS", "90"))
CACHE_NEG_TTL_DAYS = int(os.environ.get("LANDMARK_WIKI_CACHE_NEG_TTL_DAYS", "3"))

# LOCAL-878: the geo-gate. An article whose own coordinate is more than this many km
# from the stop's pin is a DIFFERENT place (the bare-name "Opera House" search returned
# the Sydney article, 6,834 km from a District-1 pin). 2 km is wide enough to admit the
# article's coordinate when it is pinned to a neighbouring entrance / plaza of the SAME
# venue (Wikipedia often pins a large complex to its centroid, a few hundred metres from
# a specific gate), yet far tighter than any same-name place in another city — the metro
# radius a genuine different-city hit would exceed is tens to thousands of km.
GEO_GATE_KM = float(os.environ.get("LANDMARK_WIKI_GEO_GATE_KM", "2.0"))
# LOCAL-881: the dense-centre gate. In a packed city centre, two unrelated civic
# buildings can sit well within the 2 km LOCAL-878 gate (the Gia Long Palace is
# ≈600 m from the Hôtel de Ville). An article whose title does NOT share a
# distinctive name token with the stop must therefore sit within this tighter
# radius, or it is a different venue and is rejected.
DENSE_CENTRE_KM = float(os.environ.get("LANDMARK_WIKI_DENSE_CENTRE_KM", "0.3"))

# LOCAL-882: a cached article is re-validated against the CURRENT acceptance rules
# on every read, so a rule change (a new gate, a tighter radius) can never be
# bypassed by an article cached under the OLD rules. Two mechanisms, together:
#
#   1. RULES_VERSION is stamped on every cache row. A read whose row carries a
#      DIFFERENT version is ignored (treated as a miss) and re-fetched — the new
#      row overwrites the old via ON CONFLICT, so NOTHING is ever DELETEd. BUMP
#      this string whenever the _pick acceptance rules change (a new gate, a new
#      radius, a new name test), and every stale entry drops out on next read.
#
#   2. Even for a same-version row, the cached payload's TITLE is re-checked with
#      the CURRENT name + dense-centre rules against the stop pin on every read
#      (``_revalidate_payload``). This is the belt-and-braces guard: it catches a
#      row that is the current version but whose stored article the present rules
#      would no longer pick (e.g. a different nearby venue the title does not name).
#
# Wave 40 (LOCAL-882): the Gia Long Palace article, cached for the "City Hall" pin
# in waves 36-39 (before LOCAL-881's 300 m dense-centre rule), was returned on a
# cache HIT without re-running _pick, so it bypassed the new rule and the City
# Hall stop shipped the Gia Long Palace again. Bumping RULES_VERSION to the
# LOCAL-881 value retires that row; the payload re-check rejects it even if the
# version matched.
RULES_VERSION = os.environ.get("LANDMARK_WIKI_RULES_VERSION", "local881-dense300")

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
_MAX_LEAD = 6000
_MAX_INFOBOX = 2500
_INFOBOX_KEYS = (
    "built", "construction", "construction_start", "construction_end", "completed",
    "completion_date", "opened", "opening", "opening_date", "open", "established",
    "founded", "date", "dedicated", "consecrated", "inaugurated", "start_date",
    "end_date", "architect", "architects", "architectural_style", "style", "designer",
    "builder", "engineer", "capacity", "seating_capacity", "owner", "built_for",
    "years_built", "year_built", "yearbuilt", "year_completed", "designation",
    "namesake", "former_names", "restored", "renovated", "height", "floors",
    "kiến_trúc_sư", "kiến trúc sư", "phong_cách", "khởi_công", "hoàn_thành",
    "xây_dựng", "khánh_thành", "ngày_khởi_công", "ngày_hoàn_thành", "thành_lập",
    "ngày_khánh_thành", "năm_xây_dựng", "kiến_trúc", "thiết_kế",
)

_COUNTRY_LANG = (
    (("vietnam", "viet nam", "việt nam", "hanoi", "hà nội", "ho chi minh", "saigon",
      "hcmc", "hue", "huế", "da nang", "đà nẵng", "hoi an"), "vi"),
    (("france", "paris", "lyon", "marseille", "nice"), "fr"),
    (("spain", "madrid", "barcelona", "seville"), "es"),
    (("italy", "rome", "venice", "florence", "milan"), "it"),
    (("germany", "berlin", "munich"), "de"),
    (("portugal", "lisbon", "porto"), "pt"),
    (("japan", "tokyo", "kyoto", "osaka"), "ja"),
    (("thailand", "bangkok"), "th"),
)


def local_languages(location: str) -> List[str]:
    """['en', 'vi'] for an HCMC / Hanoi tour; ['en'] when no local language is known."""
    loc = (location or "").lower()
    out = ["en"]
    for keys, lang in _COUNTRY_LANG:
        if any(k in loc for k in keys) and lang not in out:
            out.append(lang)
            break
    return out


# ---- infobox parsing ---------------------------------------------------------
def _clean_wikitext(v: str) -> str:
    v = re.sub(r"<!--.*?-->", " ", v or "", flags=re.S)
    v = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", " ", v, flags=re.S)
    v = re.sub(r"<br\s*/?>", ", ", v, flags=re.I)
    v = re.sub(r"<[^>]+>", " ", v)
    for _ in range(4):                       # nested templates
        v = re.sub(r"\{\{\s*(?:start date|end date|birth date|death date|start-date|"
                   r"nowrap|convert|ubl|plainlist|flatlist|hlist)\s*\|([^{}]*)\}\}",
                   lambda m: " ".join(p for p in m.group(1).split("|")
                                      if "=" not in p), v, flags=re.I)
        v = re.sub(r"\{\{[^{}|]*\|([^{}]*)\}\}",
                   lambda m: " ".join(p for p in m.group(1).split("|") if "=" not in p), v)
    v = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", v)
    v = re.sub(r"'{2,}", "", v)
    v = re.sub(r"[{}\[\]]", " ", v)
    v = re.sub(r"\s+", " ", v).strip(" ,;|")
    return v


def parse_infobox(wikitext: str) -> str:
    """'built: 1863-1880; architect: Jules Bourard; ...' from the first infobox in the
    wikitext (en 'Infobox ...' or vi 'Thông tin ...').  '' when none."""
    if not wikitext:
        return ""
    m = re.search(r"\{\{\s*(?:Infobox|Thông tin|Hộp thông tin)", wikitext, flags=re.I)
    if not m:
        return ""
    block = wikitext[m.start(): m.start() + 12000]
    facts: List[str] = []
    for line in re.split(r"\n\s*\|", block):
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        key = re.sub(r"\s+", "_", k.strip().lower())
        if key not in _INFOBOX_KEYS and key.replace("_", " ") not in _INFOBOX_KEYS:
            continue
        val = _clean_wikitext(v)
        if val and len(val) < 400:
            facts.append(f"{key.replace('_', ' ')}: {val}")
    return "; ".join(facts)[:_MAX_INFOBOX]


# ---- live fetch --------------------------------------------------------------
def _http_json(lang: str, params: dict) -> Optional[dict]:
    try:
        from venue_resolver import _request_with_backoff, _USER_AGENT
        r = _request_with_backoff(
            f"https://{lang}.wikipedia.org/w/api.php", params=params,
            headers={"User-Agent": _USER_AGENT}, timeout=12,
            host_for_cold=f"{lang}.wikipedia.org", label="LOCAL-872B wiki")
        if r is None or getattr(r, "status_code", 0) != 200:
            return None
        return r.json()
    except Exception:
        return None


def _page_coord(p: dict) -> Optional[tuple]:
    """(lat, lng) from a MediaWiki page's ``coordinates`` list, else None. LOCAL-878:
    the article's OWN coordinate, used by the geo-gate to prove it sits at the stop pin
    (so a bare "Opera House" search can never feed the Sydney article to a Saigon stop)."""
    for c in (p.get("coordinates") or []):
        lat, lng = c.get("lat"), c.get("lon")
        if lat is not None and lng is not None:
            try:
                return (float(lat), float(lng))
            except (TypeError, ValueError):
                continue
    return None


def _pages_from(data):
    pages = ((data or {}).get("query") or {}).get("pages") or []
    pages = sorted((p for p in pages if isinstance(p, dict)), key=lambda p: p.get("index", 99))
    return [{
        "title": p.get("title", ""), "lead": p.get("extract", "") or "",
        "wikitext": (((p.get("revisions") or [{}])[0].get("slots") or {})
                     .get("main") or {}).get("content", "") or "",
        "langlinks": [l.get("title", "") for l in (p.get("langlinks") or [])],
        "coord": _page_coord(p),
        "qid": (p.get("pageprops") or {}).get("wikibase_item", "") or "",
    } for p in pages if not p.get("missing")]


# LOCAL-878: ask for the article's OWN coordinate (prop=coordinates) and its Wikidata
# item (pageprops.wikibase_item, so a P625 fallback is possible) alongside the lead +
# infobox, in ONE call per page.
_CONTENT = {"prop": "extracts|revisions|coordinates|pageprops",
            "exintro": "1", "explaintext": "1", "exlimit": "3",
            "rvprop": "content", "rvslots": "main", "rvsection": "0",
            "coprop": "type|name", "colimit": "5", "ppprop": "wikibase_item"}


def _default_fetch(name: str, lang: str) -> Optional[Dict]:
    """Search hits for ``name`` on <lang>.wikipedia.org -> lead extract + section-0
    wikitext (infobox).  For a non-English language the English article's
    interlanguage link is followed first (a vi title rarely string-matches the English
    stop name); that page is 'trusted'."""
    base = {"action": "query", "format": "json", "formatversion": "2"}
    if lang != "en":
        d = _http_json("en", dict(base, generator="search", gsrsearch=name, gsrlimit="3",
                                  prop="langlinks", lllang=lang, lllimit="10"))
        if d is None:
            return None
        for p in _pages_from(d):
            if _name_ok(name, p["title"]) and p["langlinks"]:
                got = _pages_from(_http_json(lang, dict(base, titles=p["langlinks"][0], **_CONTENT)))
                if got:
                    return {"pages": got, "trusted": True}
    data = _http_json(lang, dict(base, generator="search", gsrsearch=name, gsrlimit="3",
                                 **_CONTENT))
    if data is None:
        return None
    return {"pages": _pages_from(data)}


def _name_ok(stop: str, page_title: str) -> bool:
    try:
        from landmark_second_authority import name_matches
        return bool(name_matches(stop, page_title))
    except Exception:
        return False


def _lead_names(name: str, lead: str) -> bool:
    """The article's own lead gives the stop's name as an alias ("also the Municipal
    Theatre ... Saigon Opera House") -- the lead is the first 400 chars only."""
    try:
        from landmark_second_authority import _fold
    except Exception:
        return False
    n = _fold(name)
    return len(n) >= 8 and n in _fold((lead or "")[:400])


# ---- LOCAL-878 geo-gate ------------------------------------------------------
def _haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    R = 6371.0
    la1, lo1 = math.radians(a[0]), math.radians(a[1])
    la2, lo2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * R * math.asin(min(1.0, math.sqrt(h)))


# LOCAL-881: words that name a KIND of civic/landmark venue, not a specific one.
# Two different buildings can share all of these ("Ho Chi Minh City Hall" vs
# "Gia Long Palace" share none; "City Hall" vs "Town Hall" share only kind words),
# so they do not count as a distinctive shared name token. Generic, not tied to a
# tour (D769); the city's own name is handled by _city_named, not here.
_GENERIC_NAME_WORDS = frozenset({
    "the", "of", "and", "de", "du", "la", "le", "des", "city", "town", "hall",
    "palace", "house", "building", "museum", "cathedral", "basilica", "church",
    "opera", "theatre", "theater", "square", "street", "road", "avenue",
    "boulevard", "bridge", "tower", "gate", "park", "pier", "wharf", "quay",
    "station", "market", "monument", "memorial", "centre", "center", "office",
    "post", "central", "committee", "people", "peoples", "government", "national",
    "municipal", "provincial", "cong", "trade", "commercial", "old",
})


def _distinctive_name_tokens(s: str) -> set:
    """Folded tokens of a name that are NOT generic venue/kind words — the tokens
    that pick out THIS venue ("vildieu"/"foulhoux"/"gia"/"long"/"bach"/"dang"),
    not its kind ("hall"/"palace")."""
    return {t for t in re.findall(r"[a-z0-9]+", _fold2(s or ""))
            if len(t) >= 3 and t not in _GENERIC_NAME_WORDS}


def _distinctive_name_tokens(s: str, city: str = "") -> set:
    """Folded tokens of a name that are NOT generic venue/kind words and NOT the
    tour city's own words — the tokens that pick out THIS venue
    ("vildieu"/"foulhoux"/"gia"/"long"/"bach"/"dang"), not its kind ("hall"/
    "palace") nor the city ("ho"/"chi"/"minh"), which every central article shares."""
    city_toks = {t for t in re.findall(r"[a-z0-9]+", _fold2(city or ""))} if city else set()
    return {t for t in re.findall(r"[a-z0-9]+", _fold2(s or ""))
            if len(t) >= 3 and t not in _GENERIC_NAME_WORDS and t not in city_toks}


def _titles_share_distinctive_token(stop_name: str, title: str, city: str = "") -> bool:
    """True when the article title shares a distinctive name token with the stop
    name — i.e. the title really names this venue, not just its kind or the city.
    "Ho Chi Minh City Hall" vs "Gia Long Palace" share none (both drop to kind +
    city words); "Saigon Opera House" vs "Nhà hát Thành phố" share none either.

    When the STOP name has no distinctive token of its own (a bare "Opera House",
    "City Hall" once kind + city words are removed), this sub-condition is vacuously
    satisfied (returns True); the 300 m distance test alone then decides."""
    a = _distinctive_name_tokens(stop_name, city)
    if not a:
        return True
    return bool(a & _distinctive_name_tokens(title, city))


def _p625_for_qid(qid: str) -> Optional[Tuple[float, float]]:
    """P625 (lat, lng) for a Wikidata QID, via the same backoff client, or None.
    The geo-gate fallback when a Wikipedia article carries no ``coordinates`` of its
    own but does carry a ``wikibase_item``."""
    if not qid:
        return None
    try:
        from venue_resolver import _request_with_backoff, _USER_AGENT
        r = _request_with_backoff(
            WIKIDATA_API,
            params={"action": "wbgetentities", "ids": qid, "props": "claims",
                    "format": "json"},
            headers={"User-Agent": _USER_AGENT}, timeout=12,
            host_for_cold="https://www.wikidata.org", label="LOCAL-878 P625")
        if r is None or getattr(r, "status_code", 0) != 200:
            return None
        ent = (r.json().get("entities") or {}).get(qid) or {}
        for claim in (ent.get("claims") or {}).get("P625", []) or []:
            val = (((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {})
            lat, lng = val.get("latitude"), val.get("longitude")
            if lat is not None and lng is not None:
                return (float(lat), float(lng))
    except Exception:
        return None
    return None


# LOCAL-878: city aliases so a coordinate-less article naming the city by ANY common
# form qualifies ("Saigon Central Post Office" names Ho Chi Minh City via "Saigon").
_CITY_ALIASES = (
    ({"ho chi minh city", "ho chi minh", "hcmc", "saigon", "sai gon"},
     {"saigon", "ho chi minh"}),
    ({"hanoi", "ha noi"}, {"hanoi", "ha noi"}),
)


def _city_tokens(city: str) -> set:
    """Folded forms that NAMING the tour's city can take (the city itself plus any
    known alias), for the coordinate-less article test."""
    c = _fold2(city or "").strip()
    forms = {c} if c else set()
    for keys, aliases in _CITY_ALIASES:
        if c in keys or any(k in c for k in keys):
            forms |= {_fold2(a) for a in aliases}
    return {f for f in forms if len(f) >= 3}


def _city_named(city: str, title: str, lead: str) -> bool:
    """A coordinate-less article is accepted only when its title or lead also names the
    tour's city / locality or a known alias (so "Saigon Central Post Office" names Ho Chi
    Minh City via "Saigon", but a plain "Opera House" with no pin and no city word does
    not stand in for the Saigon stop)."""
    forms = _city_tokens(city)
    if not forms:
        return False
    hay = _fold2((title or "") + " . " + (lead or "")[:800])
    return any(f in hay for f in forms)


def _geo_ok(pin: Optional[Tuple[float, float]], city: str, page: dict,
            allow_p625: bool = True) -> bool:
    """LOCAL-878: is this article's own location consistent with the stop?

    - With a pin: the article's coordinate (prop=coordinates, else a P625 fallback via
      its wikibase_item) must be within ``GEO_GATE_KM`` of the pin. An article with NO
      coordinate at all is accepted only when its title/lead names the city.
    - With no pin but a city: a coordinate-less article must name the city; a located
      article is accepted (the pin is what refutes a far place, and we have none).
    - With neither pin nor city: no geo signal to test, accept (old behaviour).
    """
    coord = page.get("coord")
    if coord is None and allow_p625 and pin is not None:
        coord = _p625_for_qid(page.get("qid", ""))
        if coord is not None:
            page["coord"] = coord       # memoise so the caller can log it
    if pin is not None:
        if coord is not None:
            return _haversine_km(pin, coord) <= GEO_GATE_KM
        # no coordinate anywhere: fall back to a city-name requirement
        return bool(city) and _city_named(city, page.get("title", ""), page.get("lead", ""))
    if city:
        if coord is not None:
            return True
        return _city_named(city, page.get("title", ""), page.get("lead", ""))
    return True


def _pick(name: str, raw: Optional[Dict], pin: Optional[Tuple[float, float]] = None,
          city: str = "", match_name: str = "") -> Optional[Dict[str, str]]:
    """The first name-matching page that also PASSES the geo-gate (LOCAL-878).
    A page that name-matches but sits at the wrong place (Sydney Opera House for a
    Saigon pin) is skipped, not returned. ``match_name`` is the name used for the
    name-match test (the ORIGINAL stop name on a city-qualified "<name> <city>" retry,
    whose search string would not itself name-match the plain title); defaults to
    ``name``.

    [LOCAL-881 §4] DENSE-CENTRE venue match. The 2 km LOCAL-878 geo-gate alone let
    the Gia Long Palace article (≈600 m away) stand in for a "City Hall" stop. An
    article whose TITLE does not share a distinctive name token with the stop name
    must also sit within ``DENSE_CENTRE_KM`` (300 m) of the pin; otherwise it is a
    different nearby venue and is rejected. A title that DOES share a distinctive
    name token keeps the wider 2 km gate (a complex pinned to its centroid)."""
    mn = match_name or name
    for p in (raw or {}).get("pages") or []:
        _title = p.get("title", "")
        _title_name_match = _name_ok(mn, _title)
        name_match = ((raw or {}).get("trusted") or _title_name_match
                      or _lead_names(mn, p.get("lead", "")))
        if not name_match:
            continue
        if not _geo_ok(pin, city, p):
            continue
        # [LOCAL-881 §4] dense-centre rule. When the article TITLE does not itself
        # name-match the stop (it was admitted via a trusted langlink, a lead
        # alias, or the city-name path), the 2 km LOCAL-878 gate is too wide in a
        # packed centre — the Gia Long Palace (~600 m) passed it for a City Hall
        # stop. Such a title must ALSO sit within 300 m AND share a distinctive
        # name token with the stop; otherwise it is a different nearby venue and is
        # rejected (the caller then retries with a city-qualified name).
        _art_coord = p.get("coord") or _p625_for_qid(p.get("qid", ""))
        if pin is not None and not _title_name_match:
            coord = _art_coord
            within_300 = coord is not None and _haversine_km(pin, coord) <= DENSE_CENTRE_KM
            shares_token = _titles_share_distinctive_token(mn, _title, city)
            if not (within_300 and shares_token):
                continue
        # [LOCAL-882] carry the article's own coordinate into the cached payload so
        # a later cache HIT can re-run the EXACT dense-centre distance check on
        # re-validation (the payload otherwise keeps only title/lead/infobox).
        # Consumers read only title/lead/infobox, so this extra key is inert there.
        _out = {"title": _title, "lead": (p.get("lead") or "")[:_MAX_LEAD],
                "infobox": parse_infobox(p.get("wikitext", ""))}
        if _art_coord is not None:
            _out["coord"] = [round(_art_coord[0], 6), round(_art_coord[1], 6)]
        return _out
    return None


def _revalidate_payload(art: Optional[Dict[str, str]], name: str,
                        pin: Optional[Tuple[float, float]] = None, city: str = "",
                        match_name: str = "") -> bool:
    """[LOCAL-882] Re-apply the CURRENT name + dense-centre acceptance rules to a
    CACHED article payload (``{title, lead, infobox}``), returning True when the
    present rules would still accept it, False when they would now reject it.

    A cached payload has already been through ``_pick`` under the rules in force
    when it was stored. Since LOCAL-882 the payload also carries the article's own
    ``coord`` (when it had one), so this re-runs the FULL name + dense-centre check:

      * The stored title (or its lead alias) must still NAME-MATCH the stop under
        the current ``name_matches`` rule.
      * In a dense centre, LOCAL-881 requires a title that does not itself
        name-match to ALSO sit within 300 m of the pin AND share a distinctive
        token. With the stored ``coord`` the 300 m test is exact; without it (a
        pre-LOCAL-882 payload or a coordinate-less article) a shared distinctive
        token is required. The Gia Long Palace shares no distinctive token with
        "City Hall" / "Ho Chi Minh City Hall", so the stale row is rejected and
        the article re-fetched under the current gate.

    A found=False (negative) row carries no payload and is re-validated trivially
    (there is nothing to re-pick); its freshness is handled by expiry + version.
    """
    if not art:
        return True
    mn = (match_name or name or "").strip()
    title = (art.get("title") or "").strip()
    if not title:
        return False
    title_name_match = _name_ok(mn, title)
    name_match = title_name_match or _lead_names(mn, art.get("lead", ""))
    if not name_match:
        return False
    # Dense-centre: a title that does not itself name-match the stop must share a
    # distinctive token AND sit within 300 m. The stored ``coord`` (LOCAL-882)
    # lets us re-run the EXACT distance check; when it is absent (a pre-LOCAL-882
    # payload or a coordinate-less article) we fall back to requiring a shared
    # distinctive token, so a different nearby venue the title does not name is
    # still rejected.
    if pin is not None and not title_name_match:
        coord = art.get("coord")
        shares_token = _titles_share_distinctive_token(mn, title, city)
        if coord is not None:
            try:
                within_300 = _haversine_km(pin, (float(coord[0]), float(coord[1]))) <= DENSE_CENTRE_KM
            except (TypeError, ValueError, IndexError):
                within_300 = False
            if not (within_300 and shares_token):
                return False
        elif not shares_token:
            return False
    return True


# ---- cache (venue-cache DB, like landmark_coord_cache) -------------------------
_TABLE_OK = False


def _pin_cell(pin: Optional[Tuple[float, float]]) -> str:
    """A coarse grid cell (~1 km) for the stop pin, so a rejected article is cached as
    rejected for THIS (name, pin-cell) pair and a same-name stop elsewhere is unaffected
    (LOCAL-878). '' when no pin."""
    if not pin:
        return ""
    return f"{round(pin[0], 2):.2f},{round(pin[1], 2):.2f}"


def _key(name: str, lang: str, pin: Optional[Tuple[float, float]] = None) -> str:
    return hashlib.sha1(
        f"{name.strip().lower()}|{lang}|{_pin_cell(pin)}".encode("utf-8")).hexdigest()


def _conn():
    try:
        from venue_resolver import _get_db_connection
        return _get_db_connection()
    except Exception:
        return None


def _ensure(conn) -> bool:
    global _TABLE_OK
    if _TABLE_OK:
        return True
    try:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS landmark_wiki_cache (
                cache_key TEXT PRIMARY KEY, name TEXT NOT NULL, language VARCHAR(10),
                payload TEXT, found BOOLEAN NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL)""")
            # [LOCAL-882] rules_version: the acceptance-rule revision that stored
            # this row. Added idempotently so an existing cache table (and its
            # rows) is upgraded in place — no DROP, no DELETE. A pre-LOCAL-882 row
            # has NULL here, which never equals the current RULES_VERSION, so it is
            # treated as stale on read and re-fetched (overwritten via ON CONFLICT).
            cur.execute("ALTER TABLE landmark_wiki_cache "
                        "ADD COLUMN IF NOT EXISTS rules_version TEXT")
        try:
            conn.commit()
        except Exception:
            pass
        _TABLE_OK = True
    except Exception:
        return False
    return True


def _cache_get(name: str, lang: str, pin: Optional[Tuple[float, float]] = None,
               city: str = "", match_name: str = ""):
    """(found, article|None) for a live row that PASSES re-validation, else None.

    [LOCAL-882] A hit is honoured only when BOTH hold:
      * its ``rules_version`` equals the current ``RULES_VERSION`` (a row from an
        older rule set is ignored — treated as a miss — and re-fetched, never
        DELETEd); and
      * the stored payload still passes the CURRENT name + dense-centre rules for
        this stop (``_revalidate_payload``) — so even a current-version row whose
        article the present rules would no longer pick is re-fetched.
    Returning None here makes ``fetch_article`` re-fetch and overwrite the row via
    ON CONFLICT, so the cache self-heals without any deletion.
    """
    conn = _conn()
    if not conn:
        return None
    try:
        if not _ensure(conn):
            return None
        with conn.cursor() as cur:
            cur.execute("SELECT payload, found, rules_version FROM landmark_wiki_cache "
                        "WHERE cache_key = %s AND expires_at > NOW()", (_key(name, lang, pin),))
            row = cur.fetchone()
        if not row:
            return None
        payload, found, row_ver = row[0], row[1], (row[2] if len(row) > 2 else None)
        if row_ver != RULES_VERSION:
            # [LOCAL-882] A row stored under an older acceptance-rule revision is
            # treated as a miss and re-fetched (never DELETEd). Logged so the
            # cloud proof can SEE the re-validation happen on a warm cache.
            print(f"[LOCAL-882] cache revalidate {name!r} @{_pin_cell(pin)}: "
                  f"STALE rules_version ({row_ver} != {RULES_VERSION}) -> re-fetch",
                  flush=True)
            return None                       # stale rule set: re-fetch (no DELETE)
        if not found:
            print(f"[LOCAL-882] cache revalidate {name!r} @{_pin_cell(pin)}: "
                  f"negative row honoured (no article at this pin)", flush=True)
            return (False, None)              # negative row: version + expiry suffice
        art = json.loads(payload)
        if not _revalidate_payload(art, name, pin=pin, city=city, match_name=match_name):
            print(f"[LOCAL-882] cache revalidate {name!r} @{_pin_cell(pin)}: "
                  f"REJECT cached {(art.get('title') or '')!r} (current rules would "
                  f"not pick it) -> re-fetch", flush=True)
            return None                       # current rules would reject it: re-fetch
        print(f"[LOCAL-882] cache revalidate {name!r} @{_pin_cell(pin)}: "
              f"HIT {(art.get('title') or '')!r} passes current rules", flush=True)
        return (True, art)
    except Exception:
        return None


def _cache_put(name: str, lang: str, art: Optional[Dict[str, str]],
               pin: Optional[Tuple[float, float]] = None) -> None:
    conn = _conn()
    if not conn:
        return
    from datetime import datetime, timedelta
    ttl = CACHE_TTL_DAYS if art else CACHE_NEG_TTL_DAYS
    try:
        if not _ensure(conn):
            return
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO landmark_wiki_cache
                (cache_key, name, language, payload, found, expires_at, rules_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (cache_key) DO UPDATE SET payload = EXCLUDED.payload,
                found = EXCLUDED.found, created_at = CURRENT_TIMESTAMP,
                expires_at = EXCLUDED.expires_at,
                rules_version = EXCLUDED.rules_version""",
                        (_key(name, lang, pin), name, lang, json.dumps(art) if art else None,
                         bool(art), datetime.utcnow() + timedelta(days=ttl), RULES_VERSION))
        try:
            conn.commit()
        except Exception:
            pass
    except Exception:
        pass


def fetch_article(name: str, lang: str = "en", fetch_fn: Optional[Callable] = None,
                  use_cache: bool = True, pin: Optional[Tuple[float, float]] = None,
                  city: str = "", match_name: str = "") -> Optional[Dict[str, str]]:
    """The name-matched, GEO-GATED Wikipedia article for a stop, or None (LOCAL-878).
    ``pin`` is the stop's (lat, lng); an article whose own coordinate is >GEO_GATE_KM
    from it is rejected (never cached as the venue's article). ``city`` lets a
    coordinate-less article qualify by naming the city. ``match_name`` is the original
    stop name on a city-qualified "<name> <city>" retry (the search string ``name`` may
    not itself name-match the plain article title). Cached (hit and miss, keyed by the
    SEARCH name + lang + pin-cell) when the live fetcher is used."""
    nm = (name or "").strip()
    if not nm:
        return None
    live = fetch_fn is None
    if use_cache and live:
        c = _cache_get(nm, lang, pin, city=city, match_name=match_name)
        if c is not None:
            return c[1]
    try:
        raw = (fetch_fn or _default_fetch)(nm, lang)
    except Exception:
        raw = None
    art = _pick(nm, raw, pin=pin, city=city, match_name=match_name)
    # only cache a real answer: a transport failure (raw None) must be retried. A
    # name-matching-but-rejected article is cached as a MISS for this (search-name,
    # pin-cell), so a repeat run does not re-fetch Sydney for the Saigon pin.
    if use_cache and live and raw is not None:
        _cache_put(nm, lang, art, pin)
    return art


_COUNTRY_WORDS = frozenset({
    "vietnam", "viet nam", "việt nam", "usa", "us", "u.s.", "u.s.a.", "united states",
    "united states of america", "france", "spain", "italy", "germany", "portugal",
    "netherlands", "japan", "china", "thailand", "australia", "uk", "united kingdom",
    "england", "canada", "russia", "greece", "poland", "sweden", "korea", "austria",
    "belgium", "switzerland",
})


def _city_of(location: str) -> str:
    """Best-effort city / locality string from a tour ``location`` for the geo-gate's
    city-name test and the city-qualified retry.

    A tour location is "City, Country" ("Ho Chi Minh City, Vietnam") or
    "Neighbourhood, City" ("District 1, Ho Chi Minh City"); the CITY/locality is the
    first comma-part that is not a bare country. (``venue_resolver.city_hint_from_location``
    is for "Venue, City, Country" request strings and skips the first part, so it is only
    a fallback here.)"""
    loc = (location or "").strip()
    if not loc:
        return ""
    parts = [p.strip() for p in loc.split(",") if p.strip()]
    for seg in parts:
        if seg.lower() not in _COUNTRY_WORDS and len(seg) > 1:
            return seg
    try:
        from venue_resolver import city_hint_from_location
        c = city_hint_from_location(loc)
        if c:
            return c
    except Exception:
        pass
    return parts[0] if parts else ""


def evidence_for(name: str, location: str = "", langs: Optional[Sequence[str]] = None,
                 fetch_fn: Optional[Callable] = None, use_cache: bool = True,
                 extra_names: Sequence[str] = (),
                 pin: Optional[Tuple[float, float]] = None, city: str = "") -> List[str]:
    """Evidence strings for the claim gate: per language, '<title>. <lead> Infobox: ...'.
    ``extra_names`` are alternative names to try when the stop's own title finds none
    (the user's wording, the Places name).

    LOCAL-878: ``pin`` (the stop's lat,lng) and ``city`` geo-gate every candidate — the
    bare-name search can no longer feed a far place (Sydney Opera House) to the stop. When
    the bare name is rejected, retry ONCE with "<name> <city>" so "Opera House" + HCMC
    reaches the Saigon Opera House / Nhà hát Thành phố listing."""
    city = city or _city_of(location)
    out: List[str] = []
    bases = [n for n in ([name] + [x for x in extra_names if x and x != name]) if n]
    for lang in (langs or local_languages(location)):
        art = None
        # (search_query, match_name): the plain names first, then each name qualified
        # with the city (match still against the ORIGINAL name — "Opera House" — so the
        # retry's article "Saigon Opera House" is accepted even though the search string
        # "Opera House Ho Chi Minh City" would not itself name-match that title).
        tried: List[Tuple[str, str]] = [(b, b) for b in bases]
        if city:
            seen = {q for q, _ in tried}
            for base in bases:
                q = f"{base} {city}"
                if _fold2(city) not in _fold2(base) and q not in seen:
                    tried.append((q, base))
                    seen.add(q)
        for query, base in tried:
            art = fetch_article(query, lang, fetch_fn=fetch_fn, use_cache=use_cache,
                                pin=pin, city=city, match_name=base)
            if art:
                break
        if art:
            txt = f"{art['title']} - Wikipedia ({lang}). {art['lead']}"
            if art.get("infobox"):
                txt += f"\nInfobox: {art['infobox']}"
            out.append(txt)
    return out


# ---- LOCAL-872C: the evidence feeds the NARRATOR, and is the authority ---------
# Wave 35 (gen 00037-k2h): the Opera House said only "French architects" although its
# Wikipedia evidence (Olivier, Guichard, Ferret; opened 1900) was fetched, because the
# evidence fed the GATE only: the narrator wrote from memory and the gate could only
# subtract.  Independence Palace shipped "built in 1885" (evidence: 1962-1966, architect
# Ngo Viet Thu).  These helpers (a) memoise the fetch so narrator and gate share ONE
# lookup, (b) render the evidence as the narrator's primary source, (c) extract the
# AUTHORITY facts (built years, architects) the gate uses to tell a claim that is merely
# unsourced from one that CONTRADICTS the evidence, (d) compose the evidence-based
# short form used instead of an empty stop.
import unicodedata as _ud

_MEMO: Dict[tuple, List[str]] = {}
_HEAD_RE = re.compile(r"^(?P<title>.*?) - Wikipedia \((?P<lang>[A-Za-z\-]+)\)\.\s*(?P<rest>.*)$", re.S)
_BUILT_KEYS = ("built", "construction", "construction start", "construction end", "completed",
               "completion date", "opened", "opening", "opening date", "open", "inaugurated",
               "years built", "year built", "yearbuilt", "year completed", "start date",
               "end date", "khởi công", "hoàn thành", "xây dựng", "khánh thành",
               "ngày khởi công", "ngày hoàn thành", "ngày khánh thành", "năm xây dựng")
_DATE_KEYS = _BUILT_KEYS + ("established", "founded", "dedicated", "consecrated", "thành lập")
_ARCH_KEYS = ("architect", "architects", "designer", "kiến trúc sư", "thiết kế")
_BUILT_CUE_RE = re.compile(
    r"(?i)\b(built|construct\w*|completed|finished|opened|inaugurat\w+|erected|"
    r"groundbreaking|ground was broken|foundation stone|began)\b")
_YEAR_RE2 = re.compile(r"(?<![\d.,])(1[0-9]{3}|20[0-9]{2})(?!\d)")


def _fold2(s: str) -> str:
    s = _ud.normalize("NFKD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if not _ud.combining(c)).lower()


def cached_evidence(name: str, location: str = "", aliases: Sequence[str] = (),
                    pin: Optional[Tuple[float, float]] = None, city: str = "") -> List[str]:
    """``evidence_for`` memoised per process (the DB cache sits underneath), so the
    narrator prompt and the claim gate read ONE lookup. LOCAL-878: ``pin``/``city``
    geo-gate the lookup (and are part of the memo key, so a different pin re-looks-up)."""
    key = (name or "", location or "", tuple(aliases or ()),
           _pin_cell(pin), (city or "").strip().lower())
    if key not in _MEMO:
        try:
            _MEMO[key] = list(evidence_for(name, location, None, None, True,
                                           list(aliases or ()), pin=pin, city=city) or [])
        except Exception:
            _MEMO[key] = []
    return list(_MEMO[key])


def split_item(item: str) -> Dict[str, str]:
    m = _HEAD_RE.match(item or "")
    title, lang, rest = (m.group("title"), m.group("lang"), m.group("rest")) if m else ("", "", item or "")
    lead, _, box = rest.partition("\nInfobox:")
    return {"title": title.strip(), "lang": lang, "lead": lead.strip(), "infobox": box.strip()}


def _infobox_map(box: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in re.split(r";\s+(?=[^;:]{2,40}:\s)", box or ""):
        k, _, v = part.partition(":")
        if k.strip() and v.strip():
            out.setdefault(k.strip().lower(), v.strip())
    return out


def _years_in(text: str) -> set:
    ys: set = set()
    for m in re.finditer(r"(?<![\d.,])(1[0-9]{3}|20[0-9]{2})\s*(?:-|–|—|to|and)\s*(1[0-9]{3}|20[0-9]{2})(?!\d)", text):
        a, b = int(m.group(1)), int(m.group(2))
        if a <= b and b - a <= 60:
            ys.update(str(y) for y in range(a, b + 1))
    ys.update(_YEAR_RE2.findall(text))
    return ys


def _lead_sentences(lead: str) -> List[str]:
    lead = re.sub(r"\s*\([^)]{0,200}\)", "", lead or "")
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ỹ\"“])", lead) if len(s.strip()) > 20]


def authority(items: Sequence[str]) -> Dict:
    """What the Wikipedia evidence itself says about construction and design.
    {'years': set[str], 'built_value': str, 'architects': [str], 'architect_value': str,
     'built_sentence': str, 'architect_sentence': str}.  Empty values when it is silent."""
    years: set = set()
    built_value = arch_value = built_sentence = arch_sentence = ""
    architects: List[str] = []
    date_facts: List[str] = []
    dated: List[tuple] = []
    for it in items or []:
        p = split_item(it)
        box = _infobox_map(p["infobox"])
        for k, v in box.items():
            kk = k.replace("_", " ")
            if kk in _DATE_KEYS:
                years |= _years_in(v)
                date_facts.append(f"{kk}: {v}")
                _ys = _YEAR_RE2.findall(v)
                if _ys:
                    _kind = ("established" if kk in ("established", "thành lập") else
                             "founded" if kk == "founded" else
                             "begun" if kk in ("construction start", "start date", "khởi công", "ngày khởi công") else
                             "opened" if kk in ("opened", "opening", "opening date", "open", "inaugurated", "khánh thành", "ngày khánh thành") else
                             "completed" if kk in ("completed", "completion date", "year completed", "end date", "construction end", "hoàn thành", "ngày hoàn thành") else
                             "built")
                    if (_kind, _ys[0]) not in dated:
                        dated.append((_kind, _ys[0]))
                    if _kind in ("built",) and len(_ys) > 1 and (_kind, _ys[-1]) not in dated:
                        dated.append(("completed", _ys[-1]))
                if kk in _BUILT_KEYS:
                    built_value = built_value or v
            elif kk in _ARCH_KEYS:
                v2 = re.sub(r"\s*\([^)]*\)", "", v)
                arch_value = arch_value or v2
                for nm in re.split(r"\s*(?:,|;|/|&|\band\b|\bvà\b)\s*", v2):
                    nm = nm.strip(" .")
                    if len(nm) >= 4 and nm not in architects:
                        architects.append(nm)
        for s in _lead_sentences(p["lead"]):
            if _BUILT_CUE_RE.search(s) and _years_in(s):
                years |= _years_in(s)
                built_sentence = built_sentence or s
            if re.search(r"(?i)\b(designed by|architects?|plans? (?:by|of))\b", s) and not arch_sentence:
                arch_sentence = s
    rng = None
    for src in (built_value, built_sentence):
        m = re.search(r"(?<![\d.,])(1[0-9]{3}|20[0-9]{2})\s*(?:-|–|—|to|and)\s*(1[0-9]{3}|20[0-9]{2})(?!\d)", src or "")
        if m and 2 <= int(m.group(2)) - int(m.group(1)) <= 60:
            rng = (m.group(1), m.group(2))
            break
    if not built_value and date_facts:
        built_value = date_facts[0].partition(": ")[2]
    return {"dated": dated, "date_facts": date_facts, "range": rng, "years": years, "built_value": built_value, "architects": architects,
            "architect_value": arch_value, "built_sentence": built_sentence,
            "architect_sentence": arch_sentence}


def narrator_block(name: str, items: Sequence[str]) -> str:
    """The stop's Wikipedia lead + infobox as the narrator's PRIMARY source."""
    items = [i for i in (items or []) if i and i.strip()]
    if not items:
        return ""
    en = [i for i in items if "Wikipedia (en)" in i[:200]]
    pick = (en + [i for i in items if i not in en])[:2]
    body = "\n\n".join(i[:3200] for i in pick)
    au = authority(items)
    key = []
    if au["date_facts"]:
        key.append("dates: " + ", ".join(dict.fromkeys(au["date_facts"])))
    elif au["built_value"]:
        key.append(f"built/opened: {au['built_value']}")
    if au["architect_value"]:
        key.append(f"architect(s): {au['architect_value']}")
    keyline = (f"KEY FACTS YOU MUST STATE in the first two paragraphs (exact wording of the years "
               f"and names; say what each date marks, e.g. established / completed / opened): {'; '.join(key)}.\n") if key else ""
    return (
        f"\nPRIMARY SOURCE FOR \"{name}\" (Wikipedia, fetched for this stop; established fact):\n"
        f"{body}\n{keyline}"
        "INSTRUCTIONS FOR THIS SOURCE: State its construction / opening dates, its architect(s) "
        "or designer(s) BY NAME, its style and its capacity, as plain statements, and attribute "
        "them plainly (\"it was designed by ...\", \"according to Wikipedia, ...\"). Use the dates "
        "and names EXACTLY as written there. NEVER put a different year or a different architect "
        "from memory. Add NO built date, architect, performer, production or event that this "
        "source or the other reference material does not give. This block overrides any earlier "
        "note saying no sourced history is available for this stop.\n")


def short_form(name: str, items: Sequence[str]) -> str:
    """2-4 sentences from the lead / infobox, for a stop whose every sentence was
    dropped.  '' when the evidence is empty."""
    items = [i for i in (items or []) if i and i.strip()]
    if not items:
        return ""
    en = [i for i in items if "Wikipedia (en)" in i[:200]]
    p = split_item((en or items)[0])
    sents = _lead_sentences(p["lead"])
    chosen: List[str] = sents[:1]
    for s in sents[1:]:
        if len(chosen) >= 3:
            break
        if _years_in(s) or re.search(r"(?i)\b(designed|architect|style|capacity|seats?|built)\b", s):
            chosen.append(s)
    au = authority(items)
    text = " ".join(chosen)
    extra = []
    if au["architect_value"] and _fold2(au["architect_value"].split(",")[0].split()[-1] if au["architect_value"].split() else "") not in _fold2(text):
        extra.append(f"According to Wikipedia, its architect was {au['architect_value']}.")
    if au["built_value"] and not (au["years"] & _years_in(text)):
        extra.append(f"According to Wikipedia, it was built {au['built_value']}.")
    out = chosen + extra
    out = [s[:400].rstrip() for s in out][:4]
    out = [s if s[-1] in ".!?" else s + "." for s in out if s]
    return " ".join(out)
