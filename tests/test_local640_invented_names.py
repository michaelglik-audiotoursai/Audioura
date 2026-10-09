#!/usr/bin/env python3
"""test_local640_invented_names.py — LOCAL-640 invented names, Bench R8.

Two defect classes, on the REAL offending sentences:

  * a composer who does not exist — Pinakothek der Moderne 533:
      "composer Losonczy created a musical piece of the same name … inspired
       directly by Klee's painting"
    A person named by a single surname in a role construction, present in NONE
    of the stop's sources, must be removed with its sentence.
    (prose_entity_grounding_gate: detect/strip_fabricated_single_names;
     stop_editor: fabricated-name body guard in edit_stop)

  * a comparison to a work NOT delivered — Ny Carlsberg Glyptotek 532:
      "…echoes the way Gauguin, in the 'Græshopperne og myrerne', …"
    A comparison that NAMES an undelivered work is dropped; a comparison to a
    DELIVERED stop stays (D636). Courtauld 485 "It echoes the social facades…"
    names no work and is left to other guards.
    (cross_stop_reference_guard: strip_unseen_comparisons[_in_text];
     D638 detector recall_unseen_work for the recall shape it still covers)

Each test asserts the real sentence is removed and a legitimate neighbour /
delivered comparison is kept (no over-drop). Deterministic; no network.

Run: python3 -m pytest tests/test_local640_invented_names.py -q
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import prose_entity_grounding_gate as peg  # noqa: E402
import cross_stop_reference_guard as g  # noqa: E402
import stop_editor as se  # noqa: E402


# ── Real Bench R8 sentences (verbatim) ───────────────────────────────────────
PINAKOTHEK_533_BODY = (
    "Before you hangs Paul Klee's painting, a small panel of layered colour. "
    "The composer Losonczy created a musical piece of the same name, inspired "
    "directly by Klee's painting. The surface shimmers under the gallery light."
)
# The stop's external sources (snippets / corpus) name Klee, never a Losonczy.
PINAKOTHEK_533_SOURCES = [
    "Paul Klee (1879–1940) was a Swiss-born German painter associated with the "
    "Bauhaus. This panel is held at the Pinakothek der Moderne in Munich.",
]

NY_CARLSBERG_532_TEXT = (
    "Stop 1: The Dying Gaul\n\n"
    "A marble figure reclines, caught at the moment of death.\n\n"
    "Stop 2: Portrait of a Woman\n\n"
    "The composition echoes the way Gauguin, in the 'Græshopperne og myrerne', "
    "framed his figures against flat planes of colour. The marble glows softly "
    "under the skylight."
)

# A comparison to a DELIVERED stop — must be KEPT (D636).
DELIVERED_COMPARISON_TEXT = (
    "Stop 1: The Third of May\n\n"
    "Goya painted the execution by lamplight.\n\n"
    "Stop 2: Guernica\n\n"
    "This mural echoes The Third of May, Goya's earlier cry against slaughter."
)

# Courtauld 485 — a comparison naming NO concrete work; this guard must not drop.
COURTAULD_485_TEXT = (
    "Stop 1: A Bar at the Folies-Bergère\n\n"
    "Manet painted the barmaid before a mirror.\n\n"
    "Stop 2: Georges Seurat\n\n"
    "It echoes the social facades of modern Parisian life."
)


# ── D638 detector (copied verbatim from the LOCAL-635 test / detectors.py) ────
def _recall_unseen_work_fires(spoken: str) -> bool:
    titles = re.findall(r"(?m)^Stop \d+:\s*(.+)$", spoken)
    _recall = re.findall(
        r"(?i)([^.]{0,80})\b(you may recall|you (?:have )?(?:already )?"
        r"(?:encountered|saw|seen|observed|met)(?: earlier| before| previously)?)\b",
        spoken)
    _bad = [a for a, _ in _recall
            if not any(t.split(" by ")[0].lower()[:18] in a.lower() for t in titles)]
    return bool(_bad)


class TestFabricatedComposer(unittest.TestCase):
    """Pinakothek 533 — a single-surname creator in no source is removed."""

    def test_losonczy_detected_against_sources(self):
        det = peg.detect_fabricated_single_name(
            PINAKOTHEK_533_BODY, PINAKOTHEK_533_SOURCES)
        self.assertTrue(any(s == "Losonczy" for s, _ in det),
                        f"Losonczy not detected: {det}")

    def test_losonczy_sentence_dropped_klee_kept(self):
        cleaned, dropped = peg.strip_fabricated_single_names(
            PINAKOTHEK_533_BODY, PINAKOTHEK_533_SOURCES)
        self.assertGreaterEqual(len(dropped), 1)
        self.assertNotIn("Losonczy", cleaned)
        # Klee is grounded in the sources — the surrounding Klee sentences stay.
        self.assertIn("Klee", cleaned)
        self.assertIn("shimmers under the gallery light", cleaned)

    def test_empty_corpus_never_drops(self):
        # No evidence → cannot check → never drop (grounding chain's posture).
        cleaned, dropped = peg.strip_fabricated_single_names(
            PINAKOTHEK_533_BODY, [])
        self.assertEqual(dropped, [])
        self.assertEqual(cleaned, PINAKOTHEK_533_BODY)

    def test_grounded_single_name_kept(self):
        body = "The composer Beethoven wrote the piece in 1808."
        src = ["Ludwig van Beethoven composed the Fifth Symphony in 1808."]
        cleaned, dropped = peg.strip_fabricated_single_names(body, src)
        self.assertEqual(dropped, [])
        self.assertIn("Beethoven", cleaned)

    def test_multiword_name_left_to_other_gate(self):
        # A full "Franz Losonczy" is a multi-word name — not this guard's job.
        body = "The composer Franz Losonczy created a piece."
        cleaned, dropped = peg.strip_fabricated_single_names(
            body, PINAKOTHEK_533_SOURCES)
        self.assertEqual(dropped, [])

    def test_authorship_verb_subject_detected(self):
        body = "Losonczy composed a symphony for the exhibition."
        det = peg.detect_fabricated_single_name(body, PINAKOTHEK_533_SOURCES)
        self.assertTrue(any(s == "Losonczy" for s, _ in det), det)

    def test_stop_editor_strips_fabricated_name_on_rejected_edit(self):
        # The editor's LLM is stubbed to return garbage (rejected). The stop
        # block that ships must still have the fabricated composer removed.
        stop_block = (
            "Stop 2: Paul Klee Panel\n\n"
            + PINAKOTHEK_533_BODY
        )
        # llm_fn returns None → treated as empty/rejected; the cleaned fallback
        # (fabrication removed) must ship.
        new_block, edited, reason = se.edit_stop(
            stop_block, stop_number=2, venue_name="Pinakothek der Moderne",
            passages=PINAKOTHEK_533_SOURCES, llm_fn=lambda p, k: None)
        self.assertNotIn("Losonczy", new_block)
        self.assertIn("Klee", new_block)


class TestUnseenComparison(unittest.TestCase):
    """Ny Carlsberg 532 — comparison to an undelivered work is removed; a
    comparison to a delivered stop stays (D636)."""

    def test_gauguin_comparison_dropped(self):
        cleaned, n = g.strip_unseen_comparisons_in_text(NY_CARLSBERG_532_TEXT)
        self.assertGreaterEqual(n, 1)
        self.assertNotIn("Græshopperne", cleaned)
        self.assertNotIn("echoes the way Gauguin", cleaned)
        # The neighbouring, non-comparison sentence survives.
        self.assertIn("marble glows softly under the skylight", cleaned)

    def test_delivered_comparison_kept(self):
        cleaned, n = g.strip_unseen_comparisons_in_text(DELIVERED_COMPARISON_TEXT)
        self.assertEqual(n, 0)
        self.assertIn("echoes The Third of May", cleaned)

    def test_vague_echo_not_dropped_by_this_guard(self):
        # No concrete work named — this guard leaves it (nothing to falsify).
        cleaned, n = g.strip_unseen_comparisons_in_text(COURTAULD_485_TEXT)
        self.assertEqual(n, 0)
        self.assertIn("social facades of modern Parisian life", cleaned)

    def test_units_path_matches_text_path(self):
        units = [
            {"title": "The Dying Gaul", "narration": "A marble figure reclines."},
            {"title": "Portrait of a Woman",
             "narration": ("The composition echoes the way Gauguin, in the "
                           "'Græshopperne og myrerne', framed his figures. "
                           "The marble glows softly.")},
        ]
        new_units, dropped = g.strip_unseen_comparisons(units)
        self.assertGreaterEqual(len(dropped), 1)
        self.assertNotIn("Græshopperne", new_units[1]["narration"])
        self.assertIn("marble glows softly", new_units[1]["narration"])


class TestNoRegressionOnRecallGuard(unittest.TestCase):
    """The existing LOCAL-634/635 recall callback guard still works — my
    additions do not disturb the recall path."""

    def test_unseen_callback_still_dropped(self):
        # A "you have already seen" callback to an undelivered artist is still
        # removed by the existing guard (unchanged behaviour).
        text = (
            "Stop 1: Las Meninas\n\nVelázquez painted the court.\n\n"
            "Stop 2: The Third of May\n\n"
            "Picasso and Braque, whose works you have already seen, pushed the "
            "same frontier.")
        cleaned, n = g.strip_unseen_callbacks_in_text(text)
        self.assertGreaterEqual(n, 1)
        self.assertNotIn("whose works you have already seen", cleaned)

    def test_delivered_recall_still_kept(self):
        kept = (
            "Stop 1: Las Meninas\n\nVelázquez painted the court.\n\n"
            "Stop 2: The Third of May\n\nGoya echoes Las Meninas, which you may "
            "recall from the first stop.")
        cleaned, n = g.strip_unseen_callbacks_in_text(kept)
        self.assertIn("Las Meninas, which you may recall", cleaned)


if __name__ == "__main__":
    unittest.main()
