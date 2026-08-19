#!/usr/bin/env python3
"""story_index_pass.py — LOCAL-485: Michael's step 5, at module scope.

Step 5 of the seven is "we evaluate the story assigning a value index".
`evaluate_story` had been built and improved twice (D468, D470) and had **zero
references in `generate_tour_text.py`**. This module is the production caller.

**It reports. It does not gate.** D474: the index is calibrated against a single
human judgement — Michael's, on one exhibition — and a gate built on one
calibration point will confidently delete good material. The index is written
onto each POI so the later steps (7a's "no valid story" retry trigger, 7c's
value-proportional sizing) can read a number somebody already computed, rather
than each re-deriving its own and disagreeing — which is the failure shape D469,
D482 and D483 all had.

**Why this lives at module scope instead of inline in `generate_tour_text()`.**
D421 bounced LOCAL-456 for exactly this: a gate written inline needs a key, a DB
and a network to reach, so its tests grep the source instead of running it, and a
grep test cannot fail. `apply_story_index` takes a list of dicts and a string and
returns a dict. It is fully testable with no key, no DB and no network.
"""
import os
from typing import Dict, List, Optional

__all__ = ['apply_story_index', 'build_index_corpus', 'STORY_INDEX_DISABLED_ENV']

STORY_INDEX_DISABLED_ENV = 'DISABLE_STORY_INDEX'


def build_index_corpus(checklist_result=None,
                       stop_corpus_data: Optional[Dict] = None) -> str:
    """Assemble the grounding corpus the index scores against.

    `evaluate_story`'s groundedness bonus is worth up to 15 of the 100 points and
    is a flat ZERO when no corpus is supplied. Passing the material we already
    retrieved and paid for is the difference between a real score and one capped
    at 85.
    """
    parts = []
    if checklist_result is not None:
        parts.append(getattr(checklist_result, 'page_text', '') or '')
    for entry in (stop_corpus_data or {}).values():
        for passage in ((entry or {}).get('passages') or []):
            parts.append(str(passage))
    return '\n'.join(p for p in parts if p)


def apply_story_index(poi_list: List[Dict], corpus: str = '',
                      evaluator=None) -> Dict:
    """Score every stop's description and record the result on the POI.

    Mutates each POI with `_story_index` (int) and `_story_axes` (dict). Never
    edits `description` — this pass is incapable of changing a tour, by
    construction, which is what makes it safe to land first.

    Returns stats: {'scored', 'skipped', 'mean', 'min', 'max', 'rows', 'weakest'}.
    `rows` is [(stop_name, evaluation_dict)] in stop order.

    `evaluator` is injectable so tests can drive the branch logic without
    depending on `evaluate_story`'s current calibration — a test that asserts a
    specific index value would go red every time the scorer is legitimately
    retuned, which is how suites end up being deleted instead of fixed.
    """
    stats = {'scored': 0, 'skipped': 0, 'mean': None, 'min': None, 'max': None,
             'rows': [], 'weakest': None, 'disabled': False}

    if os.environ.get(STORY_INDEX_DISABLED_ENV, '').strip() == '1':
        stats['disabled'] = True
        return stats

    if evaluator is None:
        from evaluate_story import evaluate_story as evaluator

    for i, poi in enumerate(poi_list or []):
        text = poi.get('description') or ''
        # A bracketed placeholder is not prose; scoring it would report a
        # confident 0 for a stop that was never written.
        if not text or text.startswith('['):
            stats['skipped'] += 1
            continue
        try:
            ev = evaluator(text, corpus=corpus)
        except Exception:
            stats['skipped'] += 1
            continue
        poi['_story_index'] = ev['valuation_index']
        poi['_story_axes'] = {'historic': ev['historic'],
                              'detail': ev['detail'],
                              'social': ev['social']}
        stats['rows'].append((poi.get('name', f'Stop {i + 1}'), ev))
        stats['scored'] += 1

    if stats['rows']:
        values = [ev['valuation_index'] for _, ev in stats['rows']]
        stats['mean'] = sum(values) / len(values)
        stats['min'] = min(values)
        stats['max'] = max(values)
        # The weakest stop is what Michael reads first when a tour disappoints,
        # and it is the one step 7a retries.
        stats['weakest'] = min(stats['rows'], key=lambda r: r[1]['valuation_index'])

    return stats


def format_index_report(stats: Dict) -> str:
    """Render the per-stop table for the generation log."""
    if stats.get('disabled'):
        return "  [LOCAL-485] PHASE 5.21: story valuation index DISABLED by env var"
    if not stats.get('rows'):
        return "  [LOCAL-485] PHASE 5.21: no scorable stops"
    lines = [f"    {'#':>2}  {'stop':<40} {'idx':>4} {'hist':>5} {'detl':>5} {'soc':>5}"]
    for n, (name, ev) in enumerate(stats['rows'], 1):
        lines.append(f"    {n:>2}  {name[:40]:<40} {ev['valuation_index']:>4} "
                     f"{ev['historic']:>5} {ev['detail']:>5} {ev['social']:>5}")
    lines.append(f"    [LOCAL-485] index mean {stats['mean']:.1f} over "
                 f"{stats['scored']} stop(s), range {stats['min']}-{stats['max']}")
    lines.append(f"    [LOCAL-485] weakest: '{stats['weakest'][0][:40]}' at "
                 f"{stats['weakest'][1]['valuation_index']}")
    return '\n'.join(lines)
