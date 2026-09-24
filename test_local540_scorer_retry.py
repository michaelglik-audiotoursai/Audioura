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
    # [2026-09-23, LEAD at merge] LOCAL-538 landed after this test was written and
    # adds dangling_complement in LOGAN_1 stop 3 ("Trippe, the founder and later Pan
    # American World Airways"). The round-9 pair this test was built around must still
    # be present; a superset is correct, not a regression. Asserting an exact set here
    # makes the test fail every time a NEW detector starts working, which is backwards.
    assert {'offsite_entity', 'self_contradiction'} <= set(res['defects_before']), \
        res['defects_before']
    # text unchanged
    assert res['text'] == LOGAN
    print("PASS test_score_only_no_retry")


def test_attribution_single_orientation_target():
    score = tq.score_tour(LOGAN, requested_stops=4, is_building_tour=True)
    plan = sr.plan_regeneration(LOGAN, score['defects'])
    # [2026-09-23, LEAD at merge] LOCAL-538's dangling_complement sits in stop 3, so
    # the plan now has two targets. What this test is actually about is that the
    # attribution pair is attributed to the ORIENTATION and to nothing else -- one
    # target carrying both, with its offending quote inside its own span.
    orient = [t for t in plan if t['kind'] == sr.ORIENTATION]
    assert len(orient) == 1, f"expected exactly 1 orientation target, got {plan}"
    t = orient[0]
    assert t['stop'] == 1, t['stop']
    assert {'offsite_entity', 'self_contradiction'} <= set(t['defects']), t['defects']
    seg = LOGAN[t['span'][0]:t['span'][1]]
    assert seg.startswith('Orientation:'), seg[:40]
    assert "St. Mary's Cathedral" in seg, "offending quote must be inside the target span"
    print("PASS test_attribution_single_orientation_target")


def test_retry_clears_defects_and_tracks_cost():
    calls = {'n': 0}
    seen_spans = []

    # [2026-09-23, LEAD at merge] The stub must answer with content appropriate to
    # the target it is handed. Returning CLEAN_ORIENT for EVERY target was fine when
    # LOGAN_1 had one broken section; once LOCAL-538 added dangling_complement in
    # stop 3, the same stub spliced an Orientation paragraph into a stop body and
    # built a document no generator would ever emit -- then the test blamed the
    # retry for the defects that Frankenstein text still carried.
    def regen(target, full_text):
        calls['n'] += 1
        seen_spans.append(target['span'])
        if target['kind'] == sr.ORIENTATION:
            return CLEAN_ORIENT, {'total_cost': 0.0123, 'total_tokens': 456}
        # Declining a target is a supported outcome -- score_and_retry does
        # `if not out: continue` and leaves that section alone. Exercising it here
        # keeps this test about the one thing it is for: that regenerating the
        # ORIENTATION clears the round-9 offsite_entity + self_contradiction pair.
        # Hand-authoring a stop body that satisfies all ten detectors is a different
        # test, and a worse one -- my first attempt at it dropped the "Stop 3:"
        # header, took the tour from 4 stops to 2, and manufactured a fresh
        # epilog_stop_mismatch that had nothing to do with the retry.
        return None

    res = sr.score_and_retry(LOGAN, requested_stops=4, is_building_tour=True,
                             regenerate_section=regen, log=_quiet)
    # [2026-09-23, LEAD at merge] The invariant is ONE PASS, never a loop -- not one
    # CALL. A tour with defects in two sections gets each section rewritten once, and
    # that is still a single pass. Asserting a call count of 1 silently encoded "only
    # ever one broken section", which LOCAL-538 immediately disproved. Assert the
    # thing that must not change: no section is regenerated twice.
    plan = sr.plan_regeneration(LOGAN, tq.score_tour(
        LOGAN, requested_stops=4, is_building_tour=True)['defects'])
    assert calls['n'] == len(plan), \
        f"one rewrite per planned section, got {calls['n']} for {len(plan)} targets"
    assert len(seen_spans) == len(set(seen_spans)), \
        f"a section was regenerated more than once: {seen_spans}"
    assert res['retried'] is True
    assert {'offsite_entity', 'self_contradiction'} <= set(res['removed']), res['removed']
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
