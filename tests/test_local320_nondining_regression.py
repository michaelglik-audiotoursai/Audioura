#!/usr/bin/env python3
"""LOCAL-320 ADDENDUM: Non-dining regression evidence.

Proves that LOCAL-320 changes (Nominatim throttle, Wikipedia article tightening,
failure→unknown classification) do NOT affect museum, walking, or cycling tours.

The affected code lives entirely inside _check_dining_existence() (line 832 of
stop_existence_gate.py). That function is called only from verify_stop_existence()
when venue_kind == 'dining'. Cycling/walking classify as 'geographic_area' and
museums classify as 'institution' — neither ever reaches Nominatim.

This test proves confinement by execution, not just inspection.
"""
import os
import sys
import time
import pytest

# This test reads venue_corpus and stop_corpus which only exist in production DB.
# It does NOT write. Safe to target production for reads.
# LOCAL-325: Scoped via autouse fixture instead of module-scope assignment to
# prevent env pollution across test files in the same pytest session.

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_connection import get_connection, check_db_available
from stop_existence_gate import (
    run_existence_gate,
    verify_stop_existence,
    _classify_venue_kind,
)


@pytest.fixture(autouse=True, scope="module")
def _force_production_db(monkeypatch_module):
    """Route this module to production DB (read-only) without polluting other modules."""
    monkeypatch_module.setenv('AUDIOURA_DB_TARGET', 'production')
    yield


@pytest.fixture(scope="module")
def monkeypatch_module():
    """Module-scoped monkeypatch (pytest's monkeypatch is function-scoped)."""
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="module")
def db_conn(_force_production_db):
    if not check_db_available():
        pytest.skip("Database unavailable")
    conn = get_connection()
    real_conn = getattr(conn, '_conn', conn)
    yield real_conn
    conn.close()


class TestCyclingTourRegression:
    """Cycling tours classify as geographic_area → never touch Nominatim."""

    def test_2stop_riviera_cycling_classification(self, db_conn):
        """2-stop Riviera cycling tour: venue classifies as geographic_area."""
        venue_kind, evidence = _classify_venue_kind(
            'French Riviera walking area', db_conn, tour_type='biking'
        )
        # 'biking' is NOT in the dining keywords, so it falls through to
        # the venue_corpus check. French Riviera walking area has no
        # sparql_works_json → geographic_area.
        assert venue_kind == 'geographic_area', (
            f"Expected geographic_area, got {venue_kind!r} ({evidence})"
        )
        print(f"  ✓ Riviera cycling classifies as: {venue_kind} ({evidence})")

    def test_2stop_riviera_cycling_gate(self, db_conn):
        """2-stop Riviera cycling tour: 2/2 stops verified, no Nominatim."""
        os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
        stops = ['Île Sainte-Marguerite', 'Cap d\'Antibes']

        start = time.time()
        result = run_existence_gate(
            stops, 'French Riviera walking area', db_conn, tour_type='biking'
        )
        elapsed = time.time() - start

        verified = result['verified_stops']
        unverified = result['unverified_stops']
        print(f"  2-stop Riviera cycling: {len(verified)}/{len(stops)} verified "
              f"in {elapsed:.1f}s")
        print(f"    Verified: {verified}")
        if unverified:
            print(f"    Unverified: {unverified}")

        assert len(verified) == 2, (
            f"Expected 2/2 verified, got {len(verified)}/2. "
            f"Unverified: {unverified}"
        )
        # Should be fast — no Nominatim throttle involved
        assert elapsed < 30, f"Took {elapsed:.1f}s — too slow for geographic gate"
        print(f"  ✓ 2/2 stops verified (baseline: 2/2)")

    def test_8stop_riviera_cycling_gate(self, db_conn):
        """8-stop Riviera cycling tour: 8/8 stops verified."""
        os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
        stops = [
            'Île Sainte-Marguerite',
            'Villa Ephrussi de Rothschild',
            'Cap d\'Antibes',
            'Monaco Grand Prix Circuit',
            'Jardin Exotique de Monaco',
            'La Croisette',
            'Port Vauban',
            'Chapelle Saint-Pierre',
        ]

        start = time.time()
        result = run_existence_gate(
            stops, 'French Riviera walking area', db_conn, tour_type='biking'
        )
        elapsed = time.time() - start

        verified = result['verified_stops']
        unverified = result['unverified_stops']
        print(f"  8-stop Riviera cycling: {len(verified)}/{len(stops)} verified "
              f"in {elapsed:.1f}s")
        print(f"    Verified: {verified}")
        if unverified:
            print(f"    Unverified: {unverified}")

        assert len(verified) == 8, (
            f"Expected 8/8 verified, got {len(verified)}/8. "
            f"Unverified: {unverified}"
        )
        print(f"  ✓ 8/8 stops verified (baseline: 8/8, LOCAL-290)")


class TestMuseumTourRegression:
    """Museum tours classify as institution → never touch Nominatim."""

    def test_museum_classification(self, db_conn):
        """Musée des Arts Asiatiques classifies as institution."""
        venue_kind, evidence = _classify_venue_kind(
            'Musee des Arts Asiatiques, Nice, France', db_conn, tour_type='museum'
        )
        # Museum has sparql_works_json → institution
        assert venue_kind == 'institution', (
            f"Expected institution, got {venue_kind!r} ({evidence})"
        )
        print(f"  ✓ Museum classifies as: {venue_kind} ({evidence})")

    def test_8stop_museum_gate(self, db_conn):
        """8-stop museum tour: 8/8 stops verified via venue_corpus."""
        os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
        stops = [
            'Kannon, le bodhisattva de la compassion',
            'Masque du vieillard kojo',
            'Ulysses Grant au Japon',
            'Kannon a mille bras',
            'La danse cosmique de Ganesh',
            'Robe de pretre taoiste',
            "L'Armure d'Ando Naoyuki",
            'Statue de Bouddha',
        ]

        start = time.time()
        result = run_existence_gate(
            stops, 'Musee des Arts Asiatiques, Nice, France', db_conn,
            tour_type='museum'
        )
        elapsed = time.time() - start

        verified = result['verified_stops']
        unverified = result['unverified_stops']
        print(f"  8-stop museum tour: {len(verified)}/{len(stops)} verified "
              f"in {elapsed:.1f}s")
        print(f"    Verified: {verified}")
        if unverified:
            print(f"    Unverified: {unverified}")

        # Baseline: 8/8 stops, base 75.0-81.2 across 4 draws
        assert len(verified) == 8, (
            f"Expected 8/8 verified, got {len(verified)}/8. "
            f"Unverified: {unverified}. "
            f"This is a REGRESSION from LOCAL-320!"
        )
        # Should be very fast — just database lookups, no external API
        assert elapsed < 15, f"Took {elapsed:.1f}s — should be <15s for DB-only path"
        print(f"  ✓ 8/8 stops verified (baseline: 8/8, 75.0-81.2)")


class TestCodePathConfinement:
    """Prove LOCAL-320 changes are confined to the dining path."""

    def test_geographic_area_never_calls_nominatim(self, db_conn):
        """Verify geographic_area path does not call _check_dining_existence."""
        from unittest.mock import patch

        with patch('stop_existence_gate._check_dining_existence') as mock_dining:
            mock_dining.side_effect = AssertionError(
                "REGRESSION: _check_dining_existence called for geographic tour!"
            )
            # This should succeed without ever calling _check_dining_existence
            result = verify_stop_existence(
                'Île Sainte-Marguerite', 'French Riviera walking area',
                db_conn, tour_type='biking'
            )
            assert result['verified'] is True, (
                f"Stop should verify via geographic path: {result}"
            )
            mock_dining.assert_not_called()
            print(f"  ✓ Geographic path never called _check_dining_existence")
            print(f"    Source: {result['source']}, Evidence: {result['evidence'][:60]}")

    def test_institution_never_calls_nominatim(self, db_conn):
        """Verify institution path does not call _check_dining_existence."""
        from unittest.mock import patch

        with patch('stop_existence_gate._check_dining_existence') as mock_dining:
            mock_dining.side_effect = AssertionError(
                "REGRESSION: _check_dining_existence called for museum tour!"
            )
            result = verify_stop_existence(
                'Ulysses Grant au Japon',
                'Musee des Arts Asiatiques, Nice, France',
                db_conn, tour_type='museum'
            )
            assert result['verified'] is True, (
                f"Stop should verify via institution path: {result}"
            )
            mock_dining.assert_not_called()
            print(f"  ✓ Institution path never called _check_dining_existence")
            print(f"    Source: {result['source']}, Evidence: {result['evidence'][:60]}")

    def test_dining_does_call_nominatim(self, db_conn):
        """Confirm the dining path DOES reach the affected code (positive control)."""
        from unittest.mock import patch

        # Use a restaurant that is ONLY in OSM (not Wikipedia/Wikidata)
        # If it verifies, it went through Nominatim
        result = verify_stop_existence(
            'La Rossettisserie', 'Nice, France', db_conn, tour_type='restaurant'
        )
        assert result['verified'] is True
        # Should verify via nominatim_osm (not Wikipedia)
        assert 'nominatim_osm' in result.get('evidence', ''), (
            f"Expected Nominatim evidence, got: {result['evidence']}"
        )
        print(f"  ✓ Dining path reaches Nominatim: {result['evidence'][:60]}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
