#!/usr/bin/env python3
"""test_local580_structural_extraction.py — Deliverable 1 (LOCAL-580).

Structural title extraction for exhibition museums.

The defect (Michael, 2026-10-05, job 7fe11ab9): the Griffin Museum of Photography
current-exhibitions page lists each show as an <h2> heading linking to its own
/show/<slug>/ detail page. The old plaintext extractor missed every one of them
and instead scraped a FlipBook viewer's button labels ("Toggle Fullscreen",
"Next Page", "Download PDF File", "Zoom Out", ...) as 22 "canonical titles".

The structural extractor (exhibition_discovery.extract_current_exhibitions) must,
WITHOUT keyword lists of show names (D476):
  * return the real exhibitions — headings that LINK to a detail page on the
    venue's own domain
  * reject every FlipBook/viewer control (buttons, aria-labels)
  * reject nav and footer ("Footer", "Home", "Contact", ...)
  * reject on-page structural headings that are not exhibitions and do not link
    to a detail page ("Winchester Galleries", "Virtual Galleries").

Run: python3 -m pytest test_local580_structural_extraction.py -q
"""
import os
import unittest

from exhibition_discovery import extract_current_exhibitions

_FIXTURE = os.path.join(
    os.path.dirname(__file__), 'tests', 'fixtures',
    'griffin_current_exhibitions.html'
)

# The real current exhibitions, exactly as published as <h2> headings.
EXPECTED_EXHIBITIONS = {
    'Lua Kobayashi | The Persistence of Memories',
    'Homage | Robert Frank: The Americans',
    'Tabitha Soren | An Artist Life',
    'Intertidal : Field Notes',
    'BU Masters Show 2026 | Traces: Pursuing Process',
    'Earth, Wind & Fire',
    'ULTRASOUND',
    'TLC',
}

# Every FlipBook viewer control + nav/footer heading that must NEVER appear.
FORBIDDEN_LABELS = {
    'Toggle Fullscreen', 'Next Page', 'Previous Page', 'Download PDF File',
    'Zoom In', 'Zoom Out', 'Toggle Thumbnails', 'Toggle Sound', 'Share',
    'First Page', 'Last Page', 'Print', 'Start Presentation', 'More options',
    'Footer', 'Home', 'Contact', 'Hours & Admission', 'Privacy Policy',
    'Winchester Galleries', 'Virtual Galleries', 'Exhibition Catalog',
    'Current Exhibitions',
}


class TestStructuralExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(_FIXTURE, encoding='utf-8') as fh:
            cls.html = fh.read()
        cls.result = extract_current_exhibitions(
            cls.html, base_url='https://griffinmuseum.org/current-exhibitions/'
        )
        cls.titles = {e['title'] for e in cls.result}

    def test_includes_every_real_exhibition(self):
        missing = EXPECTED_EXHIBITIONS - self.titles
        self.assertEqual(
            set(), missing,
            f"Structural extractor dropped real exhibitions: {sorted(missing)}"
        )

    def test_excludes_every_flipbook_and_nav_label(self):
        leaked = FORBIDDEN_LABELS & self.titles
        self.assertEqual(
            set(), leaked,
            f"Structural extractor admitted UI chrome / nav / footer: {sorted(leaked)}"
        )

    def test_only_the_real_exhibitions_no_extras(self):
        # The extracted set is EXACTLY the real exhibitions — no FlipBook noise,
        # no stray headings. This is the whole point of structural extraction.
        self.assertEqual(EXPECTED_EXHIBITIONS, self.titles)

    def test_each_exhibition_carries_its_on_domain_detail_url(self):
        for e in self.result:
            self.assertTrue(e.get('detail_url'), f"no detail_url for {e['title']}")
            self.assertIn(
                'griffinmuseum.org', e['detail_url'],
                f"detail_url not on venue domain: {e['detail_url']}"
            )
            self.assertIn('/show/', e['detail_url'],
                          f"detail_url is not a per-item page: {e['detail_url']}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
