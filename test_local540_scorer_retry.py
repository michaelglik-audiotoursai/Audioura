#!/usr/bin/env python3
"""test_local540_scorer_retry.py — offline checks for the LOCAL-540 wiring.

No network. Uses the round-9 LOGAN_1 evidence tour (which reports offsite_entity
and self_contradiction under the current scorer) to prove:

  1. score_and_retry with NO regenerator scores but does not retry (score is
     separable from action).
  2. Attribution maps both LOGAN_1 REQUIRED_CLEAN defects to a single section —
     the stop-1 Orientation preview — so ONE rewrite covers both.
  3. Splicing a clean orientation back in and re-scoring clears both defects, and
     the retry cost is tracked.
  4. A tour that is already clean triggers no retry and no cost.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import tour_quality as tq
import scorer_retry as sr

LOGAN = open(os.path.join(HERE, 'TOURS_FOR_REVIEW', 'round9', 'LOGAN_1.txt'),
             errors='ignore').read()

CLEAN_ORIENT = (
    'Orientation: You are about to embark on a walking journey through Boston '
    'Logan International Airport, Boston MA. The tour spans from the bustling '
    'Terminal A Main Concourse to the efficient Terminal A Baggage Claim, all '
    'within the same building. At Terminal A Main Concourse, the airport was '
    'renamed in 1943 to honor Major General Edward Lawrence Logan. Your first '
    'stop is Terminal A Main Concourse. Exit the transportation drop-off area '
    "and enter the main entrance doors, marked by large 'Terminal A' signs.")


def _quiet(*a, **k):
    pass


def test_score_only_no_retry():
    res = sr.score_and_retry(LOGAN, requested_stops=4, is_building_tour=True,
                             regenerate_section=None, log=_quiet)
    assert res['retried'] is False, "no regenerator => must not retry"
    assert res['retry_cost'] == {'total_cost': 0.0, 'total_tokens': 0}
    assert set(res['defects_before']) == {'offsite_entity', 'self_contradiction'}, \
        res['defects_before']
    # text unchanged
    assert res['text'] == LOGAN
    print("PASS test_score_only_no_retry")


def test_attribution_single_orientation_target():
    score = tq.score_tour(LOGAN, requested_stops=4, is_building_tour=True)
    plan = sr.plan_regeneration(LOGAN, score['defects'])
    assert len(plan) == 1, f"expected 1 target, got {len(plan)}: {plan}"
    t = plan[0]
    assert t['kind'] == sr.ORIENTATION, t['kind']
    assert t['stop'] == 1, t['stop']
    assert set(t['defects']) == {'offsite_entity', 'self_contradiction'}, t['defects']
    seg = LOGAN[t['span'][0]:t['span'][1]]
    assert seg.startswith('Orientation:'), seg[:40]
    assert "St. Mary's Cathedral" in seg, "offending quote must be inside the target span"
    print("PASS test_attribution_single_orientation_target")


def test_retry_clears_defects_and_tracks_cost():
    calls = {'n': 0}

    def regen(target, full_text):
        calls['n'] += 1
        return CLEAN_ORIENT, {'total_cost': 0.0123, 'total_tokens': 456}

    res = sr.score_and_retry(LOGAN, requested_stops=4, is_building_tour=True,
                             regenerate_section=regen, log=_quiet)
    assert calls['n'] == 1, f"exactly ONE retry expected, got {calls['n']}"
    assert res['retried'] is True
    assert res['removed'] == ['offsite_entity', 'self_contradiction'], res['removed']
    assert res['remaining'] == [], res['remaining']
    assert res['after']['clean'] is True
    assert res['retry_cost'] == {'total_cost': 0.0123, 'total_tokens': 456}, \
        res['retry_cost']
    assert "St. Mary's Cathedral" not in res['text'], \
        "offsite entity must be gone from the delivered text"
    print("PASS test_retry_clears_defects_and_tracks_cost")


def test_clean_tour_no_retry():
    calls = {'n': 0}

    def regen(target, full_text):
        calls['n'] += 1
        return "x", {'total_cost': 1.0, 'total_tokens': 1}

    # a trivially clean, single-stop tour with a named person and no framing traps
    clean = (
        "Step-by-Step Audio Guided Tour: Test Venue - Facility Tour\n"
        "Tour-Category: facility\n\n"
        "Stop 1: Main Hall\n\n"
        "Orientation: Your first stop is the Main Hall.\n\n"
        "The Main Hall was designed by architect Jane Doe and opened to visitors "
        "as a place of gathering. It remains a calm, well-lit space.\n"
    )
    res = sr.score_and_retry(clean, requested_stops=1, is_building_tour=True,
                             regenerate_section=regen, log=_quiet)
    req = [k for k in res['defects_before'] if k in tq.REQUIRED_CLEAN]
    assert req == [], f"fixture unexpectedly has REQUIRED_CLEAN defects: {req}"
    assert calls['n'] == 0, "a clean tour must not trigger a retry"
    assert res['retried'] is False
    assert res['retry_cost'] == {'total_cost': 0.0, 'total_tokens': 0}
    print("PASS test_clean_tour_no_retry")


if __name__ == '__main__':
    test_score_only_no_retry()
    test_attribution_single_orientation_target()
    test_retry_clears_defects_and_tracks_cost()
    test_clean_tour_no_retry()
    print("\nALL OFFLINE CHECKS PASSED")
