#!/usr/bin/env python3
"""test_local470_detail_detectors.py — the object detectors must see the object.

D468 made `detail` a first-class term in `valuation_index` (0-30). Three rounds of
iteration on MFA Unbound stop 2 then left it stuck at **7.1 of 30 — 24% of the term
used** — while `materials` was already saturating. Decomposing the sub-scores over
the eight round-3 stories showed why:

    materials              22 hits   drypoints, engravings, lithographs, sheepskin
    processes               5 hits   edition, numbered, printed, signed
    dimensions              1 hit    '1938 m'          <- a YEAR, read as metres
    counts                  0 hits                     <- despite "ten drypoints"
    physical_descriptions   1 hit    tactile

Two defects, both the D466 shape — a detector confidently reporting the wrong thing:

  A. `_DIMENSION_RE` allows the bare units `m` and `in` with `\\s*` permitting zero
     width, so "1938 met Freud" yields the dimension "1938 m" and "published in
     1955 in London" yields "1955 in". A year is not a measurement. `m` and `in`
     collide with the two commonest words in English museum prose; `cm` and `mm`
     do not.

  B. `_COUNT_RE` requires DIGITS — `set of \\d+` — but museum prose spells small
     numbers out: "a set of ten drypoints", "a suite of fifteen lithographs".
     `drypoints` is also missing from its noun list entirely, so "ten drypoints"
     fails on both counts at once. This is the single commonest way a livre
     d'artiste is described, and it scored zero.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evaluate_story import _DIMENSION_RE, _COUNT_RE, evaluate_story   # noqa: E402


class TestYearsAreNotMeasurements:
    """Defect A."""

    def test_a_year_before_met_is_not_metres(self):
        got = _DIMENSION_RE.findall('In 1938 met Freud in London')
        assert not got, f"'1938 met' read as a dimension: {got}"
        print("  ✅ '1938 met' is not a measurement")

    def test_a_year_before_in_is_not_inches(self):
        got = _DIMENSION_RE.findall('published in 1955 in London by Tériade')
        assert not got, f"'1955 in' read as a dimension: {got}"
        print("  ✅ '1955 in' is not a measurement")

    def test_real_dimensions_still_match(self):
        for s, want in (('the sheet measures 48 x 32 cm', True),
                        ('a plate 320 mm high', True),
                        ('printed in an edition of 200 copies', True),
                        ('48 × 32', True)):
            got = bool(_DIMENSION_RE.findall(s))
            assert got == want, f"{s!r} -> {got}, wanted {want}"
        print("  ✅ real dimensions and quantities still match")


class TestSpelledOutCountsAreCounted:
    """Defect B."""

    def test_ten_drypoints(self):
        got = _COUNT_RE.findall('a set of ten drypoints on sheepskin')
        assert got, "'ten drypoints' found no count — the commonest livre d'artiste form"
        print(f"  ✅ 'ten drypoints' -> {got}")

    def test_suite_of_fifteen_lithographs(self):
        got = _COUNT_RE.findall('a suite of fifteen lithographs')
        assert got, "'fifteen lithographs' found no count"
        print(f"  ✅ 'fifteen lithographs' -> {got}")

    def test_drypoints_is_in_the_noun_list(self):
        got = _COUNT_RE.findall('10 drypoints')
        assert got, "'10 drypoints' found no count — drypoints missing from the nouns"
        print(f"  ✅ '10 drypoints' -> {got}")

    def test_digits_still_work(self):
        assert _COUNT_RE.findall('set of 30 lithographs')
        assert _COUNT_RE.findall('12 etchings')
        print("  ✅ digit forms still match")

    def test_a_bare_number_is_not_a_count(self):
        """Standing check D242 #1 — the fix must be able to be wrong."""
        assert not _COUNT_RE.findall('ten years later he returned')
        assert not _COUNT_RE.findall('the ten commandments')
        print("  ✅ 'ten years' and 'ten commandments' are not counts")


class TestTheRealStoryScoresHigher:
    """End to end: the round-2 best story, which described exactly this."""

    STORY = ("In 1938, Salvador Dalí met Sigmund Freud in London. Decades later, "
             "Dalí paid homage through his 1974-75 work, a set of ten drypoints "
             "and lithographs on sheepskin. This livre d'artiste is now part of "
             "the Museum of Fine Arts, Boston's collection.")

    def test_the_count_is_seen(self):
        ev = evaluate_story(self.STORY)['evidence']['detail']
        assert ev['counts'], f"no count found in the story: {ev['counts']}"
        print(f"  ✅ counts: {ev['counts']}")

    def test_no_phantom_dimension(self):
        ev = evaluate_story(self.STORY)['evidence']['detail']
        bad = [d for d in ev['dimensions'] if '1938' in str(d) or '1974' in str(d)]
        assert not bad, f"a year was scored as a dimension: {bad}"
        print(f"  ✅ dimensions clean: {ev['dimensions']}")

    def test_detail_score_is_not_zero(self):
        assert evaluate_story(self.STORY)['detail'] > 0
        print(f"  ✅ detail = {evaluate_story(self.STORY)['detail']}")


def run_all():
    passed = failed = total = 0
    for cls in (TestYearsAreNotMeasurements, TestSpelledOutCountsAreCounted,
                TestTheRealStoryScoresHigher):
        print(f"\n{'=' * 62}\n  {cls.__name__}\n{'=' * 62}")
        inst = cls()
        for name in sorted(dir(inst)):
            if not name.startswith('test_'):
                continue
            total += 1
            try:
                getattr(inst, name)()
                passed += 1
            except AssertionError as e:
                failed += 1
                print(f"  ❌ {name}: {e}")
            except Exception as e:
                failed += 1
                print(f"  ❌ {name}: EXCEPTION: {type(e).__name__}: {e}")
    print(f"\n{'=' * 62}\n  RESULTS: {passed}/{total} passed, {failed} failed\n{'=' * 62}")
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(run_all())
