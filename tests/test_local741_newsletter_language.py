#!/usr/bin/env python3
"""
test_local741_newsletter_language.py — [LOCAL-741]
==================================================
Michael's review A3 (2026-10-22): a listener pasted ONE English Wikipedia
article (https://en.wikipedia.org/wiki/Boston). The newsletter service

  (a) crawled 10 linked pages instead of processing the one pasted article, and
  (b) REJECTED every page as "Non-English content detected - avoiding TTS
      costs" even though the bodies were English ("Mayor–council government",
      "Northeastern United States", 95,666 chars).

Root cause of (b): is_english_content() returned False on the FIRST non-Latin
character anywhere in the text. A Wikipedia article carries an interlanguage-
link sidebar that lists the article title in dozens of languages (Chinese,
Russian, Arabic, …). One such character tripped the whole 95k-char English
article.

Root cause of (a): the linked-article crawler ran for every URL, including a
single-article page.

These tests pin the two pure helpers in newsletter_processor_service:

  - is_english_content(): English body with a non-Latin sidebar PASSES; a
    French body and a Russian body are still REJECTED (cost guard intact).
    RED on base: the Boston fixture is rejected → test fails.
  - is_single_article_page(): a single article URL (Wikipedia) is a single
    article; a newsletter/issue/index URL is not.

Pure functions only — no network, no DB.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import newsletter_processor_service as nps


# ── Fixtures ────────────────────────────────────────────────────────────────

# An English Wikipedia article BODY plus the interlanguage-link sidebar that
# lists the title in many non-Latin scripts. This is what tripped the base
# check: English prose, a handful of CJK/Cyrillic/Arabic/Hebrew characters.
_WIKI_INTERLANGUAGE_SIDEBAR = (
    "العربية  Беларуская  Български  Česky  Deutsch  Ελληνικά  Español  "
    "فارسی  עברית  日本語  한국어  Русский  中文  "
)

# ~English body kept short here but overwhelmingly English; the real article is
# 95k chars. The ratio test does not depend on length, only on proportion.
_WIKI_BOSTON_ENGLISH_BODY = (
    "Boston is the capital and most populous city of the Commonwealth of "
    "Massachusetts in the United States. The city serves as the cultural and "
    "financial center of the New England region of the Northeastern United "
    "States. Boston has a mayor-council government; the mayor is elected to a "
    "four-year term. The city proper covers about 48 square miles and had a "
    "population of over 650,000 at the most recent census, making it the most "
    "populous city in New England and the twenty-fourth most populous city in "
    "the country. "
) * 6

# The full extracted text the service builds for the main article: an English
# body followed by the non-Latin interlanguage sidebar.
BOSTON_FIXTURE = (
    "NEWSLETTER: Boston\n\nCONTENT: "
    + _WIKI_BOSTON_ENGLISH_BODY
    + _WIKI_INTERLANGUAGE_SIDEBAR
)

# A genuinely French article body (Latin script, so the non-Latin ratio is ~0;
# it must be caught by the function-word signal).
FRENCH_FIXTURE = (
    "ARTICLE: Paris\n\nCONTENT: "
    + ("Paris est la capitale de la France et la plus grande ville du pays. "
       "La ville est située sur les rives de la Seine, dans le nord du pays. "
       "Le musée du Louvre est le plus grand musée d'art du monde et reçoit des "
       "millions de visiteurs chaque année. La cathédrale Notre-Dame est un "
       "chef-d'œuvre de l'architecture gothique. ") * 6
)

# A genuinely Russian article body (Cyrillic throughout — must be rejected by
# the script-prevalence signal).
RUSSIAN_FIXTURE = (
    "ARTICLE: Москва\n\nCONTENT: "
    + ("Москва — столица России и крупнейший город страны по численности "
       "населения. Город расположен на берегах Москвы-реки в центральной части "
       "Восточно-Европейской равнины. Москва является важнейшим политическим, "
       "экономическим и культурным центром страны. ") * 6
)


# ── is_english_content ───────────────────────────────────────────────────────

class TestIsEnglishContent(unittest.TestCase):
    def test_boston_english_wikipedia_passes(self):
        # RED on base: base rejected this on the first sidebar character.
        self.assertTrue(
            nps.is_english_content(BOSTON_FIXTURE),
            "English Wikipedia article with an interlanguage-link sidebar must "
            "PASS the language check (LOCAL-741 defect)",
        )

    def test_plain_english_passes(self):
        self.assertTrue(nps.is_english_content(
            "ARTICLE: Test\n\nCONTENT: " + _WIKI_BOSTON_ENGLISH_BODY))

    def test_french_article_rejected(self):
        self.assertFalse(
            nps.is_english_content(FRENCH_FIXTURE),
            "A genuinely French article must still be rejected (cost guard).",
        )

    def test_russian_article_rejected(self):
        self.assertFalse(
            nps.is_english_content(RUSSIAN_FIXTURE),
            "A genuinely Russian article must still be rejected (cost guard).",
        )

    def test_short_content_allowed(self):
        # <50 chars: allowed through (nothing to judge).
        self.assertTrue(nps.is_english_content("Hello"))

    def test_english_with_a_few_foreign_names_passes(self):
        # An English sentence naming accented/foreign proper nouns is English.
        text = ("ARTICLE: Museums\n\nCONTENT: " + (
            "The Musée du Louvre in Paris and the Hermitage in Saint Petersburg "
            "are among the most visited museums in the world, holding works by "
            "Cézanne, Gauguin and countless others across many centuries. ") * 6)
        self.assertTrue(nps.is_english_content(text))


# ── is_single_article_page ────────────────────────────────────────────────────

class TestIsSingleArticlePage(unittest.TestCase):
    def test_wikipedia_article_is_single(self):
        self.assertTrue(
            nps.is_single_article_page("https://en.wikipedia.org/wiki/Boston"),
            "A Wikipedia article URL is a single article — do not crawl its links.",
        )

    def test_normal_story_url_is_single(self):
        self.assertTrue(nps.is_single_article_page(
            "https://www.bostonglobe.com/2026/05/01/metro/some-story/"))

    def test_mailchimp_is_newsletter(self):
        self.assertFalse(nps.is_single_article_page(
            "https://mailchi.mp/cffaa0a1186b/friday-news-123"))

    def test_email_newsletter_host_is_newsletter(self):
        self.assertFalse(nps.is_single_article_page(
            "https://view.email.bostonglobe.com/?qs=abc123"))

    def test_issue_path_is_newsletter(self):
        self.assertFalse(nps.is_single_article_page(
            "https://example.com/newsletter/issue-42"))

    def test_bare_site_root_is_index(self):
        self.assertFalse(nps.is_single_article_page("https://example.com/"))

    def test_substack_archive_is_newsletter(self):
        self.assertFalse(nps.is_single_article_page(
            "https://guyraz.substack.com/"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
