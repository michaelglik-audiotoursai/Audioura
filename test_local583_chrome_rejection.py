#!/usr/bin/env python3
"""test_local583_chrome_rejection.py — Deliverable 2 (LOCAL-583).

The cache must store NO site chrome.

The Griffin field defect: an earlier run (before bs4 was in the local image)
wrote 23 "canonical titles" into venue_corpus Q99108607 that are SITE CHROME —
navigation / account / membership / legal / governance / support labels. The
old plaintext extractor could not tell a <nav>/<footer>/widget label from an
exhibition heading.

Two mechanisms, both tested here:
  1. `exhibition_discovery.reject_chrome_titles` filters the canonical-title
     union BEFORE it is written to venue_corpus — the unambiguous page furniture
     never survives, while real show titles do.
  2. `venue_resolver.CORPUS_VERSION` is bumped so every row the OLD extractor
     wrote (the entire Griffin chrome row) is a cache MISS — ignored, never
     DELETEd.

Fixture: the exact 23 titles from LEAD's backup
`/Volumes/AudiouraSSD/venue_corpus_Q99108607_backup_20261005_1242.sql`.

Run: python3 -m pytest test_local583_chrome_rejection.py -q
"""
import unittest

from exhibition_discovery import is_chrome_title, reject_chrome_titles

VENUE = "griffin museum of photography , Winchester, MA"

# The exact 23 canonical titles from the cached Q99108607 row (LEAD backup).
CACHED_23 = [
    "Calls For Entry", "Griffin Travel", "Exhibition Closed", "Membership Levels",
    "When Are The Member Portfolio Reviews Scheduled", "Our Team",
    "Terms Conditions", "Nepr 2026", "Function Rentals",
    "Bu Masters Show 2026 Traces Pursuing Process", "Intertidal Field Notes",
    "State Of Our Union 2026", "Portfolio Development", "Leave A Legacy",
    "Exhibition Archive", "Griffin Museum Board Of Directors 2", "Members Bulletin",
    "Membership Account", "Earth Wind Fire", "Griffin Salon",
    "Arthur Griffin Archive", "Your Support Matters", "Lua Kobayashi",
]

# The unambiguous site chrome among the 23 — nav / account / membership / legal /
# governance / support / help labels. None of these may survive the filter.
CHROME_IN_23 = {
    "Calls For Entry", "Griffin Travel", "Exhibition Closed", "Membership Levels",
    "When Are The Member Portfolio Reviews Scheduled", "Our Team",
    "Terms Conditions", "Function Rentals", "Portfolio Development",
    "Leave A Legacy", "Exhibition Archive", "Griffin Museum Board Of Directors 2",
    "Members Bulletin", "Membership Account", "Griffin Salon",
    "Your Support Matters",
}

# Real exhibition titles (the LOCAL-580 live Griffin shows, as published). These
# must ALWAYS survive — the filter is not a show blocklist.
REAL_SHOWS = [
    "Lua Kobayashi | The Persistence of Memories",
    "Homage | Robert Frank: The Americans",
    "Tabitha Soren | An Artist Life",
    "Intertidal : Field Notes",
    "BU Masters Show 2026 | Traces: Pursuing Process",
    "Earth, Wind & Fire", "ULTRASOUND", "TLC",
]


class TestChromeRejection(unittest.TestCase):
    def test_all_unambiguous_chrome_rejected(self):
        survivors = set(reject_chrome_titles(CACHED_23, VENUE))
        leaked = CHROME_IN_23 & survivors
        self.assertEqual(
            set(), leaked,
            f"Site chrome survived the filter: {sorted(leaked)}"
        )

    def test_each_chrome_label_classified_as_chrome(self):
        for t in sorted(CHROME_IN_23):
            self.assertTrue(
                is_chrome_title(t, VENUE),
                f"'{t}' is site chrome but was classified as a work"
            )

    def test_real_shows_survive(self):
        """A real show title is NEVER rejected — the filter is safe to run over
        a mixed union."""
        for t in REAL_SHOWS:
            self.assertFalse(
                is_chrome_title(t, VENUE),
                f"Real show '{t}' was wrongly rejected as chrome"
            )
        survivors = reject_chrome_titles(REAL_SHOWS, VENUE)
        self.assertEqual(set(REAL_SHOWS), set(survivors))

    def test_filter_reduces_the_cached_23(self):
        """The 23-title chrome row shrinks drastically — at least the 16
        unambiguous chrome labels are gone."""
        survivors = reject_chrome_titles(CACHED_23, VENUE)
        self.assertLessEqual(
            len(survivors), len(CACHED_23) - len(CHROME_IN_23),
            f"Expected <= {len(CACHED_23) - len(CHROME_IN_23)} survivors, got {len(survivors)}: {survivors}"
        )

    def test_empty_and_blank_rejected(self):
        self.assertTrue(is_chrome_title(""))
        self.assertTrue(is_chrome_title("   "))
        self.assertTrue(is_chrome_title("x"))

    def test_reject_handles_set_and_nonstrings(self):
        mixed = {"Our Team", "Intertidal : Field Notes"}
        out = reject_chrome_titles(mixed, VENUE)
        self.assertIn("Intertidal : Field Notes", out)
        self.assertNotIn("Our Team", out)
        # Non-strings are dropped, not crashed on.
        out2 = reject_chrome_titles(["Our Team", None, 42, "TLC"], VENUE)
        self.assertEqual(["TLC"], out2)


class TestCorpusVersionBump(unittest.TestCase):
    def test_corpus_version_bumped_past_4(self):
        """Bumping CORPUS_VERSION makes every old-extractor row a cache MISS."""
        import venue_resolver
        self.assertGreaterEqual(
            venue_resolver.CORPUS_VERSION, 5,
            "CORPUS_VERSION must be bumped so old chrome rows are ignored"
        )

    def test_cache_get_filters_by_version(self):
        """cache_get query must gate on corpus_version = CORPUS_VERSION."""
        import inspect
        import venue_resolver
        src = inspect.getsource(venue_resolver.cache_get)
        self.assertIn("corpus_version = %s", src)

    def test_cache_put_filters_chrome(self):
        """cache_put must run reject_chrome_titles before writing (defense-in-depth)."""
        import inspect
        import venue_resolver
        src = inspect.getsource(venue_resolver.cache_put)
        self.assertIn("reject_chrome_titles", src)


if __name__ == '__main__':
    unittest.main(verbosity=2)
