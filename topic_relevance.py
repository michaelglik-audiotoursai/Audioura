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
    cat_hit = next((c for c in cats if count_mentions(c, names)), None)
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
    """Theme for an article from its own title (x2), categories (x3 each category that hits),
    its first sentence (x3 per cue: it says what the article IS) and the rest of the first
    ~100 words of the lead (x1). Needs a clear winner (score >= MIN_THEME_SCORE and a margin
    over the runner-up); otherwise None: an unclear article is dropped rather than put under
    a wrong theme."""
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
        return None
    return best
