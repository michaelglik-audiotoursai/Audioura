#!/usr/bin/env python3
"""test_local667_title_split.py — LOCAL-667 title-splitting guard.

The Ho Chi Minh City Museum of Fine Arts has ONE SPARQL work whose English
Wikidata label is "North Central South Spring Garden" (reordered translation of
"Vườn xuân Bắc Trung Nam"; EN altLabel "Central South and North Spring Garden").
gpt-4.1-mini, handed that one title as a guidance hint, atomised it into FIVE
candidate POIs — North / Central / South / Spring Garden / Garden — and D1v2
verified only the fragment "Spring Garden", dropping the other four, so one real
work shipped as "1 of 5".

These tests pin the deterministic collapse guard: fragments of ONE known title
collapse into that single canonical candidate, while genuinely distinct works are
never merged, and a title is never invented.

Run: python3 -m pytest test_local667_title_split.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from candidate_collapse_guard import (  # noqa: E402
    collapse_split_title_candidates,
    quote_multiword_hint_titles,
    _is_fragment_of,
    _norm_tokens,
    _content_tokens,
)

_CANON = "North Central South Spring Garden"


def _names(pois):
    return [p["name"] for p in pois]


class TestHCMCSplitCollapses(unittest.TestCase):
    """The exact HCMC failure: five fragments of one title → one candidate."""

    def test_five_fragments_collapse_to_one(self):
        pois = [
            {"name": "North", "address": "97A Pho Duc Chinh"},
            {"name": "Central", "address": "97A Pho Duc Chinh"},
            {"name": "South", "address": "97A Pho Duc Chinh"},
            {"name": "Spring Garden", "address": "97A Pho Duc Chinh"},
            {"name": "Garden", "address": "97A Pho Duc Chinh"},
        ]
        out, collapses = collapse_split_title_candidates(pois, {_CANON})
        self.assertEqual(len(out), 1, _names(out))
        self.assertEqual(out[0]["name"], _CANON)
        self.assertEqual(len(collapses), 1)
        self.assertEqual(set(collapses[0]["fragments"]),
                         {"North", "Central", "South", "Spring Garden", "Garden"})
        # The collapsed POI keeps the fragment's address.
        self.assertEqual(out[0]["address"], "97A Pho Duc Chinh")

    def test_and_comma_clause_split_collapses(self):
        """The altLabel form split on 'and' / commas also collapses."""
        canon = "Central South and North Spring Garden"
        pois = [
            {"name": "Central South and North"},
            {"name": "Spring Garden"},
        ]
        out, collapses = collapse_split_title_candidates(pois, {canon})
        self.assertEqual(len(out), 1, _names(out))
        self.assertEqual(out[0]["name"], canon)

    def test_collapsed_title_is_from_known_set_only(self):
        """A collapse target must already be a known canonical/SPARQL title; the
        guard never invents a title from the fragments alone."""
        pois = [{"name": "North"}, {"name": "Central"}, {"name": "South"}]
        # No known title → nothing to collapse into, list unchanged.
        out, collapses = collapse_split_title_candidates(pois, set())
        self.assertEqual(_names(out), ["North", "Central", "South"])
        self.assertEqual(collapses, [])


class TestNoFalseCollapse(unittest.TestCase):
    """Distinct, well-documented works are never merged — no regression."""

    def test_courtauld_distinct_works_untouched(self):
        canon = {
            "A Bar at the Folies-Bergère",
            "Self-Portrait with Bandaged Ear",
            "Nevermore",
            "Te Rerioa",
        }
        pois = [{"name": t} for t in sorted(canon)]
        out, collapses = collapse_split_title_candidates(pois, canon)
        self.assertEqual(sorted(_names(out)), sorted(canon))
        self.assertEqual(collapses, [])

    def test_single_fragment_not_collapsed(self):
        """A lone fragment is left for the ordinary matcher — collapsing one
        candidate changes nothing and could hide a real one-word work."""
        pois = [{"name": "Spring Garden"}, {"name": "The Fisherman"}]
        out, collapses = collapse_split_title_candidates(pois, {_CANON})
        self.assertEqual(collapses, [])
        self.assertEqual(sorted(_names(out)), ["Spring Garden", "The Fisherman"])

    def test_two_word_title_is_not_a_collapse_target(self):
        """A short (2-content-word) title is not atomisable the way a long
        list-like one is; it must not be used as a collapse target (which could
        merge two short distinct works)."""
        pois = [{"name": "The Kiss"}, {"name": "The Thinker"}]
        out, collapses = collapse_split_title_candidates(pois, {"The Kiss", "The Thinker"})
        self.assertEqual(collapses, [])
        self.assertEqual(len(out), 2)

    def test_unrelated_candidates_pass_through(self):
        pois = [{"name": "Lotus Pond"}, {"name": "The Dance of the Dragon"}]
        out, collapses = collapse_split_title_candidates(pois, {_CANON})
        self.assertEqual(collapses, [])
        self.assertEqual(len(out), 2)

    def test_two_different_long_titles_not_cross_merged(self):
        """Fragments of DIFFERENT long titles stay apart (each collapses to its
        own title, not into a single merged candidate)."""
        canon = {"North Central South Spring Garden",
                 "The Dance of the Phoenix and the Dragon"}
        pois = [
            {"name": "North"},
            {"name": "Spring Garden"},
            {"name": "The Dance of the Phoenix"},
            {"name": "the Dragon"},
        ]
        out, collapses = collapse_split_title_candidates(pois, canon)
        titles = {c["title"] for c in collapses}
        self.assertEqual(titles, canon)
        self.assertEqual(len(out), 2, _names(out))


class TestFragmentPredicate(unittest.TestCase):
    def test_contiguous_subsequence(self):
        toks = _norm_tokens(_CANON)
        content = _content_tokens(_CANON)
        self.assertTrue(_is_fragment_of("Spring Garden", toks, content))
        self.assertTrue(_is_fragment_of("North", toks, content))
        self.assertTrue(_is_fragment_of("North Central", toks, content))

    def test_full_title_is_not_a_fragment(self):
        toks = _norm_tokens(_CANON)
        content = _content_tokens(_CANON)
        self.assertFalse(_is_fragment_of(_CANON, toks, content))

    def test_outside_word_is_not_a_fragment(self):
        toks = _norm_tokens(_CANON)
        content = _content_tokens(_CANON)
        self.assertFalse(_is_fragment_of("Fisherman", toks, content))
        self.assertFalse(_is_fragment_of("Lotus Pond", toks, content))


class TestQuoteHints(unittest.TestCase):
    def test_multiword_quoted_singleword_not(self):
        out = quote_multiword_hint_titles(["North Central South Spring Garden", "David"])
        self.assertEqual(out, ['"North Central South Spring Garden"', "David"])

    def test_already_quoted_not_double_quoted(self):
        out = quote_multiword_hint_titles(['"A Bar at the Folies-Bergère"'])
        self.assertEqual(out, ['"A Bar at the Folies-Bergère"'])

    def test_empty_dropped(self):
        self.assertEqual(quote_multiword_hint_titles(["", "  ", "Nevermore"]), ["Nevermore"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
