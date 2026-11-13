#!/usr/bin/env python3
"""topic_relevance.py — LOCAL-907B: is a candidate Topic Library article about THIS region?

* ``WikiMeta`` — batched (50 titles / query), polite, disk-cached lookup of what the gate
  needs per article: exists?, canonical title, url, primary coordinates, visible categories,
  lead text.
* ``check_relevance`` — the gate. A linked article passes only if (a) its coordinates are
  within the region radius, (b) its lead + first 2 sections name the region >= 3 times, or
  (c) one of its categories contains a region name. Seeds / hints are exempt (the caller
  decides). Publishers, media, sports leagues, lists, disambiguation pages and whole
  other countries/cities are excluded first.
* ``classify_article`` — theme from the article's OWN lead and categories (never from the
  link context). Returns None rather than guess.

No place names live here (D769): region names, aliases and radius come from
data/topic_regions.json.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import unicodedata
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import topic_library as tl
import wiki_client as wc

log = logging.getLogger("topic_library")

MIN_MENTIONS = 3
MENTION_SECTIONS = 2          # lead + first N sections
MIN_MENTION_DENSITY = 4.0     # mentions per 1000 words: a long national page that names the
                              # region in passing (a train network, a country) is not about it

META_CACHE_DIR = os.environ.get("TOPIC_META_CACHE", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "topic_source_cache", "meta"))


def fold(s: str) -> str:
    s = (s or "").replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


# ═════════════════════════════════════════════════════════════════════════════
# metadata lookup (batched, polite, cached)
# ═════════════════════════════════════════════════════════════════════════════
class WikiMeta:
    """meta_fn(lang, titles) -> {requested_title: meta}. A title that could not be fetched
    (failed after the retries) is simply absent from the result and is logged."""

    def __init__(self, client: Optional[wc.WikiClient] = None, cache_dir: Optional[str] = None):
        self.client = client or wc.default_client()
        self.cache_dir = cache_dir or META_CACHE_DIR
        self.failed: List[str] = []

    def _path(self, lang: str, title: str) -> str:
        h = hashlib.sha1(f"{lang}|{title}".encode("utf-8")).hexdigest()[:20]
        return os.path.join(self.cache_dir, f"{lang}_{h}.json")

    def __call__(self, lang: str, titles: Iterable[str]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        todo: List[str] = []
        for t in dict.fromkeys(x for x in titles if x):
            p = self._path(lang, t)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as fh:
                    out[t] = json.load(fh)
            else:
                todo.append(t)
        for batch in wc.chunks(todo, wc.MAX_TITLES_PER_QUERY):
            try:
                got = self._query(lang, batch)
            except wc.WikiFetchError as e:
                log.warning("[LOCAL-907B] metadata for %d titles skipped: %s", len(batch), e)
                self.failed += batch
                continue
            os.makedirs(self.cache_dir, exist_ok=True)
            for t in batch:
                m = got.get(t) or {"exists": False, "title": t}
                with open(self._path(lang, t), "w", encoding="utf-8") as fh:
                    json.dump(m, fh, ensure_ascii=False)
                out[t] = m
        return out

    def _query(self, lang: str, titles: List[str]) -> Dict[str, Dict[str, Any]]:
        api = f"https://{lang}.wikipedia.org/w/api.php"
        params: Dict[str, Any] = {
            "action": "query", "formatversion": "2", "redirects": "1",
            "prop": "coordinates|categories|extracts|info", "inprop": "url",
            "coprimary": "primary", "colimit": "max", "cllimit": "max", "clshow": "!hidden",
            "exintro": "1", "explaintext": "1", "exlimit": "max",
            "titles": "|".join(titles)}
        pages: Dict[Any, Dict[str, Any]] = {}
        redirects: Dict[str, str] = {}
        normalized: Dict[str, str] = {}
        for _ in range(60):                                   # bounded continuation
            data = self.client.get_json(api, dict(params))
            q = data.get("query") or {}
            for r in q.get("redirects", []):
                redirects[r["from"]] = r["to"]
            for r in q.get("normalized", []):
                normalized[r["from"]] = r["to"]
            for p in q.get("pages", []):
                key = p.get("pageid") or p.get("title")
                cur = pages.setdefault(key, {"title": p.get("title"), "missing": bool(p.get("missing"))})
                if p.get("fullurl"):
                    cur["url"] = p["fullurl"]
                if p.get("coordinates"):
                    cur["coords"] = (p["coordinates"][0]["lat"], p["coordinates"][0]["lon"])
                cur.setdefault("categories", [])
                for c in p.get("categories", []):
                    name = c["title"].split(":", 1)[-1]
                    if name not in cur["categories"]:
                        cur["categories"].append(name)
                if p.get("extract"):
                    cur["lead"] = p["extract"]
            cont = data.get("continue")
            if not cont:
                break
            params.update({k: v for k, v in cont.items()})
        by_title = {p["title"]: p for p in pages.values()}
        out: Dict[str, Dict[str, Any]] = {}
        for t in titles:
            n = normalized.get(t, t)
            n = redirects.get(n, n)
            p = by_title.get(n)
            if not p or p.get("missing"):
                out[t] = {"exists": False, "title": n}
            else:
                out[t] = {"exists": True, "title": p["title"],
                          "url": p.get("url") or f"https://{lang}.wikipedia.org/wiki/{p['title'].replace(' ', '_')}",
                          "coords": p.get("coords"), "categories": p.get("categories", []),
                          "lead": p.get("lead", "")}
        return out


# ═════════════════════════════════════════════════════════════════════════════
# region names
# ═════════════════════════════════════════════════════════════════════════════
_LEAD_PREFIX = re.compile(r"^(history|economy|geography|culture|demographics|politics|transport|"
                          r"transportation|cuisine)\s+of\s+(the\s+)?", re.I)


def region_names(region: Dict[str, Any]) -> List[str]:
    """Distinct folded names: display name parts, seed titles (minus the region's
    ``generic_seeds``), and the region's ``aliases``."""
    names: List[str] = []
    disp = region.get("display_name", "")
    for part in re.split(r"[/()]", disp):
        part = part.split(",")[0].strip()          # 'Boston, Massachusetts' -> 'Boston'
        if part:
            names.append(part)
    generic = {fold(g) for g in region.get("generic_seeds", [])}
    for lang_titles in (region.get("seed_articles") or {}).values():
        for t in lang_titles:
            t = t.split(":", 1)[1] if t.lower().startswith("voyage:") else t
            t = _LEAD_PREFIX.sub("", t).split(",")[0].strip()
            if t and fold(t) not in generic:
                names.append(t)
    names += list(region.get("aliases", []))
    out, seen = [], set()
    for n in names:
        f = fold(n).strip()
        if len(f) >= 3 and f not in seen:
            seen.add(f)
            out.append(f)
    return out


def count_mentions(text: str, names: List[str]) -> int:
    f = fold(text)
    total = 0
    for n in names:
        total += len(re.findall(r"(?<![^\W_])" + re.escape(n) + r"(?![^\W_])", f))
    return total


def lead_and_sections_text(article_text: str, n_sections: int = MENTION_SECTIONS) -> str:
    """Lead + the first ``n_sections`` top-level sections of a full explaintext article."""
    ms = list(re.finditer(r"(?m)^==\s*[^=].*?==\s*$", article_text or ""))
    if len(ms) <= n_sections:
        return article_text or ""
    return article_text[:ms[n_sections].start()]


# ═════════════════════════════════════════════════════════════════════════════
# exclusions
# ═════════════════════════════════════════════════════════════════════════════
_TITLE_EXCLUDE = re.compile(
    r"^(list|lists|outline|index|timeline|glossary|template|category|portal|wikipedia|help|file)\b"
    r"|\(disambiguation\)|\bdisambiguation\b|^\d{4}\b.*\b(election|season)\b", re.I)

_CAT_EXCLUDE = re.compile(
    r"\bdisambiguation\b|^lists? of\b|\blists\b|\bpublishing companies\b|\bpublishers\b|"
    r"\bbook publishers\b|\bnewspapers?\b|\bmagazines?\b|\bperiodicals\b|\btelevision (networks?|channels?|"
    r"stations?|series)\b|\bradio stations?\b|\bnews agencies\b|\bmedia companies\b|"
    r"\bbroadcasting companies\b|\bwebsites\b|"
    r"^(?!.*\b(venues|players|seasons|stadiums|coaches|people)\b).*\bsports leagues?\b|"
    r"^(?!.*\b(venues|players|seasons|stadiums|coaches|people)\b)(?:\w+ )*(basketball|football|baseball|"
    r"hockey|soccer|rugby|cricket|volleyball) (leagues?|competitions?)\b|"
    r"\bacademic publishing\b|\bscholarly\b|\bterroris|\bmass (shootings?|murders?)\b|\bstabbings?\b|"
    r"\battacks? in\b|\bmurder\b",
    re.I)

_CAT_WHOLE_PLACE = re.compile(
    r"^(countries|sovereign states|member states|states and territories|capitals|"
    r"metropolitan areas|megacities|world cities|global cities|former countries|"
    r"countries and territories|island countries|republics|monarchies|regions|provinces)\b|"
    r"\b(cities|towns|villages|communes|municipalities|county seats|populated places|"
    r"census-designated places|former countries|disestablished states)\b|"
    r"\bstates and territories\b", re.I)
_BIOGRAPHY_CAT = re.compile(r"\b\d{3,4} (births|deaths)\b|^(living people|people from|writers from|"
                            r"scientists from|musicians from)\b", re.I)


def excluded_kind(title: str, categories: List[str]) -> Optional[str]:
    if _TITLE_EXCLUDE.search(title or ""):
        return "list/disambiguation"
    for c in categories:
        if _CAT_EXCLUDE.search(c):
            return f"category '{c}'"
    return None


def is_list_or_disambiguation(meta: Dict[str, Any]) -> bool:
    return bool(_TITLE_EXCLUDE.search(meta.get("title", "")) or
                any(re.search(r"disambiguation|^lists? of\b", c, re.I) for c in meta.get("categories", [])))


_PEOPLE_GROUP_CAT = re.compile(r"\b(ethnic groups|ethnic minorities|indigenous peoples)\b", re.I)


def is_biography(categories: List[str]) -> bool:
    return any(_BIOGRAPHY_CAT.search(c) for c in categories)


def whole_place_category(categories: List[str], names: Optional[List[str]] = None) -> Optional[str]:
    """A category that says the page is about some whole country / city / town. A category
    that itself names the region ('Towns in Bình Thuận province') does not count."""
    for c in categories:
        if _CAT_WHOLE_PLACE.search(c) and not (names and count_mentions(c, names)):
            return c
    return None


def title_excluded(title: str) -> bool:
    """Cheap pre-filter on the bare title (before any lookup)."""
    return bool(_TITLE_EXCLUDE.search(title or ""))


# ═════════════════════════════════════════════════════════════════════════════
# LOCAL-907C: the category rule counts only the region's OWN categories
# ═════════════════════════════════════════════════════════════════════════════
# Facets under which "<facet> of/in/from <region>" is a category ABOUT the region.
_OWN_PREFIX = re.compile(
    r"^(history|economy|economic history|geography|culture|cultures|demographics|politics|"
    r"politics and government|government|transport|transportation|cuisine|foods?|food and drink|"
    r"drinks?|architecture|education|people|religion|tourism|society|folklore|"
    r"buildings and structures|landmarks|tourist attractions|museums|museums and galleries|"
    r"monuments and memorials|parks|beaches|bridges|streets|neighbou?rhoods|music|arts|"
    r"cultural heritage|sport|sports|geology|climate|ecology|economy and industry)$")
_OWN_SUFFIX = r"(history|culture|cuisine|economy|architecture|folklore|people|geography|demographics)"


def own_category(category: str, names: List[str]) -> bool:
    """True if ``category`` has the region (a display name / alias) as its SUBJECT, e.g.
    'History of Nice', 'People from Boston', 'Foods of Test Province', or just 'Nice'. A category
    that merely sits inside a broader region ('Islands of <Region>-<Other>', 'Films set in
    <region>', 'Gorges of the <region>') does not count, and neither does a name that is
    only a piece of a longer hyphenated proper name ('Provence-Alpes-Côte d'Azur')."""
    f = fold(category).strip()
    for n in names:
        if n not in f:
            continue
        ne = re.escape(n)
        edge = r"(?<![^\W_])" + ne + r"(?![^\W_-])(?<!-)"
        if re.match(r"^" + ne + r"(?![^\W_-])(\s*,.*|\s*\(.*\))?$", f):
            return True                                          # 'Boston', 'Boston, Massachusetts'
        if re.match(r"^" + ne + r"\s+" + _OWN_SUFFIX + r"$", f):
            return True                                          # 'Nice culture'
        m = re.match(r"^(?P<prefix>.*?)\s*\b(?:of|in|from)\s+(?:the\s+)?" + ne
                     + r"(?![^\W_-])(\s*,.*|\s*\(.*\))?$", f)
        if m and _OWN_PREFIX.match(m.group("prefix").strip()):
            # not the tail of a longer hyphenated name
            i = f.find(n)
            if not (i > 0 and f[i - 1] == "-"):
                return True
    return False


# ═════════════════════════════════════════════════════════════════════════════
# the gate
# ═════════════════════════════════════════════════════════════════════════════
def check_relevance(meta: Dict[str, Any], region: Dict[str, Any], *,
                    full_text: Optional[str] = None) -> Tuple[bool, str, str]:
    """(ok, reason, scores). reason is one of coord / mentions / category on success, else
    'excluded: ...' / 'off-region' / 'mentions-pending' (1-2 lead mentions: needs the full
    article's first sections to decide). ``full_text`` = the full article text when known."""
    title = meta.get("title", "")
    cats = meta.get("categories", [])
    ex = excluded_kind(title, cats)
    if ex:
        return False, f"excluded: {ex}", ex
    names = region_names(region)
    centre = region["centre"]
    coords = meta.get("coords")
    dist = None
    if coords:
        dist = tl.haversine_km(centre["lat"], centre["lng"], coords[0], coords[1])
    if text_present(full_text):
        mention_text, src = lead_and_sections_text(full_text), "lead+2 sections"
    else:
        mention_text, src = meta.get("lead", ""), "lead"
    mentions = count_mentions(mention_text, names)
    cat_hit = next((c for c in cats if own_category(c, names)), None)
    scores = (f"coords={'%.0fkm' % dist if dist is not None else 'none'} "
              f"(radius {region['radius_km']}km), mentions[{src}]={mentions} (need {MIN_MENTIONS}), "
              f"category={'yes' if cat_hit else 'no'}")
    whole = whole_place_category(cats, names)
    if whole:
        return False, f"excluded: whole country/city page (category '{whole}')", scores
    if dist is not None and dist <= region["radius_km"]:
        return True, "coord", scores
    if dist is not None and dist > 2 * region["radius_km"]:
        # placed far outside the region on the map: a passing mention or a broad category
        # ('Alps', a gorge two hours away) does not make it a topic of this region
        return False, "off-region", scores
    if any(re.search(t, fold(title)) for t in region.get("exclude_title_terms", [])):
        return False, "excluded: page about the wider country", scores
    if is_biography(cats):
        return False, "excluded: biography (needs coordinates or a hint)", scores
    if _PEOPLE_GROUP_CAT.search(" | ".join(cats)) and not cat_hit:
        return False, "excluded: people group of a wider area (needs coordinates or a hint)", scores
    if dist is not None:
        # LOCAL-907C: located, but outside the region -> only the region's own category can still
        # make it a topic (a reservoir shared by three provinces is not 'about' the city)
        if cat_hit and dist <= 1.5 * region["radius_km"]:
            return True, "category", scores
        return False, "off-region", scores
    words = max(1, len(mention_text.split()))
    if mentions >= MIN_MENTIONS and mentions * 1000.0 / words >= MIN_MENTION_DENSITY:
        return True, "mentions", scores
    if cat_hit:
        return True, "category", scores
    if not text_present(full_text) and 0 < mentions < MIN_MENTIONS:
        return False, "mentions-pending", scores
    return False, "off-region", scores


def text_present(t: Optional[str]) -> bool:
    return bool(t and t.strip())


# ═════════════════════════════════════════════════════════════════════════════
# theme from the article's own lead + categories
# ═════════════════════════════════════════════════════════════════════════════
ARTICLE_CUES: Dict[str, List[str]] = {
    "history": ["history", "historical", "historic", "kingdom", "dynasty", "empire", "war", "wars",
                "battle", "siege", "colonial", "ancient", "medieval", "revolution", "conquest",
                "massacre", "treaty", "archaeology", "archaeological", "prehistoric", "era",
                "occupation", "independence", "ruins", "civilisation", "civilization"],
    "modern": ["government", "administration", "administrative", "municipal", "politics", "political",
               "province", "districts", "subdivisions", "census", "demographics", "urban",
               "skyline", "development", "reform", "university", "universities", "mayor",
               "city council", "neighbourhoods", "neighborhoods", "suburbs", "infrastructure"],
    "people_economy": ["economy", "economic", "industry", "industries", "agriculture", "fishing",
                       "fisheries", "fishery", "tourism", "trade", "business", "companies", "employment",
                       "ethnic group", "ethnic groups", "population", "farming", "fruit", "crops",
                       "manufacturing", "finance", "labour", "labor", "commerce", "aquaculture",
                       "economy of", "workers", "biotechnology", "shipbuilding", "mining"],
    "religion_customs": ["religion", "religious", "church", "churches", "temple", "temples", "pagoda",
                         "buddhism", "buddhist", "hinduism", "hindu", "christianity", "catholic",
                         "islam", "islamic", "mosque", "festival", "festivals", "custom", "customs",
                         "tradition", "worship", "ritual", "rituals", "cathedral", "synagogue",
                         "caodaism", "shrine", "carnival", "holiday", "holidays", "cult", "monastery",
                         "jewish", "protestant", "faith", "pilgrimage"],
    "food": ["cuisine", "food", "foods", "dish", "dishes", "drink", "drinks", "wine", "wines",
             "cooking", "culinary", "sauce", "sauces", "seafood", "soup", "bread", "cheese",
             "restaurant", "restaurants", "bakery", "coffee", "beer", "condiment", "condiments",
             "fruit", "pastry", "dessert", "snack", "cocktail", "olive"],
    "transport": ["transport", "transportation", "railway", "railways", "rail", "road", "roads",
                  "highway", "highways", "bridge", "bridges", "airport", "airports", "harbour",
                  "harbor", "ferry", "ferries", "trolley", "tram", "trams", "metro", "subway",
                  "tunnel", "station", "stations", "bus", "buses", "shipping", "expressway",
                  "lighthouse", "lighthouses", "port", "cruise", "freeway", "commuter"],
    "nature": ["geography", "climate", "geology", "wildlife", "park", "parks", "beach", "beaches",
               "coast", "coastal", "river", "rivers", "mountain", "mountains", "dune", "dunes",
               "lake", "lakes", "forest", "flora", "fauna", "island", "islands", "bay", "desert",
               "species", "ecology", "nature reserve", "bird", "birds", "marine", "canyon",
               "estuary", "wetland", "wetlands", "hills", "peninsula", "waterfall", "ocean"],
    "legends": ["legend", "legends", "myth", "myths", "mythology", "folklore", "folktale", "folk tale",
                "ghost", "ghosts", "deity", "deities", "goddess", "supernatural", "epic", "hero",
                "haunted", "legendary", "fairy tale", "oral tradition"],
    "arts": ["art", "arts", "artist", "artists", "architecture", "architectural", "music", "museum",
             "museums", "theatre", "theater", "literature", "film", "films", "cinema", "gallery",
             "sculpture", "sculptures", "painting", "paintings", "dance", "poet", "poets", "novel",
             "culture", "cultural", "film festival", "book festival", "literary festival", "jazz festival", "music festival", "jazz", "concert", "musical", "opera", "painter", "painters", "heritage",
             "cultural heritage", "orchestra", "monument", "monuments", "cultural"],
}
MIN_THEME_SCORE = 4
MIN_THEME_MARGIN = 2
SETTLEMENT_CUES = ["town", "city", "suburb", "district", "commune", "village", "neighbourhood",
                   "neighborhood", "municipality", "ward", "borough", "campus", "institute",
                   "college", "company", "corporation", "hospital", "tower", "hotel"]
EVENT_CUES = ["attack", "assassination", "massacre", "siege", "battle", "uprising", "coup", "trial"]


def _cue_hits(text: str, cues: List[str]) -> int:
    f = fold(text)
    return sum(1 for c in cues if re.search(r"(?<![^\W_])" + re.escape(c) + r"(?![^\W_])", f))


def classify_article(title: str, lead: str, categories: List[str]) -> Optional[str]:
    return classify_scored(title, lead, categories)[0]


HINT_OVERRIDE_MARGIN = 6    # LOCAL-907C: a hint's editorial theme yields only to a clear verdict


def classify_scored(title: str, lead: str, categories: List[str]) -> Tuple[Optional[str], int]:
    """(theme or None, margin of the winner over the runner-up). A forced kind (festival,
    venue, lighthouse, ski resort) has an unbounded margin."""
    """Theme for an article from its own title (x2), categories (x3 each category that hits),
    its first sentence (x3 per cue: it says what the article IS) and the rest of the first
    ~100 words of the lead (x1). Needs a clear winner (score >= MIN_THEME_SCORE and a margin
    over the runner-up); otherwise None: an unclear article is dropped rather than put under
    a wrong theme."""
    forced = kind_theme(title, lead, categories)
    if forced:
        return forced, 99
    words = (lead or "").split()
    lead100 = " ".join(words[:100])
    m = re.search(r"[.!?](\s|$)", lead100)
    first = lead100[:m.end()] if m else lead100
    scores: Dict[str, int] = {}
    for theme in tl.THEMES:
        cues = ARTICLE_CUES[theme]
        s = 2 * _cue_hits(title, cues) + _cue_hits(lead100, cues) + 3 * _cue_hits(first, cues)
        s += 3 * sum(1 for c in categories if _cue_hits(c, cues))
        scores[theme] = s
    # what the subject IS: a settlement / institution / building is a "modern" topic, an
    # event is "history" -- unless a stronger theme cue already says otherwise
    scores["modern"] += 3 * _cue_hits(first, SETTLEMENT_CUES) + 3 * (
        1 if any(re.search(r"\b(cities|towns|suburbs|districts|wards|communes|universit|colleges|"
                           r"companies|neighbou?rhoods)\b", fold(c)) for c in categories) else 0)
    scores["history"] += 6 * _cue_hits(first, EVENT_CUES)
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], tl.THEMES.index(kv[0])))
    (best, bs), (_second, ss) = ranked[0], ranked[1]
    if bs < MIN_THEME_SCORE or bs - ss < MIN_THEME_MARGIN:
        return None, bs - ss
    return best, bs - ss


# ═════════════════════════════════════════════════════════════════════════════
# LOCAL-907C: would a guide talk about it for 10+ minutes?  (generic, no place names)
# ═════════════════════════════════════════════════════════════════════════════
SMALL_PLACE_WORDS = 3000        # a commune / village / ward / neighbourhood article shorter than this
                                # (LEAD asked ~1,500; the cited offenders run 1,600-2,700 words)
SMALL_PLACE_POPULATION = 20000  # ... or stating a population below this, is a minor place

# (reason, category regex, first-sentence regex).  Applied to gated LINKED articles only.
_KIND_RULES: List[Tuple[str, "re.Pattern", "re.Pattern"]] = [
    ("school", re.compile(r"\b(schools?|high schools|academies|kindergartens)\b", re.I),
     re.compile(r"\bis an? [^.]{0,60}?\b(school|academy)\b", re.I)),
    ("university/college", re.compile(r"\b(universit(y|ies)|colleges?|institutes of technology)\b", re.I),
     re.compile(r"\bis an? [^.]{0,60}?\b(universit(y|ies)|college|institute)\b", re.I)),
    ("hotel", re.compile(r"\b(hotels?|motels?|hostels?)\b", re.I),
     re.compile(r"\bis an? [^.]{0,60}?\b(hotel|motel|hostel)\b", re.I)),
    ("restaurant", re.compile(r"\b(restaurants?|fast food|caf[eé]s?|coffeehouses|bars|nightclubs?)\b", re.I),
     re.compile(r"\b(is|was) an? [^.]{0,60}?\b(restaurants?|caf[eé]|bar|nightclub|restaurant chain)\b", re.I)),
    ("company", re.compile(r"\b(companies|brands|retailers|banks|airlines|corporations|"
                           r"conglomerates|manufacturers|supermarkets|shopping (malls?|cent(er|re)s?))\b", re.I),
     re.compile(r"\bis an? [^.]{0,60}?\b(company|corporation|conglomerate|brand|retailer|chain|"
                r"shopping (mall|cent(er|re)))\b", re.I)),
    ("organisation", re.compile(r"\b(non-profit organi[sz]ations|student organi[sz]ations|"
                                r"volunteer organi[sz]ations|charities)\b", re.I),
     re.compile(r"\bis an? [^.]{0,40}?\b(non-?profit|charity|charitable|student|volunteer)\b[^.]{0,30}?"
                r"organi[sz]ation\b", re.I)),
    ("other administrative division", re.compile(r"\bformer provinces\b", re.I),
     re.compile(r"\bis an? [^.]{0,30}?\b(province|d[eé]partement|department|county|prefecture|state)\b"
                r"[^.]{0,20}?\b(of|in)\b", re.I)),
    ("convention centre", re.compile(r"\b(convention|exhibition|conference) (and exhibition )?cent(er|re)s?\b", re.I),
     re.compile(r"\b(convention|exhibition|conference) (and exhibition )?cent(er|re)\b", re.I)),
    ("airfield", re.compile(r"\b(airfields|airports|airbases|air force bases|heliports)\b", re.I),
     re.compile(r"\bis an? [^.]{0,60}?\b(airfield|airport|air base|airbase|heliport)\b", re.I)),
    ("sports club/venue", re.compile(r"\b(sports (venues|clubs|teams|franchises)|stadiums|arenas|ballparks|"
                                     r"(football|baseball|basketball|hockey|soccer|rugby|cricket) (clubs|teams|venues)|"
                                     r"racecourses|race tracks|golf (clubs|courses))\b", re.I),
     re.compile(r"\bis an? [^.]{0,60}?\b(stadium|ballpark|arena|(football|baseball|basketball|hockey|"
                r"soccer|rugby|cricket) (club|team)|racecourse|golf course|sports club)\b", re.I)),
    ("film/TV/album/song/book", re.compile(r"\b(films?|television (series|shows|programs?|films)|albums|songs|singles|"
                                           r"novels|books|video games|musicals|plays|comics|anime|"
                                           r"documentary films)\b", re.I),
     re.compile(r"\bis an? [^.]{0,60}?\b(film|movie|television series|tv series|album|song|single|novel|"
                r"book|video game|musical|play|documentary)\b", re.I)),
    ("festival", re.compile(r"\b(festivals?|annual events|fairs|conventions)\b", re.I),
     re.compile(r"\bis an? [^.]{0,60}?\b(festival|fair|convention)\b", re.I)),
]
_SMALL_PLACE_CAT = re.compile(r"\b(communes?|villages|hamlets|neighbou?rhoods|suburbs|localities|"
                              r"census-designated places|unincorporated communities|former communes|wards of|wards in)\b", re.I)
_SMALL_PLACE_LEAD = re.compile(r"\bis an? [^.]{0,60}?\b(commune|village|hamlet|neighbou?rhood|suburb|"
                               r"locality|settlement|ward|planned community|urban area|residential (area|district)|"
                               r"(shopping|commercial|business) district)\b", re.I)
_POP_RE = re.compile(r"\bpopulation (?:of|was|is|stood at|totall?ed)?\s*(?:about|approximately|around|roughly)?\s*"
                     r"(\d[\d,.\u202f ]*\d|\d)(\s+million)?|"
                     r"\b(\d[\d,.]*\d|\d)(\s+million)?\s+(?:inhabitants|residents)\b", re.I)


def first_sentence(lead: str) -> str:
    words = (lead or "").split()
    l100 = " ".join(words[:100])
    m = re.search(r"[.!?](\s|$)", l100)
    return l100[:m.end()] if m else l100


def stated_population(lead: str) -> Optional[int]:
    """Population figure stated in the lead (None when absent)."""
    m = _POP_RE.search(lead or "")
    if not m:
        return None
    num = m.group(1) or m.group(3)
    mil = m.group(2) or m.group(4)
    try:
        v = float(num.replace(",", "").replace("\u202f", "").replace(" ", ""))
    except ValueError:
        return None
    return int(v * 1_000_000) if mil else int(v)


def is_small_place_kind(meta: Dict[str, Any]) -> bool:
    return bool(any(_SMALL_PLACE_CAT.search(c) for c in meta.get("categories", []))
                or _SMALL_PLACE_LEAD.search(first_sentence(meta.get("lead", ""))))


def not_guide_worthy(meta: Dict[str, Any]) -> Optional[str]:
    """Reason a gated LINKED article is not something a guide would talk about for 12 minutes
    (school, hotel, film, company, ...), else None. Hints and seeds are exempt (the caller)."""
    cats = meta.get("categories", [])
    first = first_sentence(meta.get("lead", ""))
    for reason, cat_re, lead_re in _KIND_RULES:
        if any(cat_re.search(c) for c in cats) or lead_re.search(first):
            return reason
    if is_small_place_kind(meta):
        pop = stated_population(meta.get("lead", ""))
        if pop is not None and pop < SMALL_PLACE_POPULATION:
            return f"minor place (population {pop})"
    return None


def small_place_by_size(meta: Dict[str, Any], words: int) -> Optional[str]:
    if is_small_place_kind(meta) and words < SMALL_PLACE_WORDS:
        return f"minor place ({words} words)"
    return None


# ── seed sections a guide would not talk about ──────────────────────────────
_SECTION_DENY_WORDS = {"funding", "finance", "budget", "governance", "politics", "government",
                       "elections", "future", "facilities", "ridership", "fleet", "references"}
_SECTION_DENY_AGENCY_WORDS = {"management", "administration"}
_SECTION_DENY_PHRASES = ("proposed extension", "see also")
_AGENCY_TITLE = re.compile(r"\b(authority|agency|commission|department|trolley|transit|railway|railroad|"
                           r"corporation|company|board|port of|bureau|service|system)\b", re.I)


def section_denied(article_title: str, heading: str) -> Optional[str]:
    """Reason a seed article's section is dropped (a dull institutional section), else None.
    Management / Administration are denied only for an agency-like article, never for a place."""
    h = fold(heading)
    for ph in _SECTION_DENY_PHRASES:
        if ph in h:
            return f"section '{heading}'"
    words = set(re.findall(r"[^\W_]+", h))
    if words & _SECTION_DENY_WORDS:
        return f"section '{heading}'"
    if words & _SECTION_DENY_AGENCY_WORDS and _AGENCY_TITLE.search(article_title or ""):
        return f"section '{heading}'"
    return None


# ── theme fallbacks from what the article IS ───────────────────────────────
_RELIGIOUS_LEAD = re.compile(r"\b(religio\w*|worship\w*|buddhis\w*|christian\w*|catholic|saint|holy|sacred|"
                             r"pilgrim\w*|ritual\w*|ancestor\w*|goddess|deity|lent|lenten|pagoda|temple|church|"
                             r"mosque|new year)\b", re.I)
_FESTIVAL_FIRST = re.compile(r"\b(festival|carnival|f[eê]te|feria|parade|fair|annual event)\b", re.I)
_TRADE_FAIR = re.compile(r"\b(trade|fair|market|expo|exhibition|harvest|agricultur\w*)\b", re.I)
_VENUE_FIRST = re.compile(r"\b(stadium|ballpark|baseball park|arena|sports venue|racecourse|race track|"
                          r"golf course|football ground)\b", re.I)
_LIGHTHOUSE_FIRST = re.compile(r"\b(lighthouse|landmark)\b", re.I)
_LEGEND_LEAD = re.compile(r"\b(haunted|ghosts?|legends?|legendary|myths?|folklore|ghost stor\w+|curse)\b", re.I)
_SKI_FIRST = re.compile(r"\b(ski resort|ski area|skiing resort|ski station)\b", re.I)


def kind_theme(title: str, lead: str, categories: List[str]) -> Optional[str]:
    """Theme forced by what the subject IS (festival, sports venue, lighthouse, ski resort)."""
    first = first_sentence(lead)
    cats = " | ".join(categories)
    if _SKI_FIRST.search(first) or re.search(r"\bski resorts\b", cats, re.I):
        return "nature"
    if _VENUE_FIRST.search(first) or re.search(r"\b(stadiums|ballparks|sports venues|arenas)\b", cats, re.I):
        return "people_economy"
    if _FESTIVAL_FIRST.search(first) or re.search(r"\bfestivals\b", cats, re.I):
        if _RELIGIOUS_LEAD.search(first) or re.search(r"\b(religio\w*|holidays?|observances)\b", cats, re.I):
            return None                      # a religious festival: let the classifier decide
        return "people_economy" if _TRADE_FAIR.search(first) else "arts"
    if _LIGHTHOUSE_FIRST.search(first) or re.search(r"\blighthouses\b", cats, re.I):
        return "legends" if _LEGEND_LEAD.search(lead or "") else "history"
    return None


def reconcile_hint_theme(editorial: Optional[str], classified: Optional[str],
                         margin: int = 99) -> Optional[str]:
    """A hint keeps its editorial theme when the classifier agrees or is unsure (no verdict, or
    a margin below HINT_OVERRIDE_MARGIN)."""
    if editorial and (classified is None or classified == editorial or margin < HINT_OVERRIDE_MARGIN):
        return editorial
    return classified or editorial
