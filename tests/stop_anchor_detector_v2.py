#!/usr/bin/env python3
"""stop_anchor_detector_v2.py — LOCAL-175: Hardened anchor metric.

Changes from v1 (LOCAL-174):
1. SIBLING DISCRIMINATION: A token that appears in the corpus text of
   most sibling stops within the same tour is NOT an anchor. Only tokens
   that distinguish THIS stop from its siblings count.
   Threshold: token must appear in <= 50% of sibling stops' corpus text.
   Justification: Michael's test — "if you can substitute the names of
   places and say the same thing about another location, this paragraph
   is redundant." A token present in every stop's corpus is exactly that.

2. NAVIGATION CLASSIFICATION: Wayfinding/instruction sentences ("As you
   enter…", "make your way to…", "turn left") are classified NAVIGATION
   before anchor checking. They are legitimate text that this metric
   should not score — they are not storytelling, they are routing.

3. FOUR classifications: ANCHORED, NO_ANCHOR, UNLINKED_ENTITY, NAVIGATION.
   NAVIGATION paragraphs are excluded from the ANCHORED/NO_ANCHOR/UNLINKED
   percentages. They are reported separately.

Deterministic. No LLM opinion. Read-only against the database.
"""
import re
import sys
import json
from typing import Dict, List, Optional, Tuple, Set

sys.path.insert(0, 'tests')
from db_connection import get_connection

# ─── NLP-lite: proper noun / entity extraction ──────────────────────────────

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

_SENTENCE_STARTERS = {
    'the', 'a', 'an', 'this', 'that', 'here', 'there', 'it', 'he', 'she',
    'we', 'you', 'they', 'as', 'in', 'on', 'at', 'from', 'with', 'for',
    'cycling', 'stand', 'look', 'feel', 'imagine', 'notice', 'find',
    'explore', 'discover', 'continue', 'head', 'follow', 'turn',
    'prepare', 'let', 'take', 'make', 'see', 'hear', 'watch',
}

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

# ─── Navigation / wayfinding detection ──────────────────────────────────────

# Patterns that indicate navigation/wayfinding content
_NAVIGATION_PATTERNS = [
    # Directional instructions
    r'\b(?:turn|head|walk|proceed|continue|make your way|go|move)\s+(?:left|right|straight|ahead|forward|towards?|to|through|along|past|down|up|around|across|back)\b',
    # Entry/exit instructions
    r'\b(?:as you enter|upon entering|when you arrive|step (?:inside|into|through)|enter the|exit the|leave the)\b',
    # Wayfinding imperatives
    r'\b(?:make your way|find your way|navigate|cross the|pass through|look for the|you will (?:find|see|notice|reach)|follow the)\b',
    # Location-within-venue instructions
    r'\b(?:on (?:the|your) (?:left|right)|(?:first|second|third|ground|top|upper|lower) floor|(?:next|adjacent) room|main (?:hall|entrance|lobby))\b',
    # Orientation sentences
    r'^(?:you are|you\'re|we are|we\'re) (?:now |currently )?(?:standing|located|at|in|near|facing|approaching)\b',
    # Distance/direction markers
    r'\b(?:a few (?:steps|meters|feet)|just (?:ahead|beyond|past)|(?:directly|straight) ahead)\b',
]

_NAVIGATION_COMPILED = [re.compile(p, re.IGNORECASE) for p in _NAVIGATION_PATTERNS]

# Additional: a paragraph is NAVIGATION if >60% of its sentences match nav patterns
# OR if the entire paragraph is a single nav instruction
_NAV_VERB_PHRASES = {
    'enter', 'exit', 'turn', 'walk', 'proceed', 'continue', 'head',
    'navigate', 'cross', 'pass', 'approach', 'reach', 'arrive',
    'step', 'move', 'go', 'make your way', 'find your way',
}


def is_navigation_paragraph(paragraph: str) -> bool:
    """Determine if a paragraph is primarily navigation/wayfinding.
    
    A paragraph is NAVIGATION if:
    - It matches 2+ navigation patterns, OR
    - It's short (<150 chars) and matches 1+ navigation pattern, OR
    - >50% of its content words are navigation verbs/phrases
    
    This catches "As you enter the Palais Lascaris, make your way to the
    Grand Salon" — pure wayfinding regardless of what proper nouns it contains.
    """
    text_lower = paragraph.lower()
    
    # Count nav pattern matches
    nav_matches = sum(1 for pat in _NAVIGATION_COMPILED if pat.search(paragraph))
    
    # Short paragraph with any nav pattern → NAVIGATION
    if len(paragraph) < 150 and nav_matches >= 1:
        return True
    
    # Multiple nav patterns → NAVIGATION
    if nav_matches >= 2:
        return True
    
    # Check if the paragraph is predominantly instructional
    # Split into sentences and check what fraction are navigational
    sentences = re.split(r'[.!?]+', paragraph)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]
    
    if not sentences:
        return False
    
    nav_sentences = 0
    for sent in sentences:
        sent_matches = sum(1 for pat in _NAVIGATION_COMPILED if pat.search(sent))
        if sent_matches >= 1:
            nav_sentences += 1
    
    # If >50% of sentences are navigational, the whole paragraph is NAVIGATION
    if len(sentences) >= 2 and nav_sentences / len(sentences) > 0.5:
        return True
    
    return False




# ─── Entity extraction (unchanged from v1) ──────────────────────────────────

def extract_dates(text: str) -> List[str]:
    """Extract year references (4-digit numbers that look like years)."""
    years = re.findall(r'\b(1[0-9]{3}|20[0-9]{2})\b', text)
    return years


def extract_proper_nouns(text: str) -> List[str]:
    """Extract likely proper nouns from text using capitalization heuristics."""
    proper_nouns = []
    sentences = re.split(r'[.!?]\s+|\n', text)
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        words = sentence.split()
        if not words:
            continue
        i = 1
        while i < len(words):
            if words[i][0:1].isupper() and words[i].lower() not in _FALSE_POSITIVE_NAMES:
                name_parts = [words[i]]
                j = i + 1
                while j < len(words):
                    w = words[j]
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
                significant = [p for p in name_parts
                              if len(p) >= 3 and p.lower() not in _FALSE_POSITIVE_NAMES]
                if significant:
                    proper_nouns.append(name)
                i = j
            else:
                i += 1

    title_patterns = re.findall(
        r'\b([A-Z][a-z]?\.\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', text
    )
    proper_nouns.extend(title_patterns)
    seen = set()
    result = []
    for pn in proper_nouns:
        pn_lower = pn.lower()
        if pn_lower not in seen:
            seen.add(pn_lower)
            result.append(pn)
    return result


def extract_entities(text: str) -> Dict[str, List[str]]:
    """Extract all entity-like tokens from a paragraph."""
    proper_nouns = extract_proper_nouns(text)
    dates = extract_dates(text)
    quoted = re.findall(r'["\u201c\u201d\u00ab\u00bb]([^"\u201c\u201d\u00ab\u00bb]+)["\u201c\u201d\u00ab\u00bb]', text)
    quoted += re.findall(r"'([A-Z][^']{2,})'", text)
    return {
        'proper_nouns': proper_nouns,
        'dates': dates,
        'quoted_titles': quoted,
    }


# ─── Corpus anchor matching with sibling discrimination ─────────────────────

def _normalize_for_match(text: str) -> str:
    """Normalize text for fuzzy matching: lowercase, strip accents, collapse whitespace."""
    import unicodedata
    text = text.lower().strip()
    nfkd = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in nfkd if not unicodedata.combining(c))
    text = re.sub(r'\s+', ' ', text)
    return text


def build_corpus_anchors(venue_corpus: Dict, stop_title: str, tour_name: str) -> Dict:
    """Build the set of anchors that the corpus ties to this stop.

    Same as v1 — returns people, dates, titles, facts, all_corpus_text.
    Sibling discrimination happens at classification time, not here.
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

    story_elements = venue_corpus.get('story_elements_json') or []
    canonical_titles = venue_corpus.get('canonical_titles_json') or []
    pages = venue_corpus.get('pages_json') or []

    all_text = ''
    if isinstance(pages, list):
        all_text = ' '.join(p.get('text', '') for p in pages if isinstance(p, dict))
    elif isinstance(pages, dict):
        all_text = pages.get('combined_text', '') or pages.get('text', '')
    anchors['all_corpus_text'] = all_text

    for elem in story_elements:
        people = elem.get('people') or []
        for p in people:
            if p and len(p) > 2:
                anchors['all_corpus_people'].add(p)

    stop_title_norm = _normalize_for_match(stop_title)
    for elem in story_elements:
        elem_text = _normalize_for_match(elem.get('text', ''))
        stop_words = [w for w in stop_title_norm.split() if len(w) >= 4]
        if stop_words:
            match_count = sum(1 for w in stop_words if w in elem_text)
            if match_count < max(1, len(stop_words) * 0.4):
                continue
        people = elem.get('people') or []
        dates = elem.get('dates') or []
        for p in people:
            if p and len(p) > 2:
                anchors['people'].add(p)
        for d in dates:
            if d:
                anchors['dates'].add(str(d))
        anchors['facts'].append(elem.get('text', ''))

    if isinstance(canonical_titles, list):
        for ct in canonical_titles:
            if isinstance(ct, str):
                anchors['titles'].add(ct)
            elif isinstance(ct, dict):
                name = ct.get('name', '')
                if name:
                    anchors['titles'].add(name)

    if all_text:
        stop_name_in_corpus = stop_title_norm in _normalize_for_match(all_text)
        if stop_name_in_corpus:
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


def build_sibling_corpus_texts(venue_corpus: Dict, all_stop_titles: List[str],
                                tour_name: str) -> Dict[str, str]:
    """Build normalized corpus text for each stop in the tour.

    Returns {stop_title: normalized_corpus_text} for sibling discrimination.

    KEY DESIGN DECISION (LOCAL-175 hardening):
    The full venue pages text (all_corpus_text) is SHARED across all stops.
    Any token found only via substring match in that shared text cannot
    distinguish one stop from another — it fails Michael's substitution test
    by definition. Therefore:

    1. Per-stop "specific" text = matched story_elements + canonical title
       for this artwork. This is what CAN distinguish stops.
    2. The shared venue pages text is used ONLY to build the "shared pool" —
       tokens in it that are NOT in any stop's specific text are tour-wide
       chrome (venue name, art period, city context).

    The sibling discrimination rule then becomes:
    - A token is a valid anchor ONLY if it appears in THIS stop's specific
      corpus text and NOT in >50% of sibling stops' specific texts.
    - A token that appears only in the shared venue pages is NEVER a valid
      anchor (it cannot distinguish this stop from siblings).
    """
    result = {}
    if not venue_corpus:
        return result

    for title in all_stop_titles:
        anchors = build_corpus_anchors(venue_corpus, title, tour_name)
        # The "specific" text for this stop = matched facts + people + dates
        # + canonical title text. NOT the shared venue pages.
        specific_text = ' '.join(anchors['facts'])
        for p in anchors['people']:
            specific_text += ' ' + p
        for d in anchors['dates']:
            specific_text += ' ' + d
        for t in anchors['titles']:
            specific_text += ' ' + t
        result[title] = _normalize_for_match(specific_text)

    return result




# ─── Paragraph classification (hardened) ────────────────────────────────────

def classify_paragraph(paragraph: str, corpus_anchors: Dict,
                       stop_title: str, tour_name: str = '',
                       sibling_corpus_texts: Dict[str, str] = None) -> Dict:
    """Classify a paragraph as ANCHORED, NO_ANCHOR, UNLINKED_ENTITY, or NAVIGATION.

    v2 changes:
    1. NAVIGATION check first — wayfinding never counts as content.
    2. Sibling discrimination — a token that appears in >50% of sibling
       stops' corpus-specific text is not a distinguishing anchor.

    Sibling discrimination logic:
    - For each candidate anchor token, check how many sibling stops (other
      stops in the same tour) have that token in their corpus-specific text.
    - If the token appears in > 50% of siblings → it's a "tour-wide" token
      (venue name, art period, city) and does NOT count as an anchor.
    - Threshold justification: if a tour has 6 stops and a token appears
      in 4+ of them, it cannot distinguish this stop. The 50% threshold
      means a token must be in the minority of stops to qualify.
    """
    # ─── Step 0: Navigation check ───
    if is_navigation_paragraph(paragraph):
        return {
            'classification': 'NAVIGATION',
            'entities_found': extract_entities(paragraph),
            'nav_reason': 'wayfinding/instruction content',
        }

    # ─── Step 1: Extract entities ───
    entities = extract_entities(paragraph)
    all_proper = entities['proper_nouns']
    all_dates = entities['dates']
    all_titles = entities['quoted_titles']

    # ─── Step 2: Build exclusion sets (unchanged from v1) ───
    stop_title_norm = _normalize_for_match(stop_title)
    stop_title_words = set(w for w in stop_title_norm.split() if len(w) >= 3)
    tour_name_norm = _normalize_for_match(tour_name)
    tour_name_words = set(w for w in tour_name_norm.split()
                          if len(w) >= 4 and w not in ('tour', 'museum', 'walking', 'biking'))
    location_words = stop_title_words | tour_name_words

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
        name_words = set(name_norm.split())
        significant_words = {w for w in name_words if len(w) >= 3}
        if not significant_words:
            return True
        if significant_words.issubset(location_words | _GEO_GENERICS):
            return True
        if location_words:
            overlap = significant_words & (location_words | _GEO_GENERICS)
            if len(overlap) >= len(significant_words) * 0.6:
                return True
        return False

    # ─── Step 3: Sibling discrimination ───
    #
    # The hardening rule (LOCAL-175): a token is a valid anchor ONLY if it
    # appears in THIS stop's SPECIFIC corpus data. The shared venue pages
    # text (all_corpus_text) is identical for all stops in a venue tour —
    # any token found only there fails Michael's substitution test.
    #
    # "corpus_mention" (v1's weakest anchor type: substring match against
    # shared venue pages) is ELIMINATED as an anchor type. It was the
    # exact mechanism that made "Baroque", "Christ", and venue names
    # count as anchors — the gameable tokens.
    #
    # Valid anchor types in v2:
    #   - 'person': entity matched to stop-specific story_elements people
    #   - 'date': year matched to stop-specific story_elements dates
    #   - 'title': matches a canonical_title for this stop's artwork
    #   - 'stop_specific_mention': token found in THIS stop's specific
    #     corpus text AND in <50% of sibling stops' specific texts

    # Get this stop's specific corpus text (story elements + canonical titles)
    this_stop_specific = ''
    if sibling_corpus_texts:
        this_stop_specific = sibling_corpus_texts.get(stop_title, '')

    def _strip_possessive(token: str) -> str:
        """Strip English/French possessive suffixes for matching."""
        for suffix in ("'s", "'s", "'"):
            if token.endswith(suffix):
                return token[:-len(suffix)]
        return token

    def _token_in_stop_specific(token_norm: str) -> bool:
        """Check if token appears in this stop's specific corpus text.
        Also checks the stem without possessive (chagall's → chagall)."""
        if not this_stop_specific:
            return False
        if token_norm in this_stop_specific:
            return True
        stem = _strip_possessive(token_norm)
        if stem != token_norm and stem in this_stop_specific:
            return True
        return False

    def _token_is_sibling_common(token_norm: str) -> bool:
        """Return True if token appears in >50% of sibling stops' specific text.

        Checks both the full token and its possessive-stripped stem.
        If sibling data is unavailable, falls back to venue-name check.
        """
        stem = _strip_possessive(token_norm)

        if not sibling_corpus_texts:
            venue_name_norm = _normalize_for_match(
                tour_name.split(' - ')[0] if ' - ' in tour_name else tour_name)
            if token_norm in venue_name_norm or venue_name_norm in token_norm:
                return True
            if stem != token_norm and (stem in venue_name_norm or venue_name_norm in stem):
                return True
            return False

        siblings = {t: txt for t, txt in sibling_corpus_texts.items()
                    if t != stop_title}
        if not siblings:
            return False

        # Count siblings that contain either the full token or its stem
        sibling_count = sum(
            1 for txt in siblings.values()
            if txt and (token_norm in txt or (stem != token_norm and stem in txt))
        )
        total_siblings = len(siblings)

        # Threshold: >50% of siblings have this token
        if sibling_count > total_siblings * 0.5:
            return True

        # Always exclude the venue name itself
        venue_name_norm = _normalize_for_match(
            tour_name.split(' - ')[0] if ' - ' in tour_name else tour_name)
        if token_norm in venue_name_norm or venue_name_norm in token_norm:
            return True
        if stem != token_norm and (stem in venue_name_norm or venue_name_norm in stem):
            return True

        return False

    # ─── Step 4: Check for anchors ───
    found_anchors = []
    unlinked = []

    corpus_people_norm = {_normalize_for_match(p) for p in corpus_anchors.get('people', set())}
    corpus_dates = corpus_anchors.get('dates', set())
    corpus_titles_norm = {_normalize_for_match(t) for t in corpus_anchors.get('titles', set())}
    all_corpus_people_norm = {_normalize_for_match(p) for p in corpus_anchors.get('all_corpus_people', set())}
    corpus_text_norm = _normalize_for_match(corpus_anchors.get('all_corpus_text', ''))

    for pn in all_proper:
        pn_norm = _normalize_for_match(pn)
        pn_norm = pn_norm.rstrip('.,;:!?')

        if _is_geographic_self_reference(pn_norm):
            continue
        if len(pn_norm) < 4:
            continue

        # STRONG anchor: person from stop-specific story elements
        if any(pn_norm in cp or cp in pn_norm for cp in corpus_people_norm):
            if not _token_is_sibling_common(pn_norm):
                found_anchors.append(('person', pn))
            # If sibling-common, skip silently (not unlinked, just not distinguishing)
            continue

        # MEDIUM anchor: token in this stop's specific corpus text
        # (not just the shared venue pages)
        if _token_in_stop_specific(pn_norm):
            if not _token_is_sibling_common(pn_norm):
                found_anchors.append(('stop_specific_mention', pn))
            continue

        # v2 HARDENING: shared venue pages text (corpus_mention) is NO LONGER
        # a valid anchor. A token that only appears in text shared across all
        # stops cannot distinguish this stop from siblings.
        # If it's in the shared text but not stop-specific, it's noise.
        if pn_norm in corpus_text_norm:
            # Previously this was 'corpus_mention' — now it's just noise.
            # Don't flag as unlinked either (it IS in the corpus, just not
            # stop-specifically).
            continue

        # Not in corpus at all → UNLINKED_ENTITY candidate
        if len(pn_norm) >= 5:
            unlinked.append(('person', pn))

    for date in all_dates:
        if date in corpus_dates:
            if not _token_is_sibling_common(date):
                found_anchors.append(('date', date))
        elif _token_in_stop_specific(date):
            if not _token_is_sibling_common(date):
                found_anchors.append(('date_in_specific', date))
        # v2: dates only in shared corpus text are NOT anchors

    for title in all_titles:
        title_norm = _normalize_for_match(title)
        if any(title_norm in ct or ct in title_norm for ct in corpus_titles_norm):
            if not _token_is_sibling_common(title_norm):
                found_anchors.append(('title', title))
        elif _token_in_stop_specific(title_norm):
            if not _token_is_sibling_common(title_norm):
                found_anchors.append(('title_in_specific', title))
        elif len(title_norm) >= 4:
            unlinked.append(('title', title))

    # ─── Step 5: Determine classification ───
    has_any_entities = bool(all_proper or all_titles)

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
        return {
            'classification': 'NO_ANCHOR',
            'entities_found': entities,
            'note': 'entities found but too generic or sibling-common to count',
        }
    else:
        return {
            'classification': 'NO_ANCHOR',
            'entities_found': entities,
        }



# ─── Tour parsing (unchanged from v1) ───────────────────────────────────────

def parse_tour_stops(tour_content: str) -> List[Dict]:
    """Parse tour_content text into structured stops with paragraphs."""
    if not tour_content:
        return []

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

    stops = []
    for part in parts:
        lines = part.strip().split('\n')
        if not lines:
            continue
        title = lines[0].strip().rstrip(':').strip()
        if not title or 'Tour-Category' in title or 'Step-by-Step' in title:
            continue

        paragraphs = []
        metadata_patterns = [
            r'^Address:', r'^Coordinates:', r'^Type/Specialty:',
            r'^Specific Examples:', r'^Museum Information:',
            r'^Directions?:', r'^\s*$',
        ]
        current_para = []
        in_directions = False

        for line in lines[1:]:
            line_stripped = line.strip()
            if not line_stripped:
                if current_para:
                    para_text = ' '.join(current_para).strip()
                    if len(para_text) > 50:
                        paragraphs.append(para_text)
                    current_para = []
                in_directions = False
                continue

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

            if line_stripped.startswith('Orientation:'):
                content_after = line_stripped[len('Orientation:'):].strip()
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

        if current_para:
            para_text = ' '.join(current_para).strip()
            if len(para_text) > 50:
                paragraphs.append(para_text)

        if paragraphs:
            stops.append({
                'title': title,
                'paragraphs': paragraphs,
                'raw_text': part,
            })

    return stops


# ─── Main analysis ──────────────────────────────────────────────────────────

def get_venue_corpus_for_tour(tour_id: int, tour_name: str, conn) -> Optional[Dict]:
    """Retrieve the venue corpus relevant to a tour (unchanged from v1)."""
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    venue_name = tour_name.split(' - ')[0].strip() if ' - ' in tour_name else tour_name

    cur.execute(
        "SELECT * FROM venue_corpus WHERE venue_name ILIKE %s",
        (f'%{venue_name}%',)
    )
    row = cur.fetchone()
    if row:
        return dict(row)

    words = [w for w in venue_name.split() if len(w) >= 4
             and w.lower() not in ('tour', 'france', 'museum', 'nice', 'walking',
                                   'biking', 'cycling', 'restaurant', 'historical')]
    if len(words) >= 2:
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

    v2: builds sibling corpus texts for discrimination, adds NAVIGATION count.
    """
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT id, tour_name, tour_content FROM audio_tours WHERE id = %s", (tour_id,))
    row = cur.fetchone()
    if not row or not row['tour_content']:
        return {'tour_id': tour_id, 'error': 'no content'}

    tour_name = row['tour_name']
    tour_content = row['tour_content']

    venue_corpus = get_venue_corpus_for_tour(tour_id, tour_name, conn)
    stops = parse_tour_stops(tour_content)

    # v2: Build sibling corpus texts for discrimination
    all_stop_titles = [s['title'] for s in stops]
    sibling_corpus_texts = build_sibling_corpus_texts(
        venue_corpus, all_stop_titles, tour_name
    ) if venue_corpus else {}

    stop_analyses = []
    totals = {'ANCHORED': 0, 'NO_ANCHOR': 0, 'UNLINKED_ENTITY': 0,
              'NAVIGATION': 0, 'total_paragraphs': 0}

    for stop in stops:
        corpus_anchors = build_corpus_anchors(
            venue_corpus, stop['title'], tour_name
        ) if venue_corpus else {
            'people': set(), 'dates': set(), 'titles': set(),
            'facts': [], 'all_corpus_people': set(), 'all_corpus_text': '',
        }

        para_results = []
        for para in stop['paragraphs']:
            result = classify_paragraph(
                para, corpus_anchors, stop['title'], tour_name,
                sibling_corpus_texts=sibling_corpus_texts
            )
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
    """Run the hardened detector on multiple tours and produce a comparison report."""
    conn = get_connection()

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    total_tours = cur.fetchone()[0]

    report_lines = []
    report_lines.append("=" * 78)
    report_lines.append("STOP ANCHOR DETECTOR v2 — LOCAL-175 Hardened Report")
    report_lines.append("=" * 78)
    report_lines.append(f"\naudio_tours row count: {total_tours}")
    report_lines.append(f"Tours analyzed: {len(tour_ids)}")
    report_lines.append("")
    report_lines.append("HARDENING CHANGES:")
    report_lines.append("  1. Sibling discrimination: token in >50% of sibling stops → not an anchor")
    report_lines.append("  2. Navigation classification: wayfinding → NAVIGATION (not scored)")
    report_lines.append("  3. Threshold justification: Michael's substitution test — if you can say")
    report_lines.append("     the same thing about another stop, it is not an anchor.")
    report_lines.append("")

    all_results = []
    for tid in tour_ids:
        result = analyze_tour(tid, conn)
        all_results.append(result)

    # ── Michael's examples sanity check ──
    report_lines.append("-" * 78)
    report_lines.append("SANITY CHECK: Michael's examples from ClickUp wdvrdaxa7h")
    report_lines.append("-" * 78)

    example1 = ("Cycling on the French Riviera, stop at Cap d'Antibes to experience "
                "the enduring power of nature, inspiring creativity and stimulating "
                "the imagination while admiring panoramic views and soaking up the "
                "atmosphere of this everyday paradise.")
    example2 = ("As you stand on Cap d'Antibes with Mediterranean sea stretching out "
                "before you Imagine the scene that once captivated Scott Fitzgerald "
                "inspiring the setting of his timeless novels.")

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
    if result1['classification'] == 'NO_ANCHOR':
        report_lines.append(f"  ✓ MATCHES Michael's judgment")
    else:
        report_lines.append(f"  ✗ DISAGREES — got {result1['classification']}")

    report_lines.append(f"\nExample 2 (Fitzgerald name-drop — expected UNLINKED_ENTITY):")
    report_lines.append(f"  Text: \"{example2[:100]}...\"")
    report_lines.append(f"  RESULT: {result2['classification']}")
    if result2.get('unlinked_entities'):
        report_lines.append(f"  Unlinked: {result2['unlinked_entities']}")
    if result2['classification'] == 'UNLINKED_ENTITY':
        report_lines.append(f"  ✓ MATCHES Michael's judgment")
    else:
        report_lines.append(f"  ✗ DISAGREES — got {result2['classification']}")

    # ── Wayfinding example ──
    report_lines.append(f"\nExample 3 (wayfinding — expected NAVIGATION, was ANCHORED in v1):")
    wayfinding = "As you enter the Palais Lascaris, make your way to the Grand Salon on the first floor, where a masterpiece awaits."
    cur2.execute("SELECT * FROM venue_corpus WHERE venue_name ILIKE '%Palais Lascaris%'")
    lascaris_corpus = cur2.fetchone()
    lascaris_corpus = dict(lascaris_corpus) if lascaris_corpus else None
    lascaris_anchors = build_corpus_anchors(lascaris_corpus, "The Triumph of David", "Palais Lascaris, Nice, France - museum Tour")
    result3 = classify_paragraph(wayfinding, lascaris_anchors, "The Triumph of David", "Palais Lascaris, Nice, France - museum Tour")
    report_lines.append(f"  Text: \"{wayfinding}\"")
    report_lines.append(f"  RESULT: {result3['classification']}")
    if result3['classification'] == 'NAVIGATION':
        report_lines.append(f"  ✓ Correctly classified as NAVIGATION (was ANCHORED in v1)")
    else:
        report_lines.append(f"  ✗ Expected NAVIGATION, got {result3['classification']}")

    # ── Per-tour results with comparison ──
    report_lines.append("\n" + "=" * 78)
    report_lines.append("PREVALENCE REPORT — Per Tour (v1 → v2 comparison)")
    report_lines.append("=" * 78)

    # v1 baseline numbers (from LOCAL-174 submission)
    v1_baseline = {
        1:  {'ANCHORED': 38.9, 'NO_ANCHOR': 22.2, 'UNLINKED_ENTITY': 38.9, 'total': 18},
        29: {'ANCHORED': 0.0, 'NO_ANCHOR': 34.4, 'UNLINKED_ENTITY': 65.6, 'total': 32},
        12: {'ANCHORED': 0.0, 'NO_ANCHOR': 37.7, 'UNLINKED_ENTITY': 62.3, 'total': 53},
        24: {'ANCHORED': 70.0, 'NO_ANCHOR': 20.0, 'UNLINKED_ENTITY': 10.0, 'total': 10},  # Note: v1 had Chagall in the table as needing to match
        14: {'ANCHORED': 0.0, 'NO_ANCHOR': 60.4, 'UNLINKED_ENTITY': 39.6, 'total': 53},
        46: {'ANCHORED': 0.0, 'NO_ANCHOR': 16.7, 'UNLINKED_ENTITY': 83.3, 'total': 6},
        44: {'ANCHORED': 88.2, 'NO_ANCHOR': 5.9, 'UNLINKED_ENTITY': 5.9, 'total': 17},
    }

    grand_totals = {'ANCHORED': 0, 'NO_ANCHOR': 0, 'UNLINKED_ENTITY': 0,
                    'NAVIGATION': 0, 'total_paragraphs': 0}

    for result in all_results:
        if 'error' in result:
            report_lines.append(f"\n  Tour {result['tour_id']}: {result.get('error', 'unknown error')}")
            continue

        s = result['summary']
        total = s['total_paragraphs']
        if total == 0:
            continue

        tid = result['tour_id']
        v1 = v1_baseline.get(tid, {})

        # For v2 percentages, exclude NAVIGATION from denominator
        content_total = total - s['NAVIGATION']

        report_lines.append(f"\n{'─' * 78}")
        report_lines.append(f"Tour {tid}: {result['tour_name']}")
        report_lines.append(f"  Corpus: {'YES' if result['has_corpus'] else 'NO'} ({result['corpus_venue']})")
        report_lines.append(f"  Stops: {result['stop_count']}, Paragraphs: {total}")
        report_lines.append(f"  NAVIGATION (excluded from %): {s['NAVIGATION']}")
        report_lines.append(f"  Content paragraphs (scored): {content_total}")

        if content_total > 0:
            a_pct = 100 * s['ANCHORED'] / content_total
            n_pct = 100 * s['NO_ANCHOR'] / content_total
            u_pct = 100 * s['UNLINKED_ENTITY'] / content_total
        else:
            a_pct = n_pct = u_pct = 0.0

        v1_a = v1.get('ANCHORED', '?')
        v1_n = v1.get('NO_ANCHOR', '?')
        v1_u = v1.get('UNLINKED_ENTITY', '?')

        report_lines.append(f"  {'':20s} {'v1':>8s}  →  {'v2':>8s}")
        report_lines.append(f"  ANCHORED:        {v1_a:>7}%  →  {a_pct:5.1f}%")
        report_lines.append(f"  NO_ANCHOR:       {v1_n:>7}%  →  {n_pct:5.1f}%")
        report_lines.append(f"  UNLINKED_ENTITY: {v1_u:>7}%  →  {u_pct:5.1f}%")

        for k in ('ANCHORED', 'NO_ANCHOR', 'UNLINKED_ENTITY', 'NAVIGATION', 'total_paragraphs'):
            grand_totals[k] += s[k]

        # Per-stop breakdown
        for stop in result['stops']:
            classifications = [p['classification'] for p in stop['paragraphs']]
            n_a = classifications.count('ANCHORED')
            n_no = classifications.count('NO_ANCHOR')
            n_ul = classifications.count('UNLINKED_ENTITY')
            n_nav = classifications.count('NAVIGATION')
            total_s = len(classifications)
            report_lines.append(f"    Stop: {stop['title'][:50]:50s} "
                              f"A={n_a} NO={n_no} UL={n_ul} NAV={n_nav} (/{total_s})")

    # ── Grand totals ──
    report_lines.append("\n" + "=" * 78)
    report_lines.append("GRAND TOTALS — v1 vs v2")
    report_lines.append("=" * 78)
    gt = grand_totals['total_paragraphs']
    nav = grand_totals['NAVIGATION']
    content = gt - nav
    if content > 0:
        report_lines.append(f"  Total paragraphs: {gt}")
        report_lines.append(f"  NAVIGATION (excluded): {nav} ({100*nav/gt:.1f}% of all)")
        report_lines.append(f"  Content paragraphs (scored): {content}")
        report_lines.append(f"")
        report_lines.append(f"  {'':20s} {'v1':>8s}  →  {'v2':>8s}")
        report_lines.append(f"  ANCHORED:        {'19.7':>7}%  →  {100*grand_totals['ANCHORED']/content:5.1f}%")
        report_lines.append(f"  NO_ANCHOR:       {'34.9':>7}%  →  {100*grand_totals['NO_ANCHOR']/content:5.1f}%")
        report_lines.append(f"  UNLINKED_ENTITY: {'45.4':>7}%  →  {100*grand_totals['UNLINKED_ENTITY']/content:5.1f}%")

    # ── Sample ANCHORED paragraphs (10 for human judgment) ──
    report_lines.append("\n" + "=" * 78)
    report_lines.append("10 SAMPLED ANCHORED PARAGRAPHS (for human judgment)")
    report_lines.append("These passed the hardened test: sibling-discriminating anchors only.")
    report_lines.append("=" * 78)

    anchor_samples = []
    for result in all_results:
        if 'error' in result:
            continue
        for stop in result['stops']:
            for para in stop['paragraphs']:
                if para['classification'] == 'ANCHORED' and len(anchor_samples) < 10:
                    anchor_samples.append({
                        'tour': result['tour_name'][:40],
                        'stop': stop['title'][:30],
                        'anchor': para.get('anchor', ('?', '?')),
                        'all_anchors': para.get('all_anchors', []),
                        'text': para['text_preview'],
                    })

    for i, s in enumerate(anchor_samples, 1):
        report_lines.append(f"\n  [{i}] Tour: {s['tour']}")
        report_lines.append(f"      Stop: {s['stop']}")
        report_lines.append(f"      Anchor: {s['anchor']}")
        if len(s['all_anchors']) > 1:
            report_lines.append(f"      All anchors: {s['all_anchors'][:3]}")
        report_lines.append(f"      Text: \"{s['text']}\"")

    # ── Sample NAVIGATION paragraphs ──
    report_lines.append("\n" + "=" * 78)
    report_lines.append("SAMPLE NAVIGATION PARAGRAPHS (correctly excluded from scoring)")
    report_lines.append("=" * 78)

    nav_samples = []
    for result in all_results:
        if 'error' in result:
            continue
        for stop in result['stops']:
            for para in stop['paragraphs']:
                if para['classification'] == 'NAVIGATION' and len(nav_samples) < 5:
                    nav_samples.append({
                        'tour': result['tour_name'][:40],
                        'stop': stop['title'][:30],
                        'text': para['text_preview'],
                    })

    for s in nav_samples:
        report_lines.append(f"\n  Tour: {s['tour']}")
        report_lines.append(f"  Stop: {s['stop']}")
        report_lines.append(f"  Text: \"{s['text']}\"")

    # ── Noise floor ──
    report_lines.append("\n" + "=" * 78)
    report_lines.append("NOISE FLOOR (D22)")
    report_lines.append("=" * 78)
    report_lines.append("")
    report_lines.append("The detector is DETERMINISTIC: no random seed, no LLM calls,")
    report_lines.append("no sampling. Entity extraction uses regex + capitalization heuristics.")
    report_lines.append("Corpus lookup is a fixed database query.")
    report_lines.append("")
    report_lines.append("Three runs over the same tour set:")

    # Run 3 times to prove determinism
    run_results = []
    for run_num in range(3):
        run_totals = {'ANCHORED': 0, 'NO_ANCHOR': 0, 'UNLINKED_ENTITY': 0,
                      'NAVIGATION': 0, 'total': 0}
        for tid in tour_ids:
            r = analyze_tour(tid, conn)
            if 'error' not in r:
                for k in ('ANCHORED', 'NO_ANCHOR', 'UNLINKED_ENTITY', 'NAVIGATION'):
                    run_totals[k] += r['summary'][k]
                run_totals['total'] += r['summary']['total_paragraphs']
        run_results.append(run_totals)

    for i, rt in enumerate(run_results, 1):
        content = rt['total'] - rt['NAVIGATION']
        if content > 0:
            report_lines.append(f"  Run {i}: ANCHORED={100*rt['ANCHORED']/content:.1f}%  "
                              f"NO_ANCHOR={100*rt['NO_ANCHOR']/content:.1f}%  "
                              f"UNLINKED={100*rt['UNLINKED_ENTITY']/content:.1f}%  "
                              f"NAV={rt['NAVIGATION']}")

    # Check if all runs are identical
    if all(r == run_results[0] for r in run_results):
        report_lines.append("")
        report_lines.append("  All three runs are IDENTICAL.")
        report_lines.append("  Noise floor: ZERO. The metric is fully deterministic.")
        report_lines.append("  Any future change in the score represents a real change in")
        report_lines.append("  either the metric logic or the underlying data.")
    else:
        report_lines.append("")
        report_lines.append("  WARNING: Non-deterministic behavior detected!")
        report_lines.append("  This should not happen — investigate.")

    # ── DB verification ──
    report_lines.append("\n" + "=" * 78)
    report_lines.append("DATABASE VERIFICATION")
    report_lines.append("=" * 78)
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    final_count = cur.fetchone()[0]
    report_lines.append(f"  audio_tours row count before: {total_tours}")
    report_lines.append(f"  audio_tours row count after: {final_count}")
    report_lines.append(f"  Read-only: no INSERT, UPDATE, or DELETE executed")

    conn.close()
    return '\n'.join(report_lines)


if __name__ == '__main__':
    # Same 7 tours as v1 — identical baseline set
    TOUR_IDS = [1, 29, 12, 24, 14, 46, 44]
    report = run_full_report(TOUR_IDS)
    print(report)
