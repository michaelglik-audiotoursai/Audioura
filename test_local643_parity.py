"""
LOCAL-643 parity harness — prove the structured renderer reproduces today's
delivered format.

Strategy A requires that, with STRUCTURED_STOPS on, a tour rendered from records
has the SAME structure as today's output and only the known bugs disappear. This
test parses a real delivered tour into records (``parse_tour_to_records``) and
re-renders it (``render_tour``), then asserts structural parity:

  * same number of stops, same "Stop N:" headers in the same order
  * every field line (Address/Coordinates/Type-Specialty/Specific Examples/
    Operational Details/Museum Information/Orientation/Directions) that was present
    is present again, attached to the SAME stop
  * the conclusion and offer survive on the last stop
  * no header is glued onto a field line, no orientation migrates between stops

Run: python3 -m pytest test_local643_parity.py -q
 or: python3 test_local643_parity.py
"""
import os
import re
import unittest

import stop_records as sr

FIXTURE = os.path.join(os.path.dirname(__file__), "tests", "fixtures", "tour_485_r2.txt")

_STOP_HEADER_RE = re.compile(r'^Stop\s+(\d+):\s*(.+?)\s*$')
_FIELD_RE = re.compile(
    r'^(Address|Coordinates|Type/Specialty|Specific Examples|'
    r'Operational Details|Museum Information|Orientation|Directions):')


def _structure(text):
    """Return a structural signature: ordered list of (stop_index, [labels])."""
    sig = []
    cur = None
    for line in text.split("\n"):
        s = line.strip()
        hm = _STOP_HEADER_RE.match(s)
        if hm:
            cur = {"index": int(hm.group(1)), "title": hm.group(2), "labels": []}
            sig.append(cur)
            continue
        fm = _FIELD_RE.match(s)
        if fm and cur is not None:
            cur["labels"].append(fm.group(1))
    return sig


class TestStructuredRenderParity(unittest.TestCase):
    def setUp(self):
        if not os.path.exists(FIXTURE):
            self.skipTest(f"fixture missing: {FIXTURE}")
        with open(FIXTURE, encoding="utf-8") as f:
            self.original = f.read()

    def test_round_trip_preserves_structure(self):
        title, stops, opening, closing = sr.parse_tour_to_records(self.original)
        rendered = sr.render_tour(stops, title=title, opening=opening, closing=closing)

        orig_sig = _structure(self.original)
        new_sig = _structure(rendered)

        # Same stops, same headers, same order.
        self.assertEqual([s["index"] for s in orig_sig],
                         [s["index"] for s in new_sig],
                         "stop indices/order changed")
        self.assertEqual([s["title"] for s in orig_sig],
                         [s["title"] for s in new_sig],
                         "stop titles changed")

        # Every field label present originally is present again on the same stop.
        for o, n in zip(orig_sig, new_sig):
            self.assertEqual(o["labels"], n["labels"],
                             f"field labels diverged on Stop {o['index']}")

    def test_no_header_glued_to_field(self):
        """A 'Stop N:' header must never share a line with a field label."""
        title, stops, _, _ = sr.parse_tour_to_records(self.original)
        rendered = sr.render_tour(stops, title=title)
        for line in rendered.split("\n"):
            if line.strip().startswith("Stop ") and ":" in line:
                self.assertNotRegex(
                    line, r'(Address|Coordinates|Orientation|Directions):',
                    f"header glued to a field line: {line!r}")

    def test_every_header_on_own_line(self):
        title, stops, _, _ = sr.parse_tour_to_records(self.original)
        rendered = sr.render_tour(stops, title=title)
        headers = [l for l in rendered.split("\n") if _STOP_HEADER_RE.match(l.strip())]
        self.assertEqual(len(headers), len(stops),
                         "a stop header was lost or duplicated")

    def test_conclusion_and_offer_survive(self):
        title, stops, _, _ = sr.parse_tour_to_records(self.original)
        # The conclusion+offer are parsed into the last stop's narration here (the
        # reader does not separate them), so they must still be present in output.
        rendered = sr.render_tour(stops, title=title)
        self.assertIn("That's 3 stops", rendered)
        self.assertIn("restaurant tour", rendered)
        self.assertIn("Sources:", rendered)

    def test_orientation_does_not_migrate(self):
        """Stop 3's orientation names van Gogh; it must stay on Stop 3."""
        title, stops, _, _ = sr.parse_tour_to_records(self.original)
        by_index = {s.index: s for s in stops}
        self.assertIn("van Gogh", by_index[3].orientation,
                      "Stop 3 orientation lost/migrated")
        # Stop 2 in the fixture has NO Orientation line — must not acquire one.
        self.assertEqual(by_index[2].orientation, "",
                         "Stop 2 gained an orientation it never had")


if __name__ == "__main__":
    unittest.main(verbosity=2)
