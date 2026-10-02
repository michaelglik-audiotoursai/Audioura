#!/usr/bin/env python3
"""exhibition_resolution.py — Exhibition existence detector for LOCAL-465.

Pure decision function: given signals already computed by the pipeline
(venue resolution, coverage selection, candidate indices), decide whether
the requested exhibition exists. No network calls, no side effects.

The three signals:
1. Venue city contradicts the request (Boston → Houston).
2. Zero coverage — all candidates are EMPTY or VENUE_ONLY.
3. Near-match suggestions from venue_corpus/exhibition checklist titles.

Env:
    EXHIBITION_STRICT=0  → disables this check entirely, restoring pre-fix behaviour.
    Default: EXHIBITION_STRICT=1 (on).
"""
import os
import re
from typing import Dict, List, Optional, Set

from text_fold import fold

__all__ = ['resolve_request', 'ExhibitionNotFound']


# ─── Typed exception for the caller ──────────────────────────────────────────

class ExhibitionNotFound(Exception):
    """Raised when the exhibition resolution gate rejects a request.

    Attributes:
        verdict: 'NOT_FOUND' or 'DID_YOU_MEAN'
        reason: machine-readable reason string for the log
        user_message: what the app should display
        suggestions: 0-3 near-match titles, best first
    """
    def __init__(self, verdict: str, reason: str, user_message: str,
                 suggestions: Optional[List[str]] = None):
        self.verdict = verdict
        self.reason = reason
        self.user_message = user_message
        self.suggestions = suggestions or []
        super().__init__(user_message)


# ─── Configuration ────────────────────────────────────────────────────────────

def is_strict_mode() -> bool:
    """Return True when EXHIBITION_STRICT is on (the default)."""
    return os.environ.get('EXHIBITION_STRICT', '1').strip() != '0'


# ─── City extraction helpers ─────────────────────────────────────────────────

# US state abbreviations and common suffixes that follow a city name
_US_STATES = frozenset({
    'al', 'ak', 'az', 'ar', 'ca', 'co', 'ct', 'de', 'fl', 'ga',
    'hi', 'id', 'il', 'in', 'ia', 'ks', 'ky', 'la', 'me', 'md',
    'ma', 'mi', 'mn', 'ms', 'mo', 'mt', 'ne', 'nv', 'nh', 'nj',
    'nm', 'ny', 'nc', 'nd', 'oh', 'ok', 'or', 'pa', 'ri', 'sc',
    'sd', 'tn', 'tx', 'ut', 'vt', 'va', 'wa', 'wv', 'wi', 'wy',
    'usa', 'us',
})

_COUNTRY_WORDS = frozenset({
    'france', 'italy', 'usa', 'us', 'uk', 'spain', 'germany',
    'netherlands', 'belgium', 'switzerland', 'japan', 'china',
    'australia', 'canada', 'brazil', 'india', 'russia', 'mexico',
    'united states', 'united kingdom',
})


def _extract_city_from_request(request: str) -> str:
    """Extract the city name from a user request string.

    Handles patterns like:
    - "... in MFA Boston, MA"          → "Boston"
    - "... at Museum of Fine Arts, Boston, MA" → "Boston"
    - "... in Nice, France"            → "Nice"
    - "... exhibition at MFA, Boston"  → "Boston"
    """
    # Strategy 1: Look for "in <City>" or "at <Venue>, <City>" patterns
    # Try to find a city name embedded via "in" preposition (before any comma)
    m = re.search(r'\bin\s+(?:\w+\s+)*?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*[,.]', request)
    if m:
        candidate = m.group(1)
        # Skip if it's a known venue-related word
        if candidate.lower() not in ('museum', 'gallery', 'mfa', 'the', 'art', 'exhibition'):
            return candidate

    # Strategy 2: Split on commas, walk segments from end, skip states/countries
    parts = [p.strip() for p in request.split(',')]
    if len(parts) >= 2:
        # Walk segments from the end; skip state abbreviations and countries
        for seg in reversed(parts[1:]):
            seg_stripped = seg.strip()
            seg_lower = seg_stripped.lower()
            if seg_lower in _US_STATES or seg_lower in _COUNTRY_WORDS:
                continue
            # Must look like a city: 1-3 words, non-empty
            words = seg_stripped.split()
            if 1 <= len(words) <= 3 and seg_stripped:
                return seg_stripped
        # If all trailing segments are states/countries, look for city in the
        # first segment using "in <City>" pattern (no comma version)
        first = parts[0]
        m2 = re.search(r'\bin\s+(?:\w+\s+)*?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)$', first)
        if m2:
            candidate = m2.group(1)
            if candidate.lower() not in ('museum', 'gallery', 'mfa', 'the', 'art', 'exhibition'):
                return candidate
        # Try: last word(s) of first segment that look like a city
        # e.g. "exhibition blue green and silva in MFA Boston" → "Boston"
        m3 = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*$', first)
        if m3:
            candidate = m3.group(1)
            # Must not be a common noun or venue word
            if candidate.lower() not in ('museum', 'gallery', 'exhibition', 'exhibit',
                                         'show', 'art', 'arts', 'fine', 'modern',
                                         'contemporary', 'national', 'the'):
                return candidate
        return ''

    # Strategy 3: "in <City>" without commas
    m4 = re.search(r'\bin\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', request)
    if m4:
        candidate = m4.group(1)
        if candidate.lower() not in ('museum', 'gallery', 'mfa', 'the', 'art', 'exhibition'):
            return candidate

    return ''


def _extract_city_from_resolved(resolved_venue: Dict) -> str:
    """Extract the city from the resolved venue entity.

    The resolved_venue dict should have at minimum:
        name: str — the venue's resolved name
        official_url: str — the venue's official URL
        qid: str — Wikidata QID

    Optionally:
        city: str — if the venue resolver already identified it
        url_domain: str — for heuristic extraction
    """
    # Direct city field if available
    if resolved_venue.get('city'):
        return resolved_venue['city']

    # Heuristic: extract from the official URL domain
    url = resolved_venue.get('official_url', '')
    if url:
        # "mfah.org" → Houston, "mfa.org" → Boston
        # This is fragile, but for the Houston/Boston case the URL was the signal
        # that the log already showed: "URL: http://www.mfah.org/"
        # We'll rely primarily on the city-match validation already done by
        # venue_resolver — if it passed a wrong result, we compare the name.
        pass

    # Heuristic: look for city names in the resolved venue name
    name = resolved_venue.get('name', '')
    # "Museum of Fine Arts, Houston" → "Houston"
    if ',' in name:
        name_parts = [p.strip() for p in name.split(',')]
        for p in name_parts[1:]:
            if p and p[0].isupper() and p.lower() not in _COUNTRY_WORDS:
                return p

    return ''


# ─── Near-match search ────────────────────────────────────────────────────────

def _token_set_similarity(a: str, b: str) -> float:
    """Token-set similarity after accent-folding.

    Fold both, strip punctuation, tokenize. For each token in `a`, find the
    best fuzzy match in `b` (edit distance ≤ 1 for short tokens, ≤ 2 for longer).
    Score = matched_count / union_size.
    """
    a_folded = fold(a)
    b_folded = fold(b)
    if not a_folded or not b_folded:
        return 0.0

    # Strip punctuation (colons, commas, etc.) before tokenizing
    a_clean = re.sub(r'[^\w\s]', ' ', a_folded)
    b_clean = re.sub(r'[^\w\s]', ' ', b_folded)

    a_tokens = [t for t in a_clean.split() if t not in _STOP_TOKENS and len(t) > 1]
    b_tokens = [t for t in b_clean.split() if t not in _STOP_TOKENS and len(t) > 1]

    if not a_tokens or not b_tokens:
        return 0.0

    # Count how many a_tokens have a fuzzy match in b_tokens
    b_set = set(b_tokens)
    matched = 0
    for at in a_tokens:
        if at in b_set:
            matched += 1
        else:
            # Fuzzy: allow edit distance ≤ 1 for tokens ≤ 5 chars, ≤ 2 for longer
            max_dist = 1 if len(at) <= 5 else 2
            for bt in b_tokens:
                if abs(len(at) - len(bt)) <= max_dist and _levenshtein(at, bt) <= max_dist:
                    matched += 1
                    break

    # Jaccard-style: matched / union count
    union_size = len(set(a_tokens) | b_set)
    return matched / union_size if union_size > 0 else 0.0


def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


# Stop words for similarity matching — small common words that don't discriminate
_STOP_TOKENS = frozenset({
    'the', 'a', 'an', 'of', 'in', 'at', 'to', 'and', 'or', 'for',
    'de', 'du', 'des', 'le', 'la', 'les', 'et', 'en',
    'exhibition', 'exhibit', 'show', 'display',
})

# Minimum similarity threshold for a suggestion to be worth showing.
# Below this, a suggestion is more confusing than helpful.
_SUGGESTION_THRESHOLD = 0.30


def _find_near_matches(request_name: str, known_titles: List[str],
                       max_results: int = 3) -> List[str]:
    """Find exhibition titles similar to the request, best first.

    Args:
        request_name: what the user typed (e.g. "blue green and silva")
        known_titles: exhibition titles from venue_corpus/checklist
        max_results: cap on suggestions (default 3)

    Returns:
        List of matching titles above threshold, sorted by similarity descending.
    """
    if not known_titles or not request_name:
        return []

    scored = []
    for title in known_titles:
        sim = _token_set_similarity(request_name, title)
        if sim >= _SUGGESTION_THRESHOLD:
            scored.append((sim, title))

    # Sort by similarity descending
    scored.sort(key=lambda x: -x[0])
    return [title for _, title in scored[:max_results]]


# ─── Main decision function ──────────────────────────────────────────────────

def resolve_request(request: str, resolved_venue: Dict, coverage: Dict,
                    candidates: List[Dict]) -> Dict:
    """Decide whether the requested exhibition exists.

    Called after venue resolution and after LOCAL-212 coverage selection.

    Args:
        request: the original user request string
            e.g. "exhibition blue green and silva in MFA Boston, MA"
        resolved_venue: dict with venue resolution results:
            {
                'name': str,          # resolved venue name
                'qid': str,           # Wikidata QID
                'official_url': str,  # venue URL
                'city': str,          # resolved venue's city (may be empty)
            }
        coverage: dict with LOCAL-212 coverage selection results:
            {
                'covered_count': int,      # number of COVERED candidates
                'total_selected': int,     # total selected for the tour
                'verdicts': dict,          # {stop_name: verdict_string}
                'fallback_reasons': list,  # e.g. ['1×VENUE_ONLY', '2×EMPTY']
            }
        candidates: list of candidate dicts, each with:
            {
                'title': str,   # known exhibition title
            }
            These come from venue_corpus canonical_titles and/or exhibition
            checklist results for the resolved venue.

    Returns:
        {
            'verdict': 'FOUND' | 'NOT_FOUND' | 'DID_YOU_MEAN',
            'reason': str,          # for the log, specific
            'user_message': str,    # what the app shows
            'suggestions': [str],   # 0-3 near-matches, best first
        }
    """
    # ─── Check 1: Venue city contradicts the request ──────────────────────
    request_city = _extract_city_from_request(request)
    resolved_city = _extract_city_from_resolved(resolved_venue)

    if request_city and resolved_city:
        req_city_folded = fold(request_city)
        res_city_folded = fold(resolved_city)
        # Only reject if both are non-empty AND clearly different
        # Allow partial match (e.g. "Boston" in "Boston, Massachusetts")
        if (req_city_folded and res_city_folded and
                req_city_folded not in res_city_folded and
                res_city_folded not in req_city_folded):
            venue_name = resolved_venue.get('name', 'the resolved venue')
            return {
                'verdict': 'NOT_FOUND',
                'reason': (f'venue city mismatch: request says "{request_city}" '
                           f'but resolved venue is in "{resolved_city}" '
                           f'({venue_name})'),
                'user_message': (
                    f"We could not find an exhibition matching your request at "
                    f"a venue in {request_city}. The closest match was "
                    f"{venue_name} in {resolved_city}, which is a different "
                    f"institution. It may have closed, not opened yet, or the "
                    f"name may be slightly different."
                ),
                'suggestions': [],
            }

    # ─── Check 2: Zero coverage ──────────────────────────────────────────
    covered_count = coverage.get('covered_count', 0)
    total_selected = coverage.get('total_selected', 0)
    verdicts = coverage.get('verdicts', {})

    if total_selected > 0 and covered_count == 0:
        # Every candidate is EMPTY or VENUE_ONLY — no real content exists
        all_empty_or_venue = all(
            v in ('EMPTY', 'VENUE_ONLY')
            for v in verdicts.values()
        )
        if all_empty_or_venue:
            # Look for near-matches before returning NOT_FOUND
            known_titles = [c.get('title', '') for c in candidates if c.get('title')]
            exhibition_term = _extract_exhibition_term(request)
            suggestions = _find_near_matches(exhibition_term, known_titles)

            if suggestions:
                venue_display = resolved_venue.get('name', 'this venue')
                return {
                    'verdict': 'DID_YOU_MEAN',
                    'reason': (f'zero coverage (0 COVERED, all EMPTY/VENUE_ONLY) '
                               f'but near-match found: {suggestions[0]}'),
                    'user_message': (
                        f"We could not find '{exhibition_term}' at "
                        f"{venue_display}. Did you mean "
                        f"'{suggestions[0]}'? Ask again with that name "
                        f"and we will build the tour."
                    ),
                    'suggestions': suggestions,
                }
            else:
                venue_display = resolved_venue.get('name', 'this venue')
                return {
                    'verdict': 'NOT_FOUND',
                    'reason': (f'zero coverage: 0 COVERED, '
                               f'{len(verdicts)} candidates all '
                               f'EMPTY/VENUE_ONLY — no content exists'),
                    'user_message': (
                        f"We could not find an exhibition matching "
                        f"'{_extract_exhibition_term(request)}' at "
                        f"{venue_display}. It may have closed, not opened "
                        f"yet, or the name may be slightly different."
                    ),
                    'suggestions': [],
                }

    # ─── Check 3: DID_YOU_MEAN from near-matches even when coverage > 0 ──
    # If we have some coverage but also have candidates to compare against,
    # and the request term is very different from what we actually resolved,
    # this could still be a mismatch. However, if coverage is non-zero,
    # we trust the system found something real.

    # ─── Default: FOUND ──────────────────────────────────────────────────
    return {
        'verdict': 'FOUND',
        'reason': 'exhibition resolution passed',
        'user_message': '',
        'suggestions': [],
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _extract_exhibition_term(request: str) -> str:
    """Extract the exhibition name portion from a request string.

    Strips venue/location qualifiers:
    - "exhibition blue green and silva in MFA Boston, MA"
      → "blue green and silva"
    - "Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA"
      → "Picasso, Miro, Dali: Unbound"
    """
    # Remove common prefixes
    text = re.sub(r'^(?:exhibition|exhibit|the)\s+', '', request, flags=re.IGNORECASE)

    # Remove "in <Venue>, <City>, <State>" or "at <Venue>, <City>, <State>"
    text = re.sub(r'\s+(?:in|at)\s+[A-Z].*$', '', text)

    # Remove trailing "exhibition" / "exhibit"
    text = re.sub(r'\s+(?:exhibition|exhibit)s?\s*$', '', text, flags=re.IGNORECASE)

    return text.strip() or request.strip()
