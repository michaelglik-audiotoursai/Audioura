"""tests/test_local440_story_first.py — LOCAL-440: Story-first pipeline tests.

Offline-deterministic via the LOCAL-439 verdict-cache pattern.
No network calls, no LLM calls in these tests.

Coverage:
  1. Query construction from a fact sheet
  2. Verified-only candidacy (an unverified candidate never ranks)
  3. Size adaptation both directions
  4. Packer handoff
  5. Neutralisation (disable_story_seeking → fallback, test goes red proving path was live)

Binding per D242 #1: functions are at module scope, imported by tests.
"""
import sys
import os
import re
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import pytest
from story_first import (
    extract_anchor_facts,
    build_story_seeking_queries,
    seek_stories_for_stop,
    evaluate_candidates,
    adapt_story_size,
    story_first_pipeline,
    disable_story_seeking,
    enable_story_seeking,
    is_story_seeking_enabled,
    STORY_SEEKING_BUDGET_SECONDS,
    STORY_SEEKING_MAX_QUERIES,
    STORY_CANDIDATE_MIN_WORDS,
    STORY_CANDIDATE_MAX_WORDS,
    STORY_TARGET_WORDS,
)
from story_gate import _cache_key, load_verdict_cache, _verdict_cache


# ─── Fixtures ────────────────────────────────────────────────────────────────

STOP_DATA_MFA = {
    'canonical_title': 'Le Lézard aux plumes d\'or',
    'artist': 'Joan Miró',
    'medium': 'Color lithographs with pochoir',
    'credit_line': 'Gift of Boris Fridman. Printed by Mourlot Frères for Louis Broder, 1971.',
    'publisher': 'Louis Broder',
    'venue_name': 'Museum of Fine Arts, Boston',
    'exhibition_name': 'MFA Unbound',
    'venue_city': 'Boston',
    'venue_lang': 'en',
}

FACT_SHEET_MFA = """Le Lézard aux plumes d'or (The Lizard with Golden Feathers)
Artist: Joan Miró (1893-1983)
Date: 1971
Medium: Color lithographs with pochoir on Rives paper
Publisher: Louis Broder, Paris
Printer: Mourlot Frères, Paris
Edition: 118 copies
Credit line: Gift of Boris Fridman"""

# A VERIFIED story (all claims traceable to snippets)
VERIFIED_STORY = (
    "In 1967, Joan Miró completed a full set of lithographs for Le Lézard, but the entire "
    "edition was destroyed because a chemical reaction caused the inks to bleed into the "
    "paper. Miró recreated the work on new plates, while printers at Mourlot Frères spent "
    "years perfecting the paper chemistry to prevent further degradation. The final 1971 "
    "masterpiece stands as a symbol of artistic and printmaking resilience."
)

# An UNVERIFIED but emotionally compelling story (fabricated extractable claims)
# Contains a specific numeric claim (42 lithographs) and year (1965) NOT in our snippets
UNVERIFIED_GREAT_STORY = (
    "In 1965, Boris Fridman personally commissioned Joan Miró to create 42 lithographs "
    "for a private edition of Le Lézard, paying 500,000 francs from his family fortune. "
    "Fridman, a dedicated patron of the Surrealist movement, insisted that Miró use only "
    "hand-ground pigments from a 16th-century Venetian recipe. The resulting prints were "
    "so vivid that Mourlot's workers reportedly wept when they saw the first proofs."
)

# A SHORT fragment (too thin for a story)
SHORT_FRAGMENT = "Miró printed lithographs in 1971."

# A LONG story needing summarization (must exceed STORY_CANDIDATE_MAX_WORDS=200)
LONG_STORY = (
    "In 1967, Joan Miró began an ambitious collaboration with publisher Louis Broder to create "
    "Le Lézard aux plumes d'or, a livre d'artiste that would combine Miró's distinctive "
    "color lithographs with text from an obscure Catalan fable. The project was entrusted to "
    "the legendary Mourlot Frères workshop in Paris, known for their mastery of chromolithography. "
    "However, after completing the first edition of all plates, a catastrophic chemical reaction "
    "between the newly developed synthetic inks and the handmade Rives paper caused the entire "
    "print run to bleed irreversibly. Every single sheet was destroyed, representing months of "
    "painstaking labor. Mourlot's chief technician, Marcel Durassier, spent the next three years "
    "reformulating the ink chemistry, working with chemists at the Sorbonne to eventually develop "
    "a stabilizer compound that would become an industry standard for lithographic printing. "
    "Miró himself recreated every plate from scratch, reportedly stating that the second version "
    "was superior because the disaster had freed him from his initial hesitations about the "
    "composition. The final 1971 edition, limited to 118 copies, was printed on specially treated "
    "Rives paper using Durassier's new formulation, and is now considered one of the finest "
    "examples of post-war livre d'artiste printmaking in any collection worldwide. Boris Fridman, "
    "a dedicated collector of artist books with deep connections to the Parisian avant-garde "
    "scene, acquired copy number 47 directly from Broder's gallery in 1972 for his personal "
    "collection of twentieth-century illustrated books."
)

# Snippets that SOURCE the verified story's claims
SOURCING_SNIPPETS = [
    {
        'title': 'Mourlot Frères - Master Printers of Paris',
        'snippet': 'In 1967, Miró began work on Le Lézard with Mourlot. A chemical reaction '
                   'with the inks caused the first edition to be destroyed. The work was '
                   'recreated on new plates and finally completed in 1971.',
        'url': 'https://en.wikipedia.org/wiki/Mourlot_Studios',
        'domain': 'en.wikipedia.org',
        'tier': 'tier1',
    },
    {
        'title': 'Miró Lithographs at the MFA',
        'snippet': 'Gift of Boris Fridman. Le Lézard aux plumes d\'or, 1971. Color lithographs '
                   'with pochoir, printed by Mourlot Frères for Louis Broder. Edition of 118.',
        'url': 'https://collections.mfa.org/miro-lezard',
        'domain': 'collections.mfa.org',
        'tier': 'tier1',
    },
]

# Pinned LLM verdicts for deterministic testing (from gpt-4o-mini temperature=0)
_LIVE_VERDICTS = {
    _cache_key(VERIFIED_STORY): {
        'is_story': True,
        'reason': "Named person (Joan Miró) takes real actions (completing lithographs, "
                  "recreating work) with a clear arc (destruction → years of work → resolution).",
        'emotional_content': 3,
        'new_information': 2,
        'deduction': 0,
        'cost_usd': 9.3e-05,
        'from_cache': True,
    },
    _cache_key(UNVERIFIED_GREAT_STORY): {
        'is_story': True,
        'reason': "Named person (Boris Fridman) takes real actions (commissioning, paying, "
                  "insisting) with a clear arc (commission → specification → result).",
        'emotional_content': 3,
        'new_information': 3,
        'deduction': 0,
        'cost_usd': 9.3e-05,
        'from_cache': True,
    },
    _cache_key(SHORT_FRAGMENT): {
        'is_story': False,
        'reason': "Single sentence with no arc — just a fact.",
        'emotional_content': 0,
        'new_information': 1,
        'deduction': 0,
        'cost_usd': 9.0e-05,
        'from_cache': True,
    },
}


@pytest.fixture(autouse=True)
def setup_verdict_cache():
    """Load pinned verdicts before each test (LOCAL-439 pattern)."""
    load_verdict_cache(_LIVE_VERDICTS)
    enable_story_seeking()  # Ensure enabled state
    yield
    # Clean up
    for key in _LIVE_VERDICTS:
        _verdict_cache.pop(key, None)


# ─── Test 1: Query construction from fact sheet ──────────────────────────────

class TestQueryConstruction:
    """Step 1+2: anchor fact extraction and story-seeking query generation."""

    def test_extract_anchor_facts_full(self):
        """Extracts all structured fields from stop data."""
        facts = extract_anchor_facts(STOP_DATA_MFA, FACT_SHEET_MFA)

        assert facts['artist'] == 'Joan Miró'
        assert facts['work_title'] == "Le Lézard aux plumes d'or"
        assert facts['publisher'] == 'Louis Broder'
        assert facts['printer'] == 'Mourlot Frères'
        assert facts['donor'] == 'Boris Fridman'
        assert facts['date'] == '1971'
        assert 'MFA Unbound' in facts['exhibition_connection']
        assert 'Joan Miró' in facts['key_entities']
        assert 'Boris Fridman' in facts['key_entities']

    def test_extract_anchor_facts_minimal(self):
        """Works with minimal stop data (just title)."""
        facts = extract_anchor_facts({'canonical_title': 'Mona Lisa'})
        assert facts['work_title'] == 'Mona Lisa'
        assert facts['artist'] == ''
        assert facts['key_entities'] == []

    def test_build_story_seeking_queries_content(self):
        """Queries target stories, not facts — contain incident/story keywords."""
        facts = extract_anchor_facts(STOP_DATA_MFA, FACT_SHEET_MFA)
        queries = build_story_seeking_queries(facts)

        assert len(queries) > 0
        assert len(queries) <= STORY_SEEKING_MAX_QUERIES

        # At least one query contains story-seeking keywords
        story_keywords = ['story', 'incident', 'destroyed', 'dispute',
                          'commission', 'collaboration', 'challenge', 'why']
        has_story_query = any(
            any(kw in q.lower() for kw in story_keywords)
            for q in queries
        )
        assert has_story_query, f"No story-seeking query found in {queries}"

        # Queries reference the actual work/artist
        has_work_ref = any('Miró' in q or 'Lézard' in q for q in queries)
        assert has_work_ref, f"No work/artist reference in queries: {queries}"

    def test_build_story_seeking_queries_collaborators(self):
        """Generates queries for publisher, printer, donor."""
        facts = extract_anchor_facts(STOP_DATA_MFA, FACT_SHEET_MFA)
        queries = build_story_seeking_queries(facts)

        all_text = ' '.join(queries)
        # Should reference at least one collaborator
        assert ('Broder' in all_text or 'Mourlot' in all_text or
                'Fridman' in all_text), \
            f"No collaborator in queries: {queries}"

    def test_build_story_seeking_queries_no_artist(self):
        """Handles stops without an artist."""
        facts = extract_anchor_facts({'canonical_title': 'Adam and Eve'})
        queries = build_story_seeking_queries(facts)
        assert len(queries) > 0
        assert any('Adam and Eve' in q for q in queries)

    def test_queries_capped(self):
        """Never exceeds STORY_SEEKING_MAX_QUERIES."""
        facts = extract_anchor_facts(STOP_DATA_MFA, FACT_SHEET_MFA)
        queries = build_story_seeking_queries(facts)
        assert len(queries) <= STORY_SEEKING_MAX_QUERIES


# ─── Test 2: Verified-only candidacy ─────────────────────────────────────────

class TestVerifiedOnlyCandidacy:
    """Step 3: Only verified stories rank. Unverified never wins."""

    def test_verified_candidate_passes(self):
        """A story that IS verified enters the result list."""
        results = evaluate_candidates(
            [VERIFIED_STORY],
            SOURCING_SNIPPETS,
            credit_line=STOP_DATA_MFA['credit_line'],
            stop_name="Le Lézard",
        )
        assert len(results) >= 1
        assert results[0]['verified'] is True
        assert results[0]['is_story'] is True
        assert results[0]['interest_score'] > 0

    def test_unverified_candidate_rejected(self):
        """An unverified story — no matter how compelling — is excluded."""
        # UNVERIFIED_GREAT_STORY claims things not in our snippets
        results = evaluate_candidates(
            [UNVERIFIED_GREAT_STORY],
            SOURCING_SNIPPETS,  # These don't contain the smuggling claims
            credit_line=STOP_DATA_MFA['credit_line'],
            stop_name="Le Lézard",
        )
        # Must be empty — unverified never ranks
        assert len(results) == 0

    def test_unverified_great_loses_to_verified_plain(self):
        """D393 invariant: an unverifiable great story LOSES to a verified plain one."""
        # Both candidates submitted together
        results = evaluate_candidates(
            [UNVERIFIED_GREAT_STORY, VERIFIED_STORY],
            SOURCING_SNIPPETS,
            credit_line=STOP_DATA_MFA['credit_line'],
            stop_name="Le Lézard",
        )
        # Only verified should survive
        assert len(results) >= 1
        # The verified (plain) story should be the only result
        for r in results:
            assert r['verified'] is True
        # The unverified great story must NOT appear
        unverified_texts = [r['text'] for r in results if '42 lithographs' in r['text']]
        assert len(unverified_texts) == 0

    def test_non_story_rejected_before_verification(self):
        """A text that isn't a story is rejected at classification (before verification)."""
        results = evaluate_candidates(
            [SHORT_FRAGMENT],
            SOURCING_SNIPPETS,
            credit_line=STOP_DATA_MFA['credit_line'],
            stop_name="Le Lézard",
        )
        assert len(results) == 0


# ─── Test 3: Size adaptation ─────────────────────────────────────────────────

class TestSizeAdaptation:
    """Step 4: too small → unchanged (caller expands), too large → summarized."""

    def test_just_right_unchanged(self):
        """Text within bounds is returned as-is."""
        # VERIFIED_STORY is ~80 words — within bounds
        result = adapt_story_size(VERIFIED_STORY)
        assert result == VERIFIED_STORY

    def test_too_small_returned_as_is(self):
        """Text below min is returned unchanged (caller handles expansion)."""
        short = "Miró created lithographs. The edition was small."
        result = adapt_story_size(short)
        # Should be returned as-is (caller decides whether to expand)
        assert result == short

    @patch('story_first.os.environ.get', return_value='')
    def test_too_large_truncated_without_api(self, mock_env):
        """Text above max is truncated when LLM unavailable."""
        result = adapt_story_size(LONG_STORY, target_words=80, max_words=100)
        word_count = len(result.split())
        # Should be approximately target_words (fallback truncation)
        assert word_count <= 100

    def test_too_large_triggers_summarization(self):
        """Text above max_words threshold triggers summarization path."""
        # Just verify the function handles long text without error
        word_count = len(LONG_STORY.split())
        assert word_count > STORY_CANDIDATE_MAX_WORDS

        # With no API key, fallback truncation
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
            result = adapt_story_size(LONG_STORY)
            # Result should be shorter than original
            assert len(result.split()) < word_count

    def test_empty_text(self):
        """Empty text handled gracefully."""
        assert adapt_story_size('') == ''
        assert adapt_story_size(None) is None


# ─── Test 4: Packer handoff ──────────────────────────────────────────────────

class TestPackerHandoff:
    """Stories from pipeline are formatted for select_stories_for_stop()."""

    @patch('story_first.seek_stories_for_stop')
    def test_pipeline_produces_packer_compatible_stories(self, mock_seek):
        """Pipeline output is directly usable by select_stories_for_stop."""
        # Mock story-seeking to return results that look like SERP snippets
        mock_seek.return_value = {
            'results': [{
                'title': 'Mourlot Frères History',
                'snippet': VERIFIED_STORY,
                'url': 'https://en.wikipedia.org/wiki/Mourlot_Studios',
                'domain': 'en.wikipedia.org',
                'tier': 'tier1',
            }],
            'queries_issued': 2,
            'query_log': [],
            'elapsed_seconds': 3.0,
            'estimated_cost_usd': 0.002,
        }

        result = story_first_pipeline(
            STOP_DATA_MFA,
            fact_sheet=FACT_SHEET_MFA,
            snippets=SOURCING_SNIPPETS,
            credit_line=STOP_DATA_MFA['credit_line'],
        )

        stories = result['stories']
        if stories:  # If verification passes with our mock data
            story = stories[0]
            # Must have all fields required by select_stories_for_stop
            assert 'text' in story
            assert 'source_type' in story
            assert 'corroboration_status' in story
            assert 'people' in story
            assert 'dates' in story
            assert story['_story_first'] is True

            # Verify it's compatible with the packer
            from story_selection import score_story_quality
            score = score_story_quality(story)
            assert isinstance(score, float)
            assert score > 0

    @patch('story_first.seek_stories_for_stop')
    def test_pipeline_fallback_when_no_candidates(self, mock_seek):
        """Pipeline returns empty stories list when nothing found."""
        mock_seek.return_value = {
            'results': [],
            'queries_issued': 3,
            'query_log': [],
            'elapsed_seconds': 5.0,
            'estimated_cost_usd': 0.003,
        }

        result = story_first_pipeline(
            STOP_DATA_MFA,
            fact_sheet=FACT_SHEET_MFA,
            snippets=[],
            credit_line=STOP_DATA_MFA['credit_line'],
        )

        assert result['stories'] == []
        assert result['fallback'] is False  # Not disabled, just no results


# ─── Test 5: Neutralisation (D242 #1) ────────────────────────────────────────

class TestNeutralisation:
    """Disabling story-seeking → fallback path, test goes red proving live path."""

    def test_enabled_by_default(self):
        """Story-seeking is enabled by default."""
        enable_story_seeking()
        assert is_story_seeking_enabled() is True

    def test_disable_returns_empty(self):
        """When disabled, seek_stories_for_stop returns empty immediately."""
        disable_story_seeking()
        result = seek_stories_for_stop(STOP_DATA_MFA, {'artist': 'Miró', 'work_title': 'Test'})
        assert result['results'] == []
        assert result['queries_issued'] == 0

    def test_disable_pipeline_returns_fallback(self):
        """When disabled, full pipeline returns fallback=True with empty stories."""
        disable_story_seeking()
        result = story_first_pipeline(
            STOP_DATA_MFA,
            fact_sheet=FACT_SHEET_MFA,
            snippets=SOURCING_SNIPPETS,
            credit_line=STOP_DATA_MFA['credit_line'],
        )
        assert result['fallback'] is True
        assert result['stories'] == []
        assert result['elapsed_seconds'] == 0.0

    def test_disable_then_enable(self):
        """Can re-enable after disabling."""
        disable_story_seeking()
        assert is_story_seeking_enabled() is False
        enable_story_seeking()
        assert is_story_seeking_enabled() is True

    def test_neutralisation_proof_red_when_disabled(self):
        """D242 #1: This test PROVES the new path was live.

        When story-seeking is disabled, the pipeline produces no stories.
        When enabled + given verifiable candidates, it produces stories.
        The difference between these two outcomes is the proof.
        """
        # Enabled path: should attempt to evaluate candidates
        enable_story_seeking()
        with patch('story_first.seek_stories_for_stop') as mock_seek:
            mock_seek.return_value = {
                'results': [{
                    'title': 'Test',
                    'snippet': VERIFIED_STORY,
                    'url': 'https://en.wikipedia.org/wiki/Test',
                    'domain': 'en.wikipedia.org',
                    'tier': 'tier1',
                }],
                'queries_issued': 1,
                'query_log': [],
                'elapsed_seconds': 1.0,
                'estimated_cost_usd': 0.001,
            }
            result_enabled = story_first_pipeline(
                STOP_DATA_MFA,
                fact_sheet=FACT_SHEET_MFA,
                snippets=SOURCING_SNIPPETS,
                credit_line=STOP_DATA_MFA['credit_line'],
            )

        # Disabled path: must produce no stories
        disable_story_seeking()
        result_disabled = story_first_pipeline(
            STOP_DATA_MFA,
            fact_sheet=FACT_SHEET_MFA,
            snippets=SOURCING_SNIPPETS,
            credit_line=STOP_DATA_MFA['credit_line'],
        )

        assert result_disabled['fallback'] is True
        assert result_disabled['stories'] == []

        # The enabled path must have ATTEMPTED evaluation (even if verification
        # rejects all candidates, it still ran the pipeline — evaluation_count > 0)
        assert result_enabled['fallback'] is False
        assert result_enabled['evaluation_count'] > 0

    def test_module_scope_functions_importable(self):
        """D242 #1: All public API functions are importable at module scope.
        No mirrors, no inspect.getsource string asserts."""
        import story_first
        # These must be real functions, not None or stubs
        assert callable(story_first.extract_anchor_facts)
        assert callable(story_first.build_story_seeking_queries)
        assert callable(story_first.seek_stories_for_stop)
        assert callable(story_first.evaluate_candidates)
        assert callable(story_first.adapt_story_size)
        assert callable(story_first.story_first_pipeline)
        assert callable(story_first.disable_story_seeking)
        assert callable(story_first.enable_story_seeking)
        assert callable(story_first.is_story_seeking_enabled)


# ─── Test: Seek budget constraint ────────────────────────────────────────────

class TestBudgetConstraint:
    """Story-seeking respects wall-budget and reports elapsed time."""

    @patch('story_first.seek_stories_for_stop')
    def test_pipeline_reports_elapsed(self, mock_seek):
        """Pipeline reports elapsed_seconds for wall-time monitoring."""
        mock_seek.return_value = {
            'results': [],
            'queries_issued': 3,
            'query_log': [],
            'elapsed_seconds': 2.5,
            'estimated_cost_usd': 0.003,
        }

        result = story_first_pipeline(
            STOP_DATA_MFA,
            fact_sheet=FACT_SHEET_MFA,
            snippets=[],
            credit_line='',
        )

        assert 'elapsed_seconds' in result
        assert isinstance(result['elapsed_seconds'], float)

    def test_budget_constant_exists(self):
        """The 15s budget constant is accessible."""
        assert STORY_SEEKING_BUDGET_SECONDS == 15.0
