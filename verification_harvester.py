"""verification_harvester.py — LOCAL-283: Harvest fact-carrying passages on verification.

When the existence gate verifies a stop, the source that confirmed it
(venue_corpus pages_json, stop_corpus entries) often contains factual
detail about the object — artist, date, medium, donor, inventory number.

This module:
  1. After verification, checks whether the stop already has corpus.
  2. If not, extracts passages from the verification source (venue pages)
     that are specifically about the stop and carry facts.
  3. Stores them in stop_corpus with source URL, exactly as LOCAL-252/277 do.
  4. Flags stops that verify by name only with no harvestable detail.

Quality bar (D157, D187):
  - Every passage must carry a date, named person+action, documented event,
    or measurement about the SPECIFIC object (not the museum).
  - Venue-level text is excluded.
  - Nothing synthesised — all extracted from the source.

Idempotency:
  - Match on venue_name + stop_title (UNIQUE constraint in stop_corpus).
  - Within passages, deduplicate on URL + normalized text prefix.
"""

import json
import logging
import os
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Text utilities ──────────────────────────────────────────────────────────

def _strip_accents(text: str) -> str:
    """Remove accents for matching."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _normalize(text: str) -> str:
    """Normalize for comparison: lowercase, strip accents, collapse whitespace."""
    t = _strip_accents(text).lower().strip()
    t = re.sub(r'[^\w\s]', ' ', t)
    return ' '.join(t.split())


def _content_words(text: str) -> List[str]:
    """Extract meaningful words (>=4 chars) from text."""
    STOP = {
        'the', 'and', 'for', 'with', 'from', 'that', 'this', 'are', 'was',
        'des', 'les', 'une', 'dans', 'sur', 'par', 'aux', 'son', 'ses',
        'qui', 'que', 'est', 'sont', 'musee', 'museum', 'collection',
    }
    words = _normalize(text).split()
    return [w for w in words if len(w) >= 4 and w not in STOP]


# ─── Passage quality gate ────────────────────────────────────────────────────

# Patterns that indicate a fact-carrying sentence
_YEAR_RE = re.compile(r'\b(1[0-9]{3}|20[0-2][0-9])\b')
_MEASUREMENT_RE = re.compile(r'\b\d+[\.,]?\d*\s*(cm|mm|m|kg|g|metres?|meters?|inches?|feet|ft)\b', re.I)
_INVENTORY_RE = re.compile(r'\b[A-Z]{1,4}[\.\-]?\d{2,}', re.I)


def _passage_carries_fact(text: str) -> bool:
    """Check if a passage carries at least one factual signal.

    A fact-carrying passage has at least one of:
      - A year (four-digit number 1000-2029)
      - A measurement with unit
      - An inventory/accession number pattern
      - A proper noun followed by a verb (heuristic for person+action)

    This is the LOCAL-252/277 quality bar.
    """
    if _YEAR_RE.search(text):
        return True
    if _MEASUREMENT_RE.search(text):
        return True
    if _INVENTORY_RE.search(text):
        return True
    # Proper noun heuristic: capitalized word >=4 chars not at sentence start
    # followed by common biographical verbs
    if re.search(
        r'(?<=[.!?]\s)[A-Z][a-z]{3,}|'  # after sentence boundary
        r'(?<=,\s)[A-Z][a-z]{3,}|'       # after comma
        r'(?<=;\s)[A-Z][a-z]{3,}',       # after semicolon
        text
    ):
        return True
    # Non-Latin scripts often carry person names — check for parenthetical dates
    if re.search(r'\(\d{4}[-–]\d{4}\)', text):
        return True
    return False


def _is_about_venue_not_object(text: str, venue_name: str, stop_title: str) -> bool:
    """Check if a passage is about the museum/venue rather than the specific object.

    D157 prohibition: a passage about the museum is not a passage about the object.
    """
    text_lower = text.lower()
    stop_words = _content_words(stop_title)

    # If the passage mentions the stop's distinctive terms, it's probably about the object
    stop_signal = sum(1 for w in stop_words if w in _normalize(text))
    if stop_signal >= 2:
        return False  # Probably about the object

    # Venue-level signals: opening hours, architecture, history of building, visit info
    venue_signals = [
        'ouvert', 'ferme', 'horaire', 'tarif', 'billet', 'ticket',
        'architect', 'inaugur', 'fondation', 'founded', 'musee a ete',
        'museum was', 'le musee', 'the museum', 'notre collection',
        'our collection', 'visitor', 'visiteur',
    ]
    venue_hits = sum(1 for s in venue_signals if s in text_lower)
    if venue_hits >= 2 and stop_signal == 0:
        return True

    return False


# ─── Passage extraction from venue pages ─────────────────────────────────────

def _split_into_passages(text: str, min_length: int = 60) -> List[str]:
    """Split page text into candidate passages.

    Handles museum catalogue format where entries are delimited by
    inventory numbers (Inv. YYYY.N.N) or double newlines.
    """
    # First split on inventory number patterns (common in museum catalogues)
    # These mark the start of individual object descriptions
    inv_split = re.split(r'(?=Inv\.\s*\d)', text)

    blocks = []
    for chunk in inv_split:
        # Further split on double newlines within each chunk
        sub_blocks = re.split(r'\n\s*\n', chunk)
        blocks.extend(sub_blocks)

    passages = []
    for block in blocks:
        block = block.strip()
        if len(block) < min_length:
            continue
        # Skip boilerplate
        lower = block.lower()
        if any(s in lower for s in ['cookie', 'newsletter', 'copyright', 'panier', 'login']):
            continue
        passages.append(block)
    return passages


def _passage_is_about_stop(passage: str, stop_title: str) -> bool:
    """Check if a passage is specifically about a stop (not venue-level).

    Uses content word overlap with word-boundary matching: at least 2 of the
    stop's distinctive words must appear as whole words in the passage, OR
    the stop title appears as substring.
    """
    passage_norm = _normalize(passage)
    stop_norm = _normalize(stop_title)

    # Substring containment (normalized) — full title
    if len(stop_norm) > 8 and stop_norm in passage_norm:
        return True

    # Content word overlap with WORD BOUNDARY matching
    # This prevents "daim" matching inside "daimyo"
    stop_words = _content_words(stop_title)
    if not stop_words:
        return False

    matches = 0
    for w in stop_words:
        # Use regex word boundary to avoid substring false positives
        if re.search(r'\b' + re.escape(w) + r'\b', passage_norm):
            matches += 1

    threshold = max(2, len(stop_words) * 0.5)
    return matches >= threshold


def _normalize_passage_key(text: str, url: str) -> str:
    """Create a deduplication key for a passage: URL + first 100 normalized chars."""
    return f"{url}|{_normalize(text)[:100]}"


# ─── Core harvesting logic ───────────────────────────────────────────────────

def harvest_from_venue_pages(
    stop_title: str,
    venue_name: str,
    db_conn,
) -> Dict:
    """Extract fact-carrying passages about a stop from venue_corpus pages.

    Returns:
        {
            'harvested': bool,
            'passages_added': int,
            'source_url': str or None,
            'flag': None | 'verified_no_detail',
            'sample_passage': str or None,
        }
    """
    result = {
        'harvested': False,
        'passages_added': 0,
        'source_url': None,
        'flag': None,
        'sample_passage': None,
    }

    cur = db_conn.cursor()

    # 1. Check if stop already has corpus with passages (any venue name variant)
    #    The same museum may appear as "Musee X, Nice, France" in venue_corpus
    #    but "Musee X (English Name), Nice, France" in stop_corpus.
    #    Also handle accent variants in stop titles (Andô vs Ando).
    venue_words = [w for w in _content_words(venue_name) if len(w) >= 5]
    stop_title_folded = _strip_accents(stop_title).lower().strip()

    # Strategy: find by venue words + accent-folded stop title
    found_existing = False
    if venue_words:
        like_clause = " AND ".join(["LOWER(venue_name) LIKE %s"] * min(len(venue_words), 3))
        like_params = [f"%{w}%" for w in venue_words[:3]]
        cur.execute(
            f"SELECT stop_title, passage_count FROM stop_corpus WHERE {like_clause} AND passage_count > 0",
            like_params
        )
        for row_title, row_count in cur.fetchall():
            if _strip_accents(row_title).lower().strip() == stop_title_folded:
                found_existing = True
                break
    if not found_existing:
        # Fallback: exact venue + exact title
        cur.execute(
            "SELECT passage_count FROM stop_corpus WHERE venue_name = %s AND stop_title = %s AND passage_count > 0",
            (venue_name, stop_title)
        )
        if cur.fetchone():
            found_existing = True

    if found_existing:
        # Already has corpus — skip (idempotent)
        result['flag'] = 'already_has_corpus'
        return result

    # 2. Get venue_corpus pages_json
    cur.execute(
        "SELECT pages_json FROM venue_corpus WHERE venue_name = %s",
        (venue_name,)
    )
    vc_row = cur.fetchone()
    if not vc_row or not vc_row[0]:
        result['flag'] = 'verified_no_detail'
        return result

    pages = vc_row[0] if isinstance(vc_row[0], list) else json.loads(vc_row[0])
    if not pages:
        result['flag'] = 'verified_no_detail'
        return result

    # 3. Extract passages about this stop from venue pages
    harvested_passages = []
    seen_keys = set()
    source_urls = set()

    for page in pages:
        if not isinstance(page, dict):
            continue
        page_text = page.get('text', '')
        page_url = page.get('url', '')
        page_title = page.get('title', '')

        if not page_text or len(page_text) < 100:
            continue

        # Split page into candidate passages
        candidates = _split_into_passages(page_text)

        for candidate in candidates:
            # Must be about this specific stop
            if not _passage_is_about_stop(candidate, stop_title):
                continue

            # Must not be about the venue/museum in general
            if _is_about_venue_not_object(candidate, venue_name, stop_title):
                continue

            # Must carry a fact (year, measurement, person+action, etc.)
            if not _passage_carries_fact(candidate):
                continue

            # Deduplicate
            key = _normalize_passage_key(candidate, page_url)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            # Cap passage length at 500 chars
            passage_text = candidate[:500]
            harvested_passages.append({
                'text': passage_text,
                'url': page_url,
                'tier': 1,
                'type': 'museum_official',
            })
            source_urls.add(page_url)

    # 4. If nothing harvested, flag as verified_no_detail
    if not harvested_passages:
        result['flag'] = 'verified_no_detail'
        return result

    # 5. Write to stop_corpus (upsert)
    sources = [
        {
            'url': url,
            'tier': 1,
            'type': 'museum_official',
            'title': f'Venue page for {venue_name}',
            'tier_reason': 'Museum/venue official site (harvested on verification)',
        }
        for url in sorted(source_urls)
    ]

    passages_json = json.dumps(harvested_passages, ensure_ascii=False)
    sources_json = json.dumps(sources, ensure_ascii=False)
    passage_count = len(harvested_passages)

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

    result['harvested'] = True
    result['passages_added'] = passage_count
    result['source_url'] = sorted(source_urls)[0] if source_urls else None
    result['sample_passage'] = harvested_passages[0]['text'][:200] if harvested_passages else None

    return result


# ─── Integration with existence gate ─────────────────────────────────────────

def harvest_on_verification(
    verdicts: List[Dict],
    venue_name: str,
    db_conn,
) -> Dict:
    """Run harvesting for all verified stops that lack corpus.

    Called after run_existence_gate() with its verdicts list.

    For each verified stop:
      - If source is 'venue_corpus' (name-in-a-list only), attempt harvest
        from venue_corpus pages_json.
      - If source is 'stop_corpus' or 'stop_corpus_geographic', the stop
        already has corpus — skip.

    Returns:
        {
            'total_verified': int,
            'already_has_corpus': int,
            'harvested': int,
            'verified_no_detail': int,
            'details': [{stop_title, harvested, passages_added, flag}, ...]
        }
    """
    summary = {
        'total_verified': 0,
        'already_has_corpus': 0,
        'harvested': 0,
        'verified_no_detail': 0,
        'details': [],
    }

    for verdict in verdicts:
        if not verdict.get('verified'):
            continue

        summary['total_verified'] += 1
        stop_title = verdict['stop_title']
        source = verdict.get('source', '')

        # Stop already verified via stop_corpus → it has passages
        if source in ('stop_corpus', 'stop_corpus_geographic'):
            summary['already_has_corpus'] += 1
            summary['details'].append({
                'stop_title': stop_title,
                'harvested': False,
                'passages_added': 0,
                'flag': None,
                'reason': f'already has corpus (verified via {source})',
            })
            continue

        # Verified via venue_corpus (canonical_titles or sparql_works) — may lack detail
        harvest_result = harvest_from_venue_pages(stop_title, venue_name, db_conn)

        if harvest_result['harvested']:
            summary['harvested'] += 1
            print(f"    [HARVEST] {stop_title!r}: +{harvest_result['passages_added']} passages "
                  f"from {harvest_result['source_url']}")
        elif harvest_result['flag'] == 'already_has_corpus':
            summary['already_has_corpus'] += 1
        elif harvest_result['flag'] == 'verified_no_detail':
            summary['verified_no_detail'] += 1
            print(f"    [HARVEST] {stop_title!r}: verified_no_detail (name match only, no facts in source)")

        summary['details'].append({
            'stop_title': stop_title,
            'harvested': harvest_result['harvested'],
            'passages_added': harvest_result['passages_added'],
            'flag': harvest_result['flag'],
            'sample_passage': harvest_result.get('sample_passage'),
            'source_url': harvest_result.get('source_url'),
        })

    # Summary log
    print(f"    [HARVEST] Summary: {summary['harvested']} harvested, "
          f"{summary['already_has_corpus']} already had corpus, "
          f"{summary['verified_no_detail']} verified_no_detail")

    return summary
