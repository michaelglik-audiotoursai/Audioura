#!/usr/bin/env python3
"""test_local582_museum_overview.py — LOCAL-582 Deliverable 4.

Rung 3 of the ladder (D607): when a museum resolves and its own site is reachable
but no works/exhibitions can be verified, deliver ONE sourced museum OVERVIEW from
the venue's own pages instead of clean-failing.

The tests drive museum_overview.build_museum_overview with FAKE fetchers (no
network), using LOCAL-580's saved Griffin current-exhibitions fixture and a visit/
hours fixture. The sourced-facts path exercises the REAL machinery:
visitor_facts_extractor.extract_visitor_facts_from_text (LOCAL-35) builds the
VisitorInfoWithProvenance, and build_museum_overview re-verifies every practical
claim through practical_facts_gate.verify_claim_against_source (LOCAL-36 / D538).

Scenarios (from the ticket):
  1. venue resolved + 0 verified works + site pages (Griffin exhibitions + a visit
     page WITH hours) -> overview with SOURCED, dated hours/price, 150-300 words,
     exhibition names present, sources on the venue domain.
  2. a visit page WITHOUT hours -> overview OMITS hours/price (no invention).
  3. no site -> no overview (None) -> rung 4 (LOCAL-580 error path).

Plus: the engine's single-stop tour envelope (_assemble_overview_tour_text) has a
Stop 1 header, a sourced Museum Information line, and the venue-domain sources.

Run: python3 -m pytest test_local582_museum_overview.py -q
"""
import os
import re
import unittest

import museum_overview as mo
from visitor_facts_extractor import (extract_visitor_facts_from_text,
                                     VisitorInfoWithProvenance)

_FIX_DIR = os.path.join(os.path.dirname(__file__), 'tests', 'fixtures')
_EXHIBITIONS_FIXTURE = os.path.join(_FIX_DIR, 'griffin_current_exhibitions.html')
_VISIT_FIXTURE = os.path.join(_FIX_DIR, 'griffin_visit_hours.html')

with open(_EXHIBITIONS_FIXTURE, encoding='utf-8') as _fh:
    _EXHIBITIONS_HTML = _fh.read()
with open(_VISIT_FIXTURE, encoding='utf-8') as _fh:
    _VISIT_HTML = _fh.read()

_HOME_HTML = (
    '<html><body><h1>Griffin Museum of Photography</h1>'
    '<p>The Griffin Museum of Photography is dedicated to promoting the '
    'photographic arts through exhibitions, lectures, and education in '
    'Winchester, Massachusetts.</p></body></html>'
)

# A visit page with NO opening hours and NO admission price — only a welcome.
_VISIT_NO_HOURS_HTML = (
    '<html><body><h1>Visit</h1>'
    '<p>We look forward to welcoming you to the Griffin Museum of Photography. '
    'Please check back soon for details about planning your visit.</p>'
    '</body></html>'
)

_BASE = 'https://griffinmuseum.org'
_AS_OF = 'October 2026'


def _strip_html(html):
    return re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)\b.*?</\1>', ' ', html,
                                          flags=re.DOTALL | re.IGNORECASE))


def _visitor_info_from_html(html, url):
    """Build a real VisitorInfoWithProvenance from a fixture page (LOCAL-35 extractor).

    This is exactly what visitor_facts_extractor.fetch_visitor_info_with_provenance
    returns in production, minus the network fetch — so build_museum_overview runs
    its REAL claim-verification against the REAL extracted facts + source text.
    """
    text = _strip_html(html)
    facts = extract_visitor_facts_from_text(text, 'en')
    facts.source_url = url
    vi = VisitorInfoWithProvenance()
    vi.formatted_info = facts.format_en()
    vi.source_url = url
    vi.source_text = text
    vi.facts = facts
    return vi


def _make_fetcher(visit_html):
    """A fake (html, links) fetcher: exhibitions listing, a visit page, and home."""
    def _fetch(url):
        u = url.rstrip('/')
        if u.endswith('current-exhibitions') or u.endswith('/exhibitions'):
            return _EXHIBITIONS_HTML, []
        if 'visit' in u or 'hours' in u or 'about' in u:
            return visit_html, []
        if u.endswith('griffinmuseum.org'):
            return _HOME_HTML, []
        return '', []
    return _fetch


class TestOverviewWithSourcedHours(unittest.TestCase):
    """Scenario 1: resolved + 0 works + site pages WITH hours -> sourced overview."""

    @classmethod
    def setUpClass(cls):
        visit_vi = _visitor_info_from_html(_VISIT_HTML, _BASE + '/hours-admission')
        cls.ov = mo.build_museum_overview(
            venue_name='Griffin Museum of Photography',
            base_site_url=_BASE,
            locality='Winchester, MA',
            as_of=_AS_OF,
            fetcher=_make_fetcher(_VISIT_HTML),
            visitor_info_provider=lambda u, l: visit_vi,
        )

    def test_overview_is_built(self):
        self.assertIsNotNone(self.ov)
        self.assertFalse(self.ov.is_empty())

    def test_word_band_150_to_300(self):
        wc = len(self.ov.narration.split())
        self.assertTrue(150 <= wc <= 300, f"overview is {wc} words, not in 150-300")

    def test_hours_and_admission_are_sourced_and_present(self):
        # The visit fixture publishes hours (10:00–17:00, closed Monday) and a
        # $10 admission; both must survive verification and reach the narration.
        # (LOCAL-35's extractor normalises the currency symbol; we assert on the
        # amount, which is what traces to the source.)
        self.assertTrue(self.ov.has_hours, "sourced hours did not reach the overview")
        self.assertTrue(self.ov.has_admission, "sourced admission did not reach the overview")
        self.assertIn('10:00', self.ov.narration)
        self.assertRegex(self.ov.narration, r'[€$£]?10\b')

    def test_practical_facts_are_dated_and_attributed(self):
        # The honesty signal: facts are stamped "as listed on <domain>, <month year>".
        self.assertIn('griffinmuseum.org', self.ov.facts_line)
        self.assertIn(_AS_OF, self.ov.facts_line)
        self.assertIn('As listed on griffinmuseum.org', self.ov.narration)

    def test_exhibition_names_present_names_only(self):
        self.assertTrue(self.ov.exhibitions, "no exhibition names surfaced")
        self.assertIn('Lua Kobayashi | The Persistence of Memories', self.ov.exhibitions)
        # Names only — one of the real shows must be named in the narration.
        self.assertIn('Lua Kobayashi', self.ov.narration)

    def test_sources_are_on_the_venue_domain(self):
        self.assertTrue(self.ov.sources)
        for u in self.ov.sources:
            self.assertIn('griffinmuseum.org', u)

    def test_orientation_is_honest_about_being_an_overview(self):
        low = self.ov.narration.lower()
        self.assertIn('could not', low)      # states WHY it is an overview
        self.assertIn('overview', low)


class TestOverviewOmitsUnsourcedHours(unittest.TestCase):
    """Scenario 2: a visit page WITHOUT hours -> overview omits hours (no invention)."""

    @classmethod
    def setUpClass(cls):
        # The extractor finds nothing to confirm on a page with no hours/price.
        visit_vi = _visitor_info_from_html(_VISIT_NO_HOURS_HTML, _BASE + '/visit')
        cls.ov = mo.build_museum_overview(
            venue_name='Griffin Museum of Photography',
            base_site_url=_BASE,
            locality='Winchester, MA',
            as_of=_AS_OF,
            fetcher=_make_fetcher(_VISIT_NO_HOURS_HTML),
            visitor_info_provider=lambda u, l: visit_vi,
        )

    def test_overview_still_built(self):
        # A reachable site always yields an overview — just without unsourced facts.
        self.assertIsNotNone(self.ov)
        self.assertFalse(self.ov.is_empty())

    def test_no_hours_or_admission_claimed(self):
        self.assertFalse(self.ov.has_hours)
        self.assertFalse(self.ov.has_admission)
        self.assertEqual('', self.ov.facts_line)

    def test_no_invented_price_or_time_in_narration(self):
        # Nothing numeric that would read as hours/price may appear.
        self.assertNotIn('$', self.ov.narration)
        self.assertNotIn('10:00', self.ov.narration)
        self.assertNotRegex(self.ov.narration, r'\b\d{1,2}:\d{2}\b')

    def test_exhibition_names_still_present(self):
        # "What is on now" still comes from the exhibitions page.
        self.assertTrue(self.ov.exhibitions)


class TestNoSiteNoOverview(unittest.TestCase):
    """Scenario 3: no usable site -> no overview (None) -> rung 4 (LOCAL-580)."""

    def test_empty_url_returns_none(self):
        ov = mo.build_museum_overview(
            venue_name='Some Museum', base_site_url='',
            fetcher=_make_fetcher(_VISIT_HTML))
        self.assertIsNone(ov)

    def test_unreachable_site_returns_none(self):
        # URL named but every page comes back empty -> no usable site -> None.
        ov = mo.build_museum_overview(
            venue_name='Some Museum', base_site_url='https://nothing.example',
            fetcher=lambda u: ('', []))
        self.assertIsNone(ov)


class TestEngineOverviewEnvelope(unittest.TestCase):
    """The engine renders the overview as a finished single-stop tour."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-used')
        import generate_tour_text as g
        cls.g = g
        visit_vi = _visitor_info_from_html(_VISIT_HTML, _BASE + '/hours-admission')
        cls.ov = mo.build_museum_overview(
            venue_name='Griffin Museum of Photography',
            base_site_url=_BASE,
            locality='Winchester, MA',
            as_of=_AS_OF,
            fetcher=_make_fetcher(_VISIT_HTML),
            visitor_info_provider=lambda u, l: visit_vi,
        )
        cls.text = g._assemble_overview_tour_text(
            'Griffin Museum of Photography',
            'Griffin Museum of Photography, Winchester, MA',
            'museum', cls.ov)

    def test_has_single_stop_header(self):
        headers = re.findall(r'(?mi)^\s*Stop\s+(\d+)\s*[:\-]', self.text)
        self.assertEqual(['1'], headers, "overview must render exactly one Stop")

    def test_has_sourced_museum_information_line(self):
        self.assertRegex(self.text, r'(?mi)^Museum Information:\s*.+')
        self.assertIn('As listed on griffinmuseum.org', self.text)

    def test_lists_venue_domain_sources(self):
        self.assertIn('Sources', self.text)
        self.assertIn('griffinmuseum.org', self.text)

    def test_category_labelled_museum_overview(self):
        self.assertIn('Tour-Category: Museum', self.text)
        self.assertIn('Overview', self.text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
