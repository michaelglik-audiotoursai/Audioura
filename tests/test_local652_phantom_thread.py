#!/usr/bin/env python3
"""test_local652_phantom_thread.py — LOCAL-652 acceptance (unit level).

The phantom-thread defect, reproduced from the live National Gallery 584 run
(Rokeby Venus / Supper at Emmaus / Hay Wain). SQ-S6b named the tour after a work
on NO delivered stop — "Vigée Le Brun's Artistic Influence and Legacy", whose
'Self Portrait in a Straw Hat' is not among the three stops — and that foreign
work/artist leaked into the Stop-2 cross-stop callback and the conclusion. The
Stop-1 opening also carried a Hay Wain (Stop 3) description because the practical-
facts placement passes misread the work's subtitle 'Landscape: Noon' as hours.

These tests CALL the fixed functions (no network, no key; the LLM is injected or
unused). The fixture is built from the delivered tour plus the logged thread
candidates. The bar (all four fixes, demonstrated):

  FIX 1 — the Vigée Le Brun thread (and the two generic 18th-century threads whose
          every supporting element is foreign) is REJECTED by the discoverer, so
          thread discovery degrades to mosaic (no thread), never a foreign one.
  FIX 2 — the Stop-2 phantom-callback sentence naming the foreign work/artist is
          REMOVED by the stop-specificity gate; the real Caravaggio sentences stay.
  FIX 3 — the conclusion names NO foreign work/artist (a foreign theme is
          discarded, a foreign LLM body rejected, a foreign sentence stripped).
  FIX 4 — a later stop's work TITLE 'Landscape: Noon' is NOT classified as a
          practical fact, so it is never relocated into the Stop-1 opening — while
          a real 'open Noon to 4 PM' still is.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import theme_thread_discoverer as ttd
import stop_specificity_gate as ssg
import tour_conclusion as tc
import practical_facts_gate as pfg


# The three delivered stops of NG 584 (title + artist), and the venue-wide story
# elements SQ-S6b extracted — all about Vigée Le Brun / Self Portrait in a Straw
# Hat / 18th-century portraiture, NONE about the three delivered works.
POI_NAMES = ["The Toilet of Venus ('The Rokeby Venus')",
             "The Supper at Emmaus",
             "The Hay Wain"]
POI_ARTISTS = ["Velázquez", "Caravaggio", "John Constable"]

FOREIGN_ELEMENTS = [
    {"id": "se_001", "text": "Vigée Le Brun painted her Self Portrait in a Straw Hat, a calculated self-presentation.", "corroboration_status": "reported"},
    {"id": "se_002", "text": "Le Brun was a prominent French portrait painter of the 18th century.", "corroboration_status": "reported"},
    {"id": "se_003", "text": "18th century portraiture emphasised public reception and exhibitions.", "corroboration_status": "reported"},
    {"id": "se_004", "text": "The straw hat motif influenced later portraitists.", "corroboration_status": "reported"},
    {"id": "se_005", "text": "Exhibitions in the 18th century shaped artistic technique.", "corroboration_status": "reported"},
    {"id": "se_006", "text": "Self portraits became a vehicle for artistic identity.", "corroboration_status": "reported"},
    {"id": "se_007", "text": "Public reception of portraits grew in the period.", "corroboration_status": "reported"},
]

# The three candidate themes the LLM named in the live run (log lines 306/312/313).
CANDIDATE_THEMES = [
    {"name": "Vigée Le Brun's Artistic Influence and Legacy",
     "description": "How Vigée Le Brun's self-presentation echoes across the works.",
     "grounded_on": ["se_001", "se_002", "se_004", "se_006"],
     "stops_covered": [1, 2, 3]},
    {"name": "18th Century Artistic Techniques and Exhibitions",
     "description": "How 18th-century portraiture technique and exhibitions connect the works.",
     "grounded_on": ["se_003", "se_005", "se_007"],
     "stops_covered": [1, 2, 3]},
    {"name": "Portraiture and Public Reception in the 18th Century",
     "description": "How portraiture's public reception connects the works.",
     "grounded_on": ["se_001", "se_005", "se_006"],
     "stops_covered": [1, 2, 3]},
]


def _elements_per_stop():
    # SQ-S6b's round-robin assignment puts the foreign elements on every stop.
    return {0: FOREIGN_ELEMENTS[:5], 1: FOREIGN_ELEMENTS[:5], 2: FOREIGN_ELEMENTS[:4]}


class TestFix1PhantomThreadRejected(unittest.TestCase):
    """FIX 1: the discoverer rejects the phantom threads."""

    def test_vigee_thread_rejected(self):
        grounding = ttd._build_delivered_grounding(POI_NAMES, POI_ARTISTS)
        scored = ttd._score_themes(CANDIDATE_THEMES, _elements_per_stop(),
                                   FOREIGN_ELEMENTS, 3, delivered_grounding=grounding)
        names = [t.name for t in scored]
        self.assertNotIn("Vigée Le Brun's Artistic Influence and Legacy", names,
                         "the Vigée Le Brun thread names a work on no delivered stop "
                         "and must be rejected")

    def test_all_foreign_threads_rejected(self):
        """All three candidates are foreign (no element names a delivered work),
        so NONE survives — the discoverer degrades to mosaic, never a foreign thread."""
        grounding = ttd._build_delivered_grounding(POI_NAMES, POI_ARTISTS)
        scored = ttd._score_themes(CANDIDATE_THEMES, _elements_per_stop(),
                                   FOREIGN_ELEMENTS, 3, delivered_grounding=grounding)
        self.assertEqual(scored, [],
                         "every candidate thread is about a foreign artist/work; "
                         "all must be rejected so discovery degrades to mosaic")

    def test_grounded_thread_survives(self):
        """A thread whose supporting elements DO name delivered works is kept —
        the fix rejects only phantom threads, never legitimate ones."""
        grounding = ttd._build_delivered_grounding(POI_NAMES, POI_ARTISTS)
        legit_elems = [
            {"id": "e1", "text": "Caravaggio used chiaroscuro in The Supper at Emmaus.", "corroboration_status": "documented"},
            {"id": "e2", "text": "Constable painted The Hay Wain from his Suffolk childhood.", "corroboration_status": "documented"},
            {"id": "e3", "text": "Velázquez explored the human form in The Toilet of Venus.", "corroboration_status": "documented"},
        ]
        eps = {0: [legit_elems[2]], 1: [legit_elems[0]], 2: [legit_elems[1]]}
        cand = [{"name": "Light and the Everyday across Three Masters",
                 "description": "How light transforms ordinary subjects.",
                 "grounded_on": ["e1", "e2", "e3"], "stops_covered": [1, 2, 3]}]
        scored = ttd._score_themes(cand, eps, legit_elems, 3, delivered_grounding=grounding)
        self.assertEqual([t.name for t in scored], ["Light and the Everyday across Three Masters"])

    def test_non_art_tour_unaffected(self):
        """With no grounding tokens (a walking/history tour, no artist metadata)
        nothing is treated as phantom — no regression for non-art tours."""
        cand = [{"name": "Freedom and Resistance",
                 "description": "A civic thread.", "grounded_on": ["e1", "e2"],
                 "stops_covered": [1, 2]}]
        elems = [{"id": "e1", "text": "A speech was given here.", "corroboration_status": "reported"},
                 {"id": "e2", "text": "A march passed through.", "corroboration_status": "reported"}]
        eps = {0: [elems[0]], 1: [elems[1]]}
        scored = ttd._score_themes(cand, eps, elems, 2, delivered_grounding=set())
        self.assertEqual([t.name for t in scored], ["Freedom and Resistance"])


class TestFix2PhantomCallbackRemoved(unittest.TestCase):
    """FIX 2: the Stop-2 phantom-callback sentence is removed."""

    def _llm(self, prompt, key, model):
        # Part-2 relationship judge: UNGROUNDED for the foreign entities.
        if "concrete relationship" in prompt or "HOW that entity relates" in prompt:
            if any(x in prompt for x in ("Vig", "Straw Hat", "Self Portrait")):
                return "VERDICT: UNGROUNDED\nREASON: no link to this stop"
            return "VERDICT: GROUNDED\nREASON: linked"
        # Part-1 substitution test: keep (SPECIFIC) so only the foreign sentence goes.
        return "VERDICT: SPECIFIC\nREASON: concrete"

    def test_stop2_foreign_callback_sentence_removed(self):
        stop2 = ("Caravaggio layered oil paint into chiaroscuro. "
                 "The legacy of this tension echoes the calculated self-presentation "
                 "you have already seen in Vigee Le Brun's Self Portrait in a Straw Hat "
                 "from your earlier stop past The Toilet of Venus. "
                 "The Supper at Emmaus stands as a record of risk and recognition.")
        poi_list = [
            {"name": POI_NAMES[0], "artist": POI_ARTISTS[0], "description": "The Toilet of Venus is by Velazquez."},
            {"name": POI_NAMES[1], "artist": POI_ARTISTS[1], "description": stop2},
            {"name": POI_NAMES[2], "artist": POI_ARTISTS[2], "description": "John Constable painted The Hay Wain in 1821."},
        ]
        stats = ssg.apply_stop_specificity_gate(poi_list, api_key="x", llm_fn=self._llm)
        self.assertGreaterEqual(stats["foreign_entity_sentences_removed"], 1)
        new_stop2 = poi_list[1]["description"]
        self.assertNotIn("Vigee Le Brun", new_stop2)
        self.assertNotIn("Straw Hat", new_stop2)
        # The real Caravaggio sentences survive.
        self.assertIn("Caravaggio layered oil paint", new_stop2)
        self.assertIn("record of risk", new_stop2)

    def test_delivered_artist_sentence_not_removed(self):
        """A sentence naming a DELIVERED artist (Constable) is never stripped,
        even if the relationship judge flags it."""
        poi_list = [{"name": "The Hay Wain", "artist": "John Constable",
                     "description": ("John Constable painted this. "
                                     "Constable was striving for recognition. "
                                     "The scene is rural.")}]
        def llm(p, k, m):
            if "concrete relationship" in p or "HOW that entity relates" in p:
                return "VERDICT: UNGROUNDED\nREASON: x"
            return "VERDICT: SPECIFIC\nREASON: y"
        stats = ssg.apply_stop_specificity_gate(poi_list, api_key="x", llm_fn=llm)
        self.assertEqual(stats["foreign_entity_sentences_removed"], 0)
        self.assertIn("Constable was striving", poi_list[0]["description"])


class TestFix3ConclusionInvariant(unittest.TestCase):
    """FIX 3: the conclusion names no foreign work/artist."""

    DELIVERED = (
        "Step-by-Step Audio Guided Tour: National Gallery - Museum Tour\n\n"
        "Stop 1: The Toilet of Venus ('The Rokeby Venus')\n\n"
        "The Toilet of Venus is by Velazquez. Venus reclines on silvery cloth.\n\n"
        "Stop 2: The Supper at Emmaus\n\n"
        "Caravaggio layered oil paint into chiaroscuro. The scene hangs suspended.\n\n"
        "Stop 3: The Hay Wain\n\n"
        "John Constable painted The Hay Wain in 1821. The farmhouse anchors the scene.\n\n"
        "Sources: This tour draws on information from www.nationalgallery.org.uk.\n"
    )

    def test_conclusion_names_no_foreign_work(self):
        # The discovered theme AND the LLM body both name Vigée Le Brun (the defect).
        def bad_llm(prompt, key):
            return ("This tour highlights Vigee Le Brun's artistic influence and legacy. "
                    "It underscores the enduring power of art.")
        out = tc.rebuild_conclusion(
            self.DELIVERED, venue_name="National Gallery",
            theme="Vigee Le Brun's Artistic Influence and Legacy",
            use_llm=True, llm_fn=bad_llm, api_key="x")
        self.assertNotIn("Vig", out, "the conclusion must name no foreign work/artist")
        # A delivered restaurant offer and the real tour text survive.
        self.assertIn("restaurant tour", out)
        self.assertIn("The Hay Wain", out)  # a delivered title may be named

    def test_foreign_entity_detector(self):
        stops = [{"title": "The Supper at Emmaus", "artist": "Caravaggio"},
                 {"title": "The Hay Wain", "artist": "John Constable"}]
        grounding = tc._delivered_conclusion_grounding(stops)
        foreign = tc._conclusion_names_foreign_entity(
            "This tour highlights Vigee Le Brun's influence.", grounding)
        self.assertTrue(any("vig" in f.lower() for f in foreign))
        clean = tc._conclusion_names_foreign_entity(
            "This tour draws together Caravaggio and Constable.", grounding)
        self.assertEqual(clean, [])


class TestFix4OpeningLeak(unittest.TestCase):
    """FIX 4: a work title 'Landscape: Noon' is not misread as hours."""

    def test_haywain_title_not_a_practical_fact(self):
        hay = ("The Hay Wain—originally titled Landscape: Noon—shows the River Stour "
               "straddling the border of Suffolk and Essex, with three horses hauling "
               "a hay wagon through the water.")
        self.assertFalse(pfg._is_practical_facts_sentence(hay),
                         "a later stop's work title must not be classified as hours")

    def test_real_hours_still_classified(self):
        self.assertTrue(pfg._is_practical_facts_sentence(
            "The museum is open daily from 10:00 to 6:00."))
        # Page-literal 'Noon to 4 PM' must still be recognised.
        self.assertTrue(pfg._is_practical_facts_sentence("Open daily, Noon to 4 PM."))

    def test_prose_noon_midnight_not_hours(self):
        self.assertFalse(pfg._is_practical_facts_sentence(
            "At noon, the painter captured the midday light."))
        self.assertFalse(pfg._is_practical_facts_sentence(
            "The scene depicts midnight revelry in the tavern."))

    def test_haywain_not_relocated_into_opening(self):
        """End-to-end: a Stop-3 Hay Wain description with 'Landscape: Noon' is NOT
        moved into the Stop-1 opening by the placement pass."""
        text = (
            "Step-by-Step Audio Guided Tour: National Gallery - Museum Tour\n\n"
            "Stop 1: The Toilet of Venus\n\n"
            "The National Gallery is an art museum in London. "
            "The museum is open daily from 10:00 to 6:00.\n\n"
            "Orientation: Stand before the work.\n\n"
            "Stop 3: The Hay Wain\n\n"
            "The Hay Wain, originally titled Landscape: Noon, shows the River Stour.\n"
        )
        out, moved = pfg.place_practical_facts_in_opening(text)
        # The Hay Wain sentence must remain in Stop 3, not move to the opening.
        self.assertIn("Landscape: Noon", out)
        head = out.split("Stop 3:")[0]
        self.assertNotIn("Landscape: Noon", head,
                         "the Hay Wain description must not leak into the Stop-1 opening")


if __name__ == "__main__":
    unittest.main(verbosity=2)
