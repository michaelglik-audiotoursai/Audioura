#!/usr/bin/env python3
"""test_local468_valuation_counts_the_object.py — the index must see the object.

D467 measured the iteration curve on MFA Unbound stop 2 and found the plateau was
the METRIC, not the material. `valuation_index` was

    sentence_count*10 (<=30) + agency*10 (<=30) + stakes*12 (<=25)
    + grounded_fraction*15

Three defects, each tested here, each verified RED before the fix:

  A. **The object is not in the formula.** `detail` — does a sentence name a
     physical property of the thing in the case — is computed by `_score_detail`
     and then never added. That is measure 4 of `STORY_GATE_TIERS.md` and the
     weakness Michael has raised more often than any other (D449).

  B. **Groundedness punishes specificity.** Measured: raising the snippet cap
     5 -> 20 on the best iteration moved detail 0 -> 29 and historic 46 -> 66 —
     the story finally said "drypoints and lithographs on sheepskin" — and the
     index FELL 61 -> 50, because those proper nouns are absent from the museum's
     own webpage. Absence of evidence, scored as evidence against: the same
     mistake D466 fixed in the temporal gate, one layer up.

  C. **Sentences past the third are free.** 3*10 already caps that term, so
     Michael's "3-5 sentences, larger for the best one" scores as if every story
     were three.

Michael's ruling, 2026-08-18, on the weighting: continue development, and the
default stands unless he says otherwise — the object connection is first-class
and equal to agency; groundedness drops to a tiebreak.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evaluate_story import evaluate_story, _compute_valuation_index   # noqa: E402
from story_opportunity_scan import split_sentences                    # noqa: E402


# The two real stories from the D467 cap experiment, verbatim.
GENERIC = (
    "In 1938, Salvador Dalí met Sigmund Freud in London, a meeting that left a "
    "lasting impression on the surrealist artist. Dalí later illustrated Freud's "
    "controversial work, \"Moses and Monotheism,\" which proposed that Moses was "
    "actually Egyptian. The work is part of the \"Picasso, Miró, Dalí: Unbound\" "
    "exhibition at the Museum of Fine Arts, Boston."
)

# Same facts, but it names the physical object in the case.
OBJECT = (
    "In 1938, Salvador Dalí met Sigmund Freud in London, a meeting that left a "
    "lasting impression on the surrealist artist. Dalí later illustrated Freud's "
    "controversial work, \"Moses and Monotheism,\" which proposed that Moses was "
    "actually Egyptian. Through Dalí's drypoints and lithographs printed on "
    "sheepskin, visitors can see how he interpreted Freud's thesis. The work is "
    "part of the \"Picasso, Miró, Dalí: Unbound\" exhibition at the Museum of "
    "Fine Arts, Boston."
)

# A corpus that mentions almost nothing in the stories — the museum page case.
THIN_CORPUS = "Picasso, Miró, Dalí: Unbound. Gallery 184. Livres d'artiste."


class TestObjectDetailIsInTheFormula:
    """Defect A."""

    def test_naming_the_object_raises_the_index(self):
        g = evaluate_story(GENERIC)['valuation_index']
        o = evaluate_story(OBJECT)['valuation_index']
        assert o > g, (f"naming the object did not raise the index: "
                       f"generic={g} object={o}")
        print(f"  ✅ object story {o} > generic story {g}")

    def test_detail_score_actually_differs(self):
        """Guard: if _score_detail cannot tell these apart the test above is void."""
        g = evaluate_story(GENERIC)['detail']
        o = evaluate_story(OBJECT)['detail']
        assert o > g, f"_score_detail cannot separate them: {g} vs {o}"
        print(f"  ✅ detail {g} -> {o}")

    def test_detail_term_is_reported_in_evidence(self):
        ev = evaluate_story(OBJECT)['evidence']['valuation']
        assert 'detail_score' in ev, f"no detail term in evidence: {sorted(ev)}"
        assert ev['detail_score'] > 0, ev
        print(f"  ✅ evidence carries detail_score={ev['detail_score']}")


class TestGroundednessIsATiebreakNotAPenalty:
    """Defect B. A thin corpus must not be able to sink a specific story."""

    def test_thin_corpus_does_not_invert_the_ranking(self):
        g = evaluate_story(GENERIC, corpus=THIN_CORPUS)['valuation_index']
        o = evaluate_story(OBJECT, corpus=THIN_CORPUS)['valuation_index']
        assert o > g, (f"thin corpus inverted the ranking: generic={g} object={o} "
                       f"— this is the D467 failure")
        print(f"  ✅ with a thin corpus, object {o} still beats generic {g}")

    def test_corpus_absence_costs_less_than_the_object_is_worth(self):
        """The whole D467 finding in one assertion."""
        with_c = evaluate_story(OBJECT, corpus=THIN_CORPUS)['valuation_index']
        no_c = evaluate_story(OBJECT)['valuation_index']
        assert no_c - with_c <= 10, (
            f"an unmentioning corpus costs {no_c - with_c} points; "
            f"groundedness is still a penalty, not a tiebreak")
        print(f"  ✅ thin-corpus cost is {no_c - with_c} points (<=10)")

    def test_a_rich_corpus_still_helps(self):
        """The fix must not make groundedness inert — it should still reward."""
        rich = OBJECT + " Gallery 184 livres d'artiste."
        bare = evaluate_story(OBJECT)['valuation_index']
        good = evaluate_story(OBJECT, corpus=rich)['valuation_index']
        assert good >= bare, f"a corpus that confirms everything did not help: {bare} -> {good}"
        print(f"  ✅ confirming corpus: {bare} -> {good}")


class TestSentencesPastTheThirdAreNotFree:
    """Defect C. Michael's '3-5 sentences, larger for the best one'."""

    def test_a_fourth_substantive_sentence_is_worth_something(self):
        three = evaluate_story(GENERIC)
        four = evaluate_story(OBJECT)
        assert len(split_sentences(OBJECT)) > len(split_sentences(GENERIC)), \
            "fixture no longer differs in sentence count"
        assert four['valuation_index'] > three['valuation_index'], \
            "a fourth sentence carrying real content scored nothing"
        print(f"  ✅ 4 sentences {four['valuation_index']} > "
              f"3 sentences {three['valuation_index']}")


class TestTheScaleStillBehaves:
    """Standing check D242 #1 — a metric that cannot go down is not a metric."""

    def test_empty_story_is_zero(self):
        assert evaluate_story('')['valuation_index'] == 0
        print("  ✅ empty story scores 0")

    def test_index_stays_in_range(self):
        for s in (GENERIC, OBJECT, OBJECT * 3, 'A short line.'):
            v = evaluate_story(s, corpus=THIN_CORPUS)['valuation_index']
            assert 0 <= v <= 100, f"out of range: {v}"
        print("  ✅ index stays within 0-100 on all fixtures")

    def test_a_contentless_story_scores_low(self):
        junk = ("This is a place. It is here. You can look at it. "
                "It exists. There is a thing.")
        v = evaluate_story(junk)['valuation_index']
        assert v < evaluate_story(OBJECT)['valuation_index'], \
            "contentless prose scored as well as the object story"
        print(f"  ✅ contentless prose scores {v}")

    def test_compute_signature_still_callable(self):
        """Other callers use _compute_valuation_index directly."""
        total, ev = _compute_valuation_index(OBJECT, split_sentences(OBJECT), '')
        assert 0 <= total <= 100 and isinstance(ev, dict)
        print(f"  ✅ _compute_valuation_index -> {total}")


def run_all():
    passed = failed = total = 0
    for cls in (TestObjectDetailIsInTheFormula,
                TestGroundednessIsATiebreakNotAPenalty,
                TestSentencesPastTheThirdAreNotFree,
                TestTheScaleStillBehaves):
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
