"""
LOCAL-590 unit tests — stop_pool_store parse, identity and key logic.
=====================================================================
These tests CALL the real functions in stop_pool_store; they do not grep source
(D418/D421). No database is required: parse_delivered_stops, venue_identity,
_pool_key, _title_norm and _strip_title_decorations are all pure.

What is asserted:
  1. A delivered tour parses into one audio-independent unit per 'Stop N:' block.
  2. Sequence-dependent lines (Orientation, Directions) are NEVER pooled with the
     stop narration — they are properties of a sequence, not a stop (D581.1).
  3. The closing recap and the trailing Sources block belong to the tour, not any
     stop, so they are excluded from every unit.
  4. Structured renderer fields (Address, Coordinates, Type/Specialty, …) are
     captured into their own slots.
  5. Header decorations (' by {artist}', ', {year}') are split off the bare title.
  6. Venue identity is QID-first, with a normalised-location fallback that agrees
     with tour_cache_layer1 (so "Miró" and "Miro" share one pool).
  7. The pool key namespaces identity by version + tour_type.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import stop_pool_store as sp


# A compact but realistic delivered museum tour in the CURRENT format:
# header line, Tour-Category, Stop blocks with Address/Coordinates/Orientation,
# Directions hand-offs, a closing recap ("…you have followed the thread…") and a
# trailing Sources block.
TOUR = """Step-by-Step Audio Guided Tour: Test Museum, Testville - Museum Tour
Tour-Category: museum

Stop 1: The First Painting by Jane Doe, 1888

Address: 1 Test Street, Testville

Coordinates: 10.0, 20.0

Type/Specialty: Oil on canvas

Orientation: Enter the first gallery and stand before the painting.

This is the body of the first stop. It describes the painting at length and is
the reusable, audio-independent narration we want to keep.

Directions: Continue to The Second Painting.

Stop 2: The Second Painting

Address: 1 Test Street, Testville

Orientation: Move to the next room.

Body of the second stop. Also reusable prose.

Directions: Your next stop at Test Museum: The Third Painting.

Stop 3: The Third Painting

Address: 1 Test Street, Testville

Body of the third and final stop.

From The First Painting to The Third Painting, you have followed the thread of one story.

That's 3 stops.

Sources: This tour draws on information from example.org and the Wikipedia article on the museum.
"""


class TestParseDeliveredStops(unittest.TestCase):
    def setUp(self):
        self.units = sp.parse_delivered_stops(TOUR)

    def test_one_unit_per_stop(self):
        self.assertEqual(len(self.units), 3)
        self.assertEqual([u["title"] for u in self.units],
                         ["The First Painting", "The Second Painting", "The Third Painting"])

    def test_header_decorations_split_off(self):
        first = self.units[0]
        self.assertEqual(first["title"], "The First Painting")
        self.assertEqual(first["artist"], "Jane Doe")
        self.assertEqual(first["year"], "1888")
        # Undecorated stop has empty artist/year.
        self.assertEqual(self.units[1]["artist"], "")
        self.assertEqual(self.units[1]["year"], "")

    def test_orientation_and_directions_never_pooled(self):
        for u in self.units:
            self.assertNotIn("Orientation:", u["narration"])
            self.assertNotIn("Directions:", u["narration"])
            self.assertNotIn("Enter the first gallery", u["narration"])
            self.assertNotIn("Continue to", u["narration"])

    def test_recap_and_sources_excluded_from_last_stop(self):
        last = self.units[-1]
        self.assertNotIn("you have followed the thread", last["narration"])
        self.assertNotIn("Sources:", last["narration"])
        self.assertNotIn("That's 3 stops", last["narration"])
        self.assertIn("third and final stop", last["narration"])

    def test_structured_fields_captured(self):
        first = self.units[0]
        self.assertEqual(first["address"], "1 Test Street, Testville")
        self.assertEqual(first["coordinates"], "10.0, 20.0")
        self.assertEqual(first["type_specialty"], "Oil on canvas")

    def test_narration_is_the_body_prose(self):
        self.assertIn("reusable, audio-independent narration", self.units[0]["narration"])
        self.assertIn("Also reusable prose", self.units[1]["narration"])

    def test_raw_block_preserved_for_exact_reuse(self):
        # raw_block keeps the full original (incl. Orientation/Directions) so an
        # unchanged served stop can match prior audio exactly.
        self.assertIn("Orientation:", self.units[0]["raw_block"])
        self.assertIn("Stop 1:", self.units[0]["raw_block"])

    def test_empty_input(self):
        self.assertEqual(sp.parse_delivered_stops(""), [])
        self.assertEqual(sp.parse_delivered_stops("no stops here"), [])


class TestVenueIdentity(unittest.TestCase):
    def test_qid_first(self):
        self.assertEqual(sp.venue_identity("Anything", "Q12345"), "qid:Q12345")
        # QID casefolds up so case variants collapse.
        self.assertEqual(sp.venue_identity("Anything", "q12345"), "qid:Q12345")

    def test_location_fallback_without_qid(self):
        self.assertEqual(sp.venue_identity("Palais Lascaris, Nice"),
                         "loc:palais lascaris nice")

    def test_accent_fold_fallback_matches_cache_layer(self):
        # The whole reason to share tour_cache_layer1's normaliser: "Miró" and
        # "Miro" must be one pool.
        a = sp.venue_identity("Musée Miró, Barcelona")
        b = sp.venue_identity("Musee Miro, Barcelona")
        self.assertEqual(a, b)

    def test_empty_qid_falls_back(self):
        self.assertEqual(sp.venue_identity("Palais Lascaris, Nice", ""),
                         "loc:palais lascaris nice")
        self.assertEqual(sp.venue_identity("Palais Lascaris, Nice", "   "),
                         "loc:palais lascaris nice")


class TestPoolKey(unittest.TestCase):
    def test_key_namespaces_version_identity_and_type(self):
        ident = sp.venue_identity("Test Museum", "Q1")
        key = sp._pool_key(ident, "museum")
        self.assertEqual(key, f"v{sp.POOL_VERSION}|qid:Q1|museum")

    def test_different_tour_types_are_different_pools(self):
        ident = sp.venue_identity("Boston Common")
        self.assertNotEqual(sp._pool_key(ident, "walking"),
                            sp._pool_key(ident, "museum"))

    def test_tour_type_casefolded(self):
        ident = sp.venue_identity("Test", "Q1")
        self.assertEqual(sp._pool_key(ident, "Museum"), sp._pool_key(ident, "museum"))


class TestTitleNorm(unittest.TestCase):
    def test_accent_and_case_fold(self):
        self.assertEqual(sp._title_norm("Vénus and Cupid"), sp._title_norm("venus and cupid"))

    def test_strip_decorations(self):
        title, artist, year = sp._strip_title_decorations("The Starry Night by Vincent van Gogh, 1889")
        self.assertEqual(title, "The Starry Night")
        self.assertEqual(artist, "Vincent van Gogh")
        self.assertEqual(year, "1889")

    def test_title_without_decorations(self):
        title, artist, year = sp._strip_title_decorations("Raquel")
        self.assertEqual(title, "Raquel")
        self.assertEqual(artist, "")
        self.assertEqual(year, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
