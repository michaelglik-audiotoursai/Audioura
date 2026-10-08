"""test_local632_junk_and_shortfall.py — [LOCAL-632] regression tests.

Covers the three fixes on the REAL candidate lists from the bench defects:
  * junk-title guard rejects the Albertina web-page titles (tour 497) and the
    task's explicit chrome set, while keeping real works;
  * the Albertina graphic-arts classes are recognised as artworks so Dürer's
    Young Hare / Praying Hands / Great Piece of Turf survive enforce_artworks_only
    even without a SPARQL creator, and 'print' is no longer a reproduction;
  * replacement-until-N refills a short museum delivery from the verified reserve
    (Rijksmuseum / Courtauld 2-of-3) and logs the mandated shortfall line only
    when the corpus genuinely cannot reach N.

Pure/offline — no network, no DB, no LLM.
"""
import unittest

from junk_title_guard import is_junk_page_title, filter_out_junk_titles
from artwork_selection_guard import (enforce_artworks_only, is_artwork_instance)
from shortfall_reconcile import reconcile_to_n, shortfall_log_line
import venue_resolver


class TestJunkTitleGuard(unittest.TestCase):
    V = "Albertina"

    def test_tour497_webpage_titles_rejected(self):
        # The two literal stops that shipped on tour 497 (Kiro 2/10).
        self.assertTrue(is_junk_page_title("The ALBERTINA Museum Vienna", self.V))
        self.assertTrue(is_junk_page_title(
            "Profile « The ALBERTINA Museum Vienna", self.V))
        self.assertTrue(is_junk_page_title(
            "ALBERTINA MODERN « The ALBERTINA Museum Vienna", self.V))

    def test_task_named_chrome_rejected(self):
        for t in ["Profile", "Home", "Visit", "Tickets",
                  "Exhibitions | Rijksmuseum", "Home - The Courtauld",
                  "Plan Your Visit", "About Us", ""]:
            self.assertTrue(is_junk_page_title(t, self.V), t)

    def test_real_works_kept(self):
        for t in ["Young Hare", "Praying Hands", "Great Piece of Turf",
                  "The Night Watch", "The Milkmaid",
                  "Apples, Bottle and Chairback", "Self-portrait at Thirteen",
                  "Footed Bowl with the Crucifixion"]:
            self.assertFalse(is_junk_page_title(t, self.V), t)

    def test_descriptive_titles_not_overrejected(self):
        # A spaced-dash joiner is chrome; a hyphen inside a word is not.
        self.assertFalse(is_junk_page_title("Marie-Antoinette", self.V))
        self.assertFalse(is_junk_page_title("A Home in the Country", self.V))
        self.assertFalse(is_junk_page_title("Vienna Woods", self.V))

    def test_filter_out_junk_titles_splits(self):
        cands = [{"name": "Profile « The ALBERTINA Museum Vienna"},
                 {"name": "Young Hare"},
                 {"name": "The ALBERTINA Museum Vienna"},
                 {"name": "Praying Hands"}]
        kept, dropped = filter_out_junk_titles(cands, self.V)
        self.assertEqual([k["name"] for k in kept], ["Young Hare", "Praying Hands"])
        self.assertEqual(len(dropped), 2)
        self.assertTrue(all(d.get("_reject_reason") == "junk_page_title"
                            for d in dropped))


class TestAlbertinaGraphicArts(unittest.TestCase):
    def test_graphic_arts_classes_are_artworks(self):
        # The Albertina P31 classes that were missing before LOCAL-632.
        for qid in ["Q18761202",  # watercolor painting (Young Hare)
                    "Q18887969",  # copper engraving print
                    "Q18218093",  # etching print
                    "Q18219090",  # woodcut print
                    "Q1396354",   # color woodcut
                    "Q23657281",  # drypoint print
                    "Q21281546",  # gouache painting
                    "Q12043905",  # pastel artwork
                    "Q2647254",   # study
                    "Q11060274"]:  # print (original medium)
            self.assertTrue(is_artwork_instance([qid]), qid)

    def test_print_is_not_a_reproduction(self):
        # 'print' (Q11060274) must no longer be treated as a reproduction, or the
        # Albertina's Dürer prints are stripped at SPARQL intake.
        self.assertNotIn("Q11060274",
                         venue_resolver._REPRODUCTION_INSTANCE_QIDS)
        self.assertFalse(venue_resolver._work_is_reproduction(
            {"label_en": "Knight, Death, and the Devil",
             "instance_of": ["Q11060274"]}))

    def test_genuine_reproductions_still_rejected(self):
        # A replica / plaster cast / text-marked copy is still dropped.
        self.assertTrue(venue_resolver._work_is_reproduction(
            {"instance_of": ["Q16919298"]}))  # plaster cast
        self.assertTrue(venue_resolver._work_is_reproduction(
            {"label_en": "The Discobolus (reproduction)", "instance_of": []}))

    def test_durer_graphic_works_survive_enforce_artworks_only(self):
        # Young Hare (watercolor), Praying Hands (drawing), a copper engraving —
        # none carry a creator in the selection dict; they must survive on class.
        works = [
            {"title": "Young Hare", "instance_of": ["Q18761202"]},
            {"title": "Praying Hands", "instance_of": ["Q2647254", "Q93184"]},
            {"title": "Knight, Death, and the Devil", "instance_of": ["Q11060274"]},
            {"title": "Saint George on Horseback", "instance_of": ["Q18887969"]},
        ]
        kept, dropped = enforce_artworks_only(
            works, venue_name="Albertina", is_art_museum=True)
        kept_titles = {k["title"] for k in kept}
        for t in ("Young Hare", "Praying Hands", "Knight, Death, and the Devil",
                  "Saint George on Horseback"):
            self.assertIn(t, kept_titles, f"{t} wrongly dropped: {dropped}")


class TestShortfallReconcile(unittest.TestCase):
    def test_rijksmuseum_2of3_refilled_from_reserve(self):
        # Delivered 2; the verified reserve holds a third famous work → fill to 3.
        selected = [{"name": "The Night Watch"}, {"name": "The Milkmaid"}]
        reserve = [{"name": "The Night Watch"}, {"name": "The Milkmaid"},
                   {"name": "The Jewish Bride"}, {"name": "Self-Portrait"}]
        final, shortfall = reconcile_to_n(selected, reserve, 3)
        self.assertEqual([c["name"] for c in final],
                         ["The Night Watch", "The Milkmaid", "The Jewish Bride"])
        self.assertEqual(shortfall, {})

    def test_no_over_delivery(self):
        final, sf = reconcile_to_n(
            [{"name": "A"}, {"name": "B"}, {"name": "C"}],
            [{"name": "A"}, {"name": "D"}], 3)
        self.assertEqual(len(final), 3)
        self.assertEqual(sf, {})

    def test_dedup_by_title(self):
        final, sf = reconcile_to_n(
            [{"name": "The Night Watch"}],
            [{"name": "the night watch"}, {"name": "The Milkmaid"}], 2)
        self.assertEqual([c["name"] for c in final],
                         ["The Night Watch", "The Milkmaid"])

    def test_honest_shortfall_when_corpus_too_small(self):
        final, sf = reconcile_to_n([{"name": "A"}], [{"name": "A"}], 3)
        self.assertEqual(len(final), 1)
        self.assertEqual(sf["requested"], 3)
        self.assertEqual(sf["delivered"], 1)
        self.assertTrue(sf["reasons"])

    def test_shortfall_log_line_format(self):
        line = shortfall_log_line(3, 2, ["r1", "r2"])
        self.assertEqual(
            line, "[LOCAL-632] shortfall: requested=3 delivered=2 reasons=[r1; r2]")


if __name__ == "__main__":
    unittest.main(verbosity=2)
