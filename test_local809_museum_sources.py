"""test_local809_museum_sources.py — LOCAL-809 evidence tests.

Catalogue review (LOCAL-808) + Mac DB tours 850 (Met) and 861 (Belvedere):

  * Met Store merchandise written up as exhibits — "Empire State Building Custom
    Print", "Wall Calendar 2027 — The Met Store" (tour 850, stops 2 & 3).
  * Belvedere: Monet "Père Paul" and Van Gogh "Plain of Auvers" are NOT in the
    Belvedere (tour 861, stops 3 & 5); stop 1 contained "Belvedere may refer to:"
    (a Wikipedia disambiguation page); all pins ~1 km off (wrong "Belvedere").

Each test uses the EXACT strings from the evidence, not toy fixtures. The four
fixes under test:

  1. shop/commerce pages & titles are never exhibit sources (junk_title_guard);
  2. an exhibit must be held by THIS museum — P195/P276 = venue QID, else reject
     and log [LOCAL-809] not in collection <title> <found collection>
     (artwork_selection_guard.enforce_collection_membership);
  3. a Wikipedia disambiguation page ("X may refer to") is never corpus
     (disambiguation_guard.is_disambiguation_text);
  4. the museum pin is the museum's own Wikidata P625 (pin_snap — authority).

Run: python3 -m pytest test_local809_museum_sources.py -q
     python3 test_local809_museum_sources.py
"""
import unittest

import junk_title_guard as jtg
import artwork_selection_guard as asg
import disambiguation_guard as dg
import pin_snap


# ── Fix 1 — shop / commerce pages are never exhibit sources ──────────────────
class TestShopCommerceReject(unittest.TestCase):
    V = "The Metropolitan Museum of Art"

    def test_met_store_product_titles_rejected(self):
        # The two Met Store products that shipped as stops 2 & 3 of tour 850.
        self.assertTrue(jtg.is_shop_product_title("Empire State Building Custom Print"))
        self.assertTrue(jtg.is_shop_product_title("Wall Calendar 2027 — The Met Store"))
        self.assertTrue(jtg.is_junk_page_title("Empire State Building Custom Print", self.V))
        self.assertTrue(jtg.is_junk_page_title("Wall Calendar 2027 — The Met Store", self.V))

    def test_more_shop_merchandise_rejected(self):
        for t in ("Van Gogh Tote Bag", "Monet Water Lilies Jigsaw Puzzle",
                  "The Scream Magnet Set", "Starry Night Mug — $24.95",
                  "Gift Set: Impressionist Notecards", "Add to cart"):
            self.assertTrue(jtg.is_junk_page_title(t, self.V), t)

    def test_commerce_urls_rejected(self):
        for u in ("https://store.metmuseum.org/wall-calendar-2027",
                  "https://www.metmuseum.org/shop/products/12345",
                  "https://shop.belvedere.at/en/kiss-mug?add-to-cart=88"):
            self.assertTrue(jtg.is_commerce_url(u), u)

    def test_content_urls_not_commerce(self):
        for u in ("https://www.metmuseum.org/art/collection/search/436535",
                  "https://www.belvedere.at/en/the-kiss",
                  "https://en.wikipedia.org/wiki/The_Kiss_(Klimt)"):
            self.assertFalse(jtg.is_commerce_url(u), u)

    def test_commerce_url_rejects_even_clean_title(self):
        # A plain-looking title on a store page is still merchandise.
        self.assertTrue(jtg.is_junk_page_title(
            "Empire State Building", self.V,
            source_url="https://store.metmuseum.org/empire-state-building-print"))

    def test_real_artworks_survive(self):
        # Works whose titles contain shop-ish words but ARE real exhibits.
        for t in ("Self-Portrait with a Straw Hat", "The Blue Boy",
                  "Man in a Red Turban", "Woman with a Parasol", "The Umbrellas",
                  "Washington Crossing the Delaware", "The Card Players",
                  "Boy with a Pipe", "Still Life with a Scarf"):
            self.assertFalse(jtg.is_shop_product_title(t), t)
            self.assertFalse(jtg.is_junk_page_title(t, self.V), t)

    def test_filter_reads_source_url(self):
        cands = [
            {"title": "The Kiss", "creator": "Gustav Klimt",
             "source_url": "https://www.belvedere.at/en/the-kiss"},
            {"title": "Empire State Building Custom Print",
             "source_url": "https://store.metmuseum.org/x"},
            {"title": "Mug", "source_url": "https://store.metmuseum.org/mug?sku=1"},
        ]
        kept, dropped = jtg.filter_out_junk_titles(cands, self.V)
        self.assertEqual({k["title"] for k in kept}, {"The Kiss"})
        self.assertEqual({d["title"] for d in dropped},
                         {"Empire State Building Custom Print", "Mug"})


# ── Fix 2 — artwork ⇄ museum collection (P195/P276) ──────────────────────────
# Belvedere Q303139 (Österreichische Galerie Belvedere). Monet's "Père Paul"
# (P195 = Musée d'Orsay class, Q23402) and Van Gogh's "Plain of Auvers" (P195 =
# Neue Pinakothek, Q163804) are NOT in the Belvedere and must be rejected, with
# the ticket's [LOCAL-809] not in collection line emitted.
BELVEDERE_QID = "Q303139"
BELVEDERE_SPARQL = [
    {"label_en": "The Kiss", "creator": "Gustav Klimt",
     "instance_of": ["Q3305213"], "collection_qids": ["Q303139"]},
    {"label_en": "Death and the Maiden", "creator": "Egon Schiele",
     "instance_of": ["Q3305213"], "collection_qids": ["Q303139"]},
    {"label_en": "Portrait of Fritza Riedler", "creator": "Gustav Klimt",
     "instance_of": ["Q3305213"], "collection_qids": ["Q303139"]},
]
BELVEDERE_CANDIDATES = [
    {"title": "The Kiss", "creator": "Gustav Klimt",
     "instance_of": ["Q3305213"], "collection_qids": ["Q303139"]},
    # leaked — Monet "Père Paul" is NOT in the Belvedere (tour 861 stop 3):
    {"title": "Père Paul", "creator": "Claude Monet",
     "instance_of": ["Q3305213"], "collection_qids": ["Q23402"]},
    # leaked — Van Gogh "Plain of Auvers" is NOT in the Belvedere (stop 5):
    {"title": "Plain of Auvers", "creator": "Vincent van Gogh",
     "instance_of": ["Q3305213"], "collection_qids": ["Q163804"]},
]


class TestCollectionMembership(unittest.TestCase):
    def test_belvedere_rejects_monet_and_vangogh(self):
        kept, dropped = asg.enforce_collection_membership(
            BELVEDERE_CANDIDATES, sparql_works=BELVEDERE_SPARQL,
            venue_name="Belvedere", venue_qid=BELVEDERE_QID)
        kept_titles = {k["title"] for k in kept}
        dropped_titles = {d["title"] for d in dropped}
        self.assertIn("The Kiss", kept_titles)
        self.assertIn("Père Paul", dropped_titles)
        self.assertIn("Plain of Auvers", dropped_titles)
        self.assertNotIn("Père Paul", kept_titles)
        self.assertNotIn("Plain of Auvers", kept_titles)

    def test_dropped_carries_found_collection(self):
        # The reject reason names the work's own P195 (the "found collection")
        # so the [LOCAL-809] not in collection <title> <found collection> line can
        # be printed with the real collection, not the venue's.
        _, dropped = asg.enforce_collection_membership(
            BELVEDERE_CANDIDATES, sparql_works=BELVEDERE_SPARQL,
            venue_name="Belvedere", venue_qid=BELVEDERE_QID)
        by_title = {d["title"]: d for d in dropped}
        self.assertIn("Q23402", by_title["Père Paul"]["_reject_reason"])
        self.assertIn("Q163804", by_title["Plain of Auvers"]["_reject_reason"])
        # And each dropped work still carries its collection_qids for the log.
        self.assertEqual(by_title["Père Paul"]["collection_qids"], ["Q23402"])

    def test_venue_own_works_survive(self):
        kept, _ = asg.enforce_collection_membership(
            BELVEDERE_SPARQL, sparql_works=BELVEDERE_SPARQL,
            venue_name="Belvedere", venue_qid=BELVEDERE_QID)
        self.assertEqual(
            {k["label_en"] for k in kept},
            {"The Kiss", "Death and the Maiden", "Portrait of Fritza Riedler"})


# ── Fix 3 — disambiguation stub is never corpus ──────────────────────────────
class TestDisambiguationGuard(unittest.TestCase):
    def test_belvedere_disambiguation_rejected(self):
        # The exact stub that opened tour 861 stop 1.
        text = ("Belvedere may refer to:\n\nPlaces\nBelvedere, California\n"
                "Belvedere, Marin County, California\nBelvedere (Vienna) ...")
        self.assertTrue(dg.is_disambiguation_text(text, "Belvedere"))

    def test_salem_disambiguation_rejected(self):
        text = "Salem may refer to: Places ... various disambiguation entries."
        self.assertTrue(dg.is_disambiguation_text(text, "Salem"))

    def test_may_also_and_can_refer_rejected(self):
        self.assertTrue(dg.is_disambiguation_text("Vienna may also refer to: ..."))
        self.assertTrue(dg.is_disambiguation_text("Orsay can refer to: ..."))

    def test_foreign_language_disambiguation_rejected(self):
        self.assertTrue(dg.is_disambiguation_text("Das Belvedere steht für: ein Schloss ..."))
        self.assertTrue(dg.is_disambiguation_text("Le Belvédère peut faire référence à ..."))

    def test_real_belvedere_article_kept(self):
        text = ("The Belvedere is a historic building complex in Vienna, "
                "Austria, consisting of two Baroque palaces built by Prince "
                "Eugene of Savoy. It houses the Österreichische Galerie "
                "Belvedere and Gustav Klimt's The Kiss.")
        self.assertFalse(dg.is_disambiguation_text(text, "Belvedere"))

    def test_real_met_article_kept_despite_referred_to(self):
        # "referred to as the Met" must NOT trip the "refers to" rule.
        text = ("The Metropolitan Museum of Art, colloquially referred to as the "
                "Met, is the largest art museum in the Americas.")
        self.assertFalse(dg.is_disambiguation_text(text, "Metropolitan Museum of Art"))

    def test_empty_text_is_not_disambiguation(self):
        self.assertFalse(dg.is_disambiguation_text("", "Belvedere"))


# ── Fix 4 — museum pin = own Wikidata P625 ───────────────────────────────────
class TestPinUsesOwnP625(unittest.TestCase):
    def test_wikidata_p625_is_the_authority_reference(self):
        # Upper Belvedere's own P625 (48.1915, 16.3809). A shipped pin ~1 km off
        # (the wrong "Belvedere") must snap to the museum's own P625.
        wrong = (48.2015, 16.3690)          # ~1.1 km from the real palace
        own_p625 = (48.1915, 16.3809)
        row = pin_snap.snap_pin(
            "Belvedere", wrong, scope="Vienna",
            scope_center=(48.2082, 16.3738), wikidata_coord=own_p625)
        self.assertEqual(row["source"], "wikidata")
        self.assertTrue(row["snapped"])
        self.assertEqual(row["new_coordinate"], own_p625)

    def test_good_p625_pin_kept(self):
        own_p625 = (48.1915, 16.3809)
        # Shipped pin already on the P625 — within threshold, kept.
        row = pin_snap.snap_pin(
            "Belvedere", own_p625, scope="Vienna",
            scope_center=(48.2082, 16.3738), wikidata_coord=own_p625)
        self.assertEqual(row["source"], "wikidata")
        self.assertFalse(row["snapped"])

    def test_poi_list_snaps_to_wikidata(self):
        pois = [{
            "name": "Belvedere",
            "coordinates": "48.2015, 16.3690",   # ~1 km off
            "wikidata_lat": 48.1915, "wikidata_lng": 16.3809,
        }]
        _, rows = pin_snap.snap_poi_coordinates(
            pois, scope="Vienna", scope_center=(48.2082, 16.3738))
        self.assertTrue(rows[0]["snapped"])
        self.assertEqual(rows[0]["source"], "wikidata")
        self.assertTrue(pois[0]["coordinates"].startswith("48.1915"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
