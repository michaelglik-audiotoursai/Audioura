"""test_local721_cta_link_text.py — [LOCAL-721] reject website CTA / link text.

Four fresh 6-stop tours of "Courtauld Gallery, London" ALL delivered two stops
titled "Explore this sculpture in our virtual tour" and "Explore this painting in
our virtual tour". The phrase is the anchor text of the link wrapping each work's
image on the Courtauld site; it is scraped into the venue corpus / candidate-works
list (~80× per generation log) and, having no chrome separator and no bare-nav
shape, slipped past every existing junk rule to become a STOP.

The fix is a generic, venue-agnostic call-to-action rule added to the shared
intake predicate ``junk_title_guard.is_junk_page_title`` (the chokepoint used by
site_candidate_guard, exhibition_site_first, and artwork_selection_guard). A CTA
is an instruction ABOUT the website — an imperative visitor-action opener
("Explore this …", "Book your tickets", "Learn more", "Plan your visit") or a
phrase naming an online/marketing feature ("virtual tour", "gift shop", "create
your own gallery"). It is NOT a thing on a wall.

These tests pin the two literal Courtauld strings as REJECTED and a set of real
titles — including a verb-opening title ("Explosion") and genuine imperative-
looking work titles ("Take Your Son, Sir!", "View of Verona", "Visit of the Queen
of Sheba to Solomon", "Reading the Letter") — as KEPT, so the rule can never drift
into dropping a real work.

Pure/offline — no network, no DB, no LLM.
"""
import unittest

from junk_title_guard import is_junk_page_title, filter_out_junk_titles


class TestCTALinkTextRejected(unittest.TestCase):
    V = "Courtauld Gallery"

    def test_the_two_courtauld_cta_strings_rejected(self):
        # The exact stops that shipped on all four live Courtauld tours.
        self.assertTrue(is_junk_page_title(
            "Explore this painting in our virtual tour", self.V))
        self.assertTrue(is_junk_page_title(
            "Explore this sculpture in our virtual tour", self.V))
        # The sibling anchor text in the same candidate list.
        self.assertTrue(is_junk_page_title(
            "Explore this piece of furniture in our virtual tour", self.V))

    def test_other_courtauld_cta_candidates_rejected(self):
        # Further CTA / marketing link text from the same generation log.
        for t in ["Join and Support", "Create your own gallery",
                  "Shop the catalogue", "Gallery Virtual Tours"]:
            self.assertTrue(is_junk_page_title(t, self.V), t)

    def test_generic_cta_phrases_rejected_any_venue(self):
        # Venue-agnostic: the rule holds for any museum site, not just Courtauld.
        for t in ["Book tickets", "Book your tickets", "Buy tickets",
                  "Learn more", "Discover more", "Explore our collection",
                  "View in 3D", "View our online collection",
                  "Plan your visit", "Visit us today",
                  "Browse the collection online", "Download the app",
                  "Sign up for our newsletter", "Subscribe to our newsletter"]:
            self.assertTrue(is_junk_page_title(t, "The Rijksmuseum"), t)


class TestRealTitlesSurvive(unittest.TestCase):
    V = "Courtauld Gallery"

    def test_five_real_courtauld_titles_kept(self):
        # The task's named survivors + the Courtauld household names.
        for t in ["A Bar at the Folies-Bergère",
                  "Self-Portrait with Bandaged Ear",
                  "Explosion",                       # opens with a verb-like word
                  "The Card Players",
                  "Still Life with Pears"]:
            self.assertFalse(is_junk_page_title(t, self.V), t)

    def test_verb_opening_real_titles_not_dropped(self):
        # Real work titles that OPEN with an imperative-looking word must survive —
        # this is the whole risk of a CTA rule. A lone verb-like word, or a verb
        # followed by "of"/a content noun (not an instruction connective), is a
        # title, not an instruction.
        for t in ["Explosion",
                  "Take Your Son, Sir!",             # Ford Madox Brown
                  "Giving Alms",
                  "Reading the Letter",
                  "View of Verona (after Bernardo Bellotto)",
                  "View on Valmontone",
                  "View of Delft",
                  "Visit of the Queen of Sheba to Solomon",
                  "Visitation",
                  "Discovery of Honey by Bacchus",
                  "Start of the Hunt"]:
            self.assertFalse(is_junk_page_title(t, self.V), t)

    def test_descriptive_titles_with_site_words_kept(self):
        # A word that is part of a CTA elsewhere, used descriptively in a real
        # title, must not trip the rule.
        for t in ["The Haystacks", "Street in Pont Aven", "Te Rerioa",
                  "Woman Tying Her Shoe", "Landscape – Capriccio",
                  "Virgin and Child", "Signac in His Studio"]:
            self.assertFalse(is_junk_page_title(t, self.V), t)


class TestFilterSplitsCTA(unittest.TestCase):
    V = "Courtauld Gallery"

    def test_filter_out_junk_titles_drops_cta_keeps_works(self):
        cands = [{"name": "A Bar at the Folies-Bergère"},
                 {"name": "Explore this painting in our virtual tour"},
                 {"name": "Self-Portrait with Bandaged Ear"},
                 {"name": "Explore this sculpture in our virtual tour"},
                 {"name": "Explosion"},
                 {"name": "Create your own gallery"}]
        kept, dropped = filter_out_junk_titles(cands, self.V)
        self.assertEqual(
            [k["name"] for k in kept],
            ["A Bar at the Folies-Bergère", "Self-Portrait with Bandaged Ear",
             "Explosion"])
        self.assertEqual(len(dropped), 3)
        self.assertTrue(all(d.get("_reject_reason") == "junk_page_title"
                            for d in dropped))


if __name__ == "__main__":
    unittest.main()
