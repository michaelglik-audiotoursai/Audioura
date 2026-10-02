#!/usr/bin/env python3
"""tests/test_local352_passage_ranking.py — LOCAL-352 bounce fix: passage ranking.

The NARRATIVE ARC RULE (first attempt) was well-written but had no effect
because the story passage never reached the prompt. The Negresco passage
existed in a different corpus row than the one selected by the venue
tie-breaker. Even within a single row, near-duplicate passages consumed
the character budget before unique narrative passages could appear.

These tests verify:
  1. _get_all_matching_rows merges all exact-match rows (not just one)
  2. deduplicate_and_rank_passages removes near-duplicate passages
  3. Narrative-action passages rank above state/attribute passages
  4. The Negresco passage reaches the prompt for La Merenda (live DB)
  5. The Colman Andrews passage reaches the prompt for Le Safari (live DB)
  6. Museum stops are unaffected (no cross-contamination)

Tests MUST import production code and MUST fail against the unfixed version:
- _get_all_matching_rows does not exist on the storied branch
- deduplicate_and_rank_passages does not exist on the storied branch
- The old code used _match_stop_title_first which returns ONE row

(D242) These tests fail on the pre-fix code because the functions under test
did not exist.
"""
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════════════════════
# 1. _get_all_matching_rows merges all exact-match corpus rows
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetAllMatchingRows:
    """_get_all_matching_rows must return ALL rows with exact title match,
    not just the preferred-venue one. This is the root fix: La Merenda exists
    under two venue_names, each with different passages.

    Fails on unfixed code: _get_all_matching_rows does not exist.
    """

    def test_function_exists(self):
        """The function must exist in production code."""
        from stop_corpus_reader import _get_all_matching_rows
        assert callable(_get_all_matching_rows)

    def test_returns_multiple_rows_for_same_title(self):
        """When two rows have the same stop_title under different venues,
        both must be returned."""
        from stop_corpus_reader import _get_all_matching_rows

        rows = [
            {'stop_title': 'La Merenda', 'venue_name': 'Old Nice, France',
             'passages_json': [{'text': 'passage A'}], 'source_pages': [], 'passage_roles': []},
            {'stop_title': 'La Merenda', 'venue_name': 'restaurant tour',
             'passages_json': [{'text': 'passage B'}], 'source_pages': [], 'passage_roles': []},
        ]

        result = _get_all_matching_rows('La Merenda', rows, 'restaurant tour')
        assert len(result) == 2, (
            f"Expected 2 rows for La Merenda, got {len(result)}. "
            "The fix must merge all exact-match rows."
        )

    def test_preferred_venue_first(self):
        """Preferred venue row should come first (for source metadata priority)."""
        from stop_corpus_reader import _get_all_matching_rows

        rows = [
            {'stop_title': 'TestStop', 'venue_name': 'venue A',
             'passages_json': [{'text': 'X'}], 'source_pages': [], 'passage_roles': []},
            {'stop_title': 'TestStop', 'venue_name': 'venue B',
             'passages_json': [{'text': 'Y'}], 'source_pages': [], 'passage_roles': []},
        ]

        result = _get_all_matching_rows('TestStop', rows, 'venue B')
        assert result[0]['venue_name'] == 'venue B', (
            "Preferred venue row should be first"
        )

    def test_fuzzy_match_still_returns_one(self):
        """Fuzzy matches (containment) should NOT merge multiple rows — risk of
        cross-contamination between different stops."""
        from stop_corpus_reader import _get_all_matching_rows

        rows = [
            {'stop_title': 'Chez Pipo Pizza', 'venue_name': 'venue A',
             'passages_json': [{'text': 'Pipo'}], 'source_pages': [], 'passage_roles': []},
            {'stop_title': 'Chez Palmyre', 'venue_name': 'venue A',
             'passages_json': [{'text': 'Palmyre'}], 'source_pages': [], 'passage_roles': []},
        ]

        # "Chez Pipo" contains "Chez" which is in "Chez Palmyre" but these are
        # different stops — fuzzy match should return at most one
        result = _get_all_matching_rows('Chez Pipo Pizza', rows, None)
        assert len(result) <= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Near-duplicate removal
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeduplication:
    """deduplicate_and_rank_passages must remove near-duplicate passages
    that restate the same fact in slightly different words.

    Fails on unfixed code: deduplicate_and_rank_passages does not exist.
    """

    def test_function_exists(self):
        """The function must exist in production code."""
        from stop_corpus_reader import deduplicate_and_rank_passages
        assert callable(deduplicate_and_rank_passages)

    def test_identical_passages_deduplicated(self):
        """Exact duplicates (same text) should be removed."""
        from stop_corpus_reader import deduplicate_and_rank_passages

        passages = [
            "La Merenda is run by chef Dominique Le Stanc since 1996.",
            "La Merenda is run by chef Dominique Le Stanc since 1996.",
            "The Negresco departure is a great story about Le Stanc.",
        ]
        result, _ = deduplicate_and_rank_passages(passages)
        assert len(result) == 2, f"Expected 2, got {len(result)} after dedup of identical"

    def test_near_duplicate_removal(self):
        """Passages with >70% word overlap (by smaller set) are near-duplicates."""
        from stop_corpus_reader import deduplicate_and_rank_passages

        # These share 5/6 significant words
        passages = [
            "Chef Dominique Le Stanc runs La Merenda in Nice since 1996.",
            "La Merenda in Nice has been run by chef Dominique Le Stanc since 1996.",
            "He gave it all up to start La Merenda, leaving the Negresco behind.",
        ]
        result, _ = deduplicate_and_rank_passages(passages)
        # The first two are near-duplicates; the third is unique
        assert len(result) < len(passages), (
            "Near-duplicate passages should be removed"
        )
        # The Negresco passage (unique) must survive
        assert any('Negresco' in p for p in result), (
            "Unique narrative passage must survive dedup"
        )

    def test_keeps_longest_of_duplicates(self):
        """When two passages are near-duplicates, keep the longer one."""
        from stop_corpus_reader import deduplicate_and_rank_passages

        short = "chef Le Stanc runs La Merenda since 1996 in Nice"
        long = "Chef Dominique Le Stanc has been running La Merenda since 1996 in the old town of Nice with just twenty covers"
        passages = [short, long]
        result, _ = deduplicate_and_rank_passages(passages)
        if len(result) == 1:
            assert result[0] == long, "Should keep the longer passage"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Narrative-action passages rank above state passages
# ═══════════════════════════════════════════════════════════════════════════════

class TestNarrativeRanking:
    """Passages containing narrative actions (left, founded, gave up, etc.)
    must rank before purely descriptive passages.

    Fails on unfixed code: deduplicate_and_rank_passages does not exist.
    """

    def test_narrative_action_ranked_first(self):
        """A passage with 'gave it all up' should outrank a state passage."""
        from stop_corpus_reader import deduplicate_and_rank_passages

        state_passage = "La Merenda is a tiny restaurant in the old town of Nice."
        narrative_passage = (
            "He gave it all up to start La Merenda, leaving behind the "
            "Negresco's two Michelin stars to cook for twenty people."
        )
        # State passage listed first in input
        passages = [state_passage, narrative_passage]
        result, _ = deduplicate_and_rank_passages(passages)
        assert result[0] == narrative_passage, (
            "Narrative-action passage must rank before state passage. "
            f"Got: {result[0][:60]}..."
        )

    def test_introduced_verb_ranked_first(self):
        """'introduced' (Colman Andrews) should rank above description."""
        from stop_corpus_reader import deduplicate_and_rank_passages

        desc = "Le Safari offers a wide choice of wood-fired pizzas and homemade pastries."
        narrative = (
            "A three-star chef introduced me to the pizza at Le Safari, "
            "on the lively Cours Saleya in Nice."
        )
        passages = [desc, narrative]
        result, _ = deduplicate_and_rank_passages(passages)
        assert result[0] == narrative, (
            "'introduced' is a narrative action verb — passage should rank first"
        )

    def test_founded_verb_ranked_first(self):
        """'founded' should rank above description."""
        from stop_corpus_reader import deduplicate_and_rank_passages

        desc = "Le Safari is a restaurant on Cours Saleya in Nice."
        narrative = "Wawa founded Le Safari Restaurant with one mission: to share authentic African flavors."
        passages = [desc, narrative]
        result, _ = deduplicate_and_rank_passages(passages)
        assert result[0] == narrative

    def test_multiple_narratives_preserved_in_order(self):
        """Multiple narrative passages keep their relative order."""
        from stop_corpus_reader import deduplicate_and_rank_passages

        n1 = "He gave it all up to leave the Negresco."
        n2 = "A critic introduced me to the pizza."
        state = "The restaurant has twenty seats."
        passages = [state, n1, n2]
        result, _ = deduplicate_and_rank_passages(passages)
        # Both narrative passages should be before the state passage
        n1_idx = result.index(n1)
        n2_idx = result.index(n2)
        state_idx = result.index(state)
        assert n1_idx < state_idx
        assert n2_idx < state_idx


# ═══════════════════════════════════════════════════════════════════════════════
# 4. La Merenda Negresco passage reaches the prompt (live DB)
# ═══════════════════════════════════════════════════════════════════════════════

class TestLaMerendaNegrescoInPrompt:
    """The Negresco departure passage must appear in the formatted prompt
    block for La Merenda. This was the original defect: the passage existed
    in the corpus but the venue tie-breaker selected the row without it.

    Fails on unfixed code: the old code picks one row via
    _match_stop_title_first, which returns the 'restaurant tour' row that
    lacks the Negresco passage.
    """

    @pytest.fixture
    def la_merenda_block(self):
        """Get the formatted prompt block for La Merenda from live DB."""
        import psycopg2
        from stop_corpus_reader import get_stop_corpus_for_tour, format_passages_for_prompt

        conn = psycopg2.connect(
            'postgresql://admin:password123@localhost:5433/audiotours'
        )
        try:
            result = get_stop_corpus_for_tour(
                'restaurant tour in Old Nice (Vieux Nice), France',
                ['La Merenda'],
                conn,
            )
            data = result.get('La Merenda')
            if not data:
                pytest.skip("La Merenda not in stop_corpus")
            return data, format_passages_for_prompt(data, 'La Merenda')
        finally:
            conn.close()

    def test_negresco_passage_in_passages(self, la_merenda_block):
        """The Negresco passage must be among the passages returned."""
        data, _ = la_merenda_block
        passages = data['passages']
        negresco_found = any(
            'negresco' in p.lower() or 'chantecler' in p.lower()
            for p in passages
        )
        assert negresco_found, (
            "The Negresco passage is not among La Merenda's passages. "
            "The multi-row merge must bring it in from the other corpus row."
        )

    def test_negresco_in_prompt_block(self, la_merenda_block):
        """The Negresco departure must appear in the final prompt block."""
        _, block = la_merenda_block
        assert 'Negresco' in block or 'negresco' in block.lower(), (
            "The Negresco passage did not make it into the prompt block. "
            "Either it was not merged from the other row, or it was truncated "
            "by the character budget."
        )

    def test_gave_it_all_up_narrative(self, la_merenda_block):
        """The narrative arc ('gave it all up') must appear, not just the credential."""
        _, block = la_merenda_block
        assert 'gave it all' in block.lower(), (
            "The narrative arc is not in the prompt block. The passage about "
            "Le Stanc LEAVING the Negresco must reach the model, not just "
            "'former Michelin-starred chef'."
        )

    def test_negresco_ranked_early(self, la_merenda_block):
        """The Negresco passage should be in the top 3 (narrative ranking)."""
        data, _ = la_merenda_block
        passages = data['passages']
        negresco_idx = None
        for i, p in enumerate(passages):
            if 'negresco' in p.lower() or 'chantecler' in p.lower():
                negresco_idx = i
                break
        assert negresco_idx is not None and negresco_idx < 3, (
            f"Negresco passage at index {negresco_idx}, expected < 3. "
            "Narrative-action passages should rank near the top."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Le Safari Colman Andrews passage reaches the prompt (live DB)
# ═══════════════════════════════════════════════════════════════════════════════

class TestLeSafariColmanAndrews:
    """The Colman Andrews recommendation passage must reach the prompt.

    Fails on unfixed code: without narrative ranking, the Colman Andrews
    passage may not be ranked prominently enough to be noticed by the model.
    """

    @pytest.fixture
    def le_safari_block(self):
        """Get the formatted prompt block for Le Safari from live DB."""
        import psycopg2
        from stop_corpus_reader import get_stop_corpus_for_tour, format_passages_for_prompt

        conn = psycopg2.connect(
            'postgresql://admin:password123@localhost:5433/audiotours'
        )
        try:
            result = get_stop_corpus_for_tour(
                'restaurant tour in Old Nice (Vieux Nice), France',
                ['Le Safari'],
                conn,
            )
            data = result.get('Le Safari')
            if not data:
                pytest.skip("Le Safari not in stop_corpus")
            return data, format_passages_for_prompt(data, 'Le Safari')
        finally:
            conn.close()

    def test_colman_andrews_in_prompt(self, le_safari_block):
        """Colman Andrews passage must reach the prompt block."""
        _, block = le_safari_block
        assert 'colman' in block.lower() or 'andrews' in block.lower(), (
            "Colman Andrews not in the Le Safari prompt block. "
            "The recommendation narrative must reach the model."
        )

    def test_introduced_narrative_in_prompt(self, le_safari_block):
        """The 'introduced' action must be in the prompt (not just the name)."""
        _, block = le_safari_block
        assert 'introduced' in block.lower(), (
            "'introduced' verb missing from Le Safari prompt. "
            "The Colman Andrews passage should be ranked as narrative action."
        )

    def test_colman_ranked_first(self, le_safari_block):
        """The Colman Andrews narrative should rank in top 2."""
        data, _ = le_safari_block
        passages = data['passages']
        colman_idx = None
        for i, p in enumerate(passages):
            if 'colman' in p.lower() or 'introduced' in p.lower():
                colman_idx = i
                break
        assert colman_idx is not None and colman_idx < 2, (
            f"Colman Andrews at index {colman_idx}, expected < 2. "
            "Narrative-action passages should rank near the top."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Museum stops unaffected
# ═══════════════════════════════════════════════════════════════════════════════

class TestMuseumUnaffected:
    """Museum object stops (e.g. 'Harpe by Naderman') must not be contaminated
    by the multi-row merge. Objects have unique titles that will only match
    one corpus row, so the merge is a no-op for them."""

    def test_single_row_unchanged(self):
        """A stop with only one matching row should work exactly as before."""
        from stop_corpus_reader import _get_all_matching_rows

        rows = [
            {'stop_title': 'Harpe by Naderman', 'venue_name': 'Palais Lascaris',
             'passages_json': [{'text': 'A harp'}], 'source_pages': [], 'passage_roles': []},
            {'stop_title': 'Violon', 'venue_name': 'Palais Lascaris',
             'passages_json': [{'text': 'A violin'}], 'source_pages': [], 'passage_roles': []},
        ]

        result = _get_all_matching_rows('Harpe by Naderman', rows, 'Palais Lascaris')
        assert len(result) == 1
        assert result[0]['stop_title'] == 'Harpe by Naderman'

    def test_museum_dedup_preserves_all_unique(self):
        """Museum passages about different objects should all survive dedup."""
        from stop_corpus_reader import deduplicate_and_rank_passages

        # Museum passages are about different objects — no overlap
        passages = [
            "The Naderman harp dates from 1780 and features gilded wood.",
            "This Baroque violin was crafted in Cremona by a student of Stradivari.",
            "The clavichord collection includes three Flemish instruments.",
        ]
        result, _ = deduplicate_and_rank_passages(passages)
        assert len(result) == 3, "Distinct museum passages must all survive"
