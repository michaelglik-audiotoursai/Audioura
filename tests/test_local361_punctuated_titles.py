"""
LOCAL-361: Punctuated title stop loss.

These tests import and call the PRODUCTION functions
(`f3_name_is_corrupt`, `missing_stop_headers`) from generate_tour_text.py.

The original submission for this ticket tested an inline copy of the F3 logic
plus `inspect.getsource` string assertions; all 25 cases passed with
generate_tour_text.py fully reverted, so they were not evidence. LEAD lifted the
logic to module scope (2026-08-10) specifically so it could be driven directly.

Verified red/green: reverting f3_name_is_corrupt to the old
`any(c in poi_name for c in '.!?;')` turns every case in
TestF3KeepsRealTitles red.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generate_tour_text import f3_name_is_corrupt, missing_stop_headers  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════════
# F3 guard — real titles must survive
# ═══════════════════════════════════════════════════════════════════════════════

class TestF3KeepsRealTitles:
    """Punctuation is not corruption. Every one of these is a real artwork."""

    @pytest.mark.parametrize("title", [
        "Where Do We Come From? What Are We? Where Are We Going?",  # D274, the reported bug
        "Whaam!",
        "No. 14, 1960",
        "St. Jerome in His Study",
        "Mr. and Mrs. Andrews",
        "L.H.O.O.Q.",
        "Who's Afraid of Red, Yellow and Blue III",
        "Ecce Homo Triptych",
        "Untitled (Violet, Black, Orange, Yellow on White and Red)",
    ])
    def test_verified_title_kept(self, title):
        assert f3_name_is_corrupt(title, verified=True) is False

    @pytest.mark.parametrize("title", [
        "Where Do We Come From? What Are We? Where Are We Going?",
        "Whaam!",
        "No. 14, 1960",
        "St. Jerome in His Study",
    ])
    def test_unverified_real_title_also_kept(self, title):
        """Capitalization after punctuation keeps real titles safe even unverified."""
        assert f3_name_is_corrupt(title, verified=False) is False


# ═══════════════════════════════════════════════════════════════════════════════
# F3 guard — injected prose must still be caught
# ═══════════════════════════════════════════════════════════════════════════════

class TestF3CatchesInjection:
    """The guard's purpose (catching GPT prose in the name field) still works."""

    @pytest.mark.parametrize("title", [
        "This beautiful painting depicts the River Thames. the artist captured light",
        "The Water Lilies. this work was painted late in Monet's life",
        "This is the museum's most famous piece",
        "Welcome to the second stop on our tour",
        "Here we see the artist's early period",
        "In this gallery you will find the Impressionists",
    ])
    def test_unverified_injection_flagged(self, title):
        assert f3_name_is_corrupt(title, verified=False) is True

    def test_overlong_name_flagged_even_when_verified(self):
        """The length ceiling is provenance-independent — it protects TTS."""
        long_name = " ".join(["Word"] * 20)
        assert f3_name_is_corrupt(long_name, verified=True) is True
        assert f3_name_is_corrupt(long_name, verified=False) is True

    def test_verified_exemption_is_real(self):
        """A verified name skips the shape heuristics — documents the tradeoff."""
        injected = "This is the museum's most famous piece"
        assert f3_name_is_corrupt(injected, verified=False) is True
        assert f3_name_is_corrupt(injected, verified=True) is False


# ═══════════════════════════════════════════════════════════════════════════════
# Stop-heading survival invariant
# ═══════════════════════════════════════════════════════════════════════════════

class TestMissingStopHeaders:
    """The invariant that would have caught the 7-of-8 delivery in D274."""

    def test_all_headers_present(self):
        rendered = ["Stop 1: The Water Lilies", "Stop 2: Whaam!"]
        tour = "Intro\n\nStop 1: The Water Lilies\n\nbody\n\nStop 2: Whaam!\n\nbody"
        assert missing_stop_headers(tour, rendered) == []

    def test_dropped_header_detected(self):
        """A vanished stop is reported by name, not just as a count."""
        rendered = ["Stop 1: The Water Lilies", "Stop 2: Whaam!"]
        tour = "Intro\n\nStop 1: The Water Lilies\n\nbody"
        assert missing_stop_headers(tour, rendered) == ["Stop 2: Whaam!"]

    def test_body_line_starting_with_stop_n_is_not_a_false_positive(self):
        """
        Counting `^Stop \\d+:` lines would see 3 headings for 2 stops here and
        hard-fail a perfectly good tour. Non-storied mode does not run the D2
        cleanup that rewrites these body references.
        """
        rendered = ["Stop 1: The Water Lilies", "Stop 2: Whaam!"]
        tour = (
            "Stop 1: The Water Lilies\n\n"
            "As you saw at Stop 1: the light shifts here.\n\n"
            "Stop 2: Whaam!\n\nbody"
        )
        assert missing_stop_headers(tour, rendered) == []

    def test_punctuated_title_header_survives(self):
        """The end-to-end shape of the D274 bug: a '?' title must stay."""
        gauguin = "Stop 3: Where Do We Come From? What Are We? Where Are We Going?"
        rendered = ["Stop 1: A", "Stop 2: B", gauguin]
        tour = f"Stop 1: A\n\nx\n\nStop 2: B\n\ny\n\n{gauguin}\n\nz"
        assert missing_stop_headers(tour, rendered) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
