#!/usr/bin/env python3
"""test_local593_constituent_venues.py — Deliverable 1 (LOCAL-593).

The Harvard Art Museums (Q3783572) are ONE venue made of three constituent
museums: the Fogg Museum, the Busch-Reisinger Museum and the Arthur M. Sackler
Museum. The content-QA single-venue consistency check (and the venue-coherence
check) flagged "Sackler Museum" and "Reisinger Museum" as foreign venues and
failed the tour.

The fix carries the venue's own constituents/siblings (Wikidata P527/P361/P749)
in venue_context['sibling_venues']; both checks exempt a named-venue reference
that carries a distinctive token of one of them. The list is derived from
Wikidata — never hard-coded — so a genuinely foreign venue (Isabella Stewart
Gardner Museum, Peabody Essex, Worcester Art Museum) stays flagged.

This test drives the REAL content_qa_runner.run_qa and reads the printed check
verdicts, so it proves the production path — not a re-implementation.

RED on 0315513:  run_qa ignores sibling_venues → the constituent references
                 FAIL single-venue consistency and venue coherence.
GREEN after fix: with sibling_venues both checks PASS; foreign venues still FAIL.

Run: python3 -m pytest tests/test_local593_constituent_venues.py -q
"""
import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import content_qa_runner


HARVARD_SIBLINGS = [
    "Fogg Museum",
    "Busch-Reisinger Museum",
    "Arthur M. Sackler Museum",
    "Harvard University Art Museums",
]

# A museum tour that names three Harvard constituents in its prose (stops 1 & 3).
CONSTITUENT_TOUR = """Audio Guided Tour: Harvard Art Museums - Museum Tour
Tour-Category: museum

Stop 1: Light Court
Address: 32 Quincy Street, Cambridge, MA
Coordinates: 42.3744, -71.1140
The glass-roofed Calderwood Courtyard anchors the building. Works from the Fogg Museum are shown here. The Busch-Reisinger Museum lends several works.

Stop 2: Prints Gallery
Address: 32 Quincy Street, Cambridge, MA
Coordinates: 42.3744, -71.1140
Works on paper rotate frequently to limit light exposure in this teaching space.

Stop 3: Reading Room
Address: 32 Quincy Street, Cambridge, MA
Coordinates: 42.3744, -71.1140
Holdings associated with the Arthur M. Sackler Museum are consulted by appointment.
"""

# A museum tour that names three genuinely FOREIGN museums.
FOREIGN_TOUR = """Audio Guided Tour: Harvard Art Museums - Museum Tour
Tour-Category: museum

Stop 1: Light Court
Address: 32 Quincy Street, Cambridge, MA
Coordinates: 42.3744, -71.1140
Works are shown on this level. The Isabella Stewart Gardner Museum sits nearby.

Stop 2: Prints Gallery
Address: 32 Quincy Street, Cambridge, MA
Coordinates: 42.3744, -71.1140
Items here are compared to holdings at the Peabody Essex Museum downtown.

Stop 3: Modern Gallery
Address: 32 Quincy Street, Cambridge, MA
Coordinates: 42.3744, -71.1140
Loans from the Worcester Art Museum appear in this bright room upstairs.
"""


def _run_qa_verdicts(tour_text, venue_context):
    """Run the real run_qa and return {check_name_fragment: 'PASS'|'FAIL'}."""
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


class TestConstituentExemption(unittest.TestCase):
    def test_constituents_pass_with_siblings(self):
        ctx = {'venue_tokens': {'harvard', 'art', 'museums'},
               'city': 'Cambridge', 'region': 'MA', 'artist': '', 'tier': 'rich',
               'sibling_venues': HARVARD_SIBLINGS}
        v = _run_qa_verdicts(CONSTITUENT_TOUR, ctx)
        self.assertEqual('PASS', v['single_venue'],
                         "Fogg/Busch-Reisinger/Sackler must be exempt as constituents")
        self.assertEqual('PASS', v['coherence'],
                         "constituents must not count as venue drift")

    def test_constituents_fail_without_siblings(self):
        """Baseline: without the sibling list the constituents are flagged."""
        v = _run_qa_verdicts(CONSTITUENT_TOUR, {'sibling_venues': []})
        self.assertEqual('FAIL', v['single_venue'])
        self.assertEqual('FAIL', v['coherence'])

    def test_foreign_venues_still_flagged_with_siblings(self):
        """A genuinely foreign venue is not a constituent and stays flagged even
        with the Harvard sibling list present."""
        ctx = {'venue_tokens': {'harvard', 'art', 'museums'},
               'city': 'Cambridge', 'region': 'MA', 'artist': '', 'tier': 'rich',
               'sibling_venues': HARVARD_SIBLINGS}
        v = _run_qa_verdicts(FOREIGN_TOUR, ctx)
        # Venue coherence catches the drift to Gardner / Peabody Essex / Worcester.
        self.assertEqual('FAIL', v['coherence'],
                         "foreign venues must remain flagged as drift")


if __name__ == '__main__':
    unittest.main(verbosity=2)
