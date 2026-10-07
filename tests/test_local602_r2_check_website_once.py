#!/usr/bin/env python3
"""test_local602_r2_check_website_once.py — LOCAL-602 r2 / D617 item 10.

Hours and admission are spoken when published; "check the website" appears at
most ONCE in the whole tour, and only when a field is truly unpublished.

On the overview path the overview narration AND the Stop-1 opening section each
carry their own website pointer, so a 1-stop overview could say "check the
website" twice. practical_facts_gate.collapse_website_pointers keeps the first and
drops later duplicates. A tour that publishes hours+admission has no pointer and
is returned unchanged.

Run: python3 -m pytest tests/test_local602_r2_check_website_once.py -q
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import practical_facts_gate as pfg


_POINTER_SCAN = re.compile(
    r'(?i)(check[^?!]*?before you (?:go|visit)'
    r'|opening hours? (?:are|were) (?:listed|not listed)'
    r'|admission prices? (?:are|were) (?:listed|not listed))')


class TestIsPointerSentence(unittest.TestCase):

    def test_pointer_sentences_detected(self):
        for s in (
            "Check opening hours and admission on wndrmuseum.com before you go.",
            "Please check wndrmuseum.com before you visit.",
            "Check wndrmuseum.com for opening hours before you go.",
            "Admission prices are listed on wndrmuseum.com.",
            "Opening hours are listed on example-museum.org.",
            "Admission prices were not listed.",
        ):
            self.assertTrue(pfg.is_website_pointer_sentence(s), s)

    def test_real_fact_sentences_not_pointers(self):
        for s in (
            "The WNDR Museum is open Tuesday through Sunday, 10 AM to 8 PM.",
            "Admission is $32 for adults and $26 for children.",
            "This immersive installation fills a room with mirrors.",
        ):
            self.assertFalse(pfg.is_website_pointer_sentence(s), s)


class TestCollapseWebsitePointers(unittest.TestCase):

    def test_two_pointers_collapse_to_one(self):
        text = (
            "Welcome to the WNDR Museum. We could not confirm the current hours, "
            "so please check wndrmuseum.com before you visit.\n\n"
            "Before you go in, a few practical notes. "
            "Check opening hours and admission on wndrmuseum.com before you go.\n")
        out, n = pfg.collapse_website_pointers(text)
        self.assertEqual(n, 1)
        self.assertEqual(len(_POINTER_SCAN.findall(out)), 1)

    def test_three_pointers_collapse_to_one(self):
        text = (
            "Please check x.org before you visit. "
            "Opening hours are listed on x.org. "
            "Check x.org for opening hours before you go.")
        out, n = pfg.collapse_website_pointers(text)
        self.assertEqual(n, 2)
        self.assertEqual(len(_POINTER_SCAN.findall(out)), 1)

    def test_single_pointer_unchanged(self):
        text = ("Before you go in, a few practical notes. "
                "Check opening hours and admission on x.org before you go.")
        out, n = pfg.collapse_website_pointers(text)
        self.assertEqual(n, 0)
        self.assertEqual(out, text)

    def test_published_facts_have_no_pointer_and_are_untouched(self):
        text = (
            "The WNDR Museum is open Tuesday through Sunday, 10 AM to 8 PM. "
            "Admission is $32 for adults and $26 for children.")
        out, n = pfg.collapse_website_pointers(text)
        self.assertEqual(n, 0)
        self.assertEqual(out, text)
        self.assertEqual(len(_POINTER_SCAN.findall(out)), 0)

    def test_real_facts_survive_the_collapse(self):
        text = (
            "The museum is open daily, 10 AM to 6 PM. "
            "Please check x.org before you visit. "
            "Admission is $12 for adults. "
            "Check x.org for opening hours before you go.")
        out, n = pfg.collapse_website_pointers(text)
        self.assertEqual(n, 1)
        self.assertIn("open daily, 10 AM to 6 PM", out)
        self.assertIn("Admission is $12 for adults", out)
        self.assertEqual(len(_POINTER_SCAN.findall(out)), 1)


if __name__ == '__main__':
    unittest.main()
