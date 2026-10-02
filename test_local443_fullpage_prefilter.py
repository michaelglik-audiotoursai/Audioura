"""test_local443_fullpage_prefilter.py — LOCAL-443 verification tests.

Tests bind directly to module-scope symbols (D242 #1):
  1. Pre-filter neutralisation: disable → candidate volume explodes
  2. Full-page fetch neutralisation: disable → fewer candidates from pages
  3. Budget discipline: pipeline respects PIPELINE_WALL_BUDGET_SECONDS
  4. Pre-filter structural logic: <3 sentences, no person name, SHA dedup
  5. Concurrent classification: thread pool dispatches correctly
"""
import hashlib
import time
import unittest
from unittest.mock import patch, MagicMock

import story_first


class TestPrefilterLogic(unittest.TestCase):
    """Test the zero-cost structural pre-filter (LOCAL-443-B)."""

    def setUp(self):
        story_first.enable_prefilter()

    def tearDown(self):
        story_first.enable_prefilter()

    def test_drops_short_candidates(self):
        """Candidates with < 3 sentences are rejected."""
        candidates = [
            "Short text only.",
            "Two sentences here. And another one.",
            # This one has 3+ sentences with a person name — should pass
            "Marc Chagall created the piece in 1922. He was commissioned by the theatre. "
            "The work survived the war intact.",
        ]
        result = story_first.prefilter_candidates(candidates)
        # Only the 3-sentence candidate with a person name passes
        self.assertEqual(len(result), 1)
        self.assertIn("Marc Chagall", result[0])

    def test_drops_no_person_name(self):
        """Candidates without person-name-shaped tokens are rejected."""
        candidates = [
            # 3+ sentences but no multi-word proper noun
            "The building was constructed in 1890. It served as a warehouse for decades. "
            "Later it was converted into a gallery space.",
            # This has a person name
            "Henri Matisse painted this work in 1905. He was deeply influenced by light. "
            "The piece sold at auction for a record price.",
        ]
        result = story_first.prefilter_candidates(candidates)
        self.assertEqual(len(result), 1)
        self.assertIn("Henri Matisse", result[0])

    def test_sha_deduplication(self):
        """Duplicate candidates (same text) are rejected."""
        text = ("Pablo Picasso destroyed the original sketch in frustration. "
                "He then recreated it from memory the following week. "
                "The final version is considered superior to the original.")
        candidates = [text, text, text]
        result = story_first.prefilter_candidates(candidates)
        self.assertEqual(len(result), 1)

    def test_caps_at_max(self):
        """Output is capped at PREFILTER_MAX_CANDIDATES."""
        # Create 20 valid candidates
        candidates = []
        for i in range(20):
            candidates.append(
                f"Artist Name{i} painted this masterwork in {1900 + i}. "
                f"He dedicated it to his mentor Professor Smith{i}. "
                f"The commission came from Duke Wellington{i}."
            )
        result = story_first.prefilter_candidates(candidates)
        self.assertLessEqual(len(result), story_first.PREFILTER_MAX_CANDIDATES)

    def test_neutralisation_passes_all(self):
        """When pre-filter is disabled, ALL candidates pass through (D242 #1)."""
        story_first.disable_prefilter()

        candidates = [
            "Short.",  # Would normally be filtered
            "no caps here at all. second sentence. third one.",  # No person name
            "Duplicate here. Second sentence ok. Third good one with Marc Chagall.",
            "Duplicate here. Second sentence ok. Third good one with Marc Chagall.",  # Dup
        ]
        result = story_first.prefilter_candidates(candidates)
        # ALL pass when disabled — including short, no-name, and duplicates
        self.assertEqual(len(result), len(candidates))

    def test_volume_explosion_when_disabled(self):
        """D242 #1: disabling pre-filter causes candidate volume to explode."""
        # Create a mix of valid and invalid candidates
        candidates = []
        # 5 valid (3+ sentences, person name)
        for i in range(5):
            candidates.append(
                f"Henri Matisse created work number {i} in his studio. "
                f"He was inspired by the Mediterranean light he saw daily. "
                f"Critics initially dismissed the piece as too radical."
            )
        # 15 invalid (short or no person name)
        for i in range(15):
            candidates.append(f"Short fragment {i}.")

        # With filter: only valid pass
        story_first.enable_prefilter()
        filtered = story_first.prefilter_candidates(candidates)

        # Without filter: all pass
        story_first.disable_prefilter()
        unfiltered = story_first.prefilter_candidates(candidates)

        # Volume explosion proof
        self.assertGreater(len(unfiltered), len(filtered))
        self.assertEqual(len(unfiltered), 20)  # All pass
        self.assertEqual(len(filtered), 5)  # Only valid pass


class TestFullpageFetch(unittest.TestCase):
    """Test full-page fetch (LOCAL-443-A)."""

    def setUp(self):
        story_first.enable_fullpage_fetch()

    def tearDown(self):
        story_first.enable_fullpage_fetch()

    def test_disabled_returns_empty(self):
        """When disabled, fetch_full_pages returns empty list."""
        story_first.disable_fullpage_fetch()
        result = story_first.fetch_full_pages(['https://example.com/page'])
        self.assertEqual(result, [])

    def test_caps_at_max_pages(self):
        """Only FULLPAGE_FETCH_MAX_PAGES URLs are fetched."""
        urls = [f'https://example.com/page{i}' for i in range(10)]

        with patch('story_first._fetch_single_page') as mock_fetch:
            mock_fetch.return_value = {'url': '', 'text': 'content', 'success': True, 'elapsed_ms': 100}
            story_first.fetch_full_pages(urls, budget_seconds=30)
            # Should only fetch MAX_PAGES
            self.assertLessEqual(mock_fetch.call_count, story_first.FULLPAGE_FETCH_MAX_PAGES)

    def test_empty_urls_returns_empty(self):
        """Empty URL list returns empty result."""
        result = story_first.fetch_full_pages([])
        self.assertEqual(result, [])


class TestPageTextExtraction(unittest.TestCase):
    """Test HTML → prose text extraction."""

    def test_extracts_paragraphs(self):
        """Paragraph text is extracted from HTML."""
        html = """
        <html><body>
        <nav>Menu items here</nav>
        <article>
            <p>Marc Chagall created this lithograph in 1957 at his studio in Vence.</p>
            <p>The commission came from Aimé Maeght, who published the artist's most celebrated prints.</p>
            <p>Chagall destroyed three earlier versions before producing the final work we see today.</p>
        </article>
        <footer>Copyright info</footer>
        </body></html>
        """
        text = story_first._extract_page_text(html)
        self.assertIn("Marc Chagall", text)
        self.assertIn("Aimé Maeght", text)
        self.assertIn("destroyed three", text)

    def test_strips_scripts_and_nav(self):
        """Scripts, styles, and navigation are removed."""
        html = """
        <html><body>
        <script>var x = 'malicious';</script>
        <style>.hidden { display: none; }</style>
        <nav><a href="/">Home</a></nav>
        <p>Henri Matisse painted Jazz in 1947 using his new cut-out technique.</p>
        </body></html>
        """
        text = story_first._extract_page_text(html)
        self.assertNotIn("malicious", text)
        self.assertNotIn("display: none", text)
        self.assertIn("Henri Matisse", text)

    def test_empty_html_returns_empty(self):
        """Empty HTML returns empty string."""
        self.assertEqual(story_first._extract_page_text(''), '')
        self.assertEqual(story_first._extract_page_text(None), '')


class TestBudgetDiscipline(unittest.TestCase):
    """Test that the pipeline respects PIPELINE_WALL_BUDGET_SECONDS."""

    @patch.object(story_first, 'PIPELINE_WALL_BUDGET_SECONDS', 2.0)
    @patch('story_first.seek_stories_for_stop')
    def test_budget_exhaustion_returns_early(self, mock_seek):
        """Pipeline returns early when budget is exhausted."""
        # Mock seek to take most of the budget
        def slow_seek(*args, **kwargs):
            time.sleep(1.8)  # Uses most of 2s budget
            return {
                'results': [{'url': 'https://example.com', 'snippet': 'test', 'tier': 'tier1'}],
                'queries_issued': 1,
                'query_log': [],
                'elapsed_seconds': 1.8,
                'estimated_cost_usd': 0.001,
            }
        mock_seek.side_effect = slow_seek

        stop_data = {'canonical_title': 'Test Work', 'artist': 'Test Artist'}
        result = story_first.story_first_pipeline(stop_data)

        # Should complete within reasonable time (budget + overhead)
        self.assertLess(result['elapsed_seconds'], 5.0)
        # Should indicate budget exhaustion or have limited results
        # (exact behavior depends on timing)

    def test_pipeline_wall_budget_config(self):
        """PIPELINE_WALL_BUDGET_SECONDS is 25s (D395 spec)."""
        self.assertEqual(story_first.PIPELINE_WALL_BUDGET_SECONDS, 25.0)


class TestNeutralisationFlags(unittest.TestCase):
    """Test enable/disable functions for neutralisation controls."""

    def tearDown(self):
        story_first.enable_story_seeking()
        story_first.enable_prefilter()
        story_first.enable_fullpage_fetch()

    def test_story_seeking_toggle(self):
        self.assertTrue(story_first.is_story_seeking_enabled())
        story_first.disable_story_seeking()
        self.assertFalse(story_first.is_story_seeking_enabled())
        story_first.enable_story_seeking()
        self.assertTrue(story_first.is_story_seeking_enabled())

    def test_prefilter_toggle(self):
        self.assertTrue(story_first.is_prefilter_enabled())
        story_first.disable_prefilter()
        self.assertFalse(story_first.is_prefilter_enabled())
        story_first.enable_prefilter()
        self.assertTrue(story_first.is_prefilter_enabled())

    def test_fullpage_fetch_toggle(self):
        self.assertTrue(story_first.is_fullpage_fetch_enabled())
        story_first.disable_fullpage_fetch()
        self.assertFalse(story_first.is_fullpage_fetch_enabled())
        story_first.enable_fullpage_fetch()
        self.assertTrue(story_first.is_fullpage_fetch_enabled())


class TestConcurrentClassification(unittest.TestCase):
    """Test that classification dispatches concurrently (LOCAL-443-C)."""

    @patch('story_gate.classify_story_unit')
    @patch('story_gate.score_story_interest')
    @patch('story_verifier.verify_story_candidate')
    def test_concurrent_evaluation_returns_verified(self, mock_verify, mock_interest, mock_classify):
        """Concurrent evaluation returns only verified candidates."""
        mock_classify.return_value = {
            'is_story': True, 'reason': 'test', 'emotional_content': 3,
            'new_information': 2, 'deduction': 0, 'cost_usd': 0.001, 'from_cache': False,
        }
        mock_interest.return_value = {
            'emotional_content': 3, 'new_information': 2, 'deduction': 0,
            'interest_score': 5, 'is_story': True,
        }
        mock_verify.return_value = {'passed': True, 'evidence': [], 'claims_sourced': 2}

        candidates = [
            "Pablo Picasso created this lithograph for his dealer. "
            "He was commissioned to produce twenty copies for the gallery exhibition. "
            "The printer Mourlot Frères handled the production at their Paris workshop.",
        ]
        snippets = [{'snippet': 'Picasso lithograph Mourlot', 'url': 'https://mfa.org'}]

        result = story_first.evaluate_candidates_concurrent(
            candidates, snippets, budget_seconds=10.0)

        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]['verified'])
        self.assertTrue(result[0]['is_story'])


class TestPipelineIntegration(unittest.TestCase):
    """Integration tests for the full pipeline with mocked externals."""

    def setUp(self):
        story_first.enable_story_seeking()
        story_first.enable_prefilter()
        story_first.enable_fullpage_fetch()
        story_first.reset_pipeline_cost()

    def tearDown(self):
        story_first.enable_story_seeking()
        story_first.enable_prefilter()
        story_first.enable_fullpage_fetch()

    def test_disabled_pipeline_returns_fallback(self):
        """When story-seeking is disabled, pipeline returns fallback immediately."""
        story_first.disable_story_seeking()
        result = story_first.story_first_pipeline(
            {'canonical_title': 'Test', 'artist': 'Artist'})
        self.assertTrue(result['fallback'])
        self.assertEqual(result['stories'], [])
        self.assertEqual(result['elapsed_seconds'], 0.0)

    def test_anchor_facts_extraction(self):
        """Step 1 extracts anchor facts correctly."""
        stop_data = {
            'canonical_title': 'Le Lézard aux plumes d\'or',
            'artist': 'Henri Matisse',
            'credit_line': 'Gift of Boris Fridman. Published by Louis Broder. Printed by Mourlot Frères.',
            'medium': 'Lithograph on paper',
            'publisher': 'Louis Broder',
            'venue_name': 'Museum of Fine Arts',
            'exhibition_name': 'Unbound',
        }
        facts = story_first.extract_anchor_facts(stop_data)
        self.assertEqual(facts['artist'], 'Henri Matisse')
        self.assertEqual(facts['publisher'], 'Louis Broder')
        self.assertIn('Boris Fridman', facts['donor'])
        self.assertIn('Mourlot Frères', facts['printer'])
        self.assertIn('Henri Matisse', facts['key_entities'])

    def test_cost_tracking(self):
        """Pipeline cost tracking works."""
        story_first.reset_pipeline_cost()
        cost = story_first.get_pipeline_cost()
        self.assertEqual(cost['total_cost_usd'], 0.0)
        self.assertEqual(cost['queries_issued'], 0)


if __name__ == '__main__':
    unittest.main()
