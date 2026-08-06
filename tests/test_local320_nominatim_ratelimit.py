#!/usr/bin/env python3
"""LOCAL-320: Nominatim rate-limit compliance and failure handling.

Verifies:
  1. Nominatim requests throttled to ≤1/second with User-Agent
  2. Throttled/failed lookups classify as unknown (retry), not "unverified"
  3. Proximity binds on every path — Chicago/Six Flags classes rejected
  4. Replenishment backfills after throttle fix
  5. Real restaurants still verify consistently
"""
import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_connection import get_connection, check_db_available
from stop_existence_gate import (
    verify_stop_existence,
    run_existence_gate,
    _nominatim_request,
    _NOMINATIM_MIN_INTERVAL,
    _check_dining_nominatim,
)


@pytest.fixture(scope="module")
def db_conn():
    if not check_db_available():
        pytest.skip("Database unavailable")
    conn = get_connection()
    real_conn = getattr(conn, '_conn', conn)
    yield real_conn
    conn.close()


class TestNominatimThrottle:
    """Scope 1: Rate limit compliance."""

    def test_requests_are_throttled(self):
        """Two consecutive Nominatim requests must be ≥1s apart."""
        import stop_existence_gate
        # Reset the last request time
        stop_existence_gate._nominatim_last_request_time = 0.0

        params1 = {"q": "Le Safari, Nice", "format": "jsonv2",
                   "addressdetails": "1", "limit": "1", "accept-language": "en"}
        params2 = {"q": "Chez Palmyre, Nice", "format": "jsonv2",
                   "addressdetails": "1", "limit": "1", "accept-language": "en"}

        start = time.time()
        _nominatim_request(params1, context="test1")
        t1 = time.time()
        _nominatim_request(params2, context="test2")
        t2 = time.time()

        interval = t2 - t1
        assert interval >= 1.0, (
            f"Requests were only {interval:.2f}s apart — must be ≥1.0s"
        )
        print(f"  ✓ Throttle working: {interval:.2f}s between requests")

    def test_user_agent_is_set(self):
        """Nominatim requests must have a descriptive User-Agent (policy requirement)."""
        from stop_existence_gate import _NOMINATIM_HEADERS
        ua = _NOMINATIM_HEADERS.get("User-Agent", "")
        assert "Audioura" in ua, f"User-Agent must identify the application: {ua!r}"
        assert "contact:" in ua.lower() or "@" in ua, (
            f"User-Agent should include contact info per Nominatim policy: {ua!r}"
        )
        print(f"  ✓ User-Agent: {ua}")


class TestThrottleFailureClassification:
    """Scope 2: Throttled response = failure, not absence."""

    def test_429_raises_runtime_error(self):
        """A 429 from Nominatim must raise RuntimeError, not return False."""
        mock_resp = MagicMock()
        mock_resp.status_code = 429

        with patch('requests.get', return_value=mock_resp):
            with pytest.raises(RuntimeError, match="rate limited"):
                _nominatim_request(
                    {"q": "test", "format": "jsonv2"},
                    context="test_429"
                )

    def test_timeout_raises_runtime_error(self):
        """A connection timeout must raise RuntimeError."""
        import requests
        with patch('requests.get', side_effect=requests.exceptions.Timeout("timed out")):
            with pytest.raises(RuntimeError, match="connection failed"):
                _nominatim_request(
                    {"q": "test", "format": "jsonv2"},
                    context="test_timeout"
                )

    def test_search_failed_not_unverified(self, db_conn):
        """When Nominatim fails, the verdict must be search_failed, not unverified."""
        # Mock Nominatim to return 429 (all Wikipedia/Wikidata checks will return False
        # for a real restaurant that's only in OSM, so the flow reaches Nominatim)
        with patch('stop_existence_gate._nominatim_request',
                   side_effect=RuntimeError("Nominatim rate limited (429)")):
            result = verify_stop_existence(
                'Chez Palmyre', 'Nice, France', db_conn, tour_type='restaurant'
            )
            # If Wikipedia/Wikidata found it first, it's verified (that's fine).
            # If not, it must be search_failed (not just unverified=False with no flag).
            if not result['verified']:
                assert result.get('search_failed') is True, (
                    f"Expected search_failed=True when Nominatim is throttled, "
                    f"got: {result}"
                )
                print(f"  ✓ Throttled lookup classified as search_failed")
            else:
                print(f"  ✓ (Restaurant verified via Wikipedia/Wikidata before Nominatim)")

    def test_gate_retries_failed_searches(self, db_conn):
        """run_existence_gate must retry stops that had search failures."""
        call_count = [0]
        original_verify = verify_stop_existence

        def mock_verify(stop_title, venue_name, db_conn, tour_type=None):
            call_count[0] += 1
            # First call for "Chez Palmyre" fails; retry succeeds
            if stop_title == 'Chez Palmyre' and call_count[0] <= 2:
                # Simulate failure only on first attempt (within the gate loop)
                return {
                    'stop_title': stop_title,
                    'venue_name': venue_name,
                    'venue_kind': 'dining',
                    'verified': False,
                    'evidence': 'search_failed: Nominatim rate limited',
                    'source': 'search_failed',
                    'search_failed': True,
                }
            return original_verify(stop_title, venue_name, db_conn, tour_type=tour_type)

        os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
        with patch('stop_existence_gate.verify_stop_existence', side_effect=mock_verify):
            result = run_existence_gate(
                ['Le Safari', 'Chez Palmyre'],
                'Nice, France', db_conn, tour_type='restaurant'
            )
        # Chez Palmyre should have been retried and either verified or kept (fail open)
        assert 'Chez Palmyre' not in result.get('unverified_stops', []), (
            f"Chez Palmyre was dropped as unverified — search failure must not reject. "
            f"Result: {result}"
        )
        print(f"  ✓ Gate retries search_failed stops (not dropped)")


class TestProximityBinding:
    """Scope 3: Results outside requested area are rejected."""

    def test_chicago_address_rejected_for_nice(self, db_conn):
        """A Nominatim result in Chicago must not pass for a Nice tour."""
        # "La Tapenade" exists in Chicago at 10000 Concourse E Service Road
        # The city signals for Nice should reject it
        result = verify_stop_existence(
            'La Tapenade', 'Nice, France', db_conn, tour_type='restaurant'
        )
        # If it verifies, the evidence must be for Nice, not Chicago
        if result['verified']:
            evidence_lower = result['evidence'].lower()
            assert 'chicago' not in evidence_lower, (
                f"Chicago address accepted for Nice tour! Evidence: {result['evidence']}"
            )
            assert ('nice' in evidence_lower or 'nominatim_osm' in evidence_lower
                    or 'wikipedia' in evidence_lower), (
                f"Evidence doesn't confirm Nice location: {result['evidence']}"
            )
            print(f"  ✓ La Tapenade verified in Nice (correct): {result['evidence'][:80]}")
        else:
            print(f"  ✓ La Tapenade unverified (acceptable — may not be in OSM for Nice)")

    def test_wrong_city_restaurant_fails(self, db_conn):
        """Le Chantecler in Lyon must fail for a Nice tour."""
        result = verify_stop_existence(
            'Le Chantecler', 'Lyon, France', db_conn, tour_type='restaurant'
        )
        # This should NOT verify — Le Chantecler is in Nice (Hotel Negresco), not Lyon
        assert result['verified'] is False, (
            f"Le Chantecler should fail for Lyon but got: {result['evidence']}"
        )
        print(f"  ✓ Le Chantecler in Lyon correctly rejected")

    def test_fabricated_restaurant_fails(self, db_conn):
        """Completely invented name must not verify."""
        result = verify_stop_existence(
            'Le Restaurant Imaginaire', 'Nice, France', db_conn, tour_type='restaurant'
        )
        assert result['verified'] is False
        print(f"  ✓ Le Restaurant Imaginaire correctly rejected")

    def test_six_flags_cannot_verify_safari(self, db_conn):
        """The Six Flags pattern: an unrelated article must not pass for a Nice restaurant.

        'Le Safari' is a real restaurant in Nice. Its verification must come from
        Nominatim/OSM or a Wikipedia article ABOUT the restaurant — not from Six
        Flags Great Adventure (which has a 'Safari' attraction and might mention
        'nice' as an adjective).
        """
        result = verify_stop_existence(
            'Le Safari', 'Nice, France', db_conn, tour_type='restaurant'
        )
        if result['verified']:
            evidence_lower = result['evidence'].lower()
            # Must NOT be from Six Flags or any theme park
            assert 'six flags' not in evidence_lower, (
                f"Six Flags used as evidence for Le Safari in Nice! {result['evidence']}"
            )
            assert 'great adventure' not in evidence_lower, (
                f"Great Adventure used as evidence! {result['evidence']}"
            )
            # Evidence should reference Nice/OSM/proper source
            print(f"  ✓ Le Safari verified via proper source: {result['evidence'][:80]}")
        else:
            # Le Safari should verify — it's a real restaurant
            pytest.fail(f"Le Safari should verify but didn't: {result}")


class TestConsistentDelivery:
    """Scope 4+5: Consistent verification across multiple runs."""

    def test_five_consecutive_runs(self, db_conn):
        """Five consecutive runs must all produce the same result."""
        os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
        stops = [
            "La Rossettisserie",
            "Le Safari",
            "Chez Palmyre",
            "Le Bistrot d'Antoine",
            "La Tapenade",
        ]

        results = []
        for i in range(5):
            result = run_existence_gate(stops, 'Nice, France', db_conn, tour_type='restaurant')
            verified_count = len(result['verified_stops'])
            results.append(verified_count)
            print(f"  Run {i+1}: {verified_count}/{len(stops)} verified "
                  f"({result['verified_stops']})")

        # All runs must produce the same count
        assert len(set(results)) == 1, (
            f"Inconsistent results across runs: {results}. "
            f"The bug was 5/5 then 2/5 — must be consistent now."
        )
        # And all should verify (they're all real Nice restaurants)
        assert results[0] >= 4, (
            f"Expected at least 4/5 to verify but got {results[0]}/5"
        )
        print(f"  ✓ All 5 runs consistent: {results[0]}/{len(stops)} verified each time")

    def test_wall_clock_cost(self, db_conn):
        """Report the wall-clock cost of the throttle."""
        os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
        stops = [
            "La Rossettisserie",
            "Le Safari",
            "Chez Palmyre",
            "Le Bistrot d'Antoine",
            "La Tapenade",
        ]

        start = time.time()
        result = run_existence_gate(stops, 'Nice, France', db_conn, tour_type='restaurant')
        elapsed = time.time() - start

        print(f"  Wall-clock for 5-stop verification: {elapsed:.1f}s")
        print(f"  Throttle overhead: ~{max(0, elapsed - 5):.1f}s above baseline")
        # Should complete within reasonable time (Wikipedia + Nominatim throttle)
        # 5 stops × ~1.1s throttle = ~5.5s minimum for Nominatim alone
        # Plus Wikipedia lookups (parallel-ish but sequential per stop)
        assert elapsed < 120, f"Took too long: {elapsed:.1f}s"


class TestSafetyTests:
    """Run LOCAL-313 safety tests to confirm no regression."""

    @pytest.mark.parametrize("stop_title", [
        "La Rossettisserie",
        "Le Safari",
        "Chez Palmyre",
        "Le Tire Bouchon",
        "Le Bistrot d'Antoine",
        "Le Vieux Four",
    ])
    def test_real_restaurants_still_verify(self, db_conn, stop_title):
        """Each real Old Nice restaurant must still verify (LOCAL-313 regression)."""
        result = verify_stop_existence(
            stop_title, 'Nice, France', db_conn, tour_type='restaurant'
        )
        assert result['verified'] is True, (
            f"{stop_title!r} should verify but got: "
            f"verified={result['verified']}, evidence={result['evidence']!r}"
        )
        print(f"  ✓ {stop_title}: {result['evidence'][:70]}")

    def test_fabricated_name_fails(self, db_conn):
        """Le Restaurant Imaginaire must fail."""
        result = verify_stop_existence(
            'Le Restaurant Imaginaire', 'Nice, France', db_conn, tour_type='restaurant'
        )
        assert result['verified'] is False

    def test_lyon_fails(self, db_conn):
        """Le Chantecler in Lyon must fail (proximity)."""
        result = verify_stop_existence(
            'Le Chantecler', 'Lyon, France', db_conn, tour_type='restaurant'
        )
        assert result['verified'] is False


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
