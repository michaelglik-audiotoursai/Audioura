#!/usr/bin/env python3
"""test_local593_single_venue_opening_section.py — LOCAL-593 r2.

REGRESSION. Since LOCAL-592/D611 the "About the venue" history section lives at
the start of Stop 1. The July-2026 single-venue consistency check
(content_qa_runner, check 9) and the venue-coherence check (check 11) scanned
that history. A museum's own history names its predecessor and constituent
museums, and each was counted as a "foreign venue":

  * Harvard Art Museums: Stop 1 named the Fogg / Busch-Reisinger / Arthur M.
    Sackler (its constituents), plus the Sackler again in a later stop → 3 refs,
    over the <= 2 limit → FAIL.
  * McMullen (Boston College Museum of Art): Stop 1 named the Devlin Gallery and
    a bare "Art Gallery"; a later stop named the "College Museum of Art" → 3
    refs → FAIL.

The r2 fix reworks the check IN PLACE (no new mechanism):
  (a) skip the Stop 1 opening/About section (the tour-level description, found
      structurally via prolog_structure_validator.extract_prolog_from_tour_content);
  (b) exempt a ref that is a substring of / contains the tour venue's own name
      or whose distinctive tokens are all part of venue_context['venue_tokens']
      ("College Museum of Art" ⊂ "Boston College Museum of Art");
  (c) drop the bare two-word generic matches ("Art Gallery", "Art Museum").

A genuinely foreign venue named OUTSIDE the opening section stays flagged: the
Isabella Stewart Gardner Museum, named 3× in a Harvard exhibition stop, is not
the venue, not an alias, not generic, and not in the opening section → FAIL.

This test drives the REAL content_qa_runner.run_qa and reads the printed check
verdicts, so it proves the production path.

RED on r1 HEAD (8042100):  the opening-section history is scanned → Harvard and
                           McMullen FAIL single-venue consistency.
GREEN after r2:            Harvard and McMullen PASS; the foreign venue FAILs.

Run: python3 -m pytest tests/test_local593_single_venue_opening_section.py -q
"""
import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import content_qa_runner


# Harvard Art Museums: Stop 1 opening names the three constituents; Stop 7 names
# the Sackler once more. Only the Stop 7 reference should survive the scan.
HARVARD_TOUR = """Audio Guided Tour: Harvard Art Museums - Museum Tour
Tour-Category: museum

Stop 1: Calderwood Courtyard
Address: 32 Quincy Street, Cambridge, MA
Coordinates: 42.3744, -71.1140

You are about to explore the Harvard Art Museums, an institution formed in 2008 from three museums. The Fogg Museum opened in 1896. The Busch-Reisinger Museum focuses on German art. The Arthur M. Sackler Museum houses Asian art. Across the stops ahead you will encounter works drawn from all three collections.

Orientation: Position yourself in the glass-roofed courtyard facing the staircase.

Description:
The courtyard anchors the building completed in 2014.

Directions: Proceed to the stairs.

Stop 7: Asian Jades
Address: 32 Quincy Street, Cambridge, MA
Coordinates: 42.3744, -71.1140

Description:
These jades were long held by the Arthur M. Sackler Museum before the 2008 consolidation.
"""

# McMullen Museum of Art at Boston College. The Stop 1 opening history names
# three distinctive predecessor/campus galleries (Devlin, Bapst, Burns) plus a
# bare "Art Gallery"; Stop 3 names the "College Museum of Art", a sub-phrase of
# the venue's own name. On r1 HEAD the three opening galleries are counted as
# foreign venues (> 2) → FAIL. After r2 the whole opening section is skipped and
# the sub-phrase is exempted → PASS.
MCMULLEN_TOUR = """Audio Guided Tour: Boston College Museum of Art - Museum Tour
Tour-Category: museum

Stop 1: Entrance Hall
Address: 2101 Commonwealth Avenue, Chestnut Hill, MA
Coordinates: 42.3350, -71.1690

You are about to explore the Boston College Museum of Art, whose collection grew from the earlier Devlin Gallery, succeeded a display space in the Bapst Gallery, and absorbed holdings once shown in the Burns Gallery; before all that a small Art Gallery on campus served students. Over the stops ahead you will see works that trace this history.

Orientation: Stand at the entrance facing the main gallery.

Description:
The entrance hall sets the tone for the collection.

Directions: Enter the main gallery.

Stop 3: Student Works
Address: 2101 Commonwealth Avenue, Chestnut Hill, MA
Coordinates: 42.3350, -71.1690

Description:
Several pieces here were first shown at the College Museum of Art in the 1990s.
"""

# A genuinely FOREIGN venue, named three times in an exhibition stop that is NOT
# the opening section. It is not a constituent, not an alias, not generic, and
# not in the Stop 1 opening — so it must stay flagged.
FOREIGN_TOUR = """Audio Guided Tour: Harvard Art Museums - Museum Tour
Tour-Category: museum

Stop 1: Calderwood Courtyard
Address: 32 Quincy Street, Cambridge, MA
Coordinates: 42.3744, -71.1140

You are about to explore the Harvard Art Museums. Across the stops ahead you will encounter many works.

Orientation: Position yourself in the courtyard.

Description:
The courtyard anchors the building.

Directions: Proceed to the stairs.

Stop 4: Comparative Gallery
Address: 32 Quincy Street, Cambridge, MA
Coordinates: 42.3744, -71.1140

Description:
Scholars often compare these works to those at the Isabella Stewart Gardner Museum. The Isabella Stewart Gardner Museum lies two miles away. Loans from the Isabella Stewart Gardner Museum have appeared here.
"""

HARVARD_CTX = {'venue_tokens': {'harvard', 'art', 'museums'},
               'city': 'Cambridge', 'region': 'MA', 'artist': '', 'tier': 'rich'}
MCMULLEN_CTX = {'venue_tokens': {'boston', 'college', 'museum', 'art'},
                'city': 'Chestnut Hill', 'region': 'MA', 'artist': '', 'tier': 'rich'}


def _run_qa_verdicts(tour_text, venue_context):
    """Run the real run_qa and return {fragment: 'PASS'|'FAIL'}."""
    content_qa_runner.PASS_COUNT = 0
    content_qa_runner.FAIL_COUNT = 0
    content_qa_runner.FACTUAL_FAIL_COUNT = 0
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            content_qa_runner.run_qa(tour_text, story_elements=[],
                                     venue_context=venue_context)
    except SystemExit:
        pass
    verdicts = {}
    for line in buf.getvalue().splitlines():
        line = line.strip()
        if "Single-venue consistency" in line:
            verdicts['single_venue'] = 'PASS' if line.startswith('PASS') else 'FAIL'
        elif "Venue coherence" in line:
            verdicts['coherence'] = 'PASS' if line.startswith('PASS') else 'FAIL'
    return verdicts


class TestSingleVenueOpeningSection(unittest.TestCase):
    def test_harvard_constituents_in_opening_pass(self):
        """Harvard's constituents named in the Stop 1 opening history are not
        foreign venues: only the Stop 7 Sackler reference survives (1 <= 2)."""
        v = _run_qa_verdicts(HARVARD_TOUR, HARVARD_CTX)
        self.assertEqual('PASS', v['single_venue'],
                         "Stop 1 opening history must be skipped — Harvard passes")
        self.assertEqual('PASS', v['coherence'],
                         "constituents in the opening section are not venue drift")

    def test_mcmullen_opening_and_subphrase_pass(self):
        """McMullen's Stop 1 opening (Devlin Gallery + bare 'Art Gallery') is
        skipped, and 'College Museum of Art' is a sub-phrase of the venue."""
        v = _run_qa_verdicts(MCMULLEN_TOUR, MCMULLEN_CTX)
        self.assertEqual('PASS', v['single_venue'],
                         "opening skip + generic drop + venue-alias exemption → McMullen passes")
        self.assertEqual('PASS', v['coherence'],
                         "no genuine drift in the McMullen tour")

    def test_foreign_venue_outside_opening_still_fails(self):
        """A real foreign venue (Isabella Stewart Gardner Museum) named 3× in an
        exhibition stop that is NOT the opening section must still fail."""
        v = _run_qa_verdicts(FOREIGN_TOUR, HARVARD_CTX)
        self.assertEqual('FAIL', v['single_venue'],
                         "a genuinely foreign venue named 3× must stay flagged")


if __name__ == '__main__':
    unittest.main(verbosity=2)
