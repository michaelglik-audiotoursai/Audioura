#!/usr/bin/env python3
"""LOCAL-318: Dangling-demonstrative detector and repair gate.

Detects demonstrative noun phrases (this X, these X, that X, those X) where the
head noun (or a synonym used earlier in the stop) has no antecedent in the same
stop's spoken text.

Schema lines (Type/Specialty:, Specific Examples:, etc.) are excluded as
antecedents — they are never spoken.

Repair strategy (mirrors LOCAL-289 degrade path):
  1. If the stop's corpus supplies the actual name → substitute inline
     e.g. "This chickpea flour pancake" → "Socca, a chickpea flour pancake,"
  2. If no corpus name available → delete the sentence entirely

The stop's own title counts as a valid antecedent.
"""
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Schema-label regex
# ---------------------------------------------------------------------------
try:
    from tour_rubric_scorer import SCHEMA_LABEL_RE
except ImportError:
    SCHEMA_LABEL_RE = re.compile(
        r'^(?:Address|Coordinates|Museum Information|Directions|Orientation|'
        r'Type/Specialty|Specific Examples|Operational Details|Sources|'
        r'Tour-Category|Description)\s*:',
        re.IGNORECASE,
    )

# ---------------------------------------------------------------------------
# Demonstrative detection — word-by-word NP extraction
# ---------------------------------------------------------------------------

# Find sentence-initial (or clause-initial) demonstrative words
_DEMONSTRATIVE_START_RE = re.compile(
    r'\b(This|These|That|Those)\s+',
)

# Words that STOP the NP scan (verbs, prepositions, determiners, etc.)
_NP_STOPWORDS = frozenset([
    # Verbs (common in tour prose)
    'is', 'was', 'were', 'are', 'has', 'had', 'have', 'does', 'did', 'do',
    'will', 'would', 'could', 'should', 'might', 'may', 'can', 'shall',
    'seems', 'appears', 'remains', 'becomes', 'feels', 'looks',
    'stands', 'stand', 'serves', 'serve', 'offers', 'offer',
    'reveals', 'reveal', 'depicts', 'depict', 'shows', 'show',
    'exemplifies', 'illustrates', 'demonstrates', 'represents',
    'continues', 'continue', 'invites', 'invite', 'captures', 'capture',
    'holds', 'hold', 'takes', 'take', 'makes', 'make', 'gives', 'give',
    'dates', 'opens', 'opened', 'built', 'created', 'designed', 'painted',
    'provides', 'features', 'houses', 'contains', 'includes',
    'winds', 'weaves', 'meanders', 'stretches', 'covers', 'spans',
    'connects', 'links', 'leads', 'runs', 'lies', 'sits', 'rises',
    'not', 'also', 'still', 'just', 'only', 'even', 'never',
    # Prepositions
    'of', 'in', 'on', 'at', 'to', 'for', 'with', 'from', 'by',
    'into', 'onto', 'upon', 'about', 'through', 'between', 'among',
    'along', 'across', 'beyond', 'before', 'after', 'behind',
    'within', 'beneath', 'above', 'near', 'over', 'under',
    # Conjunctions / subordinators
    'and', 'or', 'but', 'nor', 'yet', 'so', 'as', 'if', 'while',
    # Pronouns / relative
    'who', 'whom', 'which', 'that', 'whose', 'where', 'when', 'how',
    'it', 'its', 'they', 'them', 'their', 'he', 'she', 'we', 'us',
])

# Words that are deictic to the setting/situation, always legitimate
_SETTING_NOUNS = frozenset([
    # Place/setting
    'restaurant', 'restaurants', 'café', 'cafe', 'cafes', 'bistro', 'bistros',
    'museum', 'gallery', 'church', 'cathedral', 'chapel', 'basilica',
    'building', 'buildings', 'structure', 'structures', 'palace', 'palaces',
    'square', 'plaza', 'piazza', 'park', 'garden', 'gardens',
    'street', 'streets', 'road', 'roads', 'avenue', 'boulevard',
    'neighborhood', 'neighbourhood', 'quarter', 'district', 'area', 'areas',
    'city', 'town', 'village', 'region', 'coast', 'coastline',
    'market', 'markets', 'shop', 'shops', 'store', 'stores',
    'harbor', 'harbour', 'port', 'bay', 'beach', 'promenade',
    'bridge', 'fountain', 'monument', 'statue', 'memorial',
    'hotel', 'inn', 'villa', 'château', 'chateau', 'castle', 'fort',
    'site', 'sites', 'place', 'places', 'spot', 'location', 'destination',
    # Time / era
    'day', 'time', 'moment', 'era', 'period', 'century', 'decade',
    'year', 'years', 'season', 'morning', 'evening', 'afternoon',
    # Manner / approach (deictic to narration)
    'way', 'style', 'approach', 'method', 'technique', 'tradition',
    'philosophy', 'practice', 'concept', 'idea', 'spirit',
    'point', 'respect', 'regard', 'sense', 'context',
    # The stop/tour itself
    'stop', 'tour', 'walk', 'journey', 'experience', 'visit',
    # Geographical features (the stop IS the feature)
    'promontory', 'peninsula', 'headland', 'cape', 'cliff', 'cliffs',
    'hill', 'hills', 'mountain', 'mountains', 'valley', 'valleys',
    'island', 'islands', 'lake', 'river', 'gorge', 'gorges',
    'path', 'trail', 'trails', 'route', 'routes', 'passage', 'passageway',
    'stretch', 'landmark', 'landmarks',
    # Generic referents pointing at the stop's subject
    'question', 'questions', 'answer', 'connection', 'connections',
    'element', 'elements', 'example', 'examples', 'detail', 'details',
    'aspect', 'aspects', 'feature', 'features', 'part', 'parts',
    'gem', 'treasure', 'jewel', 'highlight', 'highlights',
])

# Generic nouns that can refer to the stop's subject without antecedent.
# "This painting" at a painting stop, "This piece" at a music stop.
# These are ONLY allowed if the NP is short (≤2 words after demonstrative)
# and not modified by specificity-adding adjectives.
_GENERIC_SUBJECT_NOUNS = frozenset([
    'painting', 'paintings', 'piece', 'pieces', 'artwork', 'artworks',
    'masterpiece', 'masterpieces', 'work', 'works',
    'sculpture', 'sculptures', 'exhibit', 'exhibits', 'display',
    'instrument', 'instruments', 'composition', 'compositions',
    'photograph', 'photographs', 'portrait', 'portraits', 'mural', 'murals',
    'creation', 'creations', 'artifact', 'artifacts', 'relic', 'relics',
    'statue', 'statues', 'mask', 'masks', 'object', 'objects',
    'representation', 'synthesis', 'departure', 'juxtaposition',
    'material', 'use', 'approach', 'legacy', 'influence',
])

# Words that are adjective-like modifiers preceding a head noun in an NP.
# If a word is NOT in this set and NOT in _NP_STOPWORDS, it's treated as the head noun.
_MODIFIER_WORDS = frozenset([
    # Size / shape
    'big', 'small', 'large', 'tiny', 'huge', 'vast', 'narrow', 'wide', 'tall',
    'long', 'short', 'thick', 'thin', 'round', 'flat', 'deep', 'shallow',
    # Age / time
    'ancient', 'old', 'new', 'modern', 'young', 'recent', 'contemporary',
    'medieval', 'baroque', 'renaissance', 'neoclassical', 'gothic', 'romanesque',
    # Quality / evaluation
    'beautiful', 'stunning', 'magnificent', 'gorgeous', 'elegant', 'grand',
    'impressive', 'remarkable', 'extraordinary', 'unique', 'rare', 'fine',
    'exquisite', 'ornate', 'elaborate', 'intricate', 'delicate', 'simple',
    'humble', 'modest', 'rich', 'poor', 'famous', 'renowned', 'celebrated',
    'legendary', 'iconic', 'notable', 'significant', 'important', 'major',
    'minor', 'subtle', 'striking', 'dramatic', 'vibrant', 'vivid',
    'haunting', 'poignant', 'powerful', 'bold', 'gentle', 'serene', 'tranquil',
    'peaceful', 'quiet', 'dynamic', 'lively',
    # Color / material
    'golden', 'silver', 'bronze', 'iron', 'wooden', 'stone', 'marble',
    'red', 'blue', 'green', 'white', 'black', 'dark', 'light', 'bright',
    'pale', 'grey', 'gray',
    # Origin / domain
    'local', 'regional', 'national', 'international', 'european', 'asian',
    'french', 'italian', 'spanish', 'greek', 'roman', 'byzantine', 'ottoman',
    'mediterranean', 'atlantic', 'coastal', 'maritime', 'inland',
    'religious', 'sacred', 'secular', 'royal', 'noble', 'imperial', 'civic',
    'culinary', 'gastronomic', 'artistic', 'cultural', 'musical', 'literary',
    'scenic', 'picturesque', 'panoramic', 'geographical', 'geological',
    'historical', 'historic', 'traditional', 'classical', 'typical',
    # Material / composition (food/art)
    'chickpea', 'olive', 'flour', 'seafood', 'vegetable', 'almond',
    'oil', 'butter', 'cream', 'chocolate', 'lemon', 'herb',
    # Manner / intensity
    'particular', 'specific', 'exact', 'precise', 'deliberate', 'careful',
    'immersive', 'enduring', 'lasting', 'timeless', 'eternal', 'perpetual',
    # Quantity-like
    'whole', 'entire', 'full', 'complete', 'single', 'double', 'triple',
    'various', 'numerous', 'countless', 'several',
    # Compound / hyphenated modifiers (base forms)
    'large-scale', 'small-scale', 'full-scale', 'half-mask',
    'well-known', 'long-term', 'short-term', 'high-quality', 'low-cost',
    # Activity modifiers
    'cycling', 'walking', 'swimming', 'running', 'fishing', 'hunting',
    'dining', 'cooking', 'living', 'trading', 'farming',
])

# Synonym map for antecedent matching
_SYNONYM_PAIRS = {
    'pancake': {'crepe', 'crêpe', 'galette', 'flatbread', 'socca'},
    'crepe': {'pancake', 'crêpe', 'galette'},
    'flatbread': {'pancake', 'focaccia', 'pita'},
    'stew': {'ragout', 'ragoût', 'daube', 'braise'},
    'painting': {'canvas', 'artwork', 'work', 'piece', 'masterpiece', 'tableau'},
    'sculpture': {'statue', 'carving', 'bust', 'piece'},
    'fresco': {'mural', 'painting'},
    'mosaic': {'tilework', 'mosaics'},
    'mosaics': {'mosaic', 'tilework'},
    'facade': {'front', 'exterior', 'frontage'},
    'ceiling': {'vault', 'dome'},
    'work': {'piece', 'artwork', 'painting', 'composition', 'masterpiece'},
    'piece': {'work', 'artwork', 'composition', 'masterpiece'},
    'masterpiece': {'work', 'piece', 'artwork', 'painting'},
}


def _get_stop_body_text(stop_lines: List[str]) -> str:
    """Extract spoken body text from stop lines (schema lines excluded)."""
    body = []
    for line in stop_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if SCHEMA_LABEL_RE.match(stripped):
            continue
        body.append(stripped)
    return ' '.join(body)


def _get_schema_text(stop_lines: List[str]) -> str:
    """Extract only schema-line text (for corpus lookup)."""
    schema = []
    for line in stop_lines:
        stripped = line.strip()
        if stripped and SCHEMA_LABEL_RE.match(stripped):
            schema.append(stripped)
    return ' '.join(schema)


def _normalize(word: str) -> str:
    """Normalize: lowercase, strip trailing punctuation."""
    return word.lower().strip().rstrip('.,;:!?"\')]}')


def _singularize(word: str) -> str:
    """Basic singularization for matching."""
    w = word.lower()
    if w.endswith('ies') and len(w) > 4:
        return w[:-3] + 'y'
    if w.endswith('es') and len(w) > 3:
        base = w[:-2]
        if base.endswith(('sh', 'ch', 'x', 'z', 'ss')):
            return base
    if w.endswith('s') and not w.endswith('ss') and len(w) > 3:
        return w[:-1]
    return w


def _get_synonyms(word: str) -> set:
    """Get known synonyms for a word."""
    w = _singularize(word.lower())
    syns = set()
    if w in _SYNONYM_PAIRS:
        syns.update(_SYNONYM_PAIRS[w])
    for key, vals in _SYNONYM_PAIRS.items():
        if w in vals:
            syns.add(key)
            syns.update(vals)
    syns.discard(w)
    return syns


def _extract_np(text: str, start_pos: int) -> Optional[Tuple[str, str]]:
    """Extract noun phrase starting at start_pos in text.

    Strategy: scan word-by-word. Each word is classified as:
    - modifier (adjective-like) → continue, could be more NP
    - noun (not in modifier set) → this is the head noun, STOP
    - verb/prep/conj → STOP, discard this word

    Returns (full_np, head_noun) or None.
    """
    remaining = text[start_pos:]
    words = []
    pos = 0

    while pos < len(remaining) and len(words) < 6:
        # Skip whitespace
        while pos < len(remaining) and remaining[pos] == ' ':
            pos += 1
        if pos >= len(remaining):
            break

        # Punctuation stops NP
        if remaining[pos] in '.,;:!?()[]"\'':
            break

        # Extract word
        word_start = pos
        while pos < len(remaining) and remaining[pos] not in ' .,;:!?()[]"\'':
            pos += 1
        word = remaining[word_start:pos]

        if not word:
            break

        word_lower = word.lower()

        # Stop at NP-breaking words (verbs, prepositions, etc.)
        if word_lower in _NP_STOPWORDS:
            break

        words.append(word)

        # If this word is NOT a known modifier/adjective, it's the head noun → STOP
        if word_lower not in _MODIFIER_WORDS:
            break

    if not words:
        return None

    full_np = ' '.join(words)
    head_noun = words[-1]

    # Head noun must be at least 3 chars
    if len(head_noun) < 3:
        return None

    return full_np, head_noun


def _noun_has_antecedent(head_noun: str, full_np: str, preceding_text: str,
                         stop_title: str) -> bool:
    """Check if the head noun appears in preceding text or stop title."""
    norm_noun = _normalize(head_noun)
    sing_noun = _singularize(norm_noun)

    search_space = (stop_title + ' ' + preceding_text).lower()

    # Direct match
    if sing_noun in search_space or norm_noun in search_space:
        return True

    # Plural forms
    if norm_noun + 's' in search_space or norm_noun + 'es' in search_space:
        return True

    # Synonyms
    for syn in _get_synonyms(norm_noun):
        if syn in search_space or syn + 's' in search_space:
            return True

    # Full NP words all present = referent was introduced
    np_words = [_normalize(w) for w in full_np.split() if len(w) > 3]
    if len(np_words) >= 2 and all(w in search_space for w in np_words):
        return True

    # Context-creation verbs: if the preceding text contains a creative verb,
    # then "This work/piece/creation/composition" is licensed.
    # "Chagall painted the ceiling. This work took two years." — valid.
    _CREATIVE_NOUNS = {'work', 'piece', 'creation', 'composition', 'masterpiece',
                       'artwork', 'result', 'product', 'achievement', 'project'}
    _CREATIVE_VERBS_RE = re.compile(
        r'\b(?:paint(?:ed|ing|s)?|creat(?:ed|ing|es?)|built|design(?:ed|ing|s)?|'
        r'compos(?:ed|ing|es?)|construct(?:ed|ing|s)?|sculpt(?:ed|ing|s)?|'
        r'craft(?:ed|ing|s)?|produced|commissioned|completed|wrote|written)\b',
        re.IGNORECASE
    )
    if sing_noun in _CREATIVE_NOUNS and _CREATIVE_VERBS_RE.search(search_space):
        return True

    return False


def detect_dangling_demonstratives(
    stop_body: str,
    stop_title: str,
    stop_lines: List[str] = None,
) -> List[Dict]:
    """Detect demonstrative NPs with no antecedent in the stop's spoken text.

    Only flags sentence-initial demonstratives (the real defect pattern).
    Relative-clause "that" and mid-sentence deictic uses are ignored.
    """
    findings = []
    sentences = re.split(r'(?<=[.!?])\s+', stop_body)
    preceding_text = ''

    for sent in sentences:
        # Find sentence-initial demonstrative or after conjunction
        for m in _DEMONSTRATIVE_START_RE.finditer(sent):
            dem_word = m.group(1)
            dem_start = m.start()

            # --- Position filter ---
            # Only consider demonstratives that are:
            #   (a) sentence-initial (pos 0)
            #   (b) after a conjunction (and/but/yet/while)
            if dem_start > 0:
                before = sent[:dem_start].rstrip()
                if not before:
                    pass  # OK, whitespace only before
                elif before[-1] in ';':
                    pass  # after semicolon — clause-initial
                else:
                    # Check if preceded by a conjunction
                    last_word = before.split()[-1].lower().rstrip('.,;:')
                    if last_word not in ('and', 'but', 'yet', 'while', 'or'):
                        continue  # mid-sentence demonstrative — skip

            # --- Extract NP ---
            np_result = _extract_np(sent, m.end())
            if not np_result:
                continue

            full_np, head_noun = np_result

            # --- Setting noun filter ---
            if _normalize(head_noun) in _SETTING_NOUNS:
                continue

            # --- Generic subject noun filter ---
            # "This painting", "This piece", "This exquisite instrument" — when
            # the head noun is a generic subject noun and the NP has at most
            # one modifier (evaluative adjective), it's referring to the stop's
            # own subject. Only flag if modified by CONTENT adjectives that
            # specify a particular kind (e.g. "chickpea flour pancake").
            np_words = full_np.split()
            if _normalize(head_noun) in _GENERIC_SUBJECT_NOUNS:
                # Allow if NP is short (1-2 words) or all modifiers are evaluative
                if len(np_words) <= 2:
                    continue
                # Check if modifiers are all evaluative (in _MODIFIER_WORDS)
                modifiers = [w.lower() for w in np_words[:-1]]
                if all(m in _MODIFIER_WORDS for m in modifiers):
                    continue

            # --- Antecedent check ---
            if not _noun_has_antecedent(head_noun, full_np, preceding_text, stop_title):
                dem_np = dem_word + ' ' + full_np
                findings.append({
                    'sentence': sent.strip(),
                    'demonstrative_np': dem_np,
                    'head_noun': head_noun,
                    'full_np': full_np,
                    'preceding_text_snippet': preceding_text[-200:] if preceding_text else '',
                })

        preceding_text += ' ' + sent

    return findings


def _find_name_in_corpus(head_noun: str, full_np: str,
                         corpus_text: str) -> Optional[str]:
    """Search corpus for the proper name corresponding to a noun phrase."""
    if not corpus_text:
        return None

    np_words = [w.lower() for w in full_np.split() if len(w) > 3]
    corpus_lower = corpus_text.lower()
    head_lower = head_noun.lower()

    if not any(w in corpus_lower for w in np_words) and head_lower not in corpus_lower:
        return None

    corpus_sents = re.split(r'(?<=[.!?])\s+', corpus_text)
    for sent in corpus_sents:
        sent_lower = sent.lower()
        if head_lower not in sent_lower and not any(w in sent_lower for w in np_words):
            continue

        # Patterns: "Name, a <description>" or "Name is a <description>"
        name_patterns = [
            r'([A-Z][a-zéèêëàâùûôîïçñ]+(?:\s+[a-zéèêëàâùûôîïçñ]+)?),\s+a(?:n)?\s+[^.]*?'
            + re.escape(head_lower),
            r'(?:the\s+)([a-zéèêëàâùûôîïçñ]+),\s+a(?:n)?\s+[^.]*?'
            + re.escape(head_lower),
            r'([A-Z][a-zéèêëàâùûôîïçñ]+(?:\s+[a-zéèêëàâùûôîïçñ]+)?)\s+is\s+a(?:n)?\s+[^.]*?'
            + re.escape(head_lower),
            r'([A-Za-zéèêëàâùûôîïçñ]+)\s*\([^)]*' + re.escape(head_lower) + r'[^)]*\)',
        ]

        for pat in name_patterns:
            nm = re.search(pat, sent, re.IGNORECASE)
            if nm:
                name = nm.group(1).strip()
                if name.lower() not in ('the', 'a', 'an', 'this', 'that', 'it',
                                        'its', 'their', 'some', 'many', 'one'):
                    return name

    return None


def repair_dangling_demonstrative(
    sentence: str,
    finding: Dict,
    corpus_text: str = None,
) -> Tuple[str, str]:
    """Attempt to repair a sentence with a dangling demonstrative.

    1. corpus name found → substitute: "Socca, a chickpea flour pancake,"
    2. no name available → delete the sentence
    """
    dem_np = finding['demonstrative_np']
    full_np = finding['full_np']
    head_noun = finding['head_noun']

    proper_name = None
    if corpus_text:
        proper_name = _find_name_in_corpus(head_noun, full_np, corpus_text)

    if proper_name:
        dem_pos = sentence.find(dem_np)
        if dem_pos < 0:
            # Case-insensitive fallback
            lower_sent = sentence.lower()
            lower_dem = dem_np.lower()
            dem_pos = lower_sent.find(lower_dem)

        if dem_pos >= 0:
            after_np = sentence[dem_pos + len(dem_np):]
            cap_name = proper_name[0].upper() + proper_name[1:]

            if after_np.startswith(','):
                replacement = f"{cap_name}, a {full_np.lower()}"
            else:
                replacement = f"{cap_name}, a {full_np.lower()},"

            if dem_pos == 0:
                repaired = replacement + sentence[len(dem_np):]
            else:
                repaired = sentence[:dem_pos] + replacement + sentence[dem_pos + len(dem_np):]

            return repaired, 'repaired'

    return '', 'deleted'


def apply_dangling_demonstrative_gate(
    poi_list: List[Dict],
    stop_corpus_data: Dict = None,
) -> Dict:
    """Apply dangling-demonstrative detection and repair to all stops.

    Args:
        poi_list: list of stop dicts (modified in place)
        stop_corpus_data: dict mapping stop index/name to corpus passages
    """
    stats = {
        'total_detected': 0,
        'total_repaired': 0,
        'total_deleted': 0,
        'stops_affected': 0,
        'findings': [],
    }

    for i, poi in enumerate(poi_list):
        desc = poi.get('description', '') or ''
        if not desc or desc.startswith('['):
            continue

        stop_title = poi.get('name', '') or poi.get('title', '') or ''
        stop_lines = desc.split('\n')
        body_text = _get_stop_body_text(stop_lines)
        schema_text = _get_schema_text(stop_lines)

        if not body_text:
            continue

        findings = detect_dangling_demonstratives(body_text, stop_title, stop_lines)
        if not findings:
            continue

        stats['total_detected'] += len(findings)
        stats['stops_affected'] += 1

        # Build corpus text for repair
        corpus_text = ''
        if stop_corpus_data:
            stop_key = poi.get('name', '') or poi.get('title', '')
            corpus_passages = (
                stop_corpus_data.get(i, []) or
                stop_corpus_data.get(stop_key, []) or
                stop_corpus_data.get(str(i), []) or
                []
            )
            if isinstance(corpus_passages, list):
                corpus_text = ' '.join(corpus_passages)
            elif isinstance(corpus_passages, str):
                corpus_text = corpus_passages

        # Include schema text as corpus (contains factual data)
        corpus_text = (corpus_text + ' ' + schema_text).strip()

        modified_desc = desc
        for finding in findings:
            sentence = finding['sentence']
            repaired, action = repair_dangling_demonstrative(
                sentence, finding, corpus_text
            )

            if action == 'repaired':
                modified_desc = modified_desc.replace(sentence, repaired)
                stats['total_repaired'] += 1
                stats['findings'].append({
                    'stop': i + 1,
                    'stop_name': stop_title,
                    'action': 'repaired',
                    'before': sentence[:200],
                    'after': repaired[:200],
                    'head_noun': finding['head_noun'],
                    'demonstrative_np': finding['demonstrative_np'],
                })
            elif action == 'deleted':
                modified_desc = modified_desc.replace(sentence, '')
                modified_desc = re.sub(r'\s{2,}', ' ', modified_desc).strip()
                stats['total_deleted'] += 1
                stats['findings'].append({
                    'stop': i + 1,
                    'stop_name': stop_title,
                    'action': 'deleted',
                    'sentence': sentence[:200],
                    'head_noun': finding['head_noun'],
                    'demonstrative_np': finding['demonstrative_np'],
                })

        if modified_desc != desc:
            poi['description'] = modified_desc

    return stats
