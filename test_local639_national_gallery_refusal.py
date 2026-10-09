#!/usr/bin/env python3
"""test_local639_national_gallery_refusal.py — LOCAL-639 defect 2.

The live National Gallery tour (job a81b18e8…, R8) was REFUSED with
"We couldn't verify enough facts about National Gallery to narrate it safely"
even though it is one of the world's best-documented museums (389 verified works,
venue_resolver resolved it to Q180788 cleanly). The generator log of the refusing
QA round shows the real cause — a LOST NEWLINE after the Stop 2 header:

    FAIL: D3(a) Stop-title sanity — "'Stop 2: The Toilet of Venus ('The Rokeby
          Venus') Address: Tr...' (320 words — too long)"
    FAIL: D3(d) Grounding assertion — 1 suspicious title: "The Toilet of Venus
          ('The Rokeby Venus') Address: "

The newline after "Stop 2:" was dropped, so the header ran into its own
Address/Orientation body. D3(a)/D3(d) measured the WHOLE run-on line as the
"title" (320 words), and D3(d) — a FACTUAL check — refused the entire tour on a
cosmetic formatting defect. (The same tour delivered fine on a later round, which
is why id 495 ships 3 clean stops — the refusal was random/round-dependent.)

Fix (this test is the contract):
  1. ``_stop_title_from_header`` measures the TRUE title by cutting a run-on
     header at its first embedded field label — the 320-word artifact collapses
     to the real 7-word title.
  2. A run-on header no longer makes D3(a)/D3(d) fail; FACTUAL_FAIL_COUNT stays 0.
  3. A genuinely long title (a sentence masquerading as an entity, NO field
     label) is STILL caught — the fix narrows the artifact, it does not disable
     the check.

Pure/offline; no network, no LLM, no DB. Run:
    python3 -m pytest test_local639_national_gallery_refusal.py -q
"""
import io
import contextlib
import os
import unittest

import content_qa_runner as cq


def _run_qa_counts(text):
    """Run run_qa capturing stdout; return (factual_fail, fail_count)."""
    cq._J.PASS_COUNT = 0
    cq._J.FAIL_COUNT = 0
    cq._J.FACTUAL_FAIL_COUNT = 0
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cq.run_qa(text)
    return cq._J.FACTUAL_FAIL_COUNT, cq._J.FAIL_COUNT, buf.getvalue()


def _distinct_body(seed, n=210):
    return " ".join(f"{seed}{i}" for i in range(n)) + "."


class TestTitleExtractor(unittest.TestCase):
    def test_run_on_header_cut_at_field_label(self):
        header = ("Stop 2: The Toilet of Venus ('The Rokeby Venus') Address: "
                  "Trafalgar Square, London WC2N 5DN Orientation: As you stand a "
                  "few paces back, the cool gleam of oil paint draws your eye.")
        title = cq._stop_title_from_header(header)
        self.assertEqual(title, "The Toilet of Venus ('The Rokeby Venus')")
        self.assertLessEqual(len(title.split()), 15)

    def test_clean_header_unchanged(self):
        self.assertEqual(cq._stop_title_from_header("Stop 1: The Supper at Emmaus"),
                         "The Supper at Emmaus")

    def test_decoration_still_stripped(self):
        self.assertEqual(cq._stop_title_from_header("Stop 3: The Hay Wain, 1821"),
                         "The Hay Wain")

    def test_genuinely_long_title_not_cut(self):
        # No embedded field label → measured in full (still caught downstream).
        long_title = ("Stop 1: " + " ".join(f"word{i}" for i in range(20)))
        extracted = cq._stop_title_from_header(long_title)
        self.assertGreater(len(extracted.split()), 15)


class TestRunOnHeaderNoLongerRefuses(unittest.TestCase):
    """The real 495 round-1 artifact must NOT produce a FACTUAL failure."""

    def _tour(self):
        return (
            "Step-by-step audio guided tour of The National Gallery, London - Museum Tour\n"
            "Tour-Category: museum\n\n"
            "Stop 1: The Supper at Emmaus\n\nCoordinates: 51.508, -0.128\n\n"
            + _distinct_body("alpha") + "\n\n"
            "Stop 2: The Toilet of Venus ('The Rokeby Venus') Address: "
            "Trafalgar Square, London WC2N 5DN Orientation: Stand back and look. "
            + _distinct_body("beta") + "\n\n"
            "Stop 3: The Hay Wain\n\nCoordinates: 51.508, -0.128\n\n"
            + _distinct_body("gamma") + "\n\n"
            "That's 3 stops in all.\n"
        )

    def test_no_factual_failure(self):
        factual, _fail, out = _run_qa_counts(self._tour())
        self.assertEqual(factual, 0,
                         f"run-on header artifact must not fail-closed; log:\n{out}")

    def test_d3a_and_d3d_pass(self):
        _factual, _fail, out = _run_qa_counts(self._tour())
        self.assertIn("PASS: D3(a) Stop-title sanity", out)
        self.assertIn("PASS: D3(d) Grounding assertion", out)


class TestGenuineBadTitleStillCaught(unittest.TestCase):
    """A real sentence-as-title (NO field label) must still fail D3(a)/D3(d)."""

    def _tour(self):
        sentence_title = " ".join(f"word{i}" for i in range(20))
        return (
            "Step-by-step audio guided tour of A Museum - Museum Tour\n"
            "Tour-Category: museum\n\n"
            f"Stop 1: {sentence_title}\n\nCoordinates: 51.508, -0.128\n\n"
            + _distinct_body("alpha") + "\n\n"
            "Stop 2: The Hay Wain\n\nCoordinates: 51.508, -0.128\n\n"
            + _distinct_body("beta") + "\n\n"
            "That's 2 stops in all.\n"
        )

    def test_sentence_title_still_fails_factual(self):
        factual, _fail, out = _run_qa_counts(self._tour())
        self.assertGreaterEqual(factual, 1,
                                f"a 20-word sentence-title must still fail; log:\n{out}")


class TestServiceCorrectiveHelpers(unittest.TestCase):
    def setUp(self):
        import generate_tour_text_service as svc
        self.svc = svc

    def test_detects_run_on_defect(self):
        glued = ("Stop 1: Work One\n\nNarr.\n\n"
                 "Stop 2: Work Two Address: 1 Main St Orientation: Stand.\n\n")
        self.assertTrue(self.svc._header_formatting_defect(glued))

    def test_splitter_restores_newline_idempotent(self):
        glued = ("Stop 2: The Toilet of Venus ('The Rokeby Venus') Address: "
                 "Trafalgar Square Orientation: Stand back.\n\n")
        fixed = self.svc._split_run_on_stop_headers(glued)
        self.assertIn("Stop 2: The Toilet of Venus ('The Rokeby Venus')\n", fixed)
        self.assertEqual(self.svc._split_run_on_stop_headers(fixed), fixed)

    def test_clean_text_no_defect(self):
        clean = ("Stop 1: Work One\n\nAddress: 1 Main St\n\nNarr.\n\n"
                 "Stop 2: Work Two\n\nNarr two.\n\n")
        self.assertFalse(self.svc._header_formatting_defect(clean))
        self.assertEqual(self.svc._split_run_on_stop_headers(clean), clean)


if __name__ == "__main__":
    unittest.main(verbosity=2)
