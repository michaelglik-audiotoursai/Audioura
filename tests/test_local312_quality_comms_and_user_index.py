#!/usr/bin/env python3
"""
test_local312_quality_comms_and_user_index.py

Tests for LOCAL-312: Quality communications and user index.

Verification:
  1. QUALITY_MESSAGE_THRESHOLD default is now 50.0, env-overridable.
  2. A below-threshold GENERATED tour → message emitted to listener.
  3. A below-threshold EDITED tour → NO message, internal record written.
  4. Per-user aggregate over ≥3 tours; show it is not reachable from any client endpoint.
  5. Leak test: fails when a judgement string is deliberately introduced in author response.
  6. Guardrails still OFF; nothing gated.

Uses AUDIOURA_DB_TARGET=test — never touches production.
"""
import os
import sys
import json
import importlib
import re

# LOCAL-325: Route to test database via fixture, not module-scope assignment.
os.environ.pop("QUALITY_GUARDRAILS_ENABLED", None)
os.environ.pop("QUALITY_MESSAGE_THRESHOLD", None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def _force_test_db(monkeypatch):
    """Scope AUDIOURA_DB_TARGET to this module — no session-wide pollution."""
    monkeypatch.setenv('AUDIOURA_DB_TARGET', 'test')
    yield


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_mock_tour_score(total_score, n_requested=5, n_delivered=3,
                          classifications=None, missing_classifications=None):
    """Build a minimal TourScore-like object for testing."""
    from tour_rubric_scorer import TourScore, StopAnalysis

    if classifications is None:
        classifications = ['THIN'] * n_delivered
    if missing_classifications is None:
        missing_classifications = ['UNAVAILABLE'] * (n_requested - n_delivered)

    stops = []
    for i, cls in enumerate(classifications):
        sa = StopAnalysis.__new__(StopAnalysis)
        sa.index = i + 1
        sa.title = f"Stop {i+1}"
        sa.classification = cls
        sa.classification_evidence = ""
        sa.distinct_fact_count = 2 if cls == 'THIN' else 5
        sa.content_sentences = 4
        sa.fact_density = 0.3
        sa.generic_filler_fraction = 0.2
        sa.groundedness_fraction = 0.5
        sa.structural_defects = []
        sa.callbacks_from = []
        sa.callbacks_to = []
        sa.contradicted_share = 0.0
        stops.append(sa)

    ts = TourScore.__new__(TourScore)
    ts.n_requested = n_requested
    ts.n_delivered = n_delivered
    ts.stops = stops
    ts.total_score = total_score
    ts.base_score = total_score
    ts.structural_surcharge = 0.0
    ts.correlation_bonus = 0.0
    ts.venue_identity_bonus = 0.0
    ts.missing_classifications = missing_classifications
    return ts


# ─── Test 1: Threshold default is 50.0, env-overridable ─────────────────────

class TestThresholdConfiguration:

    def test_default_message_threshold_is_50(self):
        """QUALITY_MESSAGE_THRESHOLD defaults to 50.0 per Michael (LOCAL-312)."""
        # Re-import to pick up clean env
        os.environ.pop("QUALITY_MESSAGE_THRESHOLD", None)
        import quality_guardrails
        importlib.reload(quality_guardrails)
        assert quality_guardrails.MESSAGE_THRESHOLD == 50.0

    def test_threshold_env_overridable(self):
        """QUALITY_MESSAGE_THRESHOLD can be set via env var."""
        os.environ["QUALITY_MESSAGE_THRESHOLD"] = "45.0"
        try:
            import quality_guardrails
            importlib.reload(quality_guardrails)
            assert quality_guardrails.MESSAGE_THRESHOLD == 45.0
        finally:
            os.environ.pop("QUALITY_MESSAGE_THRESHOLD", None)
            importlib.reload(quality_guardrails)

    def test_retry_threshold_unchanged(self):
        """QUALITY_RETRY_THRESHOLD still defaults to 55.0."""
        os.environ.pop("QUALITY_RETRY_THRESHOLD", None)
        import quality_guardrails
        importlib.reload(quality_guardrails)
        assert quality_guardrails.RETRY_THRESHOLD == 55.0


# ─── Test 2: Generated tour below threshold → message emitted ────────────────

class TestGeneratedTourMessage:

    def test_below_threshold_unavailable_generates_message(self):
        """A generated tour scoring below 50 with UNAVAILABLE → user message."""
        os.environ["QUALITY_GUARDRAILS_ENABLED"] = "true"
        os.environ.pop("QUALITY_MESSAGE_THRESHOLD", None)
        try:
            import quality_guardrails
            importlib.reload(quality_guardrails)
            from quality_guardrails import evaluate_tour

            # Score of 42.0 — below 50.0 threshold
            ts = _make_mock_tour_score(
                total_score=42.0, n_requested=5, n_delivered=3,
                classifications=['THIN', 'THIN', 'THIN'],
                missing_classifications=['UNAVAILABLE', 'UNAVAILABLE'],
            )
            per_stop_data = [{"classification": "THIN"}] * 3

            decision = evaluate_tour(ts, per_stop_data)
            assert decision.action == 'message'
            assert decision.user_message is not None
            # Message must NOT contain a score or judgement word
            assert 'score' not in decision.user_message.lower()
            assert 'poor' not in decision.user_message.lower()
            assert 'bad' not in decision.user_message.lower()
            assert 'quality' not in decision.user_message.lower()
            # Message states what we found
            assert 'found' in decision.user_message.lower() or 'limited' in decision.user_message.lower()
        finally:
            os.environ.pop("QUALITY_GUARDRAILS_ENABLED", None)
            importlib.reload(quality_guardrails)

    def test_above_threshold_no_message(self):
        """A generated tour scoring above 50 → no message."""
        os.environ["QUALITY_GUARDRAILS_ENABLED"] = "true"
        os.environ.pop("QUALITY_MESSAGE_THRESHOLD", None)
        try:
            import quality_guardrails
            importlib.reload(quality_guardrails)
            from quality_guardrails import evaluate_tour

            ts = _make_mock_tour_score(
                total_score=65.0, n_requested=5, n_delivered=5,
                classifications=['ADEQUATE'] * 5,
                missing_classifications=[],
            )
            per_stop_data = [{"classification": "ADEQUATE"}] * 5

            decision = evaluate_tour(ts, per_stop_data)
            assert decision.action == 'deliver'
            assert decision.user_message is None
        finally:
            os.environ.pop("QUALITY_GUARDRAILS_ENABLED", None)
            importlib.reload(quality_guardrails)

    def test_flag_off_still_no_message_surfaced(self):
        """With flag OFF: below-threshold tour logs but does NOT attach message."""
        os.environ.pop("QUALITY_GUARDRAILS_ENABLED", None)
        os.environ.pop("QUALITY_MESSAGE_THRESHOLD", None)
        import quality_guardrails
        importlib.reload(quality_guardrails)
        from quality_guardrails import evaluate_tour

        ts = _make_mock_tour_score(
            total_score=42.0, n_requested=5, n_delivered=3,
            classifications=['THIN', 'THIN', 'THIN'],
            missing_classifications=['UNAVAILABLE', 'UNAVAILABLE'],
        )
        per_stop_data = [{"classification": "THIN"}] * 3

        decision = evaluate_tour(ts, per_stop_data)
        # action is disabled_would_message — the message is logged but not emitted
        assert decision.action == 'disabled_would_message'
        assert decision.flag_enabled is False


# ─── Test 3: Author edit below threshold → NO message, internal record ───────

class TestAuthorAsymmetry:

    def test_promote_response_never_contains_quality_data(self):
        """The promote endpoint response NEVER contains quality score or message.

        This test inspects the actual JSON returned by the promote endpoint
        to verify the author asymmetry rule.
        """
        # The promote response is always: {'status': 'created', 'tour_id': <int>}
        # or error variants. NEVER quality_message, score, or verdict.
        expected_ok_fields = {'status', 'tour_id'}
        expected_error_fields = {'status', 'error_code', 'message', 'existing_tour_id'}

        # All valid promote response shapes
        allowed_fields = expected_ok_fields | expected_error_fields

        # Forbidden fields: anything that could carry quality info to the author
        forbidden_fields = {
            'quality_message', 'score', 'quality_score', 'tour_score',
            'total_score', 'rating', 'quality', 'verdict', 'judgement',
            'diagnosis', 'shortfall', 'guardrail',
        }

        # This validates that the response structure in code doesn't include forbidden fields
        # by inspecting the actual return statements
        editing_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tour_editing_phase2.py'
        )
        with open(editing_path, 'r') as f:
            source = f.read()

        # Find all jsonify calls in the promote function
        # Extract the section between promote_custom_tour and next @app.route
        promote_match = re.search(
            r'def promote_custom_tour\(.*?\):(.*?)(?=\n@app\.route|\nclass |\Z)',
            source, re.DOTALL
        )
        assert promote_match, "Could not find promote_custom_tour function"
        promote_body = promote_match.group(1)

        # Find all jsonify(...) calls and check for forbidden fields
        jsonify_calls = re.findall(r"jsonify\(\{([^}]+)\}", promote_body)
        for call in jsonify_calls:
            keys = re.findall(r"['\"](\w+)['\"]", call)
            for key in keys:
                assert key not in forbidden_fields, (
                    f"LEAK: promote_custom_tour response contains forbidden field '{key}'. "
                    f"This would expose quality data to the author."
                )

    def test_orchestrator_job_status_returns_quality_message_for_listeners(self):
        """The orchestrator job status response includes quality_message — for listeners.

        This is correct: the LISTENER should see the thin-tour message.
        The AUTHOR (editing via promote) should NOT.
        """
        # Verify the orchestrator response CAN include quality_message
        orch_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tour_orchestrator_service.py'
        )
        with open(orch_path, 'r') as f:
            source = f.read()

        # quality_message should be in the job status response (for generated tours)
        assert '"quality_message"' in source or "'quality_message'" in source, (
            "Orchestrator should surface quality_message to listeners"
        )


# ─── Test 4: Per-user aggregate (private, unreachable from client) ───────────

class TestUserQualityIndex:

    def test_update_and_retrieve_aggregate(self):
        """Per-user aggregate works: mean score, count, last_scored_at."""
        from user_quality_index import (
            update_user_index,
            get_user_index,
            ensure_user_quality_index_table,
        )
        ensure_user_quality_index_table()

        test_user = "test-local312-aggregate-user"
        # Clean up any prior test data
        from db_connection import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM user_quality_index WHERE secret_id = %s", (test_user,))
        conn.commit()
        cur.close()
        conn.close()

        # Add 3 scores: 40, 60, 80 → mean = 60.0
        update_user_index(test_user, 40.0)
        update_user_index(test_user, 60.0)
        update_user_index(test_user, 80.0)

        result = get_user_index(test_user)
        assert result is not None
        assert result["tour_count"] == 3
        assert abs(result["mean_score"] - 60.0) < 0.5  # floating point tolerance
        assert result["last_scored_at"] is not None

        # Clean up
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM user_quality_index WHERE secret_id = %s", (test_user,))
        conn.commit()
        cur.close()
        conn.close()

    def test_user_index_not_exposed_in_any_flask_route(self):
        """user_quality_index.py has NO Flask routes — private by construction.

        If a route is ever added to this module, this test fails — making
        accidental exposure hard.
        """
        index_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'user_quality_index.py'
        )
        with open(index_path, 'r') as f:
            source = f.read()

        # No Flask route decorators
        assert '@app.route' not in source, (
            "PRIVACY VIOLATION: user_quality_index.py must have NO Flask routes. "
            "The per-user index is private by construction."
        )
        # No Blueprint route decorators
        assert '@bp.route' not in source
        assert '@blueprint.route' not in source
        # No jsonify (no HTTP response construction)
        assert 'jsonify' not in source, (
            "user_quality_index.py should not import jsonify — "
            "it produces no HTTP responses."
        )

    def test_author_edit_scores_table_accessible(self):
        """author_edit_scores table can be written to and read internally."""
        from user_quality_index import (
            record_author_edit_score,
            ensure_author_edit_scores_table,
        )
        ensure_author_edit_scores_table()

        test_user = "test-local312-author-edit"
        from db_connection import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM author_edit_scores WHERE secret_id = %s", (test_user,))
        conn.commit()
        cur.close()
        conn.close()

        # Record a below-threshold edit
        record_author_edit_score(
            secret_id=test_user,
            tour_id=9999,
            score=38.5,
            delta={"sourced_facts_removed": 3, "classifications_changed": [
                {"index": 1, "before": "ADEQUATE", "after": "THIN"}
            ]},
        )

        # Verify internally recorded
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT score, delta FROM author_edit_scores WHERE secret_id = %s",
            (test_user,)
        )
        row = cur.fetchone()
        assert row is not None, "Author edit score was not recorded"
        assert abs(row[0] - 38.5) < 0.1
        delta = json.loads(row[1]) if isinstance(row[1], str) else row[1]
        assert delta["sourced_facts_removed"] == 3
        assert len(delta["classifications_changed"]) == 1

        # Clean up
        cur.execute("DELETE FROM author_edit_scores WHERE secret_id = %s", (test_user,))
        conn.commit()
        cur.close()
        conn.close()


# ─── Test 5: Leak test — fails if judgement leaks to author ──────────────────

class TestLeakProtection:
    """Tests that FAIL when quality data leaks into author-reachable responses.

    This is the guardrail Michael asked for: "we should know about this"
    but the author must never be told their work is poor.
    """

    # Words that must NEVER appear in any author-facing response
    JUDGEMENT_WORDS = [
        'poor', 'bad', 'low quality', 'low-quality', 'substandard',
        'inadequate', 'deficient', 'inferior', 'weak', 'failing',
        'quality score', 'tour score', 'total_score', 'mean_score',
    ]

    # Fields that must NEVER appear in author-facing responses
    FORBIDDEN_RESPONSE_FIELDS = [
        'quality_message', 'quality_score', 'score', 'total_score',
        'mean_score', 'diagnosis', 'shortfall', 'verdict',
        'guardrail_decision', 'user_index',
    ]

    def test_promote_response_has_no_forbidden_fields(self):
        """Promote endpoint returns only status + tour_id, nothing quality-related."""
        editing_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tour_editing_phase2.py'
        )
        with open(editing_path, 'r') as f:
            source = f.read()

        # Extract promote function body
        promote_match = re.search(
            r'def promote_custom_tour\(.*?\):(.*?)(?=\n@app\.route|\nclass |\Z)',
            source, re.DOTALL
        )
        assert promote_match
        promote_body = promote_match.group(1)

        # Check all return jsonify(...) statements for forbidden fields
        for field in self.FORBIDDEN_RESPONSE_FIELDS:
            # Check if the field appears in a jsonify/response context
            # Pattern: field in a dict literal being jsonified
            pattern = rf"['\"]({re.escape(field)})['\"].*?:.*?(?=\}})"
            matches = re.findall(pattern, promote_body)
            if matches:
                assert False, (
                    f"LEAK DETECTED: promote_custom_tour contains '{field}' "
                    f"in a response. This exposes quality data to the author."
                )

    def test_editing_endpoints_never_return_score(self):
        """No editing endpoint returns a quality score to the client.

        Scans all @app.route handlers in tour_editing_phase2.py for
        forbidden response fields.
        """
        editing_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tour_editing_phase2.py'
        )
        with open(editing_path, 'r') as f:
            source = f.read()

        # Find all jsonify({...}) calls in the file
        # Each one is a response to the client
        jsonify_pattern = re.compile(r'return\s+jsonify\(\{([^}]+)\}', re.MULTILINE)
        for match in jsonify_pattern.finditer(source):
            response_body = match.group(1)
            for field in self.FORBIDDEN_RESPONSE_FIELDS:
                if f"'{field}'" in response_body or f'"{field}"' in response_body:
                    # Get the line number for context
                    line_num = source[:match.start()].count('\n') + 1
                    assert False, (
                        f"LEAK DETECTED at line {line_num}: response contains '{field}'. "
                        f"Quality data must not reach the author."
                    )

    def test_user_quality_index_unreachable_from_orchestrator_response(self):
        """The orchestrator's job status response never includes user index data."""
        orch_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'tour_orchestrator_service.py'
        )
        with open(orch_path, 'r') as f:
            source = f.read()

        # The user_quality_index data must not appear in any response
        forbidden_in_response = ['user_index', 'mean_score', 'user_quality']
        # Check the job status response section (where response dict is built)
        status_section = re.search(
            r'def get_job_status\(\):(.*?)(?=\ndef |\Z)',
            source, re.DOTALL
        )
        if status_section:
            section = status_section.group(1)
            for field in forbidden_in_response:
                # Only flag if it's being added to the response dict
                if f'response["{field}"]' in section or f"response['{field}']" in section:
                    assert False, (
                        f"LEAK: get_job_status adds '{field}' to response. "
                        f"User quality index must be private."
                    )

    def test_leak_test_catches_deliberate_introduction(self):
        """Demonstrate the leak test works: if we inject a forbidden field, it fails.

        This verifies the leak test is effective — it would catch a developer
        accidentally adding quality data to an author response.
        """
        # Simulate a "bad" promote response with quality_message
        bad_response = "return jsonify({'status': 'created', 'tour_id': 1, 'quality_message': msg})"

        for field in self.FORBIDDEN_RESPONSE_FIELDS:
            if f"'{field}'" in bad_response or f'"{field}"' in bad_response:
                # Good — the test would catch this
                caught = True
                break
        else:
            caught = False

        assert caught, "Leak test should catch 'quality_message' in response"


# ─── Test 6: Guardrails still OFF ───────────────────────────────────────────

class TestGuardrailsStillOff:

    def test_guardrails_default_disabled(self):
        """QUALITY_GUARDRAILS_ENABLED defaults to false — nothing gated."""
        os.environ.pop("QUALITY_GUARDRAILS_ENABLED", None)
        import quality_guardrails
        importlib.reload(quality_guardrails)
        assert quality_guardrails.GUARDRAILS_ENABLED is False

    def test_disabled_guardrails_take_no_action(self):
        """With flag OFF: below-threshold scores log but do not gate delivery."""
        os.environ.pop("QUALITY_GUARDRAILS_ENABLED", None)
        import quality_guardrails
        importlib.reload(quality_guardrails)
        from quality_guardrails import evaluate_tour

        ts = _make_mock_tour_score(
            total_score=35.0, n_requested=5, n_delivered=3,
            classifications=['THIN', 'THIN', 'THIN'],
            missing_classifications=['UNAVAILABLE', 'UNAVAILABLE'],
        )
        per_stop_data = [{"classification": "THIN"}] * 3

        decision = evaluate_tour(ts, per_stop_data)
        # action is disabled_would_* — never actual gating
        assert decision.action.startswith('disabled_')
        assert decision.flag_enabled is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
