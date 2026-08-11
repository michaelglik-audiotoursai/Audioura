"""[LOCAL-383] Story beat extraction and injection.

Extracts named people and what they did from exhibition/venue page text,
then provides per-stop story-beat instructions so the LLM includes at least
one sentence naming a person and what they did in each stop.

A "story beat" = a named person + a specific circumstance or consequence.
NOT a general claim about art.

Design principles:
  - Every beat must be grounded in verbatim page text (never invented).
  - People are extracted with their ROLE/ACTION from the page.
  - Beats are distributed across stops so each stop has at least one.
  - If the page genuinely supports nothing for a stop, say less (don't pad).

[LOCAL-393] A beat's subject must be a PERSON — not a country, city, region,
museum, or gallery. Places may appear inside a beat but never as the subject.
Reuses _looks_like_person_name from prose_entity_grounding_gate (D304 lesson).
"""
import re
from typing import Dict, List, Optional, Tuple

# [LOCAL-393] Import person-detection from the single source of truth (D304 lesson).
from prose_entity_grounding_gate import _looks_like_person_name

# [LOCAL-393] Known geographic place names — countries, cities, regions that regex
# patterns may misidentify as person names (single-word or multi-word).
# These must NEVER be beat subjects. Places may appear *inside* a beat's action
# ("printed by Mourlot Frères in Paris") but never as the subject.
_KNOWN_PLACE_NAMES = frozenset({
    # Countries
    'france', 'spain', 'italy', 'germany', 'england', 'portugal', 'netherlands',
    'belgium', 'switzerland', 'austria', 'greece', 'russia', 'japan', 'china',
    'brazil', 'mexico', 'canada', 'australia', 'india', 'turkey', 'egypt',
    'morocco', 'algeria', 'tunisia', 'ireland', 'scotland', 'wales', 'poland',
    'hungary', 'romania', 'sweden', 'norway', 'denmark', 'finland', 'iceland',
    'croatia', 'serbia', 'cuba', 'argentina', 'chile', 'colombia', 'peru',
    # Cities commonly found in art/museum contexts
    'paris', 'nice', 'milan', 'rome', 'florence', 'venice', 'naples',
    'london', 'berlin', 'vienna', 'madrid', 'barcelona', 'lisbon',
    'amsterdam', 'brussels', 'geneva', 'zurich', 'munich', 'hamburg',
    'nuremberg', 'almeria', 'seville', 'granada', 'toledo',
    'new york', 'boston', 'chicago', 'los angeles', 'san francisco',
    'philadelphia', 'washington', 'houston', 'dallas', 'miami',
    'tokyo', 'beijing', 'shanghai', 'moscow', 'st petersburg',
    'cairo', 'istanbul', 'athens', 'prague', 'budapest', 'warsaw',
    'dublin', 'edinburgh', 'lyon', 'marseille', 'toulouse', 'bordeaux',
    'strasbourg', 'montpellier', 'avignon', 'cannes', 'antibes',
    # Regions
    'provence', 'normandy', 'brittany', 'burgundy', 'tuscany', 'lombardy',
    'catalonia', 'andalusia', 'bavaria', 'saxony', 'flanders', 'wallonia',
    'riviera', 'côte d\'azur',
    # Common institutional/geographic words that appear title-cased
    'europe', 'america', 'africa', 'asia', 'oceania',
})


def _is_valid_beat_subject(candidate: str) -> bool:
    """[LOCAL-393] Validate that a beat subject is a PERSON, not a place.

    A beat's subject must be a person — not a country, city, region, museum,
    or gallery. Uses _looks_like_person_name for multi-word candidates and
    a place-name blocklist for single-word candidates.

    Single-word candidates (surnames like 'Dalí', 'Freud') are valid UNLESS
    they match a known place name. Multi-word candidates must pass the
    existing person-name heuristic from prose_entity_grounding_gate.
    """
    if not candidate or not candidate.strip():
        return False

    clean = candidate.strip()
    words = clean.split()

    # Reject known places (case-insensitive)
    if clean.lower() in _KNOWN_PLACE_NAMES:
        return False

    # Multi-word: delegate to the canonical person-name detector
    if len(words) >= 2:
        return _looks_like_person_name(clean)

    # Single word: accept as surname if not a known place
    # (already checked above)
    return True


# [LOCAL-391] Unfilled role pattern — 'with publisher', 'with printer', etc.
# These must be caught and scrubbed post-generation if the person name is missing.
_UNFILLED_ROLE_PATTERN = re.compile(
    r'\b(with|the|a)\s+(publisher|printer|donor|patron|editor|binder)\b',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Person + action patterns
# ---------------------------------------------------------------------------

# Pattern: "published by PERSON" / "printed by PERSON"
_PUBLISHED_PRINTED_BY = re.compile(
    r'(?:published|printed|edited|designed|bound)\s+by\s+'
    r'([A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+){0,3}(?:\s+(?:Frères|Bros|& Co|Press|Éditions))?)',
    re.UNICODE,
)

# Pattern: "Gift of PERSON" / "Bequest of PERSON"
_GIFT_OF = re.compile(
    r'(?:Gift|Bequest|Donation|Collection)\s+of\s+'
    r'([A-Z][a-zà-ÿ]+(?:\s+[A-Z]\.?\s*)?(?:[a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)*))',
    re.UNICODE,
)

# Pattern: "PERSON Gallery" / "PERSON Wing" / "PERSON Room"
_NAMED_SPACE = re.compile(
    r'((?:[A-Z][a-zà-ÿ]+\.?\s+){1,4}(?:and\s+(?:[A-Z][a-zà-ÿ]+\.?\s+){1,3})?)'
    r'(?:Gallery|Wing|Room|Center|Centre|Hall)\b',
    re.UNICODE,
)

# Pattern: "PERSON's TITLE" — possessive indicating authorship/creation
_POSSESSIVE_WORK = re.compile(
    r"([A-Z][a-zà-ÿ]+(?:'s|\u2019s))\s+(?:[\w\s]{2,40})",
    re.UNICODE,
)

# Pattern: "ARTIST and PERSON's TITLE" — collaboration pair
_COLLAB_PAIR = re.compile(
    r'([A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)?)\s+and\s+'
    r'(?:French\s+)?(?:poet\s+|writer\s+|author\s+|painter\s+)?'
    r'([A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)?)'
    r"(?:'s|\u2019s)\s+",
    re.UNICODE,
)

# Pattern: "as PERSON did in..." / "PERSON illustrat..." / "PERSON partnered"
_PERSON_ACTION = re.compile(
    r'(?:as\s+)?([A-Z][a-zà-ÿí]+(?:\s+[A-Z][a-zà-ÿ]+)?)\s+'
    r'(?:did\s+in|illustrated|partnered|created|designed|collaborated|devised|'
    r'published|printed|founded|established|assembled|donated|bequeathed)',
    re.UNICODE,
)


def extract_story_beats(page_text: str) -> List[Dict[str, str]]:
    """Extract grounded story beats from page text.

    Each beat is: {person, action, source_sentence, role}
    where:
      - person: the named person or entity
      - action: what they did (verbatim or near-verbatim from page)
      - source_sentence: the sentence from which this was extracted
      - role: publisher|printer|donor|gallery_patron|collaborator|illustrator|author|founder

    Returns empty list if no beats found (never raises).
    """
    if not page_text:
        return []

    beats = []
    seen_people = set()

    # Strip HTML tags from input for cleaner extraction
    clean_text = re.sub(r'<[^>]+>', '', page_text)
    # Collapse whitespace/newlines within fragments (nav menus become garbage)
    clean_text = re.sub(r'\s*\n\s*', ' ', clean_text)
    clean_text = re.sub(r'\s{2,}', ' ', clean_text)

    # Split into sentences for source tracking
    sentences = re.split(r'(?<=[.!?])\s+', clean_text)
    # Also include standalone metadata lines (credit lines often lack periods)
    lines = clean_text.split('\n')
    all_fragments = list(set(sentences + [l.strip() for l in lines if len(l.strip()) > 30]))
    # Filter out navigation-like fragments (too many unrelated capitalized words)
    all_fragments = [f for f in all_fragments if len(f) < 500 and '\n' not in f]

    for fragment in all_fragments:
        # --- Published/Printed by ---
        for m in _PUBLISHED_PRINTED_BY.finditer(fragment):
            person = m.group(1).strip()
            verb = fragment[m.start():m.start()+20].split()[0].lower()
            if person.lower() not in seen_people and _is_valid_beat_subject(person):
                role = 'printer' if 'print' in verb else 'publisher'
                beats.append({
                    'person': person,
                    'action': f"{verb} this work",
                    'source_sentence': fragment.strip(),
                    'role': role,
                })
                seen_people.add(person.lower())

        # --- Gift/Bequest of ---
        for m in _GIFT_OF.finditer(fragment):
            person = m.group(1).strip()
            gift_type = fragment[m.start():m.start()+10].split()[0].lower()
            if person.lower() not in seen_people and _is_valid_beat_subject(person):
                beats.append({
                    'person': person,
                    'action': f"gave this work as a {gift_type} to the museum",
                    'source_sentence': fragment.strip(),
                    'role': 'donor',
                })
                seen_people.add(person.lower())

        # --- Named gallery/space ---
        for m in _NAMED_SPACE.finditer(fragment):
            person = m.group(1).strip().rstrip('.')
            # Skip if it's just a common word
            if person.lower() in ('the', 'a', 'this', 'new', 'main', 'upper', 'lower'):
                continue
            space_type = fragment[m.end()-10:m.end()+10]
            if person.lower() not in seen_people and _is_valid_beat_subject(person):
                beats.append({
                    'person': person,
                    'action': "the gallery where these works are displayed is named for this patron",
                    'source_sentence': fragment.strip(),
                    'role': 'gallery_patron',
                })
                seen_people.add(person.lower())

        # --- Collaboration pairs ---
        for m in _COLLAB_PAIR.finditer(fragment):
            person1 = m.group(1).strip()
            person2 = m.group(2).strip()
            for p in (person1, person2):
                if p.lower() not in seen_people and _is_valid_beat_subject(p):
                    other = person2 if p == person1 else person1
                    beats.append({
                        'person': p,
                        'action': f"collaborated with {other} on a livre d'artiste",
                        'source_sentence': fragment.strip(),
                        'role': 'collaborator',
                    })
                    seen_people.add(p.lower())

        # --- Person + action verb ---
        for m in _PERSON_ACTION.finditer(fragment):
            person = m.group(1).strip()
            if person.lower() not in seen_people and _is_valid_beat_subject(person):
                # Extract the action from context
                action_start = m.start()
                action_text = fragment[action_start:min(action_start + 120, len(fragment))]
                # Clean to first period or end
                action_text = action_text.split('.')[0].strip()
                beats.append({
                    'person': person,
                    'action': action_text,
                    'source_sentence': fragment.strip(),
                    'role': 'illustrator',
                })
                seen_people.add(person.lower())

        # --- Possessive authorship: "PERSON's TITLE" → person authored the text ---
        for m in _POSSESSIVE_WORK.finditer(fragment):
            raw_person = m.group(1)  # includes the 's
            # Strip possessive suffix
            person = re.sub(r"(?:'s|\u2019s)$", '', raw_person).strip()
            if person.lower() not in seen_people and _is_valid_beat_subject(person):
                # Avoid common non-person possessives
                if person.lower() in ('today', 'museum', 'gallery', 'exhibition',
                                       'artist', 'visitor', 'world', 'century',
                                       'publisher', 'artiste'):
                    continue
                # Check if this is just a surname of someone already found
                _already_found = any(person.lower() in existing for existing in seen_people)
                if _already_found:
                    continue
                # Find what they authored from context after the match
                after_text = fragment[m.end():min(m.end()+60, len(fragment))].split(';')[0].strip()
                beats.append({
                    'person': person,
                    'action': f"authored the text that was illustrated",
                    'source_sentence': fragment.strip(),
                    'role': 'author',
                })
                seen_people.add(person.lower())

    # --- Special: "Rarely on view" as a circumstance beat ---
    if re.search(r'rarely\s+on\s+view', page_text, re.IGNORECASE):
        beats.append({
            'person': '(the works themselves)',
            'action': 'are rarely on view — normally kept in archives',
            'source_sentence': _find_sentence_containing(page_text, 'rarely on view'),
            'role': 'circumstance',
        })

    # --- Special: "had no precedent" / "revolutionized" as stakes beat ---
    if re.search(r'had\s+no\s+precedent', page_text, re.IGNORECASE):
        beats.append({
            'person': '(the livre d\'artiste form)',
            'action': 'had no precedent and revolutionized the book as an art form',
            'source_sentence': _find_sentence_containing(page_text, 'had no precedent'),
            'role': 'stakes',
        })

    return beats


def attribute_beats_to_works(
    beats: List[Dict[str, str]],
    works: List[Dict],
) -> List[Dict[str, str]]:
    """[LOCAL-392] Attribute each beat to the specific work it was derived from.

    For each beat, check which work's metadata (credit_line, publisher,
    collaborator, artist, title) mentions that beat's person. Sets
    'source_work_index' on each beat (or None if exhibition-wide).

    This ensures beats are assigned ONLY to the stop whose work they come from.
    A beat that cannot be attributed to any single work is marked as
    exhibition_wide=True and will not be demanded of any specific stop.

    [LOCAL-393] Weak title matching now uses proximity: when the source sentence
    contains multiple work titles, only the title nearest the person name counts.
    This prevents "Pierre Reverdy" from being attributed to "Moses and Monotheism"
    when both titles appear in the same sentence but Reverdy is next to
    "Au Soleil du Plafond".
    """
    if not beats or not works:
        return beats

    for beat in beats:
        if beat['role'] in ('circumstance', 'stakes'):
            beat['source_work_index'] = None
            beat['exhibition_wide'] = True
            continue

        person_lower = beat['person'].lower()
        surname_lower = beat['person'].split()[-1].lower() if beat['person'].split() else ''
        source_sentence_lower = beat.get('source_sentence', '').lower()

        best_match_idx = None
        best_match_strength = 0  # higher = more confident

        for idx, work in enumerate(works):
            strength = 0
            work_credit = (work.get('credit_line') or '').lower()
            work_publisher = (work.get('publisher') or '').lower()
            work_collaborator = (work.get('collaborator') or '').lower()
            work_artist = (work.get('artist') or '').lower()
            work_title = (work.get('title') or '').lower()

            # Strong match: person appears in credit_line or publisher or collaborator
            if work_credit and (person_lower in work_credit or surname_lower in work_credit):
                strength = max(strength, 3)
            if work_publisher and (person_lower in work_publisher or work_publisher in person_lower):
                strength = max(strength, 3)
            if work_collaborator and (person_lower in work_collaborator or work_collaborator in person_lower):
                strength = max(strength, 3)

            # Medium match: person is the artist of this work
            if work_artist and (person_lower in work_artist or surname_lower in work_artist):
                strength = max(strength, 2)

            # [LOCAL-393] Weak match: work title in source sentence, BUT only if
            # the title is proximate to the person name. When multiple titles appear
            # in the same sentence, we track distance so the closest title wins.
            # This prevents cross-attribution when a sentence mentions multiple
            # artist-work pairs (e.g., "Dalí...Moses and Monotheism; ...Reverdy...
            # Au Soleil du Plafond").
            if work_title and len(work_title) > 5 and work_title in source_sentence_lower:
                person_pos = source_sentence_lower.find(person_lower)
                if person_pos < 0:
                    person_pos = source_sentence_lower.find(surname_lower)
                title_pos = source_sentence_lower.find(work_title)
                if person_pos >= 0 and title_pos >= 0:
                    distance = abs(person_pos - title_pos)
                    # Use proximity-weighted weak match: closer = stronger signal.
                    # Only count as weak match if within 150 chars, and prefer
                    # closer matches by encoding distance in a fractional strength.
                    if distance <= 150:
                        # Strength 1.x where x encodes closeness (closer = higher)
                        proximity_strength = 1.0 + (150 - distance) / 150.0  # range [1.0, 2.0)
                        if proximity_strength > strength:
                            strength = proximity_strength
                else:
                    # Can't determine proximity — still allow weak match as fallback
                    strength = max(strength, 1)

            if strength > best_match_strength:
                best_match_strength = strength
                best_match_idx = idx

        if best_match_idx is not None and best_match_strength >= 1:
            beat['source_work_index'] = best_match_idx
            beat['exhibition_wide'] = False
            # Log the derivation per LOCAL-392 requirement
            work_title = works[best_match_idx].get('title', '(unknown)')
            print(f"  [LOCAL-392] beat='{beat['person']}' source_work='{work_title}' -> stop {best_match_idx + 1}")
        else:
            # Cannot attribute to a specific work — exhibition-wide
            beat['source_work_index'] = None
            beat['exhibition_wide'] = True
            print(f"  [LOCAL-392] beat='{beat['person']}' -> exhibition_wide (no single work match)")

    return beats


def _find_sentence_containing(text: str, phrase: str) -> str:
    """Find the sentence containing a phrase (case-insensitive)."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    for s in sentences:
        if phrase.lower() in s.lower():
            return s.strip()
    return ''


def assign_beats_to_stops(
    beats: List[Dict[str, str]],
    stop_names: List[str],
    matched_works: Optional[List[Dict]] = None,
    framing_case: str = 'none',
) -> List[List[Dict[str, str]]]:
    """[LOCAL-392] Distribute story beats across stops using work-attribution.

    Each beat is assigned ONLY to the stop whose work it was derived from.
    A beat from work A is NEVER demanded of work B's stop.

    [LOCAL-392] Fixed: previously beats were matched by weak substring heuristics
    against work metadata, causing cross-contamination. Now: beats carry a
    source_work_index (set by attribute_beats_to_works) that definitively binds
    them. Exhibition-wide beats (gallery patron, circumstance, stakes) are
    distributed without being demanded as required content.

    Args:
        beats: All extracted beats (should have source_work_index set by
               attribute_beats_to_works; falls back to old logic if missing)
        stop_names: List of stop names in order
        matched_works: Optional list of matched work dicts (from exhibition checklist)
        framing_case: 'exhibition' | 'venue_purpose' | 'none'

    Returns:
        List of beat-lists, one per stop. Each entry is a list of beat dicts
        assigned to that stop.
    """
    n_stops = len(stop_names)
    if not beats or n_stops == 0:
        return [[] for _ in range(n_stops)]

    # Classify beats by type for distribution
    person_beats = [b for b in beats if b['role'] not in ('circumstance', 'stakes')]
    context_beats = [b for b in beats if b['role'] in ('circumstance', 'stakes')]

    assigned = [[] for _ in range(n_stops)]
    used_beat_indices = set()

    # [LOCAL-392] PRIMARY PASS: assign beats by their source_work_index
    # This is the definitive assignment — a beat belongs to its source work's stop.
    has_attribution = any(
        'source_work_index' in b and b.get('source_work_index') is not None
        for b in person_beats
    )

    if has_attribution:
        for j, beat in enumerate(person_beats):
            src_idx = beat.get('source_work_index')
            if src_idx is not None and 0 <= src_idx < n_stops:
                assigned[src_idx].append(beat)
                used_beat_indices.add(j)
            elif beat.get('exhibition_wide'):
                # Exhibition-wide beats: skip for now, handle in context pass
                pass
            # else: no attribution and not exhibition_wide — will be distributed below
    else:
        # [LOCAL-392] FALLBACK: legacy matching for beats without attribution
        # (backwards compatibility for callers that don't call attribute_beats_to_works)
        if matched_works:
            for i, work in enumerate(matched_works):
                if i >= n_stops:
                    break
                if not work:
                    continue
                work_publisher = (work.get('publisher') or '').lower().strip()
                work_collaborator = (work.get('collaborator') or '').lower().strip()
                work_artist = (work.get('artist') or '').lower().strip()

                for j, beat in enumerate(person_beats):
                    if j in used_beat_indices:
                        continue
                    if len(assigned[i]) >= 1:
                        break
                    person_lower = beat['person'].lower()
                    if (person_lower and (
                        (work_publisher and person_lower in work_publisher) or
                        (work_collaborator and person_lower in work_collaborator) or
                        (work_artist and person_lower in work_artist) or
                        (work_publisher and work_publisher in person_lower) or
                        (work_collaborator and work_collaborator in person_lower)
                    )):
                        assigned[i].append(beat)
                        used_beat_indices.add(j)

    # [LOCAL-392] SECONDARY PASS: distribute exhibition-wide beats
    # These are NOT demanded as required content — they supplement without
    # being tracked by the retry mechanism.
    exhibition_wide_beats = [
        b for j, b in enumerate(person_beats)
        if j not in used_beat_indices and b.get('exhibition_wide')
    ]
    # Mark these so get_required_beat_names skips them
    for b in exhibition_wide_beats:
        b['exhibition_wide'] = True

    if exhibition_wide_beats:
        # Distribute to stops with fewest beats
        for ew_beat in exhibition_wide_beats:
            min_count = min(len(assigned[i]) for i in range(n_stops))
            candidates = [i for i in range(n_stops) if len(assigned[i]) == min_count]
            target = candidates[0]
            assigned[target].append(ew_beat)

    # [LOCAL-392] TERTIARY PASS: distribute remaining unattributed beats round-robin
    remaining_person = [
        b for j, b in enumerate(person_beats)
        if j not in used_beat_indices and not b.get('exhibition_wide')
    ]
    if remaining_person:
        bare_stops = [i for i in range(n_stops) if not assigned[i]]
        rr_idx = 0
        for i in bare_stops:
            if rr_idx >= len(remaining_person):
                break
            assigned[i].append(remaining_person[rr_idx])
            rr_idx += 1
        while rr_idx < len(remaining_person):
            min_count = min(
                sum(1 for b in assigned[i] if b['role'] not in ('circumstance', 'stakes'))
                for i in range(n_stops)
            )
            candidates = [
                i for i in range(n_stops)
                if sum(1 for b in assigned[i] if b['role'] not in ('circumstance', 'stakes')) == min_count
            ]
            target = candidates[rr_idx % len(candidates)]
            assigned[target].append(remaining_person[rr_idx])
            rr_idx += 1

    # Ensure all stops have at least one beat (context beats as fallback)
    for i in range(n_stops):
        if not assigned[i]:
            if context_beats:
                assigned[i].append(context_beats[i % len(context_beats)])
            elif person_beats:
                assigned[i].append(person_beats[i % len(person_beats)])

    # Add context beats to first and last stops (they serve as framing)
    if context_beats:
        for cb in context_beats:
            if cb['role'] == 'stakes' and assigned[0]:
                assigned[0].insert(0, cb)
            elif cb['role'] == 'circumstance' and n_stops > 1:
                mid = n_stops // 2
                assigned[mid].append(cb)

    return assigned


def get_required_beat_names(stop_beats: List[Dict[str, str]]) -> List[str]:
    """[LOCAL-391] Return the list of person surnames that MUST appear in the stop's output.

    Only person beats (not circumstance/stakes) produce required names.
    [LOCAL-392] Exhibition-wide beats are NOT required — they supplement without
    being demanded, since they don't belong to this stop's specific work.
    Returns surnames (last word of each person's name), deduplicated.
    """
    if not stop_beats:
        return []
    names = []
    seen = set()
    for b in stop_beats:
        if b['role'] in ('circumstance', 'stakes'):
            continue
        # [LOCAL-392] Skip exhibition-wide beats — they are not required
        if b.get('exhibition_wide'):
            continue
        surname = b['person'].split()[-1]
        if surname.lower() not in seen:
            names.append(surname)
            seen.add(surname.lower())
    return names


def check_required_beats_present(
    description: str,
    stop_beats: List[Dict[str, str]],
) -> Tuple[List[str], List[str]]:
    """[LOCAL-391] Check which required beat surnames are present/missing in the description.

    Returns (found, missing) — both are lists of surname strings.
    """
    required = get_required_beat_names(stop_beats)
    if not required or not description:
        return ([], required if required else [])

    desc_lower = description.lower()
    found = []
    missing = []
    for surname in required:
        if surname.lower() in desc_lower:
            found.append(surname)
        else:
            missing.append(surname)
    return (found, missing)


# [LOCAL-404] Appositive-only pattern detection.
# A sentence that merely identifies someone by role is NOT a story.
# Pattern: "Name, a/an/the ROLE" or "Name, ROLE of THING"
# Example failures: "Mourlot Frères, a renowned French lithographic printing company"
#                   "Louis Broder, a French publisher and art dealer"
# What we need: a verb that carries consequence ("Broder gambled on livres d'artiste")
_APPOSITIVE_ONLY_RE = re.compile(
    r'([A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+){0,3})'  # Person name
    r',\s+'
    r'(?:a|an|the)\s+'  # article
    r'(?:renowned\s+|famous\s+|celebrated\s+|noted\s+|prominent\s+|leading\s+|'
    r'French\s+|German\s+|Italian\s+|Spanish\s+|American\s+|British\s+)*'  # optional adjectives
    r'(?:publisher|printer|printmaker|printing\s+company|art\s+dealer|'
    r'lithograph(?:ic|er)|editor|bookseller|collector|patron|philanthropist|'
    r'designer|bookbinder|gallerist|engraver|typographer|publisher\s+and\s+art\s+dealer)',
    re.UNICODE,
)

# A CONSEQUENTIAL verb makes a sentence a story, not an appositive.
# These are verbs that carry action/consequence — not "is", "was", "been".
_CONSEQUENTIAL_VERB_RE = re.compile(
    r'\b(?:worked|gambled|assembled|spent|pulled|risked|established|revolutionized|'
    r'founded|persuaded|convinced|insisted|refused|chose|discovered|invented|'
    r'transformed|built|created|produced|collaborated|partnered|devised|'
    r'commissioned|negotiated|apprenticed|trained|mentored|introduced|'
    r'pioneered|rejected|challenged|broke|defied|sacrificed|devoted|'
    r'dedicated|abandoned|returned|travelled|traveled|visited|invited|'
    r'gathered|collected|acquired|purchased|sold|exhibited|displayed|'
    r'launched|opened|closed|destroyed|restored|preserved|donated|gave|'
    r'bequeathed|entrusted|championed|supported|financed|funded|backed)\b',
    re.IGNORECASE,
)


def detect_appositive_only_beats(description: str, stop_beats: List[Dict[str, str]]) -> List[str]:
    """[LOCAL-404] Detect beat people whose ONLY mention is an appositive (role identification).

    A beat person passes if at least one sentence mentioning them contains a
    consequential verb where THEY are the agent (subject). A beat person fails if
    every mention is of the form "Name, a/the ROLE" with no action they perform.

    Key insight: "Miró's collaboration with Broder, the publisher, revolutionized..."
    does NOT count as Broder's story — "revolutionized" is the work's verb, not Broder's.
    Broder needs his OWN verb: "Broder gambled on livres d'artiste..."

    Returns list of surnames that are appositive-only (need retry).
    """
    if not description or not stop_beats:
        return []

    required = get_required_beat_names(stop_beats)
    if not required:
        return []

    appositive_only = []
    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', description)

    for surname in required:
        surname_lower = surname.lower()
        # Find all sentences mentioning this person
        person_sentences = [s for s in sentences if surname_lower in s.lower()]
        if not person_sentences:
            continue  # Missing entirely — handled by check_required_beats_present

        # Check if ANY sentence has a consequential verb WHERE THE PERSON IS THE AGENT
        has_story = False
        for sent in person_sentences:
            if _person_has_consequential_action(sent, surname):
                has_story = True
                break

        if not has_story:
            appositive_only.append(surname)
            print(f"  [LOCAL-404] beat rejected: appositive-only '{surname}' "
                  f"— no consequential verb found")

    return appositive_only


def _person_has_consequential_action(sentence: str, surname: str) -> bool:
    """Check if the person is the AGENT of a consequential verb in this sentence.

    Passes:
      "Broder gambled on livres d'artiste" (Broder = subject of gambled)
      "At Mourlot, Miró worked the stones" (Miró = subject of worked, close to Mourlot)
      "Fridman spent decades assembling" (Fridman = subject of spent)

    Fails:
      "collaboration with Broder, the publisher, resulted in..." (result is the work's verb)
      "printed by Mourlot Frères, a printing company" (passive identification)
      "The gift [from Fridman] introduced this book" (gift = subject, not Fridman)
    """
    surname_lower = surname.lower()
    sent_lower = sentence.lower()

    # Quick check: is there ANY consequential verb?
    if not _CONSEQUENTIAL_VERB_RE.search(sentence):
        return False

    # Check if person is in a "with X, the/a ROLE" prepositional phrase
    # Also catches compound: "with A, the X, and B, the Y"
    # If so, verbs in the sentence are NOT the person's action
    prep_pattern = re.compile(
        r'\b(?:with|by)\s+(?:\w+\s+){0,3}' + re.escape(surname) + r'\s*,\s*(?:a|an|the)\s+',
        re.IGNORECASE,
    )
    # Also check compound prep phrase: "with X ... and Person, the/a ROLE"
    compound_prep_pattern = re.compile(
        r'\b(?:with|by)\s+.{0,80}\band\s+(?:\w+\s+){0,3}' + re.escape(surname) + r'\s*,\s*(?:a|an|the)\s+',
        re.IGNORECASE | re.DOTALL,
    )
    in_prep_phrase = prep_pattern.search(sentence) or compound_prep_pattern.search(sentence)
    if in_prep_phrase:
        # Person is in a prepositional phrase with appositive — not the subject.
        # But check if there's ALSO a clause where they ARE the subject
        # Split on semicolons/em-dashes for multi-clause sentences
        clauses = re.split(r'[;—–]', sentence)
        for clause in clauses:
            if surname_lower not in clause.lower():
                continue
            # Check BOTH simple and compound prep patterns
            if prep_pattern.search(clause) or compound_prep_pattern.search(clause):
                continue  # Still in the prep phrase
            # Person in a different clause — check for verb
            if _CONSEQUENTIAL_VERB_RE.search(clause):
                return True
        return False

    # Check for passive "X by Person" (e.g. "published by Broder")
    passive_pattern = re.compile(
        r'\b(?:published|printed|edited|designed|bound|gifted|donated)\s+by\s+(?:\w+\s+){0,2}'
        + re.escape(surname),
        re.IGNORECASE,
    )
    if passive_pattern.search(sentence):
        # "published by X" without further action — just identifies role
        # Check if there's MORE after the person's name that shows action
        person_pos = sent_lower.find(surname_lower)
        after_person = sentence[person_pos + len(surname):]
        # Strip the appositive clause if present
        after_person = re.sub(r'^\s*,\s*(?:a|an|the)\s+[^,]+,?', '', after_person)
        if _CONSEQUENTIAL_VERB_RE.search(after_person):
            return True
        return False

    # Person appears without prep/passive framing AND there's a consequential verb
    # Check proximity: verb should be within ~80 chars of the person's name
    person_pos = sent_lower.find(surname_lower)
    if person_pos < 0:
        return False

    # Find the nearest consequential verb
    for m in _CONSEQUENTIAL_VERB_RE.finditer(sentence):
        verb_pos = m.start()
        distance = abs(verb_pos - person_pos)
        # Verb within reasonable proximity AND not in a subordinate clause about someone else
        if distance < 100:
            # Make sure no OTHER proper noun is between person and verb as likely subject
            between_start = min(person_pos, verb_pos)
            between_end = max(person_pos, verb_pos)
            between_text = sentence[between_start:between_end]
            # If the person's name is before the verb, they're likely the subject
            if person_pos < verb_pos:
                return True
            # If verb is before person, check it's not about something else entirely
            # (e.g. "The work revolutionized... collaboration with Broder")
            # Only count if person is very close to the verb
            if distance < 30:
                return True

    return False


def build_appositive_retry_prompt(appositive_names: List[str], stop_beats: List[Dict[str, str]]) -> str:
    """[LOCAL-404] Build prompt supplement when beats are appositive-only (no story).

    Asks specifically for WHAT THE PERSON DID — an action with a consequence,
    not just their job title.
    """
    if not appositive_names:
        return ''

    appositive_lower = {n.lower() for n in appositive_names}
    parts = [
        "\n━━━ RETRY: APPOSITIVE-ONLY — NOT A STORY (LOCAL-404) ━━━",
        "Your previous attempt ONLY IDENTIFIED these people by role (\"X, a publisher\").",
        "An appositive is NOT a story. A story needs a VERB THAT CARRIES CONSEQUENCE.",
        "",
        "BAD (what you wrote — appositive only, no action):",
        "  \"Mourlot Frères, a renowned French lithographic printing company\"",
        "",
        "GOOD (what we need — a person DOING something with consequence):",
        "  \"At Mourlot Frères, Miró worked the stones himself alongside the printers\"",
        "  \"Broder gambled on livres d'artiste when almost no one bought them\"",
        "  \"Fridman spent decades assembling these books before giving them away\"",
        "",
        "REWRITE these people with an ACTION (what they did, not what they are):",
    ]

    for beat in stop_beats:
        if beat['role'] in ('circumstance', 'stakes'):
            continue
        surname = beat['person'].split()[-1]
        if surname.lower() in appositive_lower:
            parts.append(f"  ✗ {beat['person']} — write what they DID, not their job title.")
            parts.append(f"    Their role ({beat['role']}) is already known. Tell what HAPPENED.")
            parts.append("")

    parts.append(
        "If the corpus does not support a specific action for a person, state their role "
        "ONCE BRIEFLY and spend the words on something else. A short honest mention beats "
        "a padded appositive."
    )
    parts.append("━━━ END APPOSITIVE RETRY ━━━\n")
    return '\n'.join(parts)


def build_beat_retry_prompt_supplement(missing_names: List[str], stop_beats: List[Dict[str, str]]) -> str:
    """[LOCAL-391] Build a prompt supplement for retrying a stop with missing beats.

    Names the specific missing people and their actions so the model cannot
    ignore them a second time.
    """
    if not missing_names:
        return ''

    missing_lower = {n.lower() for n in missing_names}
    parts = [
        "\n━━━ RETRY: MISSING REQUIRED CONTENT (LOCAL-391) ━━━",
        "Your previous attempt OMITTED the following people. They MUST appear by",
        "surname in this description. Each person below has a documented role —",
        "write AT LEAST ONE sentence that names them and states what they did.",
        "",
    ]

    for beat in stop_beats:
        if beat['role'] in ('circumstance', 'stakes'):
            continue
        surname = beat['person'].split()[-1]
        if surname.lower() in missing_lower:
            parts.append(f"  ✗ MISSING: {beat['person']} — {beat['action']}")
            parts.append(f"    You MUST write their surname \"{surname}\" in your text.")
            parts.append("")

    parts.append(
        "Do NOT use generic role words ('the publisher', 'the donor') without the name."
    )
    parts.append("━━━ END RETRY REQUIREMENT ━━━\n")
    return '\n'.join(parts)


def build_story_beat_prompt_block(
    stop_beats: List[Dict[str, str]],
    framing_case: str = 'none',
) -> str:
    """Build the prompt injection block for story beats at a given stop.

    Returns a string to append to the stop's description_prompt.
    Returns '' if no beats.
    """
    if not stop_beats:
        return ''

    # Filter to real person beats (not context-only)
    person_beats = [b for b in stop_beats if b['role'] not in ('circumstance', 'stakes')]
    # [LOCAL-392] Separate work-specific beats (required) from exhibition-wide (supplementary)
    required_beats = [b for b in person_beats if not b.get('exhibition_wide')]
    supplementary_beats = [b for b in person_beats if b.get('exhibition_wide')]
    context_beats = [b for b in stop_beats if b['role'] in ('circumstance', 'stakes')]

    parts = []
    parts.append("""
STORY BEAT REQUIREMENT (LOCAL-383):
Your description MUST contain at least one sentence that NAMES A PERSON and
states WHAT THEY DID — a specific action or circumstance, not a general claim.
This SUPPLEMENTS (does not replace) any exhibition framing or thesis instructions above.

ARTIST ATTRIBUTION IS NON-NEGOTIABLE (LOCAL-390):
The Artist named in the WORK IDENTITY block above MUST appear by surname in your
description. A stop about a Miró book must name Miró; a stop about Dalí's
illustrations must name Dalí. The story beat persons (publishers, printers, donors)
are IN ADDITION TO the artist — never instead of. If WORK IDENTITY says
"Artist: Joan Miró", your text must contain "Miró".
""")

    # [LOCAL-391] Explicit REQUIRED CONTENT list — structurally unavoidable.
    # [LOCAL-392] Only work-specific beats are required; exhibition-wide beats are optional.
    if required_beats:
        parts.append("━━━ REQUIRED CONTENT — EACH SURNAME BELOW MUST APPEAR IN YOUR TEXT ━━━")
        for beat in required_beats[:3]:
            surname = beat['person'].split()[-1]
            parts.append(f"  ✓ \"{surname}\" — {beat['person']} ({beat['role'].replace('_', ' ')}): {beat['action']}")
        parts.append("Write at least one sentence per person above that names them by surname.")
        parts.append("If you omit any of these surnames, your response will be REJECTED and regenerated.")
        parts.append("━━━ END REQUIRED CONTENT ━━━")
        parts.append("")

    # [LOCAL-392] Exhibition-wide beats are supplementary — include if natural
    if supplementary_beats:
        parts.append("SUPPLEMENTARY PEOPLE (exhibition-wide — include if natural, not required):")
        for beat in supplementary_beats[:2]:
            parts.append(f"  ○ {beat['person']} ({beat['role'].replace('_', ' ')}): {beat['action']}")
        parts.append("")

    if person_beats:
        parts.append("GROUNDED PEOPLE AND ACTIONS (from the exhibition page — use at least one):")
        for beat in person_beats[:3]:  # Cap at 3 to avoid prompt bloat
            role_label = beat['role'].replace('_', ' ').title()
            parts.append(f"  • {beat['person']} ({role_label}): {beat['action']}")
        parts.append("")

    if context_beats:
        parts.append("GROUNDED CIRCUMSTANCES (from the exhibition page — weave in if natural):")
        for beat in context_beats[:2]:
            parts.append(f"  • {beat['action']}")
        parts.append("")

    if framing_case == 'exhibition':
        parts.append(
            "STORY SERVES THE THESIS: The person/action you name should connect to WHY\n"
            "this exhibition exists — e.g., a printer matters because the show argues printers\n"
            "were essential collaborators, not because printers are inherently interesting."
        )
    elif framing_case == 'venue_purpose':
        parts.append(
            "STORY SERVES THE VENUE: The person/action you name should connect to why\n"
            "this institution exists or how this collection was assembled."
        )
    else:
        parts.append(
            "STORY ATTACHES TO THE OBJECT: The person/action you name should illuminate\n"
            "something specific about this work or its history. No invented institutional narrative."
        )

    # [LOCAL-388] Explicit name-the-person rule: never leave a role as a placeholder
    # [LOCAL-392] Use required_beats for this rule (work-specific only)
    if required_beats:
        _role_names = []
        for beat in required_beats[:3]:
            _role_names.append(f"'{beat['role'].replace('_', ' ')}' → use '{beat['person']}'")
        parts.append(
            "NEVER-PLACEHOLDER RULE (LOCAL-388): Do NOT write 'with publisher', "
            "'with printer', 'with donor', or 'the patron'. Where a role is mentioned, "
            "NAME THE PERSON. Specifically:\n  " + "\n  ".join(_role_names)
        )
        parts.append("")

    parts.append("""
WHAT IS NOT A STORY (LOCAL-404 — CRITICAL):
An APPOSITIVE IS NOT A STORY. If the only thing you write about a person is their
job title in a comma-separated clause, that is a dictionary entry, not narration.

REJECTED (appositive-only — will trigger automatic retry):
  ✗ "Mourlot Frères, a renowned French lithographic printing company"
  ✗ "Louis Broder, a French publisher and art dealer"
  ✗ "Boris Fridman, a collector and philanthropist"

ACCEPTED (a person DOES something with consequence):
  ✓ "At Mourlot Frères, Miró worked the stones himself alongside the printers —
     the same workshop where Picasso and Matisse also pulled their plates"
  ✓ "Broder gambled on livres d'artiste when almost no one bought them,
     publishing editions of a few hundred"
  ✓ "Boris Fridman spent decades assembling these books before giving them away"

RULE: Every required person must appear in a sentence with a VERB THAT CARRIES
CONSEQUENCE — not "is", "was", or a bare role identification. If you cannot
find what someone DID, state their role ONCE BRIEFLY (five words max) and use
the remaining word budget on something you CAN ground.
""")

    return '\n'.join(parts)


def verify_beats_in_output(
    stop_beats: List[Dict[str, str]],
    output_text: str,
    stop_name: str,
) -> Dict[str, object]:
    """[LOCAL-388] Verify which assigned beats actually appear in the output prose.

    Returns dict with:
      - beats_assigned: int
      - beats_in_output: int
      - dropped: list of person names that were assigned but not found
      - found: list of person names that were found in output

    Matching is case-insensitive surname match.
    """
    if not stop_beats or not output_text:
        return {
            'beats_assigned': len(stop_beats) if stop_beats else 0,
            'beats_in_output': 0,
            'dropped': [b['person'] for b in (stop_beats or []) if b['role'] not in ('circumstance', 'stakes')],
            'found': [],
        }

    output_lower = output_text.lower()
    person_beats = [b for b in stop_beats if b['role'] not in ('circumstance', 'stakes')]
    found = []
    dropped = []

    for beat in person_beats:
        person = beat['person']
        # Check surname (last word) — case-insensitive
        surname = person.split()[-1].lower()
        # Also check full name
        if surname in output_lower or person.lower() in output_lower:
            found.append(person)
        else:
            dropped.append(person)

    return {
        'beats_assigned': len(person_beats),
        'beats_in_output': len(found),
        'dropped': dropped,
        'found': found,
    }


def _split_tour_into_stop_blocks(complete_tour: str) -> List[str]:
    """[LOCAL-390] Split a fully assembled tour into per-stop text blocks.

    Uses the 'Stop N:' header pattern to delimit blocks. Returns a list
    of strings, one per stop, containing ONLY the text for that stop
    (header through the next header or end of tour).
    """
    # Match "Stop N:" at line start (the rendered headers)
    stop_header_pattern = re.compile(r'^(Stop\s+\d+:)', re.MULTILINE)
    splits = stop_header_pattern.split(complete_tour)

    # splits = [preamble, 'Stop 1:', block1, 'Stop 2:', block2, ...]
    blocks = []
    i = 1  # skip preamble (index 0)
    while i < len(splits) - 1:
        header = splits[i]
        body = splits[i + 1]
        blocks.append(header + body)
        i += 2

    return blocks


def verify_beats_in_final_tour(
    story_beats_per_stop: List[List[Dict[str, str]]],
    complete_tour: str,
    stop_names: List[str],
    gate_removed_names: Optional[List[str]] = None,
) -> List[Dict[str, object]]:
    """[LOCAL-390] Verify beats against the FINAL assembled tour text.

    This is the authoritative verification. It measures the delivered artifact,
    not an intermediate stage.

    Args:
        story_beats_per_stop: Beat lists per stop (from assign_beats_to_stops)
        complete_tour: The fully assembled, post-gate, post-transform tour text
        stop_names: List of stop names in order
        gate_removed_names: Names known to have been removed by the grounding gate

    Returns:
        List of result dicts, one per stop:
          - beats_assigned: int
          - beats_in_output: int
          - dropped: list of person names absent from final text
          - found: list of person names present in final text
          - drop_causes: dict mapping dropped name → cause string
    """
    if not story_beats_per_stop or not complete_tour:
        return []

    gate_removed_set = set()
    if gate_removed_names:
        for name in gate_removed_names:
            gate_removed_set.add(name.lower())
            # Also track surname
            surname = name.split()[-1].lower() if name.split() else ''
            if surname:
                gate_removed_set.add(surname)

    stop_blocks = _split_tour_into_stop_blocks(complete_tour)
    results = []

    for idx, stop_beats in enumerate(story_beats_per_stop):
        stop_name = stop_names[idx] if idx < len(stop_names) else f'Stop {idx+1}'

        # Get the final text for this stop
        if idx < len(stop_blocks):
            final_text = stop_blocks[idx]
        else:
            final_text = ''

        # Also check the entire tour (a name might appear in a different stop)
        person_beats = [b for b in stop_beats if b['role'] not in ('circumstance', 'stakes')]

        if not person_beats:
            results.append({
                'beats_assigned': 0,
                'beats_in_output': 0,
                'dropped': [],
                'found': [],
                'drop_causes': {},
            })
            continue

        final_lower = final_text.lower()
        found = []
        dropped = []
        drop_causes = {}

        for beat in person_beats:
            person = beat['person']
            surname = person.split()[-1].lower()
            # Case-insensitive check against THIS stop's final text
            if surname in final_lower or person.lower() in final_lower:
                found.append(person)
            else:
                dropped.append(person)
                # Determine cause
                if person.lower() in gate_removed_set or surname in gate_removed_set:
                    drop_causes[person] = 'gate_removed'
                else:
                    drop_causes[person] = 'never_written'

        results.append({
            'beats_assigned': len(person_beats),
            'beats_in_output': len(found),
            'dropped': dropped,
            'found': found,
            'drop_causes': drop_causes,
        })

    return results


def scrub_unfilled_roles(
    description: str,
    stop_beats: List[Dict[str, str]],
) -> Tuple[str, int]:
    """[LOCAL-391] Replace 'with publisher' etc. with the actual person name when known.

    Where a role word appears without the person's name nearby, substitute the
    full person name. If the person cannot be identified from the beats, remove
    the clause entirely (an unfilled role is ungrammatical and wastes a beat).

    Returns (scrubbed_description, substitution_count).
    """
    if not description or not stop_beats:
        return (description, 0)

    # Build role→person map from beats
    role_person_map: Dict[str, str] = {}
    for beat in stop_beats:
        if beat['role'] in ('circumstance', 'stakes'):
            continue
        role = beat['role']
        person = beat['person']
        # Map both the role and common synonyms
        role_person_map[role] = person
        # Map the display word that appears in prose
        _role_word_map = {
            'publisher': 'publisher',
            'printer': 'printer',
            'donor': 'donor',
            'gallery_patron': 'patron',
            'collaborator': 'collaborator',
            'illustrator': 'illustrator',
            'author': 'author',
            'founder': 'founder',
            'editor': 'editor',
            'binder': 'binder',
        }
        prose_word = _role_word_map.get(role, role)
        if prose_word not in role_person_map:
            role_person_map[prose_word] = person

    sub_count = 0
    result = description

    # Pattern: "with publisher" / "with printer" / "the publisher" / "a donor"
    # Only replace when the person's surname is NOT already in the same sentence
    def _replace_if_unfilled(match):
        nonlocal sub_count
        prefix = match.group(1)  # 'with' / 'the' / 'a'
        role_word = match.group(2).lower()  # 'publisher' / 'printer' / etc.

        # Find the person for this role
        person = role_person_map.get(role_word)
        if not person:
            return match.group(0)  # No known person — leave as-is

        # Check if the person's surname is already in the surrounding sentence
        surname = person.split()[-1]
        # Get the sentence containing this match
        start = result.rfind('.', 0, match.start())
        end = result.find('.', match.end())
        sentence = result[max(0, start):end if end > 0 else len(result)]

        if surname.lower() in sentence.lower():
            # Person is already named in this sentence — leave the role word
            return match.group(0)

        # Replace "with publisher" → "with Louis Broder" (naming the person)
        sub_count += 1
        return f"{prefix} {person}"

    result = _UNFILLED_ROLE_PATTERN.sub(_replace_if_unfilled, result)
    return (result, sub_count)
