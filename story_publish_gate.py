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

# ─── [D515] Michael's rule, 2026-08-23 ────────────────────────────────────────
#
#   "if none of the stories on a stop pass, but the index is more than 50 —
#    accept with the highest index. If a story passes with index 50+, then this
#    is the story and we do not need to verify more. The only reason for not
#    accepting/fail should be positively identified as factual wrong events."
#
# This reverses the ruling this module was built on ("when nothing passes,
# publish nothing" — A214/D485), and Michael has asked to test it rather than
# adopt it: `STORY_GATE_D515=0` restores the old behaviour exactly.
#
# Three parts, in the order he stated them:
#
#   ACCEPT     a candidate scoring >= 50 with no positively-identified error is
#              published, and iteration STOPS there — no further candidates are
#              bought. `eventful` and `confirmed >= 3` still decide PREFERENCE,
#              they no longer decide admission.
#   FALLBACK   if nothing was accepted, the highest-index candidate above 50 is
#              published anyway.
#   VETO       a positively identified factual error, or an invented person,
#              blocks regardless of score. This is the only hard fail.
#
# The cost consequence is real and worth stating: under the old gate a stop with
# no eventful candidate bought all four and published nothing. Under this rule it
# usually stops at the first candidate — cheaper — but when it does not, it now
# pays for all four AND publishes. Nothing here can spend more than the old cap.
D515 = os.environ.get('STORY_GATE_D515', '1').strip() == '1'
D515_ACCEPT_INDEX = int(os.environ.get('STORY_GATE_D515_INDEX', '50'))

_LEN_TIERS = ((80, 8), (70, 5), (60, 3))


def allowed_sentences(index: Optional[int], tells_disagreement: bool) -> int:
    """How long this story has earned the right to be."""
    idx = index or 0
    # [D515] Without a tier at the new floor, a story accepted at 50–59 would be
    # trimmed to zero sentences and published as nothing — the rule would look
    # like it accepted and deliver silence. Three sentences, the same as 60.
    tiers = _LEN_TIERS + ((D515_ACCEPT_INDEX, 3),) if D515 else _LEN_TIERS
    for threshold, n in tiers:
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

    # [D515] Errors are the only hard fail; the score is the only admission test.
    errors = list(story.get('factual_errors') or [])
    invented = list(story.get('ungrounded') or [])
    keys['no_factual_error'] = not errors
    keys['no_invented_person'] = not invented
    keys['index_d515'] = (index or 0) >= D515_ACCEPT_INDEX

    if D515:
        d515_failed = [k for k in ('no_factual_error', 'no_invented_person',
                                   'index_d515') if not keys[k]]
        return {
            'passes': not d515_failed,
            'keys': keys,
            'failed': d515_failed,
            # What the OLD gate would have said, kept so every run can be read
            # both ways while the rule is on trial.
            'legacy_passes': not failed,
            'legacy_failed': failed,
            'factual_errors': errors,
            'ungrounded': invented,
            'preferred': not failed,          # eventful + 60 + confirmed >= 3
            'unattested': unattested,
            'confirmed': confirmed,
            'soft_warning': (None if keys['no_unattested'] else
                             f'{unattested} unattested claim(s) — not blocking (D515)'),
            'max_sentences': allowed_sentences(index,
                                               bool(story.get('tells_disagreement'))),
        }

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


def best_of(candidates: List[Dict]) -> Optional[Dict]:
    """[D515] The fallback: nothing was accepted, so take the best above 50.

    `candidates` are the loop's own dicts — each needs `index`, `gate`, and
    ideally `kind`. A candidate carrying a positively identified factual error or
    an invented person is never eligible, however high it scores: that is the one
    hard fail Michael left in place.

    Ties break toward the richer material — eventful over active over inert —
    because when two stories score the same the one where something happens is
    the one he has wanted all along.
    """
    _RANK = {'eventful': 3, 'active': 2, 'inert': 1, 'none': 0}
    eligible = []
    for c in candidates or []:
        g = c.get('gate') or {}
        if g.get('factual_errors') or c.get('ungrounded'):
            continue
        if (c.get('index') or 0) <= D515_ACCEPT_INDEX:
            continue
        if not (c.get('story') or '').strip():
            continue
        eligible.append(c)
    if not eligible:
        return None
    return max(eligible, key=lambda c: (c.get('index') or 0,
                                        _RANK.get(c.get('kind'), 0)))
