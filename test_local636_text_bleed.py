#!/usr/bin/env python3
"""test_local636_text_bleed.py — issue 1: another work's text inside a stop.

Grounded on the REAL Bench R2 tours flagged by the critic:

  * Uffizi 488 Stop 1 (*Leda col cigno*, an oil-and-resin painting on panel) had a
    SCULPTURE condition blurb bled in: "various parts of the sculpture were
    altered or added, including the head … does not originally belong to this
    body". The object-type guard's own kind must be INFERRED from the body's
    declared medium when the title ("Leda col cigno") and the material field carry
    no object noun.
  * Courtauld 485 Stop 1 (Paul Cézanne) opened with the Seurat stop's viewing
    text: "a hallmark of Seurat's pointillist method …". The same-title bleed
    guard must treat a foreign artist named POSSESSIVELY with a style/technique
    noun — while the stop's own artist is not named — as a bleed.

Pure/offline; no network, no LLM, no DB. Run:
    python3 -m pytest test_local636_text_bleed.py -q
"""
import os
import unittest

import same_title_bleed_guard as stbg


# ── Issue 1a — painting vs sculpture object-type bleed ────────────────────────
class TestObjectTypeBleedInferredFromBody(unittest.TestCase):
    # The real Leda stop: title has no object noun, medium declared in the body.
    STOP1 = (
        'Your first stop is Leda col cigno. Standing just to the right of "Leda '
        'col cigno" in the softly lit gallery, the gentle gleam of oil on panel '
        'draws your gaze to the central figures.\n\n'
        '"Leda col cigno" is an oil and resin painting on panel, measuring 130 by '
        '77.5 centimeters. The choice of oil and resin on panel allowed for soft '
        'transitions. Standing before this painting, the viewer experiences the '
        'strangeness of a divine encounter.\n\n'
        'During its lifetime, various parts of the sculpture were altered or '
        'added, including the head, which, although old, does not originally '
        'belong to this body. As a result of these changes, the piece stands as a '
        'composite of different eras. Before it became part of the Uffizi Gallery '
        'collection, "Leda col cigno" was housed in the Spiridon Collection.'
    )

    def test_body_kind_inferred_as_picture(self):
        self.assertEqual(stbg.infer_stop_kind_from_body(self.STOP1), "picture")

    def test_sculpture_sentence_dropped_when_title_and_material_empty(self):
        tour = ("Header\n\nStop 1: Leda col cigno\n\n" + self.STOP1 +
                "\n\nStop 2: Adamo ed Eva\n\nThese monumental oils on wood "
                "depict Adam and Eve.\n")
        new, rep = stbg.filter_tour_text_object_type(
            tour, stop_titles={1: "Leda col cigno", 2: "Adamo ed Eva"},
            stop_materials={1: "", 2: ""})
        self.assertTrue(rep["changed"])
        self.assertGreaterEqual(rep["dropped"], 1)
        self.assertNotIn("parts of the sculpture were altered", new)
        # the real painting content is kept
        self.assertIn("oil and resin painting on panel", new)

    def test_a_true_sculpture_stop_keeps_its_sculpture_text(self):
        # Negative: a genuine bronze stop must NOT lose its own sculpture language.
        body = ("This bronze was cast in 1880. Various parts of the sculpture "
                "were later repatinated. The figure strains against the stone.")
        tour = "H\n\nStop 1: The Thinker\n\n" + body + "\n"
        new, rep = stbg.filter_tour_text_object_type(
            tour, stop_titles={1: "The Thinker"},
            stop_materials={1: "bronze sculpture"})
        self.assertFalse(rep["changed"])
        self.assertIn("Various parts of the sculpture were later repatinated", new)

    def test_ambiguous_body_does_not_guess(self):
        # A body that only says "the painting" (decoration/activity sense) with no
        # support noun must not be force-typed, so nothing is dropped by guess.
        body = ("The painting shows a hunting scene. The painting was not chosen "
                "at random.")
        self.assertIsNone(stbg.infer_stop_kind_from_body(body))


# ── Issue 1b — possessive foreign-artist technique bleed ──────────────────────
class TestPossessiveTechniqueBleed(unittest.TestCase):
    SEURAT_IN_CEZANNE = (
        "The careful division of color, a hallmark of Seurat\u2019s pointillist "
        "method, reveals itself only at close range, where the surface vibrates "
        "with countless deliberate touches.")

    def test_seurat_method_bled_into_cezanne_stop_is_dropped(self):
        self.assertTrue(stbg.sentence_is_bleed(
            self.SEURAT_IN_CEZANNE, "Paul Cézanne", "Paul Cézanne"))

    def test_comparison_naming_own_artist_is_kept(self):
        s = ("Unlike Seurat\u2019s pointillist method, Cézanne built form with "
             "broad, deliberate planes.")
        self.assertFalse(stbg.sentence_is_bleed(s, "Paul Cézanne", "Paul Cézanne"))

    def test_own_artists_technique_in_own_stop_is_kept(self):
        s = ("The canvas is built up with Seurat\u2019s chromoluminarism "
             "technique.")
        self.assertFalse(stbg.sentence_is_bleed(s, "Georges Seurat",
                                                "Georges Seurat"))

    def test_whole_tour_drops_only_the_bleed_and_empties_no_stop(self):
        import re
        tour = open(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "fixtures", "tour_485_r2.txt")
        ).read() if _tour485_available() else None
        if tour is None:
            self.skipTest("tour_485.txt not present in this checkout")
        titles = {1: "Paul Cézanne", 2: "Georges Seurat",
                  3: "Vincent van Gogh\u2019s Self-Portrait with Bandaged Ear"}
        artists = {1: "Paul Cézanne", 2: "Georges Seurat",
                   3: "Vincent van Gogh"}
        new, rep = stbg.filter_tour_text_same_title(
            tour, stop_titles=titles, stop_artists=artists)
        self.assertTrue(rep["changed"])
        self.assertNotIn("hallmark of Seurat", new)
        for n in (1, 2, 3):
            m = re.search(rf"Stop {n}:.*?(?=\nStop {n + 1}:|$)", new, re.S)
            self.assertTrue(m and len(m.group(0).strip()) > 200)


def _tour485_available() -> bool:
    import os
    return os.path.exists(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "fixtures", "tour_485_r2.txt"))


if __name__ == "__main__":
    unittest.main()
