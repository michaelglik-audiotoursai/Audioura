r"""
test_local616_scraped_language_guard.py — [LOCAL-616 item 3]
============================================================
Tour 414 (Musée Fabre, an ENGLISH tour) shipped an untranslated French fragment
lifted verbatim from the museum's own French pages:

    "de Cherbourg, le musée Fabre expose une œuvre de jeunesse du peintre
     Jacques-Louis David"

A site-scraped sentence must be in the tour language — translate it (cheap LLM)
or drop it. These tests pin the deterministic detector + the drop-only filter,
and the integration in about_museum_stop.build_about_stop (the scraped-story
collector feeds the filter). No network: with no OPENAI_API_KEY the foreign
sentence is DROPPED, never shipped.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import language_guard as lg
import about_museum_stop as am


_FABRE_FRAGMENT = ("de Cherbourg, le musée Fabre expose une œuvre de jeunesse "
                   "du peintre Jacques-Louis David")


class TestLanguageDetector(unittest.TestCase):
    def test_french_fragment_flagged_not_english(self):
        self.assertFalse(lg.is_in_tour_language(_FABRE_FRAGMENT, "en"))

    def test_plain_english_is_english(self):
        self.assertTrue(lg.is_in_tour_language(
            "It was built in 1364 and the collection houses works by Courbet.",
            "en"))

    def test_english_with_accented_proper_nouns_kept(self):
        # A real English sentence that merely contains accented proper nouns must
        # NOT be flagged (no false positive on Musée / Cézanne / François-Xavier).
        self.assertTrue(lg.is_in_tour_language(
            "The Musée Fabre was founded in 1825 by the painter "
            "François-Xavier Fabre and holds a rich collection of European art.",
            "en"))

    def test_other_tour_language_is_noop(self):
        # Non-English tours are not guarded here — never drop their content.
        self.assertTrue(lg.is_in_tour_language(_FABRE_FRAGMENT, "fr"))

    def test_short_fragment_not_judged(self):
        self.assertTrue(lg.is_in_tour_language("Le musée", "en"))

    def test_english_sentence_naming_french_titled_work_kept(self):
        # [LOCAL-616 live] An English sentence that merely names a French-titled
        # painting must NOT be flagged — the French articles are inside a
        # Title-Cased proper noun, not foreign prose. (Live Groeningemuseum run
        # surfaced these as a harness false positive before hardening.)
        for s in (
            "Your first stop is La Mort de la Vierge.",
            "Directions: Your final stop in Groeningemuseum: La Vierge au "
            "chanoine Van der Paele.",
            "The painting La Vue du village hangs in the gallery.",
        ):
            self.assertTrue(lg.is_in_tour_language(s, "en"),
                            f"wrongly flagged English-with-French-title: {s!r}")

    def test_french_prose_with_titlecase_opener_still_caught(self):
        # Genuine French prose is still caught even when it starts with a capital
        # (sentence-initial), because its function words are lowercase mid-sentence.
        self.assertFalse(lg.is_in_tour_language(
            "Le musée expose une collection de peintures et de sculptures anciennes.",
            "en"))


class TestFilterDropsForeign(unittest.TestCase):
    def setUp(self):
        self._saved_key = os.environ.pop("OPENAI_API_KEY", None)

    def tearDown(self):
        if self._saved_key is not None:
            os.environ["OPENAI_API_KEY"] = self._saved_key

    def test_foreign_dropped_english_kept(self):
        eng = "The museum opened in 1828 and holds works by Zurbarán and Courbet."
        out = lg.filter_scraped_sentences([_FABRE_FRAGMENT, eng], "en")
        self.assertNotIn(_FABRE_FRAGMENT, out)
        self.assertIn(eng, out)

    def test_translate_false_is_drop_only(self):
        out = lg.filter_scraped_sentences([_FABRE_FRAGMENT], "en", translate=False)
        self.assertEqual(out, [])

    def test_no_api_key_drops_without_network(self):
        # Deterministic: no key → translate_to_english returns None → dropped.
        self.assertIsNone(lg.translate_to_english(_FABRE_FRAGMENT))
        out = lg.filter_scraped_sentences([_FABRE_FRAGMENT], "en")
        self.assertEqual(out, [])


class TestFilterForeignSentencesInText(unittest.TestCase):
    """[LOCAL-616 item 3] The delivered-text sweep used by the every-path guard:
    drops a genuinely-foreign sentence wherever it entered (the fresh-path closing
    recap leaked untranslated French), keeps English, never disturbs structural
    lines."""

    def setUp(self):
        self._saved_key = os.environ.pop("OPENAI_API_KEY", None)

    def tearDown(self):
        if self._saved_key is not None:
            os.environ["OPENAI_API_KEY"] = self._saved_key

    def test_french_recap_fragment_dropped(self):
        text = (
            "Stop 1: Portrait de Madame Cézanne\n\n"
            "Address: Place Saint-Jean, Aix-en-Provence\n\n"
            "From Portrait de Madame Cézanne to Leicester Square, you have followed "
            "the thread of the collection. "
            "Il faut cependant attendre 1838 pour que le musée d'Aix soit "
            "officiellement inauguré, à l'occasion de la remise des prix. "
            "That's 3 stops in all.\n"
        )
        new, dropped = lg.filter_foreign_sentences_in_text(text, "en")
        self.assertEqual(len(dropped), 1)
        self.assertNotIn("Il faut cependant", new)
        self.assertIn("you have followed the thread", new)
        self.assertIn("That's 3 stops in all.", new)
        self.assertIn("Stop 1: Portrait de Madame Cézanne", new)
        self.assertIn("Address: Place Saint-Jean, Aix-en-Provence", new)

    def test_structural_lines_never_judged(self):
        text = ("Stop 2: Jupiter et Thétis\n\n"
                "Directions: Continue through Musée Granet — next is Jupiter et Thétis.\n")
        new, dropped = lg.filter_foreign_sentences_in_text(text, "en")
        self.assertEqual(dropped, [])
        self.assertIn("Directions: Continue through Musée Granet", new)

    def test_english_recap_with_french_titles_kept(self):
        text = "This tour covered Jupiter et Thétis and Leicester Square, la nuit.\n"
        new, dropped = lg.filter_foreign_sentences_in_text(text, "en")
        self.assertEqual(dropped, [])
        self.assertIn("This tour covered", new)


class TestBuildAboutStopIntegration(unittest.TestCase):
    """The scraped-story collector in build_about_stop must route through the
    language guard, so a French sentence on the venue's page never reaches
    narration in an English tour."""

    def setUp(self):
        self._saved_key = os.environ.pop("OPENAI_API_KEY", None)

    def tearDown(self):
        if self._saved_key is not None:
            os.environ["OPENAI_API_KEY"] = self._saved_key

    def test_french_page_sentence_not_in_narration(self):
        # A fetcher returning a venue page that mixes an English founding sentence
        # with the French fragment. The English story is kept; the French dropped.
        english = ("The Musée Fabre was founded in 1825 by the painter "
                   "François-Xavier Fabre. It is one of the richest public art "
                   "collections in France.")
        html = (f"<html><body><p>{english}</p>"
                f"<p>{_FABRE_FRAGMENT}.</p></body></html>")

        def fetcher(url):
            return (html, [])

        about = am.build_about_stop(
            venue_name="Musée Fabre",
            base_site_url="https://museefabre.fr",
            request_text="Museum tour of Musée Fabre",
            locality="Montpellier, France",
            fetcher=fetcher,
            wiki_provider=None,
        )
        # build_about_stop may return None if it sources nothing; this fixture
        # yields an English founding sentence, so a stop should be built.
        self.assertIsNotNone(about)
        self.assertNotIn("expose une", about.narration)
        self.assertNotIn("œuvre de jeunesse", about.narration)
        self.assertNotIn("peintre Jacques-Louis David", about.narration)


if __name__ == "__main__":
    unittest.main(verbosity=2)
