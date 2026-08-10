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
"""
import re
from typing import Dict, List, Optional, Set, Tuple


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
    """Apply the prose entity grounding gate to all stop descriptions.

    For each stop, extract person names from the description, check them against
    the exhibition page text and the declared artist names from the checklist.
    Remove all mentions of ungrounded persons.

    Args:
        poi_list: List of POI dicts (mutated in place — descriptions are rewritten).
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
        'drop_log': [],  # [{stop, person, dropped_sentences}]
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

    # First pass: collect ALL ungrounded persons across all stops
    # (a person ungrounded in one stop is ungrounded everywhere)
    all_persons: Set[str] = set()
    ungrounded_persons: Set[str] = set()

    for poi in poi_list:
        desc = poi.get('description', '') or ''
        if not desc or desc.startswith('['):
            continue

        persons = extract_person_names(desc)
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
            print(f"  [LOCAL-378] ungrounded person '{person}' — will remove all mentions")

    if not ungrounded_persons:
        return stats

    # Second pass: remove all mentions of ungrounded persons from all stops
    for poi in poi_list:
        desc = poi.get('description', '') or ''
        if not desc or desc.startswith('['):
            continue

        stop_name = poi.get('name', '?')
        original_desc = desc
        stop_drops = []

        for person in ungrounded_persons:
            desc, dropped = remove_person_from_text(desc, person)
            if dropped:
                stop_drops.extend(dropped)
                for d in dropped:
                    print(f"  [LOCAL-378] stop='{stop_name[:30]}' dropped for "
                          f"'{person}': \"{d[:80]}...\"" if len(d) > 80
                          else f"  [LOCAL-378] stop='{stop_name[:30]}' dropped for "
                          f"'{person}': \"{d}\"")

        if desc != original_desc:
            poi['description'] = desc
            stats['stops_affected'] += 1
            stats['sentences_dropped'] += len(stop_drops)
            stats['drop_log'].append({
                'stop': stop_name,
                'persons': [p for p in ungrounded_persons
                            if any(_mentions_person(d, p, _surname_from_full_name(p))
                                   for d in stop_drops)],
                'dropped_sentences': stop_drops,
            })

    return stats
