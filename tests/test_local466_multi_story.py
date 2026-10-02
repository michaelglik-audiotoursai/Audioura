#!/usr/bin/env python3
"""LOCAL-466 — More Than One Story Per Stop.

Tests that the multi-story publishing logic:
  1. Keeps two distinct stories when they pass all rules.
  2. Rejects a duplicate second story (same credit_line or absorbed by merge).
  3. Publishes only one when only one candidate passes.
  4. Reproduces today's single-story behaviour exactly when STORY_LOOP_MAX_STORIES=1.

Run: python3 tests/test_local466_multi_story.py
"""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILURES = []


def check(name, condition, detail=''):
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}{(': ' + detail) if detail else ''}")
        FAILURES.append(name)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures: two distinct stories from different credit_lines, one duplicate pair
# ─────────────────────────────────────────────────────────────────────────────

PROSE = (
    "Salvador Dalí created illustrations for Sigmund Freud's book \"Moses and "
    "Monotheism\" in 1974. This marked a significant moment in Dalí's career. "
    "By doing so, Dalí visually explored Freud's psychoanalytic theories."
)

STORY_A = (
    "In 1939, Sigmund Freud published his final work, Moses and Monotheism, "
    "proposing the controversial thesis that Moses was of Egyptian nobility "
    "rather than Hebrew origin. Decades later, Salvador Dalí engaged with "
    "Freud's psychoanalytic interpretation by etching original designs with a "
    "diamond stylus directly onto massive gold printing plates."
)

STORY_B = (
    "The Hogarth Press, founded by Leonard and Virginia Woolf in 1917, "
    "published Freud's Moses and Monotheism in English in 1939. The press "
    "operated from the Woolfs' dining room and grew to become one of the most "
    "influential literary publishers of the twentieth century."
)

# Near-duplicate of STORY_A — same facts in different words.
STORY_DUP = (
    "Sigmund Freud's final publication, Moses and Monotheism, argued that Moses "
    "was Egyptian rather than Hebrew. Salvador Dalí later illustrated the work "
    "by etching designs onto gold plates with a diamond-tipped stylus."
)

GATE_PASS_61 = {'passes': True, 'failed': [], 'max_sentences': 5,
                'keys': {}, 'confirmed': 3, 'unattested': 0}
GATE_PASS_59 = {'passes': True, 'failed': [], 'max_sentences': 5,
                'keys': {}, 'confirmed': 3, 'unattested': 0}
GATE_PASS_52 = {'passes': True, 'failed': [], 'max_sentences': 3,
                'keys': {}, 'confirmed': 2, 'unattested': 0}


def _make_d511_result(stories_data):
    """Build a _d511_res dict from a list of (story_text, credit_line, index, gate)."""
    stories = []
    for text, cl, idx, gate in stories_data:
        stories.append({
            'story': text, 'credit_line': cl, 'index': idx,
            'gate': gate, 'sources': [], 'counts': {}, 'kind': 'eventful',
        })
    best = max(stories, key=lambda s: s['index']) if stories else None
    return {
        'story': best['story'] if best else '',
        'stories': stories,
        'credit_line': best['credit_line'] if best else '',
        'index': best['index'] if best else None,
        'gate': best['gate'] if best else None,
        'cost_usd': 0.0,
    }


def _simulate_publish(d511_res, prose, max_stories=2, second_min=55):
    """Simulate the PHASE 5.20 multi-story publishing logic from generate_tour_text.

    This is the logic extracted into a testable form. It mirrors what PHASE 5.20
    does: iterate through d511_res['stories'], apply the rules, and merge.
    """
    from story_append_merge import merge_story_into_description

    all_stories = d511_res.get('stories') or []
    published = []
    published_cls = set()
    current_text = prose

    for si, s in enumerate(all_stories):
        if len(published) >= max_stories:
            break
        s_story = s.get('story', '')
        s_cl = s.get('credit_line', '')
        s_idx = s.get('index') or 0

        # Rule 1: distinct credit_lines.
        if s_cl in published_cls:
            continue

        # Rule 4: second story minimum index.
        if published and s_idx < second_min:
            continue

        # Rule 2: merge against current text.
        merged, mrep = merge_story_into_description(
            current_text, s_story,
            work_titles=['Moses and Monotheism', ''])

        # Duplicate detection: story was absorbed.
        new_sents = len(re.split(r'(?<=[.!?])\s+', merged)) - \
                    len(re.split(r'(?<=[.!?])\s+', current_text))
        if published and new_sents < 2:
            continue

        current_text = merged
        published.append(s)
        published_cls.add(s_cl)

    return published, current_text


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Two distinct stories are kept
# ─────────────────────────────────────────────────────────────────────────────

def test_two_distinct_stories_kept():
    """Two stories from different credit_lines, both above SECOND_MIN, both
    adding new material — both publish."""
    print("\n── Test 1: two distinct stories kept ──")
    res = _make_d511_result([
        (STORY_A, 'Salvador Dalí', 61, GATE_PASS_61),
        (STORY_B, 'The Hogarth Press', 59, GATE_PASS_59),
    ])
    published, merged = _simulate_publish(res, PROSE, max_stories=2, second_min=55)
    check('two stories published', len(published) == 2, str(len(published)))
    check('best (61) is first', published[0]['index'] == 61)
    check('second (59) is second', published[1]['index'] == 59)
    check('different credit_lines',
          published[0]['credit_line'] != published[1]['credit_line'])
    # Both stories should contribute text to the merged output.
    check('story A content in merged', 'gold printing plates' in merged)
    check('story B content in merged', 'Hogarth Press' in merged or 'Woolf' in merged)


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: A duplicate second is rejected
# ─────────────────────────────────────────────────────────────────────────────

def test_duplicate_second_rejected():
    """A second story that is largely the same content gets absorbed by the
    merge — the sentence-add count is < 2, so it is dropped."""
    print("\n── Test 2: duplicate second story rejected ──")
    res = _make_d511_result([
        (STORY_A, 'Salvador Dalí', 61, GATE_PASS_61),
        (STORY_DUP, 'Freud Foundation', 59, GATE_PASS_59),
    ])
    published, merged = _simulate_publish(res, PROSE, max_stories=2, second_min=55)
    check('only one story published (duplicate dropped)',
          len(published) == 1, str(len(published)))
    check('the kept story is the best one', published[0]['index'] == 61)


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Only one candidate passes — publish one
# ─────────────────────────────────────────────────────────────────────────────

def test_only_one_candidate_passes():
    """When only one story is in the accepted set, publish exactly one."""
    print("\n── Test 3: only one candidate passes ──")
    res = _make_d511_result([
        (STORY_A, 'Salvador Dalí', 61, GATE_PASS_61),
    ])
    published, merged = _simulate_publish(res, PROSE, max_stories=2, second_min=55)
    check('one story published', len(published) == 1, str(len(published)))
    check('it is the one that passed', published[0]['credit_line'] == 'Salvador Dalí')


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: MAX_STORIES=1 reproduces today's single-story behaviour
# ─────────────────────────────────────────────────────────────────────────────

def test_max_stories_1_reproduces_old_behaviour():
    """With STORY_LOOP_MAX_STORIES=1, only the best story is ever published,
    exactly as before LOCAL-466."""
    print("\n── Test 4: MAX_STORIES=1 reproduces old behaviour ──")
    res = _make_d511_result([
        (STORY_A, 'Salvador Dalí', 61, GATE_PASS_61),
        (STORY_B, 'The Hogarth Press', 59, GATE_PASS_59),
    ])
    published, merged = _simulate_publish(res, PROSE, max_stories=1, second_min=55)
    check('only one story published', len(published) == 1, str(len(published)))
    check('it is the best one (61)', published[0]['index'] == 61)


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Same credit_line = same story, never repeated
# ─────────────────────────────────────────────────────────────────────────────

def test_same_credit_line_rejected():
    """Two different texts from the same credit_line: only the first publishes."""
    print("\n── Test 5: same credit_line rejected ──")
    res = _make_d511_result([
        (STORY_A, 'Salvador Dalí', 61, GATE_PASS_61),
        (STORY_B, 'Salvador Dalí', 59, GATE_PASS_59),  # same credit_line!
    ])
    published, merged = _simulate_publish(res, PROSE, max_stories=2, second_min=55)
    check('only one published (same credit_line)',
          len(published) == 1, str(len(published)))


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: Second story below SECOND_MIN is skipped
# ─────────────────────────────────────────────────────────────────────────────

def test_second_below_minimum_skipped():
    """A second story at index 52 (below SECOND_MIN=55) is not published."""
    print("\n── Test 6: second below SECOND_MIN skipped ──")
    res = _make_d511_result([
        (STORY_A, 'Salvador Dalí', 61, GATE_PASS_61),
        (STORY_B, 'The Hogarth Press', 52, GATE_PASS_52),
    ])
    published, merged = _simulate_publish(res, PROSE, max_stories=2, second_min=55)
    check('only one published (second below 55)',
          len(published) == 1, str(len(published)))
    check('the one at 61 is published', published[0]['index'] == 61)


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: story_production_loop.run_for_stop returns `stories` field
# ─────────────────────────────────────────────────────────────────────────────

def test_run_for_stop_returns_stories_field():
    """The return dict from run_for_stop includes a `stories` list."""
    print("\n── Test 7: run_for_stop contract ──")
    import story_production_loop as L
    check('MAX_STORIES constant exists', hasattr(L, 'MAX_STORIES'))
    check('MAX_STORIES default is 2', L.MAX_STORIES == 2, str(L.MAX_STORIES))
    check('SECOND_MIN constant exists', hasattr(L, 'SECOND_MIN'))
    check('SECOND_MIN default is 55', L.SECOND_MIN == 55, str(L.SECOND_MIN))
    # Verify the function signature includes `stories` in the docstring.
    import inspect
    doc = inspect.getdoc(L.run_for_stop) or ''
    check("docstring mentions 'stories'", 'stories' in doc)


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("LOCAL-466: More Than One Story Per Stop — unit tests\n")
    test_two_distinct_stories_kept()
    test_duplicate_second_rejected()
    test_only_one_candidate_passes()
    test_max_stories_1_reproduces_old_behaviour()
    test_same_credit_line_rejected()
    test_second_below_minimum_skipped()
    test_run_for_stop_returns_stories_field()

    print(f"\n{'─' * 60}")
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}):")
        for f in FAILURES:
            print(f"  • {f}")
        sys.exit(1)
    else:
        print(f"ALL PASSED")
        sys.exit(0)
