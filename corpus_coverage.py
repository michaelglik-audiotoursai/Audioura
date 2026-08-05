"""corpus_coverage.py — stop-corpus coverage assessment (LOCAL-198).

Canonical location is the REPO ROOT, not tests/. `generate_tour_text.py`
calls assess_stop_coverage() during generation, and `tests/` is NOT copied
into the tour-generator image — an import from there fails inside Docker and
the gate silently never runs. LOCAL-192 shipped exactly that bug two rounds
ago; this file is why it is not shipping again.

Verify after any rebuild:
    docker exec audioura-tour-generator-1 python -c "import corpus_coverage"
"""

import re
import unicodedata
from typing import Dict, List, Optional, Tuple

STOPWORDS = {
    'the', 'and', 'for', 'with', 'from', 'des', 'les', 'une', 'dans',
    'sur', 'par', 'aux', 'son', 'ses', 'que', 'qui', 'est', 'sont',
    'art', 'arts', 'musee', 'museum', 'nice', 'france', 'tour', 'walking',
    'biking', 'moderne', 'contemporain', 'national', 'marc', 'villa',
    'palais', 'chateau', 'old', 'town', 'place', 'rue', 'port', 'parc',
    'common', 'boston', 'area', 'french', 'riviera',
}


def strip_accents(text: str) -> str:
    """Remove accents from text for matching (é→e, ô→o, etc.)."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def extract_content_words(title: str, venue_name: str) -> List[str]:
    """Extract meaningful content words from a stop title.

    Rules:
    - Split on non-alpha chars
    - Lowercase, strip accents
    - Remove words < 4 chars (avoids "Long"/"Tir"/"Pop" false matches)
    - Remove stopwords
    - Remove words that appear in the venue name (they're venue-level, not stop-level)
    """
    venue_words = set(
        strip_accents(w).lower()
        for w in re.findall(r'[A-Za-zÀ-ÿ]+', venue_name)
        if len(w) >= 4
    )

    words = re.findall(r'[A-Za-zÀ-ÿ]+', title)
    content_words = []
    for w in words:
        w_norm = strip_accents(w).lower()
        if len(w_norm) < 4:
            continue
        if w_norm in STOPWORDS:
            continue
        if w_norm in venue_words:
            continue
        content_words.append(w_norm)

    return content_words


def word_appears_in_text(word: str, text: str) -> bool:
    """Check if a word appears as a whole word in text (case/accent insensitive).

    Uses word-boundary matching to avoid "Long" matching "along" (LOCAL-178 trap).
    """
    text_norm = strip_accents(text).lower()
    # Use word boundaries. The word itself is already lowercased and accent-stripped.
    pattern = r'\b' + re.escape(word) + r'\b'
    return bool(re.search(pattern, text_norm))


def assess_stop_coverage(
    stop_title: str,
    venue_name: str,
    passages: List[str],
    passage_roles: Optional[List[Dict]] = None,
) -> Dict:
    """Assess whether a stop's corpus actually covers its subject.

    Args:
        stop_title: The stop/POI title.
        venue_name: The venue name.
        passages: List of passage text strings.
        passage_roles: Optional list of role dicts (parallel to passages).
            Each dict has 'role': 'about_subject'|'about_creator'|'about_venue'|None.
            When provided, enables role-aware verdicts (LOCAL-203).

    Returns:
        {
            'passage_count': int,
            'content_words': list of extracted title words,
            'subject_in_passages': bool,
            'subject_match_words': list of which content words matched,
            'venue_only_count': int (passages mentioning venue but not stop),
            'verdict': 'COVERED' | 'CREATOR_ONLY' | 'VENUE_ONLY' | 'EMPTY',
            'has_subject_role': bool (True if any passage is about_subject),
            'has_creator_role': bool (True if any passage is about_creator),
            'has_venue_role': bool (True if any passage is about_venue),
        }
    """
    if not passages:
        content_words = extract_content_words(stop_title, venue_name)
        return {
            'passage_count': 0,
            'content_words': content_words,
            'subject_in_passages': False,
            'subject_match_words': [],
            'venue_only_count': 0,
            'verdict': 'EMPTY',
            'has_subject_role': False,
            'has_creator_role': False,
            'has_venue_role': False,
        }

    content_words = extract_content_words(stop_title, venue_name)

    # Check which content words appear anywhere in the passages
    all_text = '\n'.join(passages)
    matched_words = [w for w in content_words if word_appears_in_text(w, all_text)]

    # A stop is COVERED if at least one meaningful content word from its title
    # appears in the passages. This is the minimum bar — it means the corpus
    # at least *mentions* the stop's subject.
    subject_in_passages = len(matched_words) > 0

    # Count venue-only passages (mention venue name components but not stop subject)
    venue_words_for_check = set(
        strip_accents(w).lower()
        for w in re.findall(r'[A-Za-zÀ-ÿ]+', venue_name)
        if len(w) >= 4 and strip_accents(w).lower() not in STOPWORDS
    )

    venue_only_count = 0
    for p in passages:
        p_has_venue = any(word_appears_in_text(vw, p) for vw in venue_words_for_check)
        p_has_stop = any(word_appears_in_text(sw, p) for sw in content_words) if content_words else False
        if p_has_venue and not p_has_stop:
            venue_only_count += 1

    # --- Role-aware verdict (LOCAL-203) ---
    has_subject_role = False
    has_creator_role = False
    has_venue_role = False

    if passage_roles:
        for r in passage_roles:
            if isinstance(r, dict):
                role = r.get('role')
            else:
                role = r
            if role == 'about_subject':
                has_subject_role = True
            elif role == 'about_creator':
                has_creator_role = True
            elif role == 'about_venue':
                has_venue_role = True

    # Determine verdict
    if passage_roles:
        # Role-aware path (LOCAL-203): verdict is based on what roles are present
        if has_subject_role:
            verdict = 'COVERED'
        elif has_creator_role:
            verdict = 'CREATOR_ONLY'
        elif has_venue_role:
            verdict = 'VENUE_ONLY'
        else:
            # Has passages but none with a valid role — treat as VENUE_ONLY
            verdict = 'VENUE_ONLY' if passages else 'EMPTY'
    else:
        # Legacy path (no roles available): original word-match logic
        if subject_in_passages:
            verdict = 'COVERED'
        elif len(passages) > 0:
            verdict = 'VENUE_ONLY'
        else:
            verdict = 'EMPTY'

        # Special case: if no content words could be extracted (title is all short words
        # or all venue words), we can't determine coverage → mark as VENUE_ONLY
        # because we can't confirm the passages are about this specific stop.
        if not content_words and passages:
            verdict = 'VENUE_ONLY'

    return {
        'passage_count': len(passages),
        'content_words': content_words,
        'subject_in_passages': subject_in_passages,
        'subject_match_words': matched_words,
        'venue_only_count': venue_only_count,
        'verdict': verdict,
        'has_subject_role': has_subject_role,
        'has_creator_role': has_creator_role,
        'has_venue_role': has_venue_role,
    }


def _extract_passage_texts(passages_json) -> List[str]:
    """Extract plain text from passages_json (handles both str and dict formats)."""
    if isinstance(passages_json, list):
        passages = []
        for p in passages_json:
            if isinstance(p, str):
                passages.append(p)
            elif isinstance(p, dict):
                passages.append(p.get('text', ''))
            else:
                passages.append(str(p))
        return [p for p in passages if p]
    elif isinstance(passages_json, str):
        try:
            parsed = json.loads(passages_json)
            return _extract_passage_texts(parsed)
        except (json.JSONDecodeError, TypeError):
            return []
    return []

