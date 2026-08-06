#!/usr/bin/env python3
"""
test_local307_quality_guardrails.py — Verify quality guardrails (LOCAL-307).

Tests:
  1. PIPELINE_LOST diagnosis triggers retry candidate (flag off: logs, no action).
  2. UNAVAILABLE diagnosis generates user message (flag off: logs, no action).
  3. With flag ON: PIPELINE_LOST → retry action.
  4. With flag ON: UNAVAILABLE → message action, no retry.
  5. Retry is never attempted more than once (is_retry=True → deliver).
  6. select_better_tour delivers the higher-scoring version.
  7. User messages are specific and non-apologetic.
  8. A full-score tour (no shortfall) gets no guardrail action.
  9. Count (requested vs delivered) is always visible in diagnosis.
  10. No tour is ever suppressed.

Uses AUDIOURA_DB_TARGET=test — never touches production.
"""
import os
import sys
import json

# Route to test database
os.environ["AUDIOURA_DB_TARGET"] = "test"
# Ensure guardrails flag is OFF by default for most tests
os.environ.pop("QUALITY_GUARDRAILS_ENABLED", None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))

import pytest
from unittest.mock import patch
from dataclasses import dataclass, field
from typing import List

# Import the modules under test
from quality_guardrails import (
    diagnose_shortfall,
    generate_user_message,
    evaluate_tour,
    select_better_tour,
    format_guardrail_log,
    GuardrailDecision,
    ShortfallDiagnosis,
    RETRY_THRESHOLD,
    MESSAGE_THRESHOLD,
)
from tour_rubric_scorer import TourScore, StopAnalysis


# ─── Fixtures: mock TourScore objects ────────────────────────────────────────

def _make_tour_score(n_requested, n_delivered, total_score,
                     classifications, missing_classifications=None):
    """Build a minimal TourScore for testing."""
    stops = []
    for i, cls in enumerate(classifications):
        sa = StopAnalysis.__new__(StopAnalysis)
        sa.index = i + 1
        sa.title = f"Stop {i+1}"
        sa.classification = cls
        sa.classification_evidence = ""
        sa.distinct_fact_count = 5 if cls in ('RICH', 'ADEQUATE') else 2
        sa.content_sentences = 8
        sa.fact_density = 0.5
        sa.generic_filler_fraction = 0.1
        sa.groundedness_fraction = 0.8
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
    ts.per_stop_base = [total_score / max(n_delivered, 1)] * n_delivered
    ts.per_stop_structural = [0.0] * n_delivered
    ts.venue_identity_facts = []
    ts.coverage = n_delivered / n_requested if n_requested else 1.0
    ts.quality = total_score
    ts.n_achievable = n_requested
    ts.missing_classifications = missing_classifications or []
    return ts


def _per_stop_data(classifications):
    """Build per-stop data list from classifications."""
    return [{"classification": c} for c in classifications]


# ─── Test 1: PIPELINE_LOST diagnosis (flag OFF) ─────────────────────────────

def test_pipeline_lost_disabled():
    """PIPELINE_LOST with flag OFF logs what it would do, takes no action."""
    # Score 40 (below retry threshold of 55), 3/5 stops delivered,
    # 2 missing classified as PIPELINE_LOST
    ts = _make_tour_score(
        n_requested=5, n_delivered=3, total_score=40.0,
        classifications=['THIN', 'THIN', 'THIN'],
        missing_classifications=['PIPELINE_LOST', 'PIPELINE_LOST'],
    )
    per_stop = _per_stop_data(['THIN', 'THIN', 'THIN'])

    with patch.dict(os.environ, {"QUALITY_GUARDRAILS_ENABLED": "false"}):
        # Re-import to pick up env change
        import importlib
        import quality_guardrails
        importlib.reload(quality_guardrails)
        decision = quality_guardrails.evaluate_tour(ts, per_stop, is_retry=False)

    assert decision.action == 'disabled_would_retry'
    assert decision.diagnosis.cause == 'PIPELINE_LOST'
    assert decision.diagnosis.pipeline_lost_count == 2
    assert decision.flag_enabled is False
    # Count is visible
    assert decision.diagnosis.n_requested == 5
    assert decision.diagnosis.n_delivered == 3


# ─── Test 2: UNAVAILABLE diagnosis (flag OFF) ───────────────────────────────

def test_unavailable_disabled():
    """UNAVAILABLE with flag OFF logs the message it would show."""
    # Score 50 (below message threshold of 60), all stops delivered but all THIN
    ts = _make_tour_score(
        n_requested=2, n_delivered=2, total_score=50.0,
        classifications=['THIN', 'THIN'],
        missing_classifications=[],
    )
    per_stop = _per_stop_data(['THIN', 'THIN'])

    with patch.dict(os.environ, {"QUALITY_GUARDRAILS_ENABLED": "false"}):
        import importlib
        import quality_guardrails
        importlib.reload(quality_guardrails)
        decision = quality_guardrails.evaluate_tour(ts, per_stop, is_retry=False)

    assert decision.action == 'disabled_would_message'
    assert decision.diagnosis.cause == 'UNAVAILABLE'
    assert decision.user_message is not None
    assert "limited documented history" in decision.user_message
    assert decision.flag_enabled is False


# ─── Test 3: PIPELINE_LOST with flag ON → retry ─────────────────────────────

def test_pipeline_lost_enabled_retry():
    """PIPELINE_LOST with flag ON triggers retry action."""
    ts = _make_tour_score(
        n_requested=5, n_delivered=3, total_score=40.0,
        classifications=['THIN', 'THIN', 'THIN'],
        missing_classifications=['PIPELINE_LOST', 'PIPELINE_LOST'],
    )
    per_stop = _per_stop_data(['THIN', 'THIN', 'THIN'])

    with patch.dict(os.environ, {"QUALITY_GUARDRAILS_ENABLED": "true"}):
        import importlib
        import quality_guardrails
        importlib.reload(quality_guardrails)
        decision = quality_guardrails.evaluate_tour(ts, per_stop, is_retry=False)

    assert decision.action == 'retry'
    assert decision.diagnosis.cause == 'PIPELINE_LOST'
    assert decision.original_score == 40.0
    assert decision.flag_enabled is True


# ─── Test 4: UNAVAILABLE with flag ON → message, no retry ───────────────────

def test_unavailable_enabled_message():
    """UNAVAILABLE with flag ON emits user message, never retries."""
    # Fewer stops than requested, area lacks documented places
    ts = _make_tour_score(
        n_requested=6, n_delivered=3, total_score=45.0,
        classifications=['THIN', 'THIN', 'THIN'],
        missing_classifications=['UNAVAILABLE', 'UNAVAILABLE', 'UNAVAILABLE'],
    )
    per_stop = _per_stop_data(['THIN', 'THIN', 'THIN'])

    with patch.dict(os.environ, {"QUALITY_GUARDRAILS_ENABLED": "true"}):
        import importlib
        import quality_guardrails
        importlib.reload(quality_guardrails)
        decision = quality_guardrails.evaluate_tour(ts, per_stop, is_retry=False)

    assert decision.action == 'message'
    assert decision.diagnosis.cause == 'UNAVAILABLE'
    assert decision.user_message is not None
    # Message mentions the count
    assert "3" in decision.user_message
    assert "6" in decision.user_message
    assert "well-documented" in decision.user_message
    # No retry
    assert decision.retry_attempted is False


# ─── Test 5: Retry never more than once ─────────────────────────────────────

def test_no_double_retry():
    """When is_retry=True, always delivers — never loops."""
    ts = _make_tour_score(
        n_requested=5, n_delivered=3, total_score=30.0,
        classifications=['THIN', 'THIN', 'THIN'],
        missing_classifications=['PIPELINE_LOST', 'PIPELINE_LOST'],
    )
    per_stop = _per_stop_data(['THIN', 'THIN', 'THIN'])

    with patch.dict(os.environ, {"QUALITY_GUARDRAILS_ENABLED": "true"}):
        import importlib
        import quality_guardrails
        importlib.reload(quality_guardrails)
        decision = quality_guardrails.evaluate_tour(ts, per_stop, is_retry=True)

    assert decision.action == 'deliver'
    assert decision.retry_attempted is True
    # Even with terrible score and PIPELINE_LOST, is_retry=True → deliver


# ─── Test 6: select_better_tour ──────────────────────────────────────────────

def test_select_better_tour():
    """Better-of-two selection works correctly."""
    assert select_better_tour(40.0, 60.0) == 'retry'
    assert select_better_tour(60.0, 40.0) == 'original'
    assert select_better_tour(50.0, 50.0) == 'original'  # tie → original


# ─── Test 7: User messages are specific and non-apologetic ───────────────────

def test_user_messages_quality():
    """Messages state facts, no apology, no jargon, no 'quality score'."""
    # Case 1: Fewer places
    diag_fewer = ShortfallDiagnosis(
        cause='UNAVAILABLE', n_requested=6, n_delivered=3, score=45.0,
        pipeline_lost_count=0, unavailable_count=3,
        thin_stop_count=3, total_stops_classified=3,
    )
    msg1 = generate_user_message(diag_fewer)
    assert msg1 is not None
    assert "sorry" not in msg1.lower()
    assert "apologize" not in msg1.lower()
    assert "quality" not in msg1.lower()
    assert "score" not in msg1.lower()
    assert "3" in msg1 and "6" in msg1

    # Case 2: Places exist, sources thin
    diag_thin = ShortfallDiagnosis(
        cause='UNAVAILABLE', n_requested=5, n_delivered=5, score=50.0,
        pipeline_lost_count=0, unavailable_count=0,
        thin_stop_count=5, total_stops_classified=5,
    )
    msg2 = generate_user_message(diag_thin)
    assert msg2 is not None
    assert "sorry" not in msg2.lower()
    assert "limited documented history" in msg2

    # Case 3: Not UNAVAILABLE → no message
    diag_none = ShortfallDiagnosis(
        cause='PIPELINE_LOST', n_requested=5, n_delivered=3, score=40.0,
        pipeline_lost_count=2, unavailable_count=0,
        thin_stop_count=3, total_stops_classified=3,
    )
    msg3 = generate_user_message(diag_none)
    assert msg3 is None  # PIPELINE_LOST never messages the user


# ─── Test 8: Full-score tour → no guardrail action ──────────────────────────

def test_full_score_no_action():
    """A tour scoring well above thresholds gets no guardrail intervention."""
    ts = _make_tour_score(
        n_requested=8, n_delivered=8, total_score=85.0,
        classifications=['RICH', 'ADEQUATE', 'RICH', 'ADEQUATE',
                         'RICH', 'ADEQUATE', 'RICH', 'ADEQUATE'],
        missing_classifications=[],
    )
    per_stop = _per_stop_data(['RICH', 'ADEQUATE', 'RICH', 'ADEQUATE',
                               'RICH', 'ADEQUATE', 'RICH', 'ADEQUATE'])

    with patch.dict(os.environ, {"QUALITY_GUARDRAILS_ENABLED": "true"}):
        import importlib
        import quality_guardrails
        importlib.reload(quality_guardrails)
        decision = quality_guardrails.evaluate_tour(ts, per_stop, is_retry=False)

    assert decision.action == 'deliver'
    assert decision.diagnosis.cause == 'NONE'
    assert decision.user_message is None


# ─── Test 9: Count always visible ───────────────────────────────────────────

def test_count_always_visible():
    """Requested and delivered counts are always present in diagnosis."""
    ts = _make_tour_score(
        n_requested=10, n_delivered=7, total_score=55.0,
        classifications=['THIN'] * 7,
        missing_classifications=['PIPELINE_LOST', 'UNAVAILABLE', 'PIPELINE_LOST'],
    )
    per_stop = _per_stop_data(['THIN'] * 7)

    diag = diagnose_shortfall(ts, per_stop)
    assert diag.n_requested == 10
    assert diag.n_delivered == 7
    assert diag.pipeline_lost_count == 2
    assert diag.unavailable_count == 1


# ─── Test 10: No tour is ever suppressed ────────────────────────────────────

def test_no_suppression():
    """Even the worst possible score results in 'deliver' (never suppress)."""
    # Score of 0.0 with everything going wrong
    ts = _make_tour_score(
        n_requested=10, n_delivered=1, total_score=5.0,
        classifications=['THIN'],
        missing_classifications=['PIPELINE_LOST'] * 9,
    )
    per_stop = _per_stop_data(['THIN'])

    with patch.dict(os.environ, {"QUALITY_GUARDRAILS_ENABLED": "true"}):
        import importlib
        import quality_guardrails
        importlib.reload(quality_guardrails)

        # First call: would retry
        decision1 = quality_guardrails.evaluate_tour(ts, per_stop, is_retry=False)
        assert decision1.action == 'retry'  # wants to retry, not suppress

        # After retry (retry didn't help): delivers anyway
        decision2 = quality_guardrails.evaluate_tour(ts, per_stop, is_retry=True)
        assert decision2.action == 'deliver'
        # Tour is NEVER suppressed
        assert decision2.action != 'suppress'


# ─── Test 11: format_guardrail_log produces parseable output ─────────────────

def test_format_log():
    """Log format contains all key fields."""
    diag = ShortfallDiagnosis(
        cause='UNAVAILABLE', n_requested=6, n_delivered=3, score=45.0,
        pipeline_lost_count=0, unavailable_count=3,
        thin_stop_count=3, total_stops_classified=3,
    )
    decision = GuardrailDecision(
        action='message',
        diagnosis=diag,
        user_message="We found 3 well-documented places for this area rather than the 6 you asked for.",
        flag_enabled=True,
    )
    log_line = format_guardrail_log(decision)
    assert "[GUARDRAILS DECISION]" in log_line
    assert "action=message" in log_line
    assert "cause=UNAVAILABLE" in log_line
    assert "score=45.0" in log_line
    assert "delivered=3/6" in log_line
    assert "enabled=True" in log_line


# ─── Test 12: Thresholds are configurable via env vars ───────────────────────

def test_thresholds_from_env():
    """Thresholds read from env vars."""
    with patch.dict(os.environ, {
        "QUALITY_RETRY_THRESHOLD": "70.0",
        "QUALITY_MESSAGE_THRESHOLD": "75.0",
        "QUALITY_GUARDRAILS_ENABLED": "true",
    }):
        import importlib
        import quality_guardrails
        importlib.reload(quality_guardrails)
        assert quality_guardrails.RETRY_THRESHOLD == 70.0
        assert quality_guardrails.MESSAGE_THRESHOLD == 75.0

    # Restore defaults
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("QUALITY_RETRY_THRESHOLD", None)
        os.environ.pop("QUALITY_MESSAGE_THRESHOLD", None)
        os.environ.pop("QUALITY_GUARDRAILS_ENABLED", None)
        import importlib
        import quality_guardrails
        importlib.reload(quality_guardrails)


if __name__ == "__main__":
    # Allow running directly
    test_pipeline_lost_disabled()
    print("✅ Test 1: PIPELINE_LOST (disabled) — logs, no action")

    test_unavailable_disabled()
    print("✅ Test 2: UNAVAILABLE (disabled) — logs message, no action")

    test_pipeline_lost_enabled_retry()
    print("✅ Test 3: PIPELINE_LOST (enabled) → retry")

    test_unavailable_enabled_message()
    print("✅ Test 4: UNAVAILABLE (enabled) → message, no retry")

    test_no_double_retry()
    print("✅ Test 5: is_retry=True → always deliver (no loop)")

    test_select_better_tour()
    print("✅ Test 6: select_better_tour picks higher score")

    test_user_messages_quality()
    print("✅ Test 7: Messages are specific, non-apologetic, no jargon")

    test_full_score_no_action()
    print("✅ Test 8: Full-score tour → no intervention")

    test_count_always_visible()
    print("✅ Test 9: Count (requested/delivered) always visible")

    test_no_suppression()
    print("✅ Test 10: No tour ever suppressed")

    test_format_log()
    print("✅ Test 11: Log format correct")

    test_thresholds_from_env()
    print("✅ Test 12: Thresholds configurable via env")

    print("\nALL TESTS PASSED ✅")
