#!/usr/bin/env python3
"""test_local602_r2_about_describes_museum.py — LOCAL-602 r2 / D617 item 11.

The About text must describe the MUSEUM, not its founder. WNDR's About page is
the Bradley Keywell biography — "Bradley Keywell is a serial entrepreneur and
co-founder of Groupon …" — and every such sentence carries a story verb
("founded"), so the old _is_story_sentence lifted it as the museum's story.

These tests pin about_museum_stop:
  * _subject_is_person / _states_museum_identity classify sentences correctly;
  * _is_story_sentence REJECTS founder-biography sentences;
  * _is_story_sentence KEEPS institutional identity sentences (even when a founder
    is named inside them);
  * _collect_story_sentences on a WNDR-style About page yields museum sentences,
    never the founder biography.

Run: python3 -m pytest tests/test_local602_r2_about_describes_museum.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import about_museum_stop as am


_VENUE = "WNDR Museum"
_VENUE_FIRST = "WNDR"


class TestSubjectClassification(unittest.TestCase):

    def test_person_subject_detected(self):
        for s in (
            "Bradley Keywell is a serial entrepreneur and co-founder of Groupon.",
            "Keywell grew up in Michigan and earned his degree there.",
            "Mr. Keywell studied law before founding several companies.",
        ):
            self.assertTrue(am._subject_is_person(s, _VENUE_FIRST), s)

    def test_museum_subject_not_a_person(self):
        for s in (
            "WNDR Museum is an immersive art experience in Boston.",
            "The WNDR Museum was founded in 2018 as a permanent experience.",
            "Founded in 2018, WNDR Museum blends art and technology.",
        ):
            self.assertFalse(am._subject_is_person(s, _VENUE_FIRST), s)

    def test_states_museum_identity(self):
        self.assertTrue(am._states_museum_identity(
            "WNDR Museum is an immersive art and technology museum.", _VENUE_FIRST))
        self.assertFalse(am._states_museum_identity(
            "Bradley Keywell is a serial entrepreneur.", _VENUE_FIRST))


class TestIsStorySentence(unittest.TestCase):

    def test_founder_biography_rejected(self):
        for s in (
            "Bradley Keywell is a serial entrepreneur and the co-founder of Groupon and Lightbank.",
            "Keywell grew up in Michigan and earned his degree from the University of Michigan.",
            "He founded his first company while still a student and never looked back.",
        ):
            self.assertFalse(am._is_story_sentence(s, _VENUE, _VENUE_FIRST),
                             f"founder bio should be rejected: {s}")

    def test_museum_identity_kept(self):
        for s in (
            "WNDR Museum is an immersive art and technology experience founded in 2018.",
            "Founded in 2018, WNDR Museum blends art, science, and technology in an immersive space.",
            "The WNDR Museum was founded in 2018 as a permanent immersive art experience.",
        ):
            self.assertTrue(am._is_story_sentence(s, _VENUE, _VENUE_FIRST),
                            f"museum identity should be kept: {s}")

    def test_museum_sentence_naming_founder_is_kept(self):
        # Names the founder but states the MUSEUM'S identity → kept.
        s = ("WNDR Museum was co-founded by Bradley Keywell, a Chicago entrepreneur, "
             "as an immersive art experience.")
        self.assertTrue(am._is_story_sentence(s, _VENUE, _VENUE_FIRST))


# A WNDR-style About page: dominated by the founder biography, with two genuine
# museum-identity sentences mixed in.
_WNDR_ABOUT = (
    "<html><body>"
    "<h1>About WNDR Museum</h1>"
    "<p>Bradley Keywell is a serial entrepreneur and the co-founder of Groupon "
    "and Lightbank.</p>"
    "<p>Keywell grew up in Michigan and earned his degree from the University of "
    "Michigan, where he studied business and law.</p>"
    "<p>WNDR Museum is an immersive art and technology experience that opened its "
    "first permanent location in Chicago in 2018.</p>"
    "<p>He has long believed in the power of wonder to connect people.</p>"
    "<p>Founded in 2018, WNDR Museum blends art, science, and technology across a "
    "series of interactive installations.</p>"
    "</body></html>"
)


class TestCollectStorySentences(unittest.TestCase):

    def test_wndr_about_yields_museum_sentences_not_founder_bio(self):
        text = am._visible_text(_WNDR_ABOUT)
        picked = am._collect_story_sentences(text, _VENUE, limit=6)
        joined = " ".join(picked)
        # The museum sentences are present.
        self.assertTrue(any("immersive art and technology experience" in p
                            for p in picked),
                        f"expected a museum-identity sentence; got {picked}")
        # The founder biography is NOT lifted.
        self.assertNotIn("serial entrepreneur", joined)
        self.assertNotIn("grew up in Michigan", joined)
        self.assertNotIn("power of wonder", joined)


if __name__ == '__main__':
    unittest.main()
