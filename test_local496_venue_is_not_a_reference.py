#!/usr/bin/env python3
"""LOCAL-496 — the venue is the setting, not an unexplained reference.

**How Michael's Fridman objection survived the LOCAL-494 fix.** LOCAL-494 stopped
the unglossed gate degrading a documented donor. The 2026-08-19 11:51 live run
then lost Fridman anyway, by a different route — a cascade in which only the
FIRST step is wrong:

  :454  the unglossed gate degraded **"Fine Arts"** — a fragment of the venue's
        own name — turning "The Museum of Fine Arts, Boston" into
        "The Museum Boston"
  :476  LOCAL-479's organisation grounding gate searched the corpus for an
        organisation called "The Museum Boston", found nothing (it exists
        nowhere on earth), called it ungrounded and DROPPED THE SENTENCE:
        *"...proudly hosts this piece, thanks to the generosity of Boris
        Fridman, who donated..."*
  :537  the LOCAL-476 retry then FORBADE that relationship, so the regeneration
        could not restore him either.

Gates two and three behaved correctly on the input they were handed. The whole
defect is at :454, and it is the same class as LOCAL-475 (the stop's own artist,
degraded out of a sentence about his own book) and LOCAL-494 (the documented
donor): **the gate deleting something that is the subject or the setting rather
than an incidental reference.**

**The near-miss worth recording.** The obvious wiring was `venue_name=location`.
`location` on this run is the REQUEST string — *"Picasso, Miro, Dali: Unbound
exhibition at MFA, Boston, MA"* — whose capitalised spans are **Picasso, Miro and
Dali**. That would have exempted the three artists the gate most needs to check,
and it would have exempted nothing named "Fine Arts", so the bug would have
survived while looking fixed. `_museum_venue_name` (resolved at
`generate_tour_text.py:5157`) is the correct source.
"""
import unittest

from unglossed_reference_gate import _venue_fragments, detect_unglossed_references


class TestVenueFragments(unittest.TestCase):

    def test_extracts_the_internal_span_that_was_degraded(self):
        """"Fine Arts" is the exact string the 11:51 run deleted."""
        frags = _venue_fragments('Museum of Fine Arts, Boston')
        self.assertIn('Fine Arts', frags)

    def test_keeps_the_whole_name_and_the_head(self):
        frags = _venue_fragments('Museum of Fine Arts, Boston')
        self.assertIn('Museum of Fine Arts, Boston', frags)
        self.assertIn('Museum of Fine Arts', frags)

    def test_keeps_the_city(self):
        self.assertIn('Boston', _venue_fragments('Museum of Fine Arts, Boston'))

    def test_handles_missing_venue(self):
        for empty in (None, '', '   ', 123, []):
            self.assertEqual(_venue_fragments(empty), [])

    def test_short_fragments_are_not_offered(self):
        """A two-letter span would exempt half the tour."""
        for frag in _venue_fragments('Museum of Fine Arts, Boston'):
            self.assertGreaterEqual(len(frag), 4)


class TestTheNearMiss(unittest.TestCase):
    """`location` would have exempted the artists and missed the bug."""

    REQUEST = 'Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA'

    def test_the_request_string_yields_the_artists(self):
        frags = _venue_fragments(self.REQUEST)
        for artist in ('Picasso', 'Miro', 'Dali'):
            self.assertIn(artist, frags,
                          'guard the wiring: this is why location is wrong')

    def test_the_request_string_does_not_yield_the_broken_fragment(self):
        """So wiring `location` fixes nothing while appearing to."""
        self.assertNotIn('Fine Arts', _venue_fragments(self.REQUEST))


class TestExemptionSuppressesDetection(unittest.TestCase):
    """End of the line: an exempted fragment is never a candidate."""

    SENTENCE = ("The Museum of Fine Arts, Boston, proudly hosts this piece, "
                "thanks to the generosity of Boris Fridman, who donated it "
                "in 2019.")

    def test_fine_arts_is_detected_without_the_exemption(self):
        """Control — without this, the test below proves nothing."""
        found = {r['entity'] for r in
                 detect_unglossed_references(self.SENTENCE)}
        self.assertTrue(any('Fine Arts' in e or 'Museum' in e for e in found),
                        f'expected the venue to be flagged, got {found}')

    def test_venue_fragments_are_not_flagged_when_exempt(self):
        exempt = _venue_fragments('Museum of Fine Arts, Boston')
        found = {r['entity'] for r in
                 detect_unglossed_references(self.SENTENCE, exempt=exempt)}
        for frag in ('Fine Arts', 'Museum of Fine Arts',
                     'Museum of Fine Arts, Boston'):
            self.assertNotIn(frag, found, f'{frag!r} still flagged')

    # `SENTENCE` above explains Fridman inline ("who donated it in 2019"), so the
    # gate correctly does not flag him there — which matches the live run, where
    # only "Fine Arts" and "Mourlot Frères" were flagged. To prove the exemption
    # is NARROW we need a sentence where he genuinely is a candidate.
    DONOR_UNEXPLAINED = ("The Museum of Fine Arts, Boston, acquired the book "
                         "from Boris Fridman.")

    def test_the_donor_is_still_flagged(self):
        """The exemption must be narrow: Fridman is not part of the venue.

        He is handled by LOCAL-494's provenance path, which requires him to be
        DETECTED first. An over-broad venue exemption would silently disable
        LOCAL-494 while looking like a fix — so this asserts the exemption
        removes the venue and nothing else.
        """
        exempt = _venue_fragments('Museum of Fine Arts, Boston')
        plain = {r['entity'] for r in
                 detect_unglossed_references(self.DONOR_UNEXPLAINED)}
        self.assertIn('Fine Arts', plain)      # control: the bug is present
        self.assertIn('Boris Fridman', plain)  # control: the donor is a candidate

        found = {r['entity'] for r in
                 detect_unglossed_references(self.DONOR_UNEXPLAINED, exempt=exempt)}
        self.assertNotIn('Fine Arts', found, 'venue fragment still flagged')
        self.assertIn('Boris Fridman', found,
                      f'the donor stopped being detected: {found}')


if __name__ == '__main__':
    unittest.main(verbosity=2)
