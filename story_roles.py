#!/usr/bin/env python3
"""story_roles.py — D500: the three agents a story can be about.

Michael, 2026-08-20:

    "We should strive to get all information for all types of tour where artist
     is the hero, publisher is the sponsor, and printer is the builder for all
     tours. In this particular exhibition these names really lexicographically
     correlate ... but for a restaurant tour publisher would be either owner or
     investor/sponsor, and printer is the printer in this exhibition but for a
     historic tour it can be an architect."

**Why this is not cosmetic renaming.** A story needs an AGENT — Prince's middle
event requires someone who ACTS (D493, LOCAL-495). Today the matrix has exactly
one reliably-filled agent slot, `artist`, and two that are usually empty:
`publisher` and `printed_by`. So when the generator is asked for a story about a
change and who caused it, there is frequently only one candidate in the room, and
often that candidate did nothing but exist.

Three roles, because they are the three ways a thing comes to be:

    HERO      who made it            the imagination
    SPONSOR   who paid for or willed it   the decision
    BUILDER   who physically realised it  the craft

The livre d'artiste happens to name these artist / publisher / printer, which is
why the museum vocabulary reads like the general one. It is not general: on a
restaurant tour the sponsor is an owner or an investor; on a historic site the
builder is an architect or an engineer. `printed_by` as a universal matrix slot
is a livre-d'artiste field that a walking tour can never fill, which is a large
part of why it has been empty in every production run ever made.

**Additive by design.** The matrix keeps its existing slots and `story_pass`
keeps reading them. This module maps those slots onto roles per category, so the
prompt can ask for an agent by what it DID rather than by a trade name.
"""
from typing import Dict, List, Optional, Tuple

from text_fold import is_placeholder

__all__ = ['HERO', 'SPONSOR', 'BUILDER', 'ROLES', 'ROLE_FIELDS',
           'fields_for_role', 'roles_in', 'describe_role']

HERO = 'hero'
SPONSOR = 'sponsor'
BUILDER = 'builder'
ROLES = (HERO, SPONSOR, BUILDER)

# What each role is FOR, in the words the prompt will use. Deliberately about the
# act, not the job title — "the one who decided it should exist" is answerable on
# a restaurant tour; "publisher" is not.
_ROLE_GLOSS = {
    HERO:    'the one whose work this is — who made or created it',
    SPONSOR: 'the one who decided it should exist, or paid for it, or gave it',
    BUILDER: 'the one who physically made it — the hands, the workshop, the trade',
}

# Category → role → matrix fields, most specific first. A field may serve two
# roles (a donor is a sponsor; on some works the artist is also the builder) and
# that is allowed: `roles_in` reports the first field that actually carries a
# value, so a shared field never invents a second agent.
#
# `_default` is what an unknown category gets. It is not empty — an unmapped
# category must still be able to name a hero — and it deliberately contains only
# fields that exist on every stop.
ROLE_FIELDS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    'museum': {
        HERO:    ('artist', 'creator', 'maker'),
        SPONSOR: ('publisher', 'donor', 'patron', 'commissioned_by', 'credit_line'),
        BUILDER: ('printed_by', 'printer', 'atelier', 'workshop', 'foundry'),
    },
    'restaurant': {
        HERO:    ('chef', 'artist'),
        SPONSOR: ('owner', 'investor', 'founder', 'publisher'),
        BUILDER: ('kitchen', 'builder'),
    },
    'walking': {
        HERO:    ('architect', 'designer', 'artist'),
        SPONSOR: ('patron', 'commissioned_by', 'founder', 'publisher'),
        BUILDER: ('builder', 'engineer', 'mason', 'contractor', 'printed_by'),
    },
    'specialized': {
        HERO:    ('artist', 'creator', 'designer'),
        SPONSOR: ('publisher', 'patron', 'owner', 'founder'),
        BUILDER: ('builder', 'engineer', 'printed_by'),
    },
    '_default': {
        HERO:    ('artist', 'creator'),
        SPONSOR: ('publisher', 'patron', 'credit_line'),
        BUILDER: ('printed_by', 'printer', 'builder'),
    },
}


def fields_for_role(role: str, category: str = '') -> Tuple[str, ...]:
    """Which matrix fields can carry this role on this kind of tour."""
    table = ROLE_FIELDS.get((category or '').strip().lower(),
                            ROLE_FIELDS['_default'])
    return table.get(role, ())


def describe_role(role: str) -> str:
    return _ROLE_GLOSS.get(role, '')


def roles_in(matrix: Dict, category: str = '') -> Dict[str, Optional[Dict]]:
    """Which of the three agents does this stop actually have?

    Returns {role: {'field': str, 'value': str} or None}.

    A placeholder is NOT an agent (D500) — "Not specified" filled three slots on
    stop 2 of the 08-20 baseline. Neither is a value already claimed by an
    earlier role: if the only sponsor candidate is the same string as the hero,
    the stop has one agent, not two, and reporting two is how a "story" ends up
    being one person described twice.
    """
    found: Dict[str, Optional[Dict]] = {}
    claimed: List[str] = []
    for role in ROLES:
        hit = None
        for field in fields_for_role(role, category):
            value = (matrix.get(field) or '').strip()
            if not value or is_placeholder(value):
                continue
            if any(value.lower() == c.lower() for c in claimed):
                continue
            hit = {'field': field, 'value': value}
            claimed.append(value)
            break
        found[role] = hit
    return found


def summarise(matrix: Dict, category: str = '') -> str:
    """One log line: which agents this stop can build a story around."""
    found = roles_in(matrix, category)
    parts = []
    for role in ROLES:
        hit = found[role]
        parts.append(f"{role}={hit['value'][:28]} ({hit['field']})" if hit
                     else f"{role}=—")
    n = sum(1 for r in ROLES if found[r])
    return f"[D500] agents {n}/3: " + ', '.join(parts)
