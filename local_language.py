"""local_language.py — LOCAL-875 / D768: the tour's LOCAL LANGUAGE, decided at
run time from WHERE the tour takes place, and the three things that depend on it.

Michael (2026-11-06): "what about Chinese, French, Spanish, Russian, etc. We
have to come up with local language definitions in real time depending where the
tour actually takes place."

This module answers four questions, all keyed on the tour's resolved location:

  1. ``languages_for(city_or_coords)`` -> a list of BCP-47 language codes, e.g.
     ``["vi"]`` (Ho Chi Minh City), ``["zh-Hant"]`` (Taipei), ``["fr"]`` (Paris),
     ``["ca", "es"]`` (Barcelona), ``["ru"]`` (Moscow), ``["fr"]`` (Montréal).
     Source, in order: the resolved city's COUNTRY (the 863R curated table, then
     Nominatim ``country_code``), then the country's Wikidata official / common
     languages (P37 / P2936); regional cases (Quebec, Catalonia, Hong Kong) are
     applied on top. Cached in the DB table ``local_language_cache``.

  2. ``classify_place(name, ...)`` — the language-FREE classification order the
     task asks for: Wikidata P31 Q-id first (``P31_SUBTYPE``, >= 10 QIDs), then
     Google Places types, then name words. Thin wrapper over
     ``place_kinds.classify`` (D767), which already threads these signals in this
     order; this module adds the explicit, documented P31 Q-id map and the
     ``classify_place`` entry point the escalation path calls.

  3. ``kind_words(lang)`` — on first use for a language, ONE cheap LLM call
     (gpt-4.1-mini, temperature 0, JSON) returns the LOCAL words for every D767
     subtype, ``street_area`` and the business list. Stored forever in
     ``place_kind_words``; never regenerated unless missing. English + Vietnamese
     ship as FIXTURES (from ``place_kinds``), so those two never cost a call.
     Logs ``[LOCAL-875] kind words generated for <lang> (N words)``.

  4. Research in the local language:
       * ``local_wikipedia_evidence`` — the Wikipedia LOCAL edition for a stop, in
         addition to en (reuses ``landmark_wikipedia_evidence``);
       * ``serper_local_queries`` — Serper queries with the stop's LOCAL name
         (Wikidata label in that language) plus local kind words, and ``gl``/``hl``
         set to the country;
       * ``local_alias`` — the local-language name kept as an alias on the stop.
     ``escalate_local_language`` is the single helper LOCAL-873's thin-stop
     escalation calls; it returns all of the above in one bundle.

Everything is injectable (``fetch`` callables, ``llm``), so the module unit-tests
OFFLINE and makes NO network / DB / paid call unless a real backend is wired in.
Pure helpers never raise.
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import city_scope
import place_kinds

__all__ = [
    "languages_for", "local_language", "P31_SUBTYPE", "classify_place",
    "kind_words", "seed_kind_words", "local_wikipedia_evidence",
    "serper_local_queries", "local_alias", "escalate_local_language",
    "country_gl_hl", "wikidata_languages_for_country",
]

# ── Logging (stdout, like the rest of the pipeline) ───────────────────────────
def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# 1. languages_for — the tour's local language(s)
# ═══════════════════════════════════════════════════════════════════════════

# Country (ISO-2, lower) -> ordered BCP-47 language codes. This is the ANSWER
# the whole feature turns on: the local language depends on the country, not on
# a per-city guess. Ordered so the FIRST entry is the dominant local language.
# Script subtags (zh-Hant / zh-Hans) distinguish Taiwan/Hong Kong (Traditional)
# from the mainland (Simplified), which the task requires (Taipei -> zh-Hant).
COUNTRY_LANGUAGES: Dict[str, List[str]] = {
    "vn": ["vi"],
    "fr": ["fr"],
    "es": ["es"],          # Catalonia / Basque / Galicia handled as regional cases
    "it": ["it"],
    "de": ["de"],
    "at": ["de"],
    "ch": ["de", "fr", "it"],
    "pt": ["pt"],
    "br": ["pt"],
    "ru": ["ru"],
    "ua": ["uk", "ru"],
    "jp": ["ja"],
    "kr": ["ko"],
    "kp": ["ko"],
    "th": ["th"],
    "kh": ["km"],
    "cn": ["zh-Hans"],
    "tw": ["zh-Hant"],
    "hk": ["zh-Hant", "en"],   # yue is spoken; the WRITTEN edition is zh / zh-yue
    "mo": ["zh-Hant", "pt"],
    "sg": ["en", "zh-Hans", "ms", "ta"],
    "nl": ["nl"],
    "be": ["nl", "fr"],
    "gb": ["en"],
    "us": ["en"],
    "ca": ["en", "fr"],        # Quebec handled as a regional case -> fr first
    "ie": ["en", "ga"],
    "gr": ["el"],
    "tr": ["tr"],
    "pl": ["pl"],
    "cz": ["cs"],
    "hu": ["hu"],
    "se": ["sv"],
    "no": ["no"],
    "dk": ["da"],
    "fi": ["fi", "sv"],
    "mx": ["es"],
    "ar": ["es"],
    "in": ["hi", "en"],
    "id": ["id"],
    "ph": ["en", "tl"],
    "eg": ["ar"],
    "ma": ["ar", "fr"],
    "il": ["he"],
    "sa": ["ar"],
    "ae": ["ar", "en"],
}

# Wikidata language QID -> BCP-47 code (P37 official / P2936 used-language values).
LANG_QID: Dict[str, str] = {
    "Q1860": "en", "Q150": "fr", "Q1321": "es", "Q652": "it", "Q188": "de",
    "Q5146": "pt", "Q7737": "ru", "Q8798": "uk", "Q5287": "ja", "Q9176": "ko",
    "Q9217": "th", "Q9199": "km", "Q7850": "zh", "Q18130": "zh-Hant",
    "Q13414913": "zh-Hant", "Q7850_hans": "zh-Hans", "Q7411": "nl", "Q9240": "id",
    "Q9168": "tl", "Q9129": "el", "Q256": "tr", "Q809": "pl", "Q9056": "cs",
    "Q9067": "hu", "Q9027": "sv", "Q9043": "no", "Q9035": "da", "Q1412": "fi",
    "Q7918": "vi", "Q13955": "ar", "Q9288": "he", "Q1568": "hi", "Q7026": "ca",
    "Q8752": "eu", "Q9307": "gl", "Q9142": "yue", "Q25164": "ga",
}

# Regional cases that override the country default (D768). Matched on the
# resolved region/state name OR an alias in the request, accent-folded.
# (region alias tuple) -> ordered languages that REPLACE the country default.
_REGIONAL: List[Tuple[Tuple[str, ...], List[str]]] = [
    (("quebec", "québec", "montreal", "montréal", "quebec city", "ville de quebec",
      "gatineau", "laval", "sherbrooke", "trois rivieres"), ["fr"]),
    (("catalonia", "cataluña", "catalunya", "barcelona", "girona", "tarragona",
      "lleida", "sabadell", "badalona"), ["ca", "es"]),
    (("basque country", "pais vasco", "euskadi", "bilbao", "san sebastian",
      "donostia", "vitoria", "gasteiz"), ["eu", "es"]),
    (("galicia", "santiago de compostela", "vigo", "a coruna", "coruña"),
     ["gl", "es"]),
    (("hong kong", "hongkong", "kowloon", "victoria harbour"), ["zh-Hant", "en"]),
    (("macau", "macao"), ["zh-Hant", "pt"]),
]


# Well-known tour cities the 863R curated table does not carry, mapped to their
# ISO-2 country. Consulted AFTER the curated table and the request's named
# country, but BEFORE Nominatim — so an offline run (no ``fetch``) still resolves
# the country for a major city, and a live run that reaches Nominatim agrees.
# Folded whole-word aliases.
_CITY_COUNTRY: Dict[str, str] = {
    "taipei": "tw", "taichung": "tw", "kaohsiung": "tw", "tainan": "tw",
    "moscow": "ru", "saint petersburg": "ru", "st petersburg": "ru",
    "petersburg": "ru", "kazan": "ru", "sochi": "ru",
    "tokyo": "jp", "kyoto": "jp", "osaka": "jp", "nara": "jp",
    "seoul": "kr", "busan": "kr",
    "bangkok": "th", "chiang mai": "th",
    "beijing": "cn", "shanghai": "cn", "guangzhou": "cn", "chengdu": "cn",
    "hong kong": "hk", "macau": "hk",
    "berlin": "de", "munich": "de", "hamburg": "de", "cologne": "de",
    "vienna": "at", "salzburg": "at",
    "zurich": "ch", "geneva": "ch", "bern": "ch",
    "rome": "it", "venice": "it", "florence": "it", "milan": "it", "naples": "it",
    "madrid": "es", "seville": "es", "valencia": "es",
    "barcelona": "es", "girona": "es",  # Catalonia handled by regional override
    "lisbon": "pt", "porto": "pt",
    "athens": "gr", "thessaloniki": "gr",
    "istanbul": "tr", "ankara": "tr",
    "amsterdam": "nl", "rotterdam": "nl", "the hague": "nl", "utrecht": "nl",
    "brussels": "be", "antwerp": "be", "bruges": "be",
    "london": "gb", "edinburgh": "gb", "manchester": "gb",
    "dublin": "ie",
    "lyon": "fr", "marseille": "fr", "bordeaux": "fr", "strasbourg": "fr",
    "montreal": "ca", "quebec": "ca", "toronto": "ca", "vancouver": "ca",
    "ottawa": "ca",
    "warsaw": "pl", "krakow": "pl",
    "prague": "cz", "budapest": "hu",
    "stockholm": "se", "oslo": "no", "copenhagen": "dk", "helsinki": "fi",
    "mexico city": "mx", "buenos aires": "ar",
    "cairo": "eg", "marrakech": "ma", "jerusalem": "il", "tel aviv": "il",
    "dubai": "ae", "abu dhabi": "ae",
    "singapore": "sg", "jakarta": "id", "bali": "id", "manila": "ph",
    "mumbai": "in", "delhi": "in", "new delhi": "in",
}


def _fold(text) -> str:
    return city_scope.fold(text)


def _augmented_city_country(*texts) -> Optional[str]:
    """ISO-2 for a well-known tour city named in ``texts`` that the curated table
    lacks (Taipei, Moscow, Tokyo…). Longest alias wins. None when none match."""
    best, best_len = None, 0
    for t in texts:
        ft = _fold(t)
        if not ft:
            continue
        for alias, cc in _CITY_COUNTRY.items():
            if len(alias) > best_len and re.search(
                    r"(?:^| )" + re.escape(alias) + r"(?: |$)", ft):
                best, best_len = cc, len(alias)
    return best


def _regional_override(*texts) -> Optional[List[str]]:
    """The languages for a region named in the request, overriding the country
    default (Quebec -> fr; Catalonia -> ca+es; Hong Kong -> zh-Hant+en)."""
    folded = [_fold(t) for t in texts if t]
    for aliases, langs in _REGIONAL:
        for alias in aliases:
            if any(re.search(r"(?:^| )" + re.escape(alias) + r"(?: |$)", f)
                   for f in folded):
                return list(langs)
    return None


def _country_for(city_or_coords, *, fetch=None) -> Optional[str]:
    """ISO-2 country code for a location string (curated table first, then
    Nominatim via ``fetch``). Coordinates are passed straight to Nominatim
    reverse. Returns None when nothing resolves. Never raises."""
    # Coordinates: (lat, lng) tuple/list or "lat,lng"
    coords = _as_coords(city_or_coords)
    if coords is not None and fetch is not None:
        cc = _reverse_country(coords, fetch)
        if cc:
            return cc.lower()
    text = city_or_coords if isinstance(city_or_coords, str) else ""
    if text:
        # 1) requested country named in the text ("…, Vietnam", "Boston, MA")
        rc = city_scope.requested_country(text)
        # 2) curated city -> its country code
        cur = city_scope.find_curated_city(text)
        if cur and cur.get("country_code"):
            return cur["country_code"].lower()
        if rc:
            return rc.lower()
        # 2b) a well-known tour city the curated table lacks (offline-safe)
        aug = _augmented_city_country(text)
        if aug:
            return aug
        # 3) Nominatim forward geocode -> country_code
        if fetch is not None:
            scope = city_scope.resolve_city_scope(text, fetch=fetch, log=lambda *_: None)
            if scope and scope.get("country_code"):
                return str(scope["country_code"]).lower()
            cc = _forward_country(text, fetch)
            if cc:
                return cc.lower()
    return None


def _as_coords(v) -> Optional[Tuple[float, float]]:
    if isinstance(v, (tuple, list)) and len(v) == 2:
        try:
            return (float(v[0]), float(v[1]))
        except (TypeError, ValueError):
            return None
    if isinstance(v, str):
        m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", v)
        if m:
            return (float(m.group(1)), float(m.group(2)))
    return None


def _reverse_country(coords: Tuple[float, float], fetch) -> Optional[str]:
    try:
        rows = fetch({"lat": coords[0], "lon": coords[1], "format": "jsonv2",
                      "zoom": "5", "addressdetails": "1"}) or []
    except Exception:
        return None
    for row in (rows if isinstance(rows, list) else [rows]):
        if isinstance(row, dict):
            cc = (row.get("address") or {}).get("country_code") or row.get("country_code")
            if cc:
                return str(cc)
    return None


def _forward_country(text: str, fetch) -> Optional[str]:
    try:
        rows = fetch({"q": text, "format": "jsonv2", "limit": "1",
                      "addressdetails": "1", "accept-language": "en"}) or []
    except Exception:
        return None
    for row in (rows if isinstance(rows, list) else [rows]):
        if isinstance(row, dict):
            cc = (row.get("address") or {}).get("country_code") or row.get("country_code")
            if cc:
                return str(cc)
    return None


def wikidata_languages_for_country(country_qid: str, *, fetch=None) -> List[str]:
    """P37 (official language) + P2936 (language used) values of a country's
    Wikidata entity, mapped to BCP-47 codes, official first. ``fetch(qid)`` must
    return the wbgetentities JSON ``entities`` dict (or the full response). []
    when unresolved. Never raises — used only to ENRICH the country-table answer,
    never to override it."""
    if not country_qid or fetch is None:
        return []
    try:
        data = fetch(country_qid)
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    entities = data.get("entities", data)
    entity = entities.get(country_qid, {}) if isinstance(entities, dict) else {}
    claims = entity.get("claims", {}) if isinstance(entity, dict) else {}
    out: List[str] = []
    for prop in ("P37", "P2936"):
        for claim in claims.get(prop, []):
            qid = (claim.get("mainsnak", {}).get("datavalue", {})
                   .get("value", {}).get("id", ""))
            code = LANG_QID.get(qid)
            if code and code not in out:
                out.append(code)
    return out


# ── DB cache (local_language_cache) ───────────────────────────────────────────
_CACHE_TABLE_OK = False


def _conn():
    try:
        from venue_resolver import _get_db_connection
        return _get_db_connection()
    except Exception:
        try:
            import psycopg2
            db_url = os.environ.get(
                "DATABASE_URL",
                "postgresql://admin:password123@postgres-2:5432/audiotours")
            return psycopg2.connect(db_url)
        except Exception:
            return None


def _ensure_cache(conn) -> bool:
    """Idempotent CREATE TABLE IF NOT EXISTS for the language cache (additive)."""
    global _CACHE_TABLE_OK
    if _CACHE_TABLE_OK:
        return True
    try:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS local_language_cache (
                location_key TEXT PRIMARY KEY,
                country_code VARCHAR(8),
                languages_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        try:
            conn.commit()
        except Exception:
            pass
        _CACHE_TABLE_OK = True
        return True
    except Exception:
        return False


def _cache_key(city_or_coords) -> str:
    return _fold(city_or_coords) if isinstance(city_or_coords, str) else \
        str(city_or_coords)


def _cache_get_langs(key: str):
    conn = _conn()
    if not conn:
        return None
    try:
        if not _ensure_cache(conn):
            return None
        with conn.cursor() as cur:
            cur.execute("SELECT languages_json FROM local_language_cache "
                        "WHERE location_key = %s", (key,))
            row = cur.fetchone()
        if row and row[0]:
            return list(json.loads(row[0]))
    except Exception:
        return None
    return None


def _cache_put_langs(key: str, cc: Optional[str], langs: List[str]) -> None:
    conn = _conn()
    if not conn:
        return
    try:
        if not _ensure_cache(conn):
            return
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO local_language_cache
                (location_key, country_code, languages_json)
                VALUES (%s, %s, %s)
                ON CONFLICT (location_key) DO UPDATE SET
                    country_code = EXCLUDED.country_code,
                    languages_json = EXCLUDED.languages_json,
                    created_at = CURRENT_TIMESTAMP""",
                        (key, cc, json.dumps(langs)))
        try:
            conn.commit()
        except Exception:
            pass
    except Exception:
        pass


def languages_for(city_or_coords, *, fetch=None, wikidata_fetch=None,
                  country_qid: str = "", use_cache: bool = True,
                  _request_text: str = "") -> List[str]:
    """The tour's LOCAL language(s) as BCP-47 codes, best (dominant) first.

    ``city_or_coords`` — a request/scope string ("Montmartre walk, Paris") or a
    ``(lat, lng)`` pair / "lat,lng" string.

    Order (D768):
      1. a REGIONAL override named in the location (Quebec -> fr; Catalonia ->
         ca+es; Hong Kong -> zh-Hant+en) — these replace the country default;
      2. the resolved COUNTRY's languages from ``COUNTRY_LANGUAGES`` (the country
         comes from the 863R curated table, then Nominatim ``country_code``);
      3. the country's Wikidata P37/P2936 languages, used to ENRICH (append) the
         table answer when ``wikidata_fetch`` + ``country_qid`` are supplied.

    ``fetch`` / ``wikidata_fetch`` are injected so the module is offline by
    default; without them the curated table + the request's named country still
    answer every task case. Result cached in ``local_language_cache``. Always
    returns at least ``["en"]``. Never raises."""
    key = _cache_key(city_or_coords)
    if use_cache:
        cached = _cache_get_langs(key)
        if cached:
            return cached

    texts = [t for t in (city_or_coords if isinstance(city_or_coords, str) else "",
                         _request_text) if t]

    # 1) regional override (also check the raw request text)
    langs = _regional_override(*texts)
    cc = None

    if langs is None:
        # 2) country default
        cc = _country_for(city_or_coords, fetch=fetch)
        if cc and cc in COUNTRY_LANGUAGES:
            langs = list(COUNTRY_LANGUAGES[cc])
        elif cc:
            langs = []  # known country, unknown language set -> fill from Wikidata
        else:
            langs = []

    # 3) Wikidata enrichment (append anything new; never reorder the table answer)
    if wikidata_fetch is not None and country_qid:
        for code in wikidata_languages_for_country(country_qid, fetch=wikidata_fetch):
            if code not in langs:
                langs.append(code)

    if not langs:
        langs = ["en"]

    if use_cache:
        _cache_put_langs(key, cc, langs)
    _log(f"[LOCAL-875] local language for {city_or_coords!r}: {langs} "
         f"(country={cc or '?'})")
    return langs


def local_language(city_or_coords, **kw) -> str:
    """The single dominant local language code for a location."""
    langs = languages_for(city_or_coords, **kw)
    return langs[0] if langs else "en"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Language-free classification — P31 first, then Places, then name
# ═══════════════════════════════════════════════════════════════════════════

# The EXPLICIT, documented P31 Q-id -> (group, subtype) map the task asks for.
# place_kinds._QID already carries these (and more); this is the public,
# language-free mapping the escalation path and the tests reference by name. It
# is a SUPERSET of the 10 QIDs the ticket lists (Q16970 church, Q44539 temple,
# Q863454 pier, Q8502 mountain, Q35509 cave, Q34038 waterfall, Q39594 bay,
# Q16560 palace, Q153562 opera house, + more).
P31_SUBTYPE: Dict[str, Tuple[str, str]] = dict(place_kinds._QID)
# Guarantee the ticket's ten are present and correct even if place_kinds changes.
P31_SUBTYPE.update({
    "Q16970": ("religious", "church"),
    "Q44539": ("religious", "temple"),
    "Q32815": ("religious", "mosque"),
    "Q16560": ("royal", "palace"),
    "Q23413": ("royal", "castle"),
    "Q153562": ("performance", "opera_house"),
    "Q863454": ("maritime", "pier"),
    "Q39715": ("maritime", "lighthouse"),
    "Q12280": ("maritime", "bridge"),
    "Q8502": ("peaks", "mountain"),
    "Q35509": ("depression", "cave"),
    "Q34038": ("water", "waterfall"),
    "Q39594": ("water", "bay"),
})


def classify_place(name: str, *, places_type: str = "", places_category: str = "",
                   wikidata_instance_of: str = "", language: str = "") -> Dict:
    """Language-free-first classification of a stop (D767 order): Wikidata P31,
    then Google Places type/category, then name words. Thin wrapper over
    ``place_kinds.classify`` that names the signal arguments the escalation path
    passes. Returns ``{group, subtype, confidence}``.

    A P31 Q-id in ``wikidata_instance_of`` that is in ``P31_SUBTYPE`` decides the
    kind with no reliance on the stop's language — a Chinese temple (龍山寺,
    P31=Q44539), a Russian church (Храм, P31=Q16970) or a French lighthouse
    (Phare, P31=Q39715) classify correctly from the QID alone."""
    return place_kinds.classify(
        name or "",
        type_label=places_type or "",
        places_category=places_category or "",
        wikidata_instance_of=wikidata_instance_of or "",
        language=language or "",
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. kind_words(lang) — local words for every kind, generated once, cached
# ═══════════════════════════════════════════════════════════════════════════

# The complete list of keys the LLM must return words for: every D767 subtype,
# plus street_area and every business word. Stable, derived from place_kinds.
_SUBTYPE_KEYS: List[str] = sorted({sub for _g, sub, _l in place_kinds._T})
_BUSINESS_KEYS: List[str] = list(place_kinds.BUSINESS_WORDS)
KIND_WORD_KEYS: List[str] = _SUBTYPE_KEYS + ["street_area"] + _BUSINESS_KEYS


def _seed_from_table(lang: str) -> Dict[str, List[str]]:
    """en / vi fixtures straight from the place_kinds taxonomy — no LLM. The task
    keeps en + vi as seed lists."""
    out: Dict[str, List[str]] = {}
    for _g, sub, langs in place_kinds._T:
        words = langs.get(lang) or []
        if words:
            out.setdefault(sub, [])
            for w in words:
                if w not in out[sub]:
                    out[sub].append(w)
    # street_area
    street_words = []
    for _g, sub, langs in place_kinds._T:
        if sub == "street":
            street_words = list(langs.get(lang) or [])
    if street_words:
        out["street_area"] = street_words
    # business words
    if lang == "en":
        for w in place_kinds.BUSINESS_WORDS:
            out.setdefault(w, [w])
    elif lang == "vi":
        # the Vietnamese business equivalents are a single shared list in the
        # taxonomy; attach them under a 'business' bucket.
        out["business"] = list(place_kinds.BUSINESS_WORDS_VI)
    return out


SEED_FIXTURES: Dict[str, Dict[str, List[str]]] = {
    "en": _seed_from_table("en"),
    "vi": _seed_from_table("vi"),
}


def seed_kind_words(lang: str) -> Optional[Dict[str, List[str]]]:
    """The fixture word map for a seeded language (en, vi), else None."""
    seed = SEED_FIXTURES.get(lang)
    return {k: list(v) for k, v in seed.items()} if seed else None


# ── place_kind_words table ────────────────────────────────────────────────────
_WORDS_TABLE_OK = False


def _ensure_words(conn) -> bool:
    global _WORDS_TABLE_OK
    if _WORDS_TABLE_OK:
        return True
    try:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS place_kind_words (
                lang VARCHAR(16) NOT NULL,
                subtype VARCHAR(64) NOT NULL,
                words TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (lang, subtype))""")
        try:
            conn.commit()
        except Exception:
            pass
        _WORDS_TABLE_OK = True
        return True
    except Exception:
        return False


def _words_get(lang: str) -> Optional[Dict[str, List[str]]]:
    conn = _conn()
    if not conn:
        return None
    try:
        if not _ensure_words(conn):
            return None
        with conn.cursor() as cur:
            cur.execute("SELECT subtype, words FROM place_kind_words WHERE lang = %s",
                        (lang,))
            rows = cur.fetchall() or []
        if not rows:
            return None
        out: Dict[str, List[str]] = {}
        for subtype, words in rows:
            try:
                out[subtype] = list(json.loads(words))
            except Exception:
                out[subtype] = [w.strip() for w in str(words).split(",") if w.strip()]
        return out or None
    except Exception:
        return None


def _words_put(lang: str, word_map: Dict[str, List[str]]) -> None:
    conn = _conn()
    if not conn:
        return
    try:
        if not _ensure_words(conn):
            return
        with conn.cursor() as cur:
            for subtype, words in word_map.items():
                cur.execute("""INSERT INTO place_kind_words (lang, subtype, words)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (lang, subtype) DO UPDATE SET
                        words = EXCLUDED.words,
                        created_at = CURRENT_TIMESTAMP""",
                            (lang, subtype, json.dumps(words)))
        try:
            conn.commit()
        except Exception:
            pass
    except Exception:
        pass


def _default_llm(lang: str) -> Optional[Dict[str, List[str]]]:
    """ONE gpt-4.1-mini call (temperature 0, JSON) returning the local words for
    every KIND_WORD_KEYS key. Costs ~$0.001, once per language, forever. Returns
    None (not a raise) when no key is configured or the call fails — the caller
    then keeps whatever it has. The network meter (sitecustomize) bills the call
    automatically; nothing extra to wire."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return None
    import urllib.request
    keys_list = ", ".join(KIND_WORD_KEYS)
    prompt = (
        "You translate place-type vocabulary for an audio-tour classifier.\n"
        f"Target language (BCP-47): {lang}.\n\n"
        "For EACH English key below, return the common words a native speaker of "
        f"{lang} uses for that kind of place — the noun as it appears in real "
        "place names (include script-native forms; no transliteration unless the "
        "language is written in Latin script). 1 to 4 words per key.\n\n"
        f"KEYS: {keys_list}\n\n"
        "Respond with ONLY a JSON object mapping each key to an array of strings. "
        "No prose, no code fence."
    )
    body = json.dumps({
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "max_tokens": 2000,
    }).encode()
    try:
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions", data=body,
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode())
        content = payload["choices"][0]["message"]["content"].strip()
        content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.M).strip()
        raw = json.loads(content)
    except Exception as e:
        _log(f"[LOCAL-875] kind words LLM call failed for {lang}: {e}")
        return None
    out: Dict[str, List[str]] = {}
    for k, v in (raw or {}).items():
        if isinstance(v, str):
            v = [v]
        if isinstance(v, list):
            words = [str(w).strip() for w in v if str(w).strip()]
            if words:
                out[k] = words
    return out or None


# Per-process memo so a second call in the same run never regenerates either.
_WORDS_MEMO: Dict[str, Dict[str, List[str]]] = {}


def kind_words(lang: str, *, llm: Optional[Callable[[str], Optional[Dict]]] = None,
               use_cache: bool = True) -> Dict[str, List[str]]:
    """The LOCAL words for every D767 subtype, ``street_area`` and the business
    list, for language ``lang``.

      * en / vi come straight from the FIXTURES (no LLM, no DB) — free, forever.
      * any other language is read from ``place_kind_words``; on a MISS exactly
        ONE generation happens (``llm`` or the default gpt-4.1-mini call),
        the result is stored forever, and a log line is written:
        ``[LOCAL-875] kind words generated for <lang> (N words)``.
      * a second call for the same language makes NO generation call (process
        memo + DB cache).

    Returns ``{key: [words...]}``. Never raises; an unresolvable language with no
    LLM yields the English fixture as a safe fallback (so a stop still classifies).
    """
    lang = (lang or "en").strip()

    seed = seed_kind_words(lang)
    if seed is not None:
        return seed

    if use_cache and lang in _WORDS_MEMO:
        return {k: list(v) for k, v in _WORDS_MEMO[lang].items()}

    if use_cache:
        stored = _words_get(lang)
        if stored:
            _WORDS_MEMO[lang] = stored
            return {k: list(v) for k, v in stored.items()}

    # MISS → generate once.
    generator = llm or _default_llm
    try:
        generated = generator(lang)
    except Exception:
        generated = None

    if generated:
        n = sum(len(v) for v in generated.values())
        _log(f"[LOCAL-875] kind words generated for {lang} ({n} words)")
        if use_cache:
            _WORDS_MEMO[lang] = generated
            _words_put(lang, generated)
        return {k: list(v) for k, v in generated.items()}

    # No generation possible → English fixture fallback (stop still classifies).
    fallback = seed_kind_words("en") or {}
    return {k: list(v) for k, v in fallback.items()}


# ═══════════════════════════════════════════════════════════════════════════
# 4. Research in the local language
# ═══════════════════════════════════════════════════════════════════════════

# Country (ISO-2) -> Serper (gl, hl) pair. gl is the country; hl the UI language.
_GL_HL: Dict[str, Tuple[str, str]] = {
    "vn": ("vn", "vi"), "fr": ("fr", "fr"), "es": ("es", "es"), "it": ("it", "it"),
    "de": ("de", "de"), "at": ("at", "de"), "ch": ("ch", "de"), "pt": ("pt", "pt"),
    "br": ("br", "pt"), "ru": ("ru", "ru"), "ua": ("ua", "uk"), "jp": ("jp", "ja"),
    "kr": ("kr", "ko"), "th": ("th", "th"), "kh": ("kh", "km"), "cn": ("cn", "zh-cn"),
    "tw": ("tw", "zh-tw"), "hk": ("hk", "zh-tw"), "mo": ("mo", "zh-tw"),
    "sg": ("sg", "en"), "nl": ("nl", "nl"), "be": ("be", "nl"), "gb": ("gb", "en"),
    "us": ("us", "en"), "ca": ("ca", "en"), "gr": ("gr", "el"), "tr": ("tr", "tr"),
    "pl": ("pl", "pl"), "cz": ("cz", "cs"), "hu": ("hu", "hu"), "se": ("se", "sv"),
    "no": ("no", "no"), "dk": ("dk", "da"), "fi": ("fi", "fi"), "mx": ("mx", "es"),
    "ar": ("ar", "es"), "in": ("in", "hi"), "id": ("id", "id"), "ph": ("ph", "en"),
    "eg": ("eg", "ar"), "ma": ("ma", "ar"), "il": ("il", "he"), "sa": ("sa", "ar"),
    "ae": ("ae", "ar"),
}


def country_gl_hl(country_code: str, lang: str = "") -> Dict[str, str]:
    """Serper ``gl`` (country) and ``hl`` (interface language) for a country. Falls
    back to the country code for gl and ``lang`` (or 'en') for hl."""
    cc = (country_code or "").lower()
    if cc in _GL_HL:
        gl, hl = _GL_HL[cc]
    else:
        gl, hl = (cc or "us"), (lang or "en")
    if lang:
        # If a specific BCP-47 was resolved, honour its base for hl.
        base = lang.split("-")[0].lower()
        if base:
            hl = lang if cc in ("cn", "tw", "hk", "mo") else base
    return {"gl": gl, "hl": hl}


def local_alias(name: str, lang: str, *, label_fetch=None) -> str:
    """The stop's LOCAL-language name (its Wikidata label in ``lang``), to keep as
    an alias on the stop. ``label_fetch(name, lang) -> str`` is injected (reuses a
    Wikidata label lookup in the caller); returns '' when none / offline. The
    English name is never returned as its own alias."""
    if not name or not lang or label_fetch is None:
        return ""
    try:
        label = label_fetch(name, lang)
    except Exception:
        return ""
    label = (label or "").strip()
    if label and _fold(label) != _fold(name):
        return label
    return ""


def local_wikipedia_evidence(name: str, lang: str, *, fetch_fn=None,
                             use_cache: bool = True) -> Optional[Dict[str, str]]:
    """The stop's Wikipedia LOCAL-edition article (``lang``), reusing
    ``landmark_wikipedia_evidence.fetch_article`` (its DB cache + name-match).
    Returns ``{title, lead, infobox}`` or None. Offline when ``fetch_fn`` is
    injected."""
    if not name or not lang:
        return None
    try:
        import landmark_wikipedia_evidence as lwe
    except Exception:
        return None
    try:
        return lwe.fetch_article(name, lang=lang, fetch_fn=fetch_fn,
                                 use_cache=use_cache)
    except Exception:
        return None


def serper_local_queries(name: str, city: str, lang: str, country_code: str,
                         *, local_name: str = "",
                         words: Optional[Dict[str, List[str]]] = None,
                         subtype: str = "", max_queries: int = 3) -> Dict:
    """Build the LOCAL-language Serper queries for a thin stop.

    Uses the stop's LOCAL name (``local_name`` — the Wikidata label in ``lang`` —
    falling back to ``name``) plus the LOCAL kind words for its ``subtype`` (from
    ``words``, i.e. ``kind_words(lang)``), and returns the ``gl``/``hl`` set to the
    stop's country so Serper returns LOCAL results.

    Returns ``{"queries": [str, ...], "gl": str, "hl": str, "local_name": str}``.
    Pure — no network. The caller feeds ``queries`` + ``gl``/``hl`` to the
    existing Serper backend."""
    base = (local_name or name or "").strip()
    gl_hl = country_gl_hl(country_code, lang)
    kws: List[str] = []
    if words and subtype:
        kws = list(words.get(subtype, []))[:3]
    city = (city or "").strip()
    queries: List[str] = []

    def _add(q: str):
        q = re.sub(r"\s+", " ", q).strip()
        if q and q not in queries:
            queries.append(q)

    if base:
        _add(f"{base} {city}".strip())
        for kw in kws:
            _add(f"{base} {kw} {city}".strip())
        _add(f"{base} lịch sử" if lang == "vi" else f"{base} {city} history")
    return {"queries": queries[:max_queries], "gl": gl_hl["gl"],
            "hl": gl_hl["hl"], "local_name": base}


def escalate_local_language(name: str, scope: str, *, places_type: str = "",
                            places_category: str = "", wikidata_instance_of: str = "",
                            languages: Optional[Sequence[str]] = None,
                            country_code: str = "", local_name: str = "",
                            fetch=None, wiki_fetch_fn=None, llm=None,
                            use_cache: bool = True) -> Dict:
    """The ONE helper LOCAL-873's thin-stop escalation calls.

    Given a stop ``name`` and the tour ``scope`` string, it:
      1. detects the local language(s) (``languages`` overrides, else ``languages_for``);
      2. classifies the stop language-free (P31 → Places → name);
      3. loads the LOCAL kind words for the dominant language (``kind_words``);
      4. fetches the stop's LOCAL Wikipedia edition (in addition to en) as evidence;
      5. builds the LOCAL-language Serper queries with gl/hl;
      6. keeps the LOCAL name as an alias.

    Returns a bundle:
      ``{languages, dominant, classification, local_alias, wikipedia,
         serper, kind_words_keys}``.

    Everything is best-effort and offline-safe: injected ``fetch`` /
    ``wiki_fetch_fn`` / ``llm`` keep it from touching the network in tests."""
    langs = list(languages) if languages else languages_for(
        scope, fetch=fetch, use_cache=use_cache)
    dominant = langs[0] if langs else "en"
    cc = (country_code or city_scope.requested_country(scope) or "").lower()
    if not cc:
        cc = (_country_for(scope, fetch=fetch) or "")

    classification = classify_place(
        name, places_type=places_type, places_category=places_category,
        wikidata_instance_of=wikidata_instance_of, language=dominant)
    subtype = classification.get("subtype", "")

    kw_map: Dict[str, List[str]] = {}
    if dominant != "en":
        kw_map = kind_words(dominant, llm=llm, use_cache=use_cache)

    city = (scope or "").split(",")[-1].strip() or scope or ""
    wiki: Dict[str, Optional[Dict[str, str]]] = {}
    for lg in dict.fromkeys(["en"] + list(langs)):
        art = local_wikipedia_evidence(name, lg, fetch_fn=wiki_fetch_fn,
                                       use_cache=use_cache)
        if art:
            wiki[lg] = art

    serper = serper_local_queries(
        name, city, dominant, cc, local_name=local_name, words=kw_map,
        subtype=subtype)

    return {
        "languages": langs,
        "dominant": dominant,
        "country_code": cc,
        "classification": classification,
        "local_alias": local_name or "",
        "wikipedia": wiki,
        "serper": serper,
        "kind_words_keys": sorted(kw_map.keys()) if kw_map else [],
    }
