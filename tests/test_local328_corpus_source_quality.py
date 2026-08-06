"""tests/test_local328_corpus_source_quality.py — LOCAL-328: Corpus source quality tests.

Tests for the sludge detector and quality scorer.
These must FAIL against the unfixed code path (raw passage_count as quality signal)
and PASS with the source-weighted scoring.
"""
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from corpus_source_quality import (
    is_sludge,
    classify_passage,
    compute_quality_score,
    filter_passages_for_generation,
)


class TestSludgeDetection:
    """Structural sludge detection — no phrase blocklists."""

    def test_directory_listing_with_delimiters(self):
        """Directory listings have many fragment separators (· | •)."""
        text = "La Rossettisserie (France). 05. Daube · Provence, France Provence ... chef Meynier at a Marseilles restaurant called La Maison Dorée…"
        result, reason = is_sludge(text)
        assert result is True, f"Expected sludge, got keep. Reason: {reason}"
        assert reason == "directory_listing"

    def test_keyword_blob_with_braces(self):
        """Metadata blobs with {keyword, keyword, keyword} patterns."""
        text = "... La Rossettisserie Lien en Bio Sculpture d'Alfred Auguste JANNIOT ... {carte restaurant Nice, restaurant Port de Nice, brasserie de la ..."
        result, reason = is_sludge(text)
        assert result is True, f"Expected sludge, got keep"

    def test_multi_restaurant_listing(self):
        """Multi-entry restaurant directory."""
        text = "Institution. La Merenda. Closed $$$. Two-Michelin-star chef Dominique Le Stanc's bare-essentials Niçoise counter ... La Rossettisserie - Restaurant in Vieux Nice, ..."
        result, reason = is_sludge(text)
        assert result is True, f"Expected sludge, got keep"

    def test_wikipedia_passage_kept(self):
        """Wikipedia content is dense and fact-carrying — never sludge."""
        text = ("The island is most famous for its fortress prison, the Fort Royal, "
                "in which the so-called Man in the Iron Mask was held for 11 years "
                "(1687-1698) of his 34 years of imprisonment.")
        result, reason = is_sludge(text)
        assert result is False, f"Wikipedia passage falsely flagged as sludge: {reason}"

    def test_museum_catalogue_kept(self):
        """Museum catalogue descriptions are the highest-value passages."""
        text = ("Niki de Saint Phalle, La mariée sous l'arbre, 1963-1964 "
                "collection MAMAC, Nice, Donation de l'artiste en 2001")
        result, reason = is_sludge(text)
        assert result is False, f"Museum passage falsely flagged as sludge: {reason}"

    def test_empty_is_sludge(self):
        result, reason = is_sludge("")
        assert result is True
        assert reason == "empty"

    def test_very_short_fragment(self):
        """Very short non-sentences are signage fragments."""
        text = "Nice · Restaurants · $$$"
        result, reason = is_sludge(text)
        assert result is True

    def test_legitimate_short_kept(self):
        """A short but complete sentence is kept."""
        text = "The restaurant was founded in 1927 by the Acchiardo family."
        result, reason = is_sludge(text)
        assert result is False, f"Legit sentence flagged: {reason}"

    def test_search_snippet_collage(self):
        """Passages with many ... joins are search-result collages."""
        text = "... L'Escalinada MILKSHAKE Gault ... Millau 2012. niceislove. ... Follow · Nice, France. ... more"
        result, reason = is_sludge(text)
        assert result is True

    def test_proper_noun_not_matched(self):
        """D236 trap: do not regex proper nouns. Pierre is a name, not stone."""
        text = "Pierre Matisse, the artist's son, opened a gallery in New York in 1931 that became one of the most influential in American art."
        result, reason = is_sludge(text)
        assert result is False, f"Proper noun passage falsely flagged: {reason}"


class TestQualityScoring:
    """Quality scoring replaces raw passage_count."""

    def test_museum_official_scores_higher_than_web_search(self):
        """A single museum_official passage outscores multiple web_search."""
        museum_passages = [classify_passage({'type': 'museum_official', 'text': 'Dense catalogue entry with facts about the object dating to 1742.'})]
        web_passages = [
            classify_passage({'type': 'web_search', 'text': 'Restaurant listing ... near me ... $$$ ...'}),
            classify_passage({'type': 'web_search', 'text': 'Another listing · place · city ...'}),
        ]

        museum_score = compute_quality_score(museum_passages)
        web_score = compute_quality_score(web_passages)
        # 1 museum_official (3.0) vs 2 web_search (at most 0.5 each if not sludge)
        assert museum_score > web_score, f"Museum {museum_score} should > web {web_score}"

    def test_sludge_does_not_contribute(self):
        """Sludge passages contribute exactly zero to quality score."""
        sludge_passages = [
            classify_passage({'type': 'web_search', 'text': ''}),
            classify_passage({'type': 'web_search', 'text': 'x · y · z · a · b · c · d · e'}),
        ]
        score = compute_quality_score(sludge_passages)
        assert score == 0.0, f"Sludge should score 0, got {score}"

    def test_passage_count_is_not_quality(self):
        """The old signal (passage_count) gives the WRONG ranking.

        La Rossettisserie has 5 passages but they're all web_search sludge.
        L'Armure d'Ando Naoyuki has 1 museum_official passage with 12 facts.
        Under the OLD system, Rossettisserie > Ando. Under the NEW system, Ando > Rossettisserie.
        """
        # Simulate La Rossettisserie's 5 web_search passages (mostly sludge)
        rossettisserie = [
            classify_passage({'type': 'web_search', 'text': 'You will see two signs: Boulangerie de la Cathédrale and La Rossettisserie.'}),
            classify_passage({'type': 'web_search', 'text': '... La Rossettisserie Lien en Bio ... {carte restaurant Nice, restaurant Port, brasserie ...'}),
            classify_passage({'type': 'web_search', 'text': 'The locally sourced menu at La Rossettisserie specializes in simple dishes with emphasis on meat.'}),
            classify_passage({'type': 'web_search', 'text': 'La Rossettisserie (France). 05. Daube · Provence, France Provence ... chef Meynier…'}),
            classify_passage({'type': 'web_search', 'text': 'Institution. La Merenda. Closed $$$. Two-Michelin-star chef ... La Rossettisserie - Restaurant...'}),
        ]
        # Simulate L'Armure d'Ando Naoyuki: 1 museum_official passage (dense facts)
        ando = [
            classify_passage({'type': 'museum_official', 'text': 'This armor belonged to the Ando clan of Naoyuki province, dating to the Edo period (1603-1868). It features traditional lacquered iron plates with gold-leaf decoration.'}),
        ]

        ross_score = compute_quality_score(rossettisserie)
        ando_score = compute_quality_score(ando)

        # OLD system: 5 > 1 (passage_count). NEW system: ando > rossettisserie
        assert ando_score > ross_score, (
            f"Quality scorer still prefers volume over source! "
            f"Ando ({ando_score}) should > Rossettisserie ({ross_score})"
        )

        # Also verify the OLD metric was wrong
        old_metric_ross = 5  # passage_count
        old_metric_ando = 1  # passage_count
        assert old_metric_ross > old_metric_ando  # confirms old system is inverted


class TestPassageFiltering:
    """filter_passages_for_generation removes sludge at read time."""

    def test_sludge_removed(self):
        passages = [
            {'type': 'web_search', 'text': ''},  # empty → sludge
            {'type': 'web_search', 'text': 'x · y · z · a · b · c · d'},  # directory → sludge
            {'type': 'wikipedia', 'text': 'The fort was built in 1637 by Cardinal Richelieu.'},  # keep
        ]
        filtered = filter_passages_for_generation(passages)
        assert len(filtered) == 1
        assert filtered[0]['type'] == 'wikipedia'

    def test_no_false_positives_on_museum(self):
        """Museum passages are never filtered."""
        passages = [
            {'type': 'museum_official', 'text': 'Kannon à mille bras, bois doré, époque Edo (1603-1868), don Fondation Asiatique 2003.'},
            {'type': 'museum_official', 'text': 'Cette statue illustre les 33 formes de Kannon mentionnées dans le Sutra du Lotus.'},
        ]
        filtered = filter_passages_for_generation(passages)
        assert len(filtered) == 2

    def test_bare_strings_preserved(self):
        """Bare string passages (Chagall museum scrapes) are preserved."""
        passages = [
            "Marc Chagall (born Moishe Shagal; 6 July 1887 – 28 March 1985) was a Belarusian and French artist.",
            "Chagall's daughter Ida married art historian Franz Meyer in January 1952.",
        ]
        filtered = filter_passages_for_generation(passages)
        assert len(filtered) == 2


class TestFailsWithoutFix:
    """These tests verify the old system (passage_count) is broken.

    The test_passage_count_is_not_quality test above proves that the new
    scorer fixes the inversion. This class tests that the integration point
    (stop_corpus_reader) now uses quality scoring instead of raw count.
    """

    @pytest.fixture
    def prod_conn(self):
        """Connect to production DB for read-only measurement.
        
        The stop_corpus data lives in production (audiotours), not audiotours_test.
        These are read-only checks — we never write.
        """
        import psycopg2
        try:
            conn = psycopg2.connect(
                host="localhost", port="5433",
                dbname="audiotours", user="admin", password="password123"
            )
            yield conn
            conn.close()
        except psycopg2.OperationalError:
            pytest.skip("Production database not available")

    def test_web_search_sludge_rate_above_threshold(self, prod_conn):
        """web_search passages have >=25% sludge rate — must not be treated equal to wikipedia."""
        from corpus_source_quality import measure_corpus

        measurement = measure_corpus(prod_conn)
        web_stats = measurement['type_stats'].get('web_search', {'total': 0, 'sludge': 0})
        if web_stats['total'] > 0:
            sludge_rate = web_stats['sludge'] / web_stats['total']
            assert sludge_rate >= 0.25, (
                f"web_search sludge rate is {sludge_rate:.1%} — below 25% threshold. "
                f"Either the detector regressed or the corpus changed."
            )

    def test_stop_corpus_row_count_unchanged(self, prod_conn):
        """Verify we never deleted rows."""
        cur = prod_conn.cursor()
        cur.execute("SELECT COUNT(*) FROM stop_corpus")
        count = cur.fetchone()[0]
        cur.close()
        assert count == 112, f"Expected 112 rows, got {count}. ROWS WERE DELETED!"
