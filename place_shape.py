#!/usr/bin/env python3
"""place_shape.py — LOCAL-481. A stop name must denote a place you can stand at.

Tour 423 (Logan Airport, 2026-09-15) shipped four stops. One was a real place;
three were not places at all:

    Boston Bruins Bar                  — a real, mapped bar. Keep.
    Art Exhibits at Logan Airport      — a CATEGORY, not an instance. Which
                                         exhibit? Where? You cannot stand at it.
    Boston Logan Airport Virtual Tour  — a FORMAT. Not a physical location.
    Boston Logan Airport History Walk  — a route/concept, not a point.

A listener told to walk to "Boston Logan Airport Virtual Tour" has been sent
nowhere. LOCAL-480 decides what KIND of thing a stop should be for a venue; this
is the layer underneath — whatever kind it is, it must be a real, named, findable
place with its own coordinate.

This is DETERMINISTIC on purpose. Whether a name is a category or a format is a
fact about the words, in the same spirit as D536's waypoint rule — and D526/D528
record what happens when a rule of this shape is handed to a model instead. Two
failing shapes, both present in 423:

  1. A CATEGORY standing in for an instance. The tell is a PLURAL head noun (or an
     uncountable-collection word) followed by a CONTAINING preposition and a
     place: "Art Exhibits at Logan Airport", "Restaurants in Nice", "Museums of
     the Old Town". A specific instance names itself ("Musée Matisse"), not its
     genus and its container.

  2. A NON-PHYSICAL CONCEPT — a FORMAT the generator named as a destination:
     "Virtual Tour", "History Walk", "Audio Guide", "Self-Guided Tour",
     "Timeline". These are how a tour is DELIVERED, not somewhere you go.

CONSERVATIVE BY DESIGN. Flagging a real place is a bounce (see the Cimiez
acceptance list). Every rule here fires only on an unambiguous shape:

  * A proper singular name is never a category, even with a preposition —
    "Arc de Triomphe", "Cathedral of Notre-Dame", "Museum of Modern Art",
    "Statue of Liberty" all survive, because the head noun is singular. Only a
    PLURAL/collection head triggers the category rule.
  * A format word triggers rejection only when it is the semantic HEAD of the
    name (the tour's own medium), not merely mentioned — "Freedom Trail" is a
    real named trail and survives; "History Walk" does not, because "Walk" is
    the head and "History" is a topic, not a proper name.

REPAIR OVER DELETION. This module only CLASSIFIES. The caller decides: if the
corpus can name a specific instance inside the category, substitute it; otherwise
drop the stop and let the replenishment loop (D558) refill the count. That loop
exists for exactly this.
"""
import re
import unicodedata


def _fold(s):
    """Accent-fold + lowercase, collapse whitespace. Matches scope_memory._fold
    so 'Musée' and 'Musee' classify identically (D243)."""
    n = unicodedata.normalize('NFKD', (s or '').lower())
    n = ''.join(c for c in n if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', n).strip()


# ── Format words: the tour's own medium named as a destination ──────────────────
#
# These are FORMATS, not places. They reject only when they are the HEAD of the
# name — the last significant word — so a proper name that merely contains one
# survives ("Freedom Trail" the real trail vs "History Walk" the format).
_FORMAT_HEADS = {
    'tour', 'walk', 'guide', 'timeline', 'itinerary', 'route', 'trail',
    'walkthrough', 'overview', 'introduction', 'orientation', 'experience',
    'highlights', 'sampler', 'crawl', 'loop', 'circuit', 'expedition',
}

# A format head is only damning when qualified as a MEDIUM, not a proper place.
# "Virtual Tour", "Self-Guided Tour", "Audio Guide", "History Walk",
# "Walking Tour" — the qualifier marks it as a way of touring, not a place.
# "Freedom Trail", "Cliff Walk", "Appalachian Trail" are proper names and are NOT
# caught, because their qualifier is a proper/topographic name, not a medium.
_MEDIUM_QUALIFIERS = {
    'virtual', 'self', 'self-guided', 'selfguided', 'guided', 'audio', 'walking',
    'driving', 'biking', 'cycling', 'history', 'historical', 'heritage', 'scenic',
    'sightseeing', 'introductory', 'general', 'complete', 'grand', 'full',
    'digital', 'online', 'interactive', 'multimedia', 'photo', 'shopping',
    'food', 'culinary', 'tasting',
}

# Standalone non-place phrases — a format with no place at all, common enough to
# name outright. Matched on the whole folded name.
_STANDALONE_NONPLACE = {
    'virtual tour', 'audio guide', 'audio tour', 'self-guided tour',
    'self guided tour', 'guided tour', 'walking tour', 'driving tour',
    'history walk', 'historical walk', 'heritage walk', 'timeline',
    'photo opportunity', 'photo op', 'rest stop', 'meeting point',
    'starting point', 'end point', 'welcome', 'introduction', 'orientation',
    'overview', 'conclusion', 'q&a', 'question and answer',
}

# ── Category head nouns: a genus standing in for an instance ─────────────────────
#
# A collection word that, plural or as an uncountable group, names a KIND rather
# than a specific place. The category rule fires when one of these is the head and
# a CONTAINING preposition + place follows.
_CATEGORY_HEADS = {
    'exhibits', 'exhibitions', 'displays', 'galleries', 'museums', 'restaurants',
    'cafes', 'cafés', 'bars', 'pubs', 'shops', 'stores', 'boutiques', 'markets',
    'churches', 'temples', 'mosques', 'monuments', 'statues', 'sculptures',
    'artworks', 'artefacts', 'artifacts', 'landmarks', 'sights', 'sites',
    'attractions', 'gardens', 'parks', 'squares', 'plazas', 'fountains',
    'buildings', 'houses', 'mansions', 'villas', 'towers', 'bridges', 'gates',
    'ruins', 'temples', 'palaces', 'theatres', 'theaters', 'cinemas', 'hotels',
    'streets', 'avenues', 'boulevards', 'neighborhoods', 'neighbourhoods',
    'districts', 'quarters', 'venues', 'stalls', 'vendors', 'eateries',
    'bistros', 'brasseries', 'wineries', 'breweries', 'bakeries', 'artists',
    'works', 'pieces', 'collections', 'highlights', 'points of interest',
}

# Containing prepositions: "<category> at/in/of/around/near <place>".
_CONTAINER_PREP = re.compile(
    r'\b(at|in|on|of|by|around|near|within|inside|throughout|across|along|of the)\b',
    re.IGNORECASE)

# "ruins" is a plural noun that legitimately heads real place names ("Roman Ruins
# of Cemenelum" is one specific archaeological site). A short allowlist of proper
# forms keeps those from tripping the category rule. Kept minimal and matched as a
# whole folded name.
_CATEGORY_EXCEPTIONS = {
    'roman ruins of cemenelum',
}


def _significant_tokens(folded_name):
    """Tokens with punctuation stripped, empty dropped."""
    return [t for t in re.split(r'[\s,]+', re.sub(r"[^\w\s-]", ' ', folded_name)) if t]


def is_nonplace_format(name):
    """True when the name is a tour FORMAT rather than a place.

    Returns (True, reason) or (False, '')."""
    folded = _fold(name)
    if not folded:
        return True, "empty stop name"

    if folded in _STANDALONE_NONPLACE:
        return True, f"'{name}' is a tour format, not a place (standalone non-place)"

    toks = _significant_tokens(folded)
    if not toks:
        return True, "stop name has no words"

    head = toks[-1]
    if head in _FORMAT_HEADS:
        # The head is a format word. It is only damning as a MEDIUM: a preceding
        # medium qualifier, OR no proper qualifier at all (a bare "Tour").
        prev = toks[-2] if len(toks) >= 2 else ''
        # join possible hyphenated qualifier like "self-guided"
        joined_prev = folded.split(head)[0].strip().split(' ')[-1] if len(toks) >= 2 else ''
        if len(toks) == 1:
            return True, f"'{name}' is a bare format word ('{head}'), not a place"
        if prev in _MEDIUM_QUALIFIERS or joined_prev in _MEDIUM_QUALIFIERS:
            return (True,
                    f"'{name}' names a tour format ('{prev} {head}'), not a physical place")
    return False, ''


def is_category_label(name):
    """True when the name is a CATEGORY (genus + container) not an instance.

    "Art Exhibits at Logan Airport" — plural head 'exhibits' + 'at' + a place.
    Returns (True, reason) or (False, '')."""
    folded = _fold(name)
    if not folded:
        return False, ''
    if folded in _CATEGORY_EXCEPTIONS:
        return False, ''

    toks = _significant_tokens(folded)
    if len(toks) < 2:
        return False, ''

    # Find a category head noun anywhere before a containing preposition. The head
    # must be a plural/collection word (in _CATEGORY_HEADS); a singular head
    # ("Museum of Modern Art") is a proper name, not a category.
    prep_m = _CONTAINER_PREP.search(folded)
    if not prep_m:
        return False, ''

    before = folded[:prep_m.start()].strip()
    before_toks = _significant_tokens(before)
    if not before_toks:
        return False, ''

    # Multi-word category phrase like "points of interest".
    if before in _CATEGORY_HEADS:
        head = before
    else:
        head = before_toks[-1]

    if head in _CATEGORY_HEADS:
        after = folded[prep_m.end():].strip()
        if after:      # there is a containing place
            return (True,
                    f"'{name}' is a category ('{head}') inside a place, not a specific "
                    f"stop — which {head[:-1] if head.endswith('s') else head}?")
    return False, ''


def classify_stop_name(name):
    """The single verdict for a stop name. Returns a dict::

        {"is_place": bool, "shape": "place"|"format"|"category", "reason": str}

    A name is not a place if it is a non-physical format OR a category label.
    Everything else is treated as a place (conservative — a real singular proper
    name always passes).
    """
    bad_format, why_format = is_nonplace_format(name)
    if bad_format:
        return {"is_place": False, "shape": "format", "reason": why_format}
    bad_cat, why_cat = is_category_label(name)
    if bad_cat:
        return {"is_place": False, "shape": "category", "reason": why_cat}
    return {"is_place": True, "shape": "place", "reason": "names a specific place"}


def is_a_place(name):
    """Convenience boolean. True when the name denotes a place you can stand at."""
    return classify_stop_name(name)["is_place"]
