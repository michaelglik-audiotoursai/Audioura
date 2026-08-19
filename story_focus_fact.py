#!/usr/bin/env python3
"""story_focus_fact.py — LOCAL-491: Michael's step 7, the rotation.

    "7. From all validated valid stories we pick the most valuable ... If there
        are no valid stories, we go to the next fact make it credit_line in our
        matrix and repeat from #4."

Production did the opposite. PHASE 5.17 fed the REJECTED claim back as a
prohibition — "do not say this again" — and asked for another draft on the same
subject. That is a retry, not a rotation, and D476 recorded what it produced: the
model nominalised the verb and shipped the same falsehood in a form the gate
could not see. Telling a model what NOT to write leaves it exactly where it was.

Rotation is different in kind: **change the subject.** Take the next fact off the
matrix, make it the focus, and ask again. The model is not being asked to avoid
something; it is being pointed somewhere else.

**Why not `credit_line`, which is what Michael said.** LOCAL-406 regex-parses
`donor` and `printer` out of that field. A fact written into `credit_line` is
read downstream as a person's name, so writing "the 1967 edition was destroyed"
there would produce a donor called "The 1967 Edition". The slot has to be its
own; the lab calls it `focus_fact` (`STORY_BASELINE.md` §2) and `story_pass.py`
already reads that key. This module supplies it.

**Ordering is the whole design.** The facts are tried most-promising first,
because each rotation costs a generation call and the budget is one or two per
stop, not eight. "Most promising" means: a named agent beats a bare date, a
specific medium beats a venue, and anything already tried is skipped.
"""
import re
from typing import Dict, List, Optional, Set

from text_fold import fold

__all__ = ['candidate_facts', 'next_focus_fact', 'MAX_ROTATIONS']

# One rotation per stop by default. Each costs a full generation; two stops
# rotating twice is a doubled tour bill. Raising it is a cost decision and wants
# the A/B D484 sizes at 15 runs per arm.
MAX_ROTATIONS = 1


def _clean(v: Optional[str]) -> str:
    return re.sub(r'\s+', ' ', (v or '')).strip()


def candidate_facts(matrix: Dict, material: Optional[List[str]] = None) -> List[Dict]:
    """The facts this stop could build a story on, best first.

    Each entry is {'key', 'fact', 'why'} — `fact` is the sentence handed to the
    story pass as its focus, `why` is for the log so a rotation is explicable
    afterwards rather than mysterious.

    Ordered by how often each kind of fact has actually produced a story in this
    exhibition's material: a named human agent first (Broder, Mourlot, Fridman —
    every story Michael has approved has one), then the physical specifics, then
    the institutional context. A date alone is last; a year with nobody attached
    to it is what produced the temporal-gate fabrications of D466 and D471.
    """
    title = _clean(matrix.get('english_title') or matrix.get('canonical_title'))
    out: List[Dict] = []

    def add(key, fact, why):
        if fact and len(fact) > 3:
            out.append({'key': key, 'fact': fact, 'why': why})

    publisher = _clean(matrix.get('publisher'))
    printer = _clean(matrix.get('printed_by') or matrix.get('printer'))
    artist = _clean(matrix.get('artist'))
    credit = _clean(matrix.get('credit_line'))
    medium = _clean(matrix.get('medium'))
    venue = _clean(matrix.get('venue_name'))

    if publisher:
        add('publisher', f'{publisher} published {title}.'.strip(),
            'a publisher is a person who decided to make this happen')
    if printer and printer != publisher:
        add('printed_by', f'{printer} printed {title}.'.strip(),
            'a printing house is a workshop where people worked together')
    if credit:
        # The donor inside the credit line is a person with a reason, which the
        # credit line itself does not state — that gap is the story.
        donor = re.sub(r'^(gift|bequest|loan|promised gift)\s+of\s+', '', credit,
                       flags=re.IGNORECASE).split(',')[0].strip()
        if donor and len(donor) > 4:
            add('donor', f'{donor} gave {title} to {venue or "the museum"}.'.strip(),
                'a donor chose this work and chose this museum')
    if artist:
        add('artist', f'{artist} made {title}.'.strip(),
            'the maker, when no other agent is available')
    if medium:
        add('medium', f'{title} is {medium}.'.strip(),
            'how it was physically made — a process involves people')
    if venue:
        add('venue', f'{title} is held at {venue}.'.strip(),
            'institutional context; weakest, but it scopes the search')

    return out


def next_focus_fact(matrix: Dict, tried: Optional[Set[str]] = None,
                    material: Optional[List[str]] = None) -> Optional[Dict]:
    """The next fact to point the story pass at, or None when exhausted.

    `tried` holds the KEYS already used for this stop. Comparison is on the key,
    not the sentence, so a reworded fact cannot be silently re-tried — the same
    accent-and-spelling trap D243 has sprung nine times, avoided here by not
    comparing prose at all.
    """
    used = {fold(t) for t in (tried or set())}
    for cand in candidate_facts(matrix, material):
        if fold(cand['key']) in used:
            continue
        return cand
    return None
