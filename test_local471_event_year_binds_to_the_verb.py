#!/usr/bin/env python3
"""test_local471_event_year_binds_to_the_verb.py — the year nearest the verb wins.

Round 4 of the iteration chart rejected **three of eight** stories with the same
reason, and all three rejections are wrong:

    [LOCAL-402] 'Freud' died in 1939, cannot have met in 1974

The sentences:

    "Created in 1974-75, this set of ten drypoints and lithographs on sheepskin
     captures Dalí's fascination with Freud, whom he met only once in a bizarre
     encounter in London in 1938."

**The meeting is dated 1938 in the same sentence.** `check_temporal_coherence` takes
the FIRST year it finds anywhere in the sentence and tests it against the death
dates, so the creation year of the artwork (1974) was applied to the verb `met`.
Freud was alive in 1938; the claim is true and well documented.

D466 fixed the neighbouring case — a PUBLICATION year is not an interaction year.
This is the same error one step further out: **any year in the sentence was treated
as the interaction's year, regardless of which clause it belonged to.** A sentence
that mentions two dates is normal in tour prose; it is the shape you get whenever a
work made at one time refers to an event at another, which is most of an exhibition.

The rule: bind the event year to the interaction verb by proximity. The year nearest
the verb is the one that dates it.

**This regression was CAUSED by an improvement**, which is worth remembering: the
round-3 writer instruction to name what was at stake produced "whom he met only once
in 1938" — `only once` is exactly the stakes marker D469 went looking for, and it
walked straight into this bug.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from temporal_coherence_gate import check_temporal_coherence   # noqa: E402


# The three sentences round 4 threw away, verbatim.
TRUE_SENTENCES = [
    'In 1974-75, Salvador Dalí created a series of drypoints and lithographs on '
    'sheepskin, interpreting Sigmund Freud\'s "Moses and Monotheism." This livre '
    "d'artiste, sold as a set of ten, is a testament to Dalí's fascination with "
    'Freud, whom he met only once in 1938.',

    'Created in 1974-75, this set of ten drypoints and lithographs on sheepskin '
    "captures Dalí's fascination with Freud, whom he met only once in a bizarre "
    'encounter in London in 1938.',

    'This particular piece, created in 1974-75, reflects Dalí\'s fascination with '
    'Freud, whom he met only once in 1938.',
]

# Must still be caught. Freud died 1939; there was no 1974 meeting.
FALSE_SENTENCES = [
    'In 1974, Salvador Dalí collaborated with Sigmund Freud on this book.',
    'Salvador Dalí met Sigmund Freud in 1974 to discuss the illustrations.',
    'In 1974, Salvador Dalí and Sigmund Freud worked together on the plates.',
]


class TestTrueClaimsSurvive:
    """The false rejections measured in round 4."""

    def test_all_three_round4_sentences_survive(self):
        for i, s in enumerate(TRUE_SENTENCES, 1):
            r = check_temporal_coherence(s)
            assert r is None, f"sentence {i} still rejected: {r['reason']}"
        print(f"  ✅ all {len(TRUE_SENTENCES)} round-4 sentences survive")

    def test_the_meeting_year_is_read_not_the_creation_year(self):
        s = ('Created in 1974-75, this work reflects the 1938 meeting when Dalí '
             'met Freud in London.')
        assert check_temporal_coherence(s) is None, check_temporal_coherence(s)
        print("  ✅ 1938 binds to 'met', not 1974")

    def test_order_does_not_matter(self):
        """Same two dates, reversed. Proximity, not position, must decide."""
        s = ('Dalí met Freud in 1938, and the drypoints that came out of it were '
             'created in 1974.')
        assert check_temporal_coherence(s) is None, check_temporal_coherence(s)
        print("  ✅ works with the interaction first")


class TestFalseClaimsAreStillCaught:
    """Standing check D242 #1 — a gate that cannot fire is not a gate."""

    def test_all_three_false_sentences_rejected(self):
        for i, s in enumerate(FALSE_SENTENCES, 1):
            r = check_temporal_coherence(s)
            assert r is not None, f"false sentence {i} NOT caught: {s}"
            assert '1939' in r['reason'], r['reason']
        print(f"  ✅ all {len(FALSE_SENTENCES)} impossible claims still rejected")

    def test_the_nearest_year_is_used_even_when_it_convicts(self):
        """Proximity must not become a way to smuggle a false claim past."""
        s = ('The book was printed in 1938, but Dalí met Freud in 1974 to plan it.')
        r = check_temporal_coherence(s)
        assert r is not None, "nearest-year rule let a false claim through"
        print(f"  ✅ still rejects: {r['reason']}")

    def test_d466_publication_rule_still_holds(self):
        """The Juan Gris case must not regress."""
        s = ('"Au Soleil du Plafond," created by Juan Gris in collaboration with '
             'Pierre Reverdy, was published in 1955.')
        assert check_temporal_coherence(s) is None, check_temporal_coherence(s)
        print("  ✅ D466 Gris/Reverdy still survives")


def run_all():
    passed = failed = total = 0
    for cls in (TestTrueClaimsSurvive, TestFalseClaimsAreStillCaught):
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
