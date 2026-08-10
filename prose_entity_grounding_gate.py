#!/usr/bin/env python3
"""prose_entity_grounding_gate.py — LOCAL-378: Prose entity grounding gate.

When an exhibition-scoped museum tour is generated, the output may name persons
(artists, donors, critics, etc.) who do NOT appear on the exhibition checklist
page. These are fabrications — the model hallucinated a connection to the show.

This gate:
  1. Extracts person names from the delivered prose.
  2. Checks each against the exhibition page text (the grounding corpus).
  3. Once a person is judged ungrounded, removes EVERY mention — full name,
     bare surname, possessive — from the delivered text.
  4. Drops on sentence boundaries; if the remainder is a dangling fragment,
     drops that too.

Scope: fires ONLY for `tour_category == 'museum'` with a non-empty
`_exhibition_checklist_result` (i.e., exhibition-scoped tours). Unscoped
museum tours (Palais Lascaris, etc.) are NOT gated — stated explicitly per
task specification.

Design invariants:
  - No LLM calls. Entirely deterministic.
  - The gate never adds text, only removes.
  - Removal granularity: whole sentences on sentence boundaries.

LOCAL-385 additions:
  - GATED_PROSE_FIELDS: single source of truth for which POI fields both gates scan.
  - Both gates iterate all fields in GATED_PROSE_FIELDS (description, orientation).
  - Log messages include the field name: field=orientation, field=description.
  - Form-claim gate: metaphorical uses ("a visual tapestry") are exempt.
  - Empty orientation after removal triggers omission (field cleared).
"""
import re
from typing import Dict, List, Optional, Set, Tuple


# ═══════════════════════════════════════════════════════════════════════════════
# [LOCAL-385] GATED PROSE FIELDS — defined ONCE, consumed by BOTH gates.
# ═══════════════════════════════════════════════════════════════════════════════
# These are the POI dict keys that contain model-generated prose and therefore
# must be scanned by all truthfulness gates. Structured fields (Address,
# Coordinates, stop headings) are NOT included.
GATED_PROSE_FIELDS = ('description', 'orientation')


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWN NON-PERSON STRINGS
# ═══════════════════════════════════════════════════════════════════════════════
# Product features, UI labels, structural phrases that happen to be
# title-cased multi-word strings but are NOT personal names.

_KNOWN_NON_PERSON_STRINGS = {
    'the treat page',
    'treat page',
    'the museum',
    'the gallery',
    'the exhibition',
    'the collection',
    'the catalogue',
    'museum of fine arts',
    'fine arts',
    'stop number',
}

# ═══════════════════════════════════════════════════════════════════════════════
# PERSON NAME DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

# Multi-word capitalised name (the pattern that LOCAL-376 used)
_PERSON_MULTI_WORD = re.compile(
    r'\b([A-Z][a-zà-ÿ]+(?:\s+(?:de|du|von|van|di|del|la|le|les|des|d\'|l\')?'
    r'\s*[A-Z][a-zà-ÿ]+)+)\b'
)

# Words that cannot START a personal name — articles, demonstratives, prepositions
_NON_NAME_OPENERS = frozenset({
    'the', 'this', 'that', 'these', 'those', 'a', 'an', 'its', 'his', 'her',
    'our', 'your', 'their', 'my', 'some', 'any', 'each', 'every', 'all',
    'no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight',
    'nine', 'ten', 'at', 'in', 'on', 'by', 'to', 'for', 'with', 'from',
})

# Words that are NOT personal name parts — common nouns, adjectives, places
# that appear in title case at sentence start or in titles.
_NON_NAME_WORDS = frozenset({
    'museum', 'gallery', 'exhibition', 'collection', 'page', 'treat',
    'building', 'floor', 'room', 'hall', 'wing', 'tower', 'garden',
    'park', 'plaza', 'square', 'street', 'avenue', 'boulevard',
    'north', 'south', 'east', 'west', 'upper', 'lower',
    'modern', 'contemporary', 'ancient', 'new', 'old', 'grand',
    'national', 'international', 'royal', 'imperial', 'state',
    'art', 'arts', 'fine', 'visual', 'decorative', 'applied',
})


def _looks_like_person_name(candidate: str) -> bool:
    """Heuristic: does this multi-word string look like a personal name?

    Returns False for place names, institutional names, product strings, etc.
    A personal name has at least two words, each starting with a capital letter,
    and does NOT begin with a non-name opener word. At least one word must not
    be in the non-name vocabulary.
    """
    words = candidate.split()
    if len(words) < 2:
        return False

    # Check opener
    if words[0].lower() in _NON_NAME_OPENERS:
        return False

    # Check against known non-person strings
    if candidate.lower() in _KNOWN_NON_PERSON_STRINGS:
        return False

    # A personal name should have at least one word that is NOT a common noun/adj
    has_name_word = False
    for w in words:
        # Skip particles (de, du, von, etc.)
        if w.lower() in ('de', 'du', 'von', 'van', 'di', 'del', 'la', 'le',
                         'les', 'des', "d'", "l'"):
            continue
        if w.lower() not in _NON_NAME_WORDS:
            has_name_word = True
            break

    if not has_name_word:
        return False

    # Each significant word should start with a capital
    for w in words:
        if w.lower() in ('de', 'du', 'von', 'van', 'di', 'del', 'la', 'le',
                         'les', 'des', "d'", "l'"):
            continue
        if not w[0].isupper():
            return False

    return True


def extract_person_names(text: str) -> List[str]:
    """Extract all multi-word capitalised person names from text.

    Applies the _looks_like_person_name heuristic to filter false positives.
    Returns deduplicated list of names found.
    """
    names = []
    seen = set()
    for m in _PERSON_MULTI_WORD.finditer(text):
        candidate = m.group(1)
        if candidate in seen:
            continue
        seen.add(candidate)
        if _looks_like_person_name(candidate):
            names.append(candidate)
    return names


# ═══════════════════════════════════════════════════════════════════════════════
# GROUNDING CHECK
# ═══════════════════════════════════════════════════════════════════════════════

def _surname_from_full_name(full_name: str) -> str:
    """Extract the surname (last capitalised word) from a full name.

    For 'Xavier Lalanne' → 'Lalanne'
    For 'Henri de Toulouse-Lautrec' → 'Toulouse-Lautrec'  (skips particles)
    """
    words = full_name.split()
    particles = {'de', 'du', 'von', 'van', 'di', 'del', 'la', 'le', 'les', 'des'}
    # Walk backwards to find last non-particle word
    for w in reversed(words):
        if w.lower() not in particles:
            return w
    return words[-1] if words else ''


def check_person_grounded(person_name: str, page_text: str,
                          stop_artist_names: Optional[Set[str]] = None) -> bool:
    """Check if a person name appears in the exhibition page text.

    Also considers the stop's declared artist names as grounded (they came from
    the checklist extraction).

    Args:
        person_name: Full person name (e.g. 'Xavier Lalanne')
        page_text: Exhibition page text (the grounding corpus)
        stop_artist_names: Set of artist names from the exhibition checklist works

    Returns:
        True if the person is grounded (found in page text or checklist artists).
    """
    if not person_name or not page_text:
        return False

    # Normalise for search: case-insensitive
    page_lower = page_text.lower()
    name_lower = person_name.lower()

    # Check full name in page text
    if name_lower in page_lower:
        return True

    # Check surname in page text (word-boundary match)
    surname = _surname_from_full_name(person_name)
    if surname and len(surname) >= 3:
        # Word boundary check on the original-case page text to avoid
        # false positives on common short words
        pattern = r'\b' + re.escape(surname) + r'\b'
        if re.search(pattern, page_text, re.IGNORECASE):
            return True

    # Check against declared artist names from checklist
    if stop_artist_names:
        for artist in stop_artist_names:
            if not artist:
                continue
            # Full name match
            if name_lower == artist.lower():
                return True
            # Surname match
            artist_surname = _surname_from_full_name(artist)
            if surname and artist_surname and surname.lower() == artist_surname.lower():
                return True

    return False


# ═══════════════════════════════════════════════════════════════════════════════
# SENTENCE-LEVEL REMOVAL
# ═══════════════════════════════════════════════════════════════════════════════

def _split_sentences(text: str) -> List[str]:
    """Split text into sentences on sentence-ending punctuation boundaries."""
    # Split on sentence-ending punctuation followed by space + capital or end
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'])', text)
    return [s.strip() for s in parts if s.strip()]


def _mentions_person(sentence: str, full_name: str, surname: str) -> bool:
    """Check if a sentence mentions a person by full name or bare surname.

    Matches:
      - Full name: 'Xavier Lalanne'
      - Bare surname: 'Lalanne'
      - Possessive: "Lalanne's"
    All as whole-word matches (case-sensitive for surname).
    """
    # Full name (case-insensitive — may appear mid-sentence)
    if full_name.lower() in sentence.lower():
        return True

    # Bare surname with word boundary (case-sensitive — surnames are capitalised)
    if surname and len(surname) >= 3:
        # Match surname optionally followed by 's (possessive)
        pattern = r'\b' + re.escape(surname) + r"(?:'s)?\b"
        if re.search(pattern, sentence):
            return True

    return False


def _is_fragment(sentence: str) -> bool:
    """Detect if a sentence is a dangling fragment (not grammatically complete).

    A fragment is:
      - Starts with a coordinating conjunction following a deletion
      - Very short (< 5 words) and doesn't end with proper punctuation
      - Starts with a lowercase word (continuation of a previous sentence)
      - Starts with a dangling participle indicator
    """
    s = sentence.strip()
    if not s:
        return True

    # Starts with lowercase (was a continuation)
    if s[0].islower():
        return True

    # Starts with a coordinating conjunction (likely was connected to dropped text)
    if re.match(r'^(And|But|Or|Yet|So|Nor)\s', s):
        # Short conjunction-started sentences are likely fragments
        words = s.split()
        if len(words) < 6:
            return True

    # Very short without proper ending
    words = s.split()
    if len(words) < 4 and not s[-1] in '.!?':
        return True

    return False


def remove_person_from_text(text: str, full_name: str) -> Tuple[str, List[str]]:
    """Remove all sentences mentioning a person (by full name or surname) from text.

    Returns (cleaned_text, list_of_dropped_sentences).
    After removal, if the remaining text has dangling fragments, those are
    dropped too.
    """
    surname = _surname_from_full_name(full_name)
    sentences = _split_sentences(text)
    dropped = []
    kept = []

    for sent in sentences:
        if _mentions_person(sent, full_name, surname):
            dropped.append(sent)
        else:
            kept.append(sent)

    # Second pass: remove fragments left by deletions
    if dropped:
        final_kept = []
        for sent in kept:
            if _is_fragment(sent):
                dropped.append(sent)
            else:
                final_kept.append(sent)
        kept = final_kept

    cleaned = ' '.join(kept)
    return cleaned, dropped


# ═══════════════════════════════════════════════════════════════════════════════
# GATE ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def apply_prose_entity_grounding_gate(
    poi_list: List[Dict],
    exhibition_checklist_result,
    stop_names: Optional[List[str]] = None,
) -> Dict:
    """Apply the prose entity grounding gate to all stop prose fields.

    [LOCAL-385] Scans every field in GATED_PROSE_FIELDS (description AND
    orientation). For each stop, extract person names from the prose, check them
    against the exhibition page text and the declared artist names from the
    checklist. Remove all mentions of ungrounded persons.

    Args:
        poi_list: List of POI dicts (mutated in place — prose fields are rewritten).
        exhibition_checklist_result: ExhibitionChecklistResult with page_text and works.
        stop_names: List of stop names (excluded from person detection).

    Returns:
        Stats dict with counts of detections, drops, etc.
    """
    stats = {
        'persons_detected': 0,
        'persons_ungrounded': 0,
        'persons_grounded': 0,
        'sentences_dropped': 0,
        'stops_affected': 0,
        'ungrounded_names': [],
        'drop_log': [],  # [{stop, person, field, dropped_sentences}]
    }

    page_text = getattr(exhibition_checklist_result, 'page_text', '') or ''
    works = getattr(exhibition_checklist_result, 'works', None) or []

    # Build set of all artist names from checklist works
    artist_names: Set[str] = set()
    for work in works:
        artist = (work.get('artist') or '').strip()
        if artist:
            artist_names.add(artist)

    # Also consider stop names (the works on display) as context
    stop_name_set = set()
    if stop_names:
        for sn in stop_names:
            stop_name_set.add(sn.lower())
            for w in sn.split():
                if len(w) > 3:
                    stop_name_set.add(w.lower())

    # First pass: collect ALL ungrounded persons across all stops and ALL prose fields
    # (a person ungrounded in one stop is ungrounded everywhere)
    all_persons: Set[str] = set()
    ungrounded_persons: Set[str] = set()

    for poi in poi_list:
        for field_key in GATED_PROSE_FIELDS:
            text = poi.get(field_key, '') or ''
            if not text or text.startswith('['):
                continue

            persons = extract_person_names(text)
            for person in persons:
                # Skip if person's surname is a stop name word
                surname = _surname_from_full_name(person)
                if surname and surname.lower() in stop_name_set:
                    continue
                all_persons.add(person)

    stats['persons_detected'] = len(all_persons)

    # Check each person against the grounding corpus
    for person in all_persons:
        if check_person_grounded(person, page_text, artist_names):
            stats['persons_grounded'] += 1
        else:
            ungrounded_persons.add(person)
            stats['persons_ungrounded'] += 1
            stats['ungrounded_names'].append(person)
            print(f"  [LOCAL-385] ungrounded person '{person}' — will remove all mentions")

    if not ungrounded_persons:
        return stats

    # Second pass: remove all mentions of ungrounded persons from all stops,
    # scanning every field in GATED_PROSE_FIELDS
    for poi in poi_list:
        stop_name = poi.get('name', '?')
        stop_touched = False

        for field_key in GATED_PROSE_FIELDS:
            text = poi.get(field_key, '') or ''
            if not text or text.startswith('['):
                continue

            original_text = text
            field_drops = []

            for person in ungrounded_persons:
                text, dropped = remove_person_from_text(text, person)
                if dropped:
                    field_drops.extend(dropped)
                    for d in dropped:
                        print(f"  [LOCAL-385] field={field_key} stop='{stop_name[:30]}' "
                              f"ungrounded person '{person}' — dropping sentence"
                              + (f": \"{d[:80]}...\"" if len(d) > 80 else f": \"{d}\""))

            if text != original_text:
                # [LOCAL-385] If orientation is emptied, clear it entirely rather
                # than ship a fragment
                cleaned = text.strip()
                if field_key == 'orientation' and not cleaned:
                    poi[field_key] = ''
                    print(f"  [LOCAL-385] field=orientation stop='{stop_name[:30]}' "
                          f"emptied after person removal — omitting orientation")
                else:
                    poi[field_key] = cleaned
                stop_touched = True
                stats['sentences_dropped'] += len(field_drops)
                stats['drop_log'].append({
                    'stop': stop_name,
                    'field': field_key,
                    'persons': [p for p in ungrounded_persons
                                if any(_mentions_person(d, p, _surname_from_full_name(p))
                                       for d in field_drops)],
                    'dropped_sentences': field_drops,
                })

        if stop_touched:
            stats['stops_affected'] += 1

    return stats


# ═══════════════════════════════════════════════════════════════════════════════
# [LOCAL-384] FORM-CLAIM GATE
# ═══════════════════════════════════════════════════════════════════════════════
# The model repeatedly infers physical form from titles (e.g. "Au Soleil du
# Plafond" → "ceiling mural"). Five prompt-level rounds failed to stop it.
# This gate enforces at the output level: scan delivered text for physical
# form and placement claims, check against the known medium, remove sentences
# containing unsupported claims.
#
# Rules:
#   - medium KNOWN and INCOMPATIBLE → remove the sentence
#   - medium EMPTY/UNKNOWN → any form claim is unsupported → remove
#   - medium KNOWN and COMPATIBLE → keep (e.g. a real fresco in a palace)
#   - [LOCAL-385] Metaphorical use ("a visual tapestry") is EXEMPT
#
# [LOCAL-385] This gate now scans ALL fields in GATED_PROSE_FIELDS.
# This gate runs alongside the person gate, AFTER all generation and repair.
# ═══════════════════════════════════════════════════════════════════════════════

# Architectural surfaces — claims about WHERE or WHAT the work is physically
_FORM_SURFACE_TERMS = frozenset([
    'ceiling', 'wall', 'floor', 'vault', 'dome', 'canopy',
])

# Object-type claims — assertions about WHAT the work IS
_FORM_OBJECT_TERMS = frozenset([
    'mural', 'painting', 'sculpture', 'installation', 'panel', 'glass',
    'mosaic', 'fresco', 'tapestry', 'stained glass',
])

# Spatial instruction phrases — telling the visitor WHERE to look/stand
_FORM_SPATIAL_PHRASES = [
    'look up', 'gaze up', 'above you', 'stand beneath', 'overhead',
    'directly under', 'positioned above', 'looms above', 'rises above',
    'stretches across the ceiling', 'adorns the ceiling', 'painted on the ceiling',
    'mounted on the wall', 'hangs on the wall', 'affixed to the wall',
]

# Combined single-word terms for quick word-boundary regex scan
_ALL_FORM_SINGLE_TERMS = _FORM_SURFACE_TERMS | _FORM_OBJECT_TERMS

# Build regex patterns (case-insensitive)
_FORM_SINGLE_TERM_RE = re.compile(
    r'\b(' + '|'.join(re.escape(t) for t in sorted(_ALL_FORM_SINGLE_TERMS, key=len, reverse=True)) + r')\b',
    re.IGNORECASE
)

_FORM_SPATIAL_RE = re.compile(
    r'(' + '|'.join(re.escape(p) for p in sorted(_FORM_SPATIAL_PHRASES, key=len, reverse=True)) + r')',
    re.IGNORECASE
)

# ═══════════════════════════════════════════════════════════════════════════════
# [LOCAL-385] METAPHOR EXEMPTION
# ═══════════════════════════════════════════════════════════════════════════════
# A form term used metaphorically ("a visual tapestry", "a symphony of colour")
# is NOT a claim that the work IS that physical form. Only REFERENTIAL uses
# matter — "this ceiling mural", "the sculpture before you".
#
# Heuristic: if the form term is preceded by a metaphor qualifier (adjective that
# signals figurative use), the sentence is exempt. Also exempt when the term
# appears as part of a compound metaphor pattern.
# ═══════════════════════════════════════════════════════════════════════════════

# Metaphor qualifiers: adjectives/patterns that signal figurative use of a form term
_METAPHOR_QUALIFIER_RE = re.compile(
    r'\b(?:visual|sonic|auditory|emotional|musical|verbal|literary|poetic|'
    r'intellectual|cultural|historical|rich|vivid|intricate|complex|'
    r'sensory|dynamic|living|woven|elaborate)\s+(?=' +
    '|'.join(re.escape(t) for t in sorted(_ALL_FORM_SINGLE_TERMS, key=len, reverse=True)) +
    r')\b',
    re.IGNORECASE
)

# Full metaphor patterns: "a tapestry of X", "symphony of X" — figurative
_METAPHOR_COMPOUND_RE = re.compile(
    r'\b(?:a|the|this|creates?\s+a|weaves?\s+a|forms?\s+a|becomes?\s+a|like\s+a)\s+'
    r'(?:visual|sonic|auditory|rich|vivid|intricate|sensory|living|woven|elaborate)?\s*'
    r'(?:' + '|'.join(re.escape(t) for t in sorted(_ALL_FORM_SINGLE_TERMS, key=len, reverse=True)) + r')'
    r'\s+of\s+',
    re.IGNORECASE
)


def _is_metaphorical_use(sentence: str, term: str) -> bool:
    """Check if a form term is used metaphorically rather than referentially.

    Returns True if the term is a metaphor (should be KEPT), False if it's a
    literal claim about the work's physical form (subject to gate rules).

    A term is metaphorical when:
      - Preceded by a metaphor qualifier: "a visual tapestry", "rich mosaic"
      - Part of a compound metaphor: "a tapestry of emotions", "a mosaic of styles"
      - NOT preceded by referential indicators: "this", "the", demonstratives
        pointing to the work itself

    [LOCAL-385] D304: removing metaphor makes prose worse for no truthfulness gain.
    """
    term_lower = term.lower()

    # Check for qualifier pattern: "visual tapestry", "rich mosaic"
    if _METAPHOR_QUALIFIER_RE.search(sentence):
        return True

    # Check compound metaphor: "a tapestry of emotions/colours/..."
    if _METAPHOR_COMPOUND_RE.search(sentence):
        return True

    # Check if preceded by "a [adj] <term>" (indefinite article = metaphorical)
    # vs "this <term>" / "the <term> before you" (referential)
    _indefinite_metaphor = re.compile(
        r'\ba\s+(?:\w+\s+)?' + re.escape(term_lower) + r'\b',
        re.IGNORECASE
    )
    _referential_pattern = re.compile(
        r'\b(?:this|that|the|its)\s+(?:\w+\s+){0,2}' + re.escape(term_lower) + r'\b',
        re.IGNORECASE
    )

    has_referential = bool(_referential_pattern.search(sentence))
    has_indefinite = bool(_indefinite_metaphor.search(sentence))

    # If there's a referential use, it's a claim about the work → not metaphorical
    if has_referential:
        return False

    # "creates a tapestry", "weaves a tapestry" — action + indefinite = metaphor
    _action_metaphor = re.compile(
        r'\b(?:creates?|weaves?|forms?|paints?|builds?|crafts?|becomes?)\s+'
        r'(?:a\s+)?(?:\w+\s+)?' + re.escape(term_lower) + r'\b',
        re.IGNORECASE
    )
    if _action_metaphor.search(sentence):
        return True

    # If the indefinite article is present without a referential one,
    # and the sentence doesn't also say "this is a <term>" or "offers a <term>",
    # it's likely metaphorical
    if has_indefinite and not has_referential:
        # But check for "offers a <term>", "presents a <term>" — these could be
        # describing what the work IS
        _offers_pattern = re.compile(
            r'\b(?:offers?|presents?|features?|showcases?|displays?|reveals?)\s+'
            r'(?:a\s+)?(?:\w+\s+)?' + re.escape(term_lower) + r'\b',
            re.IGNORECASE
        )
        if _offers_pattern.search(sentence):
            return False
        return True

    return False


def _medium_compatible_with_term(medium: str, term: str) -> bool:
    """Check if a form/surface/spatial term is compatible with the known medium.

    A term is compatible if the medium itself references that term or a related
    concept.  E.g. medium="fresco" is compatible with "ceiling", "wall", "mural".
    Medium="oil on canvas" is compatible with "painting" but not "ceiling".
    Medium="ceiling fresco" is compatible with everything spatial.

    Returns True if the claim is legitimate given the medium.
    """
    if not medium:
        return False  # empty medium → nothing is compatible

    medium_lower = medium.lower()
    term_lower = term.lower()

    # Direct containment: if the medium literally says "ceiling", then "ceiling" is fine
    if term_lower in medium_lower:
        return True

    # Semantic compatibility groups: if medium mentions any member of the group,
    # all group members are compatible
    _COMPAT_GROUPS = [
        # Architectural/fresco group — if medium is a fresco or architectural element,
        # spatial claims are legitimate
        {'fresco', 'ceiling', 'wall', 'mural', 'vault', 'dome', 'canopy',
         'look up', 'gaze up', 'above you', 'stand beneath', 'overhead',
         'directly under', 'positioned above', 'looms above', 'rises above',
         'stretches across the ceiling', 'adorns the ceiling', 'painted on the ceiling'},
        # Painting group
        {'painting', 'oil', 'canvas', 'watercolor', 'acrylic', 'tempera', 'gouache'},
        # Sculpture group
        {'sculpture', 'bronze', 'marble', 'stone', 'carving', 'cast', 'statue'},
        # Glass group
        {'glass', 'stained glass', 'panel', 'window', 'mosaic'},
        # Wall-mounted group
        {'tapestry', 'mounted on the wall', 'hangs on the wall', 'affixed to the wall', 'wall'},
        # Installation group
        {'installation', 'mixed media', 'multimedia', 'video', 'light'},
    ]

    for group in _COMPAT_GROUPS:
        # If medium references any member of this group AND the term is in the group
        medium_in_group = any(member in medium_lower for member in group)
        term_in_group = term_lower in group
        if medium_in_group and term_in_group:
            return True

    return False


def _sentence_has_form_claim(sentence: str) -> Optional[str]:
    """Check if a sentence contains a physical form or placement claim.

    Returns the offending term/phrase if found, or None if clean.
    [LOCAL-385] Now checks metaphor exemption — returns None if the term is
    used metaphorically.
    """
    # Check spatial phrases first (multi-word, higher signal)
    m = _FORM_SPATIAL_RE.search(sentence)
    if m:
        phrase = m.group(1)
        # Spatial phrases are never metaphorical — they're always instructions
        return phrase

    # Check single-word form terms
    m = _FORM_SINGLE_TERM_RE.search(sentence)
    if m:
        term = m.group(1)
        # [LOCAL-385] Exempt metaphorical uses
        if _is_metaphorical_use(sentence, term):
            return None
        return term

    return None


def apply_form_claim_gate(
    poi_list: List[Dict],
    exhibition_checklist_result,
) -> Dict:
    """[LOCAL-384/385] Apply the form-claim gate to all stop prose fields.

    [LOCAL-385] Scans every field in GATED_PROSE_FIELDS (description AND
    orientation). For each stop, scan the delivered text for physical form and
    placement claims. Check each claim against the work's known medium. Remove
    sentences containing unsupported or incompatible claims.

    Metaphorical uses ("a visual tapestry", "creates a tapestry of colour")
    are exempt — D304 states removing metaphor costs prose quality with no
    truthfulness gain.

    This gate fires ONLY for exhibition-scoped museum tours (same scope as the
    person gate). Unscoped museum tours (e.g. Palais Lascaris) are NOT gated.

    Args:
        poi_list: List of POI dicts (mutated in place — prose fields are rewritten).
        exhibition_checklist_result: ExhibitionChecklistResult with works list.

    Returns:
        Stats dict with counts of detections, drops, etc.
    """
    stats = {
        'claims_detected': 0,
        'claims_removed': 0,
        'claims_kept': 0,
        'claims_metaphor_exempt': 0,
        'sentences_dropped': 0,
        'stops_affected': 0,
        'removal_log': [],  # [{stop, field, term, medium, sentence}]
    }

    works = getattr(exhibition_checklist_result, 'works', None) or []

    # Build a map of stop_name → medium from checklist works
    # We need to match each POI to its work to get the medium
    from generate_tour_text import match_work_for_stop

    for poi in poi_list:
        poi_name = poi.get('name', '') or ''
        stop_name = poi_name[:50]  # for logging

        # Find the matched work for this stop to get its medium
        matched_work = match_work_for_stop(poi_name, works) if poi_name and works else None
        medium = (matched_work.get('medium') or '').strip() if matched_work else ''

        stop_touched = False

        for field_key in GATED_PROSE_FIELDS:
            text = poi.get(field_key, '') or ''
            if not text or text.startswith('['):
                continue

            # Split into sentences and check each
            sentences = _split_sentences(text)
            kept = []
            dropped_this_field = []

            for sentence in sentences:
                claim_term = _sentence_has_form_claim(sentence)
                if claim_term is None:
                    # No form claim in this sentence (or metaphor exempt) — keep
                    kept.append(sentence)
                    continue

                stats['claims_detected'] += 1

                if medium and _medium_compatible_with_term(medium, claim_term):
                    # Medium known and compatible — keep
                    stats['claims_kept'] += 1
                    kept.append(sentence)
                else:
                    # Medium empty/unknown OR medium incompatible — remove
                    stats['claims_removed'] += 1
                    dropped_this_field.append(sentence)
                    stats['removal_log'].append({
                        'stop': stop_name,
                        'field': field_key,
                        'term': claim_term,
                        'medium': medium or 'UNKNOWN',
                        'sentence': sentence,
                    })
                    print(f"  [LOCAL-385] field={field_key} unsupported form claim "
                          f"'{claim_term}' for medium '{medium or 'UNKNOWN'}' — "
                          f"dropping sentence")

            if dropped_this_field:
                # Second pass: remove fragments left by deletions
                final_kept = []
                for sent in kept:
                    if _is_fragment(sent):
                        dropped_this_field.append(sent)
                        stats['sentences_dropped'] += 1
                    else:
                        final_kept.append(sent)

                stats['sentences_dropped'] += len(dropped_this_field)
                stop_touched = True

                new_text = ' '.join(final_kept).strip()

                # [LOCAL-385] If orientation is emptied, clear rather than ship broken
                if field_key == 'orientation' and not new_text:
                    poi[field_key] = ''
                    print(f"  [LOCAL-385] field=orientation stop='{stop_name[:30]}' "
                          f"emptied after form-claim removal — omitting orientation")
                else:
                    poi[field_key] = new_text

        if stop_touched:
            stats['stops_affected'] += 1

    return stats
