"""test_local826b_cached_canon_and_stop4.py — LOCAL-826B.

Two field defects, exercised against the EXACT data copied read-only from the
live Mac DB (tests/fixtures/local826b/):

  (1) MUSEUM CANON ON THE CACHED PATH. The LOCAL-826 matcher fixes verified the
      Orsay famous four and kept Église ≠ Chaumes on a FRESH SPARQL fetch, but on
      the real cache-HIT path they still DROPPED. Root cause (proven here): the
      cached venue_corpus row for Q23402 (written by an OLD miner) carries a work
      set that is MISSING the famous works entirely — matching against a set that
      never contained them drops them and wrong-accepts Chaumes on the shared
      toponym. The refreshed venue_works_cache (300 works) HAS them, so once the
      matchable set is rebuilt from it the 826 matcher verifies all four and keeps
      Église ≠ Chaumes. The fix bumps CORPUS_VERSION so a stale corpus is a cache
      MISS and is rebuilt from the refreshed works cache.

      These tests run the REAL matcher (venue_resolver.build_dynamic_aliases +
      story_miner.build_bilingual_map_from_sparql + match_candidate_to_canonical)
      against both snapshots — no network, no DB.

  (2) RIJKSMUSEUM STOP 4. The stop editor glued the Merry Drinker's whole narrated
      body (headerless) after Stop 3's Directions; the LOCAL-801 de-splice then
      DROPPED it as if it were a duplicate preview — deleting a real, paid,
      narrated stop — and the delivered tour shipped two "Stop 4:" headers (one a
      truncated title), the Great Wave mis-numbered Stop 4. The de-splice is now
      duplicate-aware: a unique lost-header stop is PROMOTED to its own block, and
      a delivery check asserts every header is unique+sequential with a body.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import story_miner as sm
from story_miner import match_candidate_to_canonical
from venue_resolver import build_dynamic_aliases, build_canonical_titles_from_works
from stop_dedup_collision_guard import dedupe_and_fix_stop_count
from tour_conclusion import normalise_stop_headers, check_stop_delivery, count_delivered_stops

_FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "tests", "fixtures", "local826b")

FAMOUS = [
    "L'Origine du monde",
    "Olympia",
    "La Nuit étoilée",
    "La Naissance de Vénus",
]
CHURCH = "L'Église d'Auvers-sur-Oise"


def _load_json(name):
    with open(os.path.join(_FIX, name), encoding="utf-8") as f:
        return json.load(f)


def _install(works):
    sm.CANONICAL_ALIASES = build_dynamic_aliases(works)
    sm.build_bilingual_map_from_sparql(works)


class TestCachedMuseumCanon(unittest.TestCase):
    """The matcher on the EXACT cached Q23402 payloads."""

    @classmethod
    def setUpClass(cls):
        cls.corpus = _load_json("q23402_venue_corpus.json")
        cls.works_cache = _load_json("q23402_venue_works_cache.json")

    def test_stale_corpus_snapshot_reproduces_the_field_bug(self):
        """The cache-HIT path uses the stale venue_corpus snapshot: the famous
        four are absent from its matchable set, so they DROP and Église wrong-
        accepts Chaumes — the exact field evidence. This is why a version bump
        (not an alias rebuild from this snapshot) is required."""
        titles = set(self.corpus["canonical_titles"])
        works = self.corpus["sparql_works"] or []
        _install(works)
        for cand in FAMOUS:
            self.assertIsNone(
                match_candidate_to_canonical(cand, titles, corpus=""),
                f"stale snapshot unexpectedly matched {cand!r}")
        ch = match_candidate_to_canonical(CHURCH, titles, corpus="")
        # The stale alias/title set produces the wrong accept (or at best no
        # match); it must NEVER correctly resolve to The Church at Auvers here.
        if ch is not None:
            self.assertIn("chaumes", ch[0].lower(),
                          "stale snapshot should reproduce the Chaumes wrong-accept")

    def test_fresh_works_cache_verifies_famous_four_and_keeps_church_distinct(self):
        """Rebuilding the matchable set from the refreshed venue_works_cache (300
        works) — what a CORPUS_VERSION bump forces — the 826 matcher verifies all
        four famous works (incl. the cross-language alias follow) and resolves
        Église to The Church at Auvers, NOT Chaumes."""
        works = self.works_cache["works"] or []
        titles = build_canonical_titles_from_works(works)
        _install(works)
        for cand in FAMOUS:
            m = match_candidate_to_canonical(cand, titles, corpus="")
            self.assertIsNotNone(m, f"fresh set should VERIFY {cand!r}")
        ch = match_candidate_to_canonical(CHURCH, titles, corpus="")
        self.assertIsNotNone(ch, "Église should resolve on the fresh set")
        self.assertNotIn("chaumes", ch[0].lower(),
                         f"Église wrongly accepted {ch[0]!r} (Chaumes)")
        self.assertIn("church", ch[0].lower(),
                      f"Église should resolve to The Church at Auvers, got {ch[0]!r}")

    def test_olympia_matches_its_local34_enriched_form(self):
        """Live-path regression: the LOCAL-34 bare-title enrichment stores the
        famous "Olympia" as "Olympia (toile)" in the canonical set, and the
        sibling "Une moderne Olympia" blocks the fuzzy specificity gate — so the
        bare "Olympia" DROPPED on the first live run. The alias-follow now steps
        from the resolved bare title to its own descriptor-enriched label, while
        the different work "Une moderne Olympia" stays distinct."""
        works = self.works_cache["works"] or []
        titles = build_canonical_titles_from_works(works)
        # Reproduce the enrichment the generator applies to a bare SPARQL title.
        titles = set(titles)
        if "Olympia" in titles:
            titles.discard("Olympia")
            titles.add("Olympia (toile)")
        _install(works)
        m = match_candidate_to_canonical("Olympia", titles, corpus="")
        self.assertIsNotNone(m, "bare 'Olympia' must match its enriched form")
        self.assertIn("olympia", m[0].lower())
        self.assertNotIn("moderne", m[0].lower(),
                         f"'Olympia' wrongly folded into {m[0]!r}")
        # The different work must NOT collapse into the bare Olympia; it resolves
        # to its own label (the EN alias "A Modern Olympia" is correct).
        mm = match_candidate_to_canonical("Une moderne Olympia", titles, corpus="")
        self.assertIsNotNone(mm)
        self.assertIn("modern", mm[0].lower(),
                      f"'Une moderne Olympia' wrongly resolved to {mm[0]!r}")
        self.assertNotEqual(mm[0].lower().strip(), "olympia (toile)",
                            "'Une moderne Olympia' must not fold into bare Olympia")


# A minimal reconstruction of the pre-guard shape: the stop editor glued the
# Merry Drinker's full narrated body (headerless) after Stop 3's Directions.
_GLUED_RIJKS = """Step-by-Step Audio Guided Tour: Rijks Museum, Amsterdam, Netherlands
Tour-Category: museum

Stop 3: Het Joodse Bruidje (The Jewish Bride)

Address: Museumstraat 1, 1071 XX Amsterdam, Netherlands

Coordinates: 52.360000, 4.885278

Orientation: As you stand facing the Jewish Bride, watch the two figures.

Created between 1665 and 1669, this painting shows a Jewish father bestowing a necklace.

Directions: Proceed to A Militiaman Holding a Berkemeyer, Known as the 'Merry Drinker' (Een schutter die een berkenmeier vasthoudt, bekend als 'De vrolijke drinker').

Address: Museumstraat 1, 1071 XX Amsterdam, Netherlands

Coordinates: 52.360000, 4.885278

Orientation: Stand close to observe the militiaman holding his glass.

Frans Hals painted the Merry Drinker around 1628 to 1630, capturing a live, convivial moment. The loose brushwork conveys spontaneity and warmth, a hallmark of Hals's mature style.

Directions: Your final stop in Rijksmuseum: De grote golf bij Kanagawa (The Great Wave off Kanagawa).

Stop 5: De grote golf bij Kanagawa (The Great Wave off Kanagawa)

Address: Museumstraat 1, 1071 XX Amsterdam, Netherlands

Coordinates: 52.360000, 4.885278

Orientation: Stand close to the print.

The Great Wave off Kanagawa was created by Katsushika Hokusai in late 1831 during Japan's Edo period.

Sources: This tour draws on information from www.rijksmuseum.nl and the Wikipedia article on the museum.
"""


class TestStop4DespliceAndDelivery(unittest.TestCase):

    def test_corrupt_tour866_fixture_trips_the_delivery_check(self):
        """The delivered tour866.txt shipped two "Stop 4:" headers with
        non-sequential numbering — the delivery check reports both."""
        with open(os.path.join(_FIX, "tour866_corrupt_rijks.txt"),
                  encoding="utf-8") as f:
            corrupt = f.read()
        viol = check_stop_delivery(corrupt)
        self.assertTrue(any(v.startswith("DUPLICATE_NUMBER") for v in viol),
                        f"expected a duplicate-number violation, got {viol}")
        self.assertTrue(any(v.startswith("NON_SEQUENTIAL") for v in viol),
                        f"expected a non-sequential violation, got {viol}")

    def test_unique_lost_header_stop_is_promoted_not_dropped(self):
        """The glued Merry Drinker body is a UNIQUE stop: it must be PROMOTED to
        its own sequential block with its body intact, never dropped."""
        out = normalise_stop_headers(_GLUED_RIJKS)
        self.assertEqual(count_delivered_stops(out), 3)
        self.assertIn("Frans Hals painted the Merry Drinker", out,
                      "the promoted stop lost its narration body")
        self.assertIn("A Militiaman Holding a Berkemeyer", out)
        self.assertEqual(check_stop_delivery(out), [],
                         "the repaired tour must pass the delivery check")

    def test_promoted_block_renumbers_sequentially(self):
        import re
        out = normalise_stop_headers(_GLUED_RIJKS)
        nums = [int(m.group(1)) for m in re.finditer(r'(?m)^Stop (\d+):', out)]
        self.assertEqual(nums, [1, 2, 3])

    def test_duplicate_orphan_still_dropped(self):
        """A headerless orphan that only DUPLICATES a following real stop is still
        DROPPED (the w1/w4 symptom), not promoted — no regression."""
        dup = """Step-by-Step Audio Guided Tour: T
Tour-Category: museum

Stop 1: Faneuil Hall

Orientation: Look at Faneuil Hall and its history here in detail.

Directions: Head left and follow until you spot the church. Continue to Park Street Church

Address: 1 Park St

Coordinates: 42.3577, -71.0621

Orientation: Park Street Church was established in 1809 by a group of twenty-six. Its steeple was for decades the tallest structure in the United States.

Stop 2: Park Street Church

Address: 1 Park St

Coordinates: 42.3577, -71.0621

Orientation: Park Street Church was established in 1809 by a group of twenty-six. Its steeple was for decades the tallest structure in the United States.

Sources: x.
"""
        out, rep = dedupe_and_fix_stop_count(dup, dedupe_real_stops=False)
        self.assertEqual(rep.get("promoted", 0), 0,
                         "a duplicate orphan must NOT be promoted")
        self.assertEqual(count_delivered_stops(out), 2)
        self.assertEqual(check_stop_delivery(out), [])


class TestDeliveryCheckCleanTour(unittest.TestCase):
    def test_well_formed_tour_has_no_violations(self):
        clean = """Step-by-Step Audio Guided Tour: T
Tour-Category: museum

Stop 1: A

Orientation: look at A.

Directions: next B.

Stop 2: B

Orientation: look at B.

Directions: next C.

Stop 3: C

Orientation: look at C.

Sources: x.
"""
        self.assertEqual(check_stop_delivery(clean), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
