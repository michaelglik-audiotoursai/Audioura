#!/usr/bin/env python3
"""test_local476 — the retry must not be able to paraphrase past the gate.

D474 recorded the failure. On the 2026-08-18 release run the temporal gate
correctly rejected

    "In 1955, the collaboration between Juan Gris and Pierre Reverdy…"

because Gris died in 1927. The LOCAL-474 retry then told the model not to repeat
**or rephrase** it, and the model rephrased it anyway:

    "In 1955, Juan Gris and Pierre Reverdy embarked on a profound artistic
     collaboration…"

Same false claim, and it **shipped**, because `_INTERACTION_PATTERNS` covered
`collaborated with` / `collaboration between` but no nominalised form. The gate
never reached the dates.

The lesson is structural: telling a model what was rejected hands it what it needs
to route around the detector. Our own retry loop now adversarially probes our own
gate, so this file has two jobs and both matter equally —

  * the nominalised forms must be caught, AND
  * adding them must not start rejecting true sentences, which is the failure mode
    this entire session has been removing (D466, D467, D469, D471, D473, D475).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from temporal_coherence_gate import check_temporal_coherence, _INTERACTION_RE  # noqa: E402

THE_EVASION = ('In 1955, Juan Gris and Pierre Reverdy embarked on a profound '
               'artistic collaboration, culminating in "Au Soleil du Plafond."')


class TestTheEvasionIsCaught:

    def test_the_shipped_sentence_is_now_rejected(self):
        r = check_temporal_coherence(THE_EVASION)
        assert r is not None, "the paraphrase still evades the gate"
        assert '1927' in r['reason'], r['reason']
        print(f"  ✅ {r['reason']}")

    def test_other_nominalised_forms(self):
        for s in ('In 1955, Gris and Reverdy formed a partnership on this book.',
                  'In 1955, Gris and Reverdy struck up a friendship.',
                  'In 1955, Gris and Reverdy entered into a collaboration.'):
            assert check_temporal_coherence(s) is not None, f"missed: {s}"
        print("  ✅ formed / struck up / entered into all caught")

    def test_the_verb_phrase_is_reported(self):
        m = _INTERACTION_RE.search(THE_EVASION)
        assert m and 'collaboration' in m.group(0), m
        print(f"  ✅ matched: {m.group(0)!r}")


class TestNoNewFalseRejections:
    """Adding patterns must not start convicting true sentences."""

    SAFE = [
        # A bare relationship noun with no governing verb — must not fire.
        "The collaboration exemplifies the exhibition's argument that a book "
        "can be an integrated artwork.",
        # A real, correctly dated partnership.
        'Gris and Reverdy formed a partnership in 1916 that shaped Cubist '
        'bookmaking.',
        # D466 — publication year is not an interaction year.
        '"Au Soleil du Plafond," created by Juan Gris in collaboration with '
        'Pierre Reverdy, was published in 1955.',
        # D471 — the year nearest the verb wins.
        "Created in 1974-75, this set captures Dalí's fascination with Freud, "
        "whom he met only once in 1938.",
        # One person only.
        'In 1955, Pierre Reverdy published the text with Éditions Verve.',
    ]

    def test_all_safe_sentences_survive(self):
        for s in self.SAFE:
            r = check_temporal_coherence(s)
            assert r is None, f"FALSE REJECTION: {r['reason']}\n  on: {s}"
        print(f"  ✅ all {len(self.SAFE)} true sentences survive")

    def test_the_real_impossibility_is_still_caught(self):
        """Standing check D242 #1."""
        r = check_temporal_coherence(
            'In 1974, Salvador Dalí collaborated with Sigmund Freud on this book.')
        assert r is not None and '1939' in r['reason'], r
        print(f"  ✅ still rejects: {r['reason']}")


def run_all():
    passed = failed = total = 0
    for cls in (TestTheEvasionIsCaught, TestNoNewFalseRejections):
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
