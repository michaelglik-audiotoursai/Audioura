"""
prolog_structure_validator.py — LOCAL-260: Validate the four-part prolog structure.

Michael specified that every tour prolog must follow this structure, in order:
  1. Tour name + transportation mode
  2. Directions and physicality expectation (route substance)
  3. Purpose — intrigue, story, why people take the tour (sourced facts)
  4. Forward connection to stops (naming actual stop content)

This is a STRUCTURAL COMPLETENESS CHECK. It does NOT delete or rewrite.
It reports violations. It is deterministic and free (no LLM calls).

Wired at post-assembly (after LOCAL-244 PHASE 5.9 prolog gating).
"""

import re
from typing import List, Dict, Optional


# ─── Transport mode vocabulary ────────────────────────────────────────────────
# Must match generate_tour_text.py _TRANSPORT_MODE_KEYWORDS modes
_TRANSPORT_MODE_TERMS = {
    'on_foot': ['walk', 'walking', 'hike', 'hiking', 'stroll', 'foot', 'on foot', 'pedestrian'],
    'bike': ['bike', 'biking', 'cycling', 'cycle', 'bicycle', 'pedal', 'cyclist'],
    'vehicle': ['drive', 'driving', 'car', 'jeep', 'motorcycle', 'scooter', 'auto', 'road trip'],
    'animal': ['camel', 'horse', 'horseback', 'dogsled', 'mushing'],
    'country_scale': ['road trip', 'cross-country', 'safari'],
    'boat': ['boat', 'kayak', 'canoe', 'sailing', 'sail'],
    'segway': ['segway'],
}

# Route substance indicators for Part 2
_ROUTE_ENDPOINTS_RE = re.compile(
    r'\b(?:from|to|between|starting|ending|begins?|ends?|departs?|arrives?)\b.*\b(?:from|to|between|at|in)\b',
    re.IGNORECASE
)
_DISTANCE_RE = re.compile(r'\b\d+[\s-]?(?:km|kilometers?|kilometres?|miles?|meters?|metres?|mi)\b', re.IGNORECASE)
_TERRAIN_RE = re.compile(
    r'\b(?:flat|hilly|steep|elevated|coastal|mountain|uphill|downhill|terrain|slope|cliff|'
    r'paved|unpaved|gravel|cobblestone|path|trail|route|road|track|waterfront|riverside|'
    r'hillside|plateau|valley|ridge)\b', re.IGNORECASE
)
_DURATION_RE = re.compile(r'\b\d+[\s-]?(?:hours?|minutes?|mins?|hrs?|days?)\b', re.IGNORECASE)
_NAMED_PLACE_RE = re.compile(r'[A-Z][a-zà-ú]+(?:[\s-][A-Z][a-zà-ú]+)*')

# Sourced fact indicators for Part 3
_YEAR_RE = re.compile(r'\b(?:1[0-9]{3}|20[0-2][0-9])\b')
_NAMED_PERSON_ACTION_RE = re.compile(
    r'[A-Z][a-zà-ú]+(?:\s+[A-Z][a-zà-ú]+)*\s+(?:who|that)?\s*'
    r'(?:painted|wrote|built|founded|created|composed|designed|established|'
    r'discovered|invented|published|commissioned|opened|constructed|'
    r'sculpted|directed|performed|collaborated|transformed|donated|'
    r'experimented|inaugurated|captured|documented|filmed|'
    r'lived|stayed|visited|arrived|settled|worked|died|born)\b',
    re.IGNORECASE
)
_DOCUMENTED_EVENT_RE = re.compile(
    r'\b(?:battle|war|treaty|revolution|massacre|siege|coronation|'
    r'exhibition|premiere|inauguration|founding|construction|'
    r'completion|discovery|expedition|fire|flood|earthquake|'
    r'assassination|coup|invasion|liberation)\b',
    re.IGNORECASE
)

# Vague language that does NOT count as substance
_VAGUE_FLUFF_RE = re.compile(
    r'\b(?:layer of (?:history|culture)|rich (?:history|heritage|culture|tapestry)|'
    r'where .* (?:meet|meets|dance|dances|converge|converges)|'
    r'a (?:journey|tapestry|mosaic|symphony|blend|fusion|celebration) (?:of|through)|'
    r'stories? (?:await|unfold)|secrets? (?:await|reveal)|'
    r'past and present|history and culture|art and culture|'
    r'hidden (?:gems?|treasures?|secrets?)|timeless (?:beauty|charm|elegance)|'
    r'unique blend|fascinating (?:history|blend|tapestry))\b',
    re.IGNORECASE
)

# Part 4: vague forward-reference patterns that must FAIL
# These are forward references that promise but don't deliver specific content.
# "We will explore X, Y, Z" with specific names is GOOD (passes).
# "More stories await" with no specifics is BAD (fails).
_VAGUE_FORWARD_RE = re.compile(
    r'\b(?:more (?:stories?|details?|secrets?) await|'
    r'each stop (?:reveals?|offers?|holds?|brings?)|'
    r'(?:stories?|secrets?|mysteries?|wonders?) (?:await|awaits?) (?:you|us)|'
    r'in the (?:stops?|chapters?) (?:of|that follow|ahead|to come))\b',
    re.IGNORECASE
)

# Forward-looking language (can be specific or vague depending on what follows)
_FORWARD_LOOKING_RE = re.compile(
    r'\b(?:we will (?:explore|discover|visit|see|hear|learn)|'
    r'you will (?:explore|discover|visit|see|hear|learn)|'
    r'(?:await|awaits?) (?:you|us) (?:in|at|on) the stops)\b',
    re.IGNORECASE
)


def _split_into_sentences(text: str) -> List[str]:
    """Split text into sentences, handling abbreviations."""
    # Simple sentence splitter: split on .!? followed by space+uppercase or end
    sents = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text.strip())
    return [s.strip() for s in sents if s.strip()]


def _sentence_mentions_transport(sentence: str, transport_mode: str) -> bool:
    """Check if a sentence substantively mentions the transport mode.
    
    Keyword presence alone is NOT sufficient — the sentence must convey
    that this tour uses that mode of transport (not just drop the word).
    """
    s_lower = sentence.lower()
    terms = _TRANSPORT_MODE_TERMS.get(transport_mode, _TRANSPORT_MODE_TERMS.get('on_foot', []))
    
    # Must contain at least one term
    has_term = any(t in s_lower for t in terms)
    if not has_term:
        return False
    
    # Must also have a tour/journey/route context — the sentence is ABOUT traveling
    tour_context = re.search(
        r'\b(?:tour|journey|route|trip|ride|trek|excursion|'
        r'adventure|trail|path|you are about to|embark|traveling|'
        r'travelling|travel|traversing|explore by|explore on|'
        r'cycling (?:tour|route|trip|journey)|biking (?:tour|route|trip)|'
        r'walking (?:tour|route|trip)|this is a)\b',
        s_lower
    )
    return tour_context is not None


def _sentence_has_route_substance(sentence: str) -> List[str]:
    """Check what route-substance indicators a sentence carries.
    Returns list of matched indicators: 'endpoints', 'distance', 'terrain', 'duration'.
    """
    indicators = []
    
    # Endpoints: mentions of from/to with named places
    places = _NAMED_PLACE_RE.findall(sentence)
    # At least 2 distinct named places with directional language
    if len(set(places)) >= 2 and re.search(r'\b(?:from|to|between|along|through)\b', sentence, re.IGNORECASE):
        indicators.append('endpoints')
    
    if _DISTANCE_RE.search(sentence):
        indicators.append('distance')
    
    if _TERRAIN_RE.search(sentence):
        indicators.append('terrain')
    
    if _DURATION_RE.search(sentence):
        indicators.append('duration')
    
    return indicators


def _sentence_has_sourced_fact(sentence: str) -> bool:
    """Check if a sentence carries at least one sourced fact:
    - A date (year)
    - A named person with what they did
    - A documented event
    
    Must not be entirely vague/fluff language.
    """
    # If sentence is pure fluff, reject
    if _VAGUE_FLUFF_RE.search(sentence) and not _YEAR_RE.search(sentence):
        # It has fluff language AND no year — not a fact
        if not _NAMED_PERSON_ACTION_RE.search(sentence) and not _DOCUMENTED_EVENT_RE.search(sentence):
            return False
    
    has_year = _YEAR_RE.search(sentence)
    has_person_action = _NAMED_PERSON_ACTION_RE.search(sentence)
    has_event = _DOCUMENTED_EVENT_RE.search(sentence)
    
    return bool(has_year or has_person_action or has_event)


def _sentence_names_stop_content(sentence: str, stop_names: List[str]) -> List[str]:
    """Check if a sentence names actual content from the tour's stops as a
    FORWARD REFERENCE (Part 4 function: connecting to what comes next).
    
    A forward reference must:
    1. Name a stop or its content, AND
    2. Be in a forward-looking context (will explore, upcoming, etc.)
    
    Just mentioning a place name (e.g. "from Nice to Antibes") is NOT a Part 4
    forward reference — it's Part 2 route info.
    
    Returns list of stop names referenced.
    """
    # Must have forward-looking language
    forward_context = re.search(
        r'\b(?:will (?:explore|visit|discover|see|find|encounter|learn|hear)|'
        r'upcoming|ahead|await|next|continues? (?:to|with|at)|'
        r'explore|discover|uncover|delve into|'
        r'stops? (?:include|feature|offer|reveal|cover|bring))\b',
        sentence, re.IGNORECASE
    )
    if not forward_context:
        return []
    
    referenced = []
    s_lower = sentence.lower()
    for name in stop_names:
        if name.lower() in s_lower:
            referenced.append(name)
        else:
            # Check for partial match — but only significant parts (>4 chars)
            # to avoid matching "Nice" in "nice weather" etc.
            parts = re.split(r'[\s,\'-]+', name)
            for part in parts:
                if len(part) > 4 and part.lower() in s_lower:
                    referenced.append(name)
                    break
    return referenced


def validate_prolog_structure(
    prolog_text: str,
    tour_meta: Optional[Dict] = None,
) -> List[Dict]:
    """Validate that a prolog follows Michael's four-part structure.
    
    Args:
        prolog_text: The prolog text (either from _saved_prolog or extracted
                     from Stop 1 of tour_content).
        tour_meta: Dict with optional keys:
            - transport_mode: str (e.g. 'bike', 'on_foot', 'vehicle')
            - tour_name: str (the tour title/request)
            - stop_names: list[str] (names of all stops in the tour)
    
    Returns:
        List of violation dicts, each with:
            - part: int (1-4)
            - code: str (machine-readable violation code)
            - severity: str ('error' or 'warning')
            - message: str (human-readable description)
    """
    if tour_meta is None:
        tour_meta = {}
    
    transport_mode = tour_meta.get('transport_mode', 'on_foot')
    stop_names = tour_meta.get('stop_names', [])
    
    violations = []
    
    if not prolog_text or not prolog_text.strip():
        violations.append({
            'part': 0,
            'code': 'PROLOG_MISSING',
            'severity': 'error',
            'message': 'No prolog text found.',
        })
        return violations
    
    sentences = _split_into_sentences(prolog_text)
    if not sentences:
        violations.append({
            'part': 0,
            'code': 'PROLOG_EMPTY',
            'severity': 'error',
            'message': 'Prolog text contains no complete sentences.',
        })
        return violations
    
    # ─── Detect which parts are present and where ──────────────────────────
    # We assign each sentence to its PRIMARY role. A sentence is assigned to
    # the earliest part it qualifies for (Parts 1→4), so that ordering checks
    # reflect structural intent rather than incidental keyword overlap.
    
    part1_indices = []  # Sentences that serve Part 1 (tour name + transport)
    part2_indices = []  # Sentences that serve Part 2 (route substance)
    part3_indices = []  # Sentences that serve Part 3 (sourced facts/intrigue)
    part4_indices = []  # Sentences that serve Part 4 (forward connection)
    
    # Also track raw detection (for substance checks, a sentence can qualify
    # for multiple parts)
    raw_p2_indices = []
    raw_p3_indices = []
    raw_p4_indices = []
    
    for i, sent in enumerate(sentences):
        is_p1 = _sentence_mentions_transport(sent, transport_mode)
        p2_indicators = _sentence_has_route_substance(sent)
        is_p3 = _sentence_has_sourced_fact(sent)
        is_p4_vague = bool(_VAGUE_FORWARD_RE.search(sent))
        is_p4_specific = bool(_sentence_names_stop_content(sent, stop_names)) if stop_names else False
        # Forward-looking language + specific stops = good Part 4
        is_p4_forward = bool(_FORWARD_LOOKING_RE.search(sent))
        is_p4 = is_p4_vague or is_p4_specific or (is_p4_forward and is_p4_specific)
        
        # Track raw detections for substance checks
        if p2_indicators:
            raw_p2_indices.append(i)
        if is_p3:
            raw_p3_indices.append(i)
        if is_p4:
            raw_p4_indices.append(i)
        
        # Primary role assignment: earliest qualifying part wins
        # Part 4 has special handling — only counts as primary if:
        #   (a) it's a vague forward ref (that's ALL it does), or
        #   (b) it names stops AND does not qualify as Part 2 or Part 3
        if is_p1:
            part1_indices.append(i)
        elif p2_indicators:
            part2_indices.append(i)
        elif is_p3:
            part3_indices.append(i)
        elif is_p4:
            part4_indices.append(i)
    
    # ─── CHECK 1: Present and in order ────────────────────────────────────
    # Presence check uses raw detection (any sentence qualifying counts),
    # but ordering check uses primary assignment (to avoid false positives
    # from multi-qualified sentences).
    parts_present = {
        1: len(part1_indices) > 0,
        2: len(part2_indices) > 0 or len(raw_p2_indices) > 0,
        3: len(part3_indices) > 0 or len(raw_p3_indices) > 0,
        4: len(part4_indices) > 0 or len(raw_p4_indices) > 0,
    }
    
    for part_num, present in parts_present.items():
        if not present:
            part_descriptions = {
                1: 'Tour name and transportation mode',
                2: 'Directions and physicality expectation (route substance)',
                3: 'Purpose / intrigue with sourced facts',
                4: 'Forward connection to stops',
            }
            violations.append({
                'part': part_num,
                'code': f'PART{part_num}_MISSING',
                'severity': 'error',
                'message': f'Part {part_num} ({part_descriptions[part_num]}) is not present.',
            })
    
    # Check order: use PRIMARY assignments only. The FIRST occurrence of each
    # primarily-assigned part must be in sequence 1→2→3→4.
    first_indices = {}
    if part1_indices:
        first_indices[1] = min(part1_indices)
    if part2_indices:
        first_indices[2] = min(part2_indices)
    elif raw_p2_indices:
        first_indices[2] = min(raw_p2_indices)
    if part3_indices:
        first_indices[3] = min(part3_indices)
    elif raw_p3_indices:
        first_indices[3] = min(raw_p3_indices)
    if part4_indices:
        first_indices[4] = min(part4_indices)
    elif raw_p4_indices:
        first_indices[4] = min(raw_p4_indices)
    
    present_parts_ordered = sorted(first_indices.keys())
    for i in range(len(present_parts_ordered) - 1):
        p_a = present_parts_ordered[i]
        p_b = present_parts_ordered[i + 1]
        if first_indices[p_a] > first_indices[p_b]:
            violations.append({
                'part': p_b,
                'code': 'PARTS_OUT_OF_ORDER',
                'severity': 'error',
                'message': f'Part {p_b} appears before Part {p_a} (sentence {first_indices[p_b]+1} vs {first_indices[p_a]+1}).',
            })
    
    # ─── CHECK 2: Part 1 — names tour subject AND transport mode ──────────
    if parts_present[1]:
        # Already verified by detection — but double-check it's not ONLY keyword
        p1_sents = [sentences[i] for i in part1_indices]
        # The sentence must have at least 8 words of actual content
        all_trivial = all(len(s.split()) < 8 for s in p1_sents)
        if all_trivial:
            violations.append({
                'part': 1,
                'code': 'PART1_TOO_THIN',
                'severity': 'warning',
                'message': 'Part 1 sentences are too brief to name the tour subject substantively.',
            })
    
    # ─── CHECK 3: Part 2 — at minimum two of: endpoints, distance, terrain, duration
    if parts_present[2]:
        all_indicators = set()
        # Use ALL sentences with route substance (raw), not just primary-assigned ones.
        # A sentence assigned to P1 ("biking route from Nice to Antibes, 30 km flat terrain")
        # still contributes Part 2 substance — it's just also serving Part 1.
        for i in raw_p2_indices:
            all_indicators.update(_sentence_has_route_substance(sentences[i]))
        if len(all_indicators) < 2:
            violations.append({
                'part': 2,
                'code': 'PART2_INSUFFICIENT_SUBSTANCE',
                'severity': 'error',
                'message': (
                    f'Part 2 has only {len(all_indicators)} route indicator(s) '
                    f'({", ".join(sorted(all_indicators)) or "none"}); '
                    f'need at least 2 of: endpoints, distance, terrain, duration.'
                ),
            })
    
    # ─── CHECK 4: Part 3 — at least one sourced fact ──────────────────────
    if parts_present[3]:
        # Already ensured by detection — a sentence only scores as Part 3
        # if it has a year, named-person-action, or documented event.
        # But check that it's not drowning in fluff
        check_p3_indices = part3_indices if part3_indices else raw_p3_indices
        p3_sents = [sentences[i] for i in check_p3_indices]
        all_fluff = all(_VAGUE_FLUFF_RE.search(s) for s in p3_sents)
        if all_fluff and len(p3_sents) == 1:
            violations.append({
                'part': 3,
                'code': 'PART3_FLUFF_DOMINANT',
                'severity': 'warning',
                'message': 'Part 3 contains a sourced fact but is dominated by vague language.',
            })
    
    # ─── CHECK 5: Part 4 — names actual stop content ─────────────────────
    if parts_present[4]:
        check_p4_indices = part4_indices if part4_indices else raw_p4_indices
        p4_sents = [sentences[i] for i in check_p4_indices]
        
        # Check if it's only vague ("more stories await")
        all_vague = all(
            _VAGUE_FORWARD_RE.search(s) and not _sentence_names_stop_content(s, stop_names)
            for s in p4_sents
        )
        any_specific = False
        named_stops = []
        
        if stop_names:
            for s in p4_sents:
                refs = _sentence_names_stop_content(s, stop_names)
                if refs:
                    any_specific = True
                    named_stops.extend(refs)
        
        if all_vague and not any_specific:
            violations.append({
                'part': 4,
                'code': 'PART4_VAGUE_PROMISE',
                'severity': 'error',
                'message': (
                    'Part 4 makes only vague forward references ("more stories await") '
                    'without naming actual stop content.'
                ),
            })
        
        # Cross-check: named content must actually be in the tour's stops
        if stop_names and named_stops:
            # Check for phantom stops
            for ref in named_stops:
                if ref not in stop_names:
                    # Check partial matches
                    found = False
                    for sn in stop_names:
                        if ref.lower() in sn.lower() or sn.lower() in ref.lower():
                            found = True
                            break
                    if not found:
                        violations.append({
                            'part': 4,
                            'code': 'PART4_PHANTOM_STOP',
                            'severity': 'error',
                            'message': f'Part 4 references "{ref}" which is not a stop in this tour.',
                        })
    
    return violations


def extract_prolog_from_tour_content(tour_content: str) -> str:
    """Extract the prolog text from assembled tour content.
    
    The prolog is injected into Stop 1's body (after Orientation, before the
    stop's own description). It's the text between the Orientation paragraph
    and the first description-like paragraph that is clearly about the stop's
    specific subject.
    
    For tours generated before LOCAL-259 (four-part prolog), the prolog is
    typically the first 1-3 paragraphs of Stop 1's body text after Orientation.
    """
    if not tour_content:
        return ""
    
    # Find Stop 1 section
    stop1_match = re.search(r'Stop\s+1:.*?(?=\nStop\s+2:|\Z)', tour_content, re.DOTALL)
    if not stop1_match:
        return ""
    
    s1_text = stop1_match.group(0)
    
    # The prolog is in the Orientation field (where it gets injected)
    # OR in the body text after the structured fields.
    # Check Orientation first:
    orient_match = re.search(r'Orientation:\s*(.+?)(?=\n\n)', s1_text, re.DOTALL)
    if orient_match:
        orient_text = orient_match.group(1).strip()
        # The orientation may contain BOTH the navigation sentence AND the prolog
        # The prolog is typically longer and non-navigational
        # Split by paragraph
        paragraphs = [p.strip() for p in orient_text.split('\n\n') if p.strip()]
        if paragraphs:
            # If there's only one paragraph and it's short navigation, no prolog
            # If there are multiple paragraphs, prolog is after the navigation intro
            return orient_text
    
    # Fallback: look for body text between Orientation/structured fields and the
    # stop's main description. The prolog is often the first block of flowing text.
    # Find text after all structured fields up to the main description
    body_start = re.search(
        r'(?:Specific Examples:.*?\n\n|Orientation:.*?\n\n)',
        s1_text, re.DOTALL
    )
    if body_start:
        body_text = s1_text[body_start.end():].strip()
        # Take text up to Directions:
        directions_match = re.search(r'\nDirections:', body_text)
        if directions_match:
            body_text = body_text[:directions_match.start()].strip()
        
        # The prolog is typically the first 1-3 paragraphs (before stop-specific content)
        paragraphs = [p.strip() for p in body_text.split('\n\n') if p.strip()]
        if paragraphs:
            # Heuristic: prolog paragraphs talk about the tour broadly;
            # stop-specific paragraphs mention the stop name or its specifics
            return paragraphs[0] if len(paragraphs) == 1 else '\n\n'.join(paragraphs[:2])
    
    return ""


def extract_stop_names_from_tour_content(tour_content: str) -> List[str]:
    """Extract all stop names from tour content."""
    return re.findall(r'Stop\s+\d+:\s*(.+)', tour_content)


def extract_transport_mode_from_tour_content(tour_content: str) -> str:
    """Infer transport mode from tour title/content."""
    # Check the title line
    title_match = re.match(r'.+', tour_content)
    if title_match:
        title = title_match.group(0).lower()
        if any(w in title for w in ['cycling', 'bike', 'biking']):
            return 'bike'
        if any(w in title for w in ['driving', 'car', 'road trip', 'jeep']):
            return 'vehicle'
        if any(w in title for w in ['horse', 'camel', 'dogsled']):
            return 'animal'
        if any(w in title for w in ['boat', 'kayak', 'sailing']):
            return 'boat'
    return 'on_foot'
