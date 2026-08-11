"""LOCAL-414: Source tier must gate injection — tier3 cannot outrank tier1/tier2.

Behavioural tests. Each test exercises the observable behaviour of the ranker
and the post-generation banned-phrase validation. Tests are designed to FAIL on
the current `storied` branch (before LOCAL-414 changes) and PASS after.

Run:
    python -m pytest tests/test_local414_tier_must_gate_injection.py -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from snippet_ranker import score_snippet, rank_and_cap_snippets


class TestTier3PenaltyExists:
    """The tier3 penalty must exist and be applied."""

    def test_tier3_penalty_is_negative(self):
        """TIER3_PENALTY must be a negative number (at least -5)."""
        from snippet_ranker import TIER3_PENALTY
        assert TIER3_PENALTY <= -5, (
            f"TIER3_PENALTY is {TIER3_PENALTY}, expected <= -5. "
            "Without a penalty, tier3 doctrinal sites can outrank tier1/tier2."
        )


class TestTier3CannotOutrankTier1Tier2:
    """A tier3 snippet with identical story signals cannot outscore tier1/tier2."""

    def _make_snippet(self, tier: str, text: str = None) -> dict:
        """Create a snippet with a strong story (person + verb + date + institution)."""
        if text is None:
            text = "John Smith commissioned the sculpture in 1890 at the Museum of Fine Arts"
        return {
            'title': text,
            'snippet': text,
            'url': f'https://example-{tier}.com/page',
            'tier': tier,
        }

    def test_tier1_outscores_tier3_same_content(self):
        """A tier1 snippet must always outscore a tier3 snippet with identical content."""
        tier1 = self._make_snippet('tier1')
        tier3 = self._make_snippet('tier3')

        score1 = score_snippet(tier1)
        score3 = score_snippet(tier3)

        assert score1 > score3, (
            f"tier1 scored {score1}, tier3 scored {score3} — with identical content "
            f"tier1 must ALWAYS beat tier3. This is the LOCAL-414 defect: tier is "
            f"computed but never gates injection."
        )

    def test_tier2_outscores_tier3_same_content(self):
        """A tier2 snippet must always outscore a tier3 snippet with identical content."""
        tier2 = self._make_snippet('tier2')
        tier3 = self._make_snippet('tier3')

        score2 = score_snippet(tier2)
        score3 = score_snippet(tier3)

        assert score2 > score3, (
            f"tier2 scored {score2}, tier3 scored {score3} — with identical content "
            f"tier2 must ALWAYS beat tier3."
        )

    def test_tier3_cannot_reach_tier1_score_even_with_all_signals(self):
        """A tier3 snippet with maximum story signals must still score below
        a tier1 snippet with the same signals."""
        # Maximum story signals: person (+3) + verb (+3) + date (+2) + place (+1) + artist (+1)
        text = "Pablo Picasso created the lithograph in 1951 at the Museum of Modern Art"
        tier1 = {'title': text, 'snippet': text, 'url': 'https://moma.org/x', 'tier': 'tier1'}
        tier3 = {'title': text, 'snippet': text, 'url': 'https://apologetics.org/x', 'tier': 'tier3'}

        score1 = score_snippet(tier1, artist='Pablo Picasso')
        score3 = score_snippet(tier3, artist='Pablo Picasso')

        assert score1 > score3, (
            f"tier1={score1} vs tier3={score3} — even with ALL story signals, "
            f"tier3 must not match tier1."
        )

    def test_ranking_places_tier1_above_tier3(self):
        """rank_and_cap_snippets must place tier1/tier2 material above tier3
        even when tier3 has MORE story signals (the actual failure mode)."""
        # The actual failure: apologetics site has LOTS of story-shaped content
        # (named person, verb, date, institution) while the museum snippet is shorter
        tier3_apologetics = {
            'title': 'Adam and Eve — Genesis and the Fall',
            'snippet': 'God created Adam and Eve in the Garden of Eden. '
                       'The fall represented the perfect beginning of humanity '
                       'and the subsequent fall into sin, as documented by scholars '
                       'at the Biblical Archaeology Institute in 2003.',
            'url': 'https://answersingenesis.org/adam-and-eve/',
            'tier': 'tier3',
        }
        # Museum snippet with fewer story signals (typical of short catalogue entries)
        tier1_museum = {
            'title': 'Adam and Eve',
            'snippet': 'Oil on panel, acquired 1941.',
            'url': 'https://mfa.org/collections/adam-eve',
            'tier': 'tier1',
        }

        ranked, report = rank_and_cap_snippets(
            [tier3_apologetics, tier1_museum],
            artist='Lucas Cranach the Elder',
        )

        assert len(ranked) == 2
        # The tier1 museum snippet must STILL be ranked first despite fewer story signals
        assert ranked[0]['tier'] == 'tier1', (
            f"Expected tier1 first, got {ranked[0]['tier']} — "
            f"tier3 apologetics content (with more story signals) displaced museum source. "
            f"Scores: {report['scores']}. This is the LOCAL-414 defect: a tier3 doctrinal "
            f"site outranks a legitimate museum source because tier is never penalized."
        )

    def test_report_includes_tier3_stats(self):
        """The ranking report must include tier3 demotion statistics."""
        snippets = [
            {'title': 'Test', 'snippet': 'John created x in 1900 at Museum',
             'url': 'https://a.com', 'tier': 'tier3'},
            {'title': 'Test2', 'snippet': 'Jane published y in 1905 at Gallery',
             'url': 'https://b.edu', 'tier': 'tier1'},
        ]
        _, report = rank_and_cap_snippets(snippets)

        assert 'tier3_demoted' in report, "Report must track tier3 demotions"
        assert 'tier3_in_output' in report, "Report must track tier3 count in output"
        assert 'tier1_tier2_in_output' in report, "Report must track tier1/tier2 in output"
        assert report['tier3_demoted'] == 1
        assert report['tier1_tier2_in_output'] == 1


class TestTier3StillAvailableWhenAlone:
    """When no tier1/tier2 material exists, tier3 must still be available
    (not hard-excluded). This prevents starving the pipeline."""

    def test_tier3_only_still_returns_results(self):
        """If all snippets are tier3, they must still be returned (not rejected)."""
        snippets = [
            {'title': f'Source {i}', 'snippet': f'Person{i} created work in {1900+i} at Museum',
             'url': f'https://tier3-{i}.com', 'tier': 'tier3'}
            for i in range(5)
        ]
        ranked, report = rank_and_cap_snippets(snippets)

        assert report['output_count'] > 0, (
            "With only tier3 snippets, pipeline must still return results. "
            "A hard exclusion would starve the stop of all material."
        )
        assert report['output_count'] == 5


class TestBannedPhraseInOutput:
    """The banned-phrase list must include 'invites contemplation' and related variants."""

    def test_invites_contemplation_is_banned_in_prompt(self):
        """'invites contemplation' must be in the BANNED PHRASES section of the prompt,
        not just in the specificity-short branch."""
        # Read generate_tour_text.py and find the BANNED PHRASES block
        gen_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'generate_tour_text.py')
        with open(gen_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find the BANNED PHRASES section (not the specificity_short mention)
        banned_section_start = content.find('BANNED PHRASES — do NOT use any of these')
        assert banned_section_start != -1, "BANNED PHRASES section not found in generate_tour_text.py"

        # Check that 'invites contemplation' appears in the BANNED PHRASES section
        # (within 2000 chars of the header)
        banned_section = content[banned_section_start:banned_section_start + 2000]
        assert 'invites contemplation' in banned_section, (
            "'invites contemplation' is NOT in the BANNED PHRASES list — "
            "it only appears in the _specificity_short branch, which does not fire "
            "when the stop has snippets/corpus. This is the LOCAL-414 banned-phrase bug."
        )


class TestUniversalArtistAttribution:
    """Artist attribution must fire for ALL museum stops, not just when snippets are present."""

    def test_attribution_rule_outside_snippet_block(self):
        """The NON-NEGOTIABLE artist attribution rule must exist outside the snippet block,
        so it fires even when a stop has no snippets or when snippets name a different artist."""
        gen_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'generate_tour_text.py')
        with open(gen_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # The LOCAL-414 universal attribution must exist as a separate block
        # that references "FINAL AUTHORITY" and applies regardless of snippet injection
        assert 'LOCAL-414' in content and 'FINAL AUTHORITY' in content, (
            "No universal artist attribution rule found (LOCAL-414 FINAL AUTHORITY). "
            "The only attribution rule is inside the snippet block (line ~9164) which "
            "only fires when snippets are injected and _artist_surname is set. A stop "
            "with snippets naming a DIFFERENT artist can bypass it."
        )

        # The universal rule must be AFTER the snippet block
        snippet_block_pos = content.find('ARTIST ATTRIBUTION (LOCAL-407')
        universal_pos = content.find('ARTIST ATTRIBUTION (LOCAL-414')
        assert universal_pos > snippet_block_pos, (
            "The universal attribution rule (LOCAL-414) must come AFTER the snippet "
            "block attribution (LOCAL-407) to have recency advantage in the prompt."
        )
