#!/usr/bin/env python3
"""actionable_failure.py — LOCAL-580 D4: a clean fail the app can ACT on.

When a tour genuinely cannot be built, the job's error must do more than say so.
The mobile app (LOCAL-581) needs a machine-usable structure:

    error_code   — a stable enum the app can branch on
                   (e.g. 'venue_no_verifiable_content')
    message      — one plain-language sentence saying WHY, naming the venue
    suggestion   — a ready-to-fire alternative request derived from the venue's
                   resolved locality, e.g.
                   {"label":   "Walking tour of Winchester, MA",
                    "request": "walking tour of Winchester, MA",
                    "tour_type":"walking"}

The old human-readable string is still returned verbatim in the job's `error`
field so pre-LOCAL-581 app builds keep working unchanged.

This module is pure: evidence dict + request string in, structured dict out. No
network, no imports from the engine.
"""
from __future__ import annotations

import re
from typing import Dict, Optional

__all__ = ['build_actionable_failure', 'derive_locality', 'ERROR_CODES']

# error_type (what the engine records) → error_code (what the app branches on).
# error_code is the stable, documented contract; error_type stays internal.
ERROR_CODES = {
    'thin_evidence': 'venue_no_verifiable_content',
    'all_unverified': 'venue_no_verifiable_content',
    'exhibition_not_found': 'exhibition_not_found',
    'exhibition_closed': 'exhibition_closed',
    'venue_misread': 'venue_misread',
    'address_scatter': 'stops_not_colocated',
    'unclassifiable_request': 'request_unclassifiable',
    'story_gate_failed': 'content_quality_insufficient',
    'generation_failed': 'generation_failed',
}

_US_STATES = frozenset({
    'al', 'ak', 'az', 'ar', 'ca', 'co', 'ct', 'de', 'fl', 'ga', 'hi', 'id',
    'il', 'in', 'ia', 'ks', 'ky', 'la', 'me', 'md', 'ma', 'mi', 'mn', 'ms',
    'mo', 'mt', 'ne', 'nv', 'nh', 'nj', 'nm', 'ny', 'nc', 'nd', 'oh', 'ok',
    'or', 'pa', 'ri', 'sc', 'sd', 'tn', 'tx', 'ut', 'vt', 'va', 'wa', 'wv',
    'wi', 'wy',
})

_VENUE_WORDS_RE = re.compile(
    r'(?i)\b(mus[eé]+e?|museum|gallery|galerie|palais|villa|ch[aâ]teau|library|'
    r'institute|institut|collection|foundation|fondation|center|centre|'
    r'exhibition|exhibit|photography)\b'
)

_TRANSPORT_TAIL_RE = re.compile(
    r'(?i)[,\s]+(?:\d+\s+stops?|museum|walking|biking|driving|tour).*$'
)


def derive_locality(request: str, evidence: Optional[Dict] = None) -> str:
    """Best-effort locality (city[, region]) for the suggestion.

    Preference order:
      1. an explicit 'locality' recorded on the evidence by the engine,
      2. the comma-tail of the request that is NOT the venue segment, keeping a
         trailing US state (e.g. "Winchester, MA"),
      3. ''.
    """
    evidence = evidence or {}
    _ev_loc = (evidence.get('locality') or '').strip()
    if _ev_loc:
        return _ev_loc

    if not request:
        return ''
    parts = [p.strip() for p in request.split(',') if p.strip()]
    if len(parts) < 2:
        return ''

    # Drop a leading venue segment ("Griffin museum of photography").
    body = parts[1:] if _VENUE_WORDS_RE.search(parts[0]) else parts

    # Clean a transport/stop-count suffix off the last segment.
    cleaned = []
    for seg in body:
        seg = _TRANSPORT_TAIL_RE.sub('', seg).strip()
        if seg:
            cleaned.append(seg)
    if not cleaned:
        return ''

    # City + optional trailing state abbreviation → "Winchester, MA".
    city = cleaned[0]
    if len(cleaned) >= 2 and cleaned[1].lower() in _US_STATES:
        return f"{city}, {cleaned[1].upper()}"
    # Non-US tail (e.g. "Nice, France") — keep one trailing qualifier.
    if len(cleaned) >= 2 and len(cleaned[1].split()) <= 2:
        return f"{city}, {cleaned[1]}"
    return city


def _walking_suggestion(locality: str) -> Optional[Dict]:
    if not locality:
        return None
    return {
        'label': f"Walking tour of {locality}",
        'request': f"walking tour of {locality}",
        'tour_type': 'walking',
    }


def build_actionable_failure(evidence: Optional[Dict], request: str,
                             legacy_message: str) -> Dict:
    """Return the structured fields to attach to a clean-fail job.

    Args:
        evidence: the engine's _LAST_CLEAN_FAIL_EVIDENCE (may be {} or None).
        request: the original user request / location string.
        legacy_message: the human-readable string already computed by the
            caller — returned unchanged under 'error' for old app builds.

    Returns a dict with:
        error        : str  (== legacy_message; old builds read this)
        error_code   : str  (stable enum from ERROR_CODES)
        message      : str  (plain-language WHY, == legacy_message by default)
        suggestion   : dict | None  ({label, request, tour_type})
    """
    evidence = evidence or {}
    error_type = evidence.get('error_type', 'generation_failed')
    error_code = ERROR_CODES.get(error_type, 'generation_failed')

    locality = derive_locality(request, evidence)

    # For a venue that simply has no verifiable content, the useful next step is
    # a walking tour of the surrounding locality. Other error kinds keep whatever
    # suggestion the engine supplied (e.g. exhibition_not_found 'suggestions').
    suggestion = None
    if error_code == 'venue_no_verifiable_content':
        suggestion = _walking_suggestion(locality)

    return {
        'error': legacy_message,          # unchanged for pre-LOCAL-581 builds
        'error_code': error_code,
        'message': legacy_message,
        'suggestion': suggestion,
    }
