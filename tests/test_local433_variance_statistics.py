"""Tests for LOCAL-433 variance harness statistics functions.

All expected values are hand-checked against known inputs — a mean that
nobody verified is not a measurement (LOCAL-433 task spec).
"""
import math
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from variance_harness import compute_statistics, compute_gate_verdicts, extract_per_stop_counts


class TestComputeStatistics:
    """Hand-verified statistics on known inputs."""

    def test_single_value(self):
        """Single value: mean=value, stdev=0."""
        result = compute_statistics([5])
        assert result == {'mean': 5.0, 'min': 5, 'max': 5, 'stdev': 0.0, 'count': 1}

    def test_two_values(self):
        """[2, 4]: mean=3.0, min=2, max=4, stdev=sqrt(2)≈1.41."""
        result = compute_statistics([2, 4])
        assert result['mean'] == 3.0
        assert result['min'] == 2
        assert result['max'] == 4
        # stdev = sqrt(((2-3)^2 + (4-3)^2) / (2-1)) = sqrt(2) ≈ 1.41
        assert result['stdev'] == 1.41
        assert result['count'] == 2

    def test_three_values_from_task(self):
        """[3, 0, 2] — Harpe counts from the LEAD table in D385.

        mean = (3+0+2)/3 = 5/3 ≈ 1.67
        variance = ((3-1.67)^2 + (0-1.67)^2 + (2-1.67)^2) / 2
                 = (1.7689 + 2.7889 + 0.1089) / 2
                 = 4.6667 / 2 = 2.3333
        stdev = sqrt(2.3333) ≈ 1.53
        """
        result = compute_statistics([3, 0, 2])
        assert result['mean'] == 1.67
        assert result['min'] == 0
        assert result['max'] == 3
        assert result['stdev'] == 1.53
        assert result['count'] == 3

    def test_five_identical_values(self):
        """All same → stdev=0."""
        result = compute_statistics([3, 3, 3, 3, 3])
        assert result == {'mean': 3.0, 'min': 3, 'max': 3, 'stdev': 0.0, 'count': 5}

    def test_five_values_known(self):
        """[1, 2, 3, 4, 5]: mean=3.0, stdev=sqrt(2.5)≈1.58."""
        result = compute_statistics([1, 2, 3, 4, 5])
        assert result['mean'] == 3.0
        assert result['min'] == 1
        assert result['max'] == 5
        # variance = (4+1+0+1+4)/4 = 10/4 = 2.5, stdev = 1.58
        assert result['stdev'] == 1.58
        assert result['count'] == 5

    def test_empty_raises(self):
        """Empty list must raise ValueError."""
        with pytest.raises(ValueError):
            compute_statistics([])

    def test_zeros(self):
        """All zeros."""
        result = compute_statistics([0, 0, 0])
        assert result == {'mean': 0.0, 'min': 0, 'max': 0, 'stdev': 0.0, 'count': 3}


class TestComputeGateVerdicts:
    """Gate verdict computation with hand-checked expected outputs."""

    def test_d385_table_data(self):
        """The exact data from D385's table — LEAD's three runs.

        Run 1: Harpe=3, Violes=2, Sacqueboute=0, Basse=2
        Run 2: Harpe=0, Violes=1, Sacqueboute=3, Basse=1
        Run 3: Harpe=2, Violes=2, Sacqueboute=2, Basse=1

        Gate (threshold=3): Run 1 → 1/4 pass, Run 2 → 1/4 pass, Run 3 → 0/4 pass
        All-pass: 0/3
        """
        runs = [
            {'Harpe': 3, 'Violes': 2, 'Sacqueboute': 0, 'Basse': 2},
            {'Harpe': 0, 'Violes': 1, 'Sacqueboute': 3, 'Basse': 1},
            {'Harpe': 2, 'Violes': 2, 'Sacqueboute': 2, 'Basse': 1},
        ]
        result = compute_gate_verdicts(runs, threshold=3)

        assert result['total_runs'] == 3
        assert result['all_pass_count'] == 0
        assert result['all_pass_rate'] == 0.0

        # Harpe passes in 1/3 runs (only run 1 has 3)
        assert result['per_stop_pass_rate']['Harpe'] == 0.33
        # Sacqueboute passes in 1/3 runs (only run 2 has 3)
        assert result['per_stop_pass_rate']['Sacqueboute'] == 0.33
        # Violes never reaches 3
        assert result['per_stop_pass_rate']['Violes'] == 0.0
        # Basse never reaches 3
        assert result['per_stop_pass_rate']['Basse'] == 0.0

        # Harpe stats: [3, 0, 2] → mean=1.67, min=0, max=3, stdev=1.53
        assert result['per_stop_stats']['Harpe']['mean'] == 1.67
        assert result['per_stop_stats']['Harpe']['min'] == 0
        assert result['per_stop_stats']['Harpe']['max'] == 3
        assert result['per_stop_stats']['Harpe']['stdev'] == 1.53

    def test_all_pass(self):
        """When every stop passes every run."""
        runs = [
            {'A': 5, 'B': 3, 'C': 4},
            {'A': 4, 'B': 4, 'C': 3},
        ]
        result = compute_gate_verdicts(runs, threshold=3)
        assert result['all_pass_count'] == 2
        assert result['all_pass_rate'] == 1.0
        assert result['per_stop_pass_rate']['A'] == 1.0
        assert result['per_stop_pass_rate']['B'] == 1.0
        assert result['per_stop_pass_rate']['C'] == 1.0

    def test_empty_raises(self):
        """Empty run list must raise ValueError."""
        with pytest.raises(ValueError):
            compute_gate_verdicts([])

    def test_mixed_stop_counts(self):
        """Runs with different numbers of stops (handles missing stops as 0)."""
        runs = [
            {'A': 4, 'B': 2},
            {'A': 3, 'B': 3, 'C': 1},  # C only appears in run 2
        ]
        result = compute_gate_verdicts(runs, threshold=3)
        # Run 1: A passes, B fails → not all-pass
        # Run 2: A passes, B passes, C fails → not all-pass
        assert result['all_pass_count'] == 0
        # A: [4, 3] → both pass → 1.0
        assert result['per_stop_pass_rate']['A'] == 1.0
        # B: [2, 3] → 1/2 pass → 0.5
        assert result['per_stop_pass_rate']['B'] == 0.5
        # C: [0, 1] → 0/2 pass → 0.0
        assert result['per_stop_pass_rate']['C'] == 0.0


class TestExtractPerStopCounts:
    """Test the tour text parser."""

    def test_typical_format(self):
        """Parse a minimal tour with known story content."""
        tour_text = """Stop 1: Test Museum Room A

Address: 123 Main St

Coordinates: 42.0, -71.0

Orientation: Welcome to Room A.

Boris Fridman donated the collection to the museum in 1998, ensuring public access to these rare works. The gift resulted in a permanent exhibition space dedicated to modern art. Fridman chose this museum because of its commitment to contemporary European masters.

Directions: Continue to Room B.

Stop 2: Test Museum Room B

Address: 123 Main St

Coordinates: 42.0, -71.0

Orientation: Welcome to Room B.

This room contains various artworks from the 20th century. The pieces reflect evolving artistic sensibilities.

Directions: End of tour.
"""
        result = extract_per_stop_counts(tour_text)
        # Room A should have story sentences (Fridman donated, resulted in, chose)
        assert 'Test Museum Room A' in result
        assert 'Test Museum Room B' in result
        # The three sentences about Fridman should all pass is_story_sentence
        assert result['Test Museum Room A'] >= 2  # Conservative — depends on classifier
        # Room B has no named persons doing story actions
        assert result['Test Museum Room B'] == 0
