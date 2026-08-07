"""test_local334_museum_object_questions.py — LOCAL-334: Museum questions target the object.

The defect: build_interpretive_questions for venue_kind='museum' asked
"What are the most significant works and collections at Kannon à mille bras?"
— treating the object as if it were the museum. In a museum tour, the venue
is the museum and the stops are objects inside it. Questions must target the
object, with the museum as context.

These tests MUST fail against the pre-LOCAL-334 code.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestMuseumObjectQuestions:
    """Questions for museum stops target the object, not the museum."""

    def test_museum_questions_reference_object_not_venue_as_subject(self):
        """The stop title (object) is the subject; the venue is context."""
        from interpretive_enrichment import build_interpretive_questions

        questions = build_interpretive_questions(
            stop_title="Kannon a mille bras",
            venue_kind="museum",
            city="Nice",
            country="France",
            venue_name="Musee des Arts Asiatiques (Asian Art Museum), Nice, France",
        )
        assert len(questions) == 2

        # Both questions must mention the object name
        for q in questions:
            assert "Kannon a mille bras" in q, f"Object name missing from: {q}"

        # Questions must NOT ask "what collections at <object>"
        combined = ' '.join(questions).lower()
        assert "collections at kannon" not in combined
        assert "works and collections at kannon" not in combined

        # The museum must appear as context (the "at" location), not as the subject
        assert "Musee des Arts Asiatiques" in ' '.join(questions)

    def test_museum_questions_ask_about_creation_and_significance(self):
        """Museum object questions ask who made it, what it depicts, provenance."""
        from interpretive_enrichment import build_interpretive_questions

        questions = build_interpretive_questions(
            stop_title="Robe de pretre taoiste",
            venue_kind="museum",
            city="Nice",
            country="France",
            venue_name="Musee des Arts Asiatiques (Asian Art Museum), Nice, France",
        )
        combined = ' '.join(questions).lower()
        # Must ask object-appropriate things: creation, depiction, provenance
        assert any(word in combined for word in ('created', 'depict', 'come to', 'notable')), \
            f"Questions don't ask about the object: {questions}"

    def test_museum_venue_appears_as_context_not_subject(self):
        """The venue name is used as a locator ('at'), not the subject of the question."""
        from interpretive_enrichment import build_interpretive_questions

        questions = build_interpretive_questions(
            stop_title="Masque du vieillard kojo",
            venue_kind="museum",
            city="Nice",
            country="France",
            venue_name="Musee des Arts Asiatiques (Asian Art Museum), Nice, France",
        )
        # "at Musee des Arts Asiatiques" should appear — venue as location context
        combined = ' '.join(questions)
        assert "at Musee des Arts Asiatiques" in combined, \
            f"Venue not used as location context: {questions}"
        # The venue should NOT be the grammatical subject (no "What is at Musee des Arts...")
        for q in questions:
            assert not q.startswith("What is at"), f"Venue is wrongly the subject: {q}"
            assert not q.startswith("What are the most significant works"), \
                f"Still asking about venue collections: {q}"

    def test_museum_without_venue_name_falls_to_default(self):
        """Without venue_name, museum falls back to safe default questions."""
        from interpretive_enrichment import build_interpretive_questions

        questions = build_interpretive_questions(
            stop_title="Kannon a mille bras",
            venue_kind="museum",
            city="Nice",
            country="France",
            # No venue_name
        )
        assert len(questions) == 2
        # Should use default template — "What is interesting or notable about..."
        assert "interesting" in questions[0].lower() or "notable" in questions[0].lower()
        # Must NOT ask about "collections at" the object
        assert "collections at" not in ' '.join(questions).lower()

    def test_venue_name_stripped_to_short_form(self):
        """Venue name is cleaned: parentheticals removed, comma-suffix stripped."""
        from interpretive_enrichment import build_interpretive_questions

        questions = build_interpretive_questions(
            stop_title="Statue de Bouddha",
            venue_kind="museum",
            city="Nice",
            country="France",
            venue_name="Musee des Arts Asiatiques (Asian Art Museum), Nice, France",
        )
        combined = ' '.join(questions)
        # Should have short form, not the full venue_name with city,country
        assert "Musee des Arts Asiatiques" in combined
        assert "(Asian Art Museum)" not in combined
        assert "Nice, France" not in combined or "Musee des Arts Asiatiques, Nice, France" not in combined


class TestOtherKindsNotRegressed:
    """Restaurant, geographic_area, cycling, and default templates are unchanged."""

    def test_restaurant_unchanged(self):
        """Restaurant questions still ask 'what is interesting' + 'notable people'."""
        from interpretive_enrichment import build_interpretive_questions

        questions = build_interpretive_questions(
            stop_title="Le Safari",
            venue_kind="restaurant",
            city="Nice",
            country="France",
            venue_name="Old Nice, Nice, France",
        )
        assert "interesting" in questions[0].lower()
        assert "Le Safari" in questions[0]
        assert "restaurant" in questions[0].lower()
        assert "people" in questions[1].lower() or "associated" in questions[1].lower()

    def test_geographic_area_unchanged(self):
        """Geographic area stops are places — questions are about the place itself."""
        from interpretive_enrichment import build_interpretive_questions

        questions = build_interpretive_questions(
            stop_title="Cap d Antibes",
            venue_kind="geographic_area",
            city="French Riviera",
            country="France",
        )
        assert "Cap d Antibes" in questions[0]
        assert "interesting" in questions[0].lower() or "notable" in questions[0].lower()
        # No museum-style "at <venue>" — geographic stops ARE the place
        assert "at " not in questions[0] or "at Cap" not in questions[0]

    def test_cycling_unchanged(self):
        """Cycling stops are places — fall to default templates."""
        from interpretive_enrichment import build_interpretive_questions

        questions = build_interpretive_questions(
            stop_title="Eze Village",
            venue_kind="cycling",
            city="French Riviera",
            country="France",
        )
        assert "Eze Village" in questions[0]
        assert "interesting" in questions[0].lower() or "notable" in questions[0].lower()

    def test_default_fallback_unchanged(self):
        """Unknown kinds use default templates."""
        from interpretive_enrichment import build_interpretive_questions

        questions = build_interpretive_questions(
            stop_title="Pont du Gard",
            venue_kind="aqueduct",
            city="Vers-Pont-du-Gard",
            country="France",
        )
        assert "Pont du Gard" in questions[0]
        assert "interesting" in questions[0].lower() or "notable" in questions[0].lower()

    def test_monument_unchanged(self):
        """Monument questions ask about history and commissioning."""
        from interpretive_enrichment import build_interpretive_questions

        questions = build_interpretive_questions(
            stop_title="Arc de Triomphe",
            venue_kind="monument",
            city="Paris",
            country="France",
        )
        assert "Arc de Triomphe" in questions[0]
        combined = ' '.join(questions).lower()
        assert "history" in combined or "commissioned" in combined or "designed" in combined


class TestVenueNamePassthrough:
    """venue_name is threaded through enrich_stop_interpretive."""

    def test_enrich_stop_interpretive_accepts_venue_name(self):
        """enrich_stop_interpretive has a venue_name parameter."""
        import inspect
        from interpretive_enrichment import enrich_stop_interpretive

        sig = inspect.signature(enrich_stop_interpretive)
        assert 'venue_name' in sig.parameters, \
            "enrich_stop_interpretive must accept venue_name parameter"

    def test_build_interpretive_questions_accepts_venue_name(self):
        """build_interpretive_questions has a venue_name parameter."""
        import inspect
        from interpretive_enrichment import build_interpretive_questions

        sig = inspect.signature(build_interpretive_questions)
        assert 'venue_name' in sig.parameters, \
            "build_interpretive_questions must accept venue_name parameter"
