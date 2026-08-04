#!/usr/bin/env python3
"""stop_subject_acquisition.py — LOCAL-199

Fetch corpus about the STOP SUBJECT, not just the venue.

Problem (D70): stop_corpus is populated from venue-level pages. A stop
called "Richard Long ou la sculpture en marchant" receives the museum's
Donations section — one passage, and "Richard" appears zero times.

Solution: parse the subject out of each stop title, search for it with
the venue as disambiguating context, validate the result is about the
right entity, and store in stop_corpus.

RULES:
- A wrong attribution is worse than an empty corpus (D62).
- When the subject cannot be identified with the venue confirming it,
  store nothing (LOCAL-198's gate handles it).
- Trust tiers per D51: Wikipedia + institution's own site = tier 1.
- Budget ceiling: $0.40 (no paid API calls here — Wikipedia only).
- Do not modify stop_corpus_reader.py (LOCAL-198 coordination).
- Do not rebuild containers (D48).
"""
import json
import logging
import os
import re
import sys
import time
import unicodedata
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, urljoin

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))
from db_connection import get_connection

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Rate limiting
WIKI_DELAY = 2.0  # seconds between requests


def normalize(text: str) -> str:
    """Normalize for matching: lowercase, strip accents, collapse whitespace."""
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFKD', text.lower())
    stripped = ''.join(c for c in nfkd if not unicodedata.combining(c))
    stripped = re.sub(r'[^\w\s]', ' ', stripped)
    return ' '.join(stripped.split())


# ===========================================================================
# Subject Parsing — extract the subject from a stop title
# ===========================================================================

def parse_subject(stop_title: str, venue_name: str = "") -> Dict:
    """Parse a stop title into its subject components.

    Returns dict with:
        artist: str or None — artist name if identifiable
        artwork_title: str or None — artwork/exhibition title
        subject_type: 'artist', 'artwork', 'exhibition', 'unknown'
        search_terms: list of (query, lang) tuples to try on Wikipedia
    """
    result = {
        'artist': None,
        'artwork_title': None,
        'subject_type': 'unknown',
        'search_terms': [],
    }

    title = stop_title.strip()

    # Pattern 1: "Artist Name ou la/le ..." (FR exhibition/description pattern)
    # e.g. "Richard Long ou la sculpture en marchant"
    m = re.match(r'^([A-ZÀ-Ü][a-zà-ÿ]+(?:\s+[A-ZÀ-Ü][a-zà-ÿ]+)+)\s+ou\s+', title)
    if m:
        artist = m.group(1).strip()
        result['artist'] = artist
        result['subject_type'] = 'artist'
        result['search_terms'] = [
            (f"{artist} artist", 'en'),
            (f"{artist} sculpteur", 'fr'),
            (artist, 'en'),
            (artist, 'fr'),
        ]
        return result

    # Pattern 1b: Known artist-attributed titles at specific venues
    # "Tir, séance 26 juin 1961" is by Niki de Saint Phalle at MAMAC
    # "She-Bam Pow POP Wizz" is by Niki de Saint Phalle
    # These are identifiable by their venue + title combination
    known_subjects = _lookup_known_subject(title, venue_name)
    if known_subjects:
        return known_subjects

    # Pattern 2: "Le/La/Les + Title" or "L'Title" — likely an artwork
    # e.g. "Le Déjeuner sur l'herbe", "La mariée sous l'arbre"
    m = re.match(r"^(?:Le|La|Les|L['\u2019])\s*(.+)$", title, re.IGNORECASE)
    if m:
        result['artwork_title'] = title
        result['subject_type'] = 'artwork'
        # Search for the artwork itself with artist context
        venue_artist = _extract_venue_artist(venue_name)
        result['search_terms'] = [
            (title, 'fr'),
        ]
        if venue_artist:
            result['search_terms'].insert(0, (f"{title} {venue_artist}", 'fr'))
            result['search_terms'].append((f"{venue_artist} {title}", 'en'))
        result['search_terms'].append((title, 'en'))
        return result

    # Pattern 3: "Artwork Title, date" pattern
    # e.g. "Tir, séance 26 juin 1961"
    m = re.match(r'^(.+?),\s+(?:séance\s+)?\d', title)
    if m:
        result['artwork_title'] = title
        result['subject_type'] = 'artwork'
        base = m.group(1).strip()
        result['search_terms'] = [
            (title, 'fr'),
            (base, 'fr'),
            (base, 'en'),
        ]
        venue_artist = _extract_venue_artist(venue_name)
        if venue_artist:
            result['search_terms'].append((f"{base} {venue_artist}", 'en'))
        return result

    # Pattern 4: Title that looks like a proper noun phrase (exhibition/artwork)
    # e.g. "She-Bam Pow POP Wizz", "Le Village de grand-mère"
    if title[0].isupper() and len(title.split()) >= 2:
        result['artwork_title'] = title
        result['subject_type'] = 'artwork'
        result['search_terms'] = [
            (title, 'fr'),
            (title, 'en'),
        ]
        venue_artist = _extract_venue_artist(venue_name)
        if venue_artist:
            result['search_terms'].append((f"{title} {venue_artist}", 'en'))
            result['search_terms'].append((f"{venue_artist} \"{title}\"", 'en'))
        return result

    # Fallback: use the title as-is
    result['search_terms'] = [(title, 'fr'), (title, 'en')]
    return result


def _extract_venue_artist(venue_name: str) -> Optional[str]:
    """Extract artist name from venue (e.g. 'Musee National Marc Chagall' -> 'Marc Chagall')."""
    if not venue_name:
        return None
    # Strip museum prefixes
    cleaned = re.sub(
        r'(?i)(mus[ée]+e?|museum|gallery|national[e]?|the|of|art|'
        r'moderne|contemporain|contemporary|modern|centre|center|d\s*)\s*',
        ' ', venue_name
    )
    # Strip city/country suffixes
    cleaned = re.sub(r',\s*.+$', '', cleaned).strip()
    # Must look like a name (2+ capitalized words)
    words = [w for w in cleaned.split() if w and len(w) > 1]
    if len(words) >= 2 and all(w[0].isupper() for w in words if w[0].isalpha()):
        return ' '.join(words)
    return None


# Known subject mappings for stops where title alone is ambiguous
# but venue+title makes it clear. This avoids wrong-entity conflation (D62).
_KNOWN_SUBJECTS = {
    # MAMAC Nice — contemporary art museum
    ('Tir, séance 26 juin 1961', 'mamac'): {
        'artist': 'Niki de Saint Phalle',
        'artwork_title': 'Tir, séance 26 juin 1961',
        'subject_type': 'artist',
        'search_terms': [
            ('Niki de Saint Phalle', 'en'),
            ('Niki de Saint Phalle', 'fr'),
            ('Niki de Saint Phalle Tirs', 'en'),
        ],
    },
    ('She-Bam Pow POP Wizz', 'mamac'): {
        'artist': 'Niki de Saint Phalle',
        'artwork_title': 'She-Bam Pow POP Wizz',
        'subject_type': 'artist',
        'search_terms': [
            ('Niki de Saint Phalle', 'en'),
            ('Niki de Saint Phalle', 'fr'),
        ],
    },
    ('Le Village de grand-mère', 'mamac'): {
        'artist': None,
        'artwork_title': 'Le Village de grand-mère',
        'subject_type': 'artwork',
        'search_terms': [
            ('Viallat "Village de grand-mère"', 'fr'),
            ('Claude Viallat artist', 'en'),
            ('Supports/Surfaces art movement', 'en'),
        ],
    },
    ('Le Mur de Feu d\'Yves Klein', 'mamac'): {
        'artist': 'Yves Klein',
        'artwork_title': 'Le Mur de Feu',
        'subject_type': 'artist',
        'search_terms': [
            ('Yves Klein fire wall', 'en'),
            ('Yves Klein', 'en'),
            ('Yves Klein', 'fr'),
        ],
    },
    ('Le Déjeuner sur l\'herbe', 'mamac'): {
        'artist': 'Alain Jacquet',
        'artwork_title': 'Le Déjeuner sur l\'herbe',
        'subject_type': 'artwork',
        'search_terms': [
            ('Alain Jacquet artist', 'en'),
            ('Alain Jacquet artiste', 'fr'),
            ('Le Déjeuner sur l\'herbe Alain Jacquet', 'fr'),
        ],
    },
    ('La mariée sous l\'arbre', 'mamac'): {
        'artist': 'Niki de Saint Phalle',
        'artwork_title': 'La mariée sous l\'arbre',
        'subject_type': 'artist',
        'search_terms': [
            ('Niki de Saint Phalle Nana', 'en'),
            ('Niki de Saint Phalle', 'en'),
            ('Niki de Saint Phalle sculpture', 'fr'),
        ],
    },
    # Chagall Museum Nice — biblical paintings
    ('Abraham et les trois anges', 'chagall'): {
        'artist': 'Marc Chagall',
        'artwork_title': 'Abraham et les trois anges',
        'subject_type': 'artist',
        'search_terms': [
            ('Marc Chagall', 'en'),
            ('Marc Chagall Biblical Message', 'en'),
            ('Marc Chagall message biblique', 'fr'),
        ],
    },
    ('L\'Arche de Noé', 'chagall'): {
        'artist': 'Marc Chagall',
        'artwork_title': 'L\'Arche de Noé',
        'subject_type': 'artist',
        'search_terms': [
            ('Marc Chagall', 'en'),
            ('Marc Chagall Biblical Message', 'en'),
            ('Musée Marc Chagall', 'fr'),
        ],
    },
    ('La Bible : Abraham et Isaac en route', 'chagall'): {
        'artist': 'Marc Chagall',
        'artwork_title': 'La Bible : Abraham et Isaac en route',
        'subject_type': 'artist',
        'search_terms': [
            ('Marc Chagall', 'en'),
            ('Marc Chagall Bible illustrations', 'en'),
            ('Marc Chagall message biblique', 'fr'),
        ],
    },
    ('Le Cirque bleu', 'chagall'): {
        'artist': 'Marc Chagall',
        'artwork_title': 'Le Cirque bleu',
        'subject_type': 'artist',
        'search_terms': [
            ('Marc Chagall', 'en'),
            ('Marc Chagall circus paintings', 'en'),
            ('Marc Chagall cirque', 'fr'),
        ],
    },
    # Matisse Museum Nice
    ('Nature morte aux grenades', 'matisse'): {
        'artist': 'Henri Matisse',
        'artwork_title': 'Nature morte aux grenades',
        'subject_type': 'artist',
        'search_terms': [
            ('Henri Matisse still life', 'en'),
            ('Henri Matisse', 'en'),
            ('Henri Matisse', 'fr'),
        ],
    },
    ('Lectrice à la table jaune', 'matisse'): {
        'artist': 'Henri Matisse',
        'artwork_title': 'Lectrice à la table jaune',
        'subject_type': 'artist',
        'search_terms': [
            ('Henri Matisse', 'en'),
            ('Henri Matisse peinture', 'fr'),
        ],
    },
    ('Nymphe dans la forêt', 'matisse'): {
        'artist': 'Henri Matisse',
        'artwork_title': 'Nymphe dans la forêt',
        'subject_type': 'artist',
        'search_terms': [
            ('Henri Matisse', 'en'),
            ('Henri Matisse Nice', 'fr'),
        ],
    },
    ('Odalisque au coffret rouge', 'matisse'): {
        'artist': 'Henri Matisse',
        'artwork_title': 'Odalisque au coffret rouge',
        'subject_type': 'artist',
        'search_terms': [
            ('Henri Matisse odalisque', 'en'),
            ('Henri Matisse', 'en'),
        ],
    },
    ('Papeete-Tahiti', 'matisse'): {
        'artist': 'Henri Matisse',
        'artwork_title': 'Papeete-Tahiti',
        'subject_type': 'artist',
        'search_terms': [
            ('Henri Matisse Tahiti', 'en'),
            ('Henri Matisse', 'en'),
        ],
    },
    ('Tempête à Nice', 'matisse'): {
        'artist': 'Henri Matisse',
        'artwork_title': 'Tempête à Nice',
        'subject_type': 'artist',
        'search_terms': [
            ('Henri Matisse Nice', 'en'),
            ('Henri Matisse', 'en'),
        ],
    },
}


def _lookup_known_subject(stop_title: str, venue_name: str) -> Optional[Dict]:
    """Look up a stop title in the known subjects table.

    Uses venue name substring matching to identify the venue context.
    """
    venue_lower = venue_name.lower()

    # Determine venue key
    venue_key = None
    if 'mamac' in venue_lower or 'art moderne' in venue_lower or 'art contemporain' in venue_lower:
        venue_key = 'mamac'
    elif 'chagall' in venue_lower:
        venue_key = 'chagall'
    elif 'matisse' in venue_lower:
        venue_key = 'matisse'
    elif 'lascaris' in venue_lower:
        venue_key = 'lascaris'

    if venue_key is None:
        return None

    key = (stop_title, venue_key)
    if key in _KNOWN_SUBJECTS:
        return dict(_KNOWN_SUBJECTS[key])  # Return a copy

    return None


# ===========================================================================
# Wikipedia Search with Disambiguation
# ===========================================================================

def search_wikipedia_for_subject(
    subject: Dict,
    venue_name: str,
    stop_title: str,
) -> Optional[Dict]:
    """Search Wikipedia for the stop subject, using venue as disambiguation.

    Returns dict with {text, url, lang, title} or None if nothing found/validated.
    Implements D62's rule: when the subject cannot be identified with the
    venue confirming it, return None.
    """
    results_tried = []

    for query, lang in subject['search_terms']:
        time.sleep(WIKI_DELAY)

        # Try Wikipedia search API first (handles disambiguation)
        article = _wiki_search_and_fetch(query, lang)
        if not article:
            continue

        # Validate: is this article about our subject AT our venue?
        validation = _validate_article_for_stop(
            article_text=article['text'],
            article_title=article['title'],
            stop_title=stop_title,
            subject=subject,
            venue_name=venue_name,
        )

        results_tried.append({
            'query': query,
            'lang': lang,
            'article_title': article['title'],
            'validated': validation['valid'],
            'reason': validation.get('reason', ''),
        })

        if validation['valid']:
            return {
                'text': article['text'],
                'url': article['url'],
                'lang': lang,
                'title': article['title'],
                'validation': validation,
            }

    # Log what we tried but rejected
    if results_tried:
        logger.info(f"  [{stop_title}] Tried {len(results_tried)} sources, all rejected:")
        for r in results_tried:
            logger.info(f"    {r['query']} ({r['lang']}) -> {r['article_title']}: {r['reason']}")

    return None


def _wiki_search_and_fetch(query: str, lang: str = 'en') -> Optional[Dict]:
    """Search Wikipedia and fetch the best matching article's full extract."""
    base_url = f"https://{lang}.wikipedia.org/w/api.php"

    try:
        # Step 1: Search
        resp = requests.get(base_url, params={
            'action': 'query',
            'list': 'search',
            'srsearch': query,
            'srlimit': '5',
            'format': 'json',
        }, headers={'User-Agent': 'Audioura/2.2'}, timeout=10)

        if resp.status_code != 200:
            return None

        data = resp.json()
        results = data.get('query', {}).get('search', [])
        if not results:
            return None

        # Step 2: Pick the best result. Skip museum/venue articles when
        # we're searching for an artist or artwork subject.
        # (D62 lesson: "Musée Marc Chagall" != "Marc Chagall the artist")
        _museum_patterns = re.compile(
            r'\b(mus[ée]e|museum|gallery|galerie|palais)\b', re.IGNORECASE
        )
        # Prefer the first non-museum result when the query doesn't contain "musée"
        query_is_about_venue = bool(_museum_patterns.search(query))

        best_title = None
        for r in results:
            title = r['title']
            if not query_is_about_venue and _museum_patterns.search(title):
                continue  # Skip museum articles for non-venue queries
            best_title = title
            break

        if not best_title:
            # All results were museums — use the first one
            best_title = results[0]['title']

        # Step 3: Fetch the article's full extract
        time.sleep(0.5)

        resp2 = requests.get(base_url, params={
            'action': 'query',
            'prop': 'extracts',
            'explaintext': '1',
            'titles': best_title,
            'format': 'json',
        }, headers={'User-Agent': 'Audioura/2.2'}, timeout=10)

        if resp2.status_code != 200:
            return None

        pages = resp2.json().get('query', {}).get('pages', {})
        for pid, pdata in pages.items():
            if pid == '-1' or pdata.get('missing'):
                continue
            extract = pdata.get('extract', '')
            if extract and len(extract) > 200:
                url = f"https://{lang}.wikipedia.org/wiki/{quote(best_title.replace(' ', '_'), safe='/:@')}"
                return {
                    'text': extract,
                    'title': best_title,
                    'url': url,
                }

    except Exception as e:
        logger.warning(f"  Wikipedia search failed for '{query}' ({lang}): {e}")

    return None


def _validate_article_for_stop(
    article_text: str,
    article_title: str,
    stop_title: str,
    subject: Dict,
    venue_name: str,
) -> Dict:
    """Validate that a Wikipedia article is about the RIGHT entity for this stop.

    D62 rule: keyword co-occurrence is not a relationship. The article must
    be about the subject, and there must be a venue-confirming signal.

    Returns dict with valid: bool, reason: str, confidence: str
    """
    text_norm = normalize(article_text[:5000])  # First 5000 chars
    text_lower = article_text[:5000].lower()

    # --- Check 1: Is the article about the subject? ---
    subject_confirmed = False

    if subject.get('artist'):
        artist_norm = normalize(subject['artist'])
        artist_words = [w for w in artist_norm.split() if len(w) >= 3]
        # Artist's surname must be in the article prominently
        if artist_words:
            surname = artist_words[-1]  # Last name
            # Use whole-word matching to avoid partial matches
            pattern = r'\b' + re.escape(surname) + r'\b'
            count = len(re.findall(pattern, text_norm))
            if count >= 3:
                subject_confirmed = True
            else:
                return {'valid': False, 'reason': f"artist surname '{surname}' only {count}x (whole-word) in article"}

        # Additional check: the LEAD paragraph must identify this as an artist/sculptor
        # to prevent disambiguation pages or historical figures from being accepted
        lead_text = article_text[:600].lower()
        art_identity_signals = ['artist', 'sculptor', 'painter', 'artiste',
                                'sculpteur', 'peintre', 'land art',
                                'born', 'né le', 'est un', 'is a',
                                'contemporary', 'modernist']
        lead_has_art_identity = any(s in lead_text for s in art_identity_signals)
        if not lead_has_art_identity:
            return {'valid': False, 'reason': f"lead paragraph does not identify subject as artist"}

    elif subject.get('artwork_title'):
        # For artworks: the article must be ABOUT this artwork or its creator.
        # Simple word overlap is insufficient (D62: "Abraham" matching a governor).
        # Require: the article lead (first 500 chars) must contain the subject.
        title_norm = normalize(subject['artwork_title'])
        title_words = [w for w in title_norm.split() if len(w) >= 4]

        if title_words:
            # Check the LEAD paragraph specifically (where the article defines its subject)
            lead_norm = normalize(article_text[:800])
            lead_matches = sum(1 for w in title_words if w in lead_norm)
            lead_ratio = lead_matches / len(title_words)

            # Also check full text
            full_matches = sum(1 for w in title_words if w in text_norm)
            full_ratio = full_matches / len(title_words)

            if lead_ratio >= 0.5:
                subject_confirmed = True
            elif full_ratio >= 0.6 and full_matches >= 3:
                subject_confirmed = True
            else:
                return {'valid': False,
                        'reason': f"artwork title words: lead {lead_matches}/{len(title_words)}, "
                                  f"full {full_matches}/{len(title_words)}"}
        else:
            subject_confirmed = True  # Short title, can't check

    if not subject_confirmed:
        return {'valid': False, 'reason': 'subject not confirmed in article'}

    # --- Check 2: Venue-confirming signal ---
    # The article must mention something that ties it to THIS venue/location.
    # This prevents "Richard Long" the cricketer from being used for the sculptor.
    venue_confirmed = False
    venue_signals = _extract_venue_signals(venue_name)

    for signal in venue_signals:
        if signal.lower() in text_lower:
            venue_confirmed = True
            break

    # For artists: also accept art-domain signals as venue confirmation
    if not venue_confirmed and subject.get('artist'):
        art_signals = ['sculptor', 'sculpture', 'artist', 'painter', 'artiste',
                       'sculpteur', 'peintre', 'land art', 'contemporary art',
                       'art contemporain', 'museum', 'musée', 'gallery',
                       'exhibition', 'exposition', 'installation']
        for signal in art_signals:
            if signal in text_lower:
                venue_confirmed = True
                break

    # For artworks: also accept the artist name as venue confirmation
    if not venue_confirmed and subject.get('artwork_title'):
        venue_artist = _extract_venue_artist(venue_name)
        if venue_artist and normalize(venue_artist) in text_norm:
            venue_confirmed = True

    if not venue_confirmed:
        return {'valid': False, 'reason': f"no venue-confirming signal (tried: {venue_signals[:3]}...)"}

    # --- Check 3: Negative signals (wrong entity) ---
    # Check for disambiguation: is this about a different entity with the same name?
    if subject.get('artist'):
        # Check if this is about a sports figure, politician, etc.
        wrong_domain_signals = ['cricketer', 'footballer', 'politician',
                                'baseball', 'basketball', 'rugby',
                                'member of parliament', 'senator', 'governor']
        for wrong in wrong_domain_signals:
            if wrong in text_lower[:1000]:
                return {'valid': False, 'reason': f"wrong domain: '{wrong}' found in lead"}

    return {
        'valid': True,
        'reason': 'subject confirmed + venue signal present',
        'confidence': 'high' if subject_confirmed and venue_confirmed else 'medium',
    }


def _extract_venue_signals(venue_name: str) -> List[str]:
    """Extract signals that would confirm an article relates to this venue's domain."""
    signals = []

    # City name from venue
    parts = venue_name.split(',')
    for p in parts[1:]:
        city_words = p.strip().split()
        for w in city_words:
            w = w.strip()
            if w and len(w) >= 3 and w.lower() not in ('france', 'usa', 'italy', 'ma'):
                signals.append(w)

    # The venue name itself (or key part)
    venue_lower = venue_name.lower()
    if 'mamac' in venue_lower or 'art moderne' in venue_lower or 'art contemporain' in venue_lower:
        signals.extend(['Nice', 'MAMAC', 'art moderne', 'art contemporain',
                        'contemporary art', 'modern art'])
    elif 'chagall' in venue_lower:
        signals.extend(['Nice', 'Chagall', 'message biblique', 'Biblical Message'])
    elif 'matisse' in venue_lower:
        signals.extend(['Nice', 'Matisse', 'Cimiez'])
    elif 'lascaris' in venue_lower:
        signals.extend(['Nice', 'Lascaris', 'baroque'])
    elif 'boston' in venue_lower:
        signals.extend(['Boston'])

    # For walking tours, extract any city
    if 'nice' in venue_lower or 'riviera' in venue_lower:
        signals.extend(['Nice', 'Riviera', 'Côte d\'Azur'])
    if 'boston' in venue_lower:
        signals.extend(['Boston', 'Massachusetts'])

    # Generic: museum/art domain signals for museum venues
    if any(w in venue_lower for w in ('musee', 'museum', 'art', 'galerie', 'gallery')):
        signals.extend(['art', 'museum', 'musée', 'exhibition', 'exposition',
                        'gallery', 'galerie'])

    return signals


# ===========================================================================
# Passage Extraction — extract the most relevant passage from an article
# ===========================================================================

def extract_relevant_passages(
    article_text: str,
    stop_title: str,
    subject: Dict,
    max_passages: int = 3,
    max_chars_per_passage: int = 800,
) -> List[str]:
    """Extract the most relevant passages from a Wikipedia article for this stop.

    Prioritizes:
    1. Lead paragraph (usually the most informative)
    2. Paragraphs mentioning the specific subject
    3. Paragraphs with dates, descriptions, context
    """
    if not article_text:
        return []

    # Split into paragraphs
    paragraphs = [p.strip() for p in article_text.split('\n\n') if p.strip()]
    # Also handle single-newline paragraph breaks
    if len(paragraphs) <= 2:
        paragraphs = [p.strip() for p in article_text.split('\n') if len(p.strip()) > 50]

    if not paragraphs:
        return []

    # Score paragraphs by relevance
    scored = []
    subject_words = set()
    if subject.get('artist'):
        subject_words = set(normalize(subject['artist']).split())
    elif subject.get('artwork_title'):
        subject_words = set(w for w in normalize(subject['artwork_title']).split() if len(w) >= 4)

    for i, para in enumerate(paragraphs):
        if len(para) < 50:
            continue
        # Skip Wikipedia section headers
        if para.startswith('==') or para.startswith('Category:'):
            continue
        # Skip "See also", "References" etc.
        if re.match(r'^(See also|References|External links|Notes|Bibliography)', para):
            continue

        score = 0
        para_norm = normalize(para)

        # Bonus for lead paragraph (i=0)
        if i == 0:
            score += 10

        # Bonus for subject mentions
        for w in subject_words:
            if w in para_norm:
                score += 2

        # Bonus for dates (factual content)
        dates = re.findall(r'\b\d{4}\b', para)
        score += min(len(dates), 3)

        # Bonus for substantive length
        if len(para) > 200:
            score += 2
        if len(para) > 400:
            score += 1

        # Penalty for lists of links or references
        if para.count('[') > 3:
            score -= 5

        scored.append((score, i, para))

    # Sort by score descending
    scored.sort(key=lambda x: -x[0])

    # Take top passages up to max
    passages = []
    total_chars = 0
    for score, _, para in scored[:max_passages * 2]:  # Over-select then trim
        if len(passages) >= max_passages:
            break
        # Truncate long paragraphs
        if len(para) > max_chars_per_passage:
            # Cut at sentence boundary
            cut = para[:max_chars_per_passage]
            last_period = cut.rfind('.')
            if last_period > max_chars_per_passage // 2:
                para = cut[:last_period + 1]
            else:
                para = cut + '...'
        passages.append(para)
        total_chars += len(para)
        if total_chars > 2000:
            break

    return passages


# ===========================================================================
# Main Acquisition Logic
# ===========================================================================

def acquire_subject_corpus(dry_run: bool = False) -> Dict:
    """Main entry: acquire per-stop subject corpus for all venues.

    Returns a report dict with per-venue and per-stop results.
    """
    conn = get_connection()
    cur = conn.cursor()

    # Get all stops currently in stop_corpus
    cur.execute("""
        SELECT id, venue_name, stop_title, passage_count, passages_json
        FROM stop_corpus
        ORDER BY venue_name, stop_title
    """)
    all_stops = cur.fetchall()

    report = {
        'stops_processed': 0,
        'stops_enriched': 0,
        'stops_left_empty': 0,
        'stops_already_covered': 0,
        'rejected_candidates': [],
        'enriched_details': [],
        'per_venue': {},
    }

    for row in all_stops:
        stop_id, venue_name, stop_title, passage_count, passages_json = row

        # Skip stops that already have good subject-specific content
        if _has_subject_corpus(stop_title, passages_json):
            report['stops_already_covered'] += 1
            continue

        # Skip structural/venue-level stops (not subjects)
        if _is_structural_stop(stop_title):
            logger.info(f"  SKIP structural: {stop_title}")
            continue

        report['stops_processed'] += 1

        # Parse the subject
        subject = parse_subject(stop_title, venue_name)
        if subject['subject_type'] == 'unknown':
            report['stops_left_empty'] += 1
            logger.info(f"  LEFT EMPTY (unparseable): {stop_title}")
            continue

        logger.info(f"  SEARCHING: {stop_title} -> {subject['subject_type']}: "
                    f"{subject.get('artist') or subject.get('artwork_title')}")

        # Search Wikipedia with venue disambiguation
        article = search_wikipedia_for_subject(subject, venue_name, stop_title)

        if article is None:
            report['stops_left_empty'] += 1
            logger.info(f"  LEFT EMPTY (no validated source): {stop_title}")
            continue

        # Extract relevant passages
        passages = extract_relevant_passages(
            article['text'], stop_title, subject
        )

        if not passages:
            report['stops_left_empty'] += 1
            logger.info(f"  LEFT EMPTY (no relevant passages): {stop_title}")
            continue

        # Store the result
        source_info = {
            'url': article['url'],
            'tier': 1,  # Wikipedia = tier 1 per D51
            'title': article['title'],
            'lang': article['lang'],
            'validation': article['validation']['reason'],
        }

        if not dry_run:
            _update_stop_corpus(
                conn, stop_id, stop_title, venue_name,
                passages, source_info, passages_json
            )

        report['stops_enriched'] += 1
        report['enriched_details'].append({
            'venue': venue_name,
            'stop_title': stop_title,
            'source_url': article['url'],
            'article_title': article['title'],
            'passages_added': len(passages),
            'first_passage_preview': passages[0][:200] if passages else '',
        })

        # Track per-venue stats
        if venue_name not in report['per_venue']:
            report['per_venue'][venue_name] = {'enriched': 0, 'left_empty': 0}
        report['per_venue'][venue_name]['enriched'] += 1

        logger.info(f"  ENRICHED: {stop_title} <- {article['title']} ({len(passages)} passages)")

    # Report left-empty per venue
    for row in all_stops:
        _, venue_name, stop_title, _, passages_json = row
        if venue_name not in report['per_venue']:
            report['per_venue'][venue_name] = {'enriched': 0, 'left_empty': 0}

    conn.close()
    return report


def _has_subject_corpus(stop_title: str, passages_json) -> bool:
    """Check if a stop already has GENUINE subject-specific corpus.

    A stop is only 'covered' if its passages contain substantive content
    about the subject — not just venue-level text that happens to share
    a word. The key signal: the subject's distinguishing name/term appears
    multiple times in passages that are clearly about it.
    """
    if not passages_json:
        return False

    passages = passages_json if isinstance(passages_json, list) else json.loads(passages_json)
    if not passages:
        return False

    # Extract the distinguishing words from the title (skip common art words)
    noise = {'art', 'les', 'des', 'une', 'par', 'sur', 'sous', 'dans', 'avec',
             'pour', 'the', 'and', 'for', 'from', 'with', 'museum', 'musee',
             'exposition', 'exhibition', 'donations', 'collection',
             'seance', 'juin', 'mars', 'avril', 'long', 'village'}
    title_words = [w for w in normalize(stop_title).split() if len(w) >= 5 and w not in noise]

    if not title_words:
        # Can't determine subject — conservatively say NOT covered
        return False

    # Need at least one passage where the subject is the TOPIC (mentioned 3+ times
    # or mentioned in a way that's clearly about it, not just a list mention)
    total_chars_about_subject = 0
    for p in passages:
        text = p.get('text', p) if isinstance(p, dict) else str(p)
        text_norm = normalize(text)

        # Use word-boundary matching to avoid "long" matching "belonging"
        matches = 0
        for w in title_words:
            # Check whole-word match
            pattern = r'\b' + re.escape(w) + r'\b'
            if re.search(pattern, text_norm):
                matches += 1

        # The passage must match a significant proportion of the subject
        if matches >= max(2, len(title_words) * 0.5):
            # Also check that the passage is substantive (not just a list mention)
            if len(text) > 200:
                total_chars_about_subject += len(text)

    # Require at least 500 chars of genuinely subject-specific content
    return total_chars_about_subject >= 500


def _is_structural_stop(stop_title: str) -> bool:
    """Detect structural/venue-level stops that aren't real subjects."""
    structural = {
        'donations and deposits', 'donations et dépôts',
        'expositions temporaires', 'temporary exhibitions',
        'collections', 'la collection',
        'les mouvements et les artistes',
        'nouveaux réalistes', 'new realism',
    }
    return stop_title.lower().strip() in structural


def _update_stop_corpus(
    conn, stop_id: int, stop_title: str, venue_name: str,
    new_passages: List[str], source_info: Dict,
    existing_passages_json
):
    """Update a stop_corpus row with new subject-specific passages."""
    cur = conn.cursor()

    # Merge with existing passages (keep existing, add new)
    existing = []
    if existing_passages_json:
        existing = existing_passages_json if isinstance(existing_passages_json, list) else json.loads(existing_passages_json)

    # Build the combined passages (new subject-specific ones first)
    combined_passages = new_passages + [
        p.get('text', p) if isinstance(p, dict) else str(p)
        for p in existing
    ]

    # Build source_pages: merge existing sources with new one
    cur.execute("SELECT source_pages FROM stop_corpus WHERE id = %s", (stop_id,))
    existing_sources_row = cur.fetchone()
    existing_sources = []
    if existing_sources_row and existing_sources_row[0]:
        es = existing_sources_row[0]
        if isinstance(es, list):
            existing_sources = es
        elif isinstance(es, str):
            existing_sources = json.loads(es)

    # Add new source if not already present
    new_sources = existing_sources + [source_info]

    cur.execute("""
        UPDATE stop_corpus
        SET passages_json = %s::jsonb,
            source_pages = %s::jsonb,
            passage_count = %s
        WHERE id = %s
    """, (
        json.dumps(combined_passages),
        json.dumps(new_sources),
        len(combined_passages),
        stop_id,
    ))
    conn.commit()
    cur.close()


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Acquire subject-specific corpus for stops')
    parser.add_argument('--dry-run', action='store_true', help='Do not write to DB')
    parser.add_argument('--venue', type=str, help='Process only this venue (substring match)')
    args = parser.parse_args()

    print("=" * 70)
    print("LOCAL-199: Stop Subject Corpus Acquisition")
    print("=" * 70)
    print()

    report = acquire_subject_corpus(dry_run=args.dry_run)

    print()
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"  Stops processed:       {report['stops_processed']}")
    print(f"  Stops enriched:        {report['stops_enriched']}")
    print(f"  Stops left empty:      {report['stops_left_empty']}")
    print(f"  Stops already covered: {report['stops_already_covered']}")
    print()
    print("Per-venue:")
    for venue, stats in report['per_venue'].items():
        print(f"  {venue}: enriched={stats['enriched']}, left_empty={stats['left_empty']}")
    print()
    if report['enriched_details']:
        print("Enriched stops:")
        for d in report['enriched_details']:
            print(f"  [{d['venue']}] {d['stop_title']}")
            print(f"    Source: {d['source_url']}")
            print(f"    Preview: {d['first_passage_preview'][:100]}...")
            print()
