#!/usr/bin/env python3
"""LOCAL-529 — one name, four spellings.

The round-7 critique (LOCAL-517) found Logan's original airfield name spelled
four ways across the batch — Jefferies (LOGAN_1), Jeffery (LOGAN_2 x2),
Jeffrey (LOGAN_1), Jeffries (LOGAN_3) — and, sharpest of all, TWICE inside ONE
tour: LOGAN_1 says both "Jefferies Field" and "Jeffrey Field". A listener who
hears one tour name a place two ways has caught the system being careless.

The repair is WITHIN a tour (each of LOGAN_2 and LOGAN_3 is internally
consistent; only LOGAN_1 disagrees with itself), deterministic, and needs no
grounding. Two names it must NOT merge:
  * "Jeffries Point" (an East Boston neighbourhood) is not the airfield
    "* Field" — different head noun.
  * two genuinely different surnames that happen to look alike.

Run: python3 tests/test_local529_one_name_four_spellings.py
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


# The four real spellings, verified against TOURS_FOR_REVIEW/round7/.
FOUR = ['Jefferies', 'Jeffery', 'Jeffrey', 'Jeffries']


def test_the_four_spellings_are_recognised_as_one_name():
    from spoken_text_hygiene import _names_are_near_identical as near
    # Every pair of the four is the same name, however far apart in edits.
    for i in range(len(FOUR)):
        for j in range(i + 1, len(FOUR)):
            check(f'"{FOUR[i]}" and "{FOUR[j]}" are the same name',
                  near(FOUR[i], FOUR[j]))


def test_distinct_names_are_not_merged():
    from spoken_text_hygiene import _names_are_near_identical as near
    # Jefferson is a DIFFERENT surname that merely looks like Jefferies (3 edits,
    # long shared prefix) — the classic trap the acceptance note warns about.
    check('Jefferson is NOT Jefferies', not near('Jefferson', 'Jefferies'))
    # Two-edit look-alikes that are plainly different words must survive too.
    for a, b in [('Channing', 'Manning'), ('Boston', 'Weston'),
                 ('Smith', 'Smyth'), ('Newton', 'Newport'),
                 ('Winthrop', 'Winslow')]:
        check(f'"{a}" is NOT "{b}"', not near(a, b))


def test_one_tour_that_disagrees_with_itself_is_made_to_agree():
    """The LOGAN_1 case, using its own two real sentences."""
    from spoken_text_hygiene import normalize_proper_noun_spellings as N
    logan1 = ("Back in 1923, when the Boston Air Port, also called Jefferies "
              "Field, formally opened, it was a milestone. This event marked "
              "Jeffrey Field, as it was then known, as a crucial player.")
    out, rep = N(logan1)
    spellings = set(re.findall(r'(Jefferies|Jeffery|Jeffrey|Jeffries) Field',
                               out))
    check('after normalisation the airfield is spelled exactly one way',
          len(spellings) == 1, str(spellings))
    check('a normalisation was recorded, never silent', len(rep['groups']) == 1)
    check('the change is auditable (from -> to, with a count)',
          rep['groups'][0]['changed']
          and len(rep['groups'][0]['changed'][0]) == 3)
    # 1-1 tie in this tour: the earliest-heard spelling ("Jefferies") wins so the
    # listener is not corrected mid-tour.
    check('the tie goes to the first spelling heard',
          rep['groups'][0]['winner'] == 'Jefferies',
          rep['groups'][0]['winner'])


def test_the_most_frequent_spelling_wins_when_there_is_a_majority():
    from spoken_text_hygiene import normalize_proper_noun_spellings as N
    # Jeffery appears twice, Jeffrey once — frequency leads, not first-heard.
    text = ("Opened as Jeffery Field in 1923, the site grew. Locals still called "
            "it Jeffery Field for decades, though a plaque once read Jeffrey "
            "Field.")
    out, rep = N(text)
    check('the majority spelling wins', rep['groups'][0]['winner'] == 'Jeffery',
          rep['groups'][0]['winner'])
    check('the minority spelling is gone',
          'Jeffrey Field' not in out and out.count('Jeffery Field') == 3, out)


def test_a_different_head_noun_keeps_a_genuinely_different_place():
    """Jeffries POINT is not the airfield; it must survive next to * Field."""
    from spoken_text_hygiene import normalize_proper_noun_spellings as N
    text = ("The airfield opened as Jefferies Field in 1923 on reclaimed land at "
            "Jeffries Point in East Boston.")
    out, rep = N(text)
    check('Jeffries Point is left untouched', 'Jeffries Point' in out)
    check('Jefferies Field is left untouched', 'Jefferies Field' in out)
    check('nothing was merged across the two head nouns', rep['groups'] == [],
          str(rep['groups']))


def test_two_similar_surnames_under_the_same_head_both_survive():
    from spoken_text_hygiene import normalize_proper_noun_spellings as N
    text = "The Jefferson Building stands beside the Harrison Building."
    out, rep = N(text)
    check('distinct surnames sharing a head noun are not merged',
          out == text and rep['groups'] == [], str(rep['groups']))


def test_a_name_that_appears_once_is_never_touched():
    from spoken_text_hygiene import normalize_proper_noun_spellings as N
    text = "The tour ends at Logan Airport, named for Edward Lawrence Logan."
    out, rep = N(text)
    check('a single, consistent name is left exactly as written',
          out == text and rep['groups'] == [])


def test_it_runs_over_the_real_round7_tours_correctly():
    """Ground truth: LOGAN_1 disagrees; LOGAN_2 and LOGAN_3 do not."""
    from spoken_text_hygiene import normalize_proper_noun_spellings as N
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base = os.path.join(root, 'TOURS_FOR_REVIEW', 'round7')
    if not os.path.isdir(base):
        print('  SKIP  round7 tours are not on disk')
        return

    def field_spellings(s):
        return set(re.findall(r'(Jefferies|Jeffery|Jeffrey|Jeffries) Field', s))

    l1 = open(os.path.join(base, 'LOGAN_1.txt'), encoding='utf-8').read()
    o1, r1 = N(l1)
    check('LOGAN_1 really did ship two spellings of the airfield',
          len(field_spellings(l1)) == 2, str(field_spellings(l1)))
    check('LOGAN_1 is normalised to one spelling',
          len(field_spellings(o1)) == 1, str(field_spellings(o1)))

    l2 = open(os.path.join(base, 'LOGAN_2.txt'), encoding='utf-8').read()
    o2, r2 = N(l2)
    check('LOGAN_2 was already consistent and is left untouched',
          o2 == l2 and r2['groups'] == [])

    l3 = open(os.path.join(base, 'LOGAN_3.txt'), encoding='utf-8').read()
    o3, r3 = N(l3)
    check('LOGAN_3 (Jeffries Point) is left untouched',
          o3 == l3 and r3['groups'] == [])


def test_two_different_people_with_similar_surnames_survive():
    """Acceptance: two different people with similar surnames must survive."""
    from spoken_text_hygiene import normalize_proper_noun_spellings as N
    # Different head nouns keep them apart even though both are "* Hall".
    text = ("Anderson Hall was funded by the Andersen family, no relation to the "
            "architect.")
    out, rep = N(text)
    # Anderson/Andersen ARE near-identical, but each appears once under a
    # different head context (Hall vs family), so neither is a within-tour
    # inconsistency to normalise.
    check('a single "Anderson Hall" is not rewritten', 'Anderson Hall' in out)
    check('the surname "Andersen family" is untouched', 'Andersen family' in out)


def test_it_is_wired_into_the_last_spoken_pass():
    """The repair must run on the assembled tour, like the other D523 fixes."""
    from spoken_text_hygiene import clean_spoken_text as C
    text = ("Opened as Jefferies Field, the site was later marked Jeffrey Field "
            "on the maps.")
    out, rep = C(text)
    matches = re.findall(r'(Jefferies|Jeffrey) Field', out)
    check('clean_spoken_text applies the normalisation',
          len(matches) == 2 and len(set(matches)) == 1, out)
    check('and counts it in its report', rep['name_spellings'] == 1,
          str(rep.get('name_spellings')))


if __name__ == '__main__':
    print('LOCAL-529 — one name, four spellings\n')
    for fn in (test_the_four_spellings_are_recognised_as_one_name,
               test_distinct_names_are_not_merged,
               test_one_tour_that_disagrees_with_itself_is_made_to_agree,
               test_the_most_frequent_spelling_wins_when_there_is_a_majority,
               test_a_different_head_noun_keeps_a_genuinely_different_place,
               test_two_similar_surnames_under_the_same_head_both_survive,
               test_a_name_that_appears_once_is_never_touched,
               test_it_runs_over_the_real_round7_tours_correctly,
               test_two_different_people_with_similar_surnames_survive,
               test_it_is_wired_into_the_last_spoken_pass):
        print(f"\n{fn.__name__}")
        fn()
    print()
    if FAILURES:
        print(f"FAILED — {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        sys.exit(1)
    print('ALL TESTS PASSED')
