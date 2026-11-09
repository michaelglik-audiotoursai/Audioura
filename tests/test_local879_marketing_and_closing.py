#!/usr/bin/env python3
"""test_local879_marketing_and_closing.py — LOCAL-879 §6.

Two tour-547 defects:

  (a) PROMOTIONAL / SUPERLATIVE copy repeated as narration, unattributed:
        Book Street — "a diamond-valued location … a distinctive cultural brand
                       of the city", "the Notting Hill of Ho Chi Minh"
        Thi Bar     — "one of the only real gay bars"
      spoken_text_hygiene.strip_promotional_sentences drops these sentences; the
      873C fact extractor (thin_stop_delivery.fact_sentences) drops a promo fact
      before it reaches the narrator.

  (b) EMPTY CLOSING: "one thread runs through: the places you chose on this
      route." — a circular thread. tour_conclusion drops the empty "one thread"
      sentence (keeping the substantive meaning sentence); a real city thread is
      kept.

Run: python3 -m pytest tests/test_local879_marketing_and_closing.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import spoken_text_hygiene as sth
import thin_stop_delivery as tsd
import tour_conclusion as tc


class TestPromotionalScrub(unittest.TestCase):

    def test_book_street_promo_dropped(self):
        txt = ("You are standing on Book Street, 100 meters long. It opened on "
               "January 9, 2016. Book Street is also known as the Notting Hill "
               "of Ho Chi Minh. This place is a diamond-valued location on "
               "Nguyen Van Binh Street and a distinctive cultural brand of the "
               "city. You can feel the peace here.")
        out, n = sth.strip_promotional_sentences(txt)
        self.assertGreaterEqual(n, 2)
        self.assertNotIn("Notting Hill", out)
        self.assertNotIn("diamond-valued", out)
        self.assertNotIn("cultural brand", out)
        self.assertIn("January 9, 2016", out)  # the real fact survives

    def test_thi_bar_only_real_dropped(self):
        txt = ("You are standing outside Thi Bar, open since 2010. This small "
               "but vibrant venue is one of the only real gay bars in the city.")
        out, n = sth.strip_promotional_sentences(txt)
        self.assertEqual(n, 1)
        self.assertNotIn("one of the only", out)
        self.assertIn("2010", out)

    def test_clean_spoken_text_runs_the_promo_scrub(self):
        txt = ("It opened in 2016. This place is a diamond-valued location.")
        out, rep = sth.clean_spoken_text(txt)
        self.assertNotIn("diamond-valued", out)
        self.assertEqual(rep.get("promotional"), 1)

    def test_fact_extractor_drops_promo_fact(self):
        facts = [
            {"text": "Book Street opened on January 9, 2016."},
            {"text": "Book Street is the Notting Hill of Ho Chi Minh City."},
            {"text": "It is a diamond-valued location and a cultural brand of the city."},
        ]
        out = tsd.fact_sentences(facts, require_specific=False, title="Book Street")
        joined = " ".join(out)
        self.assertNotIn("Notting Hill", joined)
        self.assertNotIn("diamond-valued", joined)
        self.assertTrue(any("2016" in s for s in out))

    def test_ordinary_prose_untouched(self):
        txt = ("The cathedral was completed in 1880. Its twin bell towers rise "
               "58 meters high.")
        out, n = sth.strip_promotional_sentences(txt)
        self.assertEqual(n, 0)
        self.assertEqual(out, txt)


class TestEmptyClosing(unittest.TestCase):

    def _body(self, thread_phrase, user_stops=True, subject="", period=""):
        common = {"thread_phrase": thread_phrase,
                  "meaning": ("Each was picked by you, and together they trace "
                              "your own route through the city."),
                  "subject_phrase": subject, "period_label": period}
        return tc._template_thematic_body(
            [{"title": "Thi Bar", "narration": "x"}],
            thread_phrase=thread_phrase, theme="", common=common,
            titles=["Thi Bar"], n=1, user_stops=user_stops)

    def test_circular_thread_sentence_dropped(self):
        out = self._body("the places you chose on this route")
        self.assertNotIn("one thread runs through: the places you chose on this route",
                         out)
        self.assertNotIn("one thread runs through", out)
        # [LOCAL-880 §6] the orphan "Each was picked by you … trace your own route"
        # meaning is replaced by a clean close naming the route (here one title ->
        # the one-line close). Never the bare orphan fragment.
        self.assertNotIn("Each was picked by you", out)
        self.assertIn("route is the one you chose through the city", out)

    def test_real_city_thread_kept(self):
        out = self._body("the places you chose across Ho Chi Minh City")
        self.assertIn("Ho Chi Minh City", out)
        self.assertIn("one thread runs through", out)

    def test_real_subject_thread_kept(self):
        out = self._body("French colonial Saigon", user_stops=False,
                         subject="French colonial Saigon")
        self.assertIn("French colonial Saigon", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
