#!/usr/bin/env python3
"""story_worthiness.py — LOCAL-486: Michael's step 2.

    "2. We analyze the tour stops and determine that some of them would benefit
        from stories."

Never implemented. Every museum stop is mined at full cost — 3–6 SERP queries
plus snippet ranking plus a story pass — whether or not it has anything a story
could be built from.

**This is a COST lever, not a quality lever, and the distinction decides the
design.** A wrong "yes" wastes a few cents. A wrong "no" silently costs a story
on a stop that had one, and nothing downstream will ever reveal it. So the bar is
deliberately asymmetric: **a stop is mined unless it has essentially nothing.**
This is not the place for a clever threshold.

WHAT IT JUDGES. Michael's own matrix, from step 3: `canonical_title`,
`english_title`, `artist`, `publisher`, `credit_line`, printed-by, `medium`,
`venue`. His methodology is Fact → Stop → Exhibition, and every one of those
chains starts from a **named agent** or a **specific fact** in that matrix. A stop
carrying neither cannot produce a story, and the queries that go looking will come
back with the generic page-furniture we then have to gate out anyway.

WHAT IT DOES NOT JUDGE. Not the generated prose — that is
`story_opportunity_scan`, which answers a different question ("does this draft
already contain a story?") at a different time (after generation). The two are
deliberately kept apart, and `agreement_report` below cross-checks them, because
two instruments answering near-identical questions and never being compared is
the exact shape of D469, D482 and D483.
"""
import os
import re
from typing import Dict, List, Optional

from text_fold import fold, is_placeholder

__all__ = ['assess_stop_worthiness', 'WORTHINESS_DISABLED_ENV', 'agreement_report']

WORTHINESS_DISABLED_ENV = 'DISABLE_STORY_WORTHINESS'

# Titles that name a category rather than a work. A stop called "Gallery 3" or
# "Introduction" has no work to hang a fact on.
_GENERIC_TITLE = re.compile(
    r'^(gallery|room|hall|wing|floor|introduction|orientation|entrance|lobby|'
    r'welcome|overview|exit|corridor|landing|stairs?|atrium)\b', re.IGNORECASE)

# A credit line that is pure boilerplate carries no fact to chase.
_BOILERPLATE_CREDIT = re.compile(
    r'^(gift of|museum purchase|bequest of|lent by|promised gift|'
    r'anonymous (gift|loan)|collection of the museum)[\s.,]*$', re.IGNORECASE)


def _has_named_agent(matrix: Dict) -> bool:
    """Is there a person or organisation to build a Fact → Stop chain from?"""
    for field in ('artist', 'publisher', 'printer', 'printed_by'):
        value = (matrix.get(field) or '').strip()
        # [LOCAL-491 r3] Was a private four-item tuple that did not include
        # 'not specified' — the commonest of them all in MFA records. Shared
        # primitive now, so this module and story_focus_fact cannot disagree
        # about what a named agent is (they did, and it shipped).
        if value and len(value) >= 3 and not is_placeholder(value):
            return True
    return False


def _credit_line_carries_a_fact(matrix: Dict) -> bool:
    """A credit line is a fact source unless it is pure donor boilerplate."""
    credit = (matrix.get('credit_line') or '').strip()
    if len(credit) < 12:
        return False
    if _BOILERPLATE_CREDIT.match(credit):
        return False
    return True


def _medium_is_specific(matrix: Dict) -> bool:
    """'Illustrated book with 40 color lithographs' is a fact. 'Mixed media' is not."""
    medium = (matrix.get('medium') or '').strip()
    if len(medium) < 6:
        return False
    return not is_placeholder(medium) and fold(medium) != 'mixed media'


def _title_is_specific(matrix: Dict) -> bool:
    title = (matrix.get('canonical_title') or matrix.get('name') or '').strip()
    if len(title) < 4:
        return False
    return not _GENERIC_TITLE.match(title)


def assess_stop_worthiness(matrix: Dict) -> Dict:
    """Would this stop benefit from story mining?

    Returns {'worth_mining': bool, 'score': int 0-4, 'why': str, 'signals': dict}.

    Scored on four independent signals. **A stop is mined on ANY one of them**;
    only a stop with zero is skipped. That threshold is the asymmetry described in
    the module docstring, written down as a number so it is visible when someone
    later wants to tighten it: tightening it trades money for stories, and needs
    the A/B that D484 sizes at 15 runs per arm.
    """
    if os.environ.get(WORTHINESS_DISABLED_ENV, '').strip() == '1':
        return {'worth_mining': True, 'score': -1, 'why': 'worthiness check disabled',
                'signals': {}, 'disabled': True}

    signals = {
        'named_agent': _has_named_agent(matrix),
        'credit_line_fact': _credit_line_carries_a_fact(matrix),
        'specific_medium': _medium_is_specific(matrix),
        'specific_title': _title_is_specific(matrix),
    }
    score = sum(1 for v in signals.values() if v)

    if score == 0:
        why = ("no named agent, no credit-line fact, no specific medium and no "
               "specific title — there is nothing for a Fact → Stop → Exhibition "
               "chain to start from")
    else:
        present = [k for k, v in signals.items() if v]
        why = f"has {', '.join(present)}"

    return {'worth_mining': score > 0, 'score': score, 'why': why,
            'signals': signals, 'disabled': False}


def agreement_report(pre_decisions: List[Dict], post_verdicts: List[Dict]) -> Dict:
    """Cross-check step 2's PRE-mining call against the POST-draft scan.

    Mission item 3 (2026-08-18 17:0x): cross-check pairs of instruments that
    should agree. These two do not answer the same question — one predicts from
    material, the other observes the result — so disagreement is not automatically
    a bug. But the interesting cell is **mined and still storyless**, which is
    money spent for nothing, and it is invisible unless somebody lines the two up.

    Returns counts per cell plus `wasted`, the count of that cell.
    """
    cells = {'mined_and_story': 0, 'mined_no_story': 0,
             'skipped_and_story': 0, 'skipped_no_story': 0}
    for pre, post in zip(pre_decisions or [], post_verdicts or []):
        mined = bool((pre or {}).get('worth_mining'))
        # `needs_additional_story` True means the draft did NOT end up with one.
        got_story = not bool((post or {}).get('needs_additional_story', True))
        key = ('mined_' if mined else 'skipped_') + ('and_story' if got_story else 'no_story')
        cells[key] = cells.get(key, 0) + 1
    cells['wasted'] = cells['mined_no_story']
    # A skipped stop that somehow produced a story means the bar is too strict.
    cells['bar_too_strict'] = cells['skipped_and_story']
    return cells
