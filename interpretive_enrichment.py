"""interpretive_enrichment.py — LOCAL-332: Ask *what is interesting* rather than *does it exist*.

The finding (D233/D241): name-based searches return directory listings.
  "Le Safari" Nice restaurant → TripAdvisor, Yelp, "Restaurants near me"
  "What is interesting about Le Safari in Nice?" → Cuisine Nissarde accreditation,
    Franck Cerutti's years at Ducasse, École de Nice painters on walls.

This module adds an INTERPRETIVE enrichment stage after the existence gate:
  1. Generates two interpretive questions derived from the venue kind + context.
  2. Searches via Serper.dev for answers.
  3. Extracts factual passages (not ratings, not atmospherics).
  4. Verifies attributed quotes against primary sources (or drops them).
  5. Stores surviving passages in stop_corpus with source URLs.

Critical safety rule (D233):
  AI-generated search summaries are CANDIDATE CLAIMS TO VERIFY, never text to narrate.
  A quote attributed to a named person or publication must be verified against a
  primary source or dropped. An unattributed atmospheric sentence is worthless.

Cost: $0.001/query × 2 queries × 5 stops = $0.01/tour (against ~$0.31 gen+TTS).
"""

import json
import logging
import os
import re
import time
import unicodedata
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ─── Text utilities ──────────────────────────────────────────────────────────

def _strip_accents(text: str) -> str:
    """Remove accents for comparison."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _normalize(text: str) -> str:
    """Normalize for comparison."""
    t = _strip_accents(text).lower().strip()
    t = re.sub(r'[^\w\s]', ' ', t)
    return ' '.join(t.split())


# ─── Question generation ─────────────────────────────────────────────────────

# Question templates by venue kind. The key insight: ask ABOUT the place,
# not FOR its name. "What is interesting about X" yields narrative content.
# "X restaurant" yields directory listings.

_QUESTION_TEMPLATES = {
    'restaurant': [
        'What is interesting about {name} {kind} in {city}, {country}?',
        'Who are notable people associated with {name} in {city} and what did they do there?',
    ],
    'cafe': [
        'What is interesting about {name} {kind} in {city}, {country}?',
        'Who are notable people associated with {name} in {city} and what is its history?',
    ],
    'bar': [
        'What is interesting about {name} {kind} in {city}, {country}?',
        'What is the history of {name} in {city} and who are notable patrons?',
    ],
    'museum': [
        'What is notable about {name} in {city}, {country}?',
        'What are the most significant works and collections at {name}?',
    ],
    'gallery': [
        'What is interesting about {name} gallery in {city}, {country}?',
        'Who are famous artists exhibited at {name} and what makes it distinctive?',
    ],
    'monument': [
        'What is interesting about {name} in {city}, {country}?',
        'What is the history of {name} and who commissioned or designed it?',
    ],
    'church': [
        'What is interesting about {name} in {city}, {country}?',
        'What is the architectural and religious history of {name}?',
    ],
    'default': [
        'What is interesting or notable about {name} in {city}, {country}?',
        'Who are notable people associated with {name} in {city} and what is its history?',
    ],
}


def build_interpretive_questions(
    stop_title: str,
    venue_kind: str,
    city: str,
    country: str = "",
) -> List[str]:
    """Generate 2 interpretive questions for a venue.

    Args:
        stop_title: The name of the stop (e.g., "Le Safari")
        venue_kind: The type of venue (restaurant, museum, etc.)
        city: City name (e.g., "Nice")
        country: Country name (e.g., "France")

    Returns:
        List of 2 question strings.
    """
    kind_key = venue_kind.lower().strip() if venue_kind else 'default'
    # Normalize kind to template key
    kind_map = {
        'restaurant': 'restaurant', 'food': 'restaurant', 'dining': 'restaurant',
        'culinary': 'restaurant', 'bistro': 'restaurant', 'brasserie': 'restaurant',
        'cafe': 'cafe', 'coffee': 'cafe', 'tea': 'cafe',
        'bar': 'bar', 'pub': 'bar', 'wine bar': 'bar',
        'museum': 'museum', 'gallery': 'gallery',
        'monument': 'monument', 'memorial': 'monument', 'statue': 'monument',
        'church': 'church', 'cathedral': 'church', 'chapel': 'church',
    }
    template_key = kind_map.get(kind_key, 'default')
    templates = _QUESTION_TEMPLATES.get(template_key, _QUESTION_TEMPLATES['default'])

    # Use "restaurant" etc. as the kind word in the query, except for default
    kind_word = kind_key if kind_key != 'default' else ''

    questions = []
    for tmpl in templates:
        q = tmpl.format(
            name=stop_title,
            kind=kind_word,
            city=city,
            country=country or "",
        )
        # Clean up double spaces
        q = re.sub(r'\s+', ' ', q).strip()
        questions.append(q)

    return questions


# ─── Passage extraction from search results ──────────────────────────────────

# Signals that a passage carries a verifiable fact (reused from dining_corpus_harvester)
_YEAR_RE = re.compile(r'\b(1[5-9]\d{2}|20[0-2]\d)\b')
_PRICE_RE = re.compile(r'[€$£]\s*\d+|\d+\s*(?:euros?|EUR|dollars?|pounds?)', re.I)
_NAMED_PERSON_RE = re.compile(
    r'(?:chef|owner|founder|patron|artist|architect|designer|director)\s+[A-Z][a-z]+',
    re.I,
)
_PROPER_NOUN_ACTION_RE = re.compile(
    r'[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}.*?\b(trained|opened|founded|took over|worked|earned|'
    r'received|awarded|designed|built|painted|composed|wrote|directed|created|established)',
    re.I,
)


def _carries_verifiable_fact(text: str) -> bool:
    """Check if text carries at least one concrete, verifiable fact."""
    if _YEAR_RE.search(text):
        return True
    if _PRICE_RE.search(text):
        return True
    if _NAMED_PERSON_RE.search(text):
        return True
    if _PROPER_NOUN_ACTION_RE.search(text):
        return True
    # Accreditation / label / award language
    if re.search(r'\b(accredit|certif|label|award|star|prize|medal)\w*\b', text, re.I):
        return True
    # "since YYYY" or "opened in YYYY"
    if re.search(r'\b(since|opened|founded|established)\s+(in\s+)?\d{4}\b', text, re.I):
        return True
    # Named dish with proper noun context
    if re.search(r'(Bagna Cauda|Petits Farcis|Pissaladi[eè]re|Socca|Daube|'
                 r'Bouillabaisse|Ratatouille|Ravioli)', text):
        return True
    return False


def _is_atmospheric_or_review(text: str) -> bool:
    """Reject passages that are opinions, atmospherics, or review language."""
    text_lower = text.lower()

    # Star/numeric ratings
    if re.search(r'\b\d\.?\d?\s*/\s*5\b', text):
        return True
    if re.search(r'\b\d\s*stars?\b', text_lower):
        return True

    # Review language
    review_signals = [
        'highly recommend', 'would recommend', 'must visit', 'don\'t miss',
        'amazing experience', 'wonderful experience', 'loved it',
        'my favorite', 'great value', 'good value', 'the service was',
        'we went', 'i went', 'i visited', 'we visited',
    ]
    if any(s in text_lower for s in review_signals):
        return True

    # Pure atmospheric with no fact
    atmospheric = [
        'warm atmosphere', 'cozy atmosphere', 'charming atmosphere',
        'buzzing with energy', 'fills the air', 'inviting ambiance',
        'clinking of cutlery', 'hum of conversation',
    ]
    if any(s in text_lower for s in atmospheric):
        return True

    return False


def _mentions_stop(text: str, stop_title: str) -> bool:
    """Check if text mentions the stop (accent-folded)."""
    text_norm = _normalize(text)
    stop_norm = _normalize(stop_title)
    # Check full name
    if stop_norm in text_norm:
        return True
    # Check significant words (≥4 chars, no articles)
    stop_words = [w for w in stop_norm.split()
                  if len(w) >= 4 and w not in ('chez', 'restaurant', 'bistrot', 'cafe', 'the')]
    return any(w in text_norm for w in stop_words) if stop_words else False


# ─── Attribution detection and verification ──────────────────────────────────

_ATTRIBUTION_RE = re.compile(
    r'(?:'
    # Pattern 1: "according to/said/wrote NAME" (verb then name)
    r'(?:according to|noted by)\s+(?:the\s+)?([A-Z][A-Za-z\s&]+?)(?:\s*,|\s+that|\s+it|\s+the|\s*")'
    r'|'
    # Pattern 2: "NAME said/wrote/declared QUOTE" (name then verb)
    r'([A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]+)?)\s+(?:said|wrote|described|called|declared|praised|noted)\s+'
    r'|'
    # Pattern 3: "quote" — Person
    r'(?:"[^"]+"\s*[-\u2014]\s*)([A-Z][A-Za-z\s&]+)'
    r'|'
    # Pattern 4: Named publications (always attributed regardless of context)
    r'(Gourmet\s+Magazine|Gault\s*[&\xb7]\s*Millau|Michelin\s+Guide|'
    r'New York Times|Le Monde|Le Figaro|The Guardian|Forbes|'
    r'Cond[eé]\s+Nast|National Geographic|Time Magazine|BBC|Reuters)'
    r')',
    re.I
)


def _has_attributed_quote(text: str) -> Optional[str]:
    """Detect if a passage contains a quote attributed to a named person/publication.

    Returns the attribution target (person/publication name) or None.
    """
    m = _ATTRIBUTION_RE.search(text)
    if m:
        # Return whichever group matched
        return m.group(1) or m.group(2) or m.group(3) or m.group(4)
    # Also check for quoted text followed by a citation
    if re.search(r'"[^"]{10,}"', text):
        # Has a substantial quote — check if there's a proper noun nearby
        if re.search(r'"[^"]+".*?[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}', text):
            # There's a quoted passage with a proper noun after it
            names = re.findall(r'([A-Z][a-z]{2,}\s+[A-Z][a-z]{2,})', text)
            if names:
                return names[-1]  # Last proper noun is likely the attributee
    return None


def _verify_attribution(
    passage_text: str,
    attribution: str,
    stop_title: str,
    city: str,
) -> Tuple[bool, str]:
    """Attempt to verify an attributed quote against a primary source.

    Returns (verified, reason).
    If we can't find the primary source, the passage is DROPPED.
    """
    import requests as _http

    serp_key = os.environ.get("SERP_API_KEY") or os.environ.get("SERPAPI_KEY")
    if not serp_key:
        return (False, "no_api_key_for_verification")

    # Build a verification query: "attribution_source" + key phrase from quote
    # Extract the quoted text
    quotes = re.findall(r'"([^"]+)"', passage_text)
    key_phrase = quotes[0][:50] if quotes else passage_text[:50]

    query = f'"{attribution}" "{key_phrase[:30]}"'

    headers = {"X-API-KEY": serp_key, "Content-Type": "application/json"}
    payload = {"q": query, "num": 5}

    try:
        resp = _http.post(
            "https://google.serper.dev/search",
            json=payload,
            headers=headers,
            timeout=12,
        )
        if resp.status_code == 200:
            data = resp.json()
            organic = data.get("organic", [])
            # Check if any result is from a primary/authoritative source
            for result in organic[:5]:
                url = result.get("link", "")
                snippet = result.get("snippet", "")
                domain = urlparse(url).netloc.lower()

                # Primary source: the publication itself, or a major reference
                is_primary = any(p in domain for p in [
                    'gourmet.com', 'gaultmillau', 'michelin', 'nytimes',
                    'lemonde', 'lefigaro', 'theguardian', 'forbes',
                    'condenast', 'bbc.', 'reuters',
                    'wikipedia.org', 'books.google',
                ])
                # Also accept if snippet actually contains similar wording
                if is_primary and _normalize(attribution) in _normalize(snippet):
                    return (True, f"verified_via:{domain}")

            # No primary source found — attribution unverified
            return (False, f"no_primary_source_found_for:{attribution}")

        elif resp.status_code == 429:
            return (False, "rate_limited_cannot_verify")
    except Exception as e:
        return (False, f"verification_error:{e}")

    return (False, "search_failed")


# ─── Core interpretive search ────────────────────────────────────────────────

def _search_interpretive(query: str) -> List[Dict]:
    """Execute a single interpretive Serper query.

    Returns list of {title, url, snippet} results.
    """
    import requests as _http

    serp_key = os.environ.get("SERP_API_KEY") or os.environ.get("SERPAPI_KEY")
    if not serp_key:
        logger.warning("[INTERPRETIVE] No SERP_API_KEY — cannot search")
        return []

    headers = {"X-API-KEY": serp_key, "Content-Type": "application/json"}
    payload = {"q": query, "num": 10}

    try:
        resp = _http.post(
            "https://google.serper.dev/search",
            json=payload,
            headers=headers,
            timeout=12,
        )
        if resp.status_code == 200:
            data = resp.json()
            results = []
            for r in data.get("organic", [])[:10]:
                results.append({
                    'title': r.get("title", ""),
                    'url': r.get("link", ""),
                    'snippet': r.get("snippet", ""),
                })
            # Also include knowledge graph if present
            kg = data.get("knowledgeGraph", {})
            if kg and kg.get("description"):
                results.append({
                    'title': kg.get("title", "Knowledge Graph"),
                    'url': kg.get("website", ""),
                    'snippet': kg.get("description", ""),
                })
            return results
        elif resp.status_code == 429:
            logger.warning("[INTERPRETIVE] Serper 429 — rate limited")
            raise RuntimeError("Serper rate limited (429)")
        else:
            logger.warning(f"[INTERPRETIVE] Serper {resp.status_code}")
            return []
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning(f"[INTERPRETIVE] Search error: {e}")
        return []


# ─── Source tier classification ──────────────────────────────────────────────

def _classify_source_tier(url: str) -> int:
    """Classify URL trust tier (1=encyclopedic, 2=press/guides, 3=general, 0=rejected)."""
    domain = urlparse(url).netloc.lower()
    if domain.startswith('www.'):
        domain = domain[4:]

    # Rejected
    rejected = ('pinterest.', 'facebook.', 'instagram.', 'twitter.',
                'youtube.', 'tiktok.', 'reddit.', 'yelp.', 'tripadvisor.')
    if any(r in domain for r in rejected):
        return 0

    # Tier 1: encyclopedic
    if any(t in domain for t in ('wikipedia.org', 'britannica.com', 'wikidata.org')):
        return 1
    if any(domain.endswith(s) for s in ('.gov', '.edu', '.gouv.fr', '.ac.uk')):
        return 1

    # Tier 2: press, guides, tourism offices
    tier2 = ('gaultmillau', 'michelin', 'nytimes', 'lemonde', 'lefigaro',
             'theguardian', 'forbes', 'timeout', 'eater', 'nicematin',
             'france24', 'bonappetit', 'saveur', 'tourisme', 'condenast',
             'bbc.', 'reuters', 'thefork', 'nicetourisme')
    if any(t in domain for t in tier2):
        return 2

    return 3


# ─── Main enrichment pipeline ────────────────────────────────────────────────

def enrich_stop_interpretive(
    stop_title: str,
    venue_kind: str,
    city: str,
    country: str = "",
    verify_attributions: bool = True,
) -> Dict:
    """Run interpretive enrichment for a single stop.

    1. Build 2 interpretive questions.
    2. Search each via Serper.
    3. Extract fact-carrying passages.
    4. Verify or drop attributed quotes.
    5. Return surviving passages with source URLs.

    Returns:
        {
            'passages': [{text, url, tier, verified}],
            'queries_issued': int,
            'dropped_attributions': [{text, attribution, reason}],
            'questions_asked': [str],
        }
    """
    result = {
        'passages': [],
        'queries_issued': 0,
        'dropped_attributions': [],
        'questions_asked': [],
    }

    questions = build_interpretive_questions(stop_title, venue_kind, city, country)
    result['questions_asked'] = questions

    seen_texts: Set[str] = set()
    all_candidate_passages: List[Dict] = []

    for question in questions:
        search_results = _search_interpretive(question)
        result['queries_issued'] += 1
        time.sleep(0.3)  # Rate-limit courtesy

        for sr in search_results:
            snippet = sr.get('snippet', '')
            url = sr.get('url', '')

            if not snippet or len(snippet) < 40:
                continue

            # Dedup
            text_key = _normalize(snippet)[:80]
            if text_key in seen_texts:
                continue
            seen_texts.add(text_key)

            # Reject reviews/atmospherics
            if _is_atmospheric_or_review(snippet):
                continue

            # Must mention the stop
            if not _mentions_stop(snippet, stop_title):
                continue

            # Must carry a verifiable fact
            if not _carries_verifiable_fact(snippet):
                continue

            # Source tier — reject tier 0
            tier = _classify_source_tier(url)
            if tier == 0:
                continue

            all_candidate_passages.append({
                'text': snippet[:500],
                'url': url,
                'tier': tier,
            })

    # ─── Attribution verification ────────────────────────────────────────
    for passage in all_candidate_passages:
        attribution = _has_attributed_quote(passage['text'])

        if attribution and verify_attributions:
            # This passage attributes content to a named source — MUST verify
            verified, reason = _verify_attribution(
                passage['text'], attribution, stop_title, city
            )
            result['queries_issued'] += 1

            if verified:
                passage['verified'] = True
                passage['verification_note'] = reason
                result['passages'].append(passage)
            else:
                # DROP the passage — D233 rule
                result['dropped_attributions'].append({
                    'text': passage['text'][:200],
                    'attribution': attribution,
                    'reason': reason,
                })
        else:
            # No attribution — passage carries its own facts, keep it
            passage['verified'] = False  # means: no attribution to verify
            result['passages'].append(passage)

    return result


# ─── Database storage ────────────────────────────────────────────────────────

def store_interpretive_corpus(
    stop_title: str,
    venue_name: str,
    passages: List[Dict],
    db_conn,
) -> int:
    """Store interpretive enrichment passages into stop_corpus.

    APPENDS to existing corpus (does not overwrite).
    Returns: number of new passages added.
    """
    if not passages:
        return 0

    cur = db_conn.cursor()

    # Read existing corpus
    cur.execute(
        "SELECT passages_json, source_pages, passage_count FROM stop_corpus "
        "WHERE venue_name = %s AND stop_title = %s",
        (venue_name, stop_title)
    )
    row = cur.fetchone()

    existing_passages = []
    existing_sources = []
    if row:
        existing_passages = row[0] if isinstance(row[0], list) else (json.loads(row[0]) if row[0] else [])
        existing_sources = row[1] if isinstance(row[1], list) else (json.loads(row[1]) if row[1] else [])

    # Dedup against existing text
    existing_texts = {_normalize(p.get('text', ''))[:80] for p in existing_passages}

    new_passages = []
    new_sources = []
    seen_urls: Set[str] = set()

    for p in passages:
        text_key = _normalize(p['text'])[:80]
        if text_key in existing_texts:
            continue
        existing_texts.add(text_key)

        new_passages.append({
            'text': p['text'],
            'url': p.get('url', ''),
            'tier': p.get('tier', 3),
            'type': 'interpretive_enrichment',
            'verified': p.get('verified', False),
        })

        url = p.get('url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            new_sources.append({
                'url': url,
                'tier': p.get('tier', 3),
                'type': 'interpretive_enrichment',
                'title': f'{stop_title} — interpretive search',
                'tier_reason': 'Interpretive enrichment (LOCAL-332)',
            })

    if not new_passages:
        cur.close()
        return 0

    # Merge
    merged_passages = existing_passages + new_passages
    merged_sources = existing_sources + new_sources
    new_count = len(merged_passages)

    passages_json = json.dumps(merged_passages, ensure_ascii=False)
    sources_json = json.dumps(merged_sources, ensure_ascii=False)

    if row:
        # Update existing row
        cur.execute("""
            UPDATE stop_corpus
            SET passages_json = %s::jsonb,
                source_pages = %s::jsonb,
                passage_count = %s
            WHERE venue_name = %s AND stop_title = %s
        """, (passages_json, sources_json, new_count, venue_name, stop_title))
    else:
        # Insert new row
        cur.execute("""
            INSERT INTO stop_corpus (venue_name, stop_title, passages_json, source_pages, passage_count)
            VALUES (%s, %s, %s::jsonb, %s::jsonb, %s)
        """, (venue_name, stop_title, passages_json, sources_json, new_count))

    db_conn.commit()
    cur.close()

    return len(new_passages)


# ─── Integration: enrich all verified stops ──────────────────────────────────

def enrich_verified_stops(
    verdicts: List[Dict],
    venue_name: str,
    venue_kind: str,
    city: str,
    country: str,
    db_conn,
) -> Dict:
    """Run interpretive enrichment on all verified stops.

    Called after the existence gate. Adds interpretive corpus for stops that
    passed verification.

    Args:
        verdicts: List of verdict dicts from the existence gate.
        venue_name: The venue_name used for stop_corpus matching.
        venue_kind: Type of venue (restaurant, museum, etc.).
        city: City name.
        country: Country name.
        db_conn: psycopg2 connection.

    Returns:
        {
            'total_enriched': int,
            'total_passages_added': int,
            'total_queries': int,
            'dropped_attributions': [{stop, text, attribution, reason}],
            'details': [{stop_title, passages_added, queries, questions_asked}],
        }
    """
    summary = {
        'total_enriched': 0,
        'total_passages_added': 0,
        'total_queries': 0,
        'dropped_attributions': [],
        'details': [],
    }

    for verdict in verdicts:
        if not verdict.get('verified'):
            continue

        stop_title = verdict['stop_title']

        enrichment = enrich_stop_interpretive(
            stop_title=stop_title,
            venue_kind=venue_kind,
            city=city,
            country=country,
            verify_attributions=True,
        )

        summary['total_queries'] += enrichment['queries_issued']

        # Store passages
        passages_added = store_interpretive_corpus(
            stop_title=stop_title,
            venue_name=venue_name,
            passages=enrichment['passages'],
            db_conn=db_conn,
        )

        summary['total_passages_added'] += passages_added
        if passages_added > 0:
            summary['total_enriched'] += 1
            print(f"    [INTERPRETIVE] {stop_title!r}: +{passages_added} passages "
                  f"({enrichment['queries_issued']} queries)")

        # Record drops
        for drop in enrichment['dropped_attributions']:
            summary['dropped_attributions'].append({
                'stop': stop_title,
                **drop,
            })
            print(f"    [INTERPRETIVE] DROPPED attributed quote for {stop_title!r}: "
                  f"{drop['attribution']!r} — {drop['reason']}")

        summary['details'].append({
            'stop_title': stop_title,
            'passages_added': passages_added,
            'queries': enrichment['queries_issued'],
            'questions_asked': enrichment['questions_asked'],
            'dropped': len(enrichment['dropped_attributions']),
        })

    # Summary
    print(f"    [INTERPRETIVE] Summary: {summary['total_enriched']} stops enriched, "
          f"+{summary['total_passages_added']} passages, "
          f"{summary['total_queries']} queries issued, "
          f"{len(summary['dropped_attributions'])} attributions dropped")

    return summary
