#!/usr/bin/env python3
"""test_local627_about_truncation_and_length.py — LOCAL-627 defects 1 and 3.

Defect 1 — truncated snippets spoken. The Uffizi About section shipped
    "built by Giorgio Vasari in 1565 on the ord... In 1675 the Uffizi was
     enriched by the collection of."
and the Prado shipped "… and w.". A sentence containing "..."/"…", a mid-word cut,
or ending on a dangling preposition/article/"of." must never be spoken. Fixed at
source (about_museum_stop._is_story_sentence / dedupe_sentences / the composed
narration) plus a final spoken-text safety check (scrub_truncated_sentences).

Defect 3 — the About section is at most 3 sentences, about what the museum is and
why it matters (no corridor/accession trivia padding, no truncation).

These tests drive the REAL functions with a FAKE fetcher (no network/LLM). RED on
base, GREEN after.

Run: python3 -m pytest test_local627_about_truncation_and_length.py -q
"""
import re
import unittest

import about_museum_stop as am


# A Uffizi "About / history" page whose scraped prose carries the exact truncated
# snippets the critic flagged on tour 488 — a literal ellipsis mid-sentence, a
# sentence ending on "collection of.", and a clean identity + why-it-matters pair.
_UFFIZI_ABOUT_HTML = (
    "<html><body>"
    "<h1>About the Uffizi Gallery</h1>"
    "<p>The Uffizi Gallery is one of the most important art museums in the world, "
    "home to the finest collection of Italian Renaissance painting.</p>"
    "<p>It was built by Giorgio Vasari in 1565 on the ord... In 1675 the Uffizi "
    "was enriched by the collection of.</p>"
    "<p>The gallery draws millions of visitors a year to see works by Botticelli, "
    "Leonardo and Michelangelo.</p>"
    "</body></html>"
)

_PRADO_ABOUT_HTML = (
    "<html><body>"
    "<h1>About the Museo del Prado</h1>"
    "<p>The Museo del Prado is the main Spanish national art museum, holding one of "
    "the world's finest collections of European art.</p>"
    "<p>The collection grew from the Spanish Royal Collection and w.</p>"
    "<p>It is renowned for the most comprehensive holdings of Goya, Velázquez and "
    "Bosch.</p>"
    "</body></html>"
)


def _fetcher_for(html):
    def _f(url):
        u = url.rstrip("/")
        if any(u.endswith(s) for s in ("about", "about-us", "history", "mission",
                                       "about-the-museum", "gallery/about")):
            return html, []
        return "", []
    return _f


class TestTruncationPredicate(unittest.TestCase):
    """is_truncated_fragment is the single deterministic predicate for defect 1."""

    def test_literal_ellipsis_three_dots(self):
        self.assertTrue(am.is_truncated_fragment(
            "built by Giorgio Vasari in 1565 on the ord... In 1675 the Uffizi."))

    def test_unicode_ellipsis(self):
        self.assertTrue(am.is_truncated_fragment("The collection grew and spread…"))

    def test_ends_in_of(self):
        self.assertTrue(am.is_truncated_fragment(
            "In 1675 the Uffizi was enriched by the collection of."))

    def test_ends_in_preposition(self):
        self.assertTrue(am.is_truncated_fragment("The works were moved to."))

    def test_ends_in_article(self):
        self.assertTrue(am.is_truncated_fragment("The painting hangs in the."))

    def test_midword_cut_single_letter(self):
        self.assertTrue(am.is_truncated_fragment("The collection grew and w."))

    def test_midword_cut_short_remnant(self):
        self.assertTrue(am.is_truncated_fragment(
            "The palace was built by Vasari on the ord."))

    def test_clean_sentence_not_flagged(self):
        self.assertFalse(am.is_truncated_fragment(
            "The Uffizi houses the finest collection of Italian Renaissance painting."))

    def test_sentence_ending_long_word_not_flagged(self):
        # Regression: a long word ending in a short tail ("education") is NOT a cut.
        self.assertFalse(am.is_truncated_fragment(
            "The museum is dedicated to the promotion of art and education."))

    def test_sentence_ending_real_short_word_not_flagged(self):
        self.assertFalse(am.is_truncated_fragment(
            "The works trace Italian painting from the Middle Ages to now."))


class TestScrubSafetyCheck(unittest.TestCase):
    """scrub_truncated_sentences drops only the fragments, keeps clean sentences."""

    def test_mixed_text_scrubbed(self):
        text = ("The Uffizi is a great museum. It was built by Vasari in 1565 on "
                "the ord. The gallery draws millions of visitors a year.")
        out = am.scrub_truncated_sentences(text)
        self.assertIn("The Uffizi is a great museum.", out)
        self.assertIn("The gallery draws millions of visitors", out)
        self.assertNotIn("on the ord", out)

    def test_clean_text_unchanged(self):
        text = "The Uffizi houses Italian Renaissance painting. It is world famous."
        self.assertEqual(am.scrub_truncated_sentences(text), text)


class TestUffiziAboutNoTruncation(unittest.TestCase):
    def setUp(self):
        self.about = am.build_about_stop(
            venue_name="Uffizi Gallery",
            base_site_url="https://www.uffizi.it",
            locality="Florence, Italy",
            fetcher=_fetcher_for(_UFFIZI_ABOUT_HTML),
        )

    def test_about_built(self):
        self.assertIsNotNone(self.about)
        self.assertTrue(self.about.narration.strip())

    def test_no_ellipsis_spoken(self):
        self.assertNotIn("...", self.about.narration)
        self.assertNotIn("\u2026", self.about.narration)

    def test_no_dangling_of_spoken(self):
        self.assertNotIn("collection of.", self.about.narration)
        self.assertNotIn("on the ord", self.about.narration)

    def test_identity_survives(self):
        # The clean identity / why-it-matters sentence IS kept.
        self.assertIn("Uffizi", self.about.narration)


class TestPradoAboutNoTruncation(unittest.TestCase):
    def setUp(self):
        self.about = am.build_about_stop(
            venue_name="Museo del Prado",
            base_site_url="https://www.museodelprado.es",
            locality="Madrid, Spain",
            fetcher=_fetcher_for(_PRADO_ABOUT_HTML),
        )

    def test_no_midword_cut_spoken(self):
        self.assertIsNotNone(self.about)
        self.assertNotIn("and w.", self.about.narration)

    def test_prado_identity_survives(self):
        self.assertIn("Prado", self.about.narration)


class TestAboutAtMostThreeSentences(unittest.TestCase):
    """Defect 3: the About body is at most 3 sentences beyond the fixed opener."""

    def _body_sentence_count(self, narration):
        # The first sentence is the fixed framing opener ("Before we look at
        # anything on the walls, here is the story of …"). Count the rest.
        sents = [s for s in re.split(r"(?<=[.!?])\s+", narration.strip()) if s.strip()]
        if sents and sents[0].lower().startswith("before we look"):
            sents = sents[1:]
        return len(sents)

    def test_uffizi_about_at_most_three_body_sentences(self):
        about = am.build_about_stop(
            venue_name="Uffizi Gallery",
            base_site_url="https://www.uffizi.it",
            locality="Florence, Italy",
            fetcher=_fetcher_for(_UFFIZI_ABOUT_HTML),
        )
        self.assertIsNotNone(about)
        self.assertLessEqual(self._body_sentence_count(about.narration), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
