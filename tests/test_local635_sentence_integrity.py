#!/usr/bin/env python3
"""test_local635_sentence_integrity.py — LOCAL-635 sentence integrity, round 3.

One test per Bench R2 defect item, on the REAL offending sentences:

  * recall of a work never delivered   — Uffizi 488 / Marmottan 514
      (cross_stop_reference_guard: generalised recall guard;
       D638 detector ``recall_unseen_work``)
  * garbled / truncated person name     — Brera 513 ("Rea Mantegna" ← Andrea)
      (stop_editor: repair + validate_edit rejection)
  * broken sentence join                — Tate 515 ("surrounding During this time")
      (stop_editor: repair; D638 detector ``lowercase_sentence_join``)
  * empty title quotes                  — Courtauld 485 ("Yet in “ ” the domestic…")
      (stop_editor: fill with the stop title; D638 detector ``empty_title_quotes``)

Each test asserts the corresponding D638 detector regex no longer fires on the
repaired text (and, for the editor-side contract, that validate_edit rejects the
defect). Deterministic; no network.

Run: python3 -m pytest tests/test_local635_sentence_integrity.py -q
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cross_stop_reference_guard as g  # noqa: E402
import stop_editor as se  # noqa: E402


# ── D638 detector regexes (copied verbatim from .continuous_dev/bench/detectors.py)
def _recall_unseen_work_fires(spoken: str) -> bool:
    titles = re.findall(r"(?m)^Stop \d+:\s*(.+)$", spoken)
    _recall = re.findall(
        r"(?i)([^.]{0,80})\b(you may recall|you (?:have )?(?:already )?"
        r"(?:encountered|saw|seen|observed|met)(?: earlier| before| previously)?)\b",
        spoken)
    _bad = [a for a, _ in _recall
            if not any(t.split(" by ")[0].lower()[:18] in a.lower() for t in titles)]
    return bool(_bad)


def _lowercase_sentence_join_fires(spoken: str) -> bool:
    return bool(re.search(r"\b[a-z]{3,} (During|After|Before|In|The|This|When)\s+[a-z]",
                          spoken))


def _empty_title_quotes_fires(spoken: str) -> bool:
    return bool(re.search(r'"\s+"|“\s*”', spoken))


# ── Real Bench R2 sentences (verbatim from .continuous_dev/calib/critique) ──────
UFFIZI_488_STOP2 = (
    "Stop 2: Adorazione dei Magi\n\n"
    "The layers of oil paint and visible underdrawing, so distinct from the "
    "completed works you have already encountered, are most legible here. The "
    "layering of earth-toned oils and visible preparatory lines marks a radical "
    "shift from the meticulous tempera of Botticelli’s Adorazione dei Magi, "
    "which you may recall from earlier in your journey through this museum."
)
# Full delivered title set for 488 (none is a Botticelli work / "completed works").
UFFIZI_488_TEXT = (
    "Stop 1: Leda col cigno\n\nLeda stands by the swan.\n\n"
    + UFFIZI_488_STOP2 +
    "\n\nStop 3: Adamo ed Eva\n\nCranach signed the panel."
)

MARMOTTAN_514_TEXT = (
    "Stop 1: Chrysanthèmes blancs et jaunes, jardin du Petit Gennevilliers\n\n"
    "Gustave Caillebotte painted the chrysanthemums in 1893.\n\n"
    "Stop 2: BIDAULD Jean Joseph Xavier ; VERNET Carle\n\n"
    "Years later, this artwork found a new home at the Musée Marmottan Monet. "
    "In the aftermath of events such as the 1985 daylight theft you encountered "
    "at Chrysanthèmes blancs et jaunes, jardin du Petit Gennevilliers, the "
    "importance of preservation becomes sharply felt.\n\n"
    "Stop 3: Pendule « L’Amitié voilant les heures »\n\nA decorative clock."
)

BRERA_513_TEXT = (
    "Stop 1: Cristo morto nel sepolcro e tre dolenti\n\n"
    "Stand directly before \"Cristo morto nel sepolcro e tre dolenti\" by "
    "Andrea Mantegna, painted between 1470 and 1474.\n\n"
    "Rea Mantegna painted \"Cristo morto nel sepolcro e tre dolenti\" between "
    "1470 and 1474, choosing to depict the dead Christ and three mourners."
)

TATE_515_TEXT = (
    "Stop 2: The Weeping Woman\n\n"
    "In 1937, Pablo Picasso was deeply affected by the Spanish Civil War and "
    "the tragedies surrounding During this time, he created a series of oil on "
    "canvas paintings known as The Weeping Woman, with the last piece completed "
    "in late 1937."
)

COURTAULD_485_TEXT = (
    "Stop 2: Georges Seurat\n\n"
    "The result is an image that feels both intimate and remote. Yet in “ ” the "
    "domestic replaces the maritime, and the quiet act of self-decoration "
    "becomes a vessel for Seurat’s larger questions about perception and reality."
)


class TestRecallUnseenWork(unittest.TestCase):
    """Item 1: 488 + 514 — any recall must name a DELIVERED title/artist."""

    def test_488_and_514_recall_of_unseen_work_dropped(self):
        # Precondition: detector fires on both raw texts.
        self.assertTrue(_recall_unseen_work_fires(UFFIZI_488_TEXT))
        self.assertTrue(_recall_unseen_work_fires(MARMOTTAN_514_TEXT))

        cleaned_488, n488 = g.strip_unseen_callbacks_in_text(UFFIZI_488_TEXT)
        cleaned_514, n514 = g.strip_unseen_callbacks_in_text(MARMOTTAN_514_TEXT)

        self.assertGreaterEqual(n488, 1)
        self.assertGreaterEqual(n514, 1)
        # The unanchored recall clauses are gone; detector no longer fires.
        self.assertFalse(_recall_unseen_work_fires(cleaned_488))
        self.assertFalse(_recall_unseen_work_fires(cleaned_514))
        self.assertNotIn("completed works you have already encountered", cleaned_488)
        self.assertNotIn("daylight theft you encountered", cleaned_514)
        # A real callback that names a delivered title is kept (not over-dropped).
        kept = (
            "Stop 1: Las Meninas\n\nVelázquez painted the court.\n\n"
            "Stop 2: The Third of May\n\nGoya echoes Las Meninas, which you may "
            "recall from the first stop.")
        kept_clean, nk = g.strip_unseen_callbacks_in_text(kept)
        self.assertIn("Las Meninas, which you may recall", kept_clean)


class TestGarbledName(unittest.TestCase):
    """Item 2: 513 — editor rejects/repairs a name that differs from the sources."""

    def test_513_rea_mantegna_repaired_and_rejected(self):
        self.assertEqual(se.detect_garbled_name(BRERA_513_TEXT), "Rea Mantegna")
        repaired, n = se.repair_garbled_names_in_text(BRERA_513_TEXT)
        self.assertGreaterEqual(n, 1)
        self.assertNotIn("Rea Mantegna", repaired)
        self.assertIn("Andrea Mantegna", repaired)

        # validate_edit REJECTS an output whose name is a truncated variant of a
        # source name (the editor's contract).
        ok, reason = se.validate_edit(
            'Rea Mantegna painted the dead Christ and three mourners.',
            'Andrea Mantegna painted "Cristo morto" between 1470 and 1474.',
            stop_title="Cristo morto nel sepolcro e tre dolenti",
            venue_name="Pinacoteca di Brera")
        self.assertFalse(ok)
        self.assertRegex(reason, r"(garbled name|new proper noun)")


class TestBrokenJoin(unittest.TestCase):
    """Item 3: 515 — repair a lowercase→Capital broken sentence join."""

    def test_515_broken_join_repaired(self):
        self.assertTrue(_lowercase_sentence_join_fires(TATE_515_TEXT))
        self.assertIsNotNone(se.detect_broken_join(TATE_515_TEXT))

        repaired, n = se.repair_broken_joins_in_text(TATE_515_TEXT)
        self.assertGreaterEqual(n, 1)
        self.assertFalse(_lowercase_sentence_join_fires(repaired))
        self.assertIsNone(se.detect_broken_join(repaired))
        # Fact-bearing content preserved, clean sentence boundary inserted.
        self.assertIn("Spanish Civil War.", repaired)
        self.assertIn("During this time, he created", repaired)
        self.assertNotIn("surrounding During", repaired)

        # validate_edit rejects an edit that still contains the broken join.
        ok, reason = se.validate_edit(
            "A war and the tragedies surrounding During this time, he painted.",
            "A war shaped him. During this time, he painted a great work.")
        self.assertFalse(ok)
        self.assertIn("broken join", reason)


class TestEmptyTitleQuotes(unittest.TestCase):
    """Item 4: 485 — never emit empty quotes; fill with the stop title."""

    def test_485_empty_quotes_filled_with_stop_title(self):
        self.assertTrue(_empty_title_quotes_fires(COURTAULD_485_TEXT))
        self.assertTrue(se.detect_empty_title_quotes(COURTAULD_485_TEXT))

        filled, n = se.fill_empty_title_quotes_in_text(COURTAULD_485_TEXT)
        self.assertGreaterEqual(n, 1)
        self.assertFalse(_empty_title_quotes_fires(filled))
        self.assertFalse(se.detect_empty_title_quotes(filled))
        # The blank pair is filled with the stop's own title ("Georges Seurat").
        self.assertIn("Georges Seurat", filled)
        self.assertNotIn("in “ ”", filled)

        # validate_edit rejects an edit that still speaks a blank quote pair.
        ok, reason = se.validate_edit(
            'Yet in “ ” the domestic replaces the maritime scene entirely here.',
            'The domestic replaces the maritime scene entirely in this work here.')
        self.assertFalse(ok)
        self.assertIn("empty title quotes", reason)


if __name__ == "__main__":
    unittest.main()
