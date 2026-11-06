#!/usr/bin/env python3
"""user_stop_enrichment.py — LOCAL-862.

The listener's own stops must be INTERESTING and TRUE.

Michael, 2026-11-03: "we either get invented fiction, or empty stops without
stories".  Sophia's seven stops are small private venues (bars, a karaoke room, a
spa, a nightlife street).  The story engine works where sourced material exists;
for a small venue the sourced material is what the BUSINESS-tour path already
collects (LOCAL-800 customer_voice, LOCAL-672 verified reviews).  The user-stops
path never called any of it, and LOCAL-855E's D759 made one Serper query per stop
whose output the verifier then discarded sentence by sentence — leaving a
two-line "X is one of the places you chose".

This module routes a user stop of BUSINESS kind through the same enrichment a
business stop gets, then lets the narrator write from that material ONLY:

  1. Serper Places record  — rating, review count, price band, website, address,
     category, hours (when Serper supplies them).  Accepted only when the record's
     name matches the stop AND it sits near the stop's pin (a wrong venue's rating
     is worse than none).
  2. customer_voice        — signature items, most praised, recurring complaint,
     "since <year>" (one review search; LOCAL-800).
  3. the venue's own site  — homepage + /about (<= 2 pages, robots.txt respected):
     founding year, owner story, concept, signature items.  Sentences are kept
     VERBATIM from the page, selected by keyword; nothing is paraphrased here.
  4. one story search      — "<name>" <city> history OR owner OR founded OR story;
     only snippets that name the venue AND corroborate the place are kept.

The result is a numbered FACT LIST with a source on every line.  The narrator
(ONE batched LLM call for the whole tour) is told that list is its ONLY source and
asked for 4-7 sentences.  The existing LOCAL-855D verifier then checks every
sentence against the same list (user_stop_verify, ``material_by_title``), so what
survives is supported by construction and little is dropped.

THIN IS STILL HONEST: with fewer than 2 sourced specifics the stop stays short and
deterministic, but uses the Places data (type, rating, price, hours) so it is
useful rather than empty.  Landmark-kind stops (cathedral, palace, museum, park)
are NOT touched — they keep the existing landmark/story path.

Network access is injected (``fetch_page``, ``serp_fn``, ``places_fn``,
``review_fn``, ``llm_fn``) so every unit test runs offline.
"""
from __future__ import annotations

import html as _html
import json
import math
import os
import re
import socket
import ipaddress
from html.parser import HTMLParser
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from urllib import robotparser

from text_polish import city_from_scope
from user_stop_narration import _fold, _split_sentences

__all__ = [
    "classify_stop_kind", "gather_material", "material_lines",
    "count_specifics", "thin_stop_body", "enrich_user_stops_in_text",
]

_DOCUMENTED_KINDS = {
    "cathedral", "basilica", "church", "temple", "pagoda", "palace",
    "museum", "memorial", "monument", "opera", "landmark", "shrine",
    "mausoleum", "fort", "citadel", "park", "castle", "tower", "bridge",
    "square", "garden", "gardens", "mosque", "synagogue", "library",
    "theatre", "theater", "historic", "historical", "heritage", "ruins",
    "cemetery", "zoo", "pagoda", "observatory", "university",
}
_BUSINESS_KINDS = {
    "bar", "pub", "club", "lounge", "restaurant", "cafe", "café", "coffee",
    "bistro", "diner", "eatery", "grill", "karaoke", "nightclub", "brewery",
    "taproom", "spa", "salon", "massage", "wellness", "studio", "gym", "shop",
    "store", "boutique", "market", "gallery", "bakery", "patisserie",
    "teahouse", "izakaya", "tavern", "speakeasy", "hotel", "hostel", "venue",
    "street", "nightlife", "walking", "cocktail", "music", "live", "food",
}
# [LOCAL-870 item 4] Institutional name words that make a stop a famous
# monument/institution, and the business words that are too weak to override them.
_STRONG_INSTITUTION_WORDS = {
    "opera", "cathedral", "basilica", "palace", "museum", "temple", "pagoda",
    "mausoleum", "citadel", "shrine", "mosque", "synagogue", "castle",
    "memorial", "monument",
}
_WEAK_BUSINESS_KINDS = {"venue", "music", "live", "nightlife", "walking",
                        "food", "street", "studio", "gallery", "market"}
_MIN_SPECIFICS = 2
_MAX_PAGES = 2
_UA = "Mozilla/5.0 (compatible; AudiouraTourBot/1.0; +https://audioura.app)"
_SKIP_SITE_HOSTS = (
    "facebook.com", "instagram.com", "google.", "goo.gl", "tripadvisor.",
    "yelp.", "foursquare.", "tiktok.com", "twitter.com", "x.com", "youtube.com",
    "booking.com", "agoda.com", "wikipedia.org", "linktr.ee",
)
# Kept in sync with user_stop_verify so a stop skipped there is skipped here.


# ─────────────────────────────────────────────────────────────────────────────
# 0. kind
# ─────────────────────────────────────────────────────────────────────────────

def classify_stop_kind(name: str, type_specialty: str = "",
                       category: str = "") -> str:
    """'landmark' for a documented monument/institution/park, else 'business'.

    A landmark word in the TYPE decides (Type/Specialty or Places category).  The
    NAME is consulted only for a clear institutional word ("Notre-Dame Cathedral
    Basilica", "Independence Palace") so a bar called "Palace Bar" with a bar type
    stays a business."""
    type_toks = set(_fold(f"{type_specialty} {category}").split())
    name_toks = set(_fold(name).split())
    # [LOCAL-870 item 4] A FAMOUS landmark takes the landmark/story path even when
    # the generator's Type label is a business-ish word ("Live music venue",
    # "Performing arts venue"): wave 28 sent "Saigon Opera House" to business
    # enrichment (3 generic sentences). Two signals, both requiring that the NAME
    # carries no business word of its own (so "Palace Bar" stays a bar):
    #   (a) the offline Wikidata-P625 landmark table knows it;
    #   (b) the name has a clear institutional word AND the Type holds only WEAK
    #       business words (venue/music/live/...), never a hard one (bar, cafe,
    #       hotel, spa, shop...).
    if not (name_toks & _BUSINESS_KINDS):
        try:
            from landmark_reference import lookup as _lm_lookup870
            if _lm_lookup870(name):
                return "landmark"
        except Exception:
            pass
        if (name_toks & _STRONG_INSTITUTION_WORDS
                and not (type_toks & (_BUSINESS_KINDS - _WEAK_BUSINESS_KINDS))):
            return "landmark"
    if type_toks & _BUSINESS_KINDS and not (type_toks & _DOCUMENTED_KINDS):
        return "business"
    if type_toks & _DOCUMENTED_KINDS:
        # "Park" in "Pool and park bar"? business kind words win above only when no
        # documented word is present; here a documented word is present.
        return "landmark"
    if name_toks & (_DOCUMENTED_KINDS - {"park", "square", "bridge", "tower",
                                         "garden", "gardens", "theatre",
                                         "theater", "library"}):
        return "landmark" if not (name_toks & _BUSINESS_KINDS - {"market"}) \
            else "business"
    return "business"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Places record
# ─────────────────────────────────────────────────────────────────────────────

def _haversine_m(a, b) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi = math.radians(b[0] - a[0])
    dl = math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def _name_match(query: str, result: str) -> float:
    q, r = _fold(query), _fold(result)
    if not q or not r:
        return 0.0
    if q == r:
        return 1.0
    if q in r or r in q:
        return 0.9
    qt, rt = set(q.split()), set(r.split())
    return len(qt & rt) / len(qt | rt) if (qt | rt) else 0.0


def _parse_pin(value) -> Optional[Tuple[float, float]]:
    if not value:
        return None
    m = re.search(r"(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)", str(value))
    return (float(m.group(1)), float(m.group(2))) if m else None


_COUNTRY_GL = {
    "vietnam": "vn", "viet nam": "vn", "ho chi minh": "vn", "saigon": "vn",
    "hanoi": "vn", "france": "fr", "paris": "fr", "japan": "jp", "tokyo": "jp",
    "thailand": "th", "bangkok": "th", "united kingdom": "gb", "london": "gb",
    "germany": "de", "italy": "it", "spain": "es", "austria": "at",
    "vienna": "at", "portugal": "pt", "netherlands": "nl", "canada": "ca",
    "australia": "au", "singapore": "sg", "korea": "kr", "seoul": "kr",
}


def country_gl(location: str) -> str:
    f = _fold(location)
    for k, v in _COUNTRY_GL.items():
        if k in f:
            return v
    return "us"


def _domain_spells_name(website: str, names: List[str]) -> bool:
    """True when the website's registrable label spells the venue name
    ("an-spa.vn" for "An Spa") — the venue's OWN domain, a brand-identity signal."""
    host = (urlparse(website if "//" in (website or "") else f"https://{website}")
            .hostname or "").lower()
    if not host or any(b in host for b in _SKIP_SITE_HOSTS):
        return False
    label = host.split(".")[-2] if host.count(".") >= 1 else host
    if host.startswith("www."):
        label = host.split(".")[1]
    lab = re.sub(r"[^a-z0-9]", "", label)
    for n in names:
        toks = [t for t in _fold(n).split() if t not in ("the",)]
        if toks and "".join(toks) == lab:
            return True
    return False


def fetch_place_record(name: str, location: str, pin, places_fn=None,
                       max_m: float = 250.0, alias: str = "",
                       brand_max_m: float = 1000.0,
                       stats: Optional[Dict] = None) -> Optional[Dict]:
    """The Serper Places record for THIS venue, or None.

    Accepted only if its title matches the stop name or its Maps-URL alias
    (>= 0.6) AND it lies within ``max_m`` of the stop's pin — or within
    ``brand_max_m`` when the record's website is the venue's OWN domain spelling
    its name (a chain/branch whose pin the listener's link approximates).  Never a
    different venue's rating.  Query: "<alias or name> <city>", gl=<country>,
    ll=@<pin>,17z (Serper Places ignores a town in the query without ll)."""
    names = [n for n in (name, alias) if n]
    if places_fn is None:
        try:
            import places_search as _ps
            if not _ps.serper_places_enabled():
                return None

            def places_fn(q, scope, near):  # noqa: E306
                ll = f"@{near[0]},{near[1]},17z" if near else None
                key = f"l862|{q.lower()}|{ll}"
                hit = _ps._cache_get(key)
                if hit is not None:
                    return hit
                recs = _ps._serper_places_call(q, ll, gl=country_gl(scope))
                _ps._cache_put(key, recs)
                return recs
        except Exception:
            return None
    city = city_from_scope(location)
    queries = [f"{alias or name} {city}".strip()]
    if alias and _fold(alias) != _fold(name):
        queries.append(f"{name} {city}".strip())
    for q in queries:
        if stats is not None:
            stats["places"] = stats.get("places", 0) + 1
        try:
            recs = places_fn(q, location, pin) or []
        except Exception:
            recs = []
        best = _best_place(recs, names, pin, max_m, brand_max_m)
        if best is not None:
            return best
    return None


def _best_place(recs, names, pin, max_m, brand_max_m):
    best, best_score = None, 0.0
    for rec in recs:
        score = max(_name_match(n, rec.get("name") or "") for n in names)
        if score < 0.6:
            continue
        if pin:
            try:
                d = _haversine_m(pin, (float(rec["lat"]), float(rec["lon"])))
            except Exception:
                continue
            limit = max_m
            if _domain_spells_name(rec.get("_serper_website") or "", names):
                limit = brand_max_m
            if d > limit:
                continue
            rec = dict(rec, _l862_distance_m=round(d))
            score += max(0.0, 0.2 - d / 5000.0)
        if score > best_score:
            best, best_score = rec, score
    return best


# ─────────────────────────────────────────────────────────────────────────────
# 2. the venue's own website (<= 2 pages, robots respected)
# ─────────────────────────────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer",
             "form", "iframe", "template"}
    _BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "br", "section",
              "article", "tr", "td", "span"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self.parts: List[str] = []
        self.meta: Dict[str, str] = {}
        self.links: List[Tuple[str, str]] = []
        self._href = None
        self._link_text: List[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            k = (a.get("name") or a.get("property") or "").lower()
            if k in ("description", "og:description") and a.get("content"):
                self.meta[k] = a["content"].strip()
        if tag == "a" and a.get("href"):
            self._href = a["href"]
            self._link_text = []
        if tag in self._SKIP and tag != "span":
            self._skip += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._link_text).strip()))
            self._href = None
        if tag in self._SKIP and tag != "span" and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._href is not None:
            self._link_text.append(data.strip())
        if not self._skip and data.strip():
            self.parts.append(data)


def _public_host(host: str) -> bool:
    """Refuse localhost / private ranges (the website comes from a third party)."""
    if not host:
        return False
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast):
                return False
        return True
    except Exception:
        return False


def _default_fetch_page(url: str, timeout: int = 8) -> Optional[str]:
    """GET one HTML page (<= 400 KB).  None on any failure or non-HTML."""
    try:
        import requests
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not _public_host(p.hostname or ""):
            return None
        r = requests.get(url, headers={"User-Agent": _UA,
                                       "Accept": "text/html,*/*;q=0.5"},
                         timeout=timeout, stream=True, allow_redirects=True)
        if r.status_code != 200:
            return None
        if "html" not in (r.headers.get("content-type") or "").lower():
            return None
        raw = r.raw.read(400_000, decode_content=True)
        enc = r.encoding or "utf-8"
        return raw.decode(enc, "ignore")
    except Exception:
        return None


def _robots_allows(url: str, fetch_page: Callable, user_agent: str = "*") -> bool:
    """True unless robots.txt of the host disallows ``url`` for any agent."""
    p = urlparse(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    try:
        body = fetch_page(robots_url, kind="robots")
    except TypeError:
        body = fetch_page(robots_url)
    if not body:
        return True       # no robots.txt (or unreachable) -> allowed
    rp = robotparser.RobotFileParser()
    try:
        rp.parse(body.splitlines())
        return rp.can_fetch(user_agent, url) and rp.can_fetch("AudiouraTourBot", url)
    except Exception:
        return True


def _fetch_robots(url: str, timeout: int = 5) -> Optional[str]:
    try:
        import requests
        r = requests.get(url, headers={"User-Agent": _UA}, timeout=timeout)
        return r.text[:100_000] if r.status_code == 200 else None
    except Exception:
        return None


def _site_fetcher(fetch_page: Optional[Callable]) -> Callable:
    """One callable ``f(url, kind='page'|'robots')`` over an injected fetcher."""
    if fetch_page is not None:
        def _f(url, kind="page"):
            return fetch_page(url)
        return _f

    def _f(url, kind="page"):
        return _fetch_robots(url) if kind == "robots" else _default_fetch_page(url)
    return _f


_ABOUT_HREF_RE = re.compile(r"(?i)(about|our-?story|story|history|who-?we|ve-chung-toi|gioi-thieu)")

# Sentences worth keeping from a venue's own pages.  Chosen by keyword, KEPT VERBATIM.
_SITE_KEYS = re.compile(
    r"(?i)\b(founded|established|since|opened|opening|owner|owned|founder|"
    r"family|story|began|started|born|inspired|concept|specialt(?:y|ies)|"
    r"signature|famous for|known for|menu|serv(?:e|es|ing)|craft|handmade|"
    r"traditional|house[- ]made|cocktails?|live music|karaoke|massage|treatments?|"
    r"therap(?:y|ies)|rooms?|stage|performances?|coffee|beer|wine|dishes?)\b")
_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20[0-2]\d)\b")


def _site_sentences(text: str, max_n: int = 6) -> List[str]:
    out, seen = [], set()
    for chunk in re.split(r"\n+", text):
        chunk = " ".join(chunk.split())
        if not chunk:
            continue
        for s in _split_sentences(chunk):
            s = s.strip()
            if not (35 <= len(s) <= 320):
                continue
            if not _SITE_KEYS.search(s):
                continue
            if re.search(r"(?i)cookie|privacy|©|copyright|subscribe|newsletter|"
                         r"book now|click|login|log in|\+?\d[\d\s().-]{8,}", s):
                continue
            key = _fold(s)
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
    # sentences carrying a founding year first, then the rest in page order
    out.sort(key=lambda s: 0 if (_YEAR_RE.search(s) and re.search(
        r"(?i)founded|established|since|opened|began|started|born", s)) else 1)
    return out[:max_n]


def fetch_site_facts(website: str, fetch_page: Optional[Callable] = None,
                     log=None) -> Dict:
    """Homepage + one /about page (never more than ``_MAX_PAGES`` GETs).

    Returns {"pages": [urls], "sentences": [...], "description": str,
    "blocked_by_robots": bool}.  Never raises."""
    res = {"pages": [], "sentences": [], "description": "",
           "blocked_by_robots": False}
    if not website:
        return res
    p = urlparse(website if "//" in website else f"https://{website}")
    host = (p.netloc or "").lower()
    if not host or any(b in host for b in _SKIP_SITE_HOSTS):
        return res
    home = f"{p.scheme or 'https'}://{p.netloc}{p.path or '/'}"
    f = _site_fetcher(fetch_page)
    if not _robots_allows(home, f):
        res["blocked_by_robots"] = True
        if log:
            log(f"[LOCAL-862] robots.txt disallows {home} — site skipped")
        return res

    texts: List[str] = []
    parsers: List[_TextExtractor] = []
    html1 = f(home)
    if html1:
        res["pages"].append(home)
        ex = _TextExtractor()
        try:
            ex.feed(html1)
        except Exception:
            pass
        parsers.append(ex)
        texts.append(" ".join(ex.parts))
        # second page: an /about-ish link on the same host, else /about
        about = None
        for href, label in ex.links:
            if _ABOUT_HREF_RE.search(href) or _ABOUT_HREF_RE.search(label or ""):
                u = urljoin(home, href)
                up = urlparse(u)
                if up.netloc == p.netloc and up.scheme in ("http", "https") \
                        and u.rstrip("/") != home.rstrip("/"):
                    about = u.split("#")[0]
                    break
        about = about or urljoin(home, "/about")
        if len(res["pages"]) < _MAX_PAGES and _robots_allows(about, f):
            html2 = f(about)
            if html2:
                res["pages"].append(about)
                ex2 = _TextExtractor()
                try:
                    ex2.feed(html2)
                except Exception:
                    pass
                parsers.append(ex2)
                texts.append(" ".join(ex2.parts))
    desc = ""
    for ex in parsers:
        d = ex.meta.get("og:description") or ex.meta.get("description") or ""
        if d:
            desc = _html.unescape(d)
            break
    res["description"] = " ".join(desc.split())[:320]
    sents = _site_sentences("\n".join(t.replace("\n ", "\n") for t in texts))
    res["sentences"] = sents
    return res


# ─────────────────────────────────────────────────────────────────────────────
# 3. one story search
# ─────────────────────────────────────────────────────────────────────────────

def story_query(name: str, location: str, alias: str = "") -> str:
    city = city_from_scope(location)
    who = f'("{name}" OR "{alias}")' if alias and _fold(alias) != _fold(name) \
        else f'"{name}"'
    return f"{who} {city} history OR owner OR founded OR story".strip()


_CITY_ALIASES_F = {
    "ho chi minh": ("ho chi minh", "hochiminh", "saigon", "sai gon", "hcmc",
                    "district 1", "district 3", "quan 1", "quan 3"),
}
_KIND_WORDS = {
    # venue NOUNS only — not "show"/"music"/"menu"/"drinks", which co-occur with
    # a same-named film or song ("A Star is Born … TV show")
    "bar", "bars", "pub", "club", "lounge", "restaurant", "cafe", "karaoke",
    "spa", "massage", "nightclub", "gallery", "street", "venue", "nightlife",
    "cocktail", "taproom", "brewery", "bistro", "salon",
}
# a house number (6E1, 384/17, 224) followed by 1-4 Capitalised street words
_ADDR_NUM_RE = re.compile(
    r"\b\d{1,4}[A-Za-z]?\d*(?:/\d+[A-Za-z]?)*\s+((?:[A-ZĐÀ-Ỹ][\wÀ-ỹ]*\s?){1,4})")


def _locality_terms(location: str, poi: Dict, place: Optional[Dict]) -> set:
    city = _fold(city_from_scope(location))
    terms = {city} if city else set()
    for k, v in _CITY_ALIASES_F.items():
        if k in city:
            terms |= set(v)
    for src in ((poi or {}).get("address") or "",
                (place or {}).get("_serper_address") or ""):
        for part in src.split(","):
            f = _fold(re.sub(r"^\s*[\d/A-Za-z]*\d[\d/A-Za-z]*\s+", "", part))
            if len(f) >= 5:
                terms.add(f)
    return {t for t in terms if t}


def _phrase_in(phrase: str, hay: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {hay} "


def _kind_near_name(hay: str, names: List[str], window: int = 6) -> bool:
    """A venue-kind word within ``window`` tokens of an occurrence of the name
    ("Rambutan bar", "a bar called Rambutan"), or inside the name itself.  A kind
    word elsewhere in a page title ("… Bar & Grill Fans group") does not make a
    fruit-picking post about the venue."""
    toks = hay.split()
    for n in names:
        nt = [t for t in _fold(n).split() if t != "the"]
        if not nt:
            continue
        if set(nt) & _KIND_WORDS:
            if _phrase_in(" ".join(nt), hay):
                return True
            continue
        L = len(nt)
        for i in range(len(toks) - L + 1):
            if toks[i:i + L] == nt:
                ctx = toks[max(0, i - window):i] + toks[i + L:i + L + window]
                if set(ctx) & _KIND_WORDS:
                    return True
    return False


def snippet_is_about_venue(text: str, names: List[str], location: str,
                           poi: Dict = None, place: Dict = None,
                           need_both: bool = True) -> bool:
    """Strict: the snippet NAMES the venue (or its Maps alias) as a whole phrase,
    carries a venue-kind word (bar/spa/karaoke/street/…, so a fruit recipe or a
    film plot is not "Longan"/"A Star is Born") AND a locality term (the city or
    an alias of it, the district, the street of the Places address).  A snippet
    citing a house-number address on a street that is NOT the venue's own is
    another branch / another place and is rejected."""
    hay = _fold(text)
    if not hay:
        return False
    named = False
    for n in names:
        fn = _fold(n)
        toks = [t for t in fn.split() if t != "the"]
        if _phrase_in(fn, hay) or (toks and _phrase_in(" ".join(toks), hay)):
            named = True
            break
    if not named:
        return False
    has_kind = _kind_near_name(hay, names)
    loc = _locality_terms(location, poi or {}, place)
    has_loc = any(_phrase_in(t, hay) for t in loc)
    if need_both and not (has_kind and has_loc):
        return False
    if not need_both and not (has_kind or has_loc):
        return False
    own = _fold((place or {}).get("_serper_address") or (poi or {}).get("address") or "")
    if own:
        own_street = [t for t in own.split() if not any(c.isdigit() for c in t)]
        for m in _ADDR_NUM_RE.finditer(text):
            cited = [t for t in _fold(m.group(1)).split()
                     if not any(c.isdigit() for c in t)
                     and t not in ("street", "st", "road", "district")]
            if cited and own_street and not (set(cited) & set(own_street)):
                return False
    return True


def story_snippets(name: str, poi: Dict, location: str, serp_fn=None,
                   log=None, max_n: int = 3, alias: str = "",
                   place: Dict = None) -> Tuple[List[Dict], str, int]:
    """ONE metered Serper search; keep only snippets about THIS venue."""
    q = story_query(name, location, alias)
    if serp_fn is None:
        try:
            from work_story_searcher import _serp_search as serp_fn
        except Exception:
            return [], q, 0
    try:
        results, _lat = serp_fn(q)
    except Exception as e:
        if log:
            log(f"[LOCAL-862] story search failed for {name!r}: {e}")
        return [], q, 1
    names = [n for n in (name, alias) if n]
    kept: List[Dict] = []
    for r in results or []:
        if not isinstance(r, dict):
            continue
        title, snip = r.get("title") or "", (r.get("snippet") or "").strip()
        if not snip:
            continue
        if not snippet_is_about_venue(f"{title}. {snip}", names, location,
                                      poi=poi, place=place):
            continue
        if any(_fold(snip) == _fold(k["text"]) for k in kept):
            continue
        kept.append({"text": snip[:360], "url": r.get("url") or r.get("link") or ""})
        if len(kept) >= max_n:
            break
    if log:
        log(f"[LOCAL-862] story {name!r} q={q!r} -> {len(kept)}/"
            f"{len(results or [])} venue snippet(s)")
    return kept, q, 1


# ─────────────────────────────────────────────────────────────────────────────
# 4. material = numbered, sourced facts
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_hours(h) -> str:
    if not h:
        return ""
    if isinstance(h, dict):
        return "; ".join(f"{k} {v}" for k, v in list(h.items())[:7])[:200]
    return " ".join(str(h).split())[:200]


def gather_material(poi: Dict, location: str, *, places_fn=None,
                    fetch_page=None, serp_fn=None, review_snippets=None,
                    allow_search: bool = True, log=None, alias: str = "",
                    wiki_fn=None, wiki_search_fn=None) -> Dict:
    """Collect everything sourced about ONE business user stop.

    Returns {"name", "facts": [{"id","kind","text","source"}], "specifics": int,
    "place": rec|None, "calls": {...}} — ``facts`` is the narrator's ONLY source."""
    name = (poi.get("name") or poi.get("title") or "").strip()
    pin = _parse_pin(poi.get("coordinates"))
    calls = {"places": 0, "review_search": 0, "story_search": 0, "pages": 0,
             "ctx_serp": 0, "wiki": 0}
    facts: List[Dict] = []

    def add(kind, text, source, specific=True, layer=1):
        text = " ".join(str(text).split())
        if text:
            facts.append({"kind": kind, "text": text, "source": source,
                          "specific": specific, "layer": layer})

    # 1) Places record
    rec = None
    if allow_search:
        rec = fetch_place_record(name, location, pin, places_fn=places_fn,
                                 alias=alias, stats=calls)
    category = ""
    # A record accepted only through the venue's OWN domain (a branch of the
    # brand, farther than 250 m from the listener's pin) supplies BRAND facts —
    # its kind and its website — but not that branch's street address, hours or
    # rating: the listener is not standing at that branch.
    brand_only = bool(rec and (rec.get("_l862_distance_m") or 0) > 250)
    if rec:
        category = (rec.get("_serper_category") or "").strip()
        addr = (rec.get("_serper_address") or "").strip()
        src = f"serper_places:cid={rec.get('_serper_cid')}" if rec.get("_serper_cid") \
            else "serper_places"
        if brand_only:
            src += (f" (brand: own domain {urlparse(rec.get('_serper_website') or '').hostname},"
                    f" branch {rec['_l862_distance_m']} m from pin)")
        if category:
            add("category", f"Google Maps lists {name} as: {category}.", src,
                specific=False)
        if addr and not brand_only:
            add("address", f"Its address is {addr}.", src, specific=False)
        hrs = _fmt_hours(rec.get("_serper_hours"))
        if hrs and not brand_only:
            add("hours", f"Opening hours listed on Google Maps: {hrs}.", src)

    # 2) customer voice — reuses the Places numbers; ONE review search (LOCAL-800)
    cvf, cv = None, None
    try:
        import customer_voice as cv
        snips = review_snippets
        if snips is None and allow_search:
            snips = cv._serper_review_snippets(
                (rec or {}).get("name") or alias or name, city_from_scope(location))
            calls["review_search"] = 1
            # only snippets about THIS venue feed "what reviewers say"
            _nm = [n for n in (name, alias, (rec or {}).get("name")) if n]
            snips = [x for x in (snips or [])
                     if snippet_is_about_venue(x, _nm, location, poi=poi, place=rec,
                                               need_both=False)]
        # review_snippets given (even []) => collect_facts makes NO network call
        cv_rec = {} if brand_only else (rec or {})
        cvf = cv.collect_facts(cv_rec, name, location, allow_search=False,
                               review_snippets=list(snips or []))
    except Exception:
        cvf = None
    if cvf:
        src = "serper_places" if rec else "serper_search:reviews"
        r, n = cvf.get("rating"), cvf.get("rating_count")
        if r is not None and n is not None:
            add("rating", f"Google reviewers give it {r:g} out of 5 from "
                f"{cv._round_count(n)} reviews.", "serper_places")
        elif r is not None:
            add("rating", f"Google reviewers give it {r:g} out of 5.", "serper_places")
        if cvf.get("price_band"):
            add("price", f"Prices are around {cvf['price_band']} per person.",
                "serper_places")
        if cvf.get("items"):
            add("signature", "Reviewers keep mentioning: "
                + ", ".join(cvf["items"]) + ".", "serper_search:reviews")
        if cvf.get("top_praise"):
            add("praise", f"Reviewers most often call it {cvf['top_praise']}.",
                "serper_search:reviews")
        if cvf.get("since_year"):
            add("since", f"Review sources say it has been open since "
                f"{cvf['since_year']}.", "serper_search:reviews")
        if cvf.get("top_complaint"):
            add("complaint", f"A recurring complaint is that some find it "
                f"{cvf['top_complaint']}.", "serper_search:reviews")

    # 3) the venue's own website
    website = ((rec or {}).get("_serper_website") or poi.get("website") or "").strip()
    if website and allow_search:
        site = fetch_site_facts(website, fetch_page=fetch_page, log=log)
        calls["pages"] = len(site["pages"])
        if site["description"]:
            add("site", site["description"], site["pages"][0] if site["pages"] else website)
        for s in site["sentences"]:
            add("site", s, site["pages"][0] if site["pages"] else website)

    # 4) one story search
    if allow_search:
        snips, q, nq = story_snippets(name, poi, location, serp_fn=serp_fn, log=log,
                                      alias=alias, place=rec)
        calls["story_search"] = nq
        own_host = (urlparse(website if "//" in (website or "") else f"https://{website}")
                    .hostname or "").lower().replace("www.", "") if website else ""
        names_ = [n for n in (name, alias) if n]
        for sn in snips:
            url = sn.get("url") or "serper_search:story"
            host = (urlparse(url).hostname or "").lower().replace("www.", "")
            third_party = not (own_host and host and own_host == host)
            # [LOCAL-862B / D760] a specific claim (a year, a "first", a legend) that
            # rests on ONE third-party web snippet, in a sentence that names the
            # venue, is unconfirmed: layer 3, told with "We couldn't confirm this,
            # but ...".  Anything else stays an ordinary story fact.
            claim = None
            if third_party:
                for sent in _split_sentences(sn["text"]):
                    if _SPECIFIC_CLAIM_RE.search(sent) and any(
                            _phrase_in(_fold(n), _fold(sent)) for n in names_):
                        claim = sent.strip()
                        break
            if claim and len(claim) >= 40 and not claim.endswith(("...", "…")):
                add("unconfirmed", claim, url, layer=3)
            else:
                try:   # [LOCAL-862C] a review/web definition never redefines the kind
                    import user_stop_context as _uscA
                    stext = _uscA.attribute_story(sn["text"], name, category)
                except Exception:
                    stext = sn["text"]
                add("story", stext, url)

    # 5) [LOCAL-862B / D760] layer 2 (true connected context) and layer 3 (a
    # disclosed legend). Sourced from Wikipedia + Serper, tied to the venue's NAME,
    # STREET, and the TRADITION behind what it offers.
    ctx_calls = {"wiki": 0, "serp": 0}
    if allow_search:
        try:
            import user_stop_context as _usc
            kt = set(_fold(category).split()) | set(_fold(name).split())
            listed = ""
            if not category:
                ts = (poi.get("type_specialty") or "").strip()
                tt = set(_fold(ts).split())
                if _usc._tradition_for(tt & _BUSINESS_KINDS) and not _usc._tradition_for(kt):
                    kt |= tt
                    listed = ts
            ctx = _usc.gather_context(poi, location, place=rec, alias=alias,
                                      kind_tokens=kt, serp_fn=serp_fn, log=log,
                                      wiki_fn=wiki_fn, wiki_search_fn=wiki_search_fn)
            ctx_calls = ctx["calls"]
            if listed and any(f["kind"] == "tradition" for f in ctx["facts"]):
                add("listed_as", f"Your tour lists {name} as: {listed.lower()}.",
                    "tour stop list (the listener's request, not independently confirmed)",
                    specific=False, layer=2)
            for cf in ctx["facts"]:
                add(cf["kind"], cf["text"], cf["source"], layer=cf["layer"])
        except Exception as e:
            if log:
                log(f"[LOCAL-862B] context skipped for {name!r}: {e}")
    calls["ctx_serp"] = ctx_calls.get("serp", 0)
    calls["wiki"] = ctx_calls.get("wiki", 0)

    for i, f in enumerate(facts, 1):
        f["id"] = f"F{i}"
    return {"name": name, "facts": facts, "place": rec, "calls": calls,
            "category": category, "specifics": count_specifics(facts),
            "layers": layer_counts(facts)}


_SPECIFIC_CLAIM_RE = re.compile(
    r"(?i)\b(1[89]\d{2}|20[0-2]\d|first|founded|established|opened\s+in|"
    r"legend|rumou?r|said\s+to|named\s+after)\b")


def layer_counts(facts: List[Dict]) -> Dict[str, int]:
    """Specific facts per layer: 1 = venue facts, 2 = connected context, 3 = legend
    or unconfirmed claim."""
    out = {"1": 0, "2": 0, "3": 0}
    for f in facts:
        if f.get("specific", True):
            out[str(f.get("layer", 1))] = out.get(str(f.get("layer", 1)), 0) + 1
    return out


def count_specifics(facts: List[Dict]) -> int:
    """Distinct sourced specifics: rating+count, price, hours, each signature /
    praise / complaint / since, each site sentence, each story snippet.  Category
    and address are context, not specifics."""
    seen = set()
    n = 0
    for f in facts:
        if not f.get("specific", True) or f.get("layer", 1) != 1:
            continue
        key = (f["kind"], _fold(f["text"]))
        if key in seen:
            continue
        seen.add(key)
        n += 1
    return n


def select_facts(material: Dict, caps=(12, 8, 3)) -> List[Dict]:
    """The facts handed to the narrator and the verifier: layer 1 (venue), then
    layer 2 (context), then layer 3 (legend/unconfirmed), each capped."""
    out: List[Dict] = []
    for layer, cap in zip((1, 2, 3), caps):
        out.extend([f for f in material.get("facts", [])
                    if f.get("layer", 1) == layer][:cap])
    return out


def material_lines(material: Dict, limit: int = 23) -> List[str]:
    """Fact-sheet lines for the verifier. Layer-2/3 lines carry a [context] /
    [legend] / [unconfirmed] tag so the verifier knows which sentences need a
    disclosure marker."""
    import user_stop_context as _usc
    lines = []
    for f in select_facts(material)[:limit]:
        tag = _usc.layer_tag(f)
        lines.append(f["text"] if tag == "venue" else f"[{tag}] {f['text']}")
    return lines


# ─────────────────────────────────────────────────────────────────────────────
# 5. thin stop (deterministic, uses the Places data)
# ─────────────────────────────────────────────────────────────────────────────

def _article(w: str) -> str:
    return "an" if (w or "").strip().lower()[:1] in "aeiou" else "a"


_NAME_KIND = (
    ("karaoke", "karaoke bar"), ("spa", "spa"), ("bar", "bar"), ("pub", "pub"),
    ("cafe", "café"), ("café", "café"), ("coffee", "café"),
    ("restaurant", "restaurant"), ("bistro", "bistro"), ("lounge", "lounge"),
    ("club", "club"), ("gallery", "gallery"), ("market", "market"),
    ("street", "street"), ("bakery", "bakery"), ("salon", "salon"),
)


def sourced_kind(name: str, material: Dict) -> str:
    """The venue's kind ONLY from a source: the Places category, else a kind word
    in the venue's own name ("An Spa" -> spa, "Acoustic Bar" -> bar).  Never the
    generator's Type/Specialty guess ("A Star is Born" is not 'a café')."""
    cat = (material.get("category") or "").strip()
    if cat:
        return cat
    toks = _fold(name).split()
    for w, kind in _NAME_KIND:
        if w in toks:
            return kind
    return ""


def sourced_examples(material: Dict) -> str:
    for f in material.get("facts", []):
        if f["kind"] == "signature":
            return f["text"].split(":", 1)[-1].strip().rstrip(".")
    return ""


def thin_stop_body(poi: Dict, material: Dict, location: str = "") -> str:
    """Short, deterministic, TRUE: what it is (only when sourced) and where, plus
    whatever Places/reviews gave (rating, price, hours, signature items).  No
    history, no atmosphere, and none of the generator's Type/Examples guesses."""
    name = material.get("name") or poi.get("name") or ""
    by_kind: Dict[str, str] = {}
    for f in material.get("facts", []):
        by_kind.setdefault(f["kind"], f["text"])
    kind = sourced_kind(name, material)
    city = city_from_scope(location)
    where = f" in {city}" if city else ""
    if kind:
        sents = [f"{name} is {_article(kind)} {kind.lower()}{where}."]
    else:
        sents = [f"{name} is one of the places you chose{', here' if city else ''}{where}."]
    for k in ("rating", "price", "hours", "signature", "praise"):
        if k in by_kind:
            sents.append(by_kind[k])
    pl = material.get("place") or {}
    addr = "" if (pl.get("_l862_distance_m") or 0) > 250 else \
        (pl.get("_serper_address") or "").strip()
    if addr:
        sents.append(f"Look for {name} at {addr}.")
    return " ".join(sents).strip()


def _set_sourced_fields(lines: List[str], start: int, end: int,
                        kind: str, examples: str) -> int:
    """Rewrite the stop's Type/Specialty and Specific Examples lines so they state
    ONLY sourced values (generator guesses removed).  Returns the line delta."""
    delta = 0
    i = start
    type_done = False
    while i < end + delta:
        ln = lines[i]
        if re.match(r"(?i)^Type/Specialty:", ln):
            type_done = True
            if kind:
                lines[i] = f"Type/Specialty: {kind}"
            else:
                del lines[i]
                if i < len(lines) and not lines[i].strip():
                    del lines[i]
                    delta -= 1
                delta -= 1
                continue
        elif re.match(r"(?i)^Specific Examples:", ln):
            if examples:
                lines[i] = f"Specific Examples: {examples}"
            else:
                del lines[i]
                if i < len(lines) and not lines[i].strip():
                    del lines[i]
                    delta -= 1
                delta -= 1
                continue
        i += 1
    if kind and not type_done:
        for j in range(start, end + delta):
            if re.match(r"(?i)^Coordinates:", lines[j]):
                lines[j + 1:j + 1] = ["", f"Type/Specialty: {kind}"]
                delta += 2
                break
    return delta


# ─────────────────────────────────────────────────────────────────────────────
# 6. narration — ONE batched call, material is the ONLY source
# ─────────────────────────────────────────────────────────────────────────────

_NARR_SYSTEM = (
    "You write short spoken audio-tour stops about small venues a listener chose. "
    "For each stop you are given a numbered FACT LIST in up to three layers. It is "
    "your ONLY source.\n"
    "THE THREE LAYERS, told in this order:\n"
    "  LAYER 1 - VENUE FACTS (about the venue itself). State them as fact.\n"
    "  LAYER 2 - CONNECTED CONTEXT (true background on the venue's NAME, its STREET "
    "or district, or the TRADITION behind what it offers). State as fact, but every "
    "layer-2 sentence must visibly tie back to the venue: it must contain the "
    "venue's name or one of the phrases 'the name', 'the street it sits on', 'the "
    "tradition it belongs to' (example: 'Vietnamese massage, the tradition An Spa "
    "belongs to, goes back ...'; 'The name Longan comes from ...'). Never "
    "suggest a context fact is part of the venue's own history, owner or menu "
    "(a fruit's story is the story of the WORD in the name, not of what is sold), "
    "and NEVER say the venue itself is a tree, a fruit, a street or a person: say "
    "'the name Rambutan comes from ...', 'the bar shares its name with ...'.\n"
    "  LAYER 3 - LEGEND OR UNCONFIRMED (facts tagged [legend] or [unconfirmed]). "
    "EVERY layer-3 sentence MUST carry a disclosure: for a [legend] fact open with "
    "'A folk tale tells that ...' (say 'Vietnamese' only if the fact does) or "
    "'Legend has it that ...'; for an [unconfirmed] fact open with 'We couldn't "
    "confirm this, but ...' (that includes the fact 'The venue may have taken its "
    "name from that title': say 'We couldn't confirm this, but the name may nod to "
    "it'). Never state a layer-3 fact as plain fact, and never put "
    "a disclosure on a layer-1 or layer-2 sentence. A [legend] fact is ONE short "
    "retelling: tell it as ONE block of consecutive sentences with the disclosure "
    "ONLY on its first sentence, self-contained; never split it up or mix it with "
    "other facts.\n"
    "KIND: what kind of place the venue is comes ONLY from the Google Maps category "
    "fact. A story or review fact that describes it as something else is what "
    "reviewers or web pages SAY ('reviews mention live bands'); never let it "
    "redefine the venue. Never repeat the same name twice in one list or sentence.\n"
    "RULES (strict):\n"
    "- Every claim comes from the FACT LIST. Do not use anything you know from "
    "memory. Do not add a year, a person, an event, a 'first', a dish, decor, a "
    "smell, a view, or any geography that is not in the list.\n"
    "- 'orientation': ONE sentence that names the venue, says what kind of place it "
    "is and where to find it, using only the kind/address facts given. If no kind "
    "is given, say it is one of the stops on the listener's route and where.\n"
    "- 'body': 4 to 7 sentences of natural spoken English, ordered layer 1, then "
    "layer 2, then layer 3. Use the facts of every layer that has any. With fewer "
    "facts, write fewer sentences, but never pad: no filler, no feelings, no "
    "questions, no commands, no superlatives the facts do not state.\n"
    "- Ignore any fact that only describes a video, a post, a page or a guide. If a "
    "fact says the venue is something other than what the FACT LIST says, ignore it.\n"
    "- Never list more than three items in a row. Numbers exactly as given. Keep "
    "foreign words and names exactly as given.\n"
    "Return ONLY JSON: {\"stops\":[{\"id\":<int>,\"orientation\":\"...\","
    "\"body\":\"...\",\"used\":[\"F1\",\"F3\"]}]} where \"used\" lists the fact ids "
    "you relied on."
)

_LAYER_HEAD = {
    1: "LAYER 1 - VENUE FACTS",
    2: "LAYER 2 - CONNECTED CONTEXT (true; tie each sentence back to the venue)",
    3: "LAYER 3 - LEGEND / UNCONFIRMED (every sentence needs a disclosure)",
}


def _narr_user(batch: List[Dict], location: str) -> str:
    import user_stop_context as _usc
    city = city_from_scope(location)
    parts = [f"City: {city}\n"]
    for b in batch:
        parts.append(f"STOP id={b['id']} - \"{b['name']}\" - FACT LIST by layer")
        for layer in (1, 2, 3):
            fl = [f for f in b["facts"] if f.get("layer", 1) == layer]
            if not fl:
                continue
            parts.append(f"{_LAYER_HEAD[layer]}:")
            for f in fl:
                tag = _usc.layer_tag(f)
                pre = f"[{tag}] " if layer == 3 else ""
                parts.append(f"  {f['id']}. {pre}{f['text']}")
        parts.append("")
    return "\n".join(parts)


def narrate_batch(batch: List[Dict], location: str, api_key: str, model: str,
                  llm_fn=None) -> Tuple[Dict[int, Dict], int, int]:
    """Returns ({id: {"text","used"}}, input_tokens, output_tokens)."""
    if not batch:
        return {}, 0, 0
    user = _narr_user(batch, location)
    if llm_fn is None:
        from user_stop_verify import _call_openai
        parsed, i, o = _call_openai(_NARR_SYSTEM, user, api_key, model,
                                    timeout=60, max_tokens=3000)
    else:
        parsed, i, o = llm_fn(_NARR_SYSTEM, user)
    out: Dict[int, Dict] = {}
    for st in (parsed or {}).get("stops", []) or []:
        try:
            ori = " ".join(str(st.get("orientation", "")).split())
            body = " ".join(str(st.get("body", "")).split())
            if not (ori or body):           # tolerate the older single-field shape
                txt = " ".join(str(st.get("text", "")).split())
                ss = _split_sentences(txt)
                ori, body = (ss[0] if ss else ""), " ".join(ss[1:])
            out[int(st.get("id"))] = {"orientation": ori, "body": body,
                                      "text": f"{ori} {body}".strip(),
                                      "used": list(st.get("used") or [])}
        except Exception:
            continue
    return out, i, o


# ─────────────────────────────────────────────────────────────────────────────
# 7. tour-text integration
# ─────────────────────────────────────────────────────────────────────────────

_FIELD = re.compile(r"(?mi)^(Coordinates|Type/Specialty|Specific Examples|Directions|"
                    r"Tour-Category|Address):")


def _rewrite_block(lines: List[str], start: int, end: int, narration: str,
                   orientation: str = None, body: str = None) -> None:
    """Replace the narration paragraphs of lines[start:end] with ``narration``.

    Field lines, Directions, Sources and a trailing tour-conclusion recap are kept.
    The narration becomes ``Orientation: <first two sentences>`` + one body
    paragraph, inserted before Directions (or before the recap / at the end)."""
    from user_stop_verify import _CONCLUSION_LEAD_RE, _FIELD_LINE_RE
    keep: List[str] = []
    insert_at = None
    for i in range(start, end):
        ln = lines[i]
        s = ln.strip()
        if not s:
            keep.append(ln)
            continue
        if re.match(r"(?i)^directions:", s) and insert_at is None:
            insert_at = len(keep)
            keep.append(ln)
            continue
        if _FIELD_LINE_RE.match(ln) or s.lower().startswith("sources"):
            keep.append(ln)
            continue
        if _CONCLUSION_LEAD_RE.match(s):
            if insert_at is None:
                insert_at = len(keep)
            keep.append(ln)
            continue
        # an old Orientation / narration paragraph -> dropped
    if orientation is not None or body is not None:
        head, tail = (orientation or "").strip(), (body or "").strip()
        if not head:
            ss = _split_sentences(tail)
            head, tail = (ss[0] if ss else ""), " ".join(ss[1:])
    else:
        sents = _split_sentences(narration)
        head = sents[0].strip() if sents else ""
        tail = " ".join(sents[1:]).strip()
    block = [f"Orientation: {head}", ""]
    if tail:
        block += [tail, ""]
    if insert_at is None:
        insert_at = len(keep)
    new = keep[:insert_at] + block + keep[insert_at:]
    # collapse runs of blank lines to one
    out: List[str] = []
    for ln in new:
        if not ln.strip() and out and not out[-1].strip():
            continue
        out.append(ln)
    lines[start:end] = out


def _set_type_line(lines: List[str], start: int, end: int, category: str) -> int:
    """When Places supplies the category, the Type/Specialty line states IT (a
    sourced fact) instead of the generator's guess.  Adds the line if missing."""
    if not category:
        return 0
    for i in range(start, end):
        if re.match(r"(?i)^Type/Specialty:", lines[i]):
            lines[i] = f"Type/Specialty: {category}"
            return 0
    for i in range(start, end):
        if re.match(r"(?i)^Coordinates:", lines[i]):
            lines[i + 1:i + 1] = ["", f"Type/Specialty: {category}"]
            return 2
    return 0


def enrich_user_stops_in_text(
        tour_text: str, user_titles: List[str], location: str = "",
        api_key: str = None, model: str = None, log=None,
        places_fn=None, fetch_page=None, serp_fn=None, review_snippets=None,
        llm_fn=None, allow_search: bool = True,
        aliases_by_title: Optional[Dict[str, str]] = None) -> Tuple[str, Dict]:
    """Rewrite every BUSINESS-kind user stop from sourced material.

    Returns (new_text, report).  report["material_by_title"] feeds the verifier;
    report["precomposed"] lists titles already final (thin deterministic stops) so
    the verifier leaves them alone."""
    from user_stop_verify import (_STOP_HDR_RE, _TYPE_LINE_RE, _ADDRESS_LINE_RE,
                                  _EXAMPLES_LINE_RE, _COORD_LINE_RE,
                                  _folded_titles, _title_is_user)
    model = model or os.environ.get("USER_STOP_ENRICH_MODEL", "gpt-4.1-mini")
    report: Dict = {"ran": False, "model": model, "stops": [], "input_tokens": 0,
                    "output_tokens": 0, "llm_cost_usd": 0.0, "serper_cost_usd": 0.0,
                    "total_cost_usd": 0.0, "material_by_title": {},
                    "precomposed": [], "specifics_ge2": 0}
    if not tour_text or not user_titles:
        return tour_text or "", report
    folded = _folded_titles(user_titles)
    lines = tour_text.split("\n")
    headers = [(i, m) for i, ln in enumerate(lines)
               for m in [_STOP_HDR_RE.match(ln)] if m]
    if not headers:
        return tour_text, report

    work: List[Dict] = []
    for h_idx, (line_no, m) in enumerate(headers):
        title = m.group(2).strip()
        if not _title_is_user(title, folded):
            continue
        start = line_no + 1
        end = headers[h_idx + 1][0] if h_idx + 1 < len(headers) else len(lines)
        block_text = "\n".join(lines[start:end])
        poi = {"name": title, "title": title, "user_explicit": True}
        for rx, key in ((_TYPE_LINE_RE, "type_specialty"),
                        (_ADDRESS_LINE_RE, "address"),
                        (_EXAMPLES_LINE_RE, "specific_examples")):
            mm = rx.search(block_text)
            if mm:
                poi[key] = mm.group(1).strip()
        cm = _COORD_LINE_RE.search(block_text)
        if cm:
            poi["coordinates"] = f"{cm.group(1)}, {cm.group(2)}"
        kind = classify_stop_kind(title, poi.get("type_specialty", ""))
        if kind != "business":
            if log:
                log(f"[LOCAL-862] {title}: landmark kind — existing story path kept")
            report["stops"].append({"stop": title, "kind": "landmark"})
            continue
        alias = ""
        for k, v in (aliases_by_title or {}).items():
            if _fold(k) == _fold(title) and v and _fold(v) != _fold(title):
                alias = v
                break
        work.append({"title": title, "poi": poi, "alias": alias})

    # gather (network) — per stop
    for w in work:
        mat = gather_material(w["poi"], location, places_fn=places_fn,
                              fetch_page=fetch_page, serp_fn=serp_fn,
                              review_snippets=review_snippets,
                              allow_search=allow_search, log=log,
                              alias=w.get("alias", ""))
        # a Places category can reveal that the "business" is really a landmark
        # (type missing from the block): keep the existing path for it.
        if mat["category"] and classify_stop_kind(
                w["title"], w["poi"].get("type_specialty", ""), mat["category"]) != "business":
            w["landmark"] = True
        w["mat"] = mat
        if log:
            kinds = {}
            for f in mat["facts"]:
                kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
            log(f"[LOCAL-862] material {w['title']}: specifics={mat['specifics']} "
                f"facts={kinds} calls={mat['calls']}")

    # [LOCAL-862B / D760] narrate whenever ANY layer has a specific (venue fact,
    # connected context, or legend); the short deterministic stop is the last
    # resort, only when all three layers are empty of specifics.
    def _narratable(m):
        lc = m.get("layers") or {}
        return (m["specifics"] + lc.get("2", 0) + lc.get("3", 0)) >= 1
    rich = [w for w in work if not w.get("landmark") and _narratable(w["mat"])]
    batch = [{"id": i, "name": w["title"], "facts": select_facts(w["mat"])}
             for i, w in enumerate(rich)]
    if api_key is None:
        api_key = os.environ.get("OPENAI_API_KEY")
    narrated, in_tok, out_tok = ({}, 0, 0)
    if batch:
        narrated, in_tok, out_tok = narrate_batch(batch, location, api_key, model,
                                                  llm_fn=llm_fn)
        report["ran"] = bool(narrated)
    report["input_tokens"], report["output_tokens"] = in_tok, out_tok
    try:
        from cost_rates import llm_cost
        report["llm_cost_usd"] = round(llm_cost(in_tok, out_tok, model), 6)
    except Exception:
        report["llm_cost_usd"] = round(in_tok / 1e6 * 0.40 + out_tok / 1e6 * 1.60, 6)

    try:
        from cost_rates import SERPER_COST_PER_QUERY as _sq, SERPER_PLACES_COST_PER_QUERY as _pq
    except Exception:
        _sq, _pq = 0.001, 0.002
    per_stop_llm = (report["llm_cost_usd"] / len(batch)) if batch else 0.0

    # apply — walk headers bottom-up so line indices stay valid
    bridge_by_title: Dict[str, str] = {}
    by_title = {w["title"]: w for w in work if not w.get("landmark")}
    id_of = {w["title"]: i for i, w in enumerate(rich)}
    for h_idx in range(len(headers) - 1, -1, -1):
        line_no, m = headers[h_idx]
        title = m.group(2).strip()
        w = by_title.get(title)
        if not w:
            continue
        start = line_no + 1
        end = headers[h_idx + 1][0] if h_idx + 1 < len(headers) else len(lines)
        mat = w["mat"]
        c = mat["calls"]
        serper = c["places"] * _pq + (c["review_search"] + c["story_search"]
                                      + c.get("ctx_serp", 0)) * _sq
        entry = {"stop": title, "kind": "business", "specifics": mat["specifics"],
                 "layers": mat.get("layers"), "calls": c, "serper_cost_usd": round(serper, 6),
                 "sources": sorted({f["source"] for f in mat["facts"]}),
                 "facts": [(f["id"], f["kind"], f["text"], f["source"], f.get("layer", 1))
                           for f in mat["facts"]]}
        end += _set_sourced_fields(lines, start, end, sourced_kind(title, mat),
                                   sourced_examples(mat))
        nar = (narrated.get(id_of.get(title, -1)) or {}) if title in id_of else {}
        text = nar.get("text")
        if title in id_of and text and len(_split_sentences(text)) >= 2:
            ori = nar.get("orientation")
            # [LOCAL-862B] with no sourced kind the venue is only "a stop you
            # chose"; a model orientation would guess a kind (or call it a fruit).
            if not sourced_kind(title, mat):
                city_ = city_from_scope(location)
                ori = (f"{title} is one of the stops you chose" +
                       (f", here in {city_}." if city_ else "."))
            body_ = nar.get("body")
            try:
                import user_stop_context as _usc2
                if body_:
                    sel_ = select_facts(mat)
                    # [LOCAL-862C] a legend is ONE coherent block, disclosed once
                    body_, n_leg = _usc2.apply_legend_blocks(body_, sel_)
                    body_, n_fix = _usc2.ensure_disclosure(body_, sel_)
                    if n_fix and log:
                        log(f"[LOCAL-862B] {title}: added the disclosure marker to "
                            f"{n_fix} layer-3 sentence(s)")
                    # [LOCAL-862C] bridge from the name to the venue
                    body_, br_ = _usc2.insert_bridge(body_, title, sourced_kind(title, mat), sel_)
                    if br_:
                        bridge_by_title[title] = br_
                    body_ = " ".join(_usc2.dedupe_names(x) for x in _split_sentences(body_))
                    body_ = _usc2.kind_guard(body_, mat.get("category") or "")
            except Exception:
                pass
            _rewrite_block(lines, start, end, text, ori, body_)
            entry.update(mode="narrated", llm_cost_usd=round(per_stop_llm, 6),
                         narration=text, used=nar.get("used"))
            report["material_by_title"][title] = material_lines(mat) + (
                [f"[context] {bridge_by_title[title]}"] if title in bridge_by_title else [])
            report["specifics_ge2"] += 1
        else:
            body = thin_stop_body(w["poi"], mat, location)
            _rewrite_block(lines, start, end, body)
            entry.update(mode="thin_deterministic", llm_cost_usd=0.0)
            report["precomposed"].append(title)
            if mat["specifics"] >= _MIN_SPECIFICS:
                entry["note"] = "narration unavailable — fell back to thin body"
        entry["total_cost_usd"] = round(entry["serper_cost_usd"]
                                        + entry["llm_cost_usd"], 6)
        report["stops"].append(entry)
        report["serper_cost_usd"] += serper
        if log:
            log(f"[LOCAL-862] {title}: {entry['mode']} specifics="
                f"{mat['specifics']} cost=${entry['total_cost_usd']:.4f}")
    report["stops"].reverse()
    report["serper_cost_usd"] = round(report["serper_cost_usd"], 6)
    report["total_cost_usd"] = round(report["serper_cost_usd"]
                                     + report["llm_cost_usd"], 6)
    return "\n".join(lines), report
