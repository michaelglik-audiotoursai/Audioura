#!/usr/bin/env python3
"""test_local626_venue_not_a_stop.py — LOCAL-626 item 1.

Tour 485 (The Courtauld Gallery, 3 requested stops) delivered Stop 1 titled
"Courtauld Gallery", carrying the museum's founding/relocation history as its
narration body — the museum became an artwork stop. With the about-museum
opening section already folded into Stop 1 (LOCAL-592), that cost the listener a
real work: only 2 artworks (Cézanne, the Footed Bowl) shipped for a 3-stop ask.

The venue-as-stop slipped the LOCAL-625 room/space guard because "Courtauld
Gallery" carries no room NUMBER. The fix adds is_venue_itself_title, drops the
venue from the canonical SET and the deterministic documented-works list (so a
real artwork fills the slot), and drops it again at the assembly last-line guard.

Inputs below are the REAL tour-485 values: the Stop-1 title and the request venue
name, taken verbatim from .continuous_dev/calib/critique/tour_485.txt.

Run: python3 -m pytest tests/test_local626_venue_not_a_stop.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from room_candidate_guard import (is_venue_itself_title,
                                   filter_out_room_candidates,
                                   is_room_or_space_title)

# The real tour-485 Stop-1 title and request venue.
VENUE_485 = "The Courtauld Gallery"
STOP1_TITLE_485 = "Courtauld Gallery"
# The real artworks that SHOULD have been the stops.
WORKS_485 = ["A Bar at the Folies-Bergère", "La loge",
             "Self-Portrait with Bandaged Ear", "The Card Players",
             "Footed Bowl with the Crucifixion"]


class TestVenueNotAStop(unittest.TestCase):
    def test_tour485_stop1_is_the_venue_itself(self):
        """The real 485 Stop-1 title is recognised as the venue, not a work."""
        self.assertTrue(is_venue_itself_title(STOP1_TITLE_485, VENUE_485))

    def test_venue_slips_the_room_guard(self):
        """Documents WHY it shipped: the room/space guard does NOT catch it
        (no room number), so item 1 needs the dedicated venue predicate."""
        self.assertFalse(is_room_or_space_title(STOP1_TITLE_485, VENUE_485))

    def test_real_artworks_are_not_flagged_as_venue(self):
        """None of the Courtauld's real works is mistaken for the venue."""
        for w in WORKS_485:
            self.assertFalse(is_venue_itself_title(w, VENUE_485),
                             f"{w!r} must not be treated as the venue")

    def test_filter_drops_venue_keeps_works_and_count_holds(self):
        """A candidate list of [venue, work, work, work] loses the venue and
        keeps all real works — so a 3-stop ask can still be filled with 3
        works once upstream refills the dropped slot."""
        cands = ([{"title": STOP1_TITLE_485}]
                 + [{"title": w} for w in WORKS_485])
        kept, dropped = filter_out_room_candidates(cands, VENUE_485)
        kept_titles = [c["title"] for c in kept]
        self.assertNotIn(STOP1_TITLE_485, kept_titles)
        self.assertEqual([c["title"] for c in dropped], [STOP1_TITLE_485])
        for w in WORKS_485:
            self.assertIn(w, kept_titles)

    def test_bare_institution_noun_is_venue(self):
        self.assertTrue(is_venue_itself_title("The Collection", VENUE_485))
        self.assertTrue(is_venue_itself_title("Museum", VENUE_485))

    def test_painting_of_the_venue_is_kept(self):
        """A painting whose title merely begins with the venue name but continues
        with more words is a WORK, not the venue."""
        self.assertFalse(
            is_venue_itself_title("Courtauld Gallery Interior, 1935", VENUE_485))

    def test_production_wires_the_guard(self):
        """generate_tour_text and stop_pool_assembly both call the venue guard."""
        _here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for fn in ("generate_tour_text.py", "stop_pool_assembly.py"):
            with open(os.path.join(_here, fn), encoding="utf-8") as fh:
                self.assertIn("is_venue_itself_title", fh.read(),
                              f"{fn} must call is_venue_itself_title")


if __name__ == "__main__":
    unittest.main(verbosity=2)
