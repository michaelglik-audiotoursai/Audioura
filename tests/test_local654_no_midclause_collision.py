#!/usr/bin/env python3
"""test_local654_no_midclause_collision.py — LOCAL-654 guard.

With the cheap arm ON (gpt-4.1-mini), the narrator drops the space after a
sentence-ending period ("…venture into its depths.Thousands of copies…"). Every
sentence splitter in the pipeline keyed on a period FOLLOWED BY WHITESPACE, so the
welded pair travelled as one "sentence"; when a sentence-removing gate dropped the
sentence it had cut, the surviving neighbour fused mid-clause into the shape

    "…the vulnerability of those who venture into Thousands of copies…"
    "…giving him two years to complete Leonardo prepared extensively…"

a lowercase word running straight into a Capitalised word with NO sentence
punctuation between them. The D638 ``lowercase_sentence_join`` detector only knows
a CLOSED set of starters {During, After, Before, In, The, This, When}, so it misses
"Thousands"/"Leonardo". This guard asserts the GENERAL shape, and that no
sentence-removing pass INTRODUCES it.

The fix is at the splitter root (``sentence_split.split_sentences`` recognises the
no-space boundary while still protecting initials, acronyms, decimals and
domains), so every pass that drops a sentence now cuts on the real boundary and
never welds a mid-clause collision — no new afterwards-cleanup pass (D643).

Tests, deterministic, no network:
  1. The hardened splitter splits the mini-model welds and keeps initials /
     acronyms / decimals / domains intact.
  2. Over EVERY tours/fixtures tour plus the five AB3 tours (592, 595, 597, 599,
     600), each sentence-removing pass introduces NO NEW mid-clause collision
     relative to its own input.

Run: python3 -m pytest tests/test_local654_no_midclause_collision.py -q
"""
import glob
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sentence_split import split_sentences  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_FIXTURES = os.path.join(_HERE, "fixtures")
_AB3 = os.path.join(_FIXTURES, "local654")


# ── The GENERAL mid-clause collision shape ──────────────────────────────────
# A lowercase word (3+ letters), a single space, then a Capitalised word whose
# second letter is lowercase (a real word, not an acronym/initial), with the
# lowercase word NOT ending on sentence/clause punctuation. This is the
# "…into Thousands…" shape, free of the D638 detector's closed starter set.
_COLLISION_RE = re.compile(r"(?<![.!?:,;)\]\"'”’])\b([a-z]{3,})\s([A-Z][a-z]{2,})")

# Capitalised words that commonly, legitimately follow a lowercase word WITHIN a
# clause (proper-noun objects): a tour says "lived in Florence", "studied under
# Verrocchio". A collision is a DROPPED-INTO sentence start, not a proper-noun
# object. To keep the guard specific (and avoid flagging ordinary proper nouns),
# we compare each pass's OUTPUT against its INPUT and flag only collisions the
# pass INTRODUCED — a pass that merely passed an existing proper-noun phrase
# through is never blamed.


def collisions(text):
    return {(m.group(1), m.group(2)) for m in _COLLISION_RE.finditer(text or "")}


def _spoken(text):
    """The lines the voice reads — drop structured field lines, as the detectors
    do, so a label like 'Coordinates: 41.8781' is never mistaken for prose."""
    keep = []
    for ln in (text or "").split("\n"):
        if re.match(r"^\s*(Museum Information|Address|Coordinates|Type/Specialty|"
                    r"Specific Examples|Operational Details|Tour-Category|Sources)\s*:",
                    ln):
            continue
        keep.append(ln)
    return "\n".join(keep)


def _load_tours():
    paths = []
    for pat in ("*.txt", "*/*.txt", "*/*/*.txt"):
        paths.extend(glob.glob(os.path.join(_FIXTURES, pat)))
    # De-dup, keep deterministic order.
    return sorted(set(os.path.abspath(p) for p in paths))


class TestHardenedSplitter(unittest.TestCase):
    """The splitter sees the no-space boundary and still protects false ones."""

    def test_mini_model_welds_split(self):
        self.assertEqual(
            split_sentences("those who venture into its depths.Thousands of copies were made."),
            ["those who venture into its depths.", "Thousands of copies were made."])
        self.assertEqual(
            split_sentences("two years to complete it.Leonardo prepared extensively."),
            ["two years to complete it.", "Leonardo prepared extensively."])

    def test_curly_quote_weld_splits(self):
        parts = split_sentences("blend of text and imagery.\u201cAu Soleil\u201d thus advances it.")
        self.assertEqual(len(parts), 2, parts)
        self.assertTrue(parts[1].startswith("\u201cAu Soleil"))

    def test_initial_not_split(self):
        parts = split_sentences(
            "named The Charles S. and Isabella V.This transition mirrored growth.")
        self.assertEqual(len(parts), 1, parts)
        self.assertIn("Isabella V. This transition", " ".join(parts))

    def test_acronym_not_split(self):
        parts = split_sentences("He served under U.S.Grant during the war.")
        self.assertEqual(len(parts), 1, parts)

    def test_decimal_and_domain_not_split(self):
        self.assertEqual(
            split_sentences("It measures 25.7 by 37.9 centimeters today."),
            ["It measures 25.7 by 37.9 centimeters today."])
        self.assertEqual(
            split_sentences("See artic.edu for details and more."),
            ["See artic.edu for details and more."])

    def test_normal_boundary_unchanged(self):
        self.assertEqual(
            split_sentences("First sentence here. Second sentence follows."),
            ["First sentence here.", "Second sentence follows."])


class TestNoPassIntroducesCollision(unittest.TestCase):
    """Every sentence-removing pass, run on every fixture tour plus the five AB3
    tours, introduces NO NEW mid-clause collision relative to its own input."""

    def _passes(self):
        """(name, fn) for each sentence-removing pass, each tour_text -> tour_text.
        Imported lazily so a missing optional module skips just that pass."""
        out = []
        try:
            import story_balance as sbal
            out.append(("LOCAL-620 story_balance",
                        lambda t: sbal.balance_tour_text_work_first(t)[0]))
        except Exception:
            pass
        try:
            import same_title_bleed_guard as stbg
            out.append(("LOCAL-623 same_title",
                        lambda t: stbg.filter_tour_text_same_title(t)[0]))
            out.append(("LOCAL-626 object_type",
                        lambda t: stbg.filter_tour_text_object_type(t)[0]))
        except Exception:
            pass
        try:
            import date_consistency_guard as dcg
            out.append(("LOCAL-626 date_consistency",
                        lambda t: dcg.filter_tour_text_date_consistency(t)[0]))
        except Exception:
            pass
        try:
            import museum_motif_guard as mmg
            out.append(("LOCAL-623 museum_motif",
                        lambda t: mmg.filter_tour_text_museum_motif(t)[0]))
        except Exception:
            pass
        try:
            import spoken_text_hygiene as sth
            out.append(("D523 clean_spoken_text",
                        lambda t: sth.clean_spoken_text(t)[0]))
            out.append(("LOCAL-618 grammar_splice_lint",
                        lambda t: sth.grammar_splice_lint(t, rewrite_fn=None)[0]))
            out.append(("LOCAL-626 strip_recruitment",
                        lambda t: sth.strip_recruitment_sentences(t)[0]))
        except Exception:
            pass
        return out

    def test_fixtures_and_ab3_no_new_collision(self):
        tours = _load_tours()
        self.assertTrue(any(os.path.basename(p).startswith("tour_599") for p in tours),
                        "AB3 tour_599 fixture missing")
        passes = self._passes()
        self.assertGreaterEqual(len(passes), 5, "expected the sentence-removing passes")

        failures = []
        for path in tours:
            with open(path, encoding="utf-8", errors="replace") as f:
                tour = f.read()
            for name, fn in passes:
                try:
                    before = _spoken(tour)
                    after = _spoken(fn(tour))
                except Exception as e:
                    failures.append(f"{os.path.basename(path)} :: {name} raised {e!r}")
                    continue
                new = collisions(after) - collisions(before)
                if new:
                    failures.append(
                        f"{os.path.basename(path)} :: {name} INTRODUCED "
                        f"{sorted(new)[:3]}")
        self.assertEqual(failures, [], "mid-clause collisions introduced:\n  "
                         + "\n  ".join(failures))

    def test_welded_body_through_passes_stays_clean(self):
        """A constructed welded body — exactly the gpt-4.1-mini shape — where the
        first half of the weld is the sentence a gate drops. With the fix the
        split happens on the real boundary, so the surviving neighbour is clean."""
        import date_consistency_guard as dcg
        body = ("Stop 1: The Great Wave of Kanagawa\n\n"
                "The Great Wave of Kanagawa was created in 1831. "
                "It was later recreated in 1950.Thousands of copies were produced. "
                "Hokusai lived from 1760 to 1849.")
        out, rep = dcg.filter_tour_text_date_consistency(body, stop_corpus_dates={1: "1831"})
        self.assertTrue(rep["changed"])
        self.assertNotIn("1950", out)                      # the conflicting sentence went
        self.assertIn("Thousands of copies were produced", out)   # neighbour intact
        self.assertEqual(collisions(_spoken(out)) - collisions(_spoken(body)), set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
