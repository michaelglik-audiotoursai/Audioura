#!/usr/bin/env python3
"""stop_anchor_detector.py — LOCAL-174: Detect paragraphs not tied to their stop.

Implements the anchor test from D51.3 (Michael's choice):
A paragraph passes if it contains at least one ANCHOR — a proper noun, date,
artefact, or figure — that the corpus ties to THIS specific stop.

Two failure modes reported separately:
- NO_ANCHOR: no stop-tied fact at all (Michael's first failure mode)
- UNLINKED_ENTITY: names a person/work/title the corpus does not connect
  to this stop (Michael's second failure mode — the Fitzgerald case)

Read-only against the database. Does not modify generation.
"""
import re
import sys
import json
from typing import Dict, List, Optional, Tuple, Set

sys.path.insert(0, 'tests')
from db_connection import get_connection

# ─── NLP-lite: proper noun / entity extraction ──────────────────────────────

# Common words that look like proper nouns but aren't (title case at sentence start, etc.)
_FALSE_POSITIVE_NAMES = {
    'the', 'a', 'an', 'this', 'that', 'these', 'those', 'here', 'there',
    'as', 'at', 'by', 'for', 'from', 'in', 'of', 'on', 'to', 'with',
    'and', 'but', 'or', 'nor', 'so', 'yet', 'not', 'no', 'yes',
    'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'shall', 'should', 'may', 'might', 'can', 'could', 'must',
    'its', 'his', 'her', 'our', 'your', 'their', 'my',
    'it', 'he', 'she', 'we', 'you', 'they', 'i', 'me', 'us',
    'what', 'which', 'who', 'whom', 'whose', 'where', 'when', 'why', 'how',
    'if', 'then', 'else', 'each', 'every', 'all', 'both', 'few', 'more',
    'most', 'other', 'some', 'such', 'only', 'own', 'same',
    'than', 'too', 'very', 'just', 'about', 'above', 'after', 'again',
    'also', 'because', 'before', 'between', 'during', 'into', 'over',
    'through', 'under', 'until', 'while',
    # Tour-specific common words often capitalized
    'stop', 'tour', 'museum', 'gallery', 'park', 'street', 'avenue',
    'road', 'place', 'square', 'church', 'cathedral', 'castle', 'palace',
    'beach', 'port', 'harbor', 'harbour', 'bay', 'cape', 'island',
    'garden', 'gardens', 'bridge', 'tower', 'gate', 'wall', 'market',
    'old', 'new', 'grand', 'great', 'ancient', 'modern', 'royal',
    'north', 'south', 'east', 'west', 'central',
    'french', 'italian', 'english', 'spanish', 'german', 'russian',
    'european', 'mediterranean', 'atlantic', 'pacific',
    'orientation', 'description', 'directions', 'address', 'coordinates',
    'cycling', 'biking', 'walking', 'driving', 'riding',
    'imagine', 'feel', 'notice', 'look', 'listen', 'stand', 'find',
    'explore', 'discover', 'continue', 'head', 'follow', 'turn',
}

# Sentence-initial words to skip (first word after period/newline often capitalized)
_SENTENCE_STARTERS = {
    'the', 'a', 'an', 'this', 'that', 'here', 'there', 'it', 'he', 'she',
    'we', 'you', 'they', 'as', 'in', 'on', 'at', 'from', 'with', 'for',
    'cycling', 'stand', 'look', 'feel', 'imagine', 'notice', 'find',
    'explore', 'discover', 'continue', 'head', 'follow', 'turn',
    'prepare', 'let', 'take', 'make', 'see', 'hear', 'watch',
}

# Generic descriptive words commonly used in filler prose
_GENERIC_DESCRIPTORS = {
    'beauty', 'grandeur', 'allure', 'charm', 'elegance', 'splendor',
    'serenity', 'tranquility', 'majesty', 'magnificence', 'wonder',
    'paradise', 'haven', 'oasis', 'jewel', 'gem', 'treasure',
    'breathtaking', 'stunning', 'captivating', 'enchanting', 'mesmerizing',
    'timeless', 'enduring', 'eternal', 'profound', 'remarkable',
    'tapestry', 'mosaic', 'symphony', 'melody', 'harmony',
    'creativity', 'imagination', 'inspiration', 'spirit', 'essence',
    'atmosphere', 'ambiance', 'aura', 'energy', 'vibe',
}


def extract_dates(text: str) -> List[str]:
    """Extract year references (4-digit numbers that look like years)."""
    # Match years from 1000-2099
    years = re.findall(r'\b(1[0-9]{3}|20[0-9]{2})\b', text)
    return years


def extract_proper_nouns(text: str) -> List[str]:
    """Extract likely proper nouns from text using capitalization heuristics.
    
    Returns multi-word proper nouns where possible (e.g. 'Scott Fitzgerald'
    rather than 'Scott' and 'Fitzgerald' separately).
    """
    proper_nouns = []
    
    # Strategy 1: Find sequences of capitalized words (multi-word names)
    # Match 2+ consecutive capitalized words not at sentence start
    sentences = re.split(r'[.!?]\s+|\n', text)
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        words = sentence.split()
        if not words:
            continue
        
        # Skip first word (sentence-initial capitalization)
        i = 1
        while i < len(words):
            # Check for sequence of capitalized words
            if words[i][0:1].isupper() and words[i].lower() not in _FALSE_POSITIVE_NAMES:
                # Start of a potential proper noun
                name_parts = [words[i]]
                j = i + 1
                while j < len(words):
                    w = words[j]
                    # Allow connectors in names: "de", "di", "van", "von", "d'", "la", "le"
                    if w.lower() in ('de', 'di', 'da', 'van', 'von', 'la', 'le', 'les',
                                     'du', 'des', 'al', 'el', 'the', 'of', 'and'):
                        if j + 1 < len(words) and words[j+1][0:1].isupper():
                            name_parts.append(w)
                            j += 1
                            continue
                        break
                    elif w.startswith("d'") or w.startswith("l'") or w.startswith("D'") or w.startswith("L'"):
                        name_parts.append(w)
                        j += 1
                        continue
                    elif w[0:1].isupper() and w.lower() not in _FALSE_POSITIVE_NAMES:
                        name_parts.append(w)
                        j += 1
                        continue
                    else:
                        break
                
                name = ' '.join(name_parts)
                # Filter: must have at least one word >= 3 chars that's not generic
                significant = [p for p in name_parts 
                              if len(p) >= 3 and p.lower() not in _FALSE_POSITIVE_NAMES]
                if significant:
                    proper_nouns.append(name)
                i = j
            else:
                i += 1
    
    # Strategy 2: Also check first words of sentences for known-entity patterns
    # (titles like "F. Scott Fitzgerald", "Le Corbusier")
    title_patterns = re.findall(
        r'\b([A-Z][a-z]?\.\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', text
    )
    proper_nouns.extend(title_patterns)
    
    # Deduplicate while preserving order
    seen = set()
    result = []
    for pn in proper_nouns:
        pn_lower = pn.lower()
        if pn_lower not in seen:
            seen.add(pn_lower)
            result.append(pn)
    
    return result


def extract_entities(text: str) -> Dict[str, List[str]]:
    """Extract all entity-like tokens from a paragraph.
    
    Returns dict with:
      - proper_nouns: capitalized multi-word names
      - dates: year references
      - quoted_titles: text in quotes (book/work titles)
    """
    proper_nouns = extract_proper_nouns(text)
    dates = extract_dates(text)
    
    # Quoted titles (book names, artwork titles, etc.)
    quoted = re.findall(r'["\u201c\u201d\u00ab\u00bb]([^"\u201c\u201d\u00ab\u00bb]+)["\u201c\u201d\u00ab\u00bb]', text)
    # Also catch titles in italics markdown or single quotes for named works
    quoted += re.findall(r"'([A-Z][^']{2,})'", text)
    
    return {
        'proper_nouns': proper_nouns,
        'dates': dates,
        'quoted_titles': quoted,
    }


# ─── Corpus anchor matching ─────────────────────────────────────────────────

def _normalize_for_match(text: str) -> str:
    """Normalize text for fuzzy matching: lowercase, strip accents, collapse whitespace."""
    import unicodedata
    text = text.lower().strip()
    # Strip accents
    nfkd = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in nfkd if not unicodedata.combining(c))
    text = re.sub(r'\s+', ' ', text)
    return text


def build_corpus_anchors(venue_corpus: Dict, stop_title: str, tour_name: str) -> Dict:
    """Build the set of anchors that the corpus ties to this stop.
    
    For museum tours: anchors are facts from story_elements + canonical_titles
    that relate to the specific artwork (stop_title).
    
    For walking/distributed tours: anchors are facts from the corpus pages
    that mention the POI name or location.
    
    Returns dict with:
      - people: set of person names from corpus for this stop
      - dates: set of years/dates from corpus for this stop
      - titles: set of work/book/artwork titles from corpus
      - facts: list of factual statements from corpus
      - all_corpus_people: set of ALL people in the entire corpus (for UNLINKED detection)
      - all_corpus_text: combined corpus text for substring checking
    """
    anchors = {
        'people': set(),
        'dates': set(),
        'titles': set(),
        'facts': [],
        'all_corpus_people': set(),
        'all_corpus_text': '',
    }
    
    if not venue_corpus:
        return anchors
    
    # Get story elements
    story_elements = venue_corpus.get('story_elements_json') or []
    canonical_titles = venue_corpus.get('canonical_titles_json') or []
    pages = venue_corpus.get('pages_json') or []
    
    # Combine all page text for general anchor checking
    all_text = ''
    if isinstance(pages, list):
        all_text = ' '.join(p.get('text', '') for p in pages if isinstance(p, dict))
    elif isinstance(pages, dict):
        all_text = pages.get('combined_text', '') or pages.get('text', '')
    anchors['all_corpus_text'] = all_text
    
    # Extract all people from ALL story elements (for unlinked detection)
    for elem in story_elements:
        people = elem.get('people') or []
        for p in people:
            if p and len(p) > 2:
                anchors['all_corpus_people'].add(p)
    
    # Now find elements specific to THIS stop
    stop_title_norm = _normalize_for_match(stop_title)
    
    # For museum tours: match elements to the stop's artwork title
    for elem in story_elements:
        elem_text = _normalize_for_match(elem.get('text', ''))
        
        # Check if this element relates to this stop's title
        # (element text contains stop title words, or vice versa)
        stop_words = [w for w in stop_title_norm.split() if len(w) >= 4]
        if stop_words:
            match_count = sum(1 for w in stop_words if w in elem_text)
            if match_count < max(1, len(stop_words) * 0.4):
                # Not about this stop specifically - but still part of venue corpus
                continue
        
        # This element is about this stop
        people = elem.get('people') or []
        dates = elem.get('dates') or []
        for p in people:
            if p and len(p) > 2:
                anchors['people'].add(p)
        for d in dates:
            if d:
                anchors['dates'].add(str(d))
        anchors['facts'].append(elem.get('text', ''))
    
    # Add canonical titles as potential anchors
    if isinstance(canonical_titles, list):
        for ct in canonical_titles:
            if isinstance(ct, str):
                anchors['titles'].add(ct)
            elif isinstance(ct, dict):
                name = ct.get('name', '')
                if name:
                    anchors['titles'].add(name)
    
    # For walking/distributed tours, also check if the stop name
    # or its components appear in corpus text alongside entities
    if all_text:
        # Extract people/dates from corpus text that appear near the stop name
        stop_name_in_corpus = stop_title_norm in _normalize_for_match(all_text)
        if stop_name_in_corpus:
            # Find the context around the stop name mention
            norm_text = _normalize_for_match(all_text)
            pos = norm_text.find(stop_title_norm)
            if pos >= 0:
                context = all_text[max(0, pos-500):pos+500]
                context_dates = extract_dates(context)
                context_names = extract_proper_nouns(context)
                for d in context_dates:
                    anchors['dates'].add(d)
                for n in context_names:
                    anchors['people'].add(n)
    
    return anchors


# ─── Paragraph classification ───────────────────────────────────────────────

def classify_paragraph(paragraph: str, corpus_anchors: Dict, 
                       stop_title: str, tour_name: str = '') -> Dict:
    """Classify a paragraph as ANCHORED, NO_ANCHOR, or UNLINKED_ENTITY.
    
    Logic (D51.3):
    1. Extract entities from the paragraph
    2. Check each entity against corpus anchors for this stop
    3. If any entity is corpus-backed → ANCHORED (with the anchor named)
    4. If entities found but none in corpus → UNLINKED_ENTITY
    5. If no entities at all → NO_ANCHOR
    
    Critical filter: the stop name itself, tour area name, and generic
    geographic references are NOT anchors — Michael's test is "if you
    substitute the place name and the sentence is still true." Self-references
    to the stop/tour location fail that test by definition.
    
    Returns dict with:
      - classification: 'ANCHORED' | 'NO_ANCHOR' | 'UNLINKED_ENTITY'
      - anchor: the matching anchor (if ANCHORED)
      - unlinked_entities: list of entities not in corpus (if UNLINKED_ENTITY)
      - entities_found: all entities extracted from paragraph
    """
    entities = extract_entities(paragraph)
    all_proper = entities['proper_nouns']
    all_dates = entities['dates']
    all_titles = entities['quoted_titles']
    
    # Build exclusion set: stop name, tour area name, and geographic self-references
    # These are the "place names" that Michael says you can substitute
    stop_title_norm = _normalize_for_match(stop_title)
    stop_title_words = set(w for w in stop_title_norm.split() if len(w) >= 3)
    
    # Tour name words to exclude (e.g. "French Riviera", "Nice", "Antibes")
    tour_name_norm = _normalize_for_match(tour_name)
    tour_name_words = set(w for w in tour_name_norm.split() 
                          if len(w) >= 4 and w not in ('tour', 'museum', 'walking', 'biking'))
    
    # Combined geographic self-reference words (these are substitutable per Michael's test)
    location_words = stop_title_words | tour_name_words
    
    # Common geographic/location terms that are never meaningful anchors
    _GEO_GENERICS = {
        'riviera', 'mediterranean', 'france', 'french', 'italy', 'italian',
        'spain', 'spanish', 'england', 'english', 'germany', 'german',
        'europe', 'european', 'africa', 'african', 'asia', 'asian',
        'america', 'american', 'atlantic', 'pacific', 'boston', 'nice',
        'antibes', 'cannes', 'monaco', 'paris', 'london', 'rome',
        'coast', 'coastline', 'shore', 'shores', 'sea', 'ocean',
        'mountain', 'mountains', 'hill', 'hills', 'valley',
        'cape', 'cap', 'port', 'bay', 'island', 'peninsula',
        'promenade', 'boulevard', 'avenue', 'street', 'place', 'square',
    }
    
    def _is_geographic_self_reference(name_norm: str) -> bool:
        """Check if a proper noun is just a geographic reference to the stop/tour location."""
        name_words = set(name_norm.split())
        # If ALL significant words are from the stop title or tour name, it's self-referencing
        significant_words = {w for w in name_words if len(w) >= 3}
        if not significant_words:
            return True
        if significant_words.issubset(location_words | _GEO_GENERICS):
            return True
        # Check partial overlap: if >60% of words are location words, likely geographic
        if location_words:
            overlap = significant_words & (location_words | _GEO_GENERICS)
            if len(overlap) >= len(significant_words) * 0.6:
                return True
        return False
    
    # Check for anchors: entities that the corpus ties to this stop
    found_anchors = []
    unlinked = []
    
    corpus_people_norm = {_normalize_for_match(p) for p in corpus_anchors.get('people', set())}
    corpus_dates = corpus_anchors.get('dates', set())
    corpus_titles_norm = {_normalize_for_match(t) for t in corpus_anchors.get('titles', set())}
    all_corpus_people_norm = {_normalize_for_match(p) for p in corpus_anchors.get('all_corpus_people', set())}
    corpus_text_norm = _normalize_for_match(corpus_anchors.get('all_corpus_text', ''))
    
    # Check proper nouns
    for pn in all_proper:
        pn_norm = _normalize_for_match(pn)
        # Strip trailing punctuation from normalized form
        pn_norm = pn_norm.rstrip('.,;:!?')
        
        # Skip geographic self-references (the substitutable place names)
        if _is_geographic_self_reference(pn_norm):
            continue
        # Skip very short/generic names
        if len(pn_norm) < 4:
            continue
            
        # Check if this person/name is in the corpus for THIS stop
        if any(pn_norm in cp or cp in pn_norm for cp in corpus_people_norm):
            found_anchors.append(('person', pn))
        # Check if name appears in the full corpus text (broader check)
        elif pn_norm in corpus_text_norm:
            found_anchors.append(('corpus_mention', pn))
        # It's a proper noun not in the corpus - potential UNLINKED_ENTITY
        elif len(pn_norm) >= 5:  # Only flag substantive names
            unlinked.append(('person', pn))
    
    # Check dates
    for date in all_dates:
        if date in corpus_dates:
            found_anchors.append(('date', date))
        elif date in corpus_text_norm:
            found_anchors.append(('date_in_corpus', date))
        # Dates alone don't make UNLINKED_ENTITY - they need context
    
    # Check quoted titles
    for title in all_titles:
        title_norm = _normalize_for_match(title)
        if any(title_norm in ct or ct in title_norm for ct in corpus_titles_norm):
            found_anchors.append(('title', title))
        elif title_norm in corpus_text_norm:
            found_anchors.append(('title_in_corpus', title))
        elif len(title_norm) >= 4:
            unlinked.append(('title', title))
    
    # Determine classification
    has_any_entities = bool(all_proper or all_titles)  # dates alone don't count
    
    if found_anchors:
        return {
            'classification': 'ANCHORED',
            'anchor': found_anchors[0],
            'all_anchors': found_anchors,
            'entities_found': entities,
        }
    elif unlinked:
        return {
            'classification': 'UNLINKED_ENTITY',
            'unlinked_entities': unlinked,
            'entities_found': entities,
        }
    elif has_any_entities:
        # Has entities but none are substantive enough to flag as unlinked
        # This is effectively no meaningful anchor
        return {
            'classification': 'NO_ANCHOR',
            'entities_found': entities,
            'note': 'entities found but too generic to classify as unlinked',
        }
    else:
        return {
            'classification': 'NO_ANCHOR',
            'entities_found': entities,
        }


# ─── Tour parsing ───────────────────────────────────────────────────────────

def parse_tour_stops(tour_content: str) -> List[Dict]:
    """Parse tour_content text into structured stops with paragraphs.
    
    Handles two formats:
    1. "Stop N: Title" markers (most tours)
    2. Title followed by Address line (older tours without Stop N: prefix)
    
    Returns list of dicts:
      - title: stop title
      - paragraphs: list of content paragraphs (excluding metadata, directions)
      - raw_text: full stop text
    """
    if not tour_content:
        return []
    
    # Detect format
    has_stop_markers = bool(re.search(r'Stop \d+:', tour_content))
    
    if has_stop_markers:
        # Format 1: Split by "Stop N:" pattern
        parts = re.split(r'\nStop \d+:\s*', tour_content)
        # Also handle "Stop N: Title" at the very start of content
        if not parts[0].strip() or 'Tour-Category' in parts[0]:
            parts = parts[1:]  # Skip header
        else:
            # Check if first part starts with Stop
            if re.match(r'Stop \d+:', tour_content):
                parts = re.split(r'Stop \d+:\s*', tour_content)[1:]
            else:
                parts = parts[1:]
    else:
        # Format 2: Split on title lines followed by Address
        # Pattern: line with title text, then \n\nAddress: ...
        parts = re.split(r'\n(?=[^\n]+\n\nAddress:)', tour_content)
        # First part might be a header (if content doesn't start with a stop)
        if parts and ('Address:' not in parts[0][:200]):
            parts = parts[1:]  # Skip header without Address
    
    stops = []
    for part in parts:
        lines = part.strip().split('\n')
        if not lines:
            continue
        
        title = lines[0].strip()
        # Clean title (remove trailing punctuation)
        title = title.rstrip(':').strip()
        
        # Skip if title looks like header/metadata
        if not title or 'Tour-Category' in title or 'Step-by-Step' in title:
            continue
        
        # Parse out metadata vs content paragraphs
        paragraphs = []
        metadata_patterns = [
            r'^Address:', r'^Coordinates:', r'^Type/Specialty:',
            r'^Specific Examples:', r'^Museum Information:',
            r'^Directions?:', r'^\s*$',
        ]
        
        # Collect all non-metadata text as paragraphs
        current_para = []
        in_directions = False
        
        for line in lines[1:]:
            line_stripped = line.strip()
            
            # Skip empty lines (paragraph separator)
            if not line_stripped:
                if current_para:
                    para_text = ' '.join(current_para).strip()
                    if len(para_text) > 50:  # Minimum paragraph length
                        paragraphs.append(para_text)
                    current_para = []
                in_directions = False
                continue
            
            # Skip metadata lines
            is_metadata = False
            for pat in metadata_patterns:
                if re.match(pat, line_stripped, re.IGNORECASE):
                    is_metadata = True
                    if 'direction' in pat.lower():
                        in_directions = True
                    break
            
            if is_metadata or in_directions:
                if current_para:
                    para_text = ' '.join(current_para).strip()
                    if len(para_text) > 50:
                        paragraphs.append(para_text)
                    current_para = []
                continue
            
            # Check if this starts with "Orientation:" - keep the content after the prefix
            if line_stripped.startswith('Orientation:'):
                content_after = line_stripped[len('Orientation:'):].strip()
                # Sometimes "Orientation: Orientation:" doubled
                if content_after.startswith('Orientation:'):
                    content_after = content_after[len('Orientation:'):].strip()
                if content_after:
                    current_para.append(content_after)
            elif line_stripped.startswith('Description:'):
                content_after = line_stripped[len('Description:'):].strip()
                if content_after:
                    current_para.append(content_after)
            else:
                current_para.append(line_stripped)
        
        # Don't forget last paragraph
        if current_para:
            para_text = ' '.join(current_para).strip()
            if len(para_text) > 50:
                paragraphs.append(para_text)
        
        if paragraphs:  # Only include stops that have content paragraphs
            stops.append({
                'title': title,
                'paragraphs': paragraphs,
                'raw_text': part,
            })
    
    return stops


# ─── Main analysis ──────────────────────────────────────────────────────────

def get_venue_corpus_for_tour(tour_id: int, tour_name: str, conn) -> Optional[Dict]:
    """Retrieve the venue corpus relevant to a tour.
    
    Matching strategy:
    1. Extract venue name from tour_name (before " - " suffix)
    2. Search venue_corpus by name similarity (requires >=2 word matches)
    """
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Extract venue name from tour name (format: "Venue Name - Tour Type")
    venue_name = tour_name.split(' - ')[0].strip() if ' - ' in tour_name else tour_name
    
    # Try exact-ish match (full venue name as substring)
    cur.execute(
        "SELECT * FROM venue_corpus WHERE venue_name ILIKE %s",
        (f'%{venue_name}%',)
    )
    row = cur.fetchone()
    if row:
        return dict(row)
    
    # Try significant words (need >=2 matching words to avoid false positives)
    words = [w for w in venue_name.split() if len(w) >= 4 
             and w.lower() not in ('tour', 'france', 'museum', 'nice', 'walking',
                                   'biking', 'cycling', 'restaurant', 'historical')]
    if len(words) >= 2:
        # Try pairs of words for higher precision
        for i in range(len(words)):
            for j in range(i+1, len(words)):
                pattern = f'%{words[i]}%{words[j]}%'
                cur.execute(
                    "SELECT * FROM venue_corpus WHERE venue_name ILIKE %s",
                    (pattern,)
                )
                rows = cur.fetchall()
                if rows:
                    return dict(min(rows, key=lambda r: len(r['venue_name'])))
    
    # Single-word fallback only for very specific words (proper nouns > 6 chars)
    if words:
        specific_words = [w for w in words if len(w) >= 6 and w[0].isupper()]
        for word in specific_words[:2]:
            cur.execute(
                "SELECT * FROM venue_corpus WHERE venue_name ILIKE %s",
                (f'%{word}%',)
            )
            rows = cur.fetchall()
            if rows:
                return dict(min(rows, key=lambda r: len(r['venue_name'])))
    
    return None


def analyze_tour(tour_id: int, conn) -> Dict:
    """Analyze a single tour: classify every paragraph in every stop.
    
    Returns dict with:
      - tour_id, tour_name
      - stops: list of stop analyses
      - summary: counts per classification
    """
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    cur.execute("SELECT id, tour_name, tour_content FROM audio_tours WHERE id = %s", (tour_id,))
    row = cur.fetchone()
    if not row or not row['tour_content']:
        return {'tour_id': tour_id, 'error': 'no content'}
    
    tour_name = row['tour_name']
    tour_content = row['tour_content']
    
    # Get venue corpus
    venue_corpus = get_venue_corpus_for_tour(tour_id, tour_name, conn)
    
    # Parse stops
    stops = parse_tour_stops(tour_content)
    
    # Analyze each stop
    stop_analyses = []
    totals = {'ANCHORED': 0, 'NO_ANCHOR': 0, 'UNLINKED_ENTITY': 0, 'total_paragraphs': 0}
    
    for stop in stops:
        # Build corpus anchors for this specific stop
        corpus_anchors = build_corpus_anchors(
            venue_corpus, stop['title'], tour_name
        ) if venue_corpus else {
            'people': set(), 'dates': set(), 'titles': set(),
            'facts': [], 'all_corpus_people': set(), 'all_corpus_text': '',
        }
        
        para_results = []
        for para in stop['paragraphs']:
            result = classify_paragraph(para, corpus_anchors, stop['title'], tour_name)
            result['text_preview'] = para[:150]
            para_results.append(result)
            totals[result['classification']] += 1
            totals['total_paragraphs'] += 1
        
        stop_analyses.append({
            'title': stop['title'],
            'paragraph_count': len(stop['paragraphs']),
            'paragraphs': para_results,
        })
    
    return {
        'tour_id': tour_id,
        'tour_name': tour_name,
        'has_corpus': venue_corpus is not None,
        'corpus_venue': venue_corpus.get('venue_name', '') if venue_corpus else '',
        'stop_count': len(stops),
        'stops': stop_analyses,
        'summary': totals,
    }


# ─── Report generation ──────────────────────────────────────────────────────

def run_full_report(tour_ids: List[int]) -> str:
    """Run the detector on multiple tours and produce a text report."""
    conn = get_connection()
    
    # Verify row count
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    total_tours = cur.fetchone()[0]
    
    report_lines = []
    report_lines.append("=" * 78)
    report_lines.append("STOP ANCHOR DETECTOR — LOCAL-174 Report")
    report_lines.append("=" * 78)
    report_lines.append(f"\naudio_tours row count: {total_tours}")
    report_lines.append(f"Tours analyzed: {len(tour_ids)}")
    report_lines.append("")
    
    all_results = []
    for tid in tour_ids:
        result = analyze_tour(tid, conn)
        all_results.append(result)
    
    # ── Michael's examples sanity check ──
    report_lines.append("-" * 78)
    report_lines.append("SANITY CHECK: Michael's examples from ClickUp wdvrdaxa7h")
    report_lines.append("-" * 78)
    
    # Example 1: Generic Cap d'Antibes paragraph (should be NO_ANCHOR)
    example1 = ("Cycling on the French Riviera, stop at Cap d'Antibes to experience "
                "the enduring power of nature, inspiring creativity and stimulating "
                "the imagination while admiring panoramic views and soaking up the "
                "atmosphere of this everyday paradise.")
    
    # Example 2: Fitzgerald name-drop (should be UNLINKED_ENTITY)
    example2 = ("As you stand on Cap d'Antibes with Mediterranean sea stretching out "
                "before you Imagine the scene that once captivated Scott Fitzgerald "
                "inspiring the setting of his timeless novels.")
    
    # Use French Riviera corpus for these examples
    import psycopg2.extras
    cur2 = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur2.execute("SELECT * FROM venue_corpus WHERE venue_name ILIKE '%french riviera%'")
    riviera_corpus = cur2.fetchone()
    riviera_corpus = dict(riviera_corpus) if riviera_corpus else None
    
    corpus_anchors = build_corpus_anchors(riviera_corpus, "Cap d'Antibes", "French Riviera Biking Tour")
    
    result1 = classify_paragraph(example1, corpus_anchors, "Cap d'Antibes", "French Riviera Biking Tour")
    result2 = classify_paragraph(example2, corpus_anchors, "Cap d'Antibes", "French Riviera Biking Tour")
    
    report_lines.append(f"\nExample 1 (generic prose — expected NO_ANCHOR):")
    report_lines.append(f"  Text: \"{example1[:100]}...\"")
    report_lines.append(f"  RESULT: {result1['classification']}")
    report_lines.append(f"  Entities found: {result1.get('entities_found', {})}")
    if result1['classification'] == 'NO_ANCHOR':
        report_lines.append(f"  ✓ MATCHES Michael's judgment")
    else:
        report_lines.append(f"  ✗ DISAGREES with Michael's judgment — detector is WRONG on this example")
    
    report_lines.append(f"\nExample 2 (Fitzgerald name-drop — expected UNLINKED_ENTITY):")
    report_lines.append(f"  Text: \"{example2[:100]}...\"")
    report_lines.append(f"  RESULT: {result2['classification']}")
    if result2.get('unlinked_entities'):
        report_lines.append(f"  Unlinked: {result2['unlinked_entities']}")
    report_lines.append(f"  Entities found: {result2.get('entities_found', {})}")
    if result2['classification'] == 'UNLINKED_ENTITY':
        report_lines.append(f"  ✓ MATCHES Michael's judgment")
    else:
        report_lines.append(f"  ✗ DISAGREES with Michael's judgment — detector is WRONG on this example")
    
    report_lines.append(f"\n  Corpus anchors for Cap d'Antibes:")
    report_lines.append(f"    People: {corpus_anchors.get('people', set())}")
    report_lines.append(f"    Dates: {corpus_anchors.get('dates', set())}")
    report_lines.append(f"    Corpus text length: {len(corpus_anchors.get('all_corpus_text', ''))}")
    
    # ── Per-tour results ──
    report_lines.append("\n" + "=" * 78)
    report_lines.append("PREVALENCE REPORT — Per Tour")
    report_lines.append("=" * 78)
    
    grand_totals = {'ANCHORED': 0, 'NO_ANCHOR': 0, 'UNLINKED_ENTITY': 0, 'total_paragraphs': 0}
    
    for result in all_results:
        if 'error' in result:
            report_lines.append(f"\n  Tour {result['tour_id']}: {result.get('error', 'unknown error')}")
            continue
        
        s = result['summary']
        total = s['total_paragraphs']
        if total == 0:
            continue
        
        report_lines.append(f"\n{'─' * 78}")
        report_lines.append(f"Tour {result['tour_id']}: {result['tour_name']}")
        report_lines.append(f"  Corpus: {'YES' if result['has_corpus'] else 'NO'} ({result['corpus_venue']})")
        report_lines.append(f"  Stops: {result['stop_count']}, Paragraphs: {total}")
        report_lines.append(f"  ANCHORED:        {s['ANCHORED']:3d} ({100*s['ANCHORED']/total:5.1f}%)")
        report_lines.append(f"  NO_ANCHOR:       {s['NO_ANCHOR']:3d} ({100*s['NO_ANCHOR']/total:5.1f}%)")
        report_lines.append(f"  UNLINKED_ENTITY: {s['UNLINKED_ENTITY']:3d} ({100*s['UNLINKED_ENTITY']/total:5.1f}%)")
        
        for k in ('ANCHORED', 'NO_ANCHOR', 'UNLINKED_ENTITY', 'total_paragraphs'):
            grand_totals[k] += s[k]
        
        # Show per-stop breakdown
        for stop in result['stops']:
            classifications = [p['classification'] for p in stop['paragraphs']]
            n_a = classifications.count('ANCHORED')
            n_no = classifications.count('NO_ANCHOR')
            n_ul = classifications.count('UNLINKED_ENTITY')
            total_s = len(classifications)
            report_lines.append(f"    Stop: {stop['title'][:50]:50s} "
                              f"A={n_a} NO={n_no} UL={n_ul} (/{total_s})")
    
    # ── Grand totals ──
    report_lines.append("\n" + "=" * 78)
    report_lines.append("GRAND TOTALS")
    report_lines.append("=" * 78)
    gt = grand_totals['total_paragraphs']
    if gt > 0:
        report_lines.append(f"  Total paragraphs analyzed: {gt}")
        report_lines.append(f"  ANCHORED:        {grand_totals['ANCHORED']:4d} ({100*grand_totals['ANCHORED']/gt:5.1f}%)")
        report_lines.append(f"  NO_ANCHOR:       {grand_totals['NO_ANCHOR']:4d} ({100*grand_totals['NO_ANCHOR']/gt:5.1f}%)")
        report_lines.append(f"  UNLINKED_ENTITY: {grand_totals['UNLINKED_ENTITY']:4d} ({100*grand_totals['UNLINKED_ENTITY']/gt:5.1f}%)")
    
    # ── Sample ANCHORED paragraphs ──
    report_lines.append("\n" + "=" * 78)
    report_lines.append("SAMPLE ANCHORED PARAGRAPHS (with named anchors)")
    report_lines.append("=" * 78)
    
    anchor_samples = []
    for result in all_results:
        if 'error' in result:
            continue
        for stop in result['stops']:
            for para in stop['paragraphs']:
                if para['classification'] == 'ANCHORED' and len(anchor_samples) < 8:
                    anchor_samples.append({
                        'tour': result['tour_name'][:40],
                        'stop': stop['title'][:30],
                        'anchor': para.get('anchor', ('?', '?')),
                        'text': para['text_preview'],
                    })
    
    for s in anchor_samples:
        report_lines.append(f"\n  Tour: {s['tour']}")
        report_lines.append(f"  Stop: {s['stop']}")
        report_lines.append(f"  Anchor: {s['anchor']}")
        report_lines.append(f"  Text: \"{s['text']}...\"")
    
    # ── Sample NO_ANCHOR paragraphs ──
    report_lines.append("\n" + "=" * 78)
    report_lines.append("SAMPLE NO_ANCHOR PARAGRAPHS")
    report_lines.append("=" * 78)
    
    no_anchor_samples = []
    for result in all_results:
        if 'error' in result:
            continue
        for stop in result['stops']:
            for para in stop['paragraphs']:
                if para['classification'] == 'NO_ANCHOR' and len(no_anchor_samples) < 6:
                    no_anchor_samples.append({
                        'tour': result['tour_name'][:40],
                        'stop': stop['title'][:30],
                        'text': para['text_preview'],
                    })
    
    for s in no_anchor_samples:
        report_lines.append(f"\n  Tour: {s['tour']}")
        report_lines.append(f"  Stop: {s['stop']}")
        report_lines.append(f"  Text: \"{s['text']}...\"")
    
    # ── Sample UNLINKED_ENTITY paragraphs ──
    report_lines.append("\n" + "=" * 78)
    report_lines.append("SAMPLE UNLINKED_ENTITY PARAGRAPHS")
    report_lines.append("=" * 78)
    
    unlinked_samples = []
    for result in all_results:
        if 'error' in result:
            continue
        for stop in result['stops']:
            for para in stop['paragraphs']:
                if para['classification'] == 'UNLINKED_ENTITY' and len(unlinked_samples) < 6:
                    unlinked_samples.append({
                        'tour': result['tour_name'][:40],
                        'stop': stop['title'][:30],
                        'unlinked': para.get('unlinked_entities', []),
                        'text': para['text_preview'],
                    })
    
    for s in unlinked_samples:
        report_lines.append(f"\n  Tour: {s['tour']}")
        report_lines.append(f"  Stop: {s['stop']}")
        report_lines.append(f"  Unlinked: {s['unlinked']}")
        report_lines.append(f"  Text: \"{s['text']}...\"")
    
    # ── False positive discussion ──
    report_lines.append("\n" + "=" * 78)
    report_lines.append("FALSE POSITIVE DISCUSSION")
    report_lines.append("=" * 78)
    report_lines.append("""
The anchor test has inherent limitations:

1. ANCHORED paragraphs that a human would call generic:
   - A paragraph containing a date like "17th century" matches if the corpus
     mentions that century for the stop. But "this 17th-century building" is
     still generic if every building on the tour is 17th century.
   - A paragraph mentioning the stop's own name (e.g. "Cap d'Antibes") gets
     ANCHORED if that name appears in corpus context. But self-referencing
     is the weakest possible anchor.

2. NO_ANCHOR paragraphs that are actually stop-specific:
   - Physical descriptions ("the three arched windows above the door") are
     deeply stop-specific but contain no proper nouns or dates.
   - Architectural/artistic technique descriptions may be specific but lack
     named entities.

3. UNLINKED_ENTITY paragraphs where the entity IS genuinely linked:
   - The corpus may be incomplete. Fitzgerald genuinely lived on Cap d'Antibes
     and set 'Tender Is the Night' there. If the corpus doesn't know this,
     the detector correctly reports UNLINKED — the CORPUS doesn't substantiate
     it, even if reality does. This is the intended behavior per D50/D51.
""")
    
    conn.close()
    return '\n'.join(report_lines)


if __name__ == '__main__':
    # Tours to analyze: tour 1 + French Riviera biking + at least 3 others with content
    # Covering museum, walking, and multilingual tours
    TOUR_IDS = [1, 29, 12, 24, 14, 46, 44]
    # 1: Palais Lascaris museum
    # 29: French Riviera Biking Tour (Michael's examples)
    # 12: walking tour in Nice
    # 24: Musée Marc Chagall museum
    # 14: Museum of Naïve Art
    # 46: Boston Common historical
    # 44: MAMAC Nice museum
    
    report = run_full_report(TOUR_IDS)
    print(report)
