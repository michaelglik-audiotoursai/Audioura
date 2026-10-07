r"""
LOCAL-614 item 4 — the SPOKEN visiting signal carries no source domain (D617).
=========================================================================
The kiro-cli critique of McMullen tour 399 found a spoken source tag:

    "Admission is free, as listed on bc.edu in October 2026."

Per D617 no domain is spoken — the source domain lives in the TEXT view only.
The honesty stamp (the month the facts were current) stays, without the domain:

    "as published by the museum in October 2026"

These tests CALL the real composer (about_museum_stop._source_month_signal and
_compose_visiting_sentences). RED on base (the spoken signal reads "as listed on
<domain> in <month>"), GREEN after.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import about_museum_stop as am


class TestSourceMonthSignalNoDomain(unittest.TestCase):
    def test_signal_omits_domain_keeps_month(self):
        sig = am._source_month_signal("bc.edu", "October 2026")
        self.assertNotIn("bc.edu", sig)
        self.assertNotIn("as listed on", sig.lower())
        self.assertEqual(sig, "as published by the museum in October 2026")

    def test_signal_without_month_still_no_domain(self):
        sig = am._source_month_signal("griffinmuseum.org", "")
        self.assertNotIn("griffinmuseum.org", sig)
        self.assertEqual(sig, "as published by the museum")

    def test_signal_ignores_any_domain(self):
        for dom in ("bc.edu", "griffinmuseum.org", "www.example-museum.org", ""):
            sig = am._source_month_signal(dom, "October 2026")
            self.assertNotRegex(sig, r"\.(edu|org|com|net)\b",
                                f"domain leaked into spoken signal: {sig!r}")


class TestComposedVisitingSentenceNoDomain(unittest.TestCase):
    def _section(self, facts):
        return am._compose_visiting_sentences(
            facts, "Griffin Museum of Photography", "griffinmuseum.org",
            "October 2026")

    def test_spoken_section_has_no_domain(self):
        section = self._section(
            "Open Tuesday through Sunday, Noon–4 PM. "
            "$12 for adults, $8 for seniors, students and teachers")
        self.assertNotIn("griffinmuseum.org", section)
        self.assertNotRegex(section, r"(?i)as listed on")
        # The honesty stamp (month) and the no-domain phrasing both present.
        self.assertRegex(section, r"(?i)as published by the museum in October 2026")

    def test_free_admission_line_no_domain(self):
        # The exact McMullen shape the critique flagged ("free, as listed on
        # bc.edu in October 2026") must now read without the domain.
        section = am._compose_visiting_sentences(
            "Open Monday–Friday 10 AM–5 PM. Free admission",
            "McMullen Museum of Art", "bc.edu", "October 2026")
        self.assertNotIn("bc.edu", section)
        self.assertIn("as published by the museum in October 2026", section)


if __name__ == "__main__":
    unittest.main(verbosity=2)
