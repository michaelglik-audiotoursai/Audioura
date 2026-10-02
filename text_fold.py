#!/usr/bin/env python3
"""text_fold.py — the one accent-folding and entity-matching helper.

D243 has now been hit six times: a French title, an artist's name or a publisher
is compared against a corpus with an exact or a `.lower()` match, the accents do
not line up, and the gate reports ABSENT for something that is plainly present.
Each occurrence was fixed in place, in one function, and the next one appeared
somewhere else a week later.

Measured 2026-08-18, on the code as it stood:

    check_person_grounded('Salvador Dali', "...Salvador Dalí...")  -> False
    _agent_in_text('Editions Verve', "...Éditions Verve...")       -> False
    _fold_org (the org gate, LOCAL-479)                            -> folds

Three sibling gates in the same chain, asking the same question about the same
corpus, and only the newest one got it right. That is not three bugs; it is one
missing primitive. This module is the primitive.

Two functions, and everything that asks "is this entity in that text?" should
call the second one:

    fold(s)                      -> accent-stripped, lowercased, space-collapsed
    contains_entity(hay, needle) -> fold both, then match on word boundaries

`contains_entity` defaults to whole-word matching because the substring form has
its own failure mode, also measured: `_agent_in_text('Ars', 'Arsenal Gallery')`
returned True, grounding a fabricated agent on an unrelated word. A gate that
accepts too easily is as wrong as one that rejects too easily; it just fails
quietly instead of loudly.
"""
import re
import unicodedata
from typing import Optional

__all__ = ['fold', 'contains_entity', 'entity_pattern', 'is_placeholder',
           'PLACEHOLDER_VALUES']

# [LOCAL-491 r3] Values a museum record uses to mean "we do not know". They are
# strings, so every naive `if field:` treats them as data.
#
# This lives here, next to `fold`, for the same reason `fold` does. Two modules
# written the same night — `story_worthiness` and `story_focus_fact` — each grew
# its own version of this list and they disagreed: worthiness accepted
# "Not specified" as a named agent, focus-fact rejected it. The visible cost was
# a focus fact reading
#     "Not specified published Moses and Monotheism."
# handed to the story pass, which produced the incoherent
#     "The Hogarth Press, the Louis Broder of Freud's original text".
#
# That is D483's exact defect class, committed inside the session that fixed
# D483. Which is the argument for the primitive, not against it: the list is only
# safe when there is one of it.
PLACEHOLDER_VALUES = frozenset({
    '', '-', '--', 'n a', 'na', 'nil', 'none', 'null',
    'not specified', 'not stated', 'not known', 'not available', 'not applicable',
    'unspecified', 'unknown', 'undetermined', 'unattributed', 'unidentified',
    'various', 'anonymous', 'tbd', 'tba', 'no data', 'no information',
})


def is_placeholder(value: Optional[str]) -> bool:
    """Does this field say "we do not know" rather than carry a value?

    Punctuation is normalised to spaces before comparison, so `n/a`, `n.a.`,
    `N-A` and `n a` are one answer rather than four entries. Enumerating the
    spellings is what produced this bug in the first place — the set had `n a`
    and `na` and not `n/a`, and `n/a` sailed through as a publisher's name.
    Normalise, then compare; do not extend the list.
    """
    folded = fold(value)
    if folded in PLACEHOLDER_VALUES:
        return True
    normalised = re.sub(r'\s+', ' ', re.sub(r'[^\w\s]+', ' ', folded)).strip()
    return normalised in PLACEHOLDER_VALUES


def fold(s: Optional[str]) -> str:
    """Accent-strip, lowercase and collapse whitespace.

    'Éditions  Verve' -> 'editions verve'
    'Joan Miró'       -> 'joan miro'
    None / ''         -> ''

    NFD then drop combining marks, so this handles both the precomposed form
    (U+00E9) and the decomposed one (e + U+0301) that arrive from different
    scrapers for the same French word.
    """
    if not s:
        return ''
    decomposed = unicodedata.normalize('NFD', str(s).lower())
    stripped = ''.join(c for c in decomposed if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', stripped).strip()


def entity_pattern(entity: str, possessive: bool = True) -> Optional[re.Pattern]:
    """Compile a folded, whole-word pattern for `entity`.

    Internal whitespace is made flexible (`\\s+`) so 'Editions  Verve' in the
    corpus still matches 'Editions Verve' in the claim. The possessive tail is
    optional and on by default — museum prose writes "Dali's etchings" far more
    often than it writes the bare surname.

    Returns None for an entity that folds to nothing (punctuation, whitespace).
    """
    folded = fold(entity)
    if not folded:
        return None
    parts = [re.escape(p) for p in folded.split(' ') if p]
    if not parts:
        return None
    body = r'\s+'.join(parts)
    tail = r"(?:'s)?" if possessive else ''
    # \b is unreliable when the entity starts or ends with a non-word character
    # (e.g. an initial "&"), so guard with an explicit non-word lookaround.
    return re.compile(r'(?<!\w)' + body + tail + r'(?!\w)')


def contains_entity(haystack: Optional[str], entity: Optional[str],
                    whole_word: bool = True, possessive: bool = True) -> bool:
    """Is `entity` present in `haystack`, ignoring accents and case?

    whole_word=True (the default) requires word boundaries, so 'Ars' does not
    match 'Arsenal'. Pass whole_word=False only where a substring really is the
    question — it almost never is for a name.
    """
    if not haystack or not entity:
        return False
    folded_hay = fold(haystack)
    if not folded_hay:
        return False
    if not whole_word:
        folded_needle = fold(entity)
        return bool(folded_needle) and folded_needle in folded_hay
    pattern = entity_pattern(entity, possessive=possessive)
    if pattern is None:
        return False
    return bool(pattern.search(folded_hay))
