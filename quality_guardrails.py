#!/usr/bin/env python3
"""
Quality Guardrails (LOCAL-307)

When a tour scores poorly, this module decides whether to retry or to tell
the user why. The two cases are mutually exclusive:

    PIPELINE_LOST → regenerate silently, once.
    UNAVAILABLE   → do not regenerate. Tell the user.

Rules:
    - At most one retry per tour. Never a loop.
    - If the retry scores no better, deliver the better of the two.
    - Never deliver nothing.
    - Never pad to clear a threshold.
    - Count (requested vs delivered) is always visible.

Feature flag: QUALITY_GUARDRAILS_ENABLED
    Default: 'false' — mechanism ships disabled until Michael reviews thresholds.
    When 'false': scoring still runs (LOCAL-306), but no regeneration or
    user messages are triggered. The guardrails module logs what it WOULD have
    done (for threshold calibration), but takes no action.

Threshold proposals (derived from corpus, see SUBMISSION_LOCAL-307.md):
    - RETRY_THRESHOLD: tours scoring below this with PIPELINE_LOST diagnosis
      are candidates for regeneration.
    - MESSAGE_THRESHOLD: tours scoring below this with UNAVAILABLE diagnosis
      get a user-facing message explaining the shortfall.
"""
import os
import sys
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

# Import scorer (LOCAL-304/305)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tour_rubric_scorer import TourScore

logger = logging.getLogger(__name__)

# ─── Feature flag ────────────────────────────────────────────────────────────
# Default OFF. Set QUALITY_GUARDRAILS_ENABLED=true to enable gating.
GUARDRAILS_ENABLED = os.environ.get("QUALITY_GUARDRAILS_ENABLED", "false").lower() == "true"

# ─── Proposed thresholds (disabled by default, pending Michael's review) ─────
# Derived from 16 production tours scored 2026-08-06:
#   P25 = 56.6, Median = 64.6, P75 = 75.6, Mean = 66.4, Stdev = 13.3
#
# RETRY_THRESHOLD: Score below which a PIPELINE_LOST tour is retried.
#   Proposed: 55.0 (below P25 — catches only the worst pipeline failures)
#   Rationale: 4/16 tours (25%) fall at or below 55. These are tours where
#   every stop is THIN and at most 5 stops were requested — the pipeline
#   probably failed to retrieve good corpus, not an area problem.
#
# MESSAGE_THRESHOLD: Score below which an UNAVAILABLE tour gets a user message.
#   Proposed: 60.0 (between P25 and Median)
#   Rationale: 6/16 tours (37.5%) fall at or below 60. But a message only
#   fires when the cause is UNAVAILABLE (area is thin), so the actual trigger
#   rate is much lower.
#
# These are PROPOSALS. They are read from env vars so Michael can tune without
# code changes, but the default is OFF (GUARDRAILS_ENABLED=false).
RETRY_THRESHOLD = float(os.environ.get("QUALITY_RETRY_THRESHOLD", "55.0"))
MESSAGE_THRESHOLD = float(os.environ.get("QUALITY_MESSAGE_THRESHOLD", "60.0"))


@dataclass
class ShortfallDiagnosis:
    """Result of diagnosing why a tour scored low."""
    cause: str                    # 'PIPELINE_LOST', 'UNAVAILABLE', or 'NONE'
    n_requested: int
    n_delivered: int
    score: float
    pipeline_lost_count: int = 0
    unavailable_count: int = 0
    thin_stop_count: int = 0     # delivered stops classified THIN
    total_stops_classified: int = 0
    detail: str = ""             # human-readable explanation of diagnosis


@dataclass
class GuardrailDecision:
    """What the guardrails decided to do (or would have done if disabled)."""
    action: str                  # 'retry', 'message', 'deliver', 'disabled_would_retry', 'disabled_would_message'
    diagnosis: ShortfallDiagnosis
    user_message: Optional[str] = None
    retry_attempted: bool = False
    retry_score: Optional[float] = None
    original_score: Optional[float] = None
    delivered_version: str = "original"  # 'original' or 'retry'
    flag_enabled: bool = False


def diagnose_shortfall(tour_score: TourScore, per_stop_data: list) -> ShortfallDiagnosis:
    """Diagnose the cause of a low-scoring tour.

    Uses the LOCAL-305 split: PIPELINE_LOST (we failed) vs UNAVAILABLE
    (the world is thin). If there's no shortfall, returns cause='NONE'.

    Args:
        tour_score: The TourScore from scoring the tour.
        per_stop_data: List of per-stop dicts with 'classification' key.

    Returns:
        ShortfallDiagnosis with the primary cause.
    """
    pipeline_lost = sum(
        1 for c in tour_score.missing_classifications if c == 'PIPELINE_LOST'
    )
    unavailable = sum(
        1 for c in tour_score.missing_classifications if c == 'UNAVAILABLE'
    )
    thin_count = sum(
        1 for s in per_stop_data if s.get('classification') == 'THIN'
    )
    total_classified = len(per_stop_data)

    # Determine primary cause
    # PIPELINE_LOST dominates if we lost stops we verified
    # UNAVAILABLE dominates if the area simply has nothing more
    # If no stops are missing but all are THIN → also diagnose based on cause
    if pipeline_lost > 0 and pipeline_lost >= unavailable:
        cause = 'PIPELINE_LOST'
        detail = (
            f"{pipeline_lost} stop(s) were verified but lost in pipeline. "
            f"Delivered {tour_score.n_delivered}/{tour_score.n_requested}."
        )
    elif unavailable > 0:
        cause = 'UNAVAILABLE'
        detail = (
            f"{unavailable} stop(s) could not be found — area lacks documented places. "
            f"Delivered {tour_score.n_delivered}/{tour_score.n_requested}."
        )
    elif thin_count == total_classified and total_classified > 0:
        # All delivered stops are THIN — sources are thin even though we found places
        # If n_delivered == n_requested, this is "places exist, sources thin"
        if tour_score.n_delivered >= tour_score.n_requested:
            cause = 'UNAVAILABLE'
            detail = (
                f"All {thin_count} stops are THIN — limited documented history. "
                f"Delivered {tour_score.n_delivered}/{tour_score.n_requested}."
            )
        else:
            # Delivered fewer and they're all thin — pipeline issue
            cause = 'PIPELINE_LOST'
            detail = (
                f"Delivered fewer stops than requested and all are THIN. "
                f"Delivered {tour_score.n_delivered}/{tour_score.n_requested}."
            )
    else:
        cause = 'NONE'
        detail = f"Score {tour_score.total_score:.1f} — no shortfall diagnosed."

    return ShortfallDiagnosis(
        cause=cause,
        n_requested=tour_score.n_requested,
        n_delivered=tour_score.n_delivered,
        score=tour_score.total_score,
        pipeline_lost_count=pipeline_lost,
        unavailable_count=unavailable,
        thin_stop_count=thin_count,
        total_stops_classified=total_classified,
        detail=detail,
    )


def generate_user_message(diagnosis: ShortfallDiagnosis) -> Optional[str]:
    """Generate an honest, specific user-facing message for UNAVAILABLE tours.

    Returns None if no message is warranted.

    Messages state what we found and what they are getting.
    No apology, no jargon, no "quality score".
    """
    if diagnosis.cause != 'UNAVAILABLE':
        return None

    n_req = diagnosis.n_requested
    n_del = diagnosis.n_delivered

    # Case 1: Fewer real places than requested
    if n_del < n_req:
        return (
            f"We found {n_del} well-documented place{'s' if n_del != 1 else ''} "
            f"for this area rather than the {n_req} you asked for. "
            f"Here is the shorter tour."
        )

    # Case 2: All places thin on sources (n_delivered == n_requested)
    if diagnosis.thin_stop_count == diagnosis.total_stops_classified:
        return (
            "We have limited documented history for some of these stops. "
            "The tour is shorter on detail than usual."
        )

    # Case 3: Mixed — some thin, some adequate (rare for UNAVAILABLE cause)
    if diagnosis.thin_stop_count > 0:
        return (
            f"{diagnosis.thin_stop_count} of {diagnosis.total_stops_classified} stops "
            f"have limited published sources. The tour covers all requested locations "
            f"but some stops are shorter on detail."
        )

    return None


def evaluate_tour(
    tour_score: TourScore,
    per_stop_data: list,
    is_retry: bool = False,
) -> GuardrailDecision:
    """Evaluate a scored tour and decide: retry, message, or deliver as-is.

    This is the main entry point called by the orchestrator after scoring.

    Args:
        tour_score: The TourScore from tour_scoring_service.
        per_stop_data: Per-stop classification data.
        is_retry: True if this is already a retry attempt (prevents loops).

    Returns:
        GuardrailDecision describing what to do.
    """
    diagnosis = diagnose_shortfall(tour_score, per_stop_data)
    score = tour_score.total_score

    # Log what we see regardless of flag state
    print(
        f"[GUARDRAILS] score={score:.1f} cause={diagnosis.cause} "
        f"delivered={diagnosis.n_delivered}/{diagnosis.n_requested} "
        f"PL={diagnosis.pipeline_lost_count} UA={diagnosis.unavailable_count} "
        f"thin={diagnosis.thin_stop_count}/{diagnosis.total_stops_classified} "
        f"enabled={GUARDRAILS_ENABLED} is_retry={is_retry}"
    )

    # No shortfall — deliver as-is
    if diagnosis.cause == 'NONE' or score >= max(RETRY_THRESHOLD, MESSAGE_THRESHOLD):
        return GuardrailDecision(
            action='deliver',
            diagnosis=diagnosis,
            flag_enabled=GUARDRAILS_ENABLED,
        )

    # ─── PIPELINE_LOST: candidate for retry ──────────────────────────────────
    if diagnosis.cause == 'PIPELINE_LOST' and score < RETRY_THRESHOLD and not is_retry:
        if GUARDRAILS_ENABLED:
            return GuardrailDecision(
                action='retry',
                diagnosis=diagnosis,
                original_score=score,
                flag_enabled=True,
            )
        else:
            print(
                f"[GUARDRAILS] WOULD RETRY (disabled): score={score:.1f} < "
                f"threshold={RETRY_THRESHOLD}, cause=PIPELINE_LOST"
            )
            return GuardrailDecision(
                action='disabled_would_retry',
                diagnosis=diagnosis,
                original_score=score,
                flag_enabled=False,
            )

    # ─── UNAVAILABLE: user message, no retry ─────────────────────────────────
    if diagnosis.cause == 'UNAVAILABLE' and score < MESSAGE_THRESHOLD:
        message = generate_user_message(diagnosis)
        if GUARDRAILS_ENABLED:
            return GuardrailDecision(
                action='message',
                diagnosis=diagnosis,
                user_message=message,
                flag_enabled=True,
            )
        else:
            print(
                f"[GUARDRAILS] WOULD MESSAGE (disabled): score={score:.1f} < "
                f"threshold={MESSAGE_THRESHOLD}, cause=UNAVAILABLE, "
                f"msg='{message}'"
            )
            return GuardrailDecision(
                action='disabled_would_message',
                diagnosis=diagnosis,
                user_message=message,
                flag_enabled=False,
            )

    # ─── Retry already attempted — deliver whatever we have ──────────────────
    if is_retry:
        return GuardrailDecision(
            action='deliver',
            diagnosis=diagnosis,
            retry_attempted=True,
            flag_enabled=GUARDRAILS_ENABLED,
        )

    # ─── Default: deliver (score is low but not below threshold, or mixed) ───
    return GuardrailDecision(
        action='deliver',
        diagnosis=diagnosis,
        flag_enabled=GUARDRAILS_ENABLED,
    )


def select_better_tour(
    original_score: float,
    retry_score: float,
    original_label: str = "original",
    retry_label: str = "retry",
) -> str:
    """After a retry, select the better-scoring tour for delivery.

    Returns 'original' or 'retry'. In case of tie, prefer original
    (avoid the latency cost of re-processing for no gain).
    """
    if retry_score > original_score:
        print(
            f"[GUARDRAILS] Retry scored better: {retry_label}={retry_score:.1f} > "
            f"{original_label}={original_score:.1f}. Delivering retry."
        )
        return 'retry'
    else:
        print(
            f"[GUARDRAILS] Original scored same or better: {original_label}={original_score:.1f} >= "
            f"{retry_label}={retry_score:.1f}. Delivering original."
        )
        return 'original'


def format_guardrail_log(decision: GuardrailDecision) -> str:
    """Format a structured log line for the guardrail decision."""
    parts = [
        f"action={decision.action}",
        f"cause={decision.diagnosis.cause}",
        f"score={decision.diagnosis.score:.1f}",
        f"delivered={decision.diagnosis.n_delivered}/{decision.diagnosis.n_requested}",
        f"enabled={decision.flag_enabled}",
    ]
    if decision.user_message:
        parts.append(f"message='{decision.user_message[:80]}'")
    if decision.retry_score is not None:
        parts.append(f"retry_score={decision.retry_score:.1f}")
    if decision.delivered_version != "original":
        parts.append(f"delivered_version={decision.delivered_version}")
    return "[GUARDRAILS DECISION] " + " | ".join(parts)
