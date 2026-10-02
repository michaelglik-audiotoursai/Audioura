"""
LOCAL-359: SCOPE-CHECK address injection and confidence gate fix.

Tests that:
1. The scope-check judge prompt includes the address when the poi dict carries one.
2. The prompt does NOT include an address line when no address is present.
3. The confidence gate requires HIGH confidence to remove (medium keeps).

These are OFFLINE, PROVABLE tests — they verify prompt construction without
calling OpenAI. The _check_one closure is inside _validate_stops_within_scope,
so we test by monkeypatching requests.post to capture the prompt.
"""
import os
import sys
import json
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestScopeCheckAddressInPrompt:
    """The scope-check judge must receive the address when available."""

    def test_address_appears_in_prompt_when_present(self, monkeypatch):
        """A poi with address='1 Cours Saleya' must have that address in the judge prompt."""
        from generate_tour_text import _validate_stops_within_scope

        captured_prompts = []

        class FakeResponse:
            status_code = 200
            def json(self):
                return {
                    "choices": [{
                        "message": {
                            "content": json.dumps({
                                "inside_scope": True,
                                "confidence": "high",
                                "reason": "Address is on Cours Saleya in Vieux Nice"
                            })
                        }
                    }]
                }

        def fake_post(url, headers=None, data=None):
            payload = json.loads(data)
            user_msg = payload["messages"][1]["content"]
            captured_prompts.append(user_msg)
            return FakeResponse()

        monkeypatch.setattr("requests.post", fake_post)

        poi_list = [
            {"stop_number": 1, "name": "Place Rossetti", "address": "Place Rossetti, 06300 Nice",
             "description": "A central square in Old Nice."},
            {"stop_number": 2, "name": "Le Safari", "address": "1 Cours Saleya, 06300 Nice",
             "description": "A classic brasserie on Cours Saleya in the heart of Vieux Nice."},
        ]

        headers = {"Authorization": "Bearer fake-key"}
        result = _validate_stops_within_scope(poi_list, "Old Nice (Vieux Nice)", headers)

        # Stop 0 is kept unconditionally; stop 1 (Le Safari) is checked
        assert len(captured_prompts) == 1, f"Expected 1 prompt, got {len(captured_prompts)}"
        prompt = captured_prompts[0]

        # The address must appear in the prompt
        assert "1 Cours Saleya" in prompt, (
            f"Address '1 Cours Saleya' not found in scope-check prompt:\n{prompt}"
        )
        # The authoritative note must be present
        assert "authoritative" in prompt.lower(), (
            f"Authoritative instruction not in prompt:\n{prompt}"
        )

    def test_no_address_line_when_address_empty(self, monkeypatch):
        """A poi with no address must NOT include an address line in the prompt."""
        from generate_tour_text import _validate_stops_within_scope

        captured_prompts = []

        class FakeResponse:
            status_code = 200
            def json(self):
                return {
                    "choices": [{
                        "message": {
                            "content": json.dumps({
                                "inside_scope": True,
                                "confidence": "low",
                                "reason": "uncertain"
                            })
                        }
                    }]
                }

        def fake_post(url, headers=None, data=None):
            payload = json.loads(data)
            user_msg = payload["messages"][1]["content"]
            captured_prompts.append(user_msg)
            return FakeResponse()

        monkeypatch.setattr("requests.post", fake_post)

        poi_list = [
            {"stop_number": 1, "name": "Start Point", "address": "", "description": ""},
            {"stop_number": 2, "name": "Mystery Stop", "address": "", "description": "A stop somewhere."},
        ]

        headers = {"Authorization": "Bearer fake-key"}
        _validate_stops_within_scope(poi_list, "Old Nice (Vieux Nice)", headers)

        assert len(captured_prompts) == 1
        prompt = captured_prompts[0]
        assert "authoritative" not in prompt.lower(), (
            f"Address/authoritative line should NOT appear when address is empty:\n{prompt}"
        )
        assert "Address (authoritative)" not in prompt


class TestScopeCheckConfidenceGate:
    """Removal requires HIGH confidence — medium must keep the stop."""

    def _run_with_verdict(self, monkeypatch, inside_scope, confidence):
        """Helper: run scope check with a predetermined LLM verdict."""
        from generate_tour_text import _validate_stops_within_scope

        class FakeResponse:
            status_code = 200
            def json(self_inner):
                return {
                    "choices": [{
                        "message": {
                            "content": json.dumps({
                                "inside_scope": inside_scope,
                                "confidence": confidence,
                                "reason": "test verdict"
                            })
                        }
                    }]
                }

        monkeypatch.setattr("requests.post", lambda *a, **kw: FakeResponse())

        poi_list = [
            {"stop_number": 1, "name": "Anchor Stop", "address": "", "description": ""},
            {"stop_number": 2, "name": "Test Stop", "address": "123 Test St", "description": "A place."},
        ]

        headers = {"Authorization": "Bearer fake-key"}
        return _validate_stops_within_scope(poi_list, "Test District", headers)

    def test_medium_confidence_outside_keeps_stop(self, monkeypatch):
        """A stop judged outside with MEDIUM confidence must be KEPT (not removed)."""
        result = self._run_with_verdict(monkeypatch, inside_scope=False, confidence="medium")
        names = [p["name"] for p in result]
        assert "Test Stop" in names, (
            f"Stop judged outside with medium confidence should be KEPT. Got: {names}"
        )

    def test_high_confidence_outside_removes_stop(self, monkeypatch):
        """A stop judged outside with HIGH confidence must be REMOVED."""
        result = self._run_with_verdict(monkeypatch, inside_scope=False, confidence="high")
        names = [p["name"] for p in result]
        assert "Test Stop" not in names, (
            f"Stop judged outside with high confidence should be REMOVED. Got: {names}"
        )

    def test_low_confidence_outside_keeps_stop(self, monkeypatch):
        """A stop judged outside with LOW confidence must be KEPT."""
        result = self._run_with_verdict(monkeypatch, inside_scope=False, confidence="low")
        names = [p["name"] for p in result]
        assert "Test Stop" in names, (
            f"Stop judged outside with low confidence should be KEPT. Got: {names}"
        )

    def test_inside_any_confidence_keeps_stop(self, monkeypatch):
        """A stop judged inside (any confidence) must always be kept."""
        for conf in ("low", "medium", "high"):
            result = self._run_with_verdict(monkeypatch, inside_scope=True, confidence=conf)
            names = [p["name"] for p in result]
            assert "Test Stop" in names, (
                f"Stop judged inside with {conf} confidence should be KEPT. Got: {names}"
            )


class TestScopeCheckStillRemoves:
    """SCOPE-CHECK must still remove genuinely out-of-scope stops (high confidence)."""

    def test_out_of_scope_high_confidence_removed(self, monkeypatch):
        """Walden Pond for a Robbins House tour: high confidence outside → removed."""
        from generate_tour_text import _validate_stops_within_scope

        class FakeResponse:
            status_code = 200
            def json(self):
                return {
                    "choices": [{
                        "message": {
                            "content": json.dumps({
                                "inside_scope": False,
                                "confidence": "high",
                                "reason": "Walden Pond is in Concord but 2 miles from Robbins House"
                            })
                        }
                    }]
                }

        monkeypatch.setattr("requests.post", lambda *a, **kw: FakeResponse())

        poi_list = [
            {"stop_number": 1, "name": "Robbins House", "address": "320 Monument St, Concord, MA",
             "description": "Historic house."},
            {"stop_number": 2, "name": "Walden Pond", "address": "915 Walden St, Concord, MA",
             "description": "Famous pond where Thoreau lived."},
        ]

        headers = {"Authorization": "Bearer fake-key"}
        result = _validate_stops_within_scope(poi_list, "Robbins House grounds", headers)
        names = [p["name"] for p in result]

        # Stop 0 always kept
        assert "Robbins House" in names
        # Out-of-scope with high confidence → removed
        assert "Walden Pond" not in names, (
            f"Walden Pond should be removed (high confidence outside). Got: {names}"
        )
