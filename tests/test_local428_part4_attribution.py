"""LOCAL-428: Tests for check_part4_attribution and should_inject_venue_snippet.

These test the PRODUCTION symbols directly — no mirrors, no inspect.getsource.
Each test goes red when the function is neutralised (returns [] unconditionally
or returns {'inject': False} unconditionally).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generate_tour_text import check_part4_attribution, should_inject_venue_snippet


class TestCheckPart4Attribution:
    """Part 4 cross-reference validation: clause-scoped, not window-scoped."""

    # ── The prompt's worked example: MUST PASS (no false positive) ──────────

    def test_prompt_worked_example_passes(self):
        """The prompt's own example names one date per stop with correct attribution.

        Text: "In the stops ahead, you will encounter Monet's 1888 paintings
               at Cap d'Antibes and the 1706 destruction of Eze Village's
               fortifications."

        1888 is attributed to Cap d'Antibes (correct — it's in that stop's desc).
        1706 is attributed to Eze Village (correct — it's in that stop's desc).

        The OLD ±80-char window put BOTH dates in BOTH windows and reported both
        as misattributed. The new clause-scoped logic must return NO errors.
        """
        part4_text = (
            "In the stops ahead, you will encounter Monet's 1888 paintings "
            "at Cap d'Antibes and the 1706 destruction of Eze Village's fortifications."
        )
        stop_data = [
            {
                'name': "Cap d'Antibes",
                'description': (
                    "Claude Monet arrived at Cap d'Antibes in January 1888 and painted "
                    "over thirty canvases during his stay. The Mediterranean light "
                    "transformed his palette, producing works like 'Antibes Seen from "
                    "the Salis Gardens'. The headland's pine trees and rocky shoreline "
                    "became iconic subjects of Impressionism."
                ),
            },
            {
                'name': "Eze Village",
                'description': (
                    "In 1706, Louis XIV ordered the destruction of Eze Village's "
                    "fortifications during the War of the Spanish Succession. The "
                    "medieval ramparts were razed, leaving only ruins of the castle "
                    "atop the 429-metre peak. The exotic garden now occupies the "
                    "former fortress site."
                ),
            },
        ]

        errors = check_part4_attribution(part4_text, stop_data)
        assert errors == [], (
            f"The prompt's own worked example must PASS (no false positives), "
            f"but got: {errors}"
        )

    # ── D373's actual bug: Moses content → "Au Soleil du Plafond" ───────────

    def test_d373_misattribution_fails(self):
        """D373 bug: Moses and Monotheism content attributed to Au Soleil du Plafond.

        Text says "Freud's 1939 Moses and Monotheism at Au Soleil du Plafond"
        but 1939 belongs to the Moses stop, not Au Soleil. Must FAIL.
        """
        part4_text = (
            "In the stops ahead, you will discover Freud's 1939 Moses and Monotheism "
            "at Au Soleil du Plafond and Matisse's vibrant paper cut-outs at Chapelle du Rosaire."
        )
        stop_data = [
            {
                'name': "Au Soleil du Plafond",
                'description': (
                    "Marc Chagall's monumental ceiling painting, commissioned in 1964, "
                    "depicts scenes from the Old Testament across 220 square metres. "
                    "The work took nearly two years to complete and was unveiled in the "
                    "Opéra Garnier's auditorium."
                ),
            },
            {
                'name': "Chapelle du Rosaire",
                'description': (
                    "Henri Matisse designed every element of the Chapelle du Rosaire "
                    "between 1948 and 1951. His vibrant paper cut-outs influenced the "
                    "stained glass windows that cast blue and yellow light across the "
                    "white-tiled interior."
                ),
            },
            {
                'name': "Moses and Monotheism",
                'description': (
                    "Sigmund Freud published Moses and Monotheism in 1939, his final "
                    "major work written in London exile. The book controversially argues "
                    "that Moses was Egyptian and that monotheism originated in Akhenaten's "
                    "religious revolution."
                ),
            },
        ]

        errors = check_part4_attribution(part4_text, stop_data)
        assert len(errors) > 0, (
            "D373 misattribution (1939 Moses content attributed to Au Soleil du Plafond) "
            "must FAIL, but check_part4_attribution returned no errors"
        )
        # Verify it identifies the right date and stop
        assert any("1939" in e and "Au Soleil" in e for e in errors), (
            f"Error must mention '1939' and 'Au Soleil du Plafond', got: {errors}"
        )

    # ── Neutralisation test: function must DO something ─────────────────────

    def test_not_trivially_empty(self):
        """If check_part4_attribution is neutralised to always return [], this fails.

        We feed it an obvious misattribution and demand at least one error.
        """
        # Simple case: "the 1500 event at StopA" but 1500 is in StopB's desc
        part4_text = "Discover the 1500 founding at StopAlpha and the 1800 expansion at StopBeta."
        stop_data = [
            {
                'name': 'StopAlpha',
                'description': 'StopAlpha was expanded significantly in 1800 by the local government.',
            },
            {
                'name': 'StopBeta',
                'description': 'StopBeta was founded in 1500 as a small trading post.',
            },
        ]
        errors = check_part4_attribution(part4_text, stop_data)
        assert len(errors) > 0, (
            "Obvious misattribution must produce errors — "
            "check_part4_attribution appears neutralised (returns [] unconditionally)"
        )


class TestShouldInjectVenueSnippet:
    """Venue-snippet injection decision function."""

    def test_venue_source_injects(self):
        """Non-third-party source with page_text > 50 chars → inject=True."""

        class FakeResult:
            is_third_party = False
            page_text = "A" * 200
            content_url = "https://museum.example.com/exhibition"
            exhibition_url = "https://museum.example.com/exhibition"

        result = should_inject_venue_snippet(FakeResult(), "Matisse Room")
        assert result['inject'] is True, (
            f"Venue source with sufficient page_text must inject, got: {result}"
        )
        assert result['snippet'] is not None
        assert 'Matisse Room' in result['snippet']['title']
        assert result['snippet']['snippet'] == "A" * 200

    def test_third_party_does_not_inject(self):
        """Third-party source → inject=False."""

        class FakeResult:
            is_third_party = True
            page_text = "A" * 200
            content_url = "https://review-site.com/exhibition"
            exhibition_url = "https://museum.example.com/exhibition"

        result = should_inject_venue_snippet(FakeResult(), "Matisse Room")
        assert result['inject'] is False, (
            f"Third-party source must NOT inject, got: {result}"
        )

    def test_short_page_text_does_not_inject(self):
        """Page text ≤ 50 chars → inject=False."""

        class FakeResult:
            is_third_party = False
            page_text = "Short"
            content_url = "https://museum.example.com/exhibition"
            exhibition_url = "https://museum.example.com/exhibition"

        result = should_inject_venue_snippet(FakeResult(), "Matisse Room")
        assert result['inject'] is False, (
            f"Short page_text must NOT inject, got: {result}"
        )

    def test_none_result_does_not_inject(self):
        """None input → inject=False."""
        result = should_inject_venue_snippet(None, "Matisse Room")
        assert result['inject'] is False

    def test_not_trivially_false(self):
        """If should_inject_venue_snippet is neutralised to always return inject=False, this fails.

        A valid venue source MUST produce inject=True.
        """

        class FakeResult:
            is_third_party = False
            page_text = "This exhibition features works by Henri Matisse from 1948 to 1951, " \
                        "including paper cut-outs and ceramic tiles designed for the chapel."
            content_url = "https://museum.example.com/matisse-exhibition"
            exhibition_url = "https://museum.example.com/matisse-exhibition"

        result = should_inject_venue_snippet(FakeResult(), "Matisse Chapel")
        assert result['inject'] is True, (
            "Valid venue source must inject=True — "
            "should_inject_venue_snippet appears neutralised (always returns False)"
        )


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v']))
