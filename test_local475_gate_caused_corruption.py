#!/usr/bin/env python3
"""test_local475 — the gates must not produce broken English.

Two defects visible in `TOUR_MFA_RELEASE_20260818_1532.txt`, both produced BY the
gates rather than by the model, and both worse for a listener than a fact error
because they are audible instantly:

    "In 1971 known for his distinct surrealist imagery, created
     'Le Lézard aux plumes d'or'"                        <- Miró's name deleted

    "bound in the Louis Broder, a mid-20th century French
     publisher,'s vellum"                                <- gloss spliced into 's

Four causes, all in `unglossed_reference_gate.py`:

  A. `_is_well_known` returns **False for Joan Miró and Salvador Dalí** while
     returning True for Picasso and Freud. `_WELL_KNOWN` holds 80 entries and has
     `picasso` and `freud` but neither `miró` nor `dalí` — the other two headline
     artists of this very exhibition — and the comparison does not accent-fold, so
     even adding `miro` would not match `Miró`. **Standing check #4 (D243), which
     has now caught something for the third time.**

  B. The possessive guard in `_insert_composed_gloss` reads

         if after.startswith("'s ") or after.startswith("'s "):

     — the SAME ASCII literal twice. The curly apostrophe GPT actually emits is
     not covered, which is exactly how the Louis Broder gloss got spliced into
     `’s`. The comment above it says "Handles possessive".

  C. `_degrade_sentence_is_wellformed` has seven guards and passes
     "In 1971 known for his distinct surrealist imagery, created ..." — a sentence
     with no subject. Dropping a name from the middle of a sentence is exactly the
     operation that produces this, and no guard looks for it.

  D. The stop's OWN artist should never be a candidate for degrading. Miró is not
     an incidental reference in a stop about a Miró book; he is the subject.
     Independent of A, because the next tour will have an artist nobody has heard
     of and the same thing will happen.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unglossed_reference_gate import (            # noqa: E402
    _is_well_known,
    _insert_composed_gloss,
    _degrade_sentence_is_wellformed,
    detect_unglossed_references,
)

BROKEN = ('In 1971 known for his distinct surrealist imagery, created '
          '"Le Lézard aux plumes d\'or," an illustrated book.')
INTACT = ('In 1971 Joan Miró, known for his distinct surrealist imagery, '
          'created "Le Lézard aux plumes d\'or," an illustrated book.')
POSSESSIVE_CURLY = ('The lithographs, printed on Rives paper and bound in the '
                    'Louis Broder’s vellum, showcase colour.')


class TestWellKnownAccentFolding:
    """Defect A."""

    def test_the_exhibition_headliners_are_well_known(self):
        for n in ('Joan Miró', 'Miró', 'Salvador Dalí', 'Dalí'):
            assert _is_well_known(n), f"{n} not recognised as well known"
        print("  ✅ Miró and Dalí recognised")

    def test_unaccented_spellings_also_match(self):
        for n in ('Joan Miro', 'Salvador Dali'):
            assert _is_well_known(n), f"{n} not recognised"
        print("  ✅ unaccented spellings match too")

    def test_the_previously_working_names_still_work(self):
        for n in ('Pablo Picasso', 'Picasso', 'Sigmund Freud'):
            assert _is_well_known(n), n
        print("  ✅ Picasso and Freud unaffected")

    def test_an_obscure_name_is_still_not_well_known(self):
        """Standing check D242 #1 — this must be able to be wrong."""
        for n in ('Boris Fridman', 'Louis Broder', 'Mourlot Frères'):
            assert not _is_well_known(n), f"{n} wrongly treated as well known"
        print("  ✅ obscure names still need a gloss")


class TestPossessiveGuardHandlesCurlyApostrophes:
    """Defect B."""

    def test_curly_possessive_is_not_spliced(self):
        out = _insert_composed_gloss(POSSESSIVE_CURLY, 'Louis Broder',
                                     'a mid-20th century French publisher')
        assert out == POSSESSIVE_CURLY, f"gloss spliced into a possessive:\n  {out}"
        print("  ✅ curly possessive left alone")

    def test_ascii_possessive_still_guarded(self):
        s = POSSESSIVE_CURLY.replace('’', "'")
        out = _insert_composed_gloss(s, 'Louis Broder', 'a French publisher')
        assert out == s, out
        print("  ✅ ascii possessive still guarded")

    def test_a_normal_gloss_still_inserts(self):
        s = 'The book was printed by Mourlot Frères in Paris.'
        out = _insert_composed_gloss(s, 'Mourlot Frères', 'a Paris lithography studio')
        assert 'a Paris lithography studio' in out and out != s
        print(f"  ✅ normal insertion still works")


class TestDegradeMustNotStripTheSubject:
    """Defect C."""

    def test_the_shipped_broken_sentence_is_rejected(self):
        assert not _degrade_sentence_is_wellformed(BROKEN), \
            "the subjectless sentence passed all guards"
        print("  ✅ subjectless sentence rejected")

    def test_the_intact_sentence_still_passes(self):
        assert _degrade_sentence_is_wellformed(INTACT), \
            "the guard now rejects a perfectly good sentence"
        print("  ✅ intact sentence still passes")

    def test_other_good_sentences_are_not_rejected(self):
        for s in ('In 1955, Juan Gris and Pierre Reverdy worked together on the book.',
                  'The lithographs were printed on Arches paper in Paris.',
                  'In 1938 Freud fled Vienna for London.',
                  'By 1974, the portfolio was complete.'):
            assert _degrade_sentence_is_wellformed(s), f"wrongly rejected: {s}"
        print("  ✅ four good sentences unaffected")


class TestTheStopsOwnArtistIsExempt:
    """Defect D."""

    def test_the_artist_is_not_a_candidate(self):
        text = ('In 1971 Anonymous Painter, known for bold colour, created this '
                'book with Mourlot Frères in Paris.')
        refs = detect_unglossed_references(text, ['A Book'], exempt=['Anonymous Painter'])
        names = [r['entity'] for r in refs]
        assert not any('Anonymous Painter' in n for n in names), names
        print(f"  ✅ artist exempt; still detected: {names}")

    def test_others_are_still_detected_when_artist_is_exempt(self):
        text = ('In 1971 Anonymous Painter, known for bold colour, created this '
                'book with Mourlot Frères in Paris.')
        refs = detect_unglossed_references(text, ['A Book'], exempt=['Anonymous Painter'])
        assert refs, "exempting the artist suppressed every other reference too"
        print(f"  ✅ {len(refs)} other reference(s) still detected")

    def test_exempt_is_optional(self):
        """Existing callers pass two arguments and must keep working."""
        refs = detect_unglossed_references('Mourlot Frères printed it.', ['A Book'])
        assert isinstance(refs, list)
        print("  ✅ two-argument call still valid")


def run_all():
    passed = failed = total = 0
    for cls in (TestWellKnownAccentFolding, TestPossessiveGuardHandlesCurlyApostrophes,
                TestDegradeMustNotStripTheSubject, TestTheStopsOwnArtistIsExempt):
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
