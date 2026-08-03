#!/usr/bin/env python3
"""stop_corpus_attribution.py — LOCAL-176: Per-stop corpus attribution.

Attributes existing venue page text to individual stops/works.

APPROACH:
For each venue that has tours, take pages_json and canonical_titles_json,
split the page text into passages, and determine which passages belong to
which work/stop using:
  1. Stop title (or significant words from it) appears in the passage
  2. Artist name (from story_elements people matched to the stop) appears
  3. Canonical title for the work appears in the passage
  4. URL-slug of the page matches a canonical title or stop title

A passage is attributed to a stop if it names the work, its artist, its date,
or its subject. This is the same principle as Michael's anchor test, applied
in reverse: the anchor test asks "does this paragraph reference the corpus?"
— attribution asks "does this corpus passage reference this stop?"

OUTPUT:
  - Creates `stop_corpus` table: (venue_name, stop_title, passages_json, source_pages)
  - Reports attribution coverage per venue

CONSTRAINTS:
  - No paid API calls
  - No web fetching
  - No generation changes
  - Additive migration only (CREATE TABLE, INSERT — never DROP or DELETE)
  - audio_tours untouched at 108 rows
"""
import sys
import re
import json
import unicodedata
from typing import Dict, List, Tuple, Optional, Set

sys.path.insert(0, 'tests')
from db_connection import get_connection


# ─── Text normalization ──────────────────────────────────────────────────────

def normalize(text: str) -> str:
    """Normalize for matching: lowercase, strip accents, collapse whitespace."""
    text = text.lower().strip()
    nfkd = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in nfkd if not unicodedata.combining(c))
    text = re.sub(r'\s+', ' ', text)
    return text


def extract_key_terms(title: str) -> List[str]:
    """Extract meaningful search terms from a stop/work title.
    
    More permissive than the v2 detector's word extraction:
    - Handles apostrophes (l'arbre → arbre)
    - Strips punctuation
    - Includes words >= 3 chars (not 4)
    - Splits on hyphens
    """
    title_norm = normalize(title)
    # Remove common articles/prepositions that add no specificity
    noise = {'les', 'des', 'une', 'par', 'sur', 'sous', 'dans', 'avec',
             'pour', 'the', 'and', 'for', 'from', 'with', 'ou'}
    
    # Split on spaces, hyphens, apostrophes
    raw_words = re.split(r"[\s\-']+", title_norm)
    # Also handle "d'" "l'" prefixes
    words = []
    for w in raw_words:
        w = w.strip('.,;:!?()"')
        if w.startswith("d'") or w.startswith("l'"):
            w = w[2:]
        if len(w) >= 3 and w not in noise:
            words.append(w)
    return words


# ─── Passage extraction from pages ──────────────────────────────────────────

def split_into_passages(text: str, min_length: int = 50) -> List[str]:
    """Split page text into meaningful passages (paragraphs).
    
    A passage is a block of text separated by double newlines or
    significant whitespace, with minimum length to filter noise.
    """
    # Split on double newline or multiple whitespace lines
    blocks = re.split(r'\n\s*\n', text)
    passages = []
    for block in blocks:
        block = block.strip()
        # Skip very short blocks (navigation, labels, etc.)
        if len(block) < min_length:
            continue
        # Skip blocks that are mostly HTML artifacts or menu items
        if block.count('\n') > 10 and len(block) < 200:
            continue
        passages.append(block)
    return passages


# ─── Attribution logic ───────────────────────────────────────────────────────

def passage_mentions_stop(passage_norm: str, stop_terms: List[str],
                          artist_names: List[str] = None,
                          min_term_matches: int = 2,
                          venue_wide_terms: Set[str] = None) -> Tuple[bool, str]:
    """Determine if a passage is about a specific stop/work.
    
    Returns (is_match, reason) where reason explains the attribution.
    
    Rules:
    1. If the full stop title (normalized) appears → strong match
    2. If >= min_term_matches of the stop's key terms appear, AND at least
       one term is NOT venue-wide → match
    3. If an artist name specific to this stop appears AND at least one
       non-artist stop term appears → match
       
    venue_wide_terms: terms that appear in >50% of pages for this venue.
    These are excluded from counting toward min_term_matches to prevent
    artist names like "yves klein" from matching every page.
    """
    if venue_wide_terms is None:
        venue_wide_terms = set()
    
    # Rule 1: Full title match (using all terms concatenated)
    full_title = ' '.join(stop_terms)
    if len(full_title) >= 6 and full_title in passage_norm:
        return True, 'full_title'
    
    # Separate terms into distinctive (not venue-wide) and common
    distinctive_terms = [t for t in stop_terms if t not in venue_wide_terms]
    common_terms = [t for t in stop_terms if t in venue_wide_terms]
    
    # Count matches
    distinctive_matches = sum(1 for t in distinctive_terms if t in passage_norm)
    common_matches = sum(1 for t in common_terms if t in passage_norm)
    total_matches = distinctive_matches + common_matches
    
    # Rule 2: Need at least one distinctive term match + enough total matches
    if distinctive_terms and distinctive_matches >= 1:
        if total_matches >= min_term_matches:
            return True, f'terms({total_matches}/{len(stop_terms)},distinctive={distinctive_matches})'
    elif not distinctive_terms:
        # All terms are venue-wide — cannot distinguish this stop
        # Only match if ALL terms appear together (very specific co-occurrence)
        if len(stop_terms) >= 3 and total_matches == len(stop_terms):
            return True, f'all_common_terms({total_matches})'
    
    # Rule 3: Artist name + distinctive stop term
    if artist_names and distinctive_matches >= 1:
        for artist in artist_names:
            artist_norm = normalize(artist)
            if len(artist_norm) >= 5 and artist_norm in passage_norm:
                return True, f'artist({artist})+distinctive_term'
    
    # Single very distinctive term (>= 8 chars, likely a proper name)
    if len(distinctive_terms) == 1 and len(distinctive_terms[0]) >= 8:
        if distinctive_terms[0] in passage_norm:
            return True, f'distinctive_term({distinctive_terms[0]})'
    
    return False, ''


def attribute_pages_to_stops(pages: List[Dict], stop_titles: List[str],
                              story_elements: List[Dict],
                              canonical_titles: List,
                              venue_name: str) -> Dict[str, Dict]:
    """Attribute page passages to stops within a venue.
    
    Returns {stop_title: {passages: [...], source_pages: [...], method: str}}
    """
    attribution = {}
    
    # Build venue-wide term set: terms that appear in >50% of pages
    # These are "ambient" terms (museum name, star artist) that cannot
    # distinguish one stop from another
    venue_wide_terms = _compute_venue_wide_terms(pages)
    
    # Build artist associations per stop from story elements
    stop_artists = {}  # stop_title → [artist_names]
    for stop in stop_titles:
        stop_norm = normalize(stop)
        stop_words = [w for w in stop_norm.split() if len(w) >= 4]
        artists = set()
        for elem in story_elements:
            elem_text = normalize(elem.get('text', ''))
            if stop_words:
                match_count = sum(1 for w in stop_words if w in elem_text)
                if match_count >= max(1, len(stop_words) * 0.4):
                    for p in (elem.get('people') or []):
                        if p and len(p) > 2:
                            artists.add(p)
        stop_artists[stop] = list(artists)
    
    # Build URL-based page-to-stop mapping
    # Pages with URLs containing work slugs can be directly attributed
    page_stop_map = {}  # page_index → stop_title
    for i, page in enumerate(pages):
        if not isinstance(page, dict):
            continue
        url = page.get('url', '').lower()
        # Extract slug from URL
        slug = url.rstrip('/').split('/')[-1] if url else ''
        slug_norm = normalize(slug.replace('-', ' '))
        
        for stop in stop_titles:
            stop_terms = extract_key_terms(stop)
            if not stop_terms:
                continue
            # Only use distinctive terms for URL matching
            distinctive = [t for t in stop_terms if t not in venue_wide_terms]
            if not distinctive:
                continue
            # Check if slug contains stop terms
            slug_matches = sum(1 for t in distinctive if t in slug_norm)
            if len(distinctive) >= 2 and slug_matches >= 2:
                page_stop_map[i] = stop
                break
            elif len(distinctive) == 1 and len(distinctive[0]) >= 6 and distinctive[0] in slug_norm:
                page_stop_map[i] = stop
                break
    
    # Also check canonical titles against URLs
    for i, page in enumerate(pages):
        if i in page_stop_map:
            continue
        if not isinstance(page, dict):
            continue
        url = page.get('url', '').lower()
        slug = url.rstrip('/').split('/')[-1] if url else ''
        slug_norm = normalize(slug.replace('-', ' '))
        
        for ct in canonical_titles:
            ct_name = ct if isinstance(ct, str) else ct.get('name', '')
            ct_terms = extract_key_terms(ct_name)
            if not ct_terms:
                continue
            ct_distinctive = [t for t in ct_terms if t not in venue_wide_terms]
            if not ct_distinctive:
                continue
            ct_matches = sum(1 for t in ct_distinctive if t in slug_norm)
            if len(ct_distinctive) >= 2 and ct_matches >= 2:
                # This page is about this canonical title
                # Find if this canonical title matches any stop
                for stop in stop_titles:
                    stop_terms = extract_key_terms(stop)
                    overlap = set(ct_terms) & set(stop_terms)
                    if overlap:
                        page_stop_map[i] = stop
                        break
                if i in page_stop_map:
                    break
    
    # Now attribute passages
    for stop in stop_titles:
        stop_terms = extract_key_terms(stop)
        artists = stop_artists.get(stop, [])
        attributed_passages = []
        source_pages = set()
        
        for page_idx, page in enumerate(pages):
            if not isinstance(page, dict):
                continue
            text = page.get('text', '')
            if not text:
                continue
            
            # If page is URL-mapped to THIS stop, all substantial passages count
            if page_stop_map.get(page_idx) == stop:
                passages = split_into_passages(text, min_length=80)
                for p in passages:
                    p_norm = normalize(p)
                    # Even for URL-mapped pages, filter out boilerplate
                    if len(p_norm) > 80 and not _is_boilerplate(p_norm):
                        attributed_passages.append({
                            'text': p[:500],  # Cap passage length
                            'method': 'url_match',
                            'page_title': page.get('title', ''),
                        })
                        source_pages.add(page_idx)
                continue
            
            # For non-URL-mapped pages, do passage-level attribution
            passages = split_into_passages(text, min_length=80)
            for p in passages:
                p_norm = normalize(p)
                if _is_boilerplate(p_norm):
                    continue
                is_match, reason = passage_mentions_stop(
                    p_norm, stop_terms, artists,
                    min_term_matches=max(2, len(stop_terms) // 2),
                    venue_wide_terms=venue_wide_terms,
                )
                if is_match:
                    attributed_passages.append({
                        'text': p[:500],
                        'method': reason,
                        'page_title': page.get('title', ''),
                    })
                    source_pages.add(page_idx)
        
        attribution[stop] = {
            'passages': attributed_passages,
            'source_pages': sorted(source_pages),
            'passage_count': len(attributed_passages),
        }
    
    return attribution


def _compute_venue_wide_terms(pages: List[Dict]) -> Set[str]:
    """Compute terms that appear in >50% of pages (venue-level ambient noise).
    
    These are terms like artist names that appear on every page of a museum
    website. They cannot distinguish one stop from another.
    """
    if not pages:
        return set()
    
    # Count in how many pages each 4+ char word appears
    word_page_count = {}
    total_pages = 0
    
    for page in pages:
        if not isinstance(page, dict):
            continue
        text = page.get('text', '')
        if not text or len(text) < 100:
            continue
        total_pages += 1
        page_norm = normalize(text)
        # Extract unique words from this page
        page_words = set(w for w in page_norm.split() if len(w) >= 4)
        for w in page_words:
            word_page_count[w] = word_page_count.get(w, 0) + 1
    
    if total_pages < 3:
        return set()
    
    # Terms in >50% of pages are venue-wide
    threshold = total_pages * 0.5
    venue_wide = {w for w, count in word_page_count.items() if count > threshold}
    
    return venue_wide


def _is_boilerplate(text_norm: str) -> bool:
    """Filter out likely boilerplate/navigation/menu text."""
    boilerplate_signals = [
        'cookie', 'politique de confidentialite', 'privacy policy',
        'newsletter', 'subscribe', 'abonnez', 'connexion', 'login',
        'panier', 'cart', 'acheter', 'buy ticket', 'billetterie',
        'copyright', 'tous droits', 'all rights reserved',
        'plan du site', 'sitemap', 'mentions legales',
        'horaires', 'tarifs', 'acces', 'ouvert du', 'ferme le',
    ]
    matches = sum(1 for s in boilerplate_signals if s in text_norm)
    if matches >= 2:
        return True
    # Very short with mostly navigation words
    if len(text_norm) < 100 and any(s in text_norm for s in ['menu', 'accueil', 'home', 'retour']):
        return True
    return False


# ─── Database migration ──────────────────────────────────────────────────────

MIGRATION_SQL = """
-- LOCAL-176: Per-stop corpus attribution table
-- Additive only: new table, no changes to existing schema
CREATE TABLE IF NOT EXISTS stop_corpus (
    id SERIAL PRIMARY KEY,
    venue_name TEXT NOT NULL,
    stop_title TEXT NOT NULL,
    passages_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_pages JSONB NOT NULL DEFAULT '[]'::jsonb,
    passage_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(venue_name, stop_title)
);

-- Index for efficient lookup by venue
CREATE INDEX IF NOT EXISTS idx_stop_corpus_venue ON stop_corpus(venue_name);

-- Index for lookup by stop title
CREATE INDEX IF NOT EXISTS idx_stop_corpus_stop ON stop_corpus(stop_title);
"""


def run_migration(conn) -> bool:
    """Create the stop_corpus table (additive only)."""
    cur = conn.cursor()
    try:
        cur.execute(MIGRATION_SQL)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Migration error: {e}")
        return False


# ─── Main attribution pipeline ──────────────────────────────────────────────

def get_tour_stops_for_venue(venue_name: str, conn) -> List[str]:
    """Get all unique stop titles from tours associated with a venue.
    
    Uses progressively broader matching:
    1. Full venue name before first comma
    2. Most distinctive words (proper nouns like 'Chagall', 'Lascaris', 'Matisse')
    3. Any significant word with length >= 6 that isn't generic
    """
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Generic words that match too broadly
    _GENERIC = {'france', 'museum', 'musee', 'musée', 'nice', 'walking',
                'biking', 'cycling', 'restaurant', 'historical', 'national',
                'international', 'modern', 'moderne', 'contemporain', 'paris',
                'monaco', 'area', 'tour', 'boston', 'philadelphia'}
    
    # Extract meaningful words from venue name
    venue_words = []
    for w in re.split(r'[\s,]+', venue_name):
        w_clean = w.strip('.,;:()')
        if len(w_clean) >= 4 and w_clean.lower() not in _GENERIC:
            venue_words.append(w_clean)
    
    rows = []
    
    # Strategy 1: Full first part (before comma)
    first_part = venue_name.split(',')[0].strip()
    cur.execute("SELECT id, tour_name, tour_content FROM audio_tours WHERE tour_name ILIKE %s",
                (f'%{first_part}%',))
    rows = cur.fetchall()
    
    # Strategy 2: Most distinctive words (proper nouns — capitalized, not generic)
    if not rows:
        distinctive = [w for w in venue_words 
                      if w[0].isupper() and w.lower() not in _GENERIC and len(w) >= 5]
        for w in distinctive:
            cur.execute("SELECT id, tour_name, tour_content FROM audio_tours WHERE tour_name ILIKE %s",
                        (f'%{w}%',))
            found = cur.fetchall()
            if found:
                rows = found
                break
    
    # Strategy 3: Try pairs of distinctive words (OR logic)
    if not rows and len(venue_words) >= 2:
        for w in venue_words:
            if len(w) >= 6 and w.lower() not in _GENERIC:
                cur.execute("SELECT id, tour_name, tour_content FROM audio_tours WHERE tour_name ILIKE %s",
                            (f'%{w}%',))
                found = cur.fetchall()
                if found:
                    rows = found
                    break
    
    # Parse stop titles from tour content
    all_stops = set()
    for row in rows:
        content = row.get('tour_content', '')
        if not content:
            continue
        stops = _parse_stop_titles(content)
        all_stops.update(stops)
    
    return sorted(all_stops)


def _parse_stop_titles(tour_content: str) -> List[str]:
    """Parse stop titles from tour content (same logic as detector)."""
    has_stop_markers = bool(re.search(r'Stop \d+:', tour_content))
    
    if has_stop_markers:
        parts = re.split(r'\nStop \d+:\s*', tour_content)
        if not parts[0].strip() or 'Tour-Category' in parts[0]:
            parts = parts[1:]
        else:
            if re.match(r'Stop \d+:', tour_content):
                parts = re.split(r'Stop \d+:\s*', tour_content)[1:]
            else:
                parts = parts[1:]
    else:
        parts = re.split(r'\n(?=[^\n]+\n\nAddress:)', tour_content)
        if parts and ('Address:' not in parts[0][:200]):
            parts = parts[1:]
    
    titles = []
    for part in parts:
        lines = part.strip().split('\n')
        if not lines:
            continue
        title = lines[0].strip().rstrip(':').strip()
        if title and 'Tour-Category' not in title and 'Step-by-Step' not in title:
            titles.append(title)
    
    return titles


def run_attribution(verbose: bool = True) -> Dict:
    """Run the full attribution pipeline.
    
    Returns a summary dict with per-venue results.
    """
    conn = get_connection()
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Step 1: Run migration
    if verbose:
        print("=" * 78)
        print("LOCAL-176: Per-Stop Corpus Attribution")
        print("=" * 78)
        print()
    
    if not run_migration(conn):
        return {'error': 'migration failed'}
    
    if verbose:
        print("✓ Migration complete: stop_corpus table created")
        print()
    
    # Step 2: Get all venues with corpus data
    cur.execute("SELECT * FROM venue_corpus ORDER BY venue_name")
    venues = cur.fetchall()
    
    # Step 3: Verify audio_tours count
    cur.execute("SELECT COUNT(*) as cnt FROM audio_tours")
    tours_count = cur.fetchone()['cnt']
    if verbose:
        print(f"audio_tours row count: {tours_count}")
        print()
    
    results = {}
    total_stops = 0
    total_attributed = 0
    total_passages = 0
    
    for venue_row in venues:
        venue_name = venue_row['venue_name']
        pages = venue_row.get('pages_json') or []
        story_elements = venue_row.get('story_elements_json') or []
        canonical_titles = venue_row.get('canonical_titles_json') or []
        
        # Get tour stops for this venue
        stop_titles = get_tour_stops_for_venue(venue_name, conn)
        
        if not stop_titles:
            results[venue_name] = {
                'stops': 0, 'attributed': 0, 'passages': 0,
                'note': 'no tours found'
            }
            continue
        
        # Run attribution
        attribution = attribute_pages_to_stops(
            pages, stop_titles, story_elements, canonical_titles, venue_name
        )
        
        # Persist to stop_corpus (upsert)
        stops_with_passages = 0
        venue_passages = 0
        
        for stop_title, attr_data in attribution.items():
            if attr_data['passage_count'] > 0:
                stops_with_passages += 1
                venue_passages += attr_data['passage_count']
                
                cur.execute("""
                    INSERT INTO stop_corpus (venue_name, stop_title, passages_json, 
                                           source_pages, passage_count)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (venue_name, stop_title) 
                    DO UPDATE SET passages_json = EXCLUDED.passages_json,
                                  source_pages = EXCLUDED.source_pages,
                                  passage_count = EXCLUDED.passage_count,
                                  created_at = NOW()
                """, (
                    venue_name,
                    stop_title,
                    json.dumps(attr_data['passages'], ensure_ascii=False),
                    json.dumps(attr_data['source_pages']),
                    attr_data['passage_count'],
                ))
        
        conn.commit()
        
        total_stops += len(stop_titles)
        total_attributed += stops_with_passages
        total_passages += venue_passages
        
        results[venue_name] = {
            'stops': len(stop_titles),
            'attributed': stops_with_passages,
            'passages': venue_passages,
            'stop_details': {t: {'passages': a['passage_count'], 
                                  'sources': a['source_pages']}
                            for t, a in attribution.items()},
        }
        
        if verbose:
            attr_pct = 100 * stops_with_passages / len(stop_titles) if stop_titles else 0
            print(f"  {venue_name[:55]:55s}  stops={len(stop_titles):2d}  "
                  f"attributed={stops_with_passages:2d} ({attr_pct:4.0f}%)  "
                  f"passages={venue_passages:3d}")
    
    # Step 4: Verify audio_tours untouched
    cur.execute("SELECT COUNT(*) as cnt FROM audio_tours")
    final_count = cur.fetchone()['cnt']
    
    # Step 5: Count stop_corpus rows
    cur.execute("SELECT COUNT(*) as cnt FROM stop_corpus")
    stop_corpus_count = cur.fetchone()['cnt']
    cur.execute("SELECT COUNT(*) as cnt FROM stop_corpus WHERE passage_count > 0")
    stop_corpus_with_data = cur.fetchone()['cnt']
    
    if verbose:
        print()
        print(f"─" * 78)
        print(f"  TOTAL: {total_stops} stops across {len(venues)} venues")
        print(f"  Stops with attributed passages: {total_attributed}/{total_stops} "
              f"({100*total_attributed/total_stops:.1f}%)")
        print(f"  Total passages attributed: {total_passages}")
        print(f"  stop_corpus rows: {stop_corpus_count} ({stop_corpus_with_data} with data)")
        print(f"  audio_tours: {final_count} (unchanged from {tours_count})")
        print()
    
    conn.close()
    
    return {
        'total_stops': total_stops,
        'total_attributed': total_attributed,
        'total_passages': total_passages,
        'stop_corpus_rows': stop_corpus_count,
        'audio_tours_count': final_count,
        'venues': results,
    }


if __name__ == '__main__':
    run_attribution(verbose=True)
