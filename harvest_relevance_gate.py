"""harvest_relevance_gate.py — LOCAL-341: Passage must be ABOUT the stop before storage.

Gate logic:
    A passage is considered relevant to a stop if it shares at least one
    distinctive content word (≥4 chars, not a stop-word) with the stop title,
    matched on word boundaries after accent-folding and apostrophe normalisation.

    This catches the Stade de France case trivially ("stadium", "football",
    "France", "Spain" share zero distinctive words with "Armure", "Ando",
    "Naoyuki"). It also catches "Archives départementales du Gard" vs "Kannon
    à mille bras" (no overlap).

Design constraints (from task):
    - No LLM calls. Structural/lexical only.
    - Absence of signal ≠ proof of irrelevance: failures are LOGGED and FLAGGED,
      never silently discarded.
    - The gate returns a verdict and a reason; the caller decides what to do.

Fold rules (D253):
    - Accents stripped via NFKD decomposition.
    - U+2019 (') folded to U+0027 (') before all matching.
    - Case-insensitive.
"""

import re
import unicodedata
from typing import List, Tuple


# ─── Stop words: too common to be distinctive ────────────────────────────────

_STOP_WORDS = frozenset({
    # English
    'the', 'and', 'for', 'with', 'from', 'that', 'this', 'are', 'was',
    'were', 'been', 'have', 'has', 'had', 'will', 'would', 'could',
    'should', 'which', 'their', 'them', 'they', 'what', 'when', 'where',
    'also', 'more', 'most', 'very', 'much', 'such', 'than', 'then',
    'some', 'only', 'just', 'over', 'into', 'about', 'after', 'before',
    # French
    'des', 'les', 'une', 'dans', 'sur', 'par', 'aux', 'son', 'ses',
    'qui', 'que', 'est', 'sont', 'avec', 'pour', 'cette', 'tout',
    'mais', 'elle', 'nous', 'vous', 'leur', 'plus', 'bien', 'faire',
    # Domain-generic (venue/museum)
    'musee', 'museum', 'collection', 'france', 'nice', 'tour', 'walking',
    'stop', 'area',
})


# ─── Text normalisation ─────────────────────────────────────────────────────

def _fold_apostrophes(text: str) -> str:
    """Fold typographic apostrophes (U+2019, U+2018) to ASCII apostrophe."""
    return text.replace('\u2019', "'").replace('\u2018', "'")


def _strip_accents(text: str) -> str:
    """Remove accents via NFKD decomposition."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _normalize(text: str) -> str:
    """Normalise for comparison: fold apostrophes, strip accents, lowercase, collapse punctuation."""
    t = _fold_apostrophes(text)
    t = _strip_accents(t)
    t = t.lower()
    # Replace non-alphanumeric (except spaces) with space
    t = re.sub(r"[^\w\s]", ' ', t)
    return ' '.join(t.split())


def _extract_content_words(text: str) -> List[str]:
    """Extract distinctive content words (≥4 chars, not stop-words)."""
    words = _normalize(text).split()
    return [w for w in words if len(w) >= 4 and w not in _STOP_WORDS]


# ─── Core gate ───────────────────────────────────────────────────────────────

def check_passage_relevance(
    passage_text: str,
    stop_title: str,
) -> Tuple[bool, str]:
    """Check whether a passage is relevant to a stop title.

    Returns:
        (is_relevant: bool, reason: str)

    The reason is always populated:
        - On pass: which words matched.
        - On fail: what was checked and found absent.
    """
    if not passage_text or not stop_title:
        return False, "empty input"

    # Extract distinctive words from stop title
    title_words = _extract_content_words(stop_title)
    if not title_words:
        # Title has no distinctive words (e.g. too short) — cannot gate, pass by default
        return True, "no distinctive words in title; gate not applicable"

    # Normalise passage text
    passage_norm = _normalize(passage_text)

    # Check: does the full normalised title appear as substring?
    title_norm = _normalize(stop_title)
    if len(title_norm) > 6 and title_norm in passage_norm:
        return True, f"full title substring match: '{title_norm}'"

    # Check: word-boundary match for each title content word
    matched_words = []
    for w in title_words:
        # Use \b word boundary to prevent "daim" matching inside "daimyo"
        if re.search(r'\b' + re.escape(w) + r'\b', passage_norm):
            matched_words.append(w)

    if matched_words:
        return True, f"title word(s) found in passage: {matched_words}"

    return False, (
        f"no title words found in passage; "
        f"searched for {title_words} in {len(passage_text)}-char passage"
    )


# ─── Batch audit helper ──────────────────────────────────────────────────────

def audit_stop_corpus_relevance(db_conn) -> dict:
    """Run the relevance gate over all stop_corpus rows with passages.

    Returns:
        {
            'total_rows': int,
            'total_passages': int,
            'passages_pass': int,
            'passages_fail': int,
            'failures': [
                {
                    'stop_title': str,
                    'venue_name': str,
                    'passage_text': str (first 120 chars),
                    'url': str,
                    'reason': str,
                },
            ],
        }
    """
    import json

    cur = db_conn.cursor()
    cur.execute("""
        SELECT stop_title, venue_name, passages_json
        FROM stop_corpus
        WHERE passages_json IS NOT NULL
          AND jsonb_typeof(passages_json) = 'array'
          AND jsonb_array_length(passages_json) > 0
    """)
    rows = cur.fetchall()
    cur.close()

    total_passages = 0
    passes = 0
    fails = 0
    failures = []

    for stop_title, venue_name, passages_json in rows:
        passages = passages_json if isinstance(passages_json, list) else json.loads(passages_json)
        for p in passages:
            if isinstance(p, dict):
                text = p.get('text', '')
                url = p.get('url', '')
            elif isinstance(p, str):
                text = p
                url = ''
            else:
                continue

            if not text:
                continue

            total_passages += 1
            is_relevant, reason = check_passage_relevance(text, stop_title)

            if is_relevant:
                passes += 1
            else:
                fails += 1
                failures.append({
                    'stop_title': stop_title,
                    'venue_name': venue_name,
                    'passage_text': text[:120],
                    'url': url,
                    'reason': reason,
                })

    return {
        'total_rows': len(rows),
        'total_passages': total_passages,
        'passages_pass': passes,
        'passages_fail': fails,
        'failures': failures,
    }
