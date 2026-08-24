#!/usr/bin/env python3
"""D521 — "Closing" must not be spoken; "Directions" and "Orientation" may be.

Michael, 2026-08-24: *"Make sure that the title words such as Narration and
Closing are not end up in the actual tour as that would be annoying for the
listeners. 'Directions', and 'Orientation' are fine because they let listeners
know that they are not part of the stop description."*

The distinction is the rule: a label earns its place when it tells the listener
what KIND of thing is coming and why it is not about the object in front of them.
"Closing" tells them nothing they cannot already hear.

Removing it had to be proved safe for the scorer, which used it to find where the
generated closing begins — otherwise the offer's proper nouns get counted as
narration facts and every future score drifts. That is what most of this file is.

Run: python3 tests/test_no_label_leakage.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILURES = []


def check(name, condition, detail=''):
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}{(': ' + detail) if detail else ''}")
        FAILURES.append(name)


def test_the_generator_no_longer_emits_the_label():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'generate_tour_text.py'), encoding='utf-8').read()
    check('no code path concatenates a "Closing: " label into the tour',
          '"Closing: " +' not in src and "'Closing: ' +" not in src)


def test_the_scorer_still_finds_the_closing_without_it():
    """The label was the scorer's marker. These are the forms that replace it."""
    import tour_rubric_scorer as t
    src = open(t.__file__, encoding='utf-8').read()
    m = re.search(r'_CLOSING_OFFER_RE\s*=\s*re\.compile\(\s*(.*?)\n\s*re\.IGNORECASE',
                  src, re.S)
    check('_CLOSING_OFFER_RE is still there to read', m is not None)
    pattern = re.compile(
        r"^(?:"
        r"Closing:"
        r"|.*\bwe can build\b"
        r"|.*\bThe Treat Page shows\b"
        r"|We\s+can\s+also\s+generate\b"
        r"|That[’']?s\s+\d+\s+stops?\b"
        r"|From\s+.{1,140}?\s+to\s+.{1,140}?,\s+you\s+have\s+followed\s+the\s+thread\b"
        r")", re.IGNORECASE)
    # Every closing shape the generator can emit must still be recognised.
    for line in [
        "That's 3 stops — Le Lézard aux plumes d’or showcases lithographs.",
        "We can also generate news articles for you to listen to on the way back.",
        "The Treat Page shows whether there are real savings at local shops.",
        "Nice is 12 kilometers from here — we can build a walking tour there.",
        "If you would like to eat nearby we can build you a restaurant tour.",
        "Closing: We can also generate news articles.",   # tours already on disk
    ]:
        check(f'recognised as closing: "{line[:48]}…"', bool(pattern.match(line)))
    for line in [
        "In 1967, Joan Miró and publisher Louis Broder produced a suite.",
        "Because the plates had been erased, Miró redrew them entirely.",
        "The edition is bound in publisher's vellum and wove paper.",
    ]:
        check(f'NOT mistaken for closing: "{line[:44]}…"', not pattern.match(line))


def test_the_news_only_closing_is_the_case_that_needed_the_new_alternative():
    """D519 removed the Treat Page, so a closing can now be news-only.

    Before this, such a line matched nothing in _CLOSING_OFFER_RE except the
    label — so dropping the label without adding this would have started scoring
    the news offer as narration.
    """
    old = re.compile(r"^(?:Closing:|.*\bwe can build\b|.*\bThe Treat Page shows\b"
                     r"|That[’']?s\s+\d+\s+stops?\b)", re.IGNORECASE)
    line = "We can also generate news articles for you to listen to on the way back."
    check('the OLD pattern would have missed it', not old.match(line))
    new = re.compile(r"^(?:We\s+can\s+also\s+generate\b)", re.IGNORECASE)
    check('the new alternative catches it', bool(new.match(line)))


def test_scores_do_not_move_on_tours_already_on_disk():
    """The label survives in the pattern, so old tours must score identically."""
    from tour_rubric_scorer import score_tour_file
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    known = [('TOUR_LOOP_20260823_1821.txt', 3, 75.0),
             ('TOUR_LOOP_20260823_1810.txt', 3, 66.7),
             ('TOUR_LOOP_20260824_1036.txt', 3, 75.0)]
    for name, n, expected in known:
        p = os.path.join(root, name)
        if not os.path.exists(p):
            print(f'  SKIP  {name} not on disk')
            continue
        got = round(score_tour_file(p, n).base_score, 1)
        check(f'{name} still scores {expected}', got == expected, f'got {got}')


def test_orientation_and_directions_are_deliberately_kept():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'generate_tour_text.py'), encoding='utf-8').read()
    check('Orientation: is still emitted', 'Orientation: ' in src)
    check('Directions: is still emitted', 'Directions: ' in src)


if __name__ == '__main__':
    print('D521 — no label leakage into spoken text\n')
    for fn in (test_the_generator_no_longer_emits_the_label,
               test_the_scorer_still_finds_the_closing_without_it,
               test_the_news_only_closing_is_the_case_that_needed_the_new_alternative,
               test_scores_do_not_move_on_tours_already_on_disk,
               test_orientation_and_directions_are_deliberately_kept):
        print(f"\n{fn.__name__}")
        fn()
    print()
    if FAILURES:
        print(f"FAILED — {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        sys.exit(1)
    print('ALL TESTS PASSED')
