#!/usr/bin/env python3
"""D523 — why the stories got fewer and worse, and the four repairs.

Michael, 2026-08-24: *"I see way less stories and less quality stories from
iteration to iteration and I wonder why."*

Answered from `story_loop_candidates.jsonl`: since D515 the loop bought exactly
ONE credit_line per stop in 12 of 13 stop-attempts, because his rule says a story
at index 50+ "is the story and we do not need to verify more" — and at a floor of
50 the first candidate always qualifies. Both halves follow: quality became one
draw from a 20-35 point spread, and since `allowed_sentences()` maps index to
length, a low draw is trimmed to three sentences where a high draw earns five.

Run: python3 tests/test_d523_story_selection_and_hygiene.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILURES = []


def check(name, condition, detail=''):
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}{(': ' + detail) if detail else ''}")
        FAILURES.append(name)


def test_the_loop_now_keeps_the_best_not_the_first():
    import story_production_loop as L
    check('best-of is ON by default', L.BEST_OF is True)
    check('there is an early exit so a very good story is not overpaid for',
          L.STOP_AT >= 70, str(L.STOP_AT))
    check('accept-first is one env var away',
          os.environ.get('STORY_LOOP_BEST_OF') is None)
    src = open(L.__file__, encoding='utf-8').read()
    check('the loop only breaks early on the STOP_AT bar, never on first pass',
          'if not BEST_OF:\n                    break' in src
          and 'if (idx or 0) >= STOP_AT:' in src)
    check('a better candidate replaces a worse one',
          "_better = (out['index'] or -1) < (idx or 0)" in src)


def test_the_sentence_allowance_is_why_length_fell():
    """The second half of the complaint, and it is arithmetic, not opinion."""
    from story_publish_gate import allowed_sentences
    low, high = allowed_sentences(52, False), allowed_sentences(74, False)
    check('a story at 52 earns 3 sentences', low == 3, str(low))
    check('a story at 74 earns more', high > low, f'{high} vs {low}')
    check('so a low draw is literally a shorter story', high - low >= 2)


def test_a_stop_may_state_the_exhibition_thesis_once():
    from story_append_merge import merge_story_into_description as M
    prose = ("Joan Miró and Louis Broder began working together in 1956. "
             "Their collaboration exemplifies the exhibition's argument that "
             "books can be revolutionary art forms. "
             "This approach highlights the role of such collaborations in "
             "reshaping the book as an art form, resonating with the broader "
             "themes of the exhibition. "
             "Miró's use of colour reflects his dialogue with the subconscious.")
    merged, report = M(prose, "In 1967 the plates were erased.")
    check('the restatement is dropped', len(report['restated']) == 1,
          str(report['restated']))
    check('the FIRST statement of the thesis survives',
          "exemplifies the exhibition's argument" in merged)
    check('sentences carrying their own facts survive',
          'Louis Broder began working together in 1956' in merged
          and 'dialogue with the subconscious' in merged)


def test_a_thesis_sentence_carrying_a_new_fact_is_never_dropped():
    from story_append_merge import merge_story_into_description as M
    prose = ("Reverdy's text exemplifies the exhibition's thesis. "
             "The Hogarth Press published Freud's text in 1939, furthering the "
             "collaborative spirit the exhibition seeks to highlight.")
    merged, report = M(prose, "Tériade revived the project in 1955.")
    check('a thesis line that brings Hogarth Press and 1939 is kept',
          'Hogarth Press' in merged and '1939' in merged, str(report['restated']))


def test_template_seams_and_missing_spaces_are_repaired():
    from spoken_text_hygiene import clean_spoken_text as C
    got, rep = C("At this work: Le Lézard aux plumes d'or, witness Miró's "
                 "exploration.")
    check('"At this work:" becomes plain speech',
          got == "At Le Lézard aux plumes d'or, witness Miró's exploration.", got)
    check('and it is counted', rep['seams'] == 1)

    got2, rep2 = C("…a mythic creature.Published by Louis Broder, this work…")
    check('a welded sentence boundary is opened',
          'creature. Published' in got2, got2)
    check('and it is counted', rep2['missing_spaces'] == 1)

    for safe in ["Read more at christies.com and sothebys.com.",
                 "The U.S.A. edition differs.",
                 "He holds a Ph.D in art history."]:
        out, _ = C(safe)
        check(f'left alone: "{safe[:34]}…"', out == safe, out)

    got3, _ = C("Closing: We can also generate news articles.")
    check('a spoken label is removed',
          got3 == "We can also generate news articles.", got3)


def test_an_established_wrong_fact_is_corrected():
    from known_fact_corrections import apply_corrections as A
    got, fired = A("Freud proposed that Moses was an Egyptian priest, which "
                   "stirred debate.")
    check('the priest claim is corrected to nobleman',
          'Egyptian nobleman' in got and 'Egyptian priest' not in got, got)
    check('the correction is auditable, never silent',
          len(fired) == 1 and fired[0]['why'], str(fired))
    untouched = "Moses was an Egyptian nobleman, a follower of Akhenaten."
    out, f2 = A(untouched)
    check('the CORRECT version is left alone', out == untouched and not f2)


def test_the_d515_amendments_are_implemented_and_off():
    import story_publish_gate as G
    check('the amendments default OFF', G.AMEND is False)
    src = open(G.__file__, encoding='utf-8').read()
    check('they are implemented, not merely discussed',
          "keys['verified_something']" in src
          and "keys['adjudication_parsed']" in src
          and 'if AMEND:' in src)
    # With them off, a story that verified nothing but scores 50+ still publishes.
    v = G.evaluate({'story_kind': 'inert', 'index': 62,
                    'counts': {'CONFIRMED': 0, 'UNATTESTED': 0},
                    'tells_disagreement': False,
                    'factual_errors': [], 'ungrounded': []})
    check('off: a C0 story at 62 still publishes, as D515 intends', v['passes'],
          str(v['failed']))


def test_the_checker_sees_both_new_defect_classes():
    """Validated against tours whose answers are already known."""
    import check_known_defects as K
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(root, 'TOUR_LOOP_20260824_1223.txt')
    if not os.path.exists(p):
        print('  SKIP  the 12:23 tour is not on disk')
        return
    text = open(p, encoding='utf-8').read()
    check('(g) finds the wrong exhibition in the 12:23 tour',
          'Dalí: Disruption and Devotion' in str(K.defect_g(text)))
    check('(h) finds the priest claim standing alone',
          'Egyptian priest' in str(K.defect_h(text)))
    check('(b) stays silent on it — which is why (h) had to exist',
          K.defect_b(text) == [], str(K.defect_b(text)))


if __name__ == '__main__':
    print('D523 — story selection, restatement, hygiene, corrections\n')
    for fn in (test_the_loop_now_keeps_the_best_not_the_first,
               test_the_sentence_allowance_is_why_length_fell,
               test_a_stop_may_state_the_exhibition_thesis_once,
               test_a_thesis_sentence_carrying_a_new_fact_is_never_dropped,
               test_template_seams_and_missing_spaces_are_repaired,
               test_an_established_wrong_fact_is_corrected,
               test_the_d515_amendments_are_implemented_and_off,
               test_the_checker_sees_both_new_defect_classes):
        print(f"\n{fn.__name__}")
        fn()
    print()
    if FAILURES:
        print(f"FAILED — {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        sys.exit(1)
    print('ALL TESTS PASSED')
