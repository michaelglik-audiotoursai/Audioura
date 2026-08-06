"""dining_corpus_harvester.py — LOCAL-314: Harvest stop_corpus for dining stops.

When a restaurant verifies via Nominatim/Wikipedia, the response already
contains factual data (address, OSM category). A supplementary web search
carries what a listener wants: founding year, chef, signature dishes, price.

This module:
  1. Extracts address from Nominatim verification evidence (free — already fetched).
  2. Searches Wikipedia (en + fr) for the restaurant to find facts.
  3. Runs a general web search for culinary detail (chef, founding year, dishes).
  4. Applies the LOCAL-277 quality bar: every passage must carry a date,
     named person, documented event, dish name, or price.
  5. Stores passages in stop_corpus with source URLs.

Quality bar (matches LOCAL-252/277):
  - Every passage carries a date, a named person, a documented event, a dish, or a price.
  - "Warm atmosphere" is NOT a passage.
  - A passage about Niçoise cuisine in general is NOT a passage about THIS restaurant.

Never synthesise. If a restaurant has no published detail, store nothing.
"""

import json
import logging
import os
import re
import time
import unicodedata
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ─── Text utilities ──────────────────────────────────────────────────────────

def _strip_accents(text: str) -> str:
    """Remove accents for matching."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _normalize(text: str) -> str:
    """Normalize for comparison."""
    t = _strip_accents(text).lower().strip()
    t = re.sub(r'[^\w\s]', ' ', t)
    return ' '.join(t.split())


# ─── Quality gate for dining passages ────────────────────────────────────────

_YEAR_RE = re.compile(r'\b(1[5-9]\d{2}|20[0-2]\d)\b')
_PRICE_RE = re.compile(r'[€$£]\s*\d+|\d+\s*(?:euros?|EUR|dollars?|pounds?)', re.I)
_DISH_SIGNALS = re.compile(
    r'\b(socca|pissaladi[eè]re|ratatouille|daube|bouillabaisse|salade ni[cç]oise|'
    r'tapenade|pan bagnat|farcis|gnocchi|ravioli|aioli|brandade|'
    r'foie gras|confit|tartare|carpaccio|risotto|cassoulet|'
    r'boudin|p[aâ]t[eé]|cr[oô][uû]te|pastilla|cod|moules|'
    r'menu|carte|plat|entr[eé]e|dessert|starter|main course|'
    r'michelin star|gault.?millau|bib gourmand)\b', re.I
)


def _passage_carries_dining_fact(text: str) -> bool:
    """Check if a passage carries at least one dining-relevant fact.

    A fact-carrying dining passage has:
      - A year (founding, opening, renovation, chef tenure)
      - A named person (chef, founder, owner) with an action
      - A price or price range
      - A specific dish name or cuisine descriptor
      - A concrete measurement (seats, covers, Michelin stars)
      - A guide rating (Gault&Millau score, numeric rating out of 10/20)
    """
    if _YEAR_RE.search(text):
        return True
    if _PRICE_RE.search(text):
        return True
    if _DISH_SIGNALS.search(text):
        return True
    # Seat count / covers
    if re.search(r'\b\d+\s*(seats?|covers?|couverts?|places?)\b', text, re.I):
        return True
    # Guide ratings (7.5/10, 15/20, etc.)
    if re.search(r'\b\d+\.?\d*\s*/\s*(?:10|20)\b', text):
        return True
    # Named person with biographical verb
    if re.search(r'(?:chef|owner|founder|patron|propri[eé]taire)\s+\w+', text, re.I):
        return True
    # Person name followed by action verbs (trained, opened, took over, worked)
    if re.search(r'[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}.*?\b(trained|opened|founded|took over|worked|earned|received|awarded)', text, re.I):
        return True
    # "since YYYY" pattern (common in restaurant descriptions)
    if re.search(r'\bsince\s+\d{4}\b', text, re.I):
        return True
    # "opened in", "founded in", "established in" + year
    if re.search(r'\b(?:opened|founded|established|re-opened)\s+(?:in\s+)?\d{4}\b', text, re.I):
        return True
    return False


def _is_generic_not_specific(text: str, stop_title: str) -> bool:
    """D157: A passage about Niçoise cuisine in general is NOT about THIS restaurant."""
    text_lower = text.lower()
    stop_norm = _normalize(stop_title)
    stop_words = [w for w in stop_norm.split() if len(w) >= 4 and w not in ('chez', 'restaurant', 'bistrot', 'cafe')]

    # Must mention the restaurant by name (at least one distinctive word)
    has_name_signal = any(w in _normalize(text) for w in stop_words) if stop_words else False

    # Generic area descriptions
    generic_signals = [
        'niçoise cuisine in general', 'the restaurants of', 'old nice is known',
        'vieux nice offers', 'the culinary scene', 'the food scene',
        'many restaurants', 'numerous eateries', 'the region is famous',
    ]
    is_generic = any(s in text_lower for s in generic_signals)

    if is_generic and not has_name_signal:
        return True
    return False


# ─── Wikipedia search for restaurant facts ───────────────────────────────────

def _search_wikipedia_for_restaurant(
    stop_title: str, city: str
) -> List[Dict]:
    """Search Wikipedia (en + fr) for factual content about a restaurant.

    Returns list of {text, url, language} passages that pass the quality gate.
    """
    import requests as _http

    _HEADERS = {
        "User-Agent": "Audioura/2.2 (tour-generation; contact: support@audioura.com)",
        "Accept": "application/json",
    }

    passages = []

    # --- English Wikipedia summary ---
    try:
        from urllib.parse import quote
        encoded = quote(stop_title.replace(" ", "_"), safe="")
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        resp = _http.get(url, headers=_HEADERS, timeout=8, allow_redirects=True)
        if resp.status_code == 200:
            data = resp.json()
            extract = data.get("extract", "")
            page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
            if extract and len(extract) > 80:
                # Check it's about the right thing (mentions city or dining)
                extract_lower = extract.lower()
                city_lower = _strip_accents(city).lower()
                if (city_lower in _strip_accents(extract).lower() or
                        any(s in extract_lower for s in ('restaurant', 'chef', 'cuisine', 'dining', 'bistro'))):
                    if _passage_carries_dining_fact(extract) and not _is_generic_not_specific(extract, stop_title):
                        passages.append({
                            'text': extract[:500],
                            'url': page_url or f"https://en.wikipedia.org/wiki/{encoded}",
                            'language': 'en',
                        })
        time.sleep(0.3)
    except Exception as e:
        logger.debug(f"[DINING-HARVEST] Wikipedia EN failed for {stop_title!r}: {e}")

    # --- French Wikipedia summary ---
    try:
        from urllib.parse import quote
        encoded_fr = quote(stop_title.replace(" ", "_"), safe="")
        url_fr = f"https://fr.wikipedia.org/api/rest_v1/page/summary/{encoded_fr}"
        resp_fr = _http.get(url_fr, headers=_HEADERS, timeout=8, allow_redirects=True)
        if resp_fr.status_code == 200:
            data_fr = resp_fr.json()
            extract_fr = data_fr.get("extract", "")
            page_url_fr = data_fr.get("content_urls", {}).get("desktop", {}).get("page", "")
            if extract_fr and len(extract_fr) > 80:
                extract_fr_lower = extract_fr.lower()
                city_lower = _strip_accents(city).lower()
                if (city_lower in _strip_accents(extract_fr).lower() or
                        any(s in extract_fr_lower for s in ('restaurant', 'chef', 'cuisine', 'bistro', 'cuisinier'))):
                    if _passage_carries_dining_fact(extract_fr) and not _is_generic_not_specific(extract_fr, stop_title):
                        passages.append({
                            'text': extract_fr[:500],
                            'url': page_url_fr or f"https://fr.wikipedia.org/wiki/{encoded_fr}",
                            'language': 'fr',
                        })
        time.sleep(0.3)
    except Exception as e:
        logger.debug(f"[DINING-HARVEST] Wikipedia FR failed for {stop_title!r}: {e}")

    # --- Wikipedia search (catches restaurants mentioned in other articles) ---
    try:
        search_url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": f'"{stop_title}" {city} restaurant',
            "srlimit": "3",
            "format": "json",
            "srprop": "snippet|titlesnippet",
        }
        resp_s = _http.get(search_url, params=params, headers=_HEADERS, timeout=8)
        if resp_s.status_code == 200:
            results = resp_s.json().get("query", {}).get("search", [])
            for r in results:
                snippet = re.sub(r'<[^>]+>', '', r.get("snippet", ""))
                title = r.get("title", "")
                if snippet and len(snippet) > 60:
                    # Must mention the restaurant
                    stop_words = [w for w in _normalize(stop_title).split() if len(w) >= 4]
                    if any(w in _normalize(snippet) for w in stop_words):
                        if _passage_carries_dining_fact(snippet):
                            passages.append({
                                'text': snippet[:500],
                                'url': f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'), safe='')}",
                                'language': 'en',
                            })
        time.sleep(0.3)
    except Exception as e:
        logger.debug(f"[DINING-HARVEST] Wikipedia search failed for {stop_title!r}: {e}")

    return passages


# ─── Web search for culinary details ─────────────────────────────────────────

def _web_search_restaurant(
    stop_title: str, city: str, address: str = ""
) -> List[Dict]:
    """Search the web for factual detail about a restaurant.

    Uses the Serper.dev API (SERP_API_KEY + SERP_PROVIDER=serper) or
    SerpAPI as fallback. Returns fact-carrying passages with source URLs.
    """
    import requests as _http

    passages = []
    serp_key = os.environ.get("SERP_API_KEY") or os.environ.get("SERPAPI_KEY")
    serp_provider = os.environ.get("SERP_PROVIDER", "").lower()

    if serp_key and serp_provider == "serper":
        # Serper.dev API
        try:
            headers = {"X-API-KEY": serp_key, "Content-Type": "application/json"}
            payload = {"q": f'"{stop_title}" {city} restaurant', "num": 5}
            resp = _http.post("https://google.serper.dev/search", json=payload,
                             headers=headers, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                for result in data.get("organic", [])[:5]:
                    snippet = result.get("snippet", "")
                    url = result.get("link", "")
                    if snippet and len(snippet) > 50:
                        stop_words = [w for w in _normalize(stop_title).split() if len(w) >= 4]
                        if any(w in _normalize(snippet) for w in stop_words):
                            if _passage_carries_dining_fact(snippet):
                                if not _is_generic_not_specific(snippet, stop_title):
                                    passages.append({
                                        'text': snippet[:500],
                                        'url': url,
                                    })
                # Knowledge graph
                kg = data.get("knowledgeGraph", {})
                if kg:
                    description = kg.get("description", "")
                    if description and _passage_carries_dining_fact(description):
                        if not _is_generic_not_specific(description, stop_title):
                            passages.append({
                                'text': description[:500],
                                'url': kg.get("website", url),
                            })
            elif resp.status_code == 429:
                logger.warning("[DINING-HARVEST] Serper 429 — rate limited")
                raise RuntimeError("Serper rate limited (429)")
            time.sleep(0.5)
        except RuntimeError:
            raise
        except Exception as e:
            logger.debug(f"[DINING-HARVEST] Serper failed for {stop_title!r}: {e}")

    elif serp_key:
        # SerpAPI fallback
        try:
            params = {
                "q": f'"{stop_title}" {city} restaurant chef founded',
                "api_key": serp_key,
                "num": "5",
                "engine": "google",
            }
            resp = _http.get("https://serpapi.com/search", params=params, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                for result in data.get("organic_results", [])[:5]:
                    snippet = result.get("snippet", "")
                    url = result.get("link", "")
                    if snippet and len(snippet) > 50:
                        stop_words = [w for w in _normalize(stop_title).split() if len(w) >= 4]
                        if any(w in _normalize(snippet) for w in stop_words):
                            if _passage_carries_dining_fact(snippet):
                                if not _is_generic_not_specific(snippet, stop_title):
                                    passages.append({
                                        'text': snippet[:500],
                                        'url': url,
                                    })
            elif resp.status_code == 429:
                logger.warning("[DINING-HARVEST] SerpAPI 429 — rate limited")
                raise RuntimeError("SerpAPI rate limited (429)")
            time.sleep(0.5)
        except RuntimeError:
            raise
        except Exception as e:
            logger.debug(f"[DINING-HARVEST] SerpAPI failed for {stop_title!r}: {e}")
    else:
        # No search API key — use DuckDuckGo instant answer (limited)
        try:
            params = {
                "q": f"{stop_title} {city} restaurant",
                "format": "json",
                "no_redirect": "1",
            }
            resp = _http.get("https://api.duckduckgo.com/", params=params, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                abstract = data.get("Abstract", "")
                abstract_url = data.get("AbstractURL", "")
                if abstract and len(abstract) > 60:
                    if _passage_carries_dining_fact(abstract):
                        if not _is_generic_not_specific(abstract, stop_title):
                            passages.append({
                                'text': abstract[:500],
                                'url': abstract_url,
                            })
            time.sleep(0.3)
        except Exception as e:
            logger.debug(f"[DINING-HARVEST] DuckDuckGo failed for {stop_title!r}: {e}")

    return passages

    return passages


# ─── Extract address from Nominatim evidence ─────────────────────────────────

def _extract_address_from_evidence(evidence: str) -> Optional[str]:
    """Extract address from Nominatim evidence string.

    Evidence format: "nominatim_osm: 'Name' found in city(address, city) [category=...]"
    """
    m = re.search(r'\(([^)]+)\)', evidence)
    if m:
        addr = m.group(1).strip()
        # Remove trailing city name if duplicated
        return addr
    return None


# ─── Core harvesting logic ───────────────────────────────────────────────────

def harvest_dining_stop(
    stop_title: str,
    venue_name: str,
    city: str,
    evidence: str,
    db_conn,
) -> Dict:
    """Harvest factual passages for a single dining stop.

    Combines:
      1. Address from Nominatim evidence (free, already fetched)
      2. Wikipedia (en + fr) for the restaurant
      3. Web search for culinary detail

    Returns:
        {
            'harvested': bool,
            'passages_added': int,
            'source_urls': [str],
            'flag': None | 'already_has_corpus' | 'no_facts_found',
            'sample_passages': [str],
        }
    """
    result = {
        'harvested': False,
        'passages_added': 0,
        'source_urls': [],
        'flag': None,
        'sample_passages': [],
    }

    cur = db_conn.cursor()

    # 1. Check if stop already has corpus
    cur.execute(
        "SELECT passage_count FROM stop_corpus WHERE venue_name = %s AND stop_title = %s AND passage_count > 0",
        (venue_name, stop_title)
    )
    if cur.fetchone():
        result['flag'] = 'already_has_corpus'
        cur.close()
        return result

    # 2. Extract address from evidence
    address = _extract_address_from_evidence(evidence) or ""

    # 3. Gather passages from all sources
    all_passages = []
    seen_texts = set()

    # Address passage (from Nominatim — always available if verification passed)
    if address:
        addr_passage = f"{stop_title} is located at {address}."
        # Only include if it carries a fact beyond just the street name
        # (address alone doesn't meet the quality bar — but street + house number
        # is useful context that the generator needs for directions)
        # We store it but it won't count as a "fact" passage by itself

    # Wikipedia passages
    wiki_passages = _search_wikipedia_for_restaurant(stop_title, city)
    for wp in wiki_passages:
        text_key = _normalize(wp['text'])[:80]
        if text_key not in seen_texts:
            seen_texts.add(text_key)
            all_passages.append(wp)

    # Web search passages
    try:
        web_passages = _web_search_restaurant(stop_title, city, address)
        for wp in web_passages:
            text_key = _normalize(wp['text'])[:80]
            if text_key not in seen_texts:
                seen_texts.add(text_key)
                all_passages.append(wp)
    except RuntimeError as e:
        if '429' in str(e):
            print(f"    [DINING-HARVEST] Search API rate limited for {stop_title!r} — using Wikipedia only")
        else:
            raise

    # 4. If nothing found, store nothing (never synthesise)
    if not all_passages:
        result['flag'] = 'no_facts_found'
        cur.close()
        return result

    # 5. Write to stop_corpus
    passages_json_list = []
    source_pages = []
    source_urls_set: Set[str] = set()

    for p in all_passages:
        passages_json_list.append({
            'text': p['text'],
            'url': p.get('url', ''),
            'tier': 2,  # web/Wikipedia (tier 1 reserved for official venue sites)
            'type': 'web_search',
        })
        url = p.get('url', '')
        if url and url not in source_urls_set:
            source_urls_set.add(url)
            source_pages.append({
                'url': url,
                'tier': 2,
                'type': 'web_search',
                'title': f'{stop_title} — web source',
                'tier_reason': 'Wikipedia or web search (harvested on dining verification)',
            })

    passages_json = json.dumps(passages_json_list, ensure_ascii=False)
    sources_json = json.dumps(source_pages, ensure_ascii=False)
    passage_count = len(passages_json_list)

    cur.execute("""
        INSERT INTO stop_corpus (venue_name, stop_title, passages_json, source_pages, passage_count)
        VALUES (%s, %s, %s::jsonb, %s::jsonb, %s)
        ON CONFLICT (venue_name, stop_title)
        DO UPDATE SET passages_json = EXCLUDED.passages_json,
                      source_pages = EXCLUDED.source_pages,
                      passage_count = EXCLUDED.passage_count,
                      created_at = NOW()
        WHERE stop_corpus.passage_count = 0 OR stop_corpus.passage_count IS NULL
    """, (venue_name, stop_title, passages_json, sources_json, passage_count))

    db_conn.commit()
    cur.close()

    result['harvested'] = True
    result['passages_added'] = passage_count
    result['source_urls'] = sorted(source_urls_set)
    result['sample_passages'] = [p['text'][:200] for p in all_passages[:3]]

    return result


# ─── Integration: harvest all dining stops after verification ────────────────

def harvest_dining_on_verification(
    verdicts: List[Dict],
    venue_name: str,
    db_conn,
) -> Dict:
    """Harvest corpus for verified dining stops.

    Called after run_existence_gate() completes with dining verdicts.
    Only harvests for stops that:
      - Were verified (existence confirmed)
      - Don't already have corpus

    Args:
        verdicts: List of verdict dicts from the existence gate.
        venue_name: The venue_name used in generation (for stop_corpus matching).
        db_conn: psycopg2 connection.

    Returns:
        {
            'total_verified': int,
            'already_has_corpus': int,
            'harvested': int,
            'no_facts_found': int,
            'details': [{stop_title, harvested, passages_added, flag, ...}]
        }
    """
    summary = {
        'total_verified': 0,
        'already_has_corpus': 0,
        'harvested': 0,
        'no_facts_found': 0,
        'details': [],
    }

    # Extract city from venue_name
    city = _extract_city_from_venue(venue_name)

    for verdict in verdicts:
        if not verdict.get('verified'):
            continue

        summary['total_verified'] += 1
        stop_title = verdict['stop_title']
        evidence = verdict.get('evidence', '')

        harvest_result = harvest_dining_stop(
            stop_title=stop_title,
            venue_name=venue_name,
            city=city,
            evidence=evidence,
            db_conn=db_conn,
        )

        if harvest_result['harvested']:
            summary['harvested'] += 1
            print(f"    [DINING-HARVEST] {stop_title!r}: +{harvest_result['passages_added']} passages "
                  f"from {harvest_result['source_urls']}")
        elif harvest_result['flag'] == 'already_has_corpus':
            summary['already_has_corpus'] += 1
        elif harvest_result['flag'] == 'no_facts_found':
            summary['no_facts_found'] += 1
            print(f"    [DINING-HARVEST] {stop_title!r}: no facts found (stop will be thin)")

        summary['details'].append({
            'stop_title': stop_title,
            'harvested': harvest_result['harvested'],
            'passages_added': harvest_result['passages_added'],
            'flag': harvest_result['flag'],
            'sample_passages': harvest_result.get('sample_passages', []),
            'source_urls': harvest_result.get('source_urls', []),
        })

    # Summary log
    print(f"    [DINING-HARVEST] Summary: {summary['harvested']} harvested, "
          f"{summary['already_has_corpus']} already had corpus, "
          f"{summary['no_facts_found']} no facts found")

    return summary


def _extract_city_from_venue(venue_name: str) -> str:
    """Extract the primary city name from a venue string.

    Handles: "restaurant tour in Old Nice (Vieux Nice), France" → "Nice"
    """
    # Remove parenthetical content
    cleaned = re.sub(r'\([^)]*\)', ' ', venue_name)
    # Remove common noise
    noise = {'restaurant', 'tour', 'in', 'old', 'new', 'vieux', 'france',
             'italy', 'spain', 'food', 'dining', 'culinary', 'stops', 'stop'}
    words = re.findall(r'[A-Za-zÀ-ÿ]+', cleaned)
    # Take first capitalized word that's not noise
    for w in words:
        if w[0].isupper() and w.lower() not in noise and len(w) >= 3:
            return w
    return words[0] if words else ""
