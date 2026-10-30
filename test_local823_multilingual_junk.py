#!/usr/bin/env python3
"""test_local823_multilingual_junk.py — [LOCAL-823] site-chrome in ANY language.

Belvedere (Vienna) cheap-arm proof tour 474, Stop 2 was titled **"Fußzeile"**
(German for "page footer") — website chrome scraped as an artwork title. It
passed every junk guard (791E etc.) because ``junk_title_guard``'s nav/section
sets were ENGLISH-ONLY. This proves the multilingual site-chrome table catches a
footer/header/imprint/privacy/navigation/search/menu/legal/sitemap label in
German, French, Italian, Spanish, Dutch, Portuguese and Vietnamese, through the
ONE shared predicate ``is_junk_page_title`` used by every title path — while a
real multi-language work/exhibition title is never caught.

Pure/offline. Run: python3 -m pytest test_local823_multilingual_junk.py -q
"""
import unittest

from junk_title_guard import is_junk_page_title, filter_out_junk_titles


class TestFusszeileAndGermanChrome(unittest.TestCase):
    V = "Belvedere"

    def test_the_exact_field_defect(self):
        # The exact string that shipped as Belvedere Stop 2.
        self.assertTrue(is_junk_page_title("Fußzeile", self.V))

    def test_fusszeile_ss_spelling(self):
        self.assertTrue(is_junk_page_title("Fusszeile", self.V))

    def test_german_cms_siblings(self):
        for t in ("Kopfzeile", "Impressum", "Datenschutz", "Navigation",
                  "Suche", "Menü", "Startseite", "Öffnungszeiten",
                  "Barrierefreiheit", "Seitenübersicht", "Kontakt",
                  "Hauptnavigation", "Rechtliches"):
            self.assertTrue(is_junk_page_title(t, self.V), t)


class TestOtherLanguageChrome(unittest.TestCase):
    def test_french(self):
        for t in ("Pied de page", "Mentions légales", "Mentions legales",
                  "Plan du site", "Accueil", "Recherche", "Billetterie",
                  "Politique de confidentialité", "Accessibilité"):
            self.assertTrue(is_junk_page_title(t, "Musée d'Orsay"), t)

    def test_italian(self):
        for t in ("Piè di pagina", "Pie di pagina", "Note legali",
                  "Mappa del sito", "Cerca", "Biglietti", "Accessibilità"):
            self.assertTrue(is_junk_page_title(t, "Uffizi"), t)

    def test_spanish(self):
        for t in ("Pie de página", "Pie de pagina", "Aviso legal",
                  "Mapa del sitio", "Buscar", "Entradas", "Accesibilidad"):
            self.assertTrue(is_junk_page_title(t, "Museo del Prado"), t)

    def test_dutch(self):
        for t in ("Voettekst", "Koptekst", "Colofon", "Zoeken",
                  "Openingstijden", "Toegankelijkheid", "Hoofdmenu"):
            self.assertTrue(is_junk_page_title(t, "Rijksmuseum"), t)

    def test_portuguese(self):
        for t in ("Rodapé", "Cabeçalho", "Aviso legal", "Mapa do site",
                  "Pesquisar", "Bilhetes", "Acessibilidade"):
            self.assertTrue(is_junk_page_title(t, "Museu de Arte"), t)

    def test_vietnamese(self):
        for t in ("Chân trang", "Đầu trang", "Trang chủ", "Tìm kiếm",
                  "Liên hệ", "Sơ đồ trang", "Chính sách bảo mật"):
            self.assertTrue(is_junk_page_title(t, "Bảo tàng"), t)


class TestRealWorksAreNotChrome(unittest.TestCase):
    """A real work/exhibition title is never caught, in any language."""

    def test_real_titles_survive(self):
        real = [
            # English / the Belvedere's real stops
            ("Austrian State Treaty", "Belvedere"),
            ("Belvedere Palace Chapel", "Belvedere"),
            ("The Kiss", "Belvedere"),      # Klimt — the Belvedere's most famous work
            ("Judith", "Belvedere"),
            # French — real Orsay works
            ("Le Déjeuner sur l’herbe", "Musée d'Orsay"),
            ("Un bar aux Folies Bergère", "Musée d'Orsay"),
            ("Bal du moulin de la Galette", "Musée d'Orsay"),
            # German
            ("Der Kuss", "Belvedere"),
            ("Napoleon am Großen Sankt Bernhard", "Belvedere"),
            # Italian / Spanish
            ("La nascita di Venere", "Uffizi"),
            ("Las Meninas", "Museo del Prado"),
        ]
        for t, v in real:
            self.assertFalse(is_junk_page_title(t, v), f"FALSE POSITIVE: {t!r}")


class TestSharedChokepointFilters(unittest.TestCase):
    """filter_out_junk_titles — the shared helper — drops the chrome, keeps works."""

    def test_filter_drops_fusszeile_keeps_work(self):
        cands = [
            {"title": "Austrian State Treaty"},
            {"title": "Fußzeile"},
            {"title": "Impressum"},
            {"title": "Belvedere Palace Chapel"},
        ]
        kept, dropped = filter_out_junk_titles(cands, venue_name="Belvedere")
        kept_titles = {c["title"] for c in kept}
        dropped_titles = {c["title"] for c in dropped}
        self.assertEqual(kept_titles,
                         {"Austrian State Treaty", "Belvedere Palace Chapel"})
        self.assertEqual(dropped_titles, {"Fußzeile", "Impressum"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
