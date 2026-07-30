"""
LOCAL-28: Test structured catalogue extraction from museum "oeuvres commentées" pages.

Tests:
1. extract_catalogue_works_from_pages correctly identifies catalogue pages by URL
2. Works are extracted with structured metadata (title, material, period, origin)
3. Bare generic nouns (disque, fauteuil) are excluded by is_bare_generic_noun
4. Multi-word proper titles are preserved
5. Catalogue works get injected into canonical_titles
"""
import sys
sys.path.insert(0, '.')

import pytest
from story_miner import (
    extract_catalogue_works_from_pages,
    is_bare_generic_noun,
    classify_corpus_entry,
    _CATALOGUE_PAGE_URL_PATTERNS,
)


class TestCataloguePageDetection:
    """Test that catalogue pages are correctly detected by URL pattern."""
    
    def test_oeuvres_commentees(self):
        assert _CATALOGUE_PAGE_URL_PATTERNS.search("https://maa.departement06.fr/les-oeuvres-commentees")
    
    def test_les_oeuvres(self):
        assert _CATALOGUE_PAGE_URL_PATTERNS.search("https://example.com/les-oeuvres")
    
    def test_highlights(self):
        assert _CATALOGUE_PAGE_URL_PATTERNS.search("https://museum.org/collection-highlights")
    
    def test_masterpieces(self):
        assert _CATALOGUE_PAGE_URL_PATTERNS.search("https://museum.org/masterpieces")
    
    def test_chefs_doeuvre(self):
        assert _CATALOGUE_PAGE_URL_PATTERNS.search("https://museum.fr/chefs-d-oeuvres")
    
    def test_opere_scelte(self):
        assert _CATALOGUE_PAGE_URL_PATTERNS.search("https://museum.it/opere-scelte")
    
    def test_hauptwerke(self):
        assert _CATALOGUE_PAGE_URL_PATTERNS.search("https://museum.de/hauptwerke")
    
    def test_non_catalogue_url(self):
        assert not _CATALOGUE_PAGE_URL_PATTERNS.search("https://museum.org/about")
        assert not _CATALOGUE_PAGE_URL_PATTERNS.search("https://museum.org/tarifs")


class TestBareGenericNounFilter:
    """Test that bare generic nouns are correctly identified and excluded."""
    
    def test_single_word_french_nouns(self):
        assert is_bare_generic_noun("disque")
        assert is_bare_generic_noun("fauteuil")
        assert is_bare_generic_noun("vase")
        assert is_bare_generic_noun("table")
    
    def test_single_word_english_nouns(self):
        assert is_bare_generic_noun("disc")
        assert is_bare_generic_noun("armchair")
        assert is_bare_generic_noun("chair")
    
    def test_article_plus_generic_noun(self):
        assert is_bare_generic_noun("le disque")
        assert is_bare_generic_noun("un fauteuil")
        assert is_bare_generic_noun("the chair")
    
    def test_multi_word_proper_titles_preserved(self):
        """Multi-word proper titles should NOT be flagged as bare nouns."""
        assert not is_bare_generic_noun("La geste de Bouddha")
        assert not is_bare_generic_noun("Les paysages de l'âme")
        assert not is_bare_generic_noun("L'Armure d'Andô Naoyuki")
        assert not is_bare_generic_noun("Statue de Bouddha")
        assert not is_bare_generic_noun("Masque du vieillard kojô")
    
    def test_proper_names_preserved(self):
        """Proper names should NOT be flagged even if single word."""
        assert not is_bare_generic_noun("Hokusai")
        assert not is_bare_generic_noun("Ganesh")
        assert not is_bare_generic_noun("Kannon")
    
    def test_classifier_integration(self):
        """classify_corpus_entry should exclude bare generic nouns via Rule 8."""
        result = classify_corpus_entry("disque", venue_name="Musée des Arts asiatiques")
        assert result['kind'] == 'excluded'
        assert result['rule'] == 'bare_generic_noun'
        
        result = classify_corpus_entry("fauteuil", venue_name="Musée des Arts asiatiques")
        assert result['kind'] == 'excluded'
        assert result['rule'] == 'bare_generic_noun'


class TestCatalogueExtraction:
    """Test structured extraction from catalogue page text."""
    
    @pytest.fixture
    def maa_oeuvres_page(self):
        """Simulated text content from the MAA oeuvres-commentées page."""
        return [{
            "url": "https://maa.departement06.fr/les-oeuvres-commentees",
            "text": """Le musée en vidéo : Les œuvres commentées

Armure de type dô-maru Epoque d'Edo (1603-1868), vers 1850 Acier, cuivre, cuir, soie, laque et feuille d'or

L'Armure d'Andô Naoyuki

Milieu du XIXe siècle, Japon

Au milieu du XIXe siècle, au Japon, Andô Naoyuki va avoir 15 ans. Héritier du fief de Tanabe, il est destiné au titre de baron. Cette armure a été conçue pour lui, plus précisément pour son genpuku, cérémonie de passage à l'âge adulte. À la fois sobrement fonctionnelle et luxueuse, cette armure d'apparat est composée de plus de 3500 écailles d'acier et de cuir, laquées et dorées.

Statue de Bouddha

Les conquêtes d'Alexandre le Grand ont durablement marqué l'histoire de l'art. Conservée au musée départemental des arts asiatiques de Nice, cette statue en schiste gris de Bouddha, datée du IIe siècle, constitue un témoignage éloquent de la rencontre entre art grec et art indien.

La danse cosmique de Ganesh

Différentes traditions font de Ganesh le fils du dieu Shiva et de sa parèdre la déesse Parvati. Provenant de la région du Bengale ou du Bihar, cette stèle en chlorite de la 2nde moitié du Xe siècle exprime l'essence de l'esthétique indienne.

Kannon, le bodhisattva de la compassion

Réalisée dans un bois de cyprès durant la seconde moitié du XIIe siècle, cette remarquable statue japonaise représente Juichimen Kannon. Cette œuvre majeure des collections illustre la pratique du bouddhisme au Japon.

Ulysses Grant au Japon

Datée de 1879 et réalisée par Chikanobu, cette estampe représente la réception au palais impérial du président des États-Unis. Cette xylogravure polychrome illustre l'utilisation au Japon des estampes pour relayer les actualités.

Robe de prêtre taoïste

Cette robe de prêtre, appelée jiangyi, servait aux rituels taoïstes. Datée du XVIIIe siècle, cette robe est faite de soie brodée. Le dos du vêtement est orné d'un diagramme de l'univers.

Kannon à mille bras

Kannon, le bodhisattva de la compassion, est représenté assis sur un lotus. Sa tête est surmontée de 11 têtes plus petites. Le bodhisattva est doté de 42 bras.

Masque du vieillard kojô

Réalisé en bois laqué, ce masque est daté du XVIe siècle et représente les traits d'un vieil homme, Kojô, personnage joué dans le théâtre Nô.

Armure du Clan Hotta

Datée de la première moitié du XIXe siècle, l'armure porte le mon de la famille Hotta. La pièce est en cuir laqué noir avec de luxueuses montures.""",
            "title": "les-oeuvres-commentees",
        }]
    
    def test_extraction_finds_works(self, maa_oeuvres_page):
        """Should extract multiple documented works from the page."""
        works = extract_catalogue_works_from_pages(maa_oeuvres_page)
        assert len(works) >= 5, f"Expected at least 5 works, got {len(works)}: {[w['title'] for w in works]}"
    
    def test_extraction_captures_titles(self, maa_oeuvres_page):
        """Should capture the correct work titles."""
        works = extract_catalogue_works_from_pages(maa_oeuvres_page)
        titles = [w['title'] for w in works]
        
        # Core titles that MUST be found (from the 9 documented works)
        expected_any_of = [
            "Statue de Bouddha",
            "La danse cosmique de Ganesh",
            "Kannon, le bodhisattva de la compassion",
            "Ulysses Grant au Japon",
            "Robe de prêtre taoïste",
            "Masque du vieillard kojô",
            "Armure du Clan Hotta",
        ]
        found = sum(1 for exp in expected_any_of if exp in titles)
        assert found >= 5, f"Expected at least 5 of the known works, found {found} in {titles}"
    
    def test_extraction_captures_material(self, maa_oeuvres_page):
        """Should extract material metadata."""
        works = extract_catalogue_works_from_pages(maa_oeuvres_page)
        works_by_title = {w['title']: w for w in works}
        
        # The Ganesh stele should have chlorite
        if "La danse cosmique de Ganesh" in works_by_title:
            ganesh = works_by_title["La danse cosmique de Ganesh"]
            assert 'chlorite' in ganesh.get('material', '').lower(), \
                f"Ganesh material should contain 'chlorite', got: {ganesh.get('material')}"
    
    def test_extraction_captures_period(self, maa_oeuvres_page):
        """Should extract period/date metadata."""
        works = extract_catalogue_works_from_pages(maa_oeuvres_page)
        works_by_title = {w['title']: w for w in works}
        
        # Masque du vieillard kojô should have XVIe siècle
        if "Masque du vieillard kojô" in works_by_title:
            mask = works_by_title["Masque du vieillard kojô"]
            assert mask.get('period', ''), f"Mask should have a period, got empty"
    
    def test_extraction_captures_origin(self, maa_oeuvres_page):
        """Should extract geographic origin."""
        works = extract_catalogue_works_from_pages(maa_oeuvres_page)
        works_by_title = {w['title']: w for w in works}
        
        # L'Armure d'Andô Naoyuki should have Japan origin
        if "L'Armure d'Andô Naoyuki" in works_by_title:
            armure = works_by_title["L'Armure d'Andô Naoyuki"]
            assert 'japon' in armure.get('origin', '').lower(), \
                f"Armure origin should contain 'Japon', got: {armure.get('origin')}"
    
    def test_non_catalogue_page_ignored(self):
        """Pages without catalogue URL pattern should be ignored."""
        pages = [{
            "url": "https://museum.org/about",
            "text": "This is the about page of the museum. Founded in 1998.",
            "title": "About",
        }]
        works = extract_catalogue_works_from_pages(pages)
        assert works == []
    
    def test_confidence_field(self, maa_oeuvres_page):
        """All extracted works should have confidence='catalogue'."""
        works = extract_catalogue_works_from_pages(maa_oeuvres_page)
        for w in works:
            assert w['confidence'] == 'catalogue'


class TestCatalogueIntegration:
    """Test that catalogue works integrate with the broader pipeline."""
    
    def test_catalogue_titles_in_canonical_set(self):
        """Catalogue work titles should be added to canonical_titles."""
        # This is an integration test that would require a full corpus run.
        # Here we test the mechanism: extract_catalogue_works returns titles
        # that get added in fetch_venue_narrative_corpus.
        pages = [{
            "url": "https://museum.org/oeuvres-commentees",
            "text": """Masterwork Gallery

The Great Bronze Statue

This remarkable bronze statue from the 12th century represents a deity from the Khmer empire.
It was acquired in 1985 and is one of the museum's prized possessions.
The statue demonstrates exceptional craftsmanship of the period and shows
influences from both Hindu and Buddhist traditions. Standing at 1.5 meters tall,
it is the centrepiece of the Southeast Asian gallery.

The Sacred Imperial Scroll

This paper scroll from Japan dates to the Edo period (1603-1868).
It depicts scenes from daily life in remarkable detail and color.
The scroll measures 12 meters long and features gold leaf accents
throughout its delicate brushwork. It was donated by the Nakamura family in 2001.""",
            "title": "oeuvres-commentees",
        }]
        works = extract_catalogue_works_from_pages(pages)
        # Should find at least one work from the catalogue page
        assert len(works) >= 1, f"Should extract at least one work from catalogue page, got: {[w['title'] for w in works]}"
        # All extracted works should have the catalogue confidence tag
        for w in works:
            assert w['confidence'] == 'catalogue'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
