#!/usr/bin/env python3
"""test_local540_cache_hit_no_score.py — a cache HIT must not be re-scored,
re-generated, or charged (LOCAL-540 acceptance).

The generation path returns the cached tour long before the LOCAL-540 scoring
block. We prove it by:
  * monkeypatching tour_cache_layer1.get_cached_tour to force a HIT,
  * installing a spy over scorer_retry.score_and_retry that raises if called,
  * calling generate_tour_text with STORIED_MODE on and cache enabled,
and asserting the returned text is the cached one, the scorer spy never fired,
and _LAST_GENERATION_COST reports $0.00 / 0 tokens / cache_hit True with a None
score record.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

for _line in open(os.path.join(HERE, '.env')):
    _line = _line.strip()
    if _line and not _line.startswith('#') and '=' in _line:
        _k, _v = _line.split('=', 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '0'          # cache ENABLED
os.environ.setdefault('DATABASE_URL',
                      'postgresql://admin:password123@localhost:5433/audiotours')

CACHED_TOUR = ("Step-by-Step Audio Guided Tour: Cached Venue - Facility Tour\n"
               "Tour-Category: facility\n\nStop 1: Cached Hall\n\n"
               "Orientation: Your first stop is the Cached Hall.\n")

import tour_cache_layer1
import scorer_retry
import generate_tour_text as gtt


def main():
    # Force a cache HIT regardless of DB state.
    tour_cache_layer1.get_cached_tour = lambda *a, **k: CACHED_TOUR

    # Spy: a cache hit must NEVER reach the scorer.
    calls = {'n': 0}
    _orig = scorer_retry.score_and_retry

    def _spy(*a, **k):
        calls['n'] += 1
        raise AssertionError("score_and_retry was called on a CACHE HIT")

    scorer_retry.score_and_retry = _spy
    try:
        text, out_file, coords = gtt.generate_tour_text(
            "Cached Venue", "facility", output_file=None, total_stops=4)
    finally:
        scorer_retry.score_and_retry = _orig

    assert text == CACHED_TOUR, f"expected cached tour back, got {text[:60]!r}"
    assert calls['n'] == 0, "scorer must not run on a cache hit"

    cost = dict(gtt._LAST_GENERATION_COST or {})
    print("cache-hit _LAST_GENERATION_COST:", {
        'total_cost': cost.get('total_cost'),
        'total_tokens': cost.get('total_tokens'),
        'cache_hit': cost.get('cache_hit'),
        'tour_total_cost': cost.get('tour_total_cost'),
        'has_score_key': 'score' in cost,
    })
    assert cost.get('total_cost') == 0.0, cost
    assert cost.get('total_tokens') == 0, cost
    assert cost.get('cache_hit') is True, cost
    assert float(cost.get('tour_total_cost', 0.0)) == 0.0, cost
    # No score record is attached on a cache hit.
    assert 'score' not in cost, "cache hit must not carry a score record"
    assert getattr(gtt, '_LAST_SCORE_RECORD', 'unset') is None or \
        gtt._LAST_SCORE_RECORD is None

    print("\nPASS: cache HIT returned cached tour, scorer NOT called, cost $0.00")


if __name__ == '__main__':
    main()
