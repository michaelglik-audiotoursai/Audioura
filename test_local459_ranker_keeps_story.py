"""LOCAL-459: Test that the ranker keeps the story and drops the noise.

Tests rank_and_cap_snippets directly with the saved 104-result fixture
(story_lab_state/stop2_enriched.json). No network, no key.

Acceptance criteria (from task):
  1. invaluable.com, freud.org.uk, belvedere.at rank INSIDE the surviving set
  2. Tamarind Lithography Workshop and Fridman Gallery do NOT
  3. Dalí is SOURCEABLE (tested via presence of Dalí+Freud narrative)
  4. ≥3 sentences of usable prose exist in surviving material

D418/D421 compliance: the test MUST be able to fail.
  - Neutralise the LOCAL-459 fix (restore old scoring) → suite FAILS
  - With LOCAL-459 fix → suite PASSES
"""
import pytest
import json
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from snippet_ranker import (
    rank_and_cap_snippets,
    score_snippet,
    TIER3_PENALTY,
    UNVERIFIED_PENALTY,
    SNIPPET_CAP_PER_STOP,
    _build_stop_relevance_terms,
    _verb_is_stop_relevant,
    _snippet_stop_relevance_score,
)


# ─── Fixture loading ─────────────────────────────────────────────────────────

FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'story_lab_state', 'stop2_enriched.json'
)


@pytest.fixture
def fixture_data():
    """Load the 104-result fixture for MFA stop 2 (Moses and Monotheism)."""
    with open(FIXTURE_PATH) as f:
        data = json.load(f)
    return data


@pytest.fixture
def stop_record(fixture_data):
    return fixture_data['stop']


@pytest.fixture
def all_snippets(fixture_data):
    return fixture_data['search_results']


# ─── Key URLs under test ─────────────────────────────────────────────────────

MUST_SURVIVE_URLS = [
    # The correct publisher — the fact the tour was getting wrong
    'https://www.invaluable.com/auction-lot/salvador-dali-moses-monotheism-suite-234-c-abc123',
    # Dalí-Freud meeting (primary story material)
    'https://www.freud.org.uk/2018/07/19/when-dali-met-freud/',
    # Dalí-Freud meeting (secondary source, Belvedere Museum Vienna)
    'https://www.belvedere.at/en/dali-and-freud',
]

MUST_NOT_SURVIVE_URLS = [
    # Tamarind Lithography Workshop: founded 1960, unrelated to this stop
    'https://en.wikipedia.org/wiki/Tamarind_Lithography_Workshop',
    # Fridman Gallery: 2013 NYC gallery, surname collision with donor Boris Fridman
    'https://www.fridmangallery.com/about',
]


# ─── Core acceptance tests ───────────────────────────────────────────────────

class TestRankerKeepsTheStory:
    """LOCAL-459: rank_and_cap_snippets must keep story material and drop noise."""

    def test_invaluable_survives(self, all_snippets, stop_record):
        """The publisher/printer snippet (invaluable.com) ranks inside surviving set."""
        ranked, _ = rank_and_cap_snippets(
            all_snippets,
            artist=stop_record['artist'],
            work_title=stop_record['canonical_title'],
            stop_record=stop_record,
        )
        surviving_urls = {s.get('url') for s in ranked}
        assert MUST_SURVIVE_URLS[0] in surviving_urls, (
            f"invaluable.com (publisher facts) was discarded. "
            f"Survivors: {[s.get('url','')[:50] for s in ranked]}"
        )

    def test_freud_org_survives(self, all_snippets, stop_record):
        """The Dalí-Freud meeting snippet (freud.org.uk) ranks inside surviving set."""
        ranked, _ = rank_and_cap_snippets(
            all_snippets,
            artist=stop_record['artist'],
            work_title=stop_record['canonical_title'],
            stop_record=stop_record,
        )
        surviving_urls = {s.get('url') for s in ranked}
        assert MUST_SURVIVE_URLS[1] in surviving_urls, (
            f"freud.org.uk (Dalí-Freud meeting) was discarded. "
            f"Survivors: {[s.get('url','')[:50] for s in ranked]}"
        )

    def test_belvedere_survives(self, all_snippets, stop_record):
        """The Dalí-Freud meeting (belvedere.at) ranks inside surviving set."""
        ranked, _ = rank_and_cap_snippets(
            all_snippets,
            artist=stop_record['artist'],
            work_title=stop_record['canonical_title'],
            stop_record=stop_record,
        )
        surviving_urls = {s.get('url') for s in ranked}
        assert MUST_SURVIVE_URLS[2] in surviving_urls, (
            f"belvedere.at (Dalí-Freud meeting) was discarded. "
            f"Survivors: {[s.get('url','')[:50] for s in ranked]}"
        )

    def test_tamarind_excluded(self, all_snippets, stop_record):
        """Tamarind Lithography Workshop (1960, unrelated) must NOT survive."""
        ranked, _ = rank_and_cap_snippets(
            all_snippets,
            artist=stop_record['artist'],
            work_title=stop_record['canonical_title'],
            stop_record=stop_record,
        )
        surviving_urls = {s.get('url') for s in ranked}
        assert MUST_NOT_SURVIVE_URLS[0] not in surviving_urls, (
            f"Tamarind Lithography Workshop survived — ranker learned nothing. "
            f"This is an unrelated 1960 workshop, not about Moses and Monotheism."
        )

    def test_fridman_gallery_excluded(self, all_snippets, stop_record):
        """Fridman Gallery (2013 NYC, surname collision) must NOT survive.

        This is the sharper test: it shares a surname with donor Boris Fridman
        but is otherwise unrelated to the stop.
        """
        ranked, _ = rank_and_cap_snippets(
            all_snippets,
            artist=stop_record['artist'],
            work_title=stop_record['canonical_title'],
            stop_record=stop_record,
        )
        surviving_urls = {s.get('url') for s in ranked}
        assert MUST_NOT_SURVIVE_URLS[1] not in surviving_urls, (
            f"Fridman Gallery survived — ranker confused the 2013 NYC gallery "
            f"with donor Boris Fridman. Surname collision not caught."
        )

    def test_dali_sourceable_from_survivors(self, all_snippets, stop_record):
        """Surviving material mentions Salvador Dalí in narrative context (SOURCEABLE).

        story_material_check.py returns SILENCE against old survivors;
        with the fix, Dalí + Freud meeting material makes Dalí SOURCEABLE.
        """
        ranked, _ = rank_and_cap_snippets(
            all_snippets,
            artist=stop_record['artist'],
            work_title=stop_record['canonical_title'],
            stop_record=stop_record,
        )
        # Check if any surviving snippet mentions Dalí in a narrative context
        # (not just as a title/attribution, but doing something)
        dali_narrative = False
        for s in ranked:
            text = f"{s.get('title', '')} {s.get('snippet', '')}"
            # Dalí doing something (verb near his name)
            if re.search(r'Dalí.{1,40}(?:met|visited|brought|arrived|encountered)',
                        text, re.IGNORECASE):
                dali_narrative = True
                break
            if re.search(r'(?:met|visited|brought|arrived|encountered).{1,40}Dalí',
                        text, re.IGNORECASE):
                dali_narrative = True
                break
        assert dali_narrative, (
            "No surviving snippet contains Dalí in narrative context. "
            "story_material_check would return SILENCE."
        )

    def test_three_sentences_available(self, all_snippets, stop_record):
        """≥3 sentences of usable prose in surviving material (Michael's bar).

        Even without R5 page-fetch, the combined snippet text from multiple
        survivors about the Dalí-Freud meeting should yield ≥3 sentences.
        """
        ranked, _ = rank_and_cap_snippets(
            all_snippets,
            artist=stop_record['artist'],
            work_title=stop_record['canonical_title'],
            stop_record=stop_record,
        )
        # Collect all snippet text from survivors that mention Dalí and Freud
        story_text = []
        for s in ranked:
            text = s.get('snippet', '')
            if 'dalí' in text.lower() or 'freud' in text.lower():
                story_text.append(text)

        combined = ' '.join(story_text)
        # Count sentences (split on period/exclamation/question followed by space+capital)
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', combined)
        sentences = [s for s in sentences if len(s) > 20]  # Filter fragments

        assert len(sentences) >= 3, (
            f"Only {len(sentences)} sentences of usable prose found. "
            f"Michael's bar is ≥3. Combined text: {combined[:200]}"
        )


class TestR1UnverifiedDistinctFromTier3:
    """R1: Wikidata failure produces 'unverified', not 'tier3'."""

    def test_unverified_penalty_lighter_than_tier3(self):
        """UNVERIFIED_PENALTY must be strictly lighter than TIER3_PENALTY."""
        assert UNVERIFIED_PENALTY > TIER3_PENALTY, (
            f"UNVERIFIED_PENALTY ({UNVERIFIED_PENALTY}) should be less negative "
            f"than TIER3_PENALTY ({TIER3_PENALTY})"
        )

    def test_unverified_snippet_scores_higher_than_tier3(self):
        """Same snippet with tier='unverified' scores higher than tier='tier3'."""
        snippet_unverified = {
            'title': 'Test Museum Page',
            'snippet': 'Salvador Dalí met someone in 1938.',
            'tier': 'unverified',
        }
        snippet_tier3 = dict(snippet_unverified)
        snippet_tier3['tier'] = 'tier3'

        score_uv = score_snippet(snippet_unverified, 'Salvador Dalí')
        score_t3 = score_snippet(snippet_tier3, 'Salvador Dalí')
        assert score_uv > score_t3, (
            f"Unverified ({score_uv}) should score higher than tier3 ({score_t3})"
        )


class TestR3StopRecordRelevance:
    """R3: Relevance judged against full stop record, not title alone."""

    def test_artist_name_provides_relevance(self, stop_record):
        """A snippet naming the artist is relevant even without title words."""
        snippet = {
            'title': 'When Dalí Met Freud',
            'snippet': 'Salvador Dalí met Sigmund Freud in 1938.',
        }
        stop_terms = _build_stop_relevance_terms(stop_record)
        title_words = {w.lower() for w in re.findall(r'\b\w{4,}\b',
                      stop_record['canonical_title'].lower())}
        score = _snippet_stop_relevance_score(snippet, stop_terms, title_words)
        assert score >= 2, (
            f"Snippet naming the artist got relevance {score}, expected ≥2"
        )

    def test_publisher_name_provides_relevance(self, stop_record):
        """A snippet naming the publisher is relevant even without title words."""
        snippet = {
            'title': 'Art & Valeur Publishers',
            'snippet': 'Editions Art & Valeur S.A. published several Dalí suites in Paris.',
        }
        stop_terms = _build_stop_relevance_terms(stop_record)
        title_words = {w.lower() for w in re.findall(r'\b\w{4,}\b',
                      stop_record['canonical_title'].lower())}
        score = _snippet_stop_relevance_score(snippet, stop_terms, title_words)
        assert score >= 2, (
            f"Snippet naming the publisher got relevance {score}, expected ≥2"
        )

    def test_unrelated_snippet_penalized(self, stop_record):
        """A snippet with no stop-record connection gets negative relevance."""
        snippet = {
            'title': 'Korean Hanboks in Modern Art',
            'snippet': 'The exhibition features traditional Korean garments reimagined.',
        }
        stop_terms = _build_stop_relevance_terms(stop_record)
        title_words = {w.lower() for w in re.findall(r'\b\w{4,}\b',
                      stop_record['canonical_title'].lower())}
        score = _snippet_stop_relevance_score(snippet, stop_terms, title_words)
        assert score < 0, (
            f"Completely unrelated snippet got relevance {score}, expected <0"
        )


class TestR4VerbActorGating:
    """R4: Verb-of-consequence bonus gated on actor's connection to stop."""

    def test_unrelated_actor_verb_not_relevant(self, stop_record):
        """'founded' by an unrelated person (June Wayne) is NOT stop-relevant."""
        text = ("The Tamarind Lithography Workshop was founded in 1960 "
                "by June Wayne in Los Angeles, California.")
        stop_terms = _build_stop_relevance_terms(stop_record)
        assert not _verb_is_stop_relevant(text, stop_terms), (
            "June Wayne founding Tamarind should NOT be stop-relevant"
        )

    def test_related_actor_verb_is_relevant(self, stop_record):
        """'met' by Salvador Dalí IS stop-relevant."""
        text = ("Salvador Dalí met Sigmund Freud at his home in London in 1938.")
        stop_terms = _build_stop_relevance_terms(stop_record)
        assert _verb_is_stop_relevant(text, stop_terms), (
            "Salvador Dalí meeting Freud should be stop-relevant"
        )

    def test_surname_collision_not_validated(self, stop_record):
        """Fridman Gallery (surname collision with donor) should NOT validate.

        'Fridman' alone without corroborating stop terms is insufficient.
        """
        text = ("Fridman Gallery is a contemporary art space founded in 2013 "
                "in New York City.")
        stop_terms = _build_stop_relevance_terms(stop_record)
        assert not _verb_is_stop_relevant(text, stop_terms), (
            "Fridman Gallery (surname collision) should NOT be stop-relevant. "
            "Only 'fridman' matches — no corroboration from other stop terms."
        )


# ─── Tier histogram test ─────────────────────────────────────────────────────

class TestTierHistogram:
    """Report tier histogram before and after (for SUBMISSION doc)."""

    def test_tier_histogram(self, all_snippets, stop_record):
        """Report and validate tier distribution."""
        from collections import Counter

        # Before (input)
        input_tiers = Counter(s.get('tier', '?') for s in all_snippets)
        print(f"\n  Tier histogram (input, {len(all_snippets)} results):")
        for tier, count in sorted(input_tiers.items()):
            print(f"    {tier}: {count}")

        # After (survivors)
        ranked, report = rank_and_cap_snippets(
            all_snippets,
            artist=stop_record['artist'],
            work_title=stop_record['canonical_title'],
            stop_record=stop_record,
        )
        output_tiers = Counter(s.get('tier', '?') for s in ranked)
        print(f"\n  Tier histogram (output, {len(ranked)} survivors):")
        for tier, count in sorted(output_tiers.items()):
            print(f"    {tier}: {count}")

        # Assert: unverified count in input should be >0
        assert input_tiers.get('unverified', 0) > 0, (
            "Fixture should have 'unverified' domains (from Wikidata timeout)"
        )
        # Assert: tier3 should NOT dominate input (R1 fix converts timeouts)
        assert input_tiers.get('tier3', 0) < input_tiers.get('unverified', 0), (
            "More domains should be 'unverified' than 'tier3' after R1 fix"
        )
