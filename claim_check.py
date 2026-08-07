"""claim_check.py — Unsupported-claim detector (LOCAL-210).

Canonical location: REPO ROOT. Production imports this; tests/ is not in the
container image (LOCAL-192, 198, 200 — the same mistake three times).

Extracts checkable factual claims from a paragraph and verifies each against
the provided corpus passages. Returns per-claim verdicts using the LOCAL-195
vocabulary: SUPPORTED_PARAPHRASE, SUPPORTED_ELSEWHERE, UNSUPPORTED,
CONTRADICTED, NOT_CHECKABLE.

Design principles (from task specification):
- Evidence is mandatory for SUPPORTED_* verdicts: return the passage substring.
- Prefer erring toward UNSUPPORTED (false pass = fabricated fact reaching listener).
- Do NOT use an LLM — cost per paragraph must be ~$0 for production use.
- Paraphrase detection uses token overlap with a conservative threshold.
"""

import re
import unicodedata
from typing import Dict, List, Optional, Tuple


# ─── Claim types we extract ─────────────────────────────────────────────────

CLAIM_TYPES = {
    'DATE': 'A specific date, year, or decade',
    'NUMBER': 'A number with units or measurement',
    'PROPER_NOUN_PREDICATE': 'A proper noun in a factual assertion',
    'ATTRIBUTION': 'An attribution (X was built/created/designed by Y)',
    'NICKNAME': 'A nickname or epithet ("known as X")',
    'COMPOSITION': 'A material, medium, or physical composition claim',
    'MOVEMENT': 'An art movement or period classification',
}

# ─── Verdict vocabulary (LOCAL-195) ──────────────────────────────────────────

SUPPORTED_PARAPHRASE = 'SUPPORTED_PARAPHRASE'
SUPPORTED_ELSEWHERE = 'SUPPORTED_ELSEWHERE'
UNSUPPORTED = 'UNSUPPORTED'
CONTRADICTED = 'CONTRADICTED'
NOT_CHECKABLE = 'NOT_CHECKABLE'


# ─── Text normalization ──────────────────────────────────────────────────────

def _strip_accents(text: str) -> str:
    """Remove diacritics for matching (é→e, ô→o)."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _normalize(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    return re.sub(r'\s+', ' ', _strip_accents(text).lower()).strip()


def _tokenize(text: str) -> List[str]:
    """Split into alpha-numeric tokens."""
    return re.findall(r'[a-z0-9]+', _normalize(text))


# ─── Claim extraction ────────────────────────────────────────────────────────

# Patterns for dates and years
_YEAR_RE = re.compile(
    r'\b(1[0-9]{3}|20[0-9]{2})\b'
)
_DECADE_RE = re.compile(
    r'\b(1[0-9]{2}0s|20[0-9]0s)\b'
)
_DATE_RE = re.compile(
    r'\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|'
    r'September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|'
    r'Oct|Nov|Dec)\s+\d{4})\b'
    r'|'
    r'\b((?:January|February|March|April|May|June|July|August|September|'
    r'October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
    r'\s+\d{1,2},?\s+\d{4})\b',
    re.IGNORECASE,
)
_FRENCH_DATE_RE = re.compile(
    r'\b(\d{1,2}\s+(?:janvier|février|mars|avril|mai|juin|juillet|août|'
    r'septembre|octobre|novembre|décembre)\s+\d{4})\b',
    re.IGNORECASE,
)

# Numbers with units
_NUMBER_UNIT_RE = re.compile(
    r'\b(\d[\d,\.]*\s*(?:meters?|metres?|feet|ft|km|miles?|kg|pounds?|lbs?|'
    r'tons?|tonnes?|pieces?|works?|paintings?|sculptures?|exhibitions?|'
    r'rooms?|m[²2]|square\s+meters?|hectares?|acres?|years?|centuries?|'
    r'dollars?|euros?|francs?))\b',
    re.IGNORECASE,
)

# Attribution patterns
_ATTRIBUTION_RE = re.compile(
    r'(?:built|created|designed|founded|established|painted|composed|'
    r'sculpted|constructed|commissioned|donated|written|invented)\s+'
    r'(?:by|in)\s+([A-Z][A-Za-zÀ-ÿ\s\-]+?)(?:\.|,|\s+in\s+|\s+on\s+|\s+at\s+)',
    re.IGNORECASE,
)

# Nickname patterns
_NICKNAME_RE = re.compile(
    r'(?:known\s+as|called|nicknamed|dubbed|named)\s+'
    r'["\']?([^"\',.]+)["\']?',
    re.IGNORECASE,
)

# Proper nouns (capitalized multi-word sequences in factual contexts)
_PROPER_NOUN_RE = re.compile(
    r'\b([A-Z][a-zÀ-ÿ]+(?:\s+(?:de|du|des|la|le|von|van|di|da|el|al|del|'
    r'et|the|of|and)\s+)?[A-Z][a-zÀ-ÿ]+(?:\s+[A-Z][a-zÀ-ÿ]+)*)\b'
)

# Material/composition/technique claims (factual assertions about artwork)
_COMPOSITION_RE = re.compile(
    r'\b(?:consists?\s+of|made\s+(?:from|of|with)|'
    r'composed\s+of|constructed\s+(?:from|of|with)|'
    r'crafted\s+(?:from|of)|carved\s+(?:from|in)|'
    r'(?:oil|acrylic|watercolor|tempera|fresco)\s+on\s+(?:canvas|panel|wood|paper)|'
    r'(?:bronze|marble|stone|wood|steel|iron|glass|ceramic|slate)\s+sculpture|'
    r'circular\s+arrangements?|'
    r'natural\s+materials?|'
    r'large-scale\s+(?:painting|sculpture|installation|mural|work)|'
    r'(?:stones?|rocks?|slate|wood|earth|mud)\s+collected|'
    r'depicts?\s+(?:a|an|the)\b|'
    r'portrays?\s+(?:a|an|the)\b)'
    r'',
    re.IGNORECASE,
)

# Art movement/period claims
_MOVEMENT_RE = re.compile(
    r'\b(?:land\s+art|pop\s+art|impressionism|expressionism|cubism|'
    r'fauvism|surrealism|dadaism|minimalism|abstract\s+expressionism|'
    r'nouveau\s+réalisme|arte\s+povera|conceptual\s+art)\b',
    re.IGNORECASE,
)

# Atmosphere/opinion markers — claims containing these are NOT_CHECKABLE
_ATMOSPHERE_MARKERS = re.compile(
    r'\b(captivating|enchanting|invit(?:ing|es?\s+you)|'
    r'imagine|feel|sense\s+of|essence\s+of|spirit\s+of|'
    r'testament\s+to|striking|remarkable|profound|'
    r'ponder|contemplate|reflect\s+on|absorb|'
    r'draws?\s+you|transport(?:s|ing)?\s+you|'
    r'feast\s+for\s+the\s+eyes|pulsate|'
    r'immediately\s+struck|gaze\s+upon|'
    r'embark\s+on|journey\s+through)\b',
    re.IGNORECASE,
)

# Second-person framing exclusions
_SECOND_PERSON_RE = re.compile(
    r'^(?:you\s+(?:are|will|can|may|might|should|could|have)|'
    r'as\s+you\s+|from\s+this\s+vantage)',
    re.IGNORECASE,
)

# Structural/transition sentences (not content)
_STRUCTURAL_RE = re.compile(
    r'^(?:from\s+.+\s+to\s+.+you\s+have\s+followed|'
    r'sources:\s+|'
    r'directions:\s+|'
    r'continue\s+through|'
    r'from\s+.+\s+to\s+.+a\s+collection\s+that)',
    re.IGNORECASE,
)


def _is_atmosphere_only(sentence: str) -> bool:
    """True if the sentence is purely atmospheric/opinion with no factual core."""
    # If it has a year, date, decade, or number, it has a factual claim
    if _YEAR_RE.search(sentence) or _NUMBER_UNIT_RE.search(sentence):
        return False
    if _DATE_RE.search(sentence) or _FRENCH_DATE_RE.search(sentence):
        return False
    if _DECADE_RE.search(sentence):
        return False
    # If it describes composition/materials, it's factual
    if _COMPOSITION_RE.search(sentence):
        return False
    # If it names an art movement, it's factual
    if _MOVEMENT_RE.search(sentence):
        return False
    # If it has a proper noun in a predicate context, it might be factual
    if _PROPER_NOUN_RE.search(sentence):
        # Check for predicate verbs
        if re.search(
            r'\b(?:is|was|were|are|has|had|built|created|opened|'
            r'founded|established|donated|painted|made|consists?|'
            r'reflects?|embod(?:ies|y)|situated|characterized|'
            r'emerged|sought|represents?|depicts?|portrays?|shows?)\b',
            sentence, re.IGNORECASE
        ):
            return False
    # If it has an attribution, it's factual
    if _ATTRIBUTION_RE.search(sentence):
        return False
    # Only mark as atmosphere if it's JUST atmosphere markers and generic language
    words = sentence.split()
    if len(words) < 5:
        return True
    atm_matches = _ATMOSPHERE_MARKERS.findall(sentence)
    return len(atm_matches) >= 2


def _extract_claims_from_sentence(sentence: str) -> List[Dict]:
    """Extract individual checkable claims from a single sentence."""
    claims = []
    sentence = sentence.strip()

    if not sentence or len(sentence) < 10:
        return claims

    # Skip structural/transition sentences
    if _STRUCTURAL_RE.match(sentence):
        return claims

    # Extract date claims
    for m in _DATE_RE.finditer(sentence):
        date_text = m.group(1) or m.group(2)
        if date_text:
            claims.append({
                'text': date_text.strip(),
                'type': 'DATE',
                'sentence': sentence,
            })

    for m in _FRENCH_DATE_RE.finditer(sentence):
        claims.append({
            'text': m.group(1).strip(),
            'type': 'DATE',
            'sentence': sentence,
        })

    # Extract decade claims (1960s, 1970s)
    for m in _DECADE_RE.finditer(sentence):
        decade = m.group(1)
        start = max(0, m.start() - 50)
        end = min(len(sentence), m.end() + 50)
        context = sentence[start:end].strip()
        claims.append({
            'text': f'{decade} (in context: "{context}")',
            'type': 'DATE',
            'sentence': sentence,
        })

    # Extract year claims (only in factual predicates, not "20th century" etc.)
    for m in _YEAR_RE.finditer(sentence):
        year = m.group(1)
        # Check context: is this year part of a factual claim?
        start = max(0, m.start() - 40)
        end = min(len(sentence), m.end() + 40)
        context = sentence[start:end]
        # Skip if it's just "20th and 21st Century" or similar
        if re.search(r'\d+(?:st|nd|rd|th)\s+[Cc]entury', context):
            continue
        # Skip if already captured as part of a date or decade
        already_captured = False
        for c in claims:
            if year in c['text'] and c['type'] == 'DATE':
                already_captured = True
                break
        if not already_captured:
            claims.append({
                'text': f'{year} (in context: "{context.strip()}")',
                'type': 'DATE',
                'sentence': sentence,
            })

    # Extract number+unit claims
    for m in _NUMBER_UNIT_RE.finditer(sentence):
        claims.append({
            'text': m.group(1).strip(),
            'type': 'NUMBER',
            'sentence': sentence,
        })

    # Extract attribution claims
    for m in _ATTRIBUTION_RE.finditer(sentence):
        claims.append({
            'text': f'attributed to {m.group(1).strip()}',
            'type': 'ATTRIBUTION',
            'sentence': sentence,
        })

    # Extract nickname claims
    for m in _NICKNAME_RE.finditer(sentence):
        claims.append({
            'text': f'known as "{m.group(1).strip()}"',
            'type': 'NICKNAME',
            'sentence': sentence,
        })

    # Extract composition/material claims
    for m in _COMPOSITION_RE.finditer(sentence):
        # Get surrounding context for the claim
        start = max(0, m.start() - 20)
        end = min(len(sentence), m.end() + 40)
        context = sentence[start:end].strip()
        claim_text = m.group(0).strip()
        # Avoid duplicates
        already = any(claim_text in c['text'] for c in claims)
        if not already:
            claims.append({
                'text': f'{claim_text} (context: "{context}")',
                'type': 'COMPOSITION',
                'sentence': sentence,
            })

    # Extract art movement claims
    for m in _MOVEMENT_RE.finditer(sentence):
        movement = m.group(0).strip()
        start = max(0, m.start() - 30)
        end = min(len(sentence), m.end() + 50)
        context = sentence[start:end].strip()
        already = any(movement.lower() in c['text'].lower() for c in claims)
        if not already:
            claims.append({
                'text': f'{movement} (context: "{context}")',
                'type': 'MOVEMENT',
                'sentence': sentence,
            })

    # Extract proper noun predicates (names of people, places, artworks
    # that are being asserted as factually related to the subject)
    if not _is_atmosphere_only(sentence):
        for m in _PROPER_NOUN_RE.finditer(sentence):
            name = m.group(1).strip()
            # Filter out common non-claim proper nouns
            if len(name) < 4:
                continue
            # Skip venue/stop names (they're given, not claimed)
            # Skip if it's just a start-of-sentence capitalization
            if m.start() == 0 and not re.match(r'[A-Z][a-z]+\s+[A-Z]', name):
                continue
            # Skip common words that happen to be capitalized
            skip_words = {
                'The', 'This', 'That', 'These', 'Those', 'Each', 'One',
                'As', 'In', 'At', 'On', 'From', 'For', 'With', 'You',
                'Your', 'His', 'Her', 'Its', 'Their', 'Our', 'Step',
                'Position', 'Stand', 'Continue', 'Sources', 'Directions',
            }
            first_word = name.split()[0]
            if first_word in skip_words:
                continue
            # Check it's in a predicate (has a verb nearby)
            start = max(0, m.start() - 30)
            end = min(len(sentence), m.end() + 30)
            context = sentence[start:end].lower()
            predicate_verbs = re.search(
                r'\b(?:is|was|were|are|has|had|have|built|created|opened|'
                r'founded|established|donated|painted|made|consists?|'
                r'reflects?|embod(?:ies|y)|situated|characterized|'
                r'emerged|sought|represents?)\b',
                context,
            )
            if predicate_verbs:
                # Don't duplicate if already captured
                already = any(name in c['text'] for c in claims)
                if not already:
                    claims.append({
                        'text': name,
                        'type': 'PROPER_NOUN_PREDICATE',
                        'sentence': sentence,
                    })

    return claims


def extract_claims(text: str) -> List[Dict]:
    """Extract all checkable factual claims from a paragraph.

    Returns list of {text, type, sentence} dicts.
    Excludes: adjectives, atmosphere, second-person framing.
    """
    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    all_claims = []

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        # Skip pure second-person framing
        if _SECOND_PERSON_RE.match(sentence) and not _YEAR_RE.search(sentence):
            continue
        claims = _extract_claims_from_sentence(sentence)
        all_claims.extend(claims)

    return all_claims


# ─── Lightweight stemmer (no dependencies) ───────────────────────────────────

# Suffix rules ordered longest-first. Each rule: (suffix, min_stem_len, replacement)
_STEM_RULES: List[Tuple[str, int, str]] = [
    ('ational', 4, 'ate'),
    ('tional', 4, 'tion'),
    ('encies', 4, 'ence'),
    ('ancies', 4, 'ance'),
    ('ement', 4, ''),
    ('ments', 4, ''),
    ('ness', 4, ''),
    ('ment', 4, ''),
    ('ting', 3, 't'),
    ('ings', 3, ''),
    ('ions', 3, ''),
    ('tion', 3, 't'),
    ('sion', 3, 's'),
    ('ious', 3, ''),
    ('eous', 3, ''),
    ('ates', 3, 'ate'),
    ('ated', 3, 'ate'),
    ('izes', 3, 'ize'),
    ('ized', 3, 'ize'),
    ('ises', 3, 'ise'),
    ('ised', 3, 'ise'),
    ('ying', 3, 'y'),
    ('ies', 3, 'y'),
    ('ing', 3, ''),
    ('ers', 3, ''),
    ('ent', 3, ''),
    ('ant', 3, ''),
    ('ous', 3, ''),
    ('ive', 3, ''),
    ('ful', 3, ''),
    ('ism', 3, ''),
    ('ist', 3, ''),
    ('als', 3, 'al'),
    ('ed', 3, ''),
    ('es', 3, ''),
    ('ly', 3, ''),
    ('er', 3, ''),
    ('or', 3, ''),
    ('al', 3, ''),
    ('s', 3, ''),
]

# Irregulars: map inflected form → base
_STEM_IRREGULARS: Dict[str, str] = {
    'gave': 'give',
    'given': 'give',
    'gives': 'give',
    'giving': 'give',
    'made': 'make',
    'took': 'take',
    'taken': 'take',
    'built': 'build',
    'went': 'go',
    'gone': 'go',
    'brought': 'bring',
    'thought': 'think',
    'became': 'become',
    'began': 'begin',
    'begun': 'begin',
    'knew': 'know',
    'known': 'know',
    'grew': 'grow',
    'grown': 'grow',
    'came': 'come',
    'ran': 'run',
    'saw': 'see',
    'seen': 'see',
    'held': 'hold',
    'kept': 'keep',
    'left': 'leave',
    'led': 'lead',
    'met': 'meet',
    'paid': 'pay',
    'said': 'say',
    'sent': 'send',
    'set': 'set',
    'shown': 'show',
    'stood': 'stand',
    'wrote': 'write',
    'written': 'write',
}


def _stem(word: str) -> str:
    """Lightweight suffix-stripping stemmer. No external dependencies."""
    if word in _STEM_IRREGULARS:
        return _STEM_IRREGULARS[word]
    for suffix, min_len, replacement in _STEM_RULES:
        if word.endswith(suffix) and len(word) - len(suffix) >= min_len:
            return word[:-len(suffix)] + replacement
    return word


# ─── Synonym groups for paraphrase detection ─────────────────────────────────

# Each group is a frozenset of stems that should be treated as interchangeable
# during matching. Curated conservatively — only tight semantic equivalences
# where the domain meaning is genuinely the same. Broad groups risk false passes.
_SYNONYM_GROUPS: List[frozenset] = [
    # Giving / contributing (these are genuinely interchangeable in museum context)
    frozenset(['donat', 'donate', 'contribut', 'give', 'offer', 'gift', 'bestow', 'endow', 'bequeath']),
    # Popular / mass (in the 'popular culture' / 'mass culture' sense)
    frozenset(['popular', 'mass']),
    # Reference / allusion / borrowing (in art context)
    frozenset(['referenc', 'allus', 'borrow', 'reinterpret', 'reground']),
    # Relate / connect / associate
    frozenset(['relat', 'connect', 'link', 'associat', 'belong']),
]

# Build a lookup: stem → set of all synonyms (their stems)
_SYNONYM_LOOKUP: Dict[str, frozenset] = {}
for _group in _SYNONYM_GROUPS:
    for _word in _group:
        _SYNONYM_LOOKUP[_word] = _group


def _get_synonyms(stem: str) -> frozenset:
    """Return the synonym group containing this stem, or empty frozenset."""
    return _SYNONYM_LOOKUP.get(stem, frozenset())


def _stems_match(stem_a: str, stem_b: str) -> bool:
    """True if two stems match directly or via synonym groups."""
    if stem_a == stem_b:
        return True
    # Check prefix overlap — only for handling stemmer imprecision
    # (e.g., donat/donate, contribut/contribute). Requires 6+ chars
    # and matching prefix of at least 6 to avoid false matches like
    # collaborate/collage (both stem to 'colla*' but are unrelated).
    if len(stem_a) >= 6 and len(stem_b) >= 6:
        if stem_a.startswith(stem_b[:6]) or stem_b.startswith(stem_a[:6]):
            return True
    # Short stems (5 chars): require full equality or synonym
    # This handles donat/donate specifically
    if len(stem_a) >= 4 and len(stem_b) >= 4:
        if stem_a == stem_b[:len(stem_a)] or stem_b == stem_a[:len(stem_b)]:
            return True
    # Check synonym groups
    group = _SYNONYM_LOOKUP.get(stem_a)
    if group and stem_b in group:
        return True
    # Check if stem_b's group contains stem_a
    group_b = _SYNONYM_LOOKUP.get(stem_b)
    if group_b and stem_a in group_b:
        return True
    return False


# ─── Enhanced matching (paraphrase-aware) ────────────────────────────────────

def _find_best_evidence_enhanced(
    claim: Dict,
    passages: List[str],
    threshold: float = 0.60,
) -> Tuple[Optional[str], float]:
    """Second-pass matching using stems + synonyms for paraphrase detection.

    Only called when basic token overlap fails. Uses:
    1. Suffix-stripped stems for morphological variants (donated→donat)
    2. Synonym groups for tight semantic equivalences (donate↔contribute↔give)
    3. Co-occurrence requirement: matching stems must appear in the SAME window

    Does NOT use multi-passage aggregation (too prone to false positives when
    concept fragments appear in unrelated passages).
    """
    claim_text = claim['text']
    core_text = claim_text.split(' (')[0].strip() if ' (' in claim_text else claim_text
    claim_tokens = _tokenize(core_text)

    # Same stopwords as basic matching
    _match_stopwords = {
        'the', 'a', 'an', 'is', 'was', 'are', 'were', 'has', 'had', 'have',
        'of', 'in', 'on', 'at', 'to', 'for', 'by', 'with', 'from', 'as',
        'it', 'its', 'this', 'that', 'and', 'or', 'but', 'not', 'be', 'been',
        'which', 'who', 'their', 'they', 'you', 'your', 'his', 'her',
        'museum', 'work', 'works', 'art', 'artist', 'piece', 'collection',
    }
    content_tokens = [
        t for t in claim_tokens
        if len(t) >= 3 and t not in _match_stopwords
    ]

    if not content_tokens:
        return None, 0.0

    # Stem the content tokens
    claim_stems = [_stem(t) for t in content_tokens]

    # Require minimum content: claims with fewer than 4 content tokens
    # after stopword removal are too ambiguous for synonym matching.
    # Short claims produce too many spurious matches in art museum corpora.
    if len(claim_stems) < 4:
        return None, 0.0

    # Filter out very common stems that appear in most passages
    _generic_stems = {
        'use', 'make', 'take', 'get', 'set', 'put', 'run', 'see', 'come',
        'know', 'think', 'look', 'want', 'tell', 'show', 'find', 'give',
        'say', 'go', 'try', 'call', 'keep', 'let', 'begin', 'seem',
        'help', 'turn', 'start', 'might', 'move', 'live', 'believ',
        'hold', 'bring', 'happen', 'write', 'provid', 'sit', 'stand',
        'los', 'pay', 'meet', 'play', 'lead', 'hav', 'includ',
        'one', 'new', 'also', 'well', 'just', 'even', 'back',
        'large', 'small', 'great', 'long', 'high', 'low', 'first',
        'natur', 'material', 'place', 'time', 'year', 'part',
        'paint', 'color', 'form', 'space', 'creat', 'world',
    }
    # Count non-generic stems — if fewer than 2 remain, bail out
    specific_stems = [s for s in claim_stems if s not in _generic_stems]
    if len(specific_stems) < 2:
        return None, 0.0

    best_score = 0.0
    best_evidence = None

    # Sliding window with stem+synonym matching
    # Uses a larger window (300 chars) since paraphrases may be verbose
    window_size = 300
    step = 50

    for passage in passages:
        passage_norm = _normalize(passage)

        for start_idx in range(0, max(1, len(passage_norm) - window_size + 1), step):
            window = passage_norm[start_idx:start_idx + window_size]
            window_tokens = _tokenize(window)
            window_stems = set(_stem(t) for t in window_tokens)

            # Count concept matches (direct stem + synonym only)
            matched = 0
            for cs in claim_stems:
                # Direct stem match in window
                if cs in window_stems:
                    matched += 1
                    continue
                # Synonym match — window stem is a synonym of this claim stem?
                for ws in window_stems:
                    if _stems_match(cs, ws):
                        matched += 1
                        break

            score = matched / len(claim_stems)
            if score > best_score:
                best_score = score
                if score >= threshold:
                    ev_start = max(0, start_idx)
                    ev_end = min(len(passage), start_idx + window_size)
                    best_evidence = passage[ev_start:ev_end].strip()

    return best_evidence, best_score


# ─── Verdict assignment ──────────────────────────────────────────────────────

def _token_overlap_score(claim_tokens: List[str], passage_tokens: List[str]) -> float:
    """Fraction of claim tokens found in the passage."""
    if not claim_tokens:
        return 0.0
    found = sum(1 for t in claim_tokens if t in passage_tokens)
    return found / len(claim_tokens)


def _find_best_evidence(
    claim: Dict,
    passages: List[str],
    threshold: float = 0.55,
) -> Tuple[Optional[str], float]:
    """Find the best matching passage substring for a claim.

    Returns (evidence_substring, score) or (None, 0.0).

    Key design choice: uses PROXIMITY-AWARE matching. Tokens must co-occur
    within a ~150-char window to count as evidence. This prevents false
    positives from large passages where "natural" and "materials" each appear
    but 5000 characters apart in unrelated contexts.
    """
    claim_text = claim['text']
    # Strip context/parenthetical annotations from claim text
    core_text = claim_text.split(' (')[0].strip() if ' (' in claim_text else claim_text
    core_norm = _normalize(core_text)
    claim_tokens = _tokenize(core_text)

    # Filter to meaningful content tokens (exclude common words)
    _match_stopwords = {
        'the', 'a', 'an', 'is', 'was', 'are', 'were', 'has', 'had', 'have',
        'of', 'in', 'on', 'at', 'to', 'for', 'by', 'with', 'from', 'as',
        'it', 'its', 'this', 'that', 'and', 'or', 'but', 'not', 'be', 'been',
        'which', 'who', 'their', 'they', 'you', 'your', 'his', 'her',
        'museum', 'work', 'works', 'art', 'artist', 'piece', 'collection',
    }
    content_tokens = [
        t for t in claim_tokens
        if len(t) >= 3 and t not in _match_stopwords
    ]

    # If no meaningful content tokens remain, can't reliably match
    if not content_tokens:
        return None, 0.0

    best_score = 0.0
    best_evidence = None

    for passage in passages:
        passage_norm = _normalize(passage)

        # Strategy 1: Direct substring match (strongest evidence)
        if len(core_norm) >= 8 and core_norm in passage_norm:
            idx = passage_norm.find(core_norm)
            start = max(0, idx - 40)
            end = min(len(passage), idx + len(core_norm) + 40)
            evidence = passage[start:end].strip()
            return evidence, 1.0

        # Strategy 2: For years/numbers, check if the value appears with context
        if claim['type'] in ('DATE', 'NUMBER'):
            numbers = re.findall(r'\d{3,}', claim_text)  # 3+ digit numbers only
            for num in numbers:
                if re.search(r'\b' + re.escape(num) + r'\b', passage):
                    pattern = re.compile(
                        r'(.{0,80}' + re.escape(num) + r'.{0,80})'
                    )
                    m = pattern.search(passage)
                    if m:
                        evidence_candidate = m.group(0).strip()
                        ev_tokens = set(_tokenize(evidence_candidate))
                        # Check that content tokens also appear near the number
                        nearby = sum(1 for t in content_tokens if t in ev_tokens)
                        if content_tokens:
                            score = (nearby + 1) / (len(content_tokens) + 1)
                        else:
                            score = 0.5
                        if score > best_score:
                            best_score = score
                            best_evidence = evidence_candidate

        # Strategy 3: Proximity-aware token overlap (sliding window)
        # Content tokens must co-occur within a window.
        window_size = 200
        step = 40
        for start_idx in range(0, max(1, len(passage_norm) - window_size + 1), step):
            window = passage_norm[start_idx:start_idx + window_size]
            window_tokens = set(_tokenize(window))
            found = sum(1 for t in content_tokens if t in window_tokens)
            score = found / len(content_tokens)
            if score > best_score:
                best_score = score
                if score >= threshold:
                    ev_start = max(0, start_idx)
                    ev_end = min(len(passage), start_idx + window_size)
                    best_evidence = passage[ev_start:ev_end].strip()

        # Strategy 3b: Stem-aware sliding window.
        # Catches morphological variants: "donations" vs "donated",
        # "contributions" vs "contributed". Uses same threshold as
        # Strategy 3 because stems are a tight match (same root word).
        content_stems = [_stem(t) for t in content_tokens]
        for start_idx in range(0, max(1, len(passage_norm) - window_size + 1), step):
            window = passage_norm[start_idx:start_idx + window_size]
            window_tokens = _tokenize(window)
            window_stems = set(_stem(t) for t in window_tokens)
            found = sum(1 for s in content_stems if s in window_stems)
            score = found / len(content_stems)
            if score > best_score:
                best_score = score
                if score >= threshold:
                    ev_start = max(0, start_idx)
                    ev_end = min(len(passage), start_idx + window_size)
                    best_evidence = passage[ev_start:ev_end].strip()

    return best_evidence, best_score


def _extract_relevant_chunk(
    claim_tokens: List[str],
    passage: str,
    max_chars: int = 200,
) -> str:
    """Extract the chunk of a passage most relevant to the claim tokens."""
    passage_lower = _normalize(passage)
    # Find position of first matching token
    best_pos = 0
    for token in claim_tokens:
        idx = passage_lower.find(token)
        if idx >= 0:
            best_pos = idx
            break

    start = max(0, best_pos - 40)
    end = min(len(passage), start + max_chars)
    chunk = passage[start:end].strip()
    if start > 0:
        chunk = '…' + chunk
    if end < len(passage):
        chunk = chunk + '…'
    return chunk


def _extract_subject_nouns(sentence: str) -> List[str]:
    """Extract the grammatical subject nouns from a sentence.

    Strategy: the subject phrase is the text BEFORE the first main verb.
    From that phrase, extract content nouns (strip determiners, prepositions).

    Returns a list of lowercase subject-noun tokens, e.g.:
        "The museum opened in 1890." → ['museum']
        "MAMAC was inaugurated in 1975." → ['mamac']
        "Place Massena dates from the mid-1800s." → ['place', 'massena']
        "Henri Matisse lived in Nice." → ['henri', 'matisse']

    If no verb is found, returns an EMPTY list — the subject is
    indeterminate and callers should not assert a match on this basis.
    (LOCAL-219 R2: returning the full sentence as subject caused false
    matches via incidental function words like "also".)
    """
    # Verbs that typically mark the end of a subject phrase
    _SUBJ_VERB_RE = re.compile(
        r'\b(opened|built|created|founded|established|designed|constructed|'
        r'inaugurated|completed|started|began|finished|dates|dated|'
        r'was|were|is|are|has|had|have|lived|worked|moved|arrived|'
        r'painted|sculpted|composed|donated|acquired|sits|stands|'
        r'houses|contains|features|includes|offers|consists|'
        r'emerged|became|remained|represents|depicts|shows)\b',
        re.IGNORECASE
    )
    # Determiners and prepositions to strip from subject phrase
    _SUBJ_STRIP = {
        'the', 'a', 'an', 'this', 'that', 'these', 'those',
        'of', 'in', 'on', 'at', 'to', 'for', 'by', 'with', 'from',
    }
    m = _SUBJ_VERB_RE.search(sentence)
    if m:
        subject_phrase = sentence[:m.start()].strip()
    else:
        # No verb found — cannot identify what the sentence is about.
        # Return empty rather than the whole sentence (which would
        # produce dozens of spurious tokens).
        return []
    # Tokenize and filter
    tokens = _tokenize(subject_phrase)
    return [t for t in tokens if t not in _SUBJ_STRIP and len(t) >= 3 and not t.isdigit()]


def _check_contradiction(
    claim: Dict,
    passages: List[str],
    stop_title: str = '',
) -> Optional[str]:
    """Check if any passage directly contradicts the claim.

    Only for DATE/NUMBER claims where we can check the specific value.
    Returns contradicting evidence or None.

    SAME-SUBJECT REQUIREMENT (LOCAL-218, refined LOCAL-219): Two claims
    conflict only when they are about the same entity or event. The check
    uses GRAMMATICAL SUBJECT extraction — identifying what the sentence is
    *about* — rather than counting shared incidental tokens.

    "The museum opened in 1890." and "The museum opened on 21 June 1990."
    share the subject "museum" → contradiction fires regardless of whether
    incidental tokens like "Nice" or "France" are present.

    "The chapel was built in 1432." vs "The museum opened in 1990."
    have different subjects (chapel ≠ museum) → no contradiction.

    [LOCAL-340] When subject extraction yields nothing (e.g. sentence starts
    with a verb like "Established in 1926..."), the stop_title is used as a
    fallback subject. If corpus passages for this stop mention the stop_title
    AND a competing date, that IS a contradiction — the stop's own corpus is
    the authoritative source for claims about the stop itself.

    If no subject match is found, the verdict is UNSUPPORTED, not
    CONTRADICTED — under-claiming is safer than crying wolf on our gravest
    verdict.
    """
    if claim['type'] not in ('DATE', 'NUMBER'):
        return None

    claim_text = claim['text']
    # Extract the sentence context (more reliable for subject extraction)
    sentence = claim.get('sentence', claim_text)

    numbers_in_claim = re.findall(r'\d+', claim_text)
    if not numbers_in_claim:
        return None

    # ─── Subject extraction (LOCAL-219) ──────────────────────────────────
    # Extract the grammatical subject from the claim sentence. This
    # identifies WHAT is being dated/measured — "the museum", "MAMAC",
    # "Place Massena" — independent of incidental context words.
    claim_subject_nouns = _extract_subject_nouns(sentence)

    # Extract proper nouns from the SUBJECT PHRASE only (LOCAL-219 fix).
    # Proper nouns in adverbial/prepositional phrases (like "Nice" in
    # "built in 1432 in Nice") are incidental locations, NOT the subject.
    # Only proper nouns that appear BEFORE the main verb identify what
    # the sentence is about.
    _month_names = {
        'january', 'february', 'march', 'april', 'may', 'june',
        'july', 'august', 'september', 'october', 'november', 'december',
        'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'oct',
        'nov', 'dec', 'janvier', 'fevrier', 'mars', 'avril', 'mai',
        'juin', 'juillet', 'aout', 'septembre', 'octobre', 'novembre',
        'decembre',
    }

    # Common proper noun prefixes/fragments that appear in many different
    # place names and are too generic to identify a specific entity.
    # "Saint-Tropez" and "Saint-Jean-Cap-Ferrat" both contain "Saint"
    # but are completely different places. These must not drive subject match.
    _proper_noun_generics = {
        'saint', 'port', 'fort', 'mont', 'cap', 'pont', 'tour',
        'villa', 'place', 'parc', 'rue', 'avenue', 'boulevard',
        'grand', 'petit', 'vieux', 'nouveau', 'belle', 'beau',
        'les', 'des', 'sur', 'sous',
        'new', 'old', 'great', 'north', 'south', 'east', 'west',
        'upper', 'lower', 'lake', 'bay', 'cape', 'point', 'hill',
    }

    # Find the subject phrase boundary (before first main verb)
    _SUBJ_BOUNDARY_RE = re.compile(
        r'\b(opened|built|created|founded|established|designed|constructed|'
        r'inaugurated|completed|started|began|finished|dates|dated|'
        r'was|were|is|are|has|had|have|lived|worked|moved|arrived|'
        r'painted|sculpted|composed|donated|acquired|sits|stands|'
        r'houses|contains|features|includes|offers|consists|'
        r'emerged|became|remained|represents|depicts|shows)\b',
        re.IGNORECASE
    )
    verb_match = _SUBJ_BOUNDARY_RE.search(sentence)
    subject_phrase_end = verb_match.start() if verb_match else len(sentence)
    subject_phrase_text = sentence[:subject_phrase_end]

    proper_nouns = set()
    for m in re.finditer(r'\b([A-Z][a-zÀ-ÿ]{2,}|[A-Z]{3,})\b', subject_phrase_text):
        word = m.group(1)
        # Skip sentence-initial capitalization ONLY for Title Case words.
        # ALL-CAPS words (acronyms) are proper nouns regardless of position.
        if m.start() == 0 and not word.isupper():
            continue
        wl = word.lower()
        if wl not in _month_names and wl not in _proper_noun_generics:
            proper_nouns.add(wl)

    # If we have no subject nouns AND no proper nouns, cannot determine
    # what the sentence is about → bail out safely.
    # [LOCAL-340] UNLESS stop_title is available: when a sentence starts with
    # a verb ("Established in 1926..."), subject extraction yields nothing.
    # But if this is the stop's own corpus, the stop_title IS the implicit
    # subject. Use its tokens as proper nouns for same-subject matching.
    if not claim_subject_nouns and not proper_nouns:
        if stop_title:
            # Use stop_title tokens as the subject (accent-folded, lowered)
            _stop_title_folded = _strip_accents(stop_title).lower()
            stop_title_tokens = set(
                t for t in re.findall(r'[a-z]+', _stop_title_folded)
                if len(t) >= 3 and t not in _proper_noun_generics
            )
            if stop_title_tokens:
                proper_nouns = stop_title_tokens
            else:
                return None
        else:
            return None

    for passage in passages:
        passage_tokens_set = set(_tokenize(passage))

        # ─── Same-subject check (LOCAL-219 rewrite) ──────────────────────
        # Match the SUBJECT of the claim against the passage. Three paths:
        #
        # Path 1: A proper noun from the claim appears in the passage.
        #     "MAMAC was inaugurated in 1975" vs passage mentioning "MAMAC"
        #
        # Path 2: The grammatical subject noun(s) of the claim appear in
        #     the passage. "The museum opened in 1890" matches a passage
        #     containing "museum" because that IS the subject.
        #     A single shared subject noun is sufficient — this is what
        #     the sentence is *about*, not a coincidental overlap.
        #
        # Path 3 (legacy fallback): If subject extraction yields nothing
        #     useful, fall back to requiring 2+ shared non-stopword tokens
        #     covering 50%+ of claim content (the LOCAL-218 rule).
        #
        # Incidental tokens ("Nice", "France", "June") that appear in
        # adverbial phrases do NOT appear in the subject phrase and thus
        # cannot influence the decision. Their presence or absence is
        # irrelevant — exactly the property we need.

        proper_overlap = proper_nouns & passage_tokens_set

        has_subject_match = False

        # Path 1: proper noun match
        if proper_overlap:
            has_subject_match = True

        # Path 2: grammatical subject noun match
        if not has_subject_match and claim_subject_nouns:
            # Extract subject nouns from the passage too
            passage_subject_nouns = _extract_subject_nouns(passage)
            # Check if any claim subject noun matches a passage subject noun.
            #
            # GUARD (LOCAL-219): Generic common nouns like "museum", "park",
            # "building", "villa" are too weak to confirm same-subject across
            # a multi-venue corpus. They identify a CLASS, not an instance.
            # However, if the generic noun matches AND the predicate verb
            # also matches (e.g., both say "museum opened"), that IS the
            # same event — the subject + predicate combination narrows the
            # reference sufficiently.
            _GENERIC_SUBJECT_NOUNS = {
                'museum', 'musee', 'park', 'building', 'villa', 'palace',
                'palais', 'castle', 'chateau', 'church', 'chapel', 'cathedral',
                'gallery', 'hall', 'house', 'maison', 'tower', 'fort',
                'garden', 'square', 'plaza', 'place', 'bridge', 'port',
                'harbor', 'beach', 'hotel', 'monument', 'statue', 'fountain',
                'theatre', 'theater', 'cinema', 'school', 'university',
                'library', 'market', 'station', 'temple', 'mosque',
                'festival', 'exhibition', 'collection', 'centre', 'center',
                'itself', 'first', 'ever',
                # Place-name prefixes and spatial words (LOCAL-219 R2)
                'saint', 'mont', 'cap', 'pont', 'bay', 'cape', 'isle',
                'shores', 'nestled', 'located', 'situated',
                'commune', 'town', 'city', 'village', 'region', 'area',
                'coast', 'promenade', 'avenue', 'boulevard', 'rue',
            }
            claim_subj_set = set(claim_subject_nouns)
            passage_subj_set = set(passage_subject_nouns)
            subj_overlap = claim_subj_set & passage_subj_set
            # Remove generic nouns from the overlap
            specific_overlap = subj_overlap - _GENERIC_SUBJECT_NOUNS
            if specific_overlap:
                # At least one specific (non-generic) subject noun matches
                has_subject_match = True
            elif subj_overlap:
                # Only generic nouns match. Check if the predicate verb
                # also matches — "museum opened" in both is strong evidence
                # of same-event, even though "museum" alone is weak.
                _PREDICATE_VERBS_RE = re.compile(
                    r'\b(opened|built|created|founded|established|designed|'
                    r'constructed|inaugurated|completed|started|began|'
                    r'finished|dated|dates|dedicated|moved|arrived|'
                    r'lived|worked|painted|sculpted|donated|acquired|'
                    r'commissioned|renovated|restored|demolished|closed|'
                    r'reopened|expanded|converted|transformed)\b',
                    re.IGNORECASE
                )
                claim_verbs = set(
                    v.lower() for v in _PREDICATE_VERBS_RE.findall(sentence)
                )
                passage_verbs = set(
                    v.lower() for v in _PREDICATE_VERBS_RE.findall(passage)
                )
                shared_verbs = claim_verbs & passage_verbs
                if shared_verbs:
                    # Same generic subject + same predicate verb = same event
                    has_subject_match = True
                elif len(subj_overlap) >= 2:
                    # Multiple generic nouns overlap (rare but possible)
                    has_subject_match = True

        # Path 3: legacy fallback — whole-sentence token overlap
        # Only used when subject extraction yields an empty set (rare).
        if not has_subject_match and not claim_subject_nouns and not proper_nouns:
            # This branch is unreachable (we bail early above) but kept
            # for defensive completeness.
            pass

        if not has_subject_match:
            continue

        # ─── Number conflict check (LOCAL-219 R2) ────────────────────────
        # Same subject established — now check if numbers differ.
        #
        # THREE requirements for CONTRADICTED:
        # 1. The passage must contain at least one 3+ digit number
        #    (a passage silent on dates/quantities cannot contradict).
        # 2. The claim's specific number must NOT appear in the passage
        #    (if it does, the passage agrees — no contradiction).
        # 3. The passage's competing number must appear IN PROXIMITY TO
        #    tokens from the claim's predicate context. This ensures
        #    the passage is asserting a date/value for the SAME event,
        #    not just having a random number somewhere.
        #
        # Without (3), "lighthouse since 1827" gets CONTRADICTED by a
        # passage saying "Cap Ferrat population 72,999" — same place,
        # completely unrelated assertion. The number 72,999 has nothing
        # to do with the lighthouse. Requirement (3) catches this: the
        # passage number must appear near words like "lighthouse",
        # "beacon", "sailors", "opened", etc. to confirm it's about
        # the same predicate.
        passage_numbers = set(re.findall(r'\d+', passage))
        passage_significant_numbers = {n for n in passage_numbers if len(n) >= 3}
        if not passage_significant_numbers:
            continue  # No competing numbers → cannot contradict

        # Extract predicate context tokens from the claim sentence.
        # These are the meaningful words AROUND the number that tell us
        # what the number is about (e.g., "opened", "inaugurated",
        # "lighthouse", "beacon", "sailors").
        _predicate_stopwords = {
            'the', 'a', 'an', 'is', 'was', 'are', 'were', 'has', 'had',
            'have', 'of', 'in', 'on', 'at', 'to', 'for', 'by', 'with',
            'from', 'as', 'it', 'its', 'this', 'that', 'and', 'or', 'but',
            'not', 'be', 'been', 'which', 'who', 'their', 'they', 'also',
            'you', 'your', 'his', 'her', 'since', 'until', 'during',
            'between', 'after', 'before', 'about', 'than', 'more', 'most',
            'very', 'just', 'only', 'other', 'would', 'could', 'should',
            'into', 'over', 'under', 'through', 'then', 'when', 'where',
            'how', 'all', 'each', 'every', 'both', 'few', 'many', 'some',
            'any', 'such', 'what', 'face', 'due', 'harsh',
        }
        # Also exclude common place names and generic nouns that appear
        # incidentally in both claims and passages without indicating the
        # same event/predicate.
        _predicate_generic = {
            'nice', 'france', 'paris', 'antibes', 'cannes', 'monaco',
            'vence', 'saint', 'jean', 'paul', 'cap', 'ferrat', 'mont',
            'place', 'became', 'world', 'first', 'city', 'town', 'village',
            'area', 'region', 'coast', 'french', 'south', 'north',
            'east', 'west', 'riviera', 'cote', 'azur', 'alpes',
            'maritimes', 'mediterranean', 'european', 'international',
            'national', 'local', 'modern', 'contemporary', 'ancient',
            'nature', 'natural', 'historical', 'cultural', 'artistic',
            # Time words (too generic — "four years" ≠ "later years")
            'years', 'year', 'time', 'century', 'period', 'later',
            'early', 'late', 'long', 'new', 'old',
            # Generic verbs that appear in many contexts
            'made', 'work', 'worked', 'make', 'became', 'stands',
            'known', 'named', 'called', 'used', 'took',
            # Common descriptive words
            'great', 'famous', 'well', 'much', 'many', 'most',
            'large', 'small', 'major', 'important', 'significant',
            'along', 'around', 'within', 'near',
            # Venue/building types (appear incidentally in many passages)
            'museum', 'musee', 'gallery', 'palace', 'chateau',
            'castle', 'church', 'cathedral', 'houses', 'building',
            'collection', 'exhibition', 'exposition',
        }
        sentence_tokens = _tokenize(sentence)
        predicate_context_tokens = set(
            t for t in sentence_tokens
            if len(t) >= 4
            and t not in _predicate_stopwords
            and t not in _predicate_generic
            and not t.isdigit()
        )
        # Remove the subject tokens themselves — we already matched on those;
        # what we need is evidence that the passage asserts a number about
        # the same PREDICATE, not just the same subject.
        predicate_context_tokens -= set(claim_subject_nouns)
        predicate_context_tokens -= proper_nouns

        for cn in numbers_in_claim:
            if cn not in passage_numbers and len(cn) >= 3:
                # The passage has a different number. But does it appear
                # in the context of the same predicate/event?
                #
                # Check: does ANY passage number (3+ digits, not equal to
                # claim number) appear within 120 chars of at least one
                # predicate context token?
                passage_norm = _normalize(passage)
                found_proximate_conflict = False
                best_chunk = None

                for pn in passage_significant_numbers:
                    if pn == cn:
                        continue  # This one agrees, not a conflict
                    # Find positions of this number in the passage
                    for num_match in re.finditer(r'\b' + re.escape(pn) + r'\b', passage_norm):
                        num_pos = num_match.start()
                        # Check if any predicate context token is nearby
                        window_start = max(0, num_pos - 120)
                        window_end = min(len(passage_norm), num_pos + len(pn) + 120)
                        window = passage_norm[window_start:window_end]
                        window_tokens = set(_tokenize(window))

                        # Require at least 1 predicate context token nearby
                        nearby_context = predicate_context_tokens & window_tokens
                        if nearby_context:
                            found_proximate_conflict = True
                            # Extract evidence chunk around the number
                            ev_start = max(0, num_pos - 30)
                            ev_end = min(len(passage), num_pos + 120)
                            best_chunk = passage[ev_start:ev_end].strip()
                            break

                    if found_proximate_conflict:
                        break

                if found_proximate_conflict and best_chunk:
                    return best_chunk

    return None


# ─── Thresholds ──────────────────────────────────────────────────────────────

# Conservative: prefer UNSUPPORTED over false SUPPORTED
PARAPHRASE_THRESHOLD = 0.55  # token overlap needed for SUPPORTED_PARAPHRASE
ELSEWHERE_THRESHOLD = 0.55   # same threshold for SUPPORTED_ELSEWHERE
ENHANCED_THRESHOLD = 0.70    # stem+synonym pass: higher bar (fuzzier match = stricter gate)


# ─── Main entry point ────────────────────────────────────────────────────────

def check_paragraph(
    text: str,
    stop_title: str,
    venue_name: str,
    passages: List[str],
    other_stop_passages: Optional[List[str]] = None,
) -> Dict:
    """Check a paragraph for unsupported factual claims.

    Args:
        text: The paragraph text to check.
        stop_title: Title of the stop this paragraph belongs to.
        venue_name: Name of the venue.
        passages: Corpus passages for THIS stop.
        other_stop_passages: Corpus passages for OTHER stops in the tour
            (for detecting SUPPORTED_ELSEWHERE / D62 entity conflation).

    Returns:
        {
            'claims': [
                {
                    'text': str,        # The claim text
                    'type': str,        # DATE, NUMBER, PROPER_NOUN_PREDICATE, etc.
                    'verdict': str,     # SUPPORTED_PARAPHRASE, UNSUPPORTED, etc.
                    'evidence': str|None,  # Passage substring (mandatory for SUPPORTED_*)
                    'score': float,     # Match confidence (0-1)
                }
            ],
            'unsupported_count': int,       # Count of UNSUPPORTED only (backward compat)
            'verdict_counts': {             # Per-verdict breakdown (LOCAL-218)
                'supported': int,
                'supported_elsewhere': int,
                'unsupported': int,
                'contradicted': int,
                'not_checkable': int,
            },
        }
    """
    # Extract claims
    raw_claims = extract_claims(text)

    # Deduplicate claims with same text
    seen_texts = set()
    unique_claims = []
    for c in raw_claims:
        key = _normalize(c['text'])
        if key not in seen_texts:
            seen_texts.add(key)
            unique_claims.append(c)

    # Filter out claims that are just the stop title or venue name.
    # IMPORTANT (LOCAL-219): Compare against the CORE claim text only,
    # not the parenthetical context annotation. The claim text often
    # includes "(in context: ...)" which contains the full sentence and
    # would spuriously match venue names that appear in the sentence.
    stop_norm = _normalize(stop_title)
    venue_norm = _normalize(venue_name)
    filtered_claims = []
    for c in unique_claims:
        # Strip the "(in context: ...)" or "(context: ...)" annotation
        core_text = c['text'].split(' (')[0].strip() if ' (' in c['text'] else c['text']
        core_norm = _normalize(core_text)
        # Skip if it's just repeating the stop title (guard against empty)
        if stop_norm and (core_norm in stop_norm or stop_norm in core_norm):
            continue
        # Skip if it's just repeating the venue name (guard against empty)
        if venue_norm and (core_norm in venue_norm or venue_norm in core_norm):
            continue
        filtered_claims.append(c)

    # Assign verdicts
    results = []
    for claim in filtered_claims:
        # Check against this stop's passages
        evidence, score = _find_best_evidence(
            claim, passages, threshold=PARAPHRASE_THRESHOLD
        )

        if score >= PARAPHRASE_THRESHOLD and evidence:
            verdict = SUPPORTED_PARAPHRASE
        elif other_stop_passages:
            # Check other stops' passages (SUPPORTED_ELSEWHERE = D62 pattern)
            elsewhere_evidence, elsewhere_score = _find_best_evidence(
                claim, other_stop_passages, threshold=ELSEWHERE_THRESHOLD
            )
            if elsewhere_score >= ELSEWHERE_THRESHOLD and elsewhere_evidence:
                verdict = SUPPORTED_ELSEWHERE
                evidence = elsewhere_evidence
                score = elsewhere_score
            else:
                # Check for contradiction
                contradiction = _check_contradiction(claim, passages, stop_title)
                if contradiction:
                    verdict = CONTRADICTED
                    evidence = contradiction
                else:
                    verdict = UNSUPPORTED
        else:
            # Check for contradiction
            contradiction = _check_contradiction(claim, passages, stop_title)
            if contradiction:
                verdict = CONTRADICTED
                evidence = contradiction
            else:
                verdict = UNSUPPORTED

        # ─── Enhanced pass: stem+synonym matching for UNSUPPORTED claims ──
        # Only fires when basic matching failed. Can only PROMOTE a verdict
        # from UNSUPPORTED to SUPPORTED_PARAPHRASE — never the reverse.
        if verdict == UNSUPPORTED:
            enh_evidence, enh_score = _find_best_evidence_enhanced(
                claim, passages, threshold=ENHANCED_THRESHOLD
            )
            if enh_score >= ENHANCED_THRESHOLD and enh_evidence:
                verdict = SUPPORTED_PARAPHRASE
                evidence = enh_evidence
                score = enh_score
            elif other_stop_passages:
                enh_evidence, enh_score = _find_best_evidence_enhanced(
                    claim, other_stop_passages, threshold=ENHANCED_THRESHOLD
                )
                if enh_score >= ENHANCED_THRESHOLD and enh_evidence:
                    verdict = SUPPORTED_ELSEWHERE
                    evidence = enh_evidence
                    score = enh_score

        results.append({
            'text': claim['text'],
            'type': claim['type'],
            'sentence': claim.get('sentence', ''),
            'verdict': verdict,
            'evidence': evidence,
            'score': round(score, 3),
        })

    # ─── Per-verdict counts (LOCAL-218) ─────────────────────────────────────
    verdict_counts = {
        'supported': sum(1 for r in results if r['verdict'] == SUPPORTED_PARAPHRASE),
        'supported_elsewhere': sum(1 for r in results if r['verdict'] == SUPPORTED_ELSEWHERE),
        'unsupported': sum(1 for r in results if r['verdict'] == UNSUPPORTED),
        'contradicted': sum(1 for r in results if r['verdict'] == CONTRADICTED),
        'not_checkable': sum(1 for r in results if r['verdict'] == NOT_CHECKABLE),
    }

    # unsupported_count: kept for backward compatibility with existing callers.
    # Includes ONLY UNSUPPORTED, not CONTRADICTED. Rationale:
    #
    # CONTRADICTED is a distinct, graver signal — the corpus actively says
    # otherwise. Callers that use unsupported_count as a "how many claims
    # lack support" number should NOT silently absorb contradictions into
    # that count, because:
    # 1. The gate response to CONTRADICTED should be different (block, not
    #    just penalize). A single contradiction in a paragraph about a
    #    museum's founding date is a factual error, not a vague unsupported
    #    opinion.
    # 2. Existing callers (run_local212_*.py, local205_claims.py) use
    #    unsupported_count to measure "how many claims we couldn't verify".
    #    CONTRADICTED is not "couldn't verify" — it's "verified wrong".
    #    Mixing them hides the severity.
    # 3. Per-verdict counts (verdict_counts dict) are now available. Callers
    #    that need CONTRADICTED visibility should check verdict_counts[
    #    'contradicted'] directly, or iterate claims for verdict ==
    #    CONTRADICTED when they need the evidence.
    #
    # Callers should be updated to check verdict_counts['contradicted'] > 0
    # as a hard-block condition. This is a separate, stronger gate than the
    # unsupported penalty.
    unsupported_count = verdict_counts['unsupported']

    return {
        'claims': results,
        'unsupported_count': unsupported_count,
        'verdict_counts': verdict_counts,
    }
