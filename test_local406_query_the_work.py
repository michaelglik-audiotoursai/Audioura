#!/usr/bin/env python3
"""test_local406_query_the_work.py — Unit tests for LOCAL-406.

Asserts that synthesize_queries produces queries targeting the work and its
collaborators, NOT just the artist biography. Also tests the biography rejection
filter, and the "worked together" coherence gate fix.

Required by D296: tests break the LOGIC, not the symbol. Reverting the query
logic should produce generic "story behind" queries without collaborator names.

Required by D307: at least one test on the real generation path.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import re
from work_story_searcher import synthesize_queries, _is_biography_only
from temporal_coherence_gate import check_temporal_coherence, _INTERACTION_RE


# ---------------------------------------------------------------------------
# Test: synthesize_queries includes work title AND collaborator names
# ---------------------------------------------------------------------------

class TestSynthesizeQueriesTargetWork:
    """Queries must include the quoted work title and at least one collaborator."""

    def test_stop_with_publisher_gets_publisher_query(self):
        """Stop with publisher='Louis Broder' produces a query containing Broder."""
        stop = {
            'canonical_title': "Le Lézard aux plumes d'or",
            'artist': 'Joan Miró',
            'venue_city': 'Boston',
            'venue_lang': 'en',
            'publisher': 'Louis Broder',
        }
        queries = synthesize_queries(stop, tour_type='contained')
        queries_joined = ' '.join(queries).lower()

        # Must contain work title (quoted)
        assert "le lézard aux plumes d'or" in queries_joined, \
            f"Work title missing from queries: {queries}"
        # Must contain publisher name
        assert 'broder' in queries_joined, \
            f"Publisher 'Broder' missing from queries: {queries}"

    def test_stop_with_printer_gets_printer_query(self):
        """Stop with printer='Mourlot Frères' produces a query about the workshop."""
        stop = {
            'canonical_title': "Le Lézard aux plumes d'or",
            'artist': 'Joan Miró',
            'venue_city': 'Boston',
            'venue_lang': 'en',
            'printer': 'Mourlot Frères',
        }
        queries = synthesize_queries(stop, tour_type='contained')
        queries_joined = ' '.join(queries).lower()
        assert 'mourlot' in queries_joined, \
            f"Printer 'Mourlot' missing from queries: {queries}"
        assert 'workshop' in queries_joined, \
            f"'workshop' missing from printer query: {queries}"

    def test_stop_with_donor_from_credit_line(self):
        """Donor extracted from credit_line gets a collection query."""
        stop = {
            'canonical_title': "Le Lézard aux plumes d'or",
            'artist': 'Joan Miró',
            'venue_city': 'Boston',
            'venue_lang': 'en',
            'credit_line': 'Gift of Boris Fridman to the Museum of Fine Arts, Boston',
        }
        queries = synthesize_queries(stop, tour_type='contained')
        queries_joined = ' '.join(queries).lower()
        assert 'fridman' in queries_joined, \
            f"Donor 'Fridman' missing from queries: {queries}"
        assert 'collection' in queries_joined, \
            f"'collection' missing from donor query: {queries}"

    def test_queries_contain_title_and_collaborator(self):
        """Core assertion: queries include the work title AND at least one collaborator name."""
        stop = {
            'canonical_title': "Le Lézard aux plumes d'or",
            'artist': 'Joan Miró',
            'venue_city': 'Boston',
            'venue_lang': 'en',
            'publisher': 'Louis Broder',
            'printer': 'Mourlot Frères',
            'credit_line': 'Gift of Boris Fridman to the Museum of Fine Arts, Boston',
        }
        queries = synthesize_queries(stop, tour_type='contained')
        queries_joined = ' '.join(queries).lower()

        # Title present
        assert "le lézard" in queries_joined

        # At least one collaborator name (not just the artist)
        collaborator_names = ['broder', 'mourlot', 'fridman']
        found = [name for name in collaborator_names if name in queries_joined]
        assert len(found) >= 1, \
            f"No collaborator names in queries (expected any of {collaborator_names}): {queries}"

    def test_no_generic_story_behind_for_contained(self):
        """[D296] Revert-detection: new queries should NOT have 'story behind' as suffix."""
        stop = {
            'canonical_title': "Le Lézard aux plumes d'or",
            'artist': 'Joan Miró',
            'venue_city': 'Boston',
            'venue_lang': 'en',
            'publisher': 'Louis Broder',
        }
        queries = synthesize_queries(stop, tour_type='contained')
        story_behind_queries = [q for q in queries if q.endswith('story behind')]
        assert len(story_behind_queries) == 0, \
            f"Found revert-indicating 'story behind' suffix: {story_behind_queries}"

    def test_livre_artiste_form_query(self):
        """When medium suggests a livre d'artiste, the form query is generated."""
        stop = {
            'canonical_title': "Le Lézard aux plumes d'or",
            'artist': 'Joan Miró',
            'venue_city': 'Boston',
            'venue_lang': 'en',
            'medium': 'lithographs',
            'publisher': 'Louis Broder',
        }
        queries = synthesize_queries(stop, tour_type='contained')
        queries_joined = ' '.join(queries).lower()
        assert "livre d'artiste" in queries_joined, \
            f"Form query 'livre d'artiste' missing: {queries}"

    def test_stop_without_collaborators_still_queries_title(self):
        """Even without publisher/printer/donor, queries are title-centric."""
        stop = {
            'canonical_title': 'Les Chants de Maldoror',
            'artist': 'Salvador Dalí',
            'venue_city': 'Boston',
            'venue_lang': 'en',
        }
        queries = synthesize_queries(stop, tour_type='contained')
        queries_joined = ' '.join(queries).lower()
        assert 'les chants de maldoror' in queries_joined
        # Must NOT be just "artist story behind"
        assert not all('story behind' in q for q in queries)


# ---------------------------------------------------------------------------
# Test: biography rejection filter
# ---------------------------------------------------------------------------

class TestBiographyRejection:
    """Snippets dominated by biography signals are rejected."""

    def test_pure_biography_rejected(self):
        """Encyclopaedia bio about Miró's childhood → reject."""
        assert _is_biography_only(
            "Joan Miró was born on April 20, 1893, in Barcelona and grew up in a family of watchmakers and goldsmiths.",
            "Joan Miró (1893–1983)"
        )

    def test_biography_with_generic_profession_rejected(self):
        """'Was a Catalan painter' + birth/death → biography."""
        assert _is_biography_only(
            "Joan Miró was a Catalan painter who combined abstract art with Surrealist fantasy. Born in 1893.",
            "Joan Miro | Biography"
        )

    def test_snippet_with_publishing_info_kept(self):
        """Snippet mentioning publisher/lithographs → NOT biography."""
        assert not _is_biography_only(
            "Le Lézard aux plumes d'or was published by Louis Broder in 1971 with lithographs by Miró.",
            "Le Lézard aux plumes d'or"
        )

    def test_snippet_with_exhibition_info_kept(self):
        """Snippet mentioning exhibition → NOT biography."""
        assert not _is_biography_only(
            "This work was exhibited at the Museum of Fine Arts as part of the Unbound exhibition.",
            "MFA Exhibition"
        )

    def test_snippet_with_collection_info_kept(self):
        """Snippet mentioning donation/collection → NOT biography."""
        assert not _is_biography_only(
            "Gift of Boris Fridman to the Museum of Fine Arts. A fine collection of livres d'artiste.",
            "Museum Collection"
        )

    def test_biography_with_workshop_rescued(self):
        """Bio snippet mentioning workshop/atelier → kept (work signal)."""
        assert not _is_biography_only(
            "Miró was born in 1893. He worked at the Mourlot workshop to produce his lithographs.",
            "Joan Miró"
        )


# ---------------------------------------------------------------------------
# Test: "worked together" coherence gate fix
# ---------------------------------------------------------------------------

class TestWorkedTogetherGateFix:
    """'X and Y worked together' must now be caught by the coherence gate."""

    def test_worked_together_caught(self):
        """'Dalí worked together with Freud' is caught when Freud was dead."""
        result = check_temporal_coherence(
            "In 1974, Dalí worked together with Freud on a new project.",
        )
        assert result is not None, "Gate missed 'worked together with'"
        assert 'Freud' in result['reason'] or 'Freud' in result.get('person_b', '')

    def test_worked_together_regex_match(self):
        """The regex pattern matches 'worked together'."""
        assert _INTERACTION_RE.search("worked together with")

    def test_working_together_caught(self):
        """'working together' variant also caught."""
        assert _INTERACTION_RE.search("working together with")


# ---------------------------------------------------------------------------
# Run with pytest or directly
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v', '--tb=short']))
