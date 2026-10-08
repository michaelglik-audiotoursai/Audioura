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


class TestRestoreLostStopHeaders(unittest.TestCase):
    """The Rijksmuseum tour-504 symptom: a narrated stop whose 'Stop 3:' header a
    late narration transform deleted, leaving the body spliced onto Stop 2."""

    def test_restores_milkmaid_header(self):
        from generate_tour_text import restore_lost_stop_headers
        tour = (
            "Stop 1: The Merry Drinker\n\nBody one.\n\n"
            "Directions: Continue through Rijksmuseum — next is De grote golf bij Kanagawa.\n\n"
            "Stop 2: De grote golf bij Kanagawa\n\nBody two.\n\n"
            "Directions: Your final stop in Rijksmuseum: The Milkmaid.\n\n"
            "This positioning reveals the delicate interplay of light.\n\n"
            "Body three about Vermeer and the milkmaid.\n\n"
            "That's 2 stops in all.\n")
        rendered = ["Stop 1: The Merry Drinker",
                    "Stop 2: De grote golf bij Kanagawa",
                    "Stop 3: The Milkmaid"]
        repaired, restored = restore_lost_stop_headers(tour, rendered)
        self.assertEqual(restored, ["Stop 3: The Milkmaid"])
        self.assertIn("\n\nStop 3: The Milkmaid\n\n", repaired)
        # Header lands between the directions announcement and the orphaned body.
        self.assertLess(
            repaired.index("final stop in Rijksmuseum: The Milkmaid"),
            repaired.index("Stop 3: The Milkmaid"))
        self.assertLess(
            repaired.index("Stop 3: The Milkmaid"),
            repaired.index("This positioning reveals"))

    def test_present_headers_untouched(self):
        from generate_tour_text import restore_lost_stop_headers
        tour = ("Stop 1: A\n\nx\n\nDirections: next is B.\n\nStop 2: B\n\ny\n")
        repaired, restored = restore_lost_stop_headers(tour, ["Stop 1: A", "Stop 2: B"])
        self.assertEqual(restored, [])
        self.assertEqual(repaired, tour)

    def test_no_anchor_no_insertion(self):
        # A lost header with no announcing directions line is left alone (never
        # invent a header with no body to attach to).
        from generate_tour_text import restore_lost_stop_headers
        tour = "Stop 1: A\n\nx\n"
        repaired, restored = restore_lost_stop_headers(tour, ["Stop 1: A", "Stop 2: Ghost"])
        self.assertEqual(restored, [])
        self.assertEqual(repaired, tour)


class TestCollectionMembershipP195(unittest.TestCase):
    """[LEAD item 6] A work belongs to a venue by its COLLECTION (P195), not a
    hard-coded list. Uses the real Wikidata QIDs: Tate = Q430682, KHM = Q95569,
    National Gallery London = Q180788, Belvedere = Q303139."""

    def test_ophelia_rejected_from_national_gallery_by_p195(self):
        from artwork_selection_guard import enforce_collection_membership
        # Ophelia (Millais) P195 = Tate (Q430682); a P276 location row leaked it
        # into the National Gallery (Q180788) SPARQL set.
        works = [
            {"title": "Ophelia", "collection_qids": ["Q430682"],
             "instance_of": ["Q3305213"]},
            {"title": "Sunflowers", "collection_qids": ["Q180788"],
             "instance_of": ["Q3305213"]},
        ]
        kept, dropped = enforce_collection_membership(
            works, sparql_works=works, venue_name="National Gallery",
            venue_qid="Q180788")
        self.assertEqual([k["title"] for k in kept], ["Sunflowers"])
        self.assertEqual(len(dropped), 1)
        self.assertIn("wrong_collection", dropped[0]["_reject_reason"])

    def test_madonna_del_prato_rejected_from_belvedere_by_p195(self):
        from artwork_selection_guard import enforce_collection_membership
        # Madonna del Prato (Raphael) P195 = Kunsthistorisches Museum (Q95569).
        works = [{"title": "Madonna del Prato", "collection_qids": ["Q95569"]}]
        kept, dropped = enforce_collection_membership(
            works, sparql_works=works, venue_name="Belvedere",
            venue_qid="Q303139")
        self.assertEqual(kept, [])
        self.assertIn("wrong_collection", dropped[0]["_reject_reason"])

    def test_p195_matches_venue_kept(self):
        from artwork_selection_guard import enforce_collection_membership
        works = [{"title": "The Night Watch", "collection_qids": ["Q190804"]}]
        kept, dropped = enforce_collection_membership(
            works, sparql_works=works, venue_name="Rijksmuseum",
            venue_qid="Q190804")
        self.assertEqual([k["title"] for k in kept], ["The Night Watch"])
        self.assertEqual(dropped, [])

    def test_parent_org_collection_accepted(self):
        from artwork_selection_guard import enforce_collection_membership
        # A work whose P195 is the parent organisation of the venue is kept.
        works = [{"title": "W", "collection_qids": ["Q999"]}]
        kept, _ = enforce_collection_membership(
            works, sparql_works=works, venue_name="Branch",
            venue_qid="Q1000", parent_qids=["Q999"])
        self.assertEqual([k["title"] for k in kept], ["W"])

    def test_no_p195_not_decided_by_collection_rule(self):
        from artwork_selection_guard import enforce_collection_membership
        # No P195 → the P195 rule is a no-op; title-set membership governs (it's in
        # the sparql set here, so kept).
        works = [{"title": "Untitled Drawing"}]
        kept, dropped = enforce_collection_membership(
            works, sparql_works=works, venue_name="Albertina",
            venue_qid="Q371908")
        self.assertEqual([k["title"] for k in kept], ["Untitled Drawing"])

    def test_known_work_home_is_only_a_fixture(self):
        # The hard-coded map remains importable as a fixture but is no longer the
        # primary mechanism (the P195 rule above is).
        import artwork_selection_guard as g
        self.assertIn("ophelia", g._KNOWN_WORK_HOME)


class TestTourismBoardChrome(unittest.TestCase):
    """[LEAD item 7] Art Institute of Chicago tour 496 Stop 1 was 'Chicago: a
    challenge for your taste buds | Choose Chicago' — tourism-board chrome from the
    site-first/exhibition path. The junk-title guard must catch it, and it must run
    on EVERY candidate path (site-first _append + JS fallback)."""

    def test_choose_chicago_breadcrumb_rejected(self):
        self.assertTrue(is_junk_page_title(
            "Chicago: a challenge for your taste buds | Choose Chicago",
            "Art Institute of Chicago"))
        self.assertTrue(is_junk_page_title(
            "Things to Do in Chicago | Choose Chicago", "Art Institute of Chicago"))

    def test_guard_wired_into_site_first_paths(self):
        # The site-first builder's _append and the JS fallback both import and call
        # is_junk_page_title — assert the wiring is present in source.
        import inspect
        import exhibition_site_first as esf
        src = inspect.getsource(esf)
        self.assertIn("from junk_title_guard import is_junk_page_title", src)
        self.assertIn("_is_junk", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
