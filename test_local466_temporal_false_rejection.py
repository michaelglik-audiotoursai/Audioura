#!/usr/bin/env python3
"""test_local466_temporal_false_rejection.py — the gate must not reject TRUE claims.

Michael's mission, 2026-08-18: *"improve the validators so the good stories for
humans are not dismissed as inaccurate when there is no evidence that they are."*

`test_local402_temporal_coherence.py` is 11/11 green and tests only that the gate
FIRES on impossible relations. It has no case in which firing would be wrong, so
it cannot detect a false rejection. This file supplies that half.

THE PRODUCTION FAILURE — verbatim from `local413_run_output.log`:

    [LOCAL-402] coherence reject: '"Au Soleil du Plafond," created by Juan Gris
    in collaboration with Pierre Reverd' — 'Juan Gris' died in 1887, cannot have
    collaboration with in 1955

Juan Gris died in **1927**. 1887 is his BIRTH year, and `_KNOWN_DATES` has both
correct. The claim the gate threw away is true and documented: Gris made the
lithographs for `Au Soleil du Plafond` to Pierre Reverdy's text, published 1955.

Two independent defects put it there. Each gets a test.

  A. `_DEATH_PATTERNS[0]` is `(?:died|d\\.?)\\s*(?:in\\s*)?(\\d{4})`. The `d\\.?`
     branch has an optional period and `\\s*` permits zero width, so the final
     `d` of ANY word before a year reads as "died": "published 1887",
     "printed 1971", "signed 1916". Worse, it matches left-to-right, so
     "Gris signed 1916 and died 1927" yields 1916 and the real death year is
     never reached. `_BIRTH_PATTERNS[0]` has the same flaw via `b\\.?` ("Feb 1955").

  B. `get_person_dates` returns the snippet result whenever it is non-empty. A
     snippet that yields only `{'birth': 1887}` therefore SHADOWS `_KNOWN_DATES`,
     which holds the correct `{'birth': 1887, 'death': 1927}`. Partial evidence
     silently outranks a known answer.

Both are the D423/D243 shape: an instrument that reports a confident falsehood.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from temporal_coherence_gate import (          # noqa: E402
    check_temporal_coherence,
    extract_person_dates_from_snippets,
    get_person_dates,
    _BIRTH_PATTERNS,
    _DEATH_PATTERNS,
)


class TestDeathRegexDoesNotEatOrdinaryWords:
    """Defect A. A word ending in 'd' before a year is not a death date."""

    def _death(self, text):
        for pat in _DEATH_PATTERNS:
            m = pat.search(text)
            if m:
                return int(m.group(1))
        return None

    def test_published_is_not_died(self):
        got = self._death('Juan Gris published 1887 lithographs')
        assert got is None, f"'published 1887' read as death={got}"
        print("  ✅ 'published 1887' is not a death date")

    def test_printed_is_not_died(self):
        got = self._death('Le Lezard was printed 1971 by Mourlot Freres')
        assert got is None, f"'printed 1971' read as death={got}"
        print("  ✅ 'printed 1971' is not a death date")

    def test_real_death_wins_over_earlier_d_word(self):
        """'signed 1916 and died 1927' must yield 1927, not 1916."""
        got = self._death('Gris signed 1916 and died 1927')
        assert got == 1927, f"expected 1927, got {got}"
        print("  ✅ 'signed 1916 and died 1927' -> 1927")

    def test_parenthesised_lifespan_still_works(self):
        """The fix must not cost us the case the gate was built for."""
        got = self._death('Juan Gris (1887-1927), Spanish cubist')
        assert got == 1927, f"expected 1927, got {got}"
        print("  ✅ '(1887-1927)' -> 1927")

    def test_explicit_died_still_works(self):
        assert self._death('Sigmund Freud died in 1939 in London') == 1939
        assert self._death('Freud, d. 1939') == 1939
        print("  ✅ 'died in 1939' and 'd. 1939' both -> 1939")

    def test_birth_regex_does_not_eat_month_abbreviations(self):
        """Defect A, birth side: 'Feb 1955' must not be a birth year."""
        got = None
        for pat in _BIRTH_PATTERNS[:1]:      # the `born|b\.?` pattern only
            m = pat.search('Exhibition opened Feb 1955 at the MFA')
            if m:
                got = int(m.group(1))
        assert got is None, f"'Feb 1955' read as birth={got}"
        print("  ✅ 'Feb 1955' is not a birth date")


class TestKnownDatesAreNotShadowedByPartialSnippets:
    """Defect B. Partial snippet evidence must not outrank a known answer."""

    SNIPPETS = [{
        'title': 'Juan Gris',
        'snippet': 'Juan Gris, Spanish painter, was born 1887 in Madrid '
                   'and worked in Paris.',
        'url': '',
    }]

    def test_snippets_alone_are_partial(self):
        got = extract_person_dates_from_snippets(self.SNIPPETS, 'Juan Gris')
        assert got is not None and 'death' not in got, \
            f"fixture no longer partial: {got}"
        print(f"  ✅ snippets yield only {got} — no death year")

    def test_known_death_survives_a_partial_snippet(self):
        got = get_person_dates('Juan Gris', self.SNIPPETS)
        assert got.get('death') == 1927, \
            f"known death 1927 shadowed by snippets: {got}"
        assert got.get('birth') == 1887, f"birth lost: {got}"
        print(f"  ✅ merged: {got}")

    def test_snippet_wins_where_it_actually_knows(self):
        """Merging must not make the table override live evidence it lacks."""
        snips = [{'title': 'Pierre Reverdy (1889-1960)',
                  'snippet': 'French poet.', 'url': ''}]
        got = get_person_dates('Reverdy', snips)
        assert got.get('death') == 1960, f"snippet death lost: {got}"
        print(f"  ✅ Reverdy from snippets: {got}")


class TestTheProductionSentenceIsNotRejected:
    """The whole point: this true sentence must survive the gate."""

    SENTENCE = ('"Au Soleil du Plafond," created by Juan Gris in collaboration '
                'with Pierre Reverdy, was published in 1955.')

    SNIPPETS = [
        {'title': 'Juan Gris', 'snippet': 'Juan Gris, Spanish painter, was '
                                          'born 1887 in Madrid.', 'url': ''},
        {'title': 'Au Soleil du Plafond', 'snippet': 'Published 1955 by '
                                                     'Teriade.', 'url': ''},
    ]

    def test_not_rejected_with_snippets(self):
        r = check_temporal_coherence(self.SENTENCE, snippets=self.SNIPPETS)
        assert r is None, f"TRUE claim rejected: {r['reason']}"
        print("  ✅ Gris/Reverdy 1955 survives (with snippets)")

    def test_not_rejected_without_snippets(self):
        r = check_temporal_coherence(self.SENTENCE)
        assert r is None, f"TRUE claim rejected: {r['reason']}"
        print("  ✅ Gris/Reverdy 1955 survives (table only)")

    def test_the_gate_still_catches_the_real_impossibility(self):
        """Standing check D242 #1 — a test that cannot fail is not evidence."""
        false_claim = ('In 1974, Salvador Dalí collaborated with Sigmund Freud '
                       'on this book.')
        r = check_temporal_coherence(false_claim)
        assert r is not None, "gate no longer catches Dalí/Freud 1974"
        assert '1939' in r['reason'], r['reason']
        print(f"  ✅ still rejects: {r['reason']}")


def run_all():
    passed = failed = total = 0
    for cls in (TestDeathRegexDoesNotEatOrdinaryWords,
                TestKnownDatesAreNotShadowedByPartialSnippets,
                TestTheProductionSentenceIsNotRejected):
        print(f"\n{'=' * 60}\n  {cls.__name__}\n{'=' * 60}")
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
                print(f"  ❌ {name}: EXCEPTION: {e}")

    print(f"\n{'=' * 60}")
    print(f"  RESULTS: {passed}/{total} passed, {failed} failed")
    print(f"{'=' * 60}")
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(run_all())
