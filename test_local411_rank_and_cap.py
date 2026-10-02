"""LOCAL-411: Test snippet ranking, capping, and generation-path wiring.

Tests:
1. snippet_ranker scores story-rich snippets higher than biography-only
2. snippet_ranker caps output at SNIPPET_CAP_PER_STOP (default 5)
3. biography-only snippets are rejected (score -999)
4. rank_and_cap_snippets returns a ranking report
5. generate_tour_text imports and applies rank_and_cap_snippets on the real path
6. search_stories_for_stop is called on the real generation path (D307 invariant)

Expected red-on-revert count: 6
Reverting LOCAL-411 removes the import of snippet_ranker and the ranking/capping
logic from the injection path — tests 1-4 fail because the module doesn't exist,
tests 5-6 fail because the wiring is gone.
"""

import os
import sys
import re
import inspect
import pytest

# Ensure environment
os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['GENERATION_TIER'] = 'plus'
os.environ.setdefault('DATABASE_URL', 'postgresql://admin:password123@localhost:5433/audiotours')


class TestSnippetRanker:
    """Unit tests for the snippet_ranker module."""

    def test_story_rich_snippet_scores_high(self):
        """A snippet with named person + verb + date scores ≥8."""
        from snippet_ranker import score_snippet

        story_snippet = {
            'title': 'Mourlot and Picasso',
            'snippet': 'Picasso met Fernand Mourlot in October 1945 at the atelier on rue de Chabrol.',
            'tier': 'tier1',
        }
        score = score_snippet(story_snippet, artist='Pablo Picasso')
        # person(3) + verb(3) + date(2) + tier1(1) + artist(1) = 10
        assert score >= 8, f"Story-rich snippet scored only {score}, expected ≥8"

    def test_biography_only_snippet_rejected(self):
        """A biography-only snippet gets -999 (hard reject)."""
        from snippet_ranker import score_snippet

        bio_snippet = {
            'title': 'Joan Miró',
            'snippet': 'Joan Miró (1893–1983) was a Catalan painter, sculptor and ceramicist born in Barcelona.',
            'tier': 'tier3',
        }
        score = score_snippet(bio_snippet, artist='Joan Miró')
        assert score == -999, f"Biography-only snippet scored {score}, expected -999"

    def test_cap_limits_output(self):
        """rank_and_cap_snippets returns at most `cap` snippets."""
        from snippet_ranker import rank_and_cap_snippets

        # Create 20 snippets with varying quality
        snippets = []
        for i in range(20):
            snippets.append({
                'title': f'Source {i}',
                'snippet': f'Person{i} Name{i} published edition {i} in {1900 + i}.',
                'tier': 'tier2',
            })

        ranked, report = rank_and_cap_snippets(snippets, artist='Test Artist', cap=5)
        assert len(ranked) <= 5, f"Cap violated: got {len(ranked)} snippets, expected ≤5"
        assert report['cap_applied'] == 5
        assert report['input_count'] == 20
        assert report['output_count'] <= 5

    def test_ranking_report_structure(self):
        """rank_and_cap_snippets returns a well-formed report dict."""
        from snippet_ranker import rank_and_cap_snippets

        snippets = [
            {'title': 'Good', 'snippet': 'Mourlot printed 40 lithographs in 1945.', 'tier': 'tier1'},
            {'title': 'Bad', 'snippet': 'Miró (1893-1983) was a Spanish painter born in Barcelona.', 'tier': 'tier3'},
        ]
        ranked, report = rank_and_cap_snippets(snippets, artist='Joan Miró')

        assert 'input_count' in report
        assert 'rejected_biography_only' in report
        assert 'cap_applied' in report
        assert 'output_count' in report
        assert 'scores' in report
        assert report['input_count'] == 2
        assert report['rejected_biography_only'] >= 1  # the bio snippet
        assert report['output_count'] <= report['input_count']


class TestLocal411GenerationWiring:
    """Test that LOCAL-411 ranking is wired into the real generation path."""

    def test_generation_path_imports_snippet_ranker(self):
        """generate_tour_text must import rank_and_cap_snippets from snippet_ranker.

        This is the invariant: reverting LOCAL-411 removes the ranking logic
        and search results flood the prompt unranked.
        """
        import generate_tour_text as gtt
        source = inspect.getsource(gtt.generate_tour_text)

        assert 'from snippet_ranker import rank_and_cap_snippets' in source, (
            "generate_tour_text does not import rank_and_cap_snippets — "
            "LOCAL-411 ranking has been reverted"
        )
        assert '_ranked_snippets, _ranking_report = rank_and_cap_snippets(' in source, (
            "generate_tour_text does not call rank_and_cap_snippets — "
            "LOCAL-411 ranking has been reverted"
        )

    def test_search_stories_for_stop_called_on_real_path(self):
        """generate_tour_text calls search_stories_for_stop (D307 invariant).

        The absence of exactly this test is why the gap survived six rounds.
        Reverting LOCAL-410 removes this call; reverting LOCAL-411 keeps it.
        """
        import generate_tour_text as gtt
        source = inspect.getsource(gtt.generate_tour_text)

        # Must import and call search_stories_for_stop
        assert 'from work_story_searcher import search_stories_for_stop' in source, (
            "generate_tour_text no longer imports search_stories_for_stop — "
            "production path has no search"
        )
        assert '_s_result = search_stories_for_stop(' in source, (
            "generate_tour_text no longer calls search_stories_for_stop — "
            "production path has no search"
        )
        # Must populate _DIRECT_SNIPPETS_PER_STOP
        assert '_DIRECT_SNIPPETS_PER_STOP = _local410_snippets' in source, (
            "generate_tour_text no longer populates _DIRECT_SNIPPETS_PER_STOP — "
            "search results never reach the prompt"
        )


# Expected red-on-revert count: 6
# - test_story_rich_snippet_scores_high: fails (module removed)
# - test_biography_only_snippet_rejected: fails (module removed)
# - test_cap_limits_output: fails (module removed)
# - test_ranking_report_structure: fails (module removed)
# - test_generation_path_imports_snippet_ranker: fails (import removed from gtt)
# - test_search_stories_for_stop_called_on_real_path: fails (call removed from gtt)

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
