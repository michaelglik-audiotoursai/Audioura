#!/usr/bin/env python3
"""
LOCAL-253: Directions mode guard — transport mode reaches directions and
mode-inappropriate infrastructure is caught.

This test validates all seven boundary rows from the task specification:

MUST SURVIVE (navigation exempt from style rules, per D107):
1. "Start cycling south on the main road with the sea on your right."
2. "Head east along the coastal path until you reach the roundabout."
3. "Follow the signs up the hill to reach the village."

MUST BE CAUGHT (mode-inappropriate content on a biking tour):
4. "From Antibes train station, take a train towards Eze Village." (public transport)
5. "Continue east until you hit the A8 highway." (motorway)
6. "Start your walk from Cap d'Antibes." (wrong-mode verb)
7. "Enjoy the walk!" (wrong-mode verb)

Run with: python3 -m pytest tests/test_local253_directions_mode_guard.py -v -s
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from directions_generator import validate_directions_mode


class TestDirectionsModeGuard:
    """Boundary tests for the LOCAL-253 directions mode guard."""

    # ─── MUST SURVIVE (no violations) ────────────────────────────────────

    def test_survive_cycling_south(self):
        """D107 navigation exemption: cycling direction with movement verb."""
        text = "Start cycling south on the main road with the sea on your right."
        violations = validate_directions_mode(text, "bike")
        assert violations == [], f"Should survive but got: {violations}"

    def test_survive_head_east(self):
        """D107 navigation exemption: generic direction without mode verb."""
        text = "Head east along the coastal path until you reach the roundabout."
        violations = validate_directions_mode(text, "bike")
        assert violations == [], f"Should survive but got: {violations}"

    def test_survive_follow_signs(self):
        """D107 navigation exemption: generic direction without mode verb."""
        text = "Follow the signs up the hill to reach the village."
        violations = validate_directions_mode(text, "bike")
        assert violations == [], f"Should survive but got: {violations}"

    # ─── MUST BE CAUGHT (violations detected) ────────────────────────────

    def test_catch_train_on_biking_tour(self):
        """Public transport on a biking tour: train suggestion rejected."""
        text = "From Antibes train station, take a train towards Eze Village."
        violations = validate_directions_mode(text, "bike")
        assert len(violations) >= 1, f"Should be caught but passed: {text}"
        assert any("PUBLIC_TRANSPORT" in v for v in violations), \
            f"Expected PUBLIC_TRANSPORT violation, got: {violations}"

    def test_catch_a8_motorway_on_biking_tour(self):
        """Motorway on a biking tour: A8 highway rejected."""
        text = "Continue east until you hit the A8 highway."
        violations = validate_directions_mode(text, "bike")
        assert len(violations) >= 1, f"Should be caught but passed: {text}"
        # Should catch BOTH A8 and highway
        violation_text = " ".join(violations)
        assert "MOTORWAY" in violation_text, \
            f"Expected MOTORWAY violation, got: {violations}"

    def test_catch_start_your_walk_on_biking_tour(self):
        """Wrong-mode verb: 'Start your walk' on a biking tour."""
        text = "Start your walk from Cap d'Antibes."
        violations = validate_directions_mode(text, "bike")
        assert len(violations) >= 1, f"Should be caught but passed: {text}"
        assert any("WRONG_MODE_VERB" in v for v in violations), \
            f"Expected WRONG_MODE_VERB violation, got: {violations}"

    def test_catch_enjoy_the_walk_on_biking_tour(self):
        """Wrong-mode verb: 'Enjoy the walk!' on a biking tour."""
        text = "Enjoy the walk!"
        violations = validate_directions_mode(text, "bike")
        assert len(violations) >= 1, f"Should be caught but passed: {text}"
        assert any("WRONG_MODE_VERB" in v for v in violations), \
            f"Expected WRONG_MODE_VERB violation, got: {violations}"

    # ─── Additional boundary coverage ────────────────────────────────────

    def test_empty_text_no_violations(self):
        """Empty directions should not trigger violations."""
        assert validate_directions_mode("", "bike") == []

    def test_no_mode_no_violations(self):
        """No transport mode should not trigger violations."""
        assert validate_directions_mode("Take a train to Paris.", "") == []

    def test_motorway_ok_for_vehicle(self):
        """Motorways are fine for vehicle tours."""
        text = "Continue east on the A8 highway towards Nice."
        violations = validate_directions_mode(text, "vehicle")
        assert violations == [], f"Vehicle mode should allow highways, got: {violations}"

    def test_walking_verbs_ok_for_walking(self):
        """Walking verbs are fine on walking tours."""
        text = "Start your walk from Cap d'Antibes towards the lighthouse."
        violations = validate_directions_mode(text, "on_foot")
        assert violations == [], f"Walking mode should allow walk verbs, got: {violations}"

    def test_autoroute_caught_on_bike(self):
        """French autoroute name caught on cycling tour."""
        text = "Merge onto the autoroute heading east."
        violations = validate_directions_mode(text, "bike")
        assert len(violations) >= 1
        assert any("MOTORWAY" in v for v in violations)

    def test_bus_caught_on_bike(self):
        """Bus suggestion caught on cycling tour."""
        text = "Take a bus from the town centre to the village."
        violations = validate_directions_mode(text, "bike")
        assert len(violations) >= 1
        assert any("PUBLIC_TRANSPORT" in v for v in violations)

    def test_pedal_along_ok_for_bike(self):
        """Cycling verbs should survive on bike tours."""
        text = "Pedal along the coastal road towards Nice, passing the marina on your left."
        violations = validate_directions_mode(text, "bike")
        assert violations == [], f"Cycling verb should pass on bike tour, got: {violations}"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v", "-s"]))
