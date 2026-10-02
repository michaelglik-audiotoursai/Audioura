#!/usr/bin/env python3
"""
Tests for amenities_near_service.py (LOCAL-337).

Tests verify:
  1. Three states are distinguishable: found / none_found / service_unavailable
  2. Museum tour exclusion
  3. Rate-limit compliance (interval between calls)
  4. Landmark hint returned when available
  5. Invalid parameters rejected
  6. D162: throttled lookup never reported as "no water nearby"

Per D242: these tests import the PRODUCTION module and can fail against a
broken version.
"""
import json
import math
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

# Import the actual production module
sys.path.insert(0, "/Users/micha/audioura-worktrees/LOCAL-337")
import amenities_near_service


@pytest.fixture
def client():
    """Flask test client for amenities_near_service."""
    amenities_near_service.app.config['TESTING'] = True
    with amenities_near_service.app.test_client() as c:
        yield c


# ──── Unit: haversine ────────────────────────────────────────────────────────

class TestHaversine:
    def test_same_point_is_zero(self):
        assert amenities_near_service.haversine_metres(43.0, 7.0, 43.0, 7.0) == 0.0

    def test_known_distance(self):
        # Nice Old Town to Nice port is roughly 800m
        dist = amenities_near_service.haversine_metres(43.6961, 7.2758, 43.6945, 7.2850)
        assert 700 < dist < 1000


# ──── Three states ───────────────────────────────────────────────────────────

class TestThreeStates:
    """D162 compliance: found, none_found, and service_unavailable are
    distinguishable in the JSON response."""

    def test_found_state(self, client):
        """When Overpass returns an amenity, status='found'."""
        mock_amenity_response = {
            "elements": [{
                "id": 12345,
                "lat": 43.6965,
                "lon": 7.2762,
                "tags": {"amenity": "drinking_water", "name": "Fontaine Place Rossetti"},
            }]
        }
        mock_landmark_response = {
            "elements": [{
                "id": 99999,
                "lat": 43.6964,
                "lon": 7.2760,
                "tags": {"name": "Cathédrale Sainte-Réparate", "building": "church"},
            }]
        }

        with patch.object(amenities_near_service, '_overpass_query',
                          side_effect=[mock_amenity_response, mock_landmark_response]):
            resp = client.get('/amenities-near/43.6961/7.2758?kind=drinking_water')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "found"
        assert "amenity" in data
        assert data["amenity"]["kind"] == "drinking_water"
        assert data["amenity"]["distance_m"] >= 0
        assert data["amenity"]["landmark_hint"] == "Cathédrale Sainte-Réparate"

    def test_none_found_state(self, client):
        """When Overpass returns empty results, status='none_found'."""
        mock_empty = {"elements": []}

        with patch.object(amenities_near_service, '_overpass_query',
                          return_value=mock_empty):
            resp = client.get('/amenities-near/43.6961/7.2758?kind=drinking_water')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "none_found"
        assert "amenity" not in data

    def test_service_unavailable_state(self, client):
        """When Overpass fails (429/timeout), status='service_unavailable'."""
        with patch.object(amenities_near_service, '_overpass_query',
                          side_effect=RuntimeError("Overpass rate limited (429)")):
            resp = client.get('/amenities-near/43.6961/7.2758?kind=drinking_water')

        assert resp.status_code == 503
        data = resp.get_json()
        assert data["status"] == "service_unavailable"

    def test_states_are_distinguishable(self, client):
        """The three states use different status strings — the app can
        reliably tell a thirsty person the truth."""
        states = set()

        # found
        mock_found = {"elements": [{"id": 1, "lat": 43.69, "lon": 7.27, "tags": {"name": "X"}}]}
        mock_lm = {"elements": []}
        with patch.object(amenities_near_service, '_overpass_query',
                          side_effect=[mock_found, mock_lm]):
            r = client.get('/amenities-near/43.6961/7.2758?kind=drinking_water')
            states.add(r.get_json()["status"])

        # none_found
        with patch.object(amenities_near_service, '_overpass_query',
                          return_value={"elements": []}):
            r = client.get('/amenities-near/43.6961/7.2758?kind=drinking_water')
            states.add(r.get_json()["status"])

        # service_unavailable
        with patch.object(amenities_near_service, '_overpass_query',
                          side_effect=RuntimeError("timeout")):
            r = client.get('/amenities-near/43.6961/7.2758?kind=drinking_water')
            states.add(r.get_json()["status"])

        assert states == {"found", "none_found", "service_unavailable"}


# ──── Museum exclusion ───────────────────────────────────────────────────────

class TestMuseumExclusion:
    """Museum tours are excluded — GPS is useless indoors."""

    def test_museum_tour_rejected(self, client):
        """A tour with 'museum' in its name returns 403."""
        with patch.object(amenities_near_service, 'is_museum_tour', return_value=True):
            resp = client.get('/amenities-near/43.6961/7.2758?kind=drinking_water&tour_id=1')

        assert resp.status_code == 403
        data = resp.get_json()
        assert data["status"] == "excluded"
        assert data["reason"] == "museum_tour"

    def test_non_museum_tour_allowed(self, client):
        """A walking tour is allowed through."""
        mock_empty = {"elements": []}
        with patch.object(amenities_near_service, 'is_museum_tour', return_value=False):
            with patch.object(amenities_near_service, '_overpass_query',
                              return_value=mock_empty):
                resp = client.get('/amenities-near/43.6961/7.2758?kind=drinking_water&tour_id=12')

        assert resp.status_code == 200
        assert resp.get_json()["status"] == "none_found"

    def test_no_tour_id_still_works(self, client):
        """Without tour_id, the endpoint still works (no exclusion check)."""
        mock_empty = {"elements": []}
        with patch.object(amenities_near_service, '_overpass_query',
                          return_value=mock_empty):
            resp = client.get('/amenities-near/43.6961/7.2758?kind=toilets')

        assert resp.status_code == 200


# ──── Rate-limit compliance ──────────────────────────────────────────────────

class TestRateLimit:
    """Overpass requests are spaced >= OVERPASS_MIN_INTERVAL apart."""

    def test_interval_enforced(self):
        """Two sequential calls sleep between them."""
        call_times = []
        original_post = requests_post = None

        def mock_post(*args, **kwargs):
            call_times.append(time.time())
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"elements": []}
            return mock_resp

        # Reset the last request time
        amenities_near_service._overpass_last_request_time = 0.0

        with patch('amenities_near_service.requests.post', side_effect=mock_post):
            amenities_near_service._overpass_query("[out:json];node;out;")
            amenities_near_service._overpass_query("[out:json];node;out;")

        assert len(call_times) == 2
        interval = call_times[1] - call_times[0]
        assert interval >= amenities_near_service.OVERPASS_MIN_INTERVAL - 0.05


# ──── Parameter validation ───────────────────────────────────────────────────

class TestValidation:
    def test_missing_kind(self, client):
        resp = client.get('/amenities-near/43.6961/7.2758')
        assert resp.status_code == 400
        assert "kind" in resp.get_json()["error"]

    def test_invalid_kind(self, client):
        resp = client.get('/amenities-near/43.6961/7.2758?kind=hospital')
        assert resp.status_code == 400
        assert "Invalid kind" in resp.get_json()["error"]

    def test_invalid_coordinates(self, client):
        resp = client.get('/amenities-near/abc/def?kind=toilets')
        assert resp.status_code == 400

    def test_valid_kinds_accepted(self, client):
        """Both drinking_water and toilets are accepted kinds."""
        mock_empty = {"elements": []}
        with patch.object(amenities_near_service, '_overpass_query',
                          return_value=mock_empty):
            r1 = client.get('/amenities-near/43.6961/7.2758?kind=drinking_water')
            r2 = client.get('/amenities-near/43.6961/7.2758?kind=toilets')
        assert r1.status_code == 200
        assert r2.status_code == 200


# ──── Landmark hint ──────────────────────────────────────────────────────────

class TestLandmarkHint:
    def test_landmark_returned_when_available(self, client):
        mock_amenity = {"elements": [{
            "id": 1, "lat": 43.696, "lon": 7.276,
            "tags": {"amenity": "drinking_water"},
        }]}
        mock_landmark = {"elements": [{
            "id": 2, "lat": 43.6961, "lon": 7.2761,
            "tags": {"name": "Église Saint-Jacques", "building": "church"},
        }]}

        with patch.object(amenities_near_service, '_overpass_query',
                          side_effect=[mock_amenity, mock_landmark]):
            resp = client.get('/amenities-near/43.6961/7.2758?kind=drinking_water')

        data = resp.get_json()
        assert data["status"] == "found"
        assert data["amenity"]["landmark_hint"] == "Église Saint-Jacques"

    def test_null_landmark_when_none_nearby(self, client):
        mock_amenity = {"elements": [{
            "id": 1, "lat": 43.696, "lon": 7.276,
            "tags": {"amenity": "drinking_water"},
        }]}
        mock_no_landmark = {"elements": []}

        with patch.object(amenities_near_service, '_overpass_query',
                          side_effect=[mock_amenity, mock_no_landmark]):
            resp = client.get('/amenities-near/43.6961/7.2758?kind=drinking_water')

        data = resp.get_json()
        assert data["status"] == "found"
        assert data["amenity"]["landmark_hint"] is None

    def test_landmark_failure_does_not_block_amenity(self, client):
        """If landmark lookup fails, still return the amenity (with null hint)."""
        mock_amenity = {"elements": [{
            "id": 1, "lat": 43.696, "lon": 7.276,
            "tags": {"amenity": "drinking_water", "name": "Fountain"},
        }]}

        call_count = [0]

        def side_effect(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_amenity
            raise RuntimeError("Overpass timeout on landmark")

        with patch.object(amenities_near_service, '_overpass_query',
                          side_effect=side_effect):
            resp = client.get('/amenities-near/43.6961/7.2758?kind=drinking_water')

        data = resp.get_json()
        assert data["status"] == "found"
        assert data["amenity"]["name"] == "Fountain"
        assert data["amenity"]["landmark_hint"] is None


# ──── D162 regression: throttled ≠ not found ─────────────────────────────────

class TestD162Regression:
    """A throttled or failed lookup must NEVER be reported as 'no water nearby'.
    This is the bug from LOCAL-320."""

    def test_429_is_service_unavailable_not_none_found(self, client):
        with patch.object(amenities_near_service, '_overpass_query',
                          side_effect=RuntimeError("Overpass rate limited (429)")):
            resp = client.get('/amenities-near/43.6961/7.2758?kind=drinking_water')

        data = resp.get_json()
        # Must be service_unavailable, NEVER none_found
        assert data["status"] == "service_unavailable"
        assert data["status"] != "none_found"

    def test_timeout_is_service_unavailable_not_none_found(self, client):
        with patch.object(amenities_near_service, '_overpass_query',
                          side_effect=RuntimeError("Overpass connection failed: timeout")):
            resp = client.get('/amenities-near/43.6961/7.2758?kind=toilets')

        data = resp.get_json()
        assert data["status"] == "service_unavailable"
        assert data["status"] != "none_found"


# ──── Health check ───────────────────────────────────────────────────────────

class TestHealth:
    def test_health(self, client):
        resp = client.get('/health')
        assert resp.status_code == 200
        assert resp.get_json()["service"] == "amenities-near"
