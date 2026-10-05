#!/usr/bin/env python3
"""test_local584_venue_bound_hours.py — LOCAL-584 r2.

Why it bounced (LEAD review, 2026-10-05): the r1 currency fix was right
(Griffin $12), but the hours it stated for the Griffin Museum — "8 AM–8 PM" —
are the Lafayette City Center *satellite* gallery's hours, not the museum's.
A listener told "8 AM–8 PM" arrives four hours before the museum opens
(Tue–Sun, Noon–4 PM). Hours must be BOUND TO THE VENUE.

The committed fixture tests/fixtures/griffin_about_2026.html lists, in order:
  <h2>Hours</h2>  Tuesday through Sunday: Noon to 4 PM  Closed: Every Monday …
  <em>Satellite Galleries</em>  Lafayette City Center Gallery  8 AM – 8 PM daily.
                                Jenks Center Gallery  Monday through Friday 9 AM — 4 PM
  <h2>Admission</h2>  General Admission: $12 for adults …
  footer: 67 Shore Road, Winchester, Ma 01890 … Hours: Tues-Sun Noon-4pm

These tests pin that the extractor reads ONLY the venue's own section:
  - hours are Noon–4 PM (never 8 AM, never 9 AM),
  - closed day is Monday,
  - admission is $12 (never €),
  - every token the facts carry is on the page.

RED on 37f6000 (the pre-r2 extractor binds to the first time range it sees,
the satellite "8 AM–8 PM"); GREEN after. The French regression lives in
test_local584_practical_facts_currency.py and is unaffected (scoping is a
no-op on a page with no heading sentinels).

Run: python3 -m pytest test_local584_venue_bound_hours.py -q
"""
import os
import re
import unittest

from visitor_facts_extractor import (
    _html_to_sectioned_text,
    extract_visitor_facts_from_text,
)

try:
    from practical_facts_gate import claim_tokens_in_source
    _GATE = True
except Exception:  # pragma: no cover
    _GATE = False

    def claim_tokens_in_source(*_a, **_k):  # type: ignore
        raise AssertionError("claim_tokens_in_source missing")

_FIX = os.path.join(os.path.dirname(__file__), 'tests', 'fixtures',
                    'griffin_about_2026.html')
_VENUE_NAME = "Griffin Museum of Photography"
_VENUE_ADDR = "67 Shore Road, Winchester, MA"

with open(_FIX, encoding='utf-8') as _fh:
    _HTML = _fh.read()

# Sectioned flattening (keeps heading boundaries) — this is what the live
# pipeline now produces via _fetch_visitor_pages.
_SECTIONED = _html_to_sectioned_text(_HTML)


def _plain(html: str) -> str:
    html = re.sub(r'<(script|style)\b.*?</\1>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<[^>]+>', ' ', html)
    return re.sub(r'\s+', ' ', html).strip()


_PLAIN = _plain(_HTML)


class TestFixtureStructure(unittest.TestCase):
    """The fixture really is the LEAD-described multi-place page."""

    def test_satellite_hours_present_in_raw_page(self):
        # The satellite hours ARE on the page — the point is they must not be the
        # venue's stated hours.
        self.assertIn('8 AM', _PLAIN)
        self.assertIn('9 AM', _PLAIN)
        self.assertIn('Noon to 4 PM', _PLAIN)
        self.assertIn('Satellite Galleries', _PLAIN)

    def test_sectioning_inserts_boundaries(self):
        self.assertIn('\x1e', _SECTIONED,
                      "sectioned flattening must mark heading boundaries")


class TestVenueBoundHours(unittest.TestCase):
    """Hours/closed-days bind to the venue's own section — the r2 contract."""

    @classmethod
    def setUpClass(cls):
        cls.facts = extract_visitor_facts_from_text(
            _SECTIONED, 'en', venue_name=_VENUE_NAME, venue_address=_VENUE_ADDR)
        cls.formatted = cls.facts.format_en()

    def test_hours_are_the_venue_not_the_satellite(self):
        joined = ' '.join(h['time'] for h in self.facts.hours)
        self.assertNotIn('8 AM', joined,
                         f"hours must not be the Lafayette satellite's 8 AM: {self.facts.hours}")
        self.assertNotIn('9 AM', joined,
                         f"hours must not be the Jenks satellite's 9 AM: {self.facts.hours}")
        self.assertNotIn('08:00', joined)
        self.assertNotIn('20:00', joined)

    def test_hours_state_noon_to_4pm(self):
        joined = ' '.join(h['time'] for h in self.facts.hours).lower()
        self.assertTrue(self.facts.hours, "the venue's hours must be extracted")
        self.assertIn('4 pm', joined, f"venue hours are Noon–4 PM: {self.facts.hours}")
        self.assertRegex(joined, r'noon|12', f"venue hours open at Noon: {self.facts.hours}")

    def test_closed_monday(self):
        self.assertIn('Monday', self.facts.closed_days,
                      f"the venue closes Mondays: {self.facts.closed_days}")

    def test_admission_is_dollar_12(self):
        self.assertIn('$12', self.facts.admission,
                      f"admission is $12: {self.facts.admission!r}")
        self.assertNotIn('€', self.facts.admission)

    def test_formatted_has_no_satellite_hours_no_euro(self):
        self.assertNotIn('8 AM', self.formatted)
        self.assertNotIn('9 AM', self.formatted)
        self.assertNotIn('€', self.formatted)
        self.assertIn('4 PM', self.formatted)
        self.assertIn('Monday', self.formatted)
        self.assertIn('$12', self.formatted)

    def test_every_token_is_on_the_page(self):
        self.assertTrue(claim_tokens_in_source(self.formatted, _PLAIN.lower()),
                        f"formatted facts carry a token not on the page: {self.formatted!r}")


class TestScopingIsNoOpWithoutSentinels(unittest.TestCase):
    """A page with no heading sentinels is unchanged — French plain-text pages safe."""

    def test_plain_single_section_text_unchanged(self):
        # A simple one-venue page (no sentinels, no foreign-place heading): the
        # scoper must not drop its only hours.
        txt = ("Opening hours Museum open daily except Tuesdays. "
               "Open from 10 am to 6 pm. Museum Ticket 12€.")
        facts = extract_visitor_facts_from_text(txt, 'en', venue_name="Some Museum")
        self.assertTrue(facts.hours, "a single-section page must keep its hours")


if __name__ == '__main__':
    unittest.main(verbosity=2)
