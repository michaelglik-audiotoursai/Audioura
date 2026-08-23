#!/usr/bin/env python3
"""story_publish_gate.py — D510: publish a story, or publish nothing.

**NAME.** This was briefly written to `story_gate.py`, which ALREADY EXISTS as a
741-line LOCAL-439 module (`classify_story_unit`, `score_story_interest`,
`verify_tour_stories`) imported by `story_first.py`, `story_selection.py` and
`variance_harness.py`. Writing over it silently destroyed a production module and
would have broken tour generation at import. Restored from `c49e89f`; this file
takes a name nothing else uses. Two modules can both be "the gate" — one gates a
SENTENCE as a story-unit, this one gates a FINISHED STORY for publication.

Michael, 2026-08-22, replacing permute-and-select with iterate-to-threshold:

    "We should not use all permutations per stop and then select the best one;
     instead we should evaluate the actual story coming up from a number of
     iterations, and once it achieves a certain score we should use that story.
     That saves speed and money."

**The gate is two keys, not one score**, and the reason is measured. Across the
37 D509 stories:

    kind          n     valuation index  min / mean / max
    eventful     10          59 / 64 / 70
    active       16          38 / 51 / 70
    inert/none   11          10 / 49 / 74

Moses 6.1 scores **74 — the highest of all 37 — and is `inert`**: Freud
published, Dalí illustrated, 300 copies on glove leather. Facts, no event. The
index cannot see the difference, so `eventful` is mandatory and the index is a
second key rather than the key.

**Thresholds, approved 2026-08-22:**

    material kind        eventful          mandatory
    valuation index      >= 60             the eventful floor is 59
    confirmed claims     >= 3              below that the story is mostly assertion
    unattested in text   0                 SOFT until page-fetch is proven

**`unattested = 0` is deliberately soft for now**, and this is Michael's ruling
rather than a compromise LEAD chose:

    "Until then, don't enforce unattested=0 as hard fail — log only, because
     false negatives are from truncation, not invention."

D510 fixed the truncation (bare `<div>` content was invisible to `_fetch_page`,
so the Christie's Lot Essay never reached the adjudicator). Once a run shows
page-fetch supplying the evidence, `STORY_GATE_STRICT=1` makes it a hard key.

**Length by score**, his rule: 3 sentences at >=60, 5 at >=70, more than 5 only
at >=80 AND with a disagreement told — the extra length has to be earned by the
most interesting thing we produce.

**When nothing passes, publish nothing.** His ruling, and it is right: a stop
with no story is a retrieval failure to be fixed upstream, not a reason to lower
the bar. Le Lézard produced 0 of 16 `eventful` in D509 while its one real story
sat in a page we were not reading.
"""
import os
from typing import Dict, List, Optional

__all__ = ['evaluate', 'first_passing', 'allowed_sentences',
           'MIN_INDEX', 'MIN_CONFIRMED']

MIN_INDEX = int(os.environ.get('STORY_GATE_MIN_INDEX', '60'))
MIN_CONFIRMED = int(os.environ.get('STORY_GATE_MIN_CONFIRMED', '3'))
STRICT = os.environ.get('STORY_GATE_STRICT', '0').strip() == '1'

_LEN_TIERS = ((80, 8), (70, 5), (60, 3))


def allowed_sentences(index: Optional[int], tells_disagreement: bool) -> int:
    """How long this story has earned the right to be."""
    idx = index or 0
    for threshold, n in _LEN_TIERS:
        if idx >= threshold:
            # Above 5 sentences requires a told disagreement as well as the
            # score — the extra length is for the disagreement, not for padding.
            if n > 5 and not tells_disagreement:
                return 5
            return n
    return 0


def evaluate(story: Dict) -> Dict:
    """Does this story pass? -> {'passes', 'keys', 'failed', 'max_sentences'}

    `story` needs: story_kind, index, counts{CONFIRMED,...}, tells_disagreement,
    and optionally the delivered text for the length check.
    """
    counts = story.get('counts') or {}
    kind = story.get('story_kind', 'none')
    index = story.get('index')
    confirmed = counts.get('CONFIRMED', 0) + counts.get('CORRECTED', 0)
    unattested = counts.get('UNATTESTED', 0)

    keys = {
        'eventful': kind == 'eventful',
        'index': (index or 0) >= MIN_INDEX,
        'confirmed': confirmed >= MIN_CONFIRMED,
        'no_unattested': unattested == 0,
    }
    # The soft key does not decide the verdict unless STRICT.
    hard = ['eventful', 'index', 'confirmed'] + (['no_unattested'] if STRICT else [])
    failed = [k for k in hard if not keys[k]]

    return {
        'passes': not failed,
        'keys': keys,
        'failed': failed,
        'unattested': unattested,
        'confirmed': confirmed,
        'soft_warning': (None if keys['no_unattested'] else
                         f'{unattested} unattested claim(s) — '
                         f'{"BLOCKING" if STRICT else "logged only, not blocking"}'),
        'max_sentences': allowed_sentences(index,
                                           bool(story.get('tells_disagreement'))),
    }


def first_passing(stories: List[Dict]) -> Dict:
    """Iterate in the order given; stop at the first story that passes.

    Returns {'chosen', 'index_of', 'evaluated', 'spent'} where `spent` counts
    how many candidates were examined — the number the stopping rule exists to
    reduce. On the D509 data Au Soleil passes on its FIRST credit_line, so 11 of
    its 12 rounds were waste.
    """
    evaluated = []
    for i, s in enumerate(stories):
        verdict = evaluate(s)
        evaluated.append({'id': s.get('id'), 'verdict': verdict})
        if verdict['passes']:
            return {'chosen': s, 'index_of': i, 'evaluated': evaluated,
                    'spent': i + 1}
    return {'chosen': None, 'index_of': -1, 'evaluated': evaluated,
            'spent': len(stories)}
