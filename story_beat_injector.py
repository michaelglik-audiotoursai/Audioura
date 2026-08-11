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
"""
import re
from typing import Dict, List, Optional, Tuple


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
            if person.lower() not in seen_people and len(person) > 3:
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
            if person.lower() not in seen_people and len(person) > 3:
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
            if person.lower() not in seen_people and len(person) > 3:
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
                if p.lower() not in seen_people and len(p) > 3:
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
            if person.lower() not in seen_people and len(person) > 3:
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
            if person.lower() not in seen_people and len(person) > 3:
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
    """Distribute story beats across stops.

    Each stop gets at least one beat (if possible). Beats are assigned
    based on relevance to the stop's matched work, then round-robin
    distributes remaining beats so EVERY stop receives at least one.

    [LOCAL-388] Fixed: previously all beats clustered on stop 0 because
    the relevance pass was too greedy. Now: at most 2 beats per stop in
    the relevance pass, then round-robin fills all bare stops, then any
    remaining beats are spread evenly.

    Args:
        beats: All extracted beats
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

    # First pass: assign beats that match a specific stop's work
    # [LOCAL-388] Cap at 1 relevance-matched beat per stop to prevent clustering
    assigned = [[] for _ in range(n_stops)]
    used_beat_indices = set()

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
                # [LOCAL-388] Stop after 1 relevance match per stop
                if len(assigned[i]) >= 1:
                    break
                person_lower = beat['person'].lower()
                # Match if person appears in work's publisher/collaborator/artist
                # [LOCAL-388] Guard against empty-string substring match
                if (person_lower and (
                    (work_publisher and person_lower in work_publisher) or
                    (work_collaborator and person_lower in work_collaborator) or
                    (work_artist and person_lower in work_artist) or
                    (work_publisher and work_publisher in person_lower) or
                    (work_collaborator and work_collaborator in person_lower)
                )):
                    assigned[i].append(beat)
                    used_beat_indices.add(j)

    # Second pass: round-robin ALL remaining person beats across ALL stops
    # [LOCAL-388] Fixed: distribute evenly so every stop gets at least one beat
    remaining_person = [b for j, b in enumerate(person_beats) if j not in used_beat_indices]
    if remaining_person:
        # First fill stops that have nothing yet
        bare_stops = [i for i in range(n_stops) if not assigned[i]]
        rr_idx = 0
        for i in bare_stops:
            if rr_idx >= len(remaining_person):
                break
            assigned[i].append(remaining_person[rr_idx])
            rr_idx += 1
        # Then distribute any leftovers to stops with fewest beats
        while rr_idx < len(remaining_person):
            # Find the stop with the fewest person beats
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

    # Third pass: ensure all stops have at least one beat
    # Use context beats (rarity, stakes) as fallback for bare stops, then reuse person beats
    for i in range(n_stops):
        if not assigned[i]:
            if context_beats:
                assigned[i].append(context_beats[i % len(context_beats)])
            elif person_beats:
                # Last resort: reuse a person beat (round-robin from all)
                assigned[i].append(person_beats[i % len(person_beats)])

    # Add context beats to first and last stops (they serve as framing)
    if context_beats:
        for cb in context_beats:
            if cb['role'] == 'stakes' and assigned[0]:
                assigned[0].insert(0, cb)
            elif cb['role'] == 'circumstance' and n_stops > 1:
                # Assign "rarely on view" to a middle stop
                mid = n_stops // 2
                assigned[mid].append(cb)

    return assigned


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
    context_beats = [b for b in stop_beats if b['role'] in ('circumstance', 'stakes')]

    parts = []
    parts.append("""
STORY BEAT REQUIREMENT (LOCAL-383):
Your description MUST contain at least one sentence that NAMES A PERSON and
states WHAT THEY DID — a specific action or circumstance, not a general claim.
This SUPPLEMENTS (does not replace) any exhibition framing or thesis instructions above.
The artists and collaborators named in EXHIBITION FRAMING must still appear.
""")

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
    if person_beats:
        _role_names = []
        for beat in person_beats[:3]:
            _role_names.append(f"'{beat['role'].replace('_', ' ')}' → use '{beat['person']}'")
        parts.append(
            "NEVER-PLACEHOLDER RULE (LOCAL-388): Do NOT write 'with publisher', "
            "'with printer', 'with donor', or 'the patron'. Where a role is mentioned, "
            "NAME THE PERSON. Specifically:\n  " + "\n  ".join(_role_names)
        )
        parts.append("")

    parts.append("""
WHAT IS NOT A STORY: "This masterpiece challenges boundaries" is not a story.
"Published by Louis Broder in Paris" IS a story — it names who and what they did.
A story has: a person, a specific circumstance, a consequence.
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
