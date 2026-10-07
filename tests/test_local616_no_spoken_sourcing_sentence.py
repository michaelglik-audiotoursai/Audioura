r"""
test_local616_no_spoken_sourcing_sentence.py — [LOCAL-616 item 2 / D617]
========================================================================
The kiro-cli critique of Musée Fabre tour 414 flagged a SPOKEN source list in
Stop 1:

    "This account is drawn from the museum's own pages on museefabre.fr and
     public reference sources."

D617: no domain or source list is spoken — the source lives in the TEXT-view
Sources line only. These tests CALL the real About composer
(about_museum_stop._compose_about_narration) and assert the sentence is gone,
and that AboutStop.sources (which feeds the text-view Sources block) still
carries the sourcing. RED on base, GREEN after.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import about_museum_stop as am


class TestNoSpokenSourcingSentence(unittest.TestCase):
    def _narration(self, wiki_summary=""):
        return am._compose_about_narration(
            museum_name="Musée Fabre",
            locality="Montpellier, France",
            story_sentences=[
                "The Musée Fabre was founded in 1825 by the painter François-Xavier Fabre.",
                "It holds one of the richest public collections of European art in France.",
            ],
            arch_sentences=[],
            wiki_summary=wiki_summary,
            domain="museefabre.fr",
        )

    def test_no_drawn_from_sentence(self):
        text = self._narration()
        self.assertNotIn("This account is drawn from", text)
        self.assertNotIn("public reference sources", text)

    def test_no_domain_spoken_even_with_wiki(self):
        text = self._narration(
            wiki_summary="The Musée Fabre is a museum in Montpellier, France.")
        self.assertNotIn("This account is drawn from", text)
        self.assertNotIn("public reference sources", text)
        # No bare domain leaks into narration either (D617).
        self.assertNotIn("museefabre.fr", text)
        self.assertNotRegex(text, r"\.(fr|edu|org|com|net)\b")

    def test_story_still_present(self):
        # Removing the sourcing close must NOT drop the actual story.
        text = self._narration()
        self.assertIn("Musée Fabre was founded in 1825", text)


class TestSourcingPreservedInTextView(unittest.TestCase):
    """The source provenance must survive on AboutStop.sources — the field that
    becomes the text-view Sources block — so removing the spoken line loses no
    attribution, it just moves it out of narration."""

    def _fetcher(self, html, links):
        def _f(url):
            return (html, links)
        return _f

    def test_about_stop_unit_carries_sources(self):
        # about_stop_unit() must expose the sources list for the text view.
        about = am.AboutStop(
            museum_name="Musée Fabre",
            narration="The Musée Fabre was founded in 1825.",
            orientation="You are at Musée Fabre.",
            sources=["https://museefabre.fr/histoire",
                     "https://en.wikipedia.org/wiki/Mus%C3%A9e_Fabre"],
            site_domain="museefabre.fr",
        )
        unit = am.about_stop_unit(about)
        self.assertIn("museefabre.fr/histoire", " ".join(unit["sources"]))
        # And the narration carries no spoken sourcing sentence.
        self.assertNotIn("This account is drawn from", unit["narration"])


class TestVisitingPointersAreDomainFree(unittest.TestCase):
    """[LOCAL-616 item 2 / D617] The website pointers used when hours/admission
    can't be sourced must NOT speak a source domain (the Groeninge live run flagged
    'Opening hours are listed on museabrugge.be'). They point generically to
    'the museum's website'."""

    def test_full_fallback_pointer_has_no_domain(self):
        s = am._visiting_fallback_sentence("museabrugge.be")
        self.assertNotIn("museabrugge.be", s)
        self.assertIn("the museum's website", s)
        # Must still match the hours-fold regex so the preflight can replace it.
        import stop_pool_orchestrator as orch
        self.assertRegex(s, orch._CHECK_HOURS_FALLBACK_RE)

    def test_partial_pointer_hours_missing_no_domain(self):
        # admission known, hours missing → "Opening hours are listed on <generic>."
        s = am._partial_pointer_sentence("Admission is free", "museabrugge.be")
        self.assertNotIn("museabrugge.be", s)
        self.assertIn("Opening hours are listed on the museum's website", s)

    def test_partial_pointer_admission_missing_no_domain(self):
        # hours known, admission missing → "Admission prices are listed on <generic>."
        s = am._partial_pointer_sentence("Open Monday to Friday, 10 AM to 5 PM",
                                         "bc.edu")
        self.assertNotIn("bc.edu", s)
        self.assertIn("Admission prices are listed on the museum's website", s)


if __name__ == "__main__":
    unittest.main(verbosity=2)