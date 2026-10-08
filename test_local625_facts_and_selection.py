"""LOCAL-625 — one regression test per defect, built on the real tour inputs.

Each test reproduces the exact garbage the live tours shipped and asserts the fix:

  1. Hours parse  — Alte Pinakothek (tour 471) "Museum Information: 00–18; 00–20;
     00–17; 00–19": a dot/colon clock's minute half must not leak out as a bare
     "00–18".
  2. Address      — SMK (tour 470) Stop 1 carried the donor-merchant address
     "Bredgade 14" scraped from a provenance sentence; every stop must use the
     museum's verified address.
  3. Room-as-stop — Alte Pinakothek (tour 471) Stop 2 was "Obergeschoss,
     Kabinett 1-2", a ROOM; a museum stop must be an artwork, so a room/gallery/
     wing/building title is rejected.
  4. Wrong entity — "Mauritshuis, The Hague" resolved to the 0-work painting
     Q17324051 instead of the museum Q221092; the resolver must prefer a
     collecting institution with sitelinks over a 0-work entity.

All four run offline/deterministically (item 4 injects the P31/collection
lookups with the REAL Wikidata values observed for the two Mauritshuis QIDs).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class Item1HoursParse(unittest.TestCase):
    """'10.00-18.00' / '10:00-18:00' must never become the bare '00–18'."""

    def test_dot_and_colon_clock_never_loses_its_hour(self):
        import visitor_facts_extractor as v
        # The Alte Pinakothek (Munich) page renders times with a dot: "10.00-18.00".
        # The old FR-path regex matched the minute half "00" and produced "00–18".
        facts = v.extract_visitor_facts_from_text(
            "Öffnungszeiten\n"
            "Dienstag: de 10.00 à 20.00\n"      # fr-path trigger (de … à) + dot clock
            "Mittwoch bis Sonntag: de 10.00 à 18.00\n",
            "fr",
        )
        times = [h["time"] for h in facts.hours]
        self.assertTrue(times, f"no hours extracted: {facts.hours}")
        for t in times:
            # Every emitted range must start on a real hour (10:00 / 10.00), not "00".
            self.assertNotRegex(
                t, r"^0?0\s*[-–]",
                f"hour half leaked — got {t!r} (the '00–18' defect)")
            self.assertRegex(
                t, r"(?:^|[^\d])(?:10|20|18)\b",
                f"expected the page's real hours in {t!r}")

    def test_normalize_time_handles_dot_and_bare_hour(self):
        import visitor_facts_extractor as v
        self.assertEqual(v._normalize_time("10.00"), "10:00")
        self.assertEqual(v._normalize_time("9.30"), "09:30")
        self.assertEqual(v._normalize_time("18"), "18:00")
        self.assertEqual(v._normalize_time("10:00"), "10:00")


class Item2AddressConsistency(unittest.TestCase):
    """A per-work donor/merchant address must not override the museum's address."""

    SMK_ADDRESS = "Sølvgade 48-50, 1307 København, Denmark"
    # Stop 1 "In a Roman Osteria": the donor's address sits in a PROVENANCE
    # sentence, not a location cue — the tour-470 defect. Phrased number-first so
    # the street parser accepts it (as it did when the defect shipped); the fix
    # rejects it because no location cue introduces it.
    STOP1_BODY = ("The work was commissioned in 1866 by Moritz G. Melchior, a "
                  "Danish merchant who lived at 14 Bredgade Street.")

    def test_donor_address_rejected_binds_to_museum(self):
        from about_museum_stop import venue_bound_address
        got = venue_bound_address("14 Bredgade Street", self.SMK_ADDRESS,
                                  stop_page_text=self.STOP1_BODY)
        self.assertEqual(got, self.SMK_ADDRESS,
                         "donor address in prose must not survive — bind to venue")

    def test_genuine_satellite_with_location_cue_is_kept(self):
        from about_museum_stop import venue_bound_address
        sat_page = ("This show is at our East Annex, located at 12 King Street, "
                    "Boston.")
        got = venue_bound_address("12 King Street, Boston", self.SMK_ADDRESS,
                                  stop_page_text=sat_page)
        self.assertEqual(got, "12 King Street, Boston",
                         "a real satellite address with a location cue is kept")


class Item3RoomAsStop(unittest.TestCase):
    """A room/gallery/wing/building title is never an artwork stop."""

    def test_kabinett_room_is_rejected(self):
        from room_candidate_guard import is_room_or_space_title
        # The exact tour-471 Stop 2 title.
        self.assertTrue(is_room_or_space_title(
            "Alte Pinakothek, Obergeschoss, Kabinett 1-2", "Alte Pinakothek"))
        for room in ("Kabinett 1-2", "Gallery 3", "Saal II", "Second Floor",
                     "Obergeschoss", "Salle 5", "East Wing", "The Building"):
            self.assertTrue(is_room_or_space_title(room),
                            f"{room!r} must be rejected as a room/space")

    def test_real_artworks_are_kept(self):
        from room_candidate_guard import is_room_or_space_title
        # Real works from the three evidence tours — none may be rejected,
        # including paintings whose TITLE mentions a room.
        for work in ("The Holy Family", "In a Roman Osteria",
                     "View from the Artist's Window", "Ecce Homo",
                     "Crucifixion (XXe siècle)", "The Music Room",
                     "View of the Great Hall"):
            self.assertFalse(is_room_or_space_title(work),
                             f"{work!r} is an artwork, must be kept")


class Item4VenueEntityRanking(unittest.TestCase):
    """A 0-work painting entity must never beat a collecting museum."""

    # Real QIDs + the real Wikidata values observed for them.
    MUSEUM = "Q221092"      # Mauritshuis — national art museum, 111 works, 5 sitelinks
    PAINTING = "Q17324051"  # "Mauritshuis in The Hague" — a painting, 0 works

    def _props(self, qid):
        from venue_resolver import _MUSEUM_TYPES
        art_museum = "Q17431399"  # national art museum (in _MUSEUM_TYPES)
        self.assertIn(art_museum, _MUSEUM_TYPES)
        if qid == self.MUSEUM:
            return {"part_of": [], "instance_of": [art_museum]}
        if qid == self.PAINTING:
            return {"part_of": [], "instance_of": ["Q3305213"]}  # painting
        return {"part_of": [], "instance_of": []}

    def _counts(self, qid):
        if qid == self.MUSEUM:
            return (111, 5)
        return (0, 0)

    def test_museum_outranks_zero_work_painting(self):
        from venue_resolver import prefer_parent_institution
        # Both present (as the UNION fix now guarantees), painting listed FIRST
        # (its search order in the live run).
        candidates = [(self.PAINTING, "Mauritshuis in The Hague"),
                      (self.MUSEUM, "Mauritshuis")]
        ranked = prefer_parent_institution(candidates, self._props, self._counts)
        self.assertTrue(ranked, "ranking returned nothing")
        self.assertEqual(ranked[0][0], self.MUSEUM,
                         f"the museum with 111 works must win, got {ranked[0]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
