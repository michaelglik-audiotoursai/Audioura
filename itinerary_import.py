#!/usr/bin/env python3
"""itinerary_import.py — LOCAL-867 (D762, server side).

Turn a PASTED ITINERARY (e.g. from Musa.AI) into an ordered, reviewable stop list
with a map pin per stop — with NO LLM and at most a fraction of a cent.

    Cathedral → Post Office → Book Street → Independence Palace → ...

Two halves:

1. ``parse_itinerary(text, city_hint) -> [{name, alt_names, note, url}]``
   Pure string logic. Splits on → ⇒ -> => > , ; | newlines and numbered / bulleted
   lines (order kept). Strips "Stop 3:" prefixes, numbering and emoji. Keeps
   "Name + URL" items (the LOCAL-852 forms). "A/B" and "A & B" become ONE stop
   (``name=A``, ``alt_names=[B]``). Numbers are part of a name ("Café Apartments
   42"). Parenthetical text becomes ``note``.

2. ``preview_stops(text, city) -> {...}``
   Resolves every parsed stop to a pin, cheapest authority first:
       Maps link in the item  (free, LOCAL-852/859 parser)
       -> curated city alias table + landmark table  (offline)
       -> Wikidata P625                              (free)
       -> Nominatim INSIDE the city box              (free)
       -> at most ONE Serper /places per item still unresolved   ($0.002)
   An item nothing resolves comes back ``unresolved`` — NEVER the city centroid
   and NEVER the country centroid. The city comes from ``city`` or, failing that,
   from the text; if neither names a city the call is refused (no guessing).

Every network edge is injected (``Resolvers``) so the whole module is unit-tested
offline. No LLM is ever called; ``cost`` in the result says so and counts the
paid calls.

``stops_for_generation`` / ``stop_to_generation_string`` turn the REVIEWED preview
back into the existing user-stops input: a pin the listener kept is carried as a
Google-Maps ``@lat,lng`` link, which the LOCAL-852/859 parser already treats as a
user pin — so every 855E / 859B / 862 / D760 rule applies unchanged.
"""
from __future__ import annotations

import html
import math
import re
import threading
import time
import unicodedata
from urllib.parse import quote
from typing import Callable, Dict, List, Optional, Tuple

__all__ = [
    "parse_itinerary",
    "preview_stops",
    "Resolvers",
    "stop_to_generation_string",
    "stops_for_generation",
    "CITY_ALIASES",
]

# ═════════════════════════════════════════════════════════════════════════════
# 1. PARSER
# ═════════════════════════════════════════════════════════════════════════════

_PH_OPEN, _PH_CLOSE = "\uE000", "\uE001"
_PH_RE = re.compile(_PH_OPEN + r"(\d+)" + _PH_CLOSE)

# A URL: real, or the "https___host_path" underscore-mangled form (LOCAL-852).
_URL_RE = re.compile(r"(?:https?://|https?___|www\.)[^\s\uE000\uE001]+", re.I)
_URL_CUT_RE = re.compile(r"(?:->|=>|→|⇒|➜|➡)")
# A bare "lat,lng" pair must survive the comma split.
_LATLNG_RE = re.compile(
    r"(?<![\w.])-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}(?![\w.])")
_PAREN_RE = re.compile(r"\([^()]*\)|\[[^\[\]]*\]|（[^（）]*）")

# Item delimiters, outside parentheses and URLs.
_SPLIT_RE = re.compile(
    r"\s*(?:-+>|=+>|→|⇒|➜|➡|➔|⟶|⟹|»|>|;|\||,|\u2028|\u2029|\r\n|\n|\r)\s*")
# Numbering that sits INLINE on one line ("1) A 2) B").
_INLINE_NUM_RE = re.compile(r"(?:(?<=\s)|^)\d{1,2}[.)]\s+(?=[^\W\d_])")

_BULLET_RE = re.compile(
    r"^\s*(?:[-*•·▪▫●○◦‣►▶■□✔✓☑✅➤–—]+\s+|\d{1,2}\s*[.)\]:]\s*|\(\d{1,2}\)\s*|"
    r"\d\uFE0F?\u20E3\s*|[\u2460-\u2473]\s*|#\s*\d{1,2}\s*[.):\-]?\s*)")
_STOP_PREFIX_RE = re.compile(
    r"^\s*(?:stop|step|point|poi|waypoint|leg|day|dừng|điểm)\s*#?\s*\d{1,2}\s*"
    r"[:.)\-–—]*\s*", re.I)
_HEADER_RE = re.compile(
    r"^\s*(?:itinerary|route|stops?|tour|plan|walking\s+route|walking\s+tour|"
    r"my\s+route|day\s*\d+)\s*:\s*", re.I)

_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2300-\u23FF"
    "\uFE00-\uFE0F\u200D\u20E3\U000E0020-\U000E007F]")
_ZERO_WIDTH_RE = re.compile("[\u200B\u200C\u2060\uFEFF]")

_COMBINE_RE = re.compile(r"\s*/\s*|\s+&\s+")
_EDGE_PUNCT = " \t\u00a0-–—:·•.*_`~\"'“”‘’«»|+=#"


def strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text or "")


def _unmangle(url: str) -> str:
    u = url
    if u.lower().startswith(("https___", "http___")):
        u = re.sub(r"^(https?)___", r"\1://", u, flags=re.I)
        host, _, rest = u.partition("://")[2].partition("_")
        u = u.partition("://")[0] + "://" + host + ("/" + rest.replace("_", "/")
                                                    if rest else "")
    elif u.lower().startswith("www."):
        u = "https://" + u
    return u


def _trim_url(u: str) -> str:
    m = _URL_CUT_RE.search(u)
    if m:
        u = u[:m.start()]
    u = u.lstrip("<")
    while u and u[-1] in ".,;:!?'\"}>]":
        u = u[:-1]
    if u.endswith(")") and "(" not in u:
        u = u[:-1]
    return u


def _has_letter(s: str) -> bool:
    return any(ch.isalpha() for ch in s)


def _restore(s: str, store: List[str]) -> str:
    for _ in range(8):  # nested placeholders
        new = _PH_RE.sub(lambda m: store[int(m.group(1))], s)
        if new == s:
            break
        s = new
    return s


def _clean_name(s: str) -> str:
    s = strip_emoji(s)
    s = _ZERO_WIDTH_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip(_EDGE_PUNCT)
    return s.strip()


def _strip_prefixes(s: str) -> str:
    for _ in range(4):
        before = s
        s = _BULLET_RE.sub("", s, count=1)
        s = _STOP_PREFIX_RE.sub("", s, count=1)
        s = _HEADER_RE.sub("", s, count=1)
        if s == before:
            break
    return s


def parse_itinerary(text: str, city_hint: str = "") -> List[Dict]:
    """Parse a pasted itinerary into ``[{name, alt_names, note, url}, ...]`` in
    the order given. Never raises; garbage in gives ``[]``.

    ``city_hint`` is used only to drop an item that is nothing but the city's own
    name (a heading such as "Ho Chi Minh City")."""
    if not isinstance(text, str) or not text.strip():
        return []
    s = html.unescape(unicodedata.normalize("NFC", text))
    s = s.replace("\u00a0", " ")
    store: List[str] = []

    def _protect(val: str) -> str:
        store.append(val)
        return f"{_PH_OPEN}{len(store) - 1}{_PH_CLOSE}"

    # 1. protect URLs, bare lat,lng pairs, and parenthetical groups.
    def _protect_url(m):
        full = m.group(0)
        core = _trim_url(full)
        return _protect(core) + full[len(core):]

    s = _URL_RE.sub(_protect_url, s)
    s = _LATLNG_RE.sub(lambda m: _protect(m.group(0)), s)
    for _ in range(4):
        new = _PAREN_RE.sub(lambda m: _protect(m.group(0)), s)
        if new == s:
            break
        s = new

    # 2. inline "1) A 2) B" numbering -> newlines (only with >= 2 markers).
    if len(_INLINE_NUM_RE.findall(s)) >= 2:
        s = _INLINE_NUM_RE.sub("\n", s)

    # 3. split into raw items.
    raw_items = [p for p in _SPLIT_RE.split(s) if p and p.strip()]

    city_fold = _fold(city_hint) if city_hint else ""
    out: List[Dict] = []
    for raw in raw_items:
        item = _strip_prefixes(raw)
        item = _restore(item, store)

        # URL (first one wins) — also when it sat inside a parenthesis.
        url = None
        mu = _URL_RE.search(item)
        if mu:
            url = _unmangle(_trim_url(mu.group(0)))
            item = item[:mu.start()] + " " + item[mu.end():]

        # parenthetical text -> note
        notes: List[str] = []

        def _take_note(m):
            inner = m.group(0)[1:-1].strip()
            if inner:
                notes.append(inner)
            return " "

        for _ in range(3):
            new = _PAREN_RE.sub(_take_note, item)
            if new == item:
                break
            item = new
        item = item.replace("(", " ").replace(")", " ")

        item = _strip_prefixes(strip_emoji(item))

        # combined stops: "A/B", "A & B" -> one stop, alt_names=[B...]
        parts = [p for p in _COMBINE_RE.split(item) if p and p.strip()]
        if len(parts) > 1 and not all(_has_letter(p) for p in parts):
            parts = [item]  # "24/7", "1/2": not a combined stop
        parts = [_clean_name(p) for p in parts]
        parts = [p for p in parts if p and any(c.isalnum() for c in p)]
        if not parts:
            continue
        name, alts = parts[0], []
        for p in parts[1:]:
            if p != name and p not in alts:
                alts.append(p)

        # a heading ("Itinerary:") or the city's own name is not a stop
        if raw.rstrip().endswith(":") and not url:
            continue
        if city_fold and _fold(name) == city_fold and not alts:
            continue

        note = "; ".join(_clean_name(n) if not _URL_RE.search(n) else n
                         for n in notes if n).strip("; ")
        out.append({"name": name, "alt_names": alts, "note": note, "url": url})
    return out


# ═════════════════════════════════════════════════════════════════════════════
# 2. RESOLUTION
# ═════════════════════════════════════════════════════════════════════════════

def _fold(text: str) -> str:
    """Accent/case fold with Vietnamese đ handled (NFKD does not decompose it)."""
    raw = str(text or "").lower().replace("đ", "d")
    nfkd = unicodedata.normalize("NFKD", raw)
    s = "".join(c for c in nfkd if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


_GENERIC = {
    "the", "of", "and", "a", "an", "de", "la", "le", "saigon", "sai", "gon",
    "ho", "chi", "minh", "city", "hcmc", "vietnam", "district", "quan", "q1",
}
# Words that name a KIND of place. They never identify one: "Book Street" must not
# match "Phuong Nam Book City" just because both say "book".
_CLASS_WORDS = {
    "street", "st", "road", "rd", "avenue", "boulevard", "walking", "alley",
    "pier", "wharf", "port", "bar", "pub", "club", "book", "books", "bookstore",
    "cafe", "coffee", "restaurant", "market", "museum", "hall", "house", "palace",
    "temple", "pagoda", "church", "cathedral", "basilica", "park", "square",
    "hotel", "bridge", "tower", "center", "centre", "theatre", "theater", "garden",
    "old", "new", "ben", "tau", "duong", "pho", "cong", "vien", "quan", "nha",
}
_STREETISH = {"street", "road", "avenue", "boulevard", "walking", "alley", "lane",
              "duong", "pho", "hem"}


def _stem(t: str) -> str:
    return t[:-1] if len(t) > 4 and t.endswith("s") else t


def _tokens(name: str) -> set:
    return {_stem(t) for t in _fold(name).split()
            if len(t) >= 2 and t not in _GENERIC}


def name_ok(query: str, cand: str) -> bool:
    """A geocoder/Places hit NAME plausibly names the stop we asked for: they share
    the DISTINCTIVE part of the name (class words such as street / pier / bar /
    book do not count). A name made only of class words ("Opera House") must be
    contained in, or contain, the candidate."""
    qt, ct = _tokens(query), _tokens(cand)
    qc, cc = qt - _CLASS_WORDS, ct - _CLASS_WORDS
    if qc and cc:
        return qc <= cc or cc <= qc
    fq, fc = _fold(query), _fold(cand)
    if qt and ct and (qt <= ct or ct <= qt):
        return True
    return bool(fq and fc and (fq in fc or fc in fq))


def _is_streetish(names) -> bool:
    return any(t in _STREETISH for n in names for t in _fold(n).split())


def _km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


# Curated per-city aliases: the bare word a visitor types ("Cathedral",
# "Book Street") -> the place it means in THAT city. Only the NAMES to search are
# stored — never a coordinate; the pin always comes from an authority below.
#   title : the name the tour should use for the stop
#   lm    : name for the offline landmark table (landmark_reference)
#   wd    : name for the Wikidata P625 search
#   nom   : name for the Nominatim box search
#   serper: name for the single Serper /places call
CITY_ALIASES: Dict[str, Dict[str, Dict[str, str]]] = {
    "Ho Chi Minh City": {
        "cathedral": {
            "title": "Notre-Dame Cathedral Basilica of Saigon",
            "lm": "Saigon Notre-Dame Basilica",
            "wd": "Notre-Dame Cathedral Basilica of Saigon",
            "nom": "Nhà thờ Đức Bà Sài Gòn",
            "serper": "Notre-Dame Cathedral Basilica of Saigon"},
        "notre dame cathedral": {"title": "Notre-Dame Cathedral Basilica of Saigon",
                                 "lm": "Saigon Notre-Dame Basilica"},
        "post office": {
            "title": "Saigon Central Post Office",
            "lm": "Saigon Central Post Office",
            "wd": "Saigon Central Post Office",
            "nom": "Bưu điện Trung tâm Sài Gòn",
            "serper": "Saigon Central Post Office"},
        "book street": {
            "title": "Nguyễn Văn Bình Book Street",
            "nom": "Đường sách Nguyễn Văn Bình",
            "serper": "Nguyen Van Binh Book Street"},
        "independence palace": {
            "title": "Independence Palace",
            "wd": "Independence Palace",
            "nom": "Dinh Độc Lập",
            "serper": "Independence Palace Ho Chi Minh City"},
        "war remnants museum": {
            "title": "War Remnants Museum",
            "wd": "War Remnants Museum",
            "nom": "Bảo tàng Chứng tích Chiến tranh",
            "serper": "War Remnants Museum"},
        "opera house": {
            "title": "Saigon Opera House",
            "lm": "Saigon Opera House",
            "wd": "Saigon Opera House",
            "nom": "Nhà hát Thành phố Hồ Chí Minh",
            "serper": "Saigon Opera House"},
        "city hall": {
            "title": "Ho Chi Minh City Hall (People's Committee Building)",
            "lm": "Ho Chi Minh City Hall",
            "wd": "Ho Chi Minh City People's Committee Building",
            "nom": "Trụ sở Ủy ban Nhân dân Thành phố Hồ Chí Minh",
            "serper": "Ho Chi Minh City Hall"},
        "nguyen hue": {
            "title": "Nguyễn Huệ Walking Street",
            "nom": "Phố đi bộ Nguyễn Huệ",
            "serper": "Nguyen Hue Walking Street"},
        "cafe apartments 42": {
            "title": "Café Apartments, 42 Nguyễn Huệ",
            "nom": "42 Nguyễn Huệ, Bến Nghé, Quận 1",
            "serper": "The Cafe Apartments 42 Nguyen Hue"},
        "bach dang pier": {
            "title": "Bạch Đằng Pier",
            "nom": "Bến tàu Bạch Đằng",
            "serper": "Bach Dang Pier Ho Chi Minh City"},
        "thi bar": {"title": "Thi Bar Saigon", "serper": "Thi Bar Saigon"},
    },
}


class Resolvers:
    """Network edges, injectable. Every method fails SOFT (returns empty/None)."""

    def __init__(self, wikidata=None, nominatim=None, serper=None, link=None,
                 city_fetch=None, canonical=None):
        self.wikidata = wikidata or _default_wikidata
        self.nominatim = nominatim or _default_nominatim
        self.serper = serper or _default_serper
        self.link = link or _default_link
        self.city_fetch = city_fetch or _default_nominatim
        # [LOCAL-882 task C] canonical(user_name, pin, city, local_lang) -> dict|None
        # The RUNTIME canonical-venue-at-the-pin resolver. Injectable (offline
        # tests pass a stub); the live default is venue_canonical_resolver.
        self.canonical = canonical if canonical is not None else _default_canonical


def _default_canonical(user_name, pin, city="", local_lang=""):
    """Live canonical-venue resolution (Wikidata within 300 m of the pin, then
    Places). Fails soft to None so pin resolution is never blocked by it."""
    try:
        import venue_canonical_resolver as _vcr
        return _vcr.resolve_canonical(user_name, pin, city=city, local_lang=local_lang)
    except Exception:
        return None


_NOM_LOCK = threading.Lock()
_NOM_LAST = [0.0]
_NOM_URL = "https://nominatim.openstreetmap.org/search"
_UA = "Audioura/1.0 (audio tour generator; info@audioura.com)"


def _default_nominatim(params: Dict) -> list:
    """Free Nominatim, <= 1 request/second, identifying User-Agent."""
    try:
        import requests
    except Exception:
        return []
    with _NOM_LOCK:
        wait = 1.1 - (time.time() - _NOM_LAST[0])
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.get(_NOM_URL, params=params, timeout=10,
                             headers={"User-Agent": _UA})
            _NOM_LAST[0] = time.time()
            if r.status_code != 200:
                return []
            return r.json() or []
        except Exception:
            _NOM_LAST[0] = time.time()
            return []


def _default_wikidata(name: str, scope: str, center, bbox):
    """Wikidata P625 for ``name`` inside the city. ``(lat, lng, qid)`` or None."""
    try:
        import wikidata_landmark_lookup as wl
        import requests

        def _fetch(action, params):
            try:
                r = requests.get(wl.WIKIDATA_API, params=params, timeout=12,
                                 headers={"User-Agent": _UA})
                return r.json() if r.status_code == 200 else None
            except Exception:
                return None
        hit = wl.lookup(name, scope=scope, scope_center=center,
                        scope_bbox=list(bbox) if bbox else None,
                        fetch_fn=_fetch, use_cache=False)
        return (hit[0], hit[1], hit[3]) if hit else None
    except Exception:
        return None


def _default_serper(query: str, ll: Optional[str], location: Optional[str]) -> list:
    """ONE metered Serper /places call (places_search is the budget-metered door)."""
    try:
        import places_search as ps
        if not ps.serper_places_enabled():
            return []
        return ps._serper_places_call(query, ll, location=location) or []
    except Exception:
        return []


def _default_link(raw: str) -> Dict:
    try:
        import user_stop_input as usi
        return usi.parse_user_stop(raw)
    except Exception:
        return {"lat": None, "lng": None}


# ── city ────────────────────────────────────────────────────────────────────

def resolve_city(city: str, text: str, res: Resolvers) -> Optional[Dict]:
    """The tour city from ``city``, else from the text. Never a country."""
    import city_scope as cs
    quiet = lambda *_a, **_k: None  # noqa: E731
    if (city or "").strip():
        hit = cs.resolve_city_scope(city, fetch=res.city_fetch, log=quiet)
        if hit:
            return hit
    cur = cs.find_curated_city(text or "")
    return cur


def _canon_city_key(city: Dict) -> str:
    return city.get("name") or ""


# ── one stop ────────────────────────────────────────────────────────────────

class _State:
    def __init__(self, serper_cap: int):
        self.serper_calls = 0
        self.serper_cap = serper_cap
        self.wikidata_calls = 0
        self.nominatim_calls = 0


def _in_city(pt, city) -> bool:
    try:
        lat, lng = float(pt[0]), float(pt[1])
    except (TypeError, ValueError, IndexError):
        return False
    if abs(lat) > 90 or abs(lng) > 180 or (lat == 0 and lng == 0):
        return False
    return _km((lat, lng), (city["lat"], city["lng"])) <= 25.0


def _bbox_params(city: Dict) -> Dict:
    bb = city.get("bbox")
    if not bb or len(bb) < 4:
        return {}
    s, n, w, e = (float(x) for x in bb[:4])
    return {"viewbox": f"{w},{n},{e},{s}", "bounded": "1"}


def _row_names(row: Dict) -> List[str]:
    names = []
    for k in ("name", "title"):
        if row.get(k):
            names.append(str(row[k]))
    dn = str(row.get("display_name") or "")
    if dn:
        names.append(dn.split(",")[0])
    nd = row.get("namedetails")
    if isinstance(nd, dict):
        names.extend(str(v) for v in nd.values() if v)
    return names


def _result(lat, lng, source, confidence, tier, resolved_name=None,
            matched_name=None) -> Dict:
    """``matched_name`` is the AUTHORITY's own name for the place (OSM / Google /
    landmark table local name), carried to generation so the venue research
    looks the stop up under its real name (LOCAL-862 alias)."""
    return {"lat": round(float(lat), 6), "lng": round(float(lng), 6),
            "source": source, "confidence": confidence, "tier": tier,
            "resolved_name": resolved_name,
            "matched_name": (str(matched_name).strip() or None) if matched_name else None}


def _resolve_stop(stop: Dict, city: Dict, res: Resolvers, st: _State,
                  log: Callable[[str], None]) -> Dict:
    names = [stop["name"]] + list(stop.get("alt_names") or [])
    aliases = CITY_ALIASES.get(_canon_city_key(city), {})
    alias = None
    for nm in names:
        alias = aliases.get(_fold(nm))
        if alias:
            break
    title = (alias or {}).get("title") or stop["name"]
    scope = f"{city['name']}, {city.get('country_code') or ''}".strip(", ")
    center = (city["lat"], city["lng"])
    bbox = city.get("bbox")

    # (0) a Maps link / bare lat,lng pasted with the stop — free, authoritative.
    if stop.get("url") or _LATLNG_RE.fullmatch(stop["name"] or ""):
        raw = (stop["name"] + " " + stop["url"]) if stop.get("url") else stop["name"]
        try:
            p = res.link(raw) or {}
        except Exception:
            p = {}
        if p.get("lat") is not None and _in_city((p["lat"], p["lng"]), city):
            return _result(p["lat"], p["lng"], "user_link", "high", "link",
                           p.get("resolved_name") or title,
                           matched_name=p.get("resolved_name"))

    # An alias says what the visitor's generic word MEANS in this city. When one
    # applies, search for THAT and judge hits against THAT — never the bare typed
    # word ("Book Street" must not be matched to any shop with "book" in its name).
    if alias:
        targets = [v for k, v in alias.items() if k != "serper" and v] + \
                  ([alias["serper"]] if alias.get("serper") else [])
    else:
        targets = list(names)

    # (1) offline landmark table, then Wikidata P625.
    lm_names = [alias["lm"]] if alias and alias.get("lm") else ([] if alias else list(names))
    try:
        import landmark_reference as lr
    except Exception:
        lr = None
    if lr:
        for q in lm_names:
            hit = lr.lookup(q)
            if hit and _in_city((hit[0], hit[1]), city):
                return _result(hit[0], hit[1], "landmark_table", "high",
                               "landmark", title,
                               matched_name=hit[4] if len(hit) > 4 else None)
    wd_names = [alias["wd"]] if alias and alias.get("wd") else ([] if alias else list(names))
    seen = set()
    for q in wd_names:
        if q in seen:
            continue
        seen.add(q)
        st.wikidata_calls += 1
        try:
            hit = res.wikidata(q, scope, center, bbox)
        except Exception:
            hit = None
        if hit and _in_city((hit[0], hit[1]), city):
            # A bare generic word with no alias ("Museum") is too ambiguous to
            # trust the first Wikidata hit blindly; require an alias or a
            # multi-token name.
            if alias or len(_tokens(q)) >= 2:
                return _result(hit[0], hit[1], "wikidata_p625", "high",
                               "wikidata", title)

    # (2) Nominatim inside the city box.
    nom_names = [alias["nom"]] if alias and alias.get("nom") else ([] if alias else list(names))
    street_stop = _is_streetish(targets)
    seen = set()
    for q in nom_names:
        if q in seen:
            continue
        seen.add(q)
        params = {"q": q, "format": "jsonv2", "limit": "5",
                  "namedetails": "1", "accept-language": "vi,en"}
        params.update(_bbox_params(city))
        if city.get("country_code"):
            params["countrycodes"] = city["country_code"]
        st.nominatim_calls += 1
        try:
            rows = res.nominatim(params) or []
        except Exception:
            rows = []
        for row in rows:
            # a road is a plausible hit only for a stop that IS a street; a pier,
            # bar or palace must not be pinned on the avenue that carries its
            # old name.
            if not street_stop and str(row.get("category") or row.get("class")) == "highway":
                continue
            try:
                pt = (float(row["lat"]), float(row["lon"]))
            except (KeyError, TypeError, ValueError):
                continue
            if not _in_city(pt, city):
                continue
            if any(name_ok(t, rn) for t in targets for rn in _row_names(row)):
                return _result(pt[0], pt[1], "nominatim", "medium", "nominatim",
                               title if alias else (_row_names(row) or [title])[0],
                               matched_name=(_row_names(row) or [None])[0])

    # (3) at most ONE Serper /places for an item still unresolved.
    if st.serper_calls >= st.serper_cap:
        return {"unresolved": True,
                "reason": "no free authority matched; Serper cap for this call reached"}
    q = (alias or {}).get("serper") or stop["name"]
    ll = f"@{city['lat']},{city['lng']},14z"
    st.serper_calls += 1
    try:
        recs = res.serper(q, ll, city["name"]) or []
    except Exception:
        recs = []
    for rec in recs:
        try:
            pt = (float(rec.get("lat", rec.get("latitude"))),
                  float(rec.get("lon", rec.get("lng", rec.get("longitude")))))
        except (TypeError, ValueError):
            continue
        if not _in_city(pt, city):
            continue
        if any(name_ok(t, rn) for t in targets + [q] for rn in _row_names(rec)):
            return _result(pt[0], pt[1], "serper_places", "medium", "serper",
                           title if alias else (_row_names(rec) or [title])[0],
                           matched_name=(_row_names(rec) or [None])[0])
    return {"unresolved": True,
            "reason": "no in-city match from the landmark table, Wikidata, "
                      "Nominatim or one Serper /places lookup"}


def preview_stops(text: str, city: str = "", *, resolvers: Optional[Resolvers] = None,
                  max_serper_calls: int = 10, max_stops: int = 50,
                  log: Callable[[str], None] = print) -> Dict:
    """Parse + resolve a pasted itinerary. Returns::

        {"ok": True, "city": {...}, "count": N, "unresolved_count": K,
         "stops": [{index, name, alt_names, note, url, stop_name,
                    resolved_name, lat, lng, source, confidence, unresolved,
                    reason?}, ...],
         "cost": {...}}

    or ``{"ok": False, "error": ...}`` (no stops / no city / too many)."""
    res = resolvers or Resolvers()
    stops = parse_itinerary(text, city)
    if not stops:
        return {"ok": False, "error": "no stops found in the pasted text"}
    if len(stops) > max_stops:
        return {"ok": False,
                "error": f"{len(stops)} stops pasted; the maximum is {max_stops}"}
    c = resolve_city(city, text, res)
    if not c:
        return {"ok": False,
                "error": "could not determine the city — pass 'city' (e.g. "
                         "\"Ho Chi Minh City\") or name it in the text"}

    st = _State(max_serper_calls)
    out = []
    for i, s in enumerate(stops):
        try:
            r = _resolve_stop(s, c, res, st, log)
        except Exception as e:  # one bad item must not sink the preview
            r = {"unresolved": True, "reason": f"lookup error: {type(e).__name__}"}
        item = {"index": i, "name": s["name"], "alt_names": s["alt_names"],
                "note": s["note"], "url": s["url"]}
        if r.get("unresolved"):
            item.update(stop_name=s["name"], resolved_name=None, matched_name=None,
                        lat=None,
                        lng=None, source=None, confidence=None, unresolved=True,
                        reason=r["reason"])
        else:
            alias_title = None
            for nm in [s["name"]] + s["alt_names"]:
                a = CITY_ALIASES.get(c["name"], {}).get(_fold(nm))
                if a:
                    alias_title = a["title"]
                    break
            # [LOCAL-882 task C] Derive the CANONICAL venue at the resolved pin at
            # RUNTIME (Wikidata within 300 m of the pin, then Places), so the
            # name carried to generation as the research match_name/alias comes
            # from the pin, not from a hand-written place-name table (D769). The
            # user's own wording stays the spoken title (stop_name); the canonical
            # English + local labels become match_name and aliases for evidence
            # and signature stories. A None result keeps the existing behaviour.
            _canon = None
            _canon_aliases: List[str] = []
            try:
                _local_lang = ""
                try:
                    import wikidata_landmark_lookup as _wll882
                    _local_lang = _wll882.local_lang_for_scope(
                        f"{c.get('name','')}, {c.get('country_code','')}")
                except Exception:
                    _local_lang = ""
                _canon = res.canonical(s["name"], (r["lat"], r["lng"]),
                                       c.get("name", ""), _local_lang)
            except Exception as _ce882:
                log(f"[LOCAL-882] canonical resolve skipped for {s['name']!r}: {_ce882}")
                _canon = None
            if _canon and _canon.get("canonical_en"):
                _matched = _canon["canonical_en"]
                _canon_aliases = list(_canon.get("aliases") or [])
                log(f"[LOCAL-882] canonical for {s['name']!r} @pin -> "
                    f"{_matched!r} ({_canon.get('source')}, "
                    f"{_canon.get('distance_m')} m, tier {_canon.get('match_tier')})")
            else:
                _matched = r.get("matched_name")
            item.update(stop_name=alias_title or s["name"],
                        resolved_name=r.get("resolved_name") or alias_title
                        or s["name"],
                        matched_name=_matched or r.get("matched_name"),
                        canonical_aliases=_canon_aliases,
                        lat=r["lat"], lng=r["lng"], source=r["source"],
                        confidence=r["confidence"], unresolved=False)
        out.append(item)
        log(f"[LOCAL-867] preview {i + 1}/{len(stops)} {s['name']!r} -> "
            f"{item['source'] or 'UNRESOLVED'}")

    rate = 0.002
    try:
        import cost_rates
        rate = float(cost_rates.SERPER_PLACES_COST_PER_QUERY)
    except Exception:
        pass
    return {
        "ok": True,
        "city": {"name": c["name"], "lat": c["lat"], "lng": c["lng"],
                 "source": c.get("source")},
        "count": len(out),
        "unresolved_count": sum(1 for x in out if x["unresolved"]),
        "stops": out,
        "cost": {"llm_calls": 0, "serper_places_calls": st.serper_calls,
                 "wikidata_calls": st.wikidata_calls,
                 "nominatim_calls": st.nominatim_calls,
                 "usd": round(st.serper_calls * rate, 4),
                 "note": "Serper /places at the cost_rates price; Wikidata and "
                         "Nominatim are free."},
    }


# ═════════════════════════════════════════════════════════════════════════════
# 3. PREVIEW -> GENERATION
# ═════════════════════════════════════════════════════════════════════════════

# tour_orchestrator_service.sanitize_input truncates a user string to 200 chars.
MAX_STOP_STRING = 200


def stop_to_generation_string(item) -> str:
    """One reviewed stop -> the existing user-stops string.

    * a plain string is passed through unchanged;
    * ``{name|stop_name, lat, lng}`` -> ``"<name> https://www.google.com/maps/@lat,lng,18z"``
      — the form the LOCAL-852/859 parser reads as a user pin. An item with no
      usable coordinate (unresolved) is just its name, and is geocoded by name
      downstream exactly like any typed stop."""
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        raise ValueError("a stop must be a string or an object with a name")
    name = str(item.get("stop_name") or item.get("name") or "").strip()
    if not name:
        raise ValueError("a stop object needs a name")
    try:
        lat, lng = float(item["lat"]), float(item["lng"])
        if abs(lat) <= 90 and abs(lng) <= 180 and not (lat == 0 and lng == 0):
            # The authority's own name rides in the /place/ segment: the
            # LOCAL-852 parser reads it as resolved_name and LOCAL-862 uses it as
            # the stop's research alias. The display title stays ``name``.
            #
            # The orchestrator's sanitize_input CUTS every stop string at
            # MAX_STOP_STRING chars; a cut that lands in the URL loses the
            # coordinate (live run: City Hall's long title + Vietnamese alias was
            # cut at "@10.77647" and re-pinned by name lookup). So the string must
            # fit: the alias segment is dropped when it does not, and the NAME is
            # shortened as a last resort — never the coordinate.
            pin = f"@{lat:.6f},{lng:.6f},18z"
            mn = str(item.get("matched_name") or "").strip()
            if mn and _fold(mn) != _fold(name):
                seg = quote(re.sub(r"\s+", "+", mn), safe="+")
                full = f"{name} https://www.google.com/maps/place/{seg}/{pin}"
                if len(full) <= MAX_STOP_STRING:
                    return full
            tail = f" https://www.google.com/maps/{pin}"
            room = MAX_STOP_STRING - len(tail)
            if len(name) > room:
                name = name[:room].rstrip()
            return f"{name}{tail}"
    except (KeyError, TypeError, ValueError):
        pass
    return name


def stops_for_generation(items) -> Tuple[List[str], int]:
    """The reviewed preview list -> (user-stops strings in order, pins carried)."""
    strings = [stop_to_generation_string(i) for i in items]
    pins = sum(1 for i in items if isinstance(i, dict)
               and "/@" in stop_to_generation_string(i))
    return strings, pins


_LIST_MARKERS = ("→", "⇒", "➜", "->", "=>", "\n", ";", "|")


def expand_pasted_lists(raw_stops, city_hint: str = "", resolve: bool = False):
    """[LEAD, D762 quick path] The app's own-stop fields are free text. A listener
    who pastes a whole itinerary ("Cathedral → Post Office → …") into ONE field
    should get every place as its own stop, in order, before any app update.

    A string item that carries a list marker (arrows, new lines, ``;``, ``|``)
    and parses into 2+ places is replaced by those places, as names with any
    pasted link kept (``"<name> <url>"``). Commas alone do NOT trigger expansion,
    because a single stop is often "Name, street address". Everything else is
    passed through unchanged. Returns ``(new_list, n_expanded_items)``. Never
    raises; on any error the input is returned as-is."""
    if not isinstance(raw_stops, list):
        return raw_stops, 0
    out, n = [], 0
    try:
        for item in raw_stops:
            if isinstance(item, str) and any(m in item for m in _LIST_MARKERS):
                parsed = parse_itinerary(item, city_hint)
                if len(parsed) >= 2:
                    n += 1
                    # [LEAD wave-29 finding A] Resolve the pins exactly as the
                    # free /preview-stops does (no LLM, ≈$0.004/10 stops), so each
                    # stop carries a reviewed-quality pin as a user pin instead of
                    # falling to a model guess downstream.
                    if resolve and city_hint:
                        try:
                            pv = preview_stops(item, city_hint)
                            if pv.get("ok") and len(pv.get("stops") or []) == len(parsed):
                                strs, _pins = stops_for_generation(pv["stops"])
                                out.extend(x for x in strs if x)
                                continue
                        except Exception:
                            pass
                    for p in parsed:
                        name = (p.get("name") or "").strip()
                        if not name:
                            continue
                        url = (p.get("url") or "").strip()
                        out.append(f"{name} {url}".strip())
                    continue
            out.append(item)
        return out, n
    except Exception:
        return raw_stops, 0


def resolve_user_stop_pins(raw_stops, city_hint: str = "", log=print, preview_fn=None):
    """[LEAD wave-30 finding] Give every plain-name user stop a checked pin, with the
    same free resolvers as /preview-stops (no LLM; Serper /places only for leftovers).
    This covers the pasted list AND the app's already-split stops. Items that already
    carry a link or a pin, and objects, are left alone. Returns ``(new_list,
    n_pinned)``. Logs why when it cannot run. Never raises."""
    if not isinstance(raw_stops, list) or not raw_stops:
        return raw_stops, 0
    if any(isinstance(s, dict) for s in raw_stops):
        return raw_stops, 0  # a reviewed preview (LOCAL-867) already carries its pins
    try:
        idx = [i for i, s in enumerate(raw_stops)
               if isinstance(s, str) and s.strip() and "http" not in s
               and not any(m in s for m in _LIST_MARKERS)]
        if not idx or not (city_hint or "").strip():
            return raw_stops, 0
        names = [raw_stops[i].strip() for i in idx]
        if preview_fn is not None:
            pv = preview_fn("\n".join(names), city_hint) or {}
        else:
            pv = preview_stops("\n".join(names), city_hint, log=lambda *_a: None)
        if not pv.get("ok"):
            log(f"[D762] user-stop pin resolve skipped: {pv.get('error')}")
            return raw_stops, 0
        got = pv.get("stops") or []
        if len(got) != len(names):
            log(f"[D762] user-stop pin resolve skipped: parsed {len(got)} of {len(names)}")
            return raw_stops, 0
        out = list(raw_stops)
        n = 0
        for i, st in zip(idx, got):
            if st.get("unresolved") or st.get("lat") is None:
                continue
            st = dict(st)
            # The listener's own wording, cleaned the way the parser cleans it:
            # "Opera House/Đồng Khởi" -> "Opera House", "(tour-bus + waterbus)" ->
            # a note, never part of the title (wave-32 cosmetic finding).
            _clean = (st.get("name") or "").strip() or raw_stops[i].strip()
            st["name"] = st["stop_name"] = _clean
            s = stop_to_generation_string(st)
            if "/@" in s:
                out[i] = s
                n += 1
        log(f"[D762] user-stop pins resolved {n}/{len(names)} "
            f"(city {pv.get('city', {}).get('name') if isinstance(pv.get('city'), dict) else city_hint})")
        return out, n
    except Exception as e:
        log(f"[D762] user-stop pin resolve error: {e}")
        return raw_stops, 0
