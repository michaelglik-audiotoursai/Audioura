#!/usr/bin/env python3
"""LOCAL-313: Test dining verification with Nominatim/OSM fallback.

The six restaurants from the bug report — all real, operating restaurants in
Vieux Nice — must now verify via Wikipedia/Wikidata OR Nominatim/OSM.

Boundary cases:
  MUST verify:
    - La Rossettisserie (Old Nice)
    - Le Safari (Old Nice)
    - Chez Palmyre (Old Nice, since 1926)
    - Le Tire Bouchon (Old Nice)
    - Le Bistrot d'Antoine (Old Nice, Gault&Millau)
    - Le Vieux Four (Old Nice)
  MUST reject:
    - Le Restaurant Imaginaire (fabricated)
    - Le Chantecler in Lyon (wrong city — proximity constraint)
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_connection import get_connection, check_db_available
from stop_existence_gate import (
    verify_stop_existence,
    run_existence_gate,
)


@pytest.fixture(scope="module")
def db_conn():
    if not check_db_available():
        pytest.skip("Database unavailable")
    conn = get_connection()
    real_conn = getattr(conn, '_conn', conn)
    yield real_conn
    conn.close()


class TestOldNiceRestaurants:
    """LOCAL-313: The six restaurants that triggered the bug."""

    @pytest.mark.parametrize("stop_title", [
        "La Rossettisserie",
        "Le Safari",
        "Chez Palmyre",
        "Le Tire Bouchon",
        "Le Bistrot d'Antoine",
        "Le Vieux Four",
    ])
    def test_real_restaurant_verifies(self, db_conn, stop_title):
        """Each real Old Nice restaurant must verify."""
        result = verify_stop_existence(
            stop_title, 'Nice, France', db_conn, tour_type='restaurant'
        )
        assert result['verified'] is True, (
            f"{stop_title!r} should verify but got: "
            f"verified={result['verified']}, evidence={result['evidence']!r}"
        )
        assert result['venue_kind'] == 'dining'
        # Evidence must name a source
        assert result['evidence'], f"No evidence string for {stop_title!r}"
        print(f"  ✓ {stop_title}: {result['evidence']}")


class TestSafetyConstraints:
    """Fabricated and wrong-city restaurants must still fail."""

    def test_fabricated_name_fails(self, db_conn):
        """A completely invented restaurant name must not verify."""
        result = verify_stop_existence(
            'Le Restaurant Imaginaire',
            'Nice, France', db_conn, tour_type='restaurant'
        )
        assert result['verified'] is False
        assert result['venue_kind'] == 'dining'

    def test_wrong_city_fails(self, db_conn):
        """Le Chantecler verified in Nice but must FAIL for Lyon."""
        result = verify_stop_existence(
            'Le Chantecler', 'Lyon, France', db_conn, tour_type='restaurant'
        )
        assert result['verified'] is False

    def test_another_fabricated_name(self, db_conn):
        """Another invented name — different pattern."""
        result = verify_stop_existence(
            'Chez Monsieur Personne',
            'Nice, France', db_conn, tour_type='restaurant'
        )
        assert result['verified'] is False


class TestGateIntegration:
    """Full gate run with the Old Nice restaurant list."""

    def test_run_gate_old_nice(self, db_conn):
        """Run gate on all six — all should verify (zero dropped)."""
        os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
        stops = [
            "La Rossettisserie",
            "Le Safari",
            "Chez Palmyre",
            "Le Tire Bouchon",
            "Le Bistrot d'Antoine",
            "Le Vieux Four",
        ]
        result = run_existence_gate(stops, 'Nice, France', db_conn, tour_type='restaurant')
        assert result['action'] == 'ENFORCE'
        # All six should verify now
        assert len(result['verified_stops']) == 6, (
            f"Expected 6 verified, got {len(result['verified_stops'])}. "
            f"Unverified: {result['unverified_stops']}"
        )
        assert len(result['unverified_stops']) == 0
        print(f"  Gate: {len(result['verified_stops'])}/6 verified")
        for v in result['verdicts']:
            print(f"    {v['stop_title']}: {v['evidence']}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
