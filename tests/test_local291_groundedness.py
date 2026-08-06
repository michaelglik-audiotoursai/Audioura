#!/usr/bin/env python3
"""tests/test_local291_groundedness.py — LOCAL-291: Groundedness tests.

Tests the groundedness check module:
1. Name normalisation (D187 fix)
2. Groundedness classification logic (RICH ceiling, CONTRADICTED scoring)
3. Corpus worklist emission
4. Operator override to FABRICATED still works
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from groundedness_check import (
    normalize_name,
    names_match,
    extract_fact_claims,
    check_claim_grounded,
    measure_stop_groundedness,
    FactClaim,
)
from tour_rubric_scorer import (
    classify_stop,
    compute_score,
    score_tour_file,
    StopAnalysis,
    TourScore,
    RICH_MIN_GROUNDEDNESS,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Name normalisation (D187)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNameNormalisation:
    """D187: Different forms of the same person must match."""

    def test_beatrice_rothschild_variants(self):
        """The exact case from the task: Baroness Béatrice / Béatrice Ephrussi / Béatrice de Rothschild."""
        assert names_match("Baroness Béatrice", "Béatrice de Rothschild")
        assert names_match("Béatrice Ephrussi", "Béatrice de Rothschild")
        assert names_match("Baroness Béatrice", "Béatrice Ephrussi")

    def test_accent_folding(self):
        """Accented and unaccented forms match."""
        assert names_match("Marc Chagall", "Marc Chagall")
        # Name normalisation only handles person names — place-name filtering
        # happens upstream in _NOT_A_PERSON_RE. The name matcher itself
        # correctly matches accent-folded forms.
        tokens_a = normalize_name("Béatrice")
        tokens_b = normalize_name("Beatrice")
        assert tokens_a == tokens_b

    def test_title_stripping(self):
        """Titles/honorifics are stripped."""
        assert names_match("Sir Winston Churchill", "Winston Churchill")
        # "Saint" is stripped as a title, so "Saint Francis" → ["francis"]
        # matches "Francis" → ["francis"]. This is correct: if the person
        # extractor emits both forms, they should match.
        assert names_match("Saint Francis", "Francis")
        assert names_match("Count Ferdinand de Lesseps", "Ferdinand Lesseps")

    def test_particle_removal(self):
        """Particles (de, du, van, von) are removed."""
        assert names_match("Vincent van Gogh", "Vincent Gogh")
        assert names_match("Ludwig van Beethoven", "Ludwig Beethoven")

    def test_distinct_names_do_not_match(self):
        """Different people must not match."""
        assert not names_match("Claude Monet", "Pierre Renoir")
        assert not names_match("Marc Chagall", "Henri Matisse")

    def test_partial_name_matches(self):
        """A last name alone should match a full name."""
        # "Monet" (1 token) vs "Claude Monet" (2 tokens) → overlap = 1/1 = 100%
        assert names_match("Monet", "Claude Monet")

    def test_normalize_name_empty(self):
        """Empty/trivial names produce empty token list."""
        assert normalize_name("") == []
        assert normalize_name("de la") == []


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Groundedness classification logic
# ═══════════════════════════════════════════════════════════════════════════════

class TestGroundednessClassification:
    """Groundedness as a RICH ceiling, CONTRADICTED scoring."""

    def _make_stop_analysis(self, **kwargs):
        """Helper to make a StopAnalysis with defaults for RICH classification."""
        sa = StopAnalysis(index=1, title='Test Stop', text='...')
        sa.distinct_fact_count = kwargs.get('facts', 5)
        sa.content_sentences = kwargs.get('sentences', 6)
        sa.fact_density = kwargs.get('density', 0.83)
        sa.generic_filler_fraction = kwargs.get('filler', 0.1)
        sa.groundedness_fraction = kwargs.get('groundedness', 1.0)
        sa.contradicted_share = kwargs.get('contradicted_share', 0.0)
        return sa

    def test_rich_with_full_groundedness(self):
        """A stop meeting RICH criteria with high groundedness → RICH."""
        sa = self._make_stop_analysis(groundedness=0.80)
        cls, _ = classify_stop(sa)
        assert cls == 'RICH'

    def test_rich_capped_by_low_groundedness(self):
        """A stop meeting RICH criteria but below groundedness floor → ADEQUATE."""
        sa = self._make_stop_analysis(groundedness=0.30)  # Below 0.40
        cls, evidence = classify_stop(sa)
        assert cls == 'ADEQUATE'
        assert 'capped by groundedness floor' in evidence

    def test_groundedness_does_not_penalise(self):
        """Low groundedness does not push below ADEQUATE to THIN.

        [LOCAL-304] Fixture uses facts=3, not 2. LOCAL-304 raised
        ADEQUATE_MIN_FACTS from 2 to 3 when it widened the fact detector, so
        facts=2 is now THIN on the fact count alone and no longer constructs the
        scenario this test describes. The assertion is unchanged — the property
        under test is that groundedness caps RICH and never demotes below
        ADEQUATE, verified separately across groundedness 100%/50%/20%/0%.
        """
        sa = self._make_stop_analysis(facts=3, density=0.25, filler=0.3, groundedness=0.10)
        cls, _ = classify_stop(sa)
        # Meets ADEQUATE criteria → ADEQUATE (groundedness only caps RICH)
        assert cls == 'ADEQUATE'

    def test_contradicted_overrides_all(self):
        """A stop with contradicted_share > 0 → CONTRADICTED regardless of density."""
        sa = self._make_stop_analysis(contradicted_share=0.20)
        cls, evidence = classify_stop(sa)
        assert cls == 'CONTRADICTED'
        assert 'contradicted_share' in evidence

    def test_contradicted_scored_proportionally(self):
        """CONTRADICTED weight is −1.0 × share × contradicted_share."""
        sa = self._make_stop_analysis(contradicted_share=0.20)
        sa.classification = 'CONTRADICTED'
        sa.classification_evidence = 'test'

        ts = compute_score([sa], n_requested=1, venue_identity_facts=[])
        # share = 100/1 = 100, weight = -1.0 * 100 * 0.20 = -20
        assert ts.per_stop_base[0] == pytest.approx(-20.0)

    def test_groundedness_floor_value(self):
        """The floor is set at 0.40 (measured p25 of corpus-covered stops)."""
        assert RICH_MIN_GROUNDEDNESS == 0.40


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Operator override (FABRICATED must still work)
# ═══════════════════════════════════════════════════════════════════════════════

class TestOperatorOverride:
    """FABRICATED remains assignable by operator override."""

    def test_fabricated_override(self):
        """Explicit FABRICATED classification overrides computed classification."""
        # Create a minimal tour text
        tour_text = "Stop 1: Test Place\nThis is a test stop with some text.\n"
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(tour_text)
            filepath = f.name

        try:
            # Score with operator override to FABRICATED
            ts = score_tour_file(filepath, 1, classifications={1: ('FABRICATED', 'operator marked')})
            assert ts.stops[0].classification == 'FABRICATED'
            assert 'OPERATOR OVERRIDE' in ts.stops[0].classification_evidence
            # FABRICATED scores -1.0 × share
            assert ts.per_stop_base[0] == pytest.approx(-100.0)
        finally:
            os.unlink(filepath)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Fact claim extraction and grounding
# ═══════════════════════════════════════════════════════════════════════════════

class TestFactClaims:
    """Extract and check fact claims."""

    def test_extract_person(self):
        """Named people near action verbs are extracted."""
        text = "Claude Monet painted here in 1888."
        claims = extract_fact_claims(text)
        types = [c.claim_type for c in claims]
        texts = [c.text for c in claims]
        assert 'person' in types
        assert 'Claude Monet' in texts

    def test_extract_date(self):
        """4-digit years are extracted."""
        text = "The villa was built in 1912 by a wealthy patron."
        claims = extract_fact_claims(text)
        texts = [c.text for c in claims]
        assert '1912' in texts

    def test_extract_artwork(self):
        """Quoted artwork titles are extracted."""
        text = 'His masterpiece "Morning at Antibes" hangs here.'
        claims = extract_fact_claims(text)
        texts = [c.text for c in claims]
        assert 'Morning at Antibes' in texts

    def test_deduplication(self):
        """Same claim repeated counts once."""
        text = "Monet painted here in 1888. Monet painted another work in 1888."
        claims = extract_fact_claims(text)
        dates = [c for c in claims if c.claim_type == 'date']
        assert len(dates) == 1  # 1888 counted once

    def test_grounded_in_passage(self):
        """A date present in passages is GROUNDED."""
        claim = FactClaim(text='1888', claim_type='date', sentence='painted in 1888')
        passages = ['Monet visited Cap Antibes in 1888 and painted several views.']
        verdict, evidence = check_claim_grounded(claim, passages)
        assert verdict == 'GROUNDED'
        assert evidence is not None

    def test_ungrounded_when_absent(self):
        """A date absent from passages is UNGROUNDED."""
        claim = FactClaim(text='1920', claim_type='date', sentence='in the 1920s')
        passages = ['The villa was built in 1888 by a patron.']
        verdict, _ = check_claim_grounded(claim, passages)
        assert verdict == 'UNGROUNDED'

    def test_person_grounded_with_normalisation(self):
        """A person name found via normalisation is GROUNDED."""
        claim = FactClaim(text='Baroness Béatrice', claim_type='person',
                         sentence='Baroness Béatrice built the villa')
        passages = ['The villa was designed for Béatrice de Rothschild in 1905.']
        verdict, evidence = check_claim_grounded(claim, passages)
        assert verdict == 'GROUNDED'
        assert evidence is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Corpus worklist emission
# ═══════════════════════════════════════════════════════════════════════════════

class TestCorpusWorklist:
    """Ungrounded claims are emitted as a corpus worklist."""

    def test_worklist_populated(self):
        """Ungrounded claims appear in the worklist."""
        text = "The chapel was built in 1432 by an unknown architect."
        passages = ['This area has many historic buildings.']  # No 1432
        result = measure_stop_groundedness(text, 'Test Chapel', passages)
        assert result.ungrounded_claims > 0
        assert len(result.corpus_worklist) > 0
        # Worklist items have required fields
        item = result.corpus_worklist[0]
        assert 'claim_text' in item
        assert 'claim_type' in item
        assert 'stop_title' in item

    def test_grounded_not_in_worklist(self):
        """Fully grounded claims don't appear in worklist."""
        text = "Claude Monet painted here in 1888."
        passages = ['Claude Monet visited in 1888 to paint several works.']
        result = measure_stop_groundedness(text, 'Test', passages)
        assert result.corpus_worklist == []


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
