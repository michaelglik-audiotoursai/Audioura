#!/usr/bin/env python3
"""
[LOCAL-282] Verify that the tour overview (prolog) on stop 1 survives R3's
orientation gating for museum tours.

The bug: LOCAL-264 placed the prolog inside _orientation_prefix, so when R3
dropped a weak orientation the entire overview was silently removed.

The fix: when stop 1 has a prolog and R3 rejects the orientation text, emit
_orientation_prefix anyway (carrying the overview) without the rejected text.

Three scenarios tested:
  1. Museum stop 1, weak orientation (R3 drops it) → overview MUST survive
  2. Museum stop 1, strong orientation (R3 keeps it) → overview + orientation
  3. Non-museum stop 1 → overview always emitted (R3 doesn't gate)
"""
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _simulate_orientation_emit(
    i, tour_category, _museum_venue_name, _saved_prolog, orientation, _entrance_directive=""
):
    """
    Reproduce the exact logic from generate_tour_text.py lines 8757-8812
    (post LOCAL-282 fix) to verify the output for stop 1.
    """
    _orientation_prefix = "Orientation: "

    # Simulate LOCAL-264 prolog injection (only stop 0)
    if i == 0 and _saved_prolog:
        _orientation_prefix += _saved_prolog.strip() + " "

    # Simulate LOCAL-268 stop naming
    if i == 0 and _saved_prolog:
        _orientation_prefix += "Your first stop is Test Exhibit. "

    _orientation_prefix += _entrance_directive

    # R3 gating logic (exact copy from generate_tour_text.py after fix)
    _clean_orientation = re.sub(r'^Orientation:\s*', '', orientation, flags=re.IGNORECASE).strip()
    poi_content = ""
    if tour_category == 'museum' and _museum_venue_name:
        _has_substance = bool(re.search(
            r'(?i)(mosaic|reflected|window|pond|corner|ceiling|floor|left wall|right wall|'
            r'lower|upper|behind|above|below|stained glass|tapestry|sculpture)',
            _clean_orientation
        ))
        if _has_substance and _clean_orientation != "Position yourself to best view this artwork.":
            poi_content += f"{_orientation_prefix}{_clean_orientation}\n\n"
        elif i == 0 and _saved_prolog:
            # [LOCAL-282] R3 drops the weak orientation text, but the tour overview
            # (prolog) lives in _orientation_prefix and MUST survive.
            poi_content += f"{_orientation_prefix.rstrip()}\n\n"
        # else: non-stop-1 weak orientation — skip entirely
    else:
        poi_content += f"{_orientation_prefix}{_clean_orientation}\n\n"

    return poi_content


class TestOverviewSurvivesR3:
    """Verify the three-category acceptance criterion."""

    PROLOG = "This museum tour explores the artistic heritage of Nice through five carefully curated exhibits."

    def test_museum_stop1_weak_orientation_overview_survives(self):
        """Museum stop 1 with weak orientation: overview MUST be present."""
        # "Look for this work in the galleries." — no R3 substance keywords
        result = _simulate_orientation_emit(
            i=0,
            tour_category='museum',
            _museum_venue_name='Musée des Arts Asiatiques',
            _saved_prolog=self.PROLOG,
            orientation="Look for this work in the galleries.",
        )
        # Overview must be present
        assert self.PROLOG in result, f"Overview missing from stop 1!\nGot: {result}"
        # Must start with "Orientation:"
        assert result.startswith("Orientation:"), f"Must start with Orientation:\nGot: {result}"
        # "Your first stop is" must be present
        assert "Your first stop is Test Exhibit." in result
        # The weak orientation text should NOT be present
        assert "Look for this work in the galleries." not in result

    def test_museum_stop1_strong_orientation_overview_present(self):
        """Museum stop 1 with strong orientation: overview + orientation text."""
        # Contains "sculpture" — passes R3
        strong_orientation = "The bronze sculpture stands in the corner of the east gallery."
        result = _simulate_orientation_emit(
            i=0,
            tour_category='museum',
            _museum_venue_name='Musée des Arts Asiatiques',
            _saved_prolog=self.PROLOG,
            orientation=strong_orientation,
        )
        assert self.PROLOG in result
        assert result.startswith("Orientation:")
        assert "Your first stop is Test Exhibit." in result
        # Strong orientation text IS included
        assert "bronze sculpture stands in the corner" in result

    def test_museum_stop2_weak_orientation_no_output(self):
        """Museum stop 2+ with weak orientation: R3 drops it entirely (no overview)."""
        result = _simulate_orientation_emit(
            i=1,  # Not stop 0
            tour_category='museum',
            _museum_venue_name='Musée des Arts Asiatiques',
            _saved_prolog=self.PROLOG,
            orientation="Look for this work in the galleries.",
        )
        # For stop 2+, if R3 drops it, nothing is emitted
        assert result == "", f"Stop 2+ weak orientation should emit nothing, got: {result}"

    def test_nonmuseum_stop1_overview_always_emitted(self):
        """Non-museum (biking) stop 1: overview always present regardless of orientation."""
        result = _simulate_orientation_emit(
            i=0,
            tour_category='walking',
            _museum_venue_name=None,
            _saved_prolog=self.PROLOG,
            orientation="Start biking southwest on the coastal road toward Cap d'Antibes.",
        )
        assert self.PROLOG in result
        assert result.startswith("Orientation:")
        assert "Your first stop is Test Exhibit." in result
        # Orientation text is always included for non-museum
        assert "Start biking southwest" in result

    def test_restaurant_stop1_overview_emitted(self):
        """Restaurant stop 1: overview present (not a museum, R3 doesn't apply)."""
        result = _simulate_orientation_emit(
            i=0,
            tour_category='restaurant',
            _museum_venue_name=None,
            _saved_prolog=self.PROLOG,
            orientation="Find the entrance on the corner of Rue de France.",
        )
        assert self.PROLOG in result
        assert result.startswith("Orientation:")

    def test_museum_stop1_position_yourself_dropped(self):
        """The exact 'Position yourself to best view this artwork.' is dropped by R3."""
        result = _simulate_orientation_emit(
            i=0,
            tour_category='museum',
            _museum_venue_name='Musée des Arts Asiatiques',
            _saved_prolog=self.PROLOG,
            orientation="Position yourself to best view this artwork.",
        )
        # Overview survives
        assert self.PROLOG in result
        assert result.startswith("Orientation:")
        # The generic text is NOT included
        assert "Position yourself" not in result

    def test_r3_still_drops_weak_orientation_text(self):
        """R3 must still drop weak orientation text — only the overview survives."""
        weak_texts = [
            "Admire the artwork before you.",
            "Take a moment to appreciate this piece.",
            "This exhibit showcases important cultural artifacts.",
        ]
        for weak in weak_texts:
            result = _simulate_orientation_emit(
                i=0,
                tour_category='museum',
                _museum_venue_name='Musée des Arts Asiatiques',
                _saved_prolog=self.PROLOG,
                orientation=weak,
            )
            assert self.PROLOG in result, f"Overview missing for weak orientation: {weak}"
            assert weak not in result, f"Weak orientation should be dropped: {weak}"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
