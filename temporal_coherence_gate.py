"""[LOCAL-402] Temporal coherence gate — reject impossible temporal relations.

The prose entity grounding gate checks that *facts* are grounded (persons exist,
forms are correct). This gate checks *relations* — that claims about interactions
between people are temporally possible.

Defect (D328): "In 1974, Salvador Dalí collaborated with Freud" — Freud d.1939.
The grounding gate passed this because both Dalí and Freud are individually real.
The coherence check from LOCAL-400 did not fire because it tested facts in
isolation, not relations between them.

Design:
  1. Extract dated facts about persons from the retrieved snippet corpus.
  2. Scan the delivered prose for INTERACTION VERBS between named parties.
  3. Test whether the interaction is temporally possible given known dates.
  4. Reject sentences with impossible temporal relations.

Interaction verbs (bidirectional — both parties must be alive/active):
  collaborated with, worked with, met, partnered, together with,
  in dialogue with, corresponded with, alongside, joined with,
  commissioned by, assisted by

Non-interaction verbs (unidirectional — the acting party must be alive,
the referenced party need not be):
  illustrated (a book by), inspired by, influenced by, based on,
  dedicated to, in tribute to, in honor of, after (as in 'after Freud')
"""
import re
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# [LOCAL-405] Interaction patterns — match the RELATION, not just the surface verb.
#
# D334: "collaboration with" sailed past the gate because we only matched
# "collaborated with". The gate must catch verb, noun, and participle forms of
# every interaction word. Coverage:
#   collaborate → collaborated/collaborating/collaboration(s)
#   partner    → partnered/partnering/partnership(s)
#   meet       → met/meeting(s)/met with
#   work with  → worked with/working with/worked alongside/working alongside
#   correspond → corresponded/corresponding/correspondence
#   dialogue   → in dialogue with/dialogue(s) with/dialogue(s) between
#   join       → joined/joining/joint (project/work/effort/venture)
#   alongside  → standalone adverb near two names
#   together   → together with
#   commission → commissioned/commissioning/commission(s) by/from
#   co-author  → co-authored/co-authoring/co-author(s)
#   co-create  → co-created/co-creating/co-creation(s)
# ---------------------------------------------------------------------------

# Verbs/phrases that assert MUTUAL INTERACTION (both parties alive at the time)
_INTERACTION_PATTERNS = [
    # collaborate / collaboration / collaborating
    r'collaborat(?:ed|ing|ion|ions)\s+(?:with|between)',
    r'collaborat(?:ed|ing|ion|ions)\s+(?:of\s+)?\w+\s+(?:with|and)',
    # partner / partnership / partnering
    r'partner(?:ed|ing|ship|ships)\s+(?:with|between)',
    # meet / met / meeting(s) / met with
    r'\bmet\s+with',
    r'\bmet\b',
    r'\bmeeting(?:s)?\s+(?:with|between)',
    # work with / worked with / working with / worked alongside / working alongside
    r'work(?:ed|ing)\s+(?:with|alongside|together)',
    # correspond / correspondence / corresponding
    r'correspond(?:ed|ing|ence|ences)\s+(?:with|between)',
    # dialogue / in dialogue with
    r'(?:in\s+)?dialogue(?:s)?\s+(?:with|between)',
    # alongside (standalone — catches "X alongside Y")
    r'alongside\b',
    # together with
    r'together\s+with',
    # join / joined / joining / joint (project/work/effort/venture)
    r'join(?:ed|ing)\s+(?:with|forces)',
    r'\bjoint\s+(?:project|work|effort|venture|exhibition|creation)',
    # commission / commissioned / commissioning
    r'commission(?:ed|ing|s)?\s+(?:by|from)',
    # co-author / co-authored / co-authoring
    r'co-?author(?:ed|ing|s)?\s+(?:with|by)',
    # co-create / co-created / co-creating / co-creation
    r'co-?creat(?:ed|ing|ion|ions)\s+(?:with|by)',
]

_INTERACTION_RE = re.compile(
    r'(' + '|'.join(_INTERACTION_PATTERNS) + r')',
    re.IGNORECASE
)

# Year extraction from text
_YEAR_RE = re.compile(r'\b(1[4-9]\d{2}|20[0-2]\d)\b')

# Birth/death year patterns for extracting from snippets
# LOCAL-466: the abbreviation branches used to be `b\.?` and `d\.?` — an OPTIONAL
# period with `\s*` permitting zero width, so the final letter of any ordinary word
# before a year was read as a lifespan marker: "published 1887" → died 1887,
# "printed 1971" → died 1971, "Feb 1955" → born 1955. That is how the gate came to
# believe Juan Gris died in 1887 (his birth year) and threw away a true sentence.
# The period is now REQUIRED on the abbreviation and both branches are anchored on
# a word boundary, so `\bd\.` cannot match inside "published".
_BIRTH_PATTERNS = [
    re.compile(r'\b(?:born|b\.)\s*(?:in\s*)?(\d{4})', re.IGNORECASE),
    re.compile(r'\((\d{4})\s*[-–—]\s*(?:\d{4}|present)\)', re.IGNORECASE),  # (1856–1939)
    re.compile(r'(\d{4})\s*[-–—]\s*(?:\d{4}|present)', re.IGNORECASE),
]

_DEATH_PATTERNS = [
    re.compile(r'\b(?:died|d\.)\s*(?:in\s*)?(\d{4})', re.IGNORECASE),
    re.compile(r'\(\d{4}\s*[-–—]\s*(\d{4})\)', re.IGNORECASE),  # (1856–1939) → 1939
    re.compile(r'\d{4}\s*[-–—]\s*(\d{4})', re.IGNORECASE),
]

# LOCAL-466: a year governed by one of these is when the OBJECT was made public,
# not when the people worked together. Gris drew the lithographs for `Au Soleil du
# Plafond` before his death in 1927; Tériade published them in 1955. Reading 1955
# as the year of the collaboration made a true, documented partnership look
# chronologically impossible. Posthumous publication is normal in this corpus —
# livres d'artiste are the whole subject — so this is not an edge case.
_PUBLICATION_YEAR_RE = re.compile(
    r'\b(?:published|printed|issued|released|reissued|republished|exhibited|'
    r'shown|displayed|acquired|donated|bequeathed|catalogued)\b'
    r'[^.;]{0,40}?(\d{4})', re.IGNORECASE)

# Well-known dates for persons frequently appearing in this corpus
# (fallback when snippets don't carry dates explicitly)
_KNOWN_DATES: Dict[str, Dict[str, int]] = {
    'sigmund freud': {'birth': 1856, 'death': 1939},
    'freud': {'birth': 1856, 'death': 1939},
    'salvador dalí': {'birth': 1904, 'death': 1989},
    'dalí': {'birth': 1904, 'death': 1989},
    'dali': {'birth': 1904, 'death': 1989},
    'joan miró': {'birth': 1893, 'death': 1983},
    'miró': {'birth': 1893, 'death': 1983},
    'miro': {'birth': 1893, 'death': 1983},
    'pablo picasso': {'birth': 1881, 'death': 1973},
    'picasso': {'birth': 1881, 'death': 1973},
    'henri matisse': {'birth': 1869, 'death': 1954},
    'matisse': {'birth': 1869, 'death': 1954},
    'marc chagall': {'birth': 1887, 'death': 1985},
    'chagall': {'birth': 1887, 'death': 1985},
    'juan gris': {'birth': 1887, 'death': 1927},
    'gris': {'birth': 1887, 'death': 1927},
    'pierre reverdy': {'birth': 1889, 'death': 1960},
    'reverdy': {'birth': 1889, 'death': 1960},
    'louis broder': {'birth': 1906, 'death': 1971},
    'broder': {'birth': 1906, 'death': 1971},
    'fernand mourlot': {'birth': 1895, 'death': 1988},
    'mourlot': {'birth': 1895, 'death': 1988},
    'tériade': {'birth': 1897, 'death': 1983},
    'ambroise vollard': {'birth': 1866, 'death': 1939},
    'vollard': {'birth': 1866, 'death': 1939},
    'daniel-henry kahnweiler': {'birth': 1884, 'death': 1979},
    'kahnweiler': {'birth': 1884, 'death': 1979},
    'aimé maeght': {'birth': 1906, 'death': 1981},
    'maeght': {'birth': 1906, 'death': 1981},
    'moses': {'birth': -1400, 'death': -1200},  # Biblical figure
}


def extract_person_dates_from_snippets(
    snippets: List[Dict[str, str]],
    person_name: str,
) -> Optional[Dict[str, int]]:
    """Extract birth/death years for a person from SERP snippets.

    Searches snippet titles and texts for lifespan patterns near the person's name.
    Returns {'birth': YYYY, 'death': YYYY} or partial/None.
    """
    name_lower = person_name.lower()
    surname = person_name.split()[-1].lower() if person_name.split() else name_lower

    result = {}

    for snippet in snippets:
        text = f"{snippet.get('title', '')} {snippet.get('snippet', '')}"
        text_lower = text.lower()

        # Only look at snippets that mention this person
        if surname not in text_lower and name_lower not in text_lower:
            continue

        # Try birth patterns
        if 'birth' not in result:
            for pat in _BIRTH_PATTERNS:
                m = pat.search(text)
                if m:
                    year = int(m.group(1))
                    if 1200 <= year <= 2025:
                        result['birth'] = year
                        break

        # Try death patterns
        if 'death' not in result:
            for pat in _DEATH_PATTERNS:
                m = pat.search(text)
                if m:
                    year = int(m.group(1))
                    if 1200 <= year <= 2025:
                        result['death'] = year
                        break

    return result if result else None


def get_person_dates(
    person_name: str,
    snippets: Optional[List[Dict[str, str]]] = None,
) -> Optional[Dict[str, int]]:
    """Get birth/death dates for a person: snippets first, table filling the gaps.

    LOCAL-466: this used to RETURN the snippet result the moment it was non-empty,
    so a snippet yielding only `{'birth': 1887}` shadowed the table's correct
    `{'birth': 1887, 'death': 1927}` for Juan Gris. Partial evidence outranked a
    known answer, and the missing death year is exactly what the coherence check
    reads. The two sources are now MERGED, with the snippet winning per-field
    where it actually has a value — live evidence still beats a stale table, but
    it can no longer erase what it does not mention.
    """
    from_snippets = {}
    if snippets:
        from_snippets = extract_person_dates_from_snippets(snippets, person_name) or {}

    known = None
    name_lower = person_name.lower().strip()
    if name_lower in _KNOWN_DATES:
        known = _KNOWN_DATES[name_lower]
    else:
        surname = person_name.split()[-1].lower() if person_name.split() else ''
        if surname and surname in _KNOWN_DATES:
            known = _KNOWN_DATES[surname]

    if not from_snippets and not known:
        return None

    merged = dict(known or {})
    merged.update(from_snippets)
    return merged


def _extract_persons_from_sentence(sentence: str) -> List[str]:
    """Extract likely person names from a sentence.

    Uses capitalized word sequences (2+ words starting with uppercase) as candidates.
    Also catches single surnames preceded by interaction verbs.
    """
    # Unicode-aware character classes for accented names (Dalí, Miró, Tériade, etc.)
    _LC = r'[a-záàâäãåæçéèêëíìîïñóòôöõøúùûüýÿ]'
    _UC = r'[A-ZÁÀÂÄÃÅÆÇÉÈÊËÍÌÎÏÑÓÒÔÖÕØÚÙÛÜÝ]'

    # Multi-word capitalized names (e.g. "Salvador Dalí", "Joan Miró")
    _multi_pattern = rf'(?:^|(?<=[\s,;:(]))({_UC}{_LC}+(?:\s+{_UC}{_LC}+)+)'
    names = re.findall(_multi_pattern, sentence)

    # Single-word proper nouns (common in art context: "Dalí", "Freud", "Mourlot")
    _single_pattern = rf'(?:^|(?<=[\s,;:(]))({_UC}{_LC}{{2,}})'
    single_caps = re.findall(_single_pattern, sentence)

    # Filter out sentence starters and common words
    _common_words = {'The', 'This', 'That', 'These', 'Their', 'Through', 'Throughout',
                     'During', 'Between', 'Within', 'Before', 'After', 'Under', 'Over',
                     'While', 'When', 'Where', 'Which', 'Whether', 'Although', 'However',
                     'Indeed', 'Perhaps', 'Meanwhile', 'Furthermore', 'Moreover', 'Finally',
                     'Initially', 'Originally', 'Additionally', 'Subsequently', 'Ultimately',
                     'Published', 'Printed', 'Created', 'Designed', 'Produced', 'Written',
                     'According', 'Despite'}
    # Track last words of multi-word names to avoid duplicates
    multi_name_last_words = set()
    for n in names:
        multi_name_last_words.add(n.split()[-1])

    for word in single_caps:
        if word not in _common_words and word not in multi_name_last_words:
            names.append(word)

    return names


def check_temporal_coherence(
    sentence: str,
    snippets: Optional[List[Dict[str, str]]] = None,
    event_year: Optional[int] = None,
) -> Optional[Dict[str, str]]:
    """Check a single sentence for impossible temporal relations.

    Args:
        sentence: The prose sentence to check
        snippets: Available SERP snippets (for date extraction)
        event_year: An explicit year mentioned in or near the sentence

    Returns:
        None if sentence is coherent, or a dict with:
          - 'sentence': the offending sentence
          - 'reason': human-readable explanation
          - 'person_a': first party
          - 'person_b': second party (if applicable)
          - 'dates': date evidence string
    """
    # 1. Does the sentence contain an interaction verb?
    interaction_match = _INTERACTION_RE.search(sentence)
    if not interaction_match:
        return None

    interaction_verb = interaction_match.group(0)

    # 2. Extract person names from the sentence
    persons = _extract_persons_from_sentence(sentence)
    if len(persons) < 2:
        # Need at least two parties for a temporal relation check
        # But also check for single person + implicit "with X" reference
        return None

    # 3. Extract or infer the event year from the sentence.
    #
    # LOCAL-466: a publication year is NOT the year the people interacted. The
    # gate used to take the first year in the sentence and test it against the
    # death dates, which rejected
    #   '"Au Soleil du Plafond," created by Juan Gris in collaboration with
    #    Pierre Reverdy, was published in 1955'
    # as impossible because Gris died in 1927 — a true claim about a posthumously
    # published livre d'artiste. When the only year present is governed by a
    # publication verb we have no evidence about WHEN they collaborated, and
    # under D450 knowing nothing is not a rejection.
    # [LOCAL-471] Bind the year to the VERB, not to the sentence. This used to take
    # the first year anywhere in the sentence, which rejected three of eight stories
    # in round 4 of the iteration chart — all true, all with the meeting dated in
    # the same breath:
    #
    #   "Created in 1974-75, this set of ten drypoints ... captures Dalí's
    #    fascination with Freud, whom he met only once in 1938."
    #
    # 1974 is when the artwork was made; 1938 is when they met, and it is right
    # there next to the verb. Two dates in one sentence is not an edge case — it is
    # the normal shape whenever a work made at one time refers to an event at
    # another, which is most of an exhibition. The year nearest the interaction verb
    # is the one that dates it.
    if event_year is None:
        verb_pos = interaction_match.start()
        candidates = []
        for m in _YEAR_RE.finditer(sentence):
            y = int(m.group(1))
            pub = _PUBLICATION_YEAR_RE.search(sentence)
            # D466: a year governed by a publication verb dates the object, not the
            # people. Skip it here too, so it cannot win on proximity alone.
            if pub and int(pub.group(1)) == y:
                continue
            candidates.append((abs(m.start() - verb_pos), y))
        if candidates:
            event_year = min(candidates)[1]

    # 4. For each pair of persons, check temporal feasibility
    for i in range(len(persons)):
        for j in range(i + 1, len(persons)):
            person_a = persons[i]
            person_b = persons[j]

            dates_a = get_person_dates(person_a, snippets)
            dates_b = get_person_dates(person_b, snippets)

            if not dates_a and not dates_b:
                continue  # Can't check without dates

            # [LOCAL-473] An ancient or mythological figure is a SUBJECT, not a
            # collaborator. The D472 release run rejected a true sentence about
            # "Dalí's illustrations for Moses and Monotheism" with
            #   'Moses' died in -1200, cannot have collaboration with in 1974
            # Nobody has ever claimed Dalí collaborated with Moses; the name is in
            # the work's TITLE. This gate exists to catch an impossible interaction
            # between real contemporaries — a three-thousand-year gap is a category
            # error, not a factual one, and reporting it as a falsehood is exactly
            # how a gate throws away a true sentence. Same class as the `World War`
            # and `Maresfield Gardens` misreadings of D447/D449.
            if any(d and d.get('death') is not None and d['death'] < 1000
                   for d in (dates_a, dates_b)):
                continue

            # Check: if we have an event year, was either party dead?
            if event_year:
                if dates_a and dates_a.get('death') and event_year > dates_a['death']:
                    return {
                        'sentence': sentence,
                        'reason': f"'{person_a}' died in {dates_a['death']}, "
                                  f"cannot have {interaction_verb} in {event_year}",
                        'person_a': person_a,
                        'person_b': person_b,
                        'dates': f"{person_a} d.{dates_a['death']}, event {event_year}",
                    }
                if dates_b and dates_b.get('death') and event_year > dates_b['death']:
                    return {
                        'sentence': sentence,
                        'reason': f"'{person_b}' died in {dates_b['death']}, "
                                  f"cannot have {interaction_verb} in {event_year}",
                        'person_a': person_a,
                        'person_b': person_b,
                        'dates': f"{person_b} d.{dates_b['death']}, event {event_year}",
                    }

            # Check: even without an explicit year, if one party died before
            # the other was born, interaction is impossible
            if dates_a and dates_b:
                death_a = dates_a.get('death')
                birth_b = dates_b.get('birth')
                death_b = dates_b.get('death')
                birth_a = dates_a.get('birth')

                if death_a and birth_b and death_a < birth_b:
                    return {
                        'sentence': sentence,
                        'reason': f"'{person_a}' died in {death_a}, "
                                  f"'{person_b}' born in {birth_b} — "
                                  f"cannot have {interaction_verb}",
                        'person_a': person_a,
                        'person_b': person_b,
                        'dates': f"{person_a} d.{death_a}, {person_b} b.{birth_b}",
                    }
                if death_b and birth_a and death_b < birth_a:
                    return {
                        'sentence': sentence,
                        'reason': f"'{person_b}' died in {death_b}, "
                                  f"'{person_a}' born in {birth_a} — "
                                  f"cannot have {interaction_verb}",
                        'person_a': person_a,
                        'person_b': person_b,
                        'dates': f"{person_b} d.{death_b}, {person_a} b.{birth_a}",
                    }

    return None


def apply_temporal_coherence_gate(
    poi_list: List[Dict],
    snippets_per_stop: Optional[Dict[str, List[Dict[str, str]]]] = None,
) -> Dict:
    """Apply temporal coherence gate to all stops in a tour.

    Scans each stop's description for sentences with impossible temporal relations
    and removes them.

    Args:
        poi_list: List of stop dicts (modified in place — sentences removed)
        snippets_per_stop: Optional dict mapping stop name → list of SERP snippets

    Returns:
        Stats dict with:
          - relations_checked: int
          - relations_rejected: int
          - sentences_removed: int
          - stops_affected: int
          - rejection_log: list of rejection detail dicts
    """
    stats = {
        'relations_checked': 0,
        'relations_rejected': 0,
        'sentences_removed': 0,
        'stops_affected': 0,
        'rejection_log': [],
    }

    stops_affected = set()

    # Fields to scan (same as other gates)
    _GATED_FIELDS = ['description', 'orientation']

    for poi in poi_list:
        poi_name = poi.get('name', '')
        stop_snippets = (snippets_per_stop or {}).get(poi_name, [])

        # [LOCAL-405] Extract the work/stop year as contextual event_year.
        # If the sentence doesn't carry an explicit date, the work's own date
        # provides the temporal context (e.g. a 1974 livre d'artiste cannot
        # describe a collaboration with someone who died in 1939).
        _poi_year_str = poi.get('year', '') or ''
        _poi_year_match = _YEAR_RE.search(str(_poi_year_str))
        _poi_event_year: Optional[int] = int(_poi_year_match.group(1)) if _poi_year_match else None

        for field in _GATED_FIELDS:
            text = poi.get(field, '')
            if not text:
                continue

            # Split into sentences
            sentences = re.split(r'(?<=[.!?])\s+', text)
            kept_sentences = []
            removed_any = False

            for sentence in sentences:
                stats['relations_checked'] += 1
                rejection = check_temporal_coherence(
                    sentence, snippets=stop_snippets,
                    event_year=_poi_event_year,
                )

                if rejection:
                    stats['relations_rejected'] += 1
                    stats['sentences_removed'] += 1
                    removed_any = True
                    stops_affected.add(poi_name)

                    log_entry = {
                        'stop': poi_name,
                        'field': field,
                        'sentence': sentence[:120],
                        'reason': rejection['reason'],
                        'person_a': rejection['person_a'],
                        'person_b': rejection['person_b'],
                        'dates': rejection['dates'],
                    }
                    stats['rejection_log'].append(log_entry)

                    # LOG EVERY REJECTION (the defect was silence)
                    print(f"  [LOCAL-402] coherence reject: '{sentence[:80]}' — {rejection['reason']}")
                else:
                    kept_sentences.append(sentence)

            if removed_any:
                poi[field] = ' '.join(kept_sentences)

    stats['stops_affected'] = len(stops_affected)
    return stats
