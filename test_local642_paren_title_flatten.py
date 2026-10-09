#!/usr/bin/env python3
"""test_local642_paren_title_flatten.py — LOCAL-642.

National Gallery 495 (Bench R9, R12): the stop whose title carries PARENTHESES
and QUOTES — "The Toilet of Venus ('The Rokeby Venus')" — was delivered with its
header, Address, Coordinates and Orientation FLATTENED onto ONE line, and the
flattened block was DUPLICATED under a "Continue to …" transition. R12
generator.log:

    21: Directions: Continue through The National Gallery — next is The Toilet of Venus ('The Rokeby Venus').
    23: Continue to The Toilet of Venus ('The Rokeby Venus') Address: … Coordinates: … Orientation: …
    25: Stop 2: The Toilet of Venus ('The Rokeby Venus') Address: … Coordinates: … Orientation: …

tour_conclusion.enforce_header_field_line_invariant (run inside
normalise_stop_headers, and thus on every finalization path) repairs both
symptoms deterministically. It keys ONLY on the house field labels
(Address/Coordinates/Orientation/Directions) and the "Stop N:" header — never on
the title text — so a title containing "(", ")", "'", "[", "]", "+" or "?" is
carried through byte-for-byte.

Contract (binding):
  1. The flattened "Stop N:" header line is re-broken so the header carries ONLY
     the title and each field label starts its own line (the live ``run_on``
     detector is clear).
  2. The duplicated "Continue to <title> <field block>" line is reduced to the
     bare hand-off sentence; the field block is dropped (the real "Stop N:"
     header for that title carries the fields).
  3. count_delivered_stops is unchanged (3) and every title is preserved exactly.
  4. A clean, well-formed tour is a byte-for-byte no-op.
  5. Idempotent.
  6. Titles with regex metacharacters ( ) ' [ ] + ? are handled identically.
  7. Lowercase prose like "the address: look left" is NEVER re-broken.

Pure/offline; no network, no LLM, no DB. Run:
    python3 -m pytest test_local642_paren_title_flatten.py -q
"""
import re
import unittest

import tour_conclusion as tc


TITLE = "The Toilet of Venus ('The Rokeby Venus')"

# The live detectors (verbatim from run_local639_container.py:122-123).
_RUN_ON = re.compile(r"(?mi)^Stop\s+\d+:.*\b(?:Address|Coordinates|Orientation|Directions):")
_LABEL_GLUED = re.compile(r"(?mi)^(?:Address|Directions|Coordinates|Orientation):\S*Stop\s+\d+:")
_HEADER = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")

_FIELD_LABELS = ("Address:", "Coordinates:", "Orientation:", "Directions:")


def _flattened_headers(text):
    return [h for h in _HEADER.findall(text)
            if any(fl in h for fl in _FIELD_LABELS)]


# The exact R12 495 defect shape: a correct transition line, then a DUPLICATED
# "Continue to <title>" with the next stop's block FLATTENED onto it, then the
# real "Stop 2:" header ALSO flattened.
_NG_495_DEFECT = (
    "Step-by-Step Audio Guided Tour: The National Gallery, London, UK - Museum Tour\n\n"
    "Stop 1: Ophelia\n\n"
    "Coordinates: 51.5081, -0.128\n\n"
    "Millais painted Ophelia between 1851 and 1852.\n\n"
    "Directions: Continue through The National Gallery \u2014 next is " + TITLE + ".\n\n"
    "Continue to " + TITLE + " Address: The National Gallery, Trafalgar Square, "
    "London WC2N 5DN Coordinates: 51.5081, -0.128 Orientation: Stand just far "
    "enough back to take in the whole canvas.\n\n"
    "Stop 2: " + TITLE + " Address: The National Gallery, Trafalgar Square, London "
    "WC2N 5DN Coordinates: 51.5081, -0.128 Orientation: Stand just far enough back "
    "to take in the whole canvas.\n\n"
    "Velazquez painted the only surviving nude of his career here.\n\n"
    "Directions: Your final stop in The National Gallery: The Supper at Emmaus.\n\n"
    "Stop 3: The Supper at Emmaus\n\n"
    "Coordinates: 51.5081, -0.128\n\n"
    "Caravaggio captured the moment of recognition.\n\n"
    "That's 3 stops in all.\n\n"
    "Sources: This tour draws on information from www.nationalgallery.org.uk.\n"
)


class TestNG495Defect(unittest.TestCase):
    def setUp(self):
        self.fixed = tc.normalise_stop_headers(_NG_495_DEFECT)

    def test_defect_present_in_fixture(self):
        # Before the fix: Stop 2 header is flattened and the dup block is present.
        self.assertTrue(_RUN_ON.search(_NG_495_DEFECT))
        self.assertIn("Continue to " + TITLE + " Address:", _NG_495_DEFECT)
        self.assertEqual(len(_flattened_headers(_NG_495_DEFECT)), 1)

    def test_run_on_header_cleared(self):
        self.assertFalse(_RUN_ON.search(self.fixed),
                         "flattened 'Stop N:' header line still present")
        self.assertFalse(_LABEL_GLUED.search(self.fixed))

    def test_header_carries_only_title(self):
        self.assertEqual(_flattened_headers(self.fixed), [])
        titles = [h.strip() for h in _HEADER.findall(self.fixed)]
        self.assertIn(TITLE, titles)
        self.assertEqual(titles, ["Ophelia", TITLE, "The Supper at Emmaus"])

    def test_duplicated_field_block_dropped(self):
        self.assertNotIn("Continue to " + TITLE + " Address:", self.fixed)
        # The hand-off sentence survives (as its own line, ending with a period).
        self.assertIn("Continue to " + TITLE + ".", self.fixed)

    def test_field_labels_each_start_a_line(self):
        for raw in self.fixed.split("\n"):
            for fl in _FIELD_LABELS:
                idx = raw.find(fl)
                if idx > 0:
                    # a label may only be preceded by whitespace on its line
                    self.assertEqual(raw[:idx].strip(), "",
                                     f"field label not at line start: {raw!r}")

    def test_count_and_title_preserved(self):
        self.assertEqual(tc.count_delivered_stops(self.fixed), 3)
        # The parenthesized title survives byte-for-byte everywhere it appears.
        self.assertIn("Stop 2: " + TITLE, self.fixed)
        self.assertIn("next is " + TITLE + ".", self.fixed)

    def test_idempotent(self):
        twice = tc.normalise_stop_headers(self.fixed)
        self.assertEqual(twice, self.fixed)

    def test_narration_untouched(self):
        self.assertIn("Velazquez painted the only surviving nude of his career here.",
                      self.fixed)
        self.assertIn("Millais painted Ophelia between 1851 and 1852.", self.fixed)


class TestSyntheticMetacharTitles(unittest.TestCase):
    """A title with parentheses, quotes, brackets, '+' and '?' must be handled
    exactly like any other — the repair keys on field labels, never the title."""

    METACHAR_TITLES = [
        "A (B) [C] + D?",
        "Study (No. 2) 'quote'",
        "What? (Really!) [draft]",
        "x+y? (z)",
        "The Lizard (aux plumes d'or) [1782]",
    ]

    def _defect_for(self, title):
        return (
            "Step-by-Step Audio Guided Tour: X - Museum Tour\n\n"
            "Stop 1: First Work\n\n"
            "Coordinates: 1.0, 2.0\n\n"
            "First narration.\n\n"
            "Directions: Continue to " + title + ".\n\n"
            "Continue to " + title + " Address: 1 Road Coordinates: 3.0, 4.0 "
            "Orientation: Stand before it.\n\n"
            "Stop 2: " + title + " Address: 1 Road Coordinates: 3.0, 4.0 "
            "Orientation: Stand before it.\n\n"
            "Second narration.\n\n"
            "That's 2 stops in all.\n"
        )

    def test_each_metachar_title(self):
        for title in self.METACHAR_TITLES:
            with self.subTest(title=title):
                defect = self._defect_for(title)
                fixed = tc.normalise_stop_headers(defect)
                self.assertFalse(_RUN_ON.search(fixed),
                                 f"flattened header remains for {title!r}")
                self.assertNotIn("Continue to " + title + " Address:", fixed)
                titles = [h.strip() for h in _HEADER.findall(fixed)]
                self.assertIn(title, titles,
                              f"title not preserved byte-for-byte: {title!r}")
                self.assertEqual(tc.count_delivered_stops(fixed), 2)
                # Idempotent for every title.
                self.assertEqual(tc.normalise_stop_headers(fixed), fixed)


class TestCleanTourNoOp(unittest.TestCase):
    _CLEAN = (
        "Step-by-Step Audio Guided Tour: The National Gallery, London, UK - Museum Tour\n\n"
        "Stop 1: " + TITLE + "\n\n"
        "Address: Trafalgar Square\n\n"
        "Coordinates: 51.5081, -0.128\n\n"
        "Orientation: Stand before it. The guide points you to the address: look left.\n\n"
        "Velazquez painted the only surviving nude of his career.\n\n"
        "Directions: Continue to Ophelia.\n\n"
        "Stop 2: Ophelia\n\n"
        "Coordinates: 51.5081, -0.128\n\n"
        "Millais painted it.\n\n"
        "That's 2 stops in all.\n"
    )

    def test_clean_is_byte_for_byte_noop(self):
        self.assertEqual(tc.normalise_stop_headers(self._CLEAN), self._CLEAN)

    def test_lowercase_prose_label_not_rebroken(self):
        # "the address: look left" (lowercase) is prose, NOT a house label.
        out = tc.normalise_stop_headers(self._CLEAN)
        self.assertIn("points you to the address: look left.", out)

    def test_count(self):
        self.assertEqual(tc.count_delivered_stops(self._CLEAN), 2)


class TestInvariantFunctionDirect(unittest.TestCase):
    """enforce_header_field_line_invariant reports its actions for logging."""

    def test_reports_actions_on_defect(self):
        _fixed, actions = tc.enforce_header_field_line_invariant(_NG_495_DEFECT)
        self.assertTrue(actions, "expected the invariant to report its repairs")
        self.assertTrue(any("duplicated field block" in a for a in actions))
        self.assertTrue(any("glued field label" in a for a in actions))

    def test_no_actions_on_clean(self):
        clean = (
            "Stop 1: Work\n\nAddress: 1 Rd\n\nCoordinates: 1,2\n\n"
            "Orientation: Stand.\n\nNarr.\n\nThat's 1 stops in all.\n"
        )
        _fixed, actions = tc.enforce_header_field_line_invariant(clean)
        self.assertEqual(actions, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
