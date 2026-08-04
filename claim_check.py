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


def _check_contradiction(
    claim: Dict,
    passages: List[str],
) -> Optional[str]:
    """Check if any passage directly contradicts the claim.

    Only for DATE/NUMBER claims where we can check the specific value.
    Returns contradicting evidence or None.
    """
    if claim['type'] not in ('DATE', 'NUMBER'):
        return None

    claim_text = claim['text']
    numbers_in_claim = re.findall(r'\d+', claim_text)
    if not numbers_in_claim:
        return None

    # Get non-numeric context words from the claim
    context_words = [t for t in _tokenize(claim_text) if not t.isdigit()]
    if not context_words:
        return None

    for passage in passages:
        passage_tokens = _tokenize(passage)
        # Check if passage discusses the same topic but with different numbers
        context_overlap = sum(1 for w in context_words if w in passage_tokens)
        if context_overlap >= max(1, len(context_words) * 0.4):
            # Same topic — check if numbers differ
            passage_numbers = re.findall(r'\d+', passage)
            for cn in numbers_in_claim:
                if cn not in passage_numbers and len(cn) >= 3:
                    # The passage discusses the same thing but has different numbers
                    # Find the relevant chunk
                    for cw in context_words:
                        idx = _normalize(passage).find(cw)
                        if idx >= 0:
                            start = max(0, idx - 30)
                            end = min(len(passage), idx + 100)
                            return passage[start:end].strip()

    return None


# ─── Thresholds ──────────────────────────────────────────────────────────────

# Conservative: prefer UNSUPPORTED over false SUPPORTED
PARAPHRASE_THRESHOLD = 0.55  # token overlap needed for SUPPORTED_PARAPHRASE
ELSEWHERE_THRESHOLD = 0.55   # same threshold for SUPPORTED_ELSEWHERE


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
            'unsupported_count': int,
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

    # Filter out claims that are just the stop title or venue name
    stop_norm = _normalize(stop_title)
    venue_norm = _normalize(venue_name)
    filtered_claims = []
    for c in unique_claims:
        c_norm = _normalize(c['text'])
        # Skip if it's just repeating the stop title
        if c_norm in stop_norm or stop_norm in c_norm:
            continue
        # Skip if it's just repeating the venue name
        if c_norm in venue_norm or venue_norm in c_norm:
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
                contradiction = _check_contradiction(claim, passages)
                if contradiction:
                    verdict = CONTRADICTED
                    evidence = contradiction
                else:
                    verdict = UNSUPPORTED
        else:
            # Check for contradiction
            contradiction = _check_contradiction(claim, passages)
            if contradiction:
                verdict = CONTRADICTED
                evidence = contradiction
            else:
                verdict = UNSUPPORTED

        results.append({
            'text': claim['text'],
            'type': claim['type'],
            'verdict': verdict,
            'evidence': evidence,
            'score': round(score, 3),
        })

    unsupported_count = sum(
        1 for r in results if r['verdict'] == UNSUPPORTED
    )

    return {
        'claims': results,
        'unsupported_count': unsupported_count,
    }
