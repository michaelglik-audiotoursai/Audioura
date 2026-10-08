#!/usr/bin/env python3
"""test_local623_stop_body_defects.py — one test per LOCAL-623 defect.

Each test is grounded on the REAL tour 468 (Museum Folkwang, Essen) text or its
inputs — the exact sentences the critic flagged at 3/10:

  1. Same-title / wrong-artist bleed: Stop 1 (Daumier's *Ecce Homo*) also narrated
     Lovis Corinth's 1925 *Ecce Homo* (different work, different artist).
  2. Museum preamble + recurring motif: the founding/merger/Chipperfield block and
     the "museum story of preservation and renewal" refrain in the stop bodies.
  3. Garbage address: "Address: 1922 by way, Essen, Germany" (a year + preposition,
     not a street).
  4. Citation leftover in narration: "as published by the museum in October 2026".
  5. Dropped possessives: "Corot scene", "the painting celebration" (the curly-
     apostrophe orphan strip removed every possessive sentence-wide).

Pure/offline; no network, no LLM, no DB. Run:
    python3 -m pytest test_local623_stop_body_defects.py -q
"""
import unittest

import same_title_bleed_guard as stbg
import museum_motif_guard as mmg
import about_museum_stop as am
import spoken_text_hygiene as sth
import unglossed_reference_gate as urg


# ── Defect 1 — same-title / wrong-artist bleed ────────────────────────────────
class TestSameTitleBleed(unittest.TestCase):
    # The real Stop-1 tail: Daumier's Ecce Homo, then Corinth's 1925 Ecce Homo.
    STOP1 = (
        'In 1850, Honoré Daumier created the oil-on-canvas painting "Ecce Homo," '
        'a work he left unfinished. Standing before this canvas, the viewer sees '
        'the marks of Daumier’s process. '
        'Lovis Corinth painted Ecce Homo in 1925 as an oil painting on canvas. '
        'In keeping with a long-standing artistic tradition, he chose to represent '
        'himself as the figure of Christ in the composition. '
        'The work emerged from an expressionistic style that Corinth developed '
        'late in his career, combining elements of impressionism and expressionism.'
    )

    def test_corinth_bleed_dropped_daumier_kept(self):
        new_body, rep = stbg.filter_stop_body_same_title(
            self.STOP1, stop_title="Ecce homo", stop_artist="Honoré Daumier")
        self.assertTrue(rep["changed"])
        # the wrong artist and his follow-on sentences are gone
        self.assertNotIn("Corinth", new_body)
        self.assertNotIn("figure of Christ", new_body)
        # the stop's own artist and work survive
        self.assertIn("Daumier", new_body)
        self.assertIn("Ecce Homo", new_body)
        self.assertIn("Lovis Corinth", rep["bled_artists"])

    def test_no_drop_when_artist_matches(self):
        # A sentence naming the SAME title by the SAME artist is never a bleed.
        body = ('Honoré Daumier painted Ecce Homo in 1850. '
                'The unfinished surface reveals his searching brushwork.')
        new_body, rep = stbg.filter_stop_body_same_title(
            body, stop_title="Ecce homo", stop_artist="Honoré Daumier")
        self.assertFalse(rep["changed"])
        self.assertEqual(new_body, body)

    def test_tour_text_level_binds_header_title(self):
        tour = (
            "Stop 1: Ecce homo\n\n"
            + self.STOP1 + "\n\n"
            "Directions: Continue.\n\n"
        )
        new_tour, rep = stbg.filter_tour_text_same_title(
            tour, stop_titles={1: "Ecce homo"}, stop_artists={1: "Honoré Daumier"})
        self.assertNotIn("Corinth", new_tour)
        self.assertIn("Daumier", new_tour)


# ── Defect 2 — museum preamble + recurring motif ──────────────────────────────
class TestMuseumPreambleAndMotif(unittest.TestCase):
    FOLKWANG_ABOUT = [
        "Museum Folkwang is a major collection of 19th- and 20th-century art in Essen, Germany.",
        "The museum was established in 1922 by merging the Essener Kunstmuseum, "
        "which was founded in 1906, and the private Folkwang Museum.",
        "In 2010, the new building designed by David Chipperfield Architects gave "
        "the Museum Folkwang a striking appearance and large additional exhibition spaces.",
    ]
    GRIFFIN_FOUNDER = (
        "The Griffin Museum of Photography was founded in 1992 by the photographer "
        "Arthur Griffin, and is dedicated to promoting the art of photography.")

    def test_merger_and_building_dropped_identity_kept(self):
        kept = am.filter_museum_boilerplate(self.FOLKWANG_ABOUT)
        joined = " ".join(kept)
        self.assertNotIn("merging", joined)      # merger of predecessor institutions
        self.assertNotIn("Chipperfield", joined)  # the building
        self.assertNotIn("1906", joined)          # the bare founding date
        self.assertIn("major collection", joined)  # the plain identity stays

    def test_named_founder_story_is_kept(self):
        # D634: a REAL founder story (named person) may stay.
        self.assertFalse(am.is_forbidden_museum_boilerplate(self.GRIFFIN_FOUNDER))

    def test_recurring_museum_motif_dropped_from_stop_body(self):
        stop2 = (
            'Bacchus, the Roman god of wine, presides over a gathering. '
            'The museum story of preservation and renewal—of holding fast to culture '
            'in times of change—resonates with the joyous abandon of the scene. '
            'The palette is muted, with earthy ochres and gentle greens.'
        )
        new_body, rep = mmg.filter_stop_body_museum_motif(stop2)
        self.assertTrue(rep["changed"])
        self.assertNotIn("preservation and renewal", new_body)
        self.assertIn("Bacchus", new_body)        # the work content survives
        self.assertIn("muted", new_body)


# ── Defect 3 — garbage address ────────────────────────────────────────────────
class TestGarbageAddress(unittest.TestCase):
    def test_year_preposition_fragment_rejected(self):
        self.assertFalse(am.is_valid_street_address("1922 by way, Essen, Germany"))
        self.assertFalse(am.is_valid_street_address("1922 by way"))

    def test_real_addresses_accepted(self):
        for a in ("67 Shore Road, Winchester, MA 01890",
                  "164 Newbury Street, Boston, MA 02116",
                  "10½ Beacon Street"):
            self.assertTrue(am.is_valid_street_address(a), a)

    def test_extract_skips_narrative_year(self):
        # The exact Folkwang clause that produced "1922 by way".
        corpus = ("the collection he had founded in Hagen in 1902 was acquired in "
                  "1922 by way of a joint initiative by local Essen citizens.")
        self.assertEqual(am.extract_venue_address(corpus, locality="Essen, Germany"), "")

    def test_render_omits_invalid_address(self):
        from stop_pool_assembly import _render_stop_block
        stop = {"title": "Ecce homo", "address": "1922 by way, Essen, Germany",
                "narration": "Narration body."}
        block = _render_stop_block(stop, 1, "museum", None)
        self.assertNotIn("1922 by way", block)
        self.assertNotIn("Address:", block)


# ── Defect 4 — citation leftover in narration ─────────────────────────────────
class TestCitationLeftover(unittest.TestCase):
    def test_strip_published_by_museum_tail(self):
        s = ("An optional climate contribution ticket can be added for €1, "
             "as published by the museum in October 2026.")
        out, n = sth.strip_citation_tails(s)
        self.assertEqual(n, 1)
        self.assertNotIn("as published by the museum", out)
        self.assertIn("€1", out)                 # the fact itself survives

    def test_clean_spoken_text_removes_tail(self):
        s = ("Admission is free. An optional climate contribution ticket can be "
             "added for €1, as published by the museum in October 2026.")
        out, rep = sth.clean_spoken_text(s)
        self.assertGreaterEqual(rep.get("citation_tails", 0), 1)
        self.assertNotIn("as published by the museum", out)

    def test_no_false_positive_on_reception(self):
        # "praised ... as a masterpiece" is NOT a citation tail.
        s = "The work was praised by critics as a masterpiece."
        out, n = sth.strip_citation_tails(s)
        self.assertEqual(n, 0)
        self.assertEqual(out, s)


# ── Defect 5 — dropped possessives ────────────────────────────────────────────
class TestDroppedPossessives(unittest.TestCase):
    def test_curly_possessive_preserved(self):
        # The two real 468 Stop-2 fragments.
        self.assertIn("Corot\u2019s",
                      urg._clean_degrade_artifacts("depicted in Corot\u2019s scene"))
        self.assertIn("painting\u2019s",
                      urg._clean_degrade_artifacts("the painting\u2019s celebration of life"))

    def test_straight_possessive_preserved(self):
        self.assertIn("Corot's",
                      urg._clean_degrade_artifacts("depicted in Corot's scene"))

    def test_orphan_possessive_still_removed(self):
        # A dangling "'s" with no word before it IS removed (the real orphan case).
        out_s = urg._clean_degrade_artifacts("the landscape \u2019s rarely seen")
        self.assertNotIn("\u2019s", out_s)
        out_a = urg._clean_degrade_artifacts("the landscape 's rarely seen")
        self.assertNotIn("'s", out_a)


if __name__ == "__main__":
    unittest.main()
