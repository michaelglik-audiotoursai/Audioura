#!/usr/bin/env python3
"""tests/test_local340_groundedness_misattribution.py — LOCAL-340

Tests that the groundedness measurement correctly isolates per-stop corpus:
a claim must be grounded against its OWN stop's corpus, not a neighbouring
stop with a similar name.

The defect: "Chez Pipo" (stop 4 in the restaurant tour) was being grounded
against "Chez Palmyre" corpus because the word-overlap matcher treated "chez"
(4 chars >= threshold) as sufficient to cross-match. With Palmyre's corpus
saying "established 1926", the prose's fabricated "1926" was marked GROUNDED.

Fix: exact/accent-folded title matches take strict priority over fuzzy
word-overlap matches in _match_stop_title_first.

Second defect: the 1926/1923 contradiction was not detected because the
claim sentence "Established in 1926..." starts with a verb, producing an
empty subject phrase. Fix: when subject extraction yields nothing, the
stop_title is used as a fallback subject for same-subject matching.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Corpus matching: exact title match must beat fuzzy word overlap
# ═══════════════════════════════════════════════════════════════════════════════

class TestCorpusMatchingPriority:
    """Exact title match always wins over word-overlap match."""

    @pytest.fixture
    def db_connection(self):
        from tests.db_connection import get_connection, check_db_available
        if not check_db_available():
            pytest.skip("Database unavailable")
        # These tests require production data (stop_corpus rows)
        old_target = os.environ.get('AUDIOURA_DB_TARGET')
        os.environ['AUDIOURA_DB_TARGET'] = 'production'
        try:
            conn = get_connection()
            # Verify the corpus data exists
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM stop_corpus WHERE stop_title = 'Chez Pipo'")
            count = cur.fetchone()[0]
            cur.close()
            if count == 0:
                conn.close()
                pytest.skip("Chez Pipo corpus not in database")
            yield conn
            conn.close()
        finally:
            if old_target is None:
                os.environ.pop('AUDIOURA_DB_TARGET', None)
            else:
                os.environ['AUDIOURA_DB_TARGET'] = old_target

    def test_chez_pipo_not_matched_to_chez_palmyre(self, db_connection):
        """Chez Pipo corpus must contain Pipo passages, not Palmyre passages.

        This was the root cause: word-overlap (shared 'chez') plus venue
        preference made Palmyre's corpus win the match for Pipo.
        """
        from stop_corpus_reader import get_stop_corpus_for_tour

        result = get_stop_corpus_for_tour(
            'restaurant tour in Old Nice (Vieux Nice), France',
            ['Chez Pipo'],
            db_connection,
        )
        entry = result.get('Chez Pipo')
        assert entry is not None, "Chez Pipo should have corpus"
        passages_text = ' '.join(entry['passages']).lower()

        # The passages must contain "chez pipo" (its own corpus)
        assert 'chez pipo' in passages_text, (
            "Chez Pipo's corpus should mention Chez Pipo itself"
        )
        # The passages must NOT be primarily about Chez Palmyre
        # (Palmyre may appear incidentally in Pipo passages, but 'palmyre'
        # should not dominate — Pipo's corpus talks about socca, 1923, etc.)
        assert passages_text.count('chez pipo') > passages_text.count('chez palmyre'), (
            "Chez Pipo's corpus should mention Pipo more than Palmyre"
        )

    def test_chez_pipo_corpus_says_1923_not_1926(self, db_connection):
        """Chez Pipo's own corpus says 1923, not 1926."""
        from stop_corpus_reader import get_stop_corpus_for_tour

        result = get_stop_corpus_for_tour(
            'restaurant tour in Old Nice (Vieux Nice), France',
            ['Chez Pipo'],
            db_connection,
        )
        entry = result.get('Chez Pipo')
        passages_text = ' '.join(entry['passages'])

        assert '1923' in passages_text, "Chez Pipo corpus should contain 1923"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Groundedness: a fabricated date is not grounded
# ═══════════════════════════════════════════════════════════════════════════════

class TestGroundednessNotOneForFabricatedDate:
    """Stop with fabricated date must NOT report groundedness 1.00."""

    @pytest.fixture
    def db_connection(self):
        from tests.db_connection import get_connection, check_db_available
        if not check_db_available():
            pytest.skip("Database unavailable")
        old_target = os.environ.get('AUDIOURA_DB_TARGET')
        os.environ['AUDIOURA_DB_TARGET'] = 'production'
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM stop_corpus WHERE stop_title = 'Chez Pipo'")
            count = cur.fetchone()[0]
            cur.close()
            if count == 0:
                conn.close()
                pytest.skip("Chez Pipo corpus not in database")
            yield conn
            conn.close()
        finally:
            if old_target is None:
                os.environ.pop('AUDIOURA_DB_TARGET', None)
            else:
                os.environ['AUDIOURA_DB_TARGET'] = old_target

    def test_1926_not_grounded_against_pipo_corpus(self, db_connection):
        """The claim '1926' must be UNGROUNDED when corpus says 1923."""
        from stop_corpus_reader import get_stop_corpus_for_tour
        from groundedness_check import measure_stop_groundedness

        result_corpus = get_stop_corpus_for_tour(
            'restaurant tour in Old Nice (Vieux Nice), France',
            ['Chez Pipo'],
            db_connection,
        )
        passages = result_corpus['Chez Pipo']['passages']

        stop_text = (
            'Chez Pipo. Established in 1926 as Chez Palmyre by Palmyre Moni, '
            'the founder from Tuscany, this socca institution has been serving '
            'the signature chickpea flatbread that defines Nice culinary identity.'
        )
        result = measure_stop_groundedness(stop_text, 'Chez Pipo', passages)

        # Groundedness must NOT be 1.00 — at minimum "1926" is ungrounded
        assert result.groundedness_fraction < 1.0, (
            f"Groundedness should not be 1.00 when 1926 is fabricated "
            f"(corpus says 1923). Got {result.groundedness_fraction}"
        )

    def test_palmyre_moni_not_grounded(self, db_connection):
        """'Palmyre Moni' must be UNGROUNDED — doesn't appear in Pipo corpus."""
        from stop_corpus_reader import get_stop_corpus_for_tour
        from groundedness_check import measure_stop_groundedness

        result_corpus = get_stop_corpus_for_tour(
            'restaurant tour in Old Nice (Vieux Nice), France',
            ['Chez Pipo'],
            db_connection,
        )
        passages = result_corpus['Chez Pipo']['passages']

        stop_text = (
            'Established in 1926 as Chez Palmyre by Palmyre Moni, '
            'the founder from Tuscany.'
        )
        result = measure_stop_groundedness(stop_text, 'Chez Pipo', passages)

        # Check that Palmyre Moni is ungrounded
        moni_claim = next(
            (d for d in result.claims_detail if 'Palmyre Moni' in d.get('text', '')),
            None
        )
        if moni_claim:
            assert moni_claim['verdict'] == 'UNGROUNDED', (
                f"'Palmyre Moni' should be UNGROUNDED in Chez Pipo corpus, "
                f"got {moni_claim['verdict']}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Contradiction detection: 1926 vs 1923 must fire CONTRADICTED
# ═══════════════════════════════════════════════════════════════════════════════

class TestContradictionDetection:
    """A date contradicted by stop's own corpus must be flagged."""

    @pytest.fixture
    def db_connection(self):
        from tests.db_connection import get_connection, check_db_available
        if not check_db_available():
            pytest.skip("Database unavailable")
        old_target = os.environ.get('AUDIOURA_DB_TARGET')
        os.environ['AUDIOURA_DB_TARGET'] = 'production'
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM stop_corpus WHERE stop_title = 'Chez Pipo'")
            count = cur.fetchone()[0]
            cur.close()
            if count == 0:
                conn.close()
                pytest.skip("Chez Pipo corpus not in database")
            yield conn
            conn.close()
        finally:
            if old_target is None:
                os.environ.pop('AUDIOURA_DB_TARGET', None)
            else:
                os.environ['AUDIOURA_DB_TARGET'] = old_target

    def test_1926_contradicted_by_corpus_1923(self, db_connection):
        """claim_check must detect 1926 as CONTRADICTED when corpus says 1923.

        The sentence 'Established in 1926...' starts with a verb, so subject
        extraction yields nothing. The fix uses stop_title='Chez Pipo' as
        fallback subject, which matches passages mentioning 'Chez Pipo...
        founded in 1923'.
        """
        from stop_corpus_reader import get_stop_corpus_for_tour
        from claim_check import check_paragraph, CONTRADICTED

        result_corpus = get_stop_corpus_for_tour(
            'restaurant tour in Old Nice (Vieux Nice), France',
            ['Chez Pipo'],
            db_connection,
        )
        passages = result_corpus['Chez Pipo']['passages']

        stop_text = (
            'Established in 1926 as Chez Palmyre by Palmyre Moni, '
            'the founder from Tuscany, this socca institution has been serving '
            'the signature chickpea flatbread that defines Nice culinary identity.'
        )
        result = check_paragraph(
            text=stop_text,
            stop_title='Chez Pipo',
            venue_name='',
            passages=passages,
        )
        assert result['verdict_counts']['contradicted'] > 0, (
            f"Expected CONTRADICTED for 1926 (corpus says 1923). "
            f"Got verdicts: {result['verdict_counts']}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Unit test: _match_stop_title_first prioritises exact over fuzzy
# ═══════════════════════════════════════════════════════════════════════════════

class TestMatchStopTitleFirstPriority:
    """Unit test for the tiered matching fix."""

    def test_exact_beats_fuzzy_even_when_fuzzy_has_preferred_venue(self):
        """An exact title match must win even if a fuzzy match has the
        preferred venue."""
        from stop_corpus_reader import _match_stop_title_first

        # Simulate: 'Chez Pipo' exact match under venue A,
        # 'Chez Palmyre' fuzzy match under preferred venue B
        corpus_rows = [
            {'stop_title': 'Chez Palmyre', 'venue_name': 'preferred_venue',
             'passages_json': '[1,2,3,4,5]'},
            {'stop_title': 'Chez Pipo', 'venue_name': 'other_venue',
             'passages_json': '[1,2,3]'},
        ]
        # Preferred venue matches Palmyre (fuzzy), not Pipo (exact)
        result = _match_stop_title_first('Chez Pipo', corpus_rows, 'preferred_venue')

        assert result is not None
        assert result['stop_title'] == 'Chez Pipo', (
            f"Expected 'Chez Pipo' (exact match) but got '{result['stop_title']}'"
        )

    def test_fuzzy_used_when_no_exact(self):
        """When no exact match exists, fuzzy matches are still used."""
        from stop_corpus_reader import _match_stop_title_first

        # Only a containment match available
        corpus_rows = [
            {'stop_title': 'Old Town of Nice and Port Area',
             'venue_name': 'Nice', 'passages_json': '[1,2]'},
        ]
        result = _match_stop_title_first('Old Town of Nice', corpus_rows, 'Nice')
        assert result is not None
        assert result['stop_title'] == 'Old Town of Nice and Port Area'
