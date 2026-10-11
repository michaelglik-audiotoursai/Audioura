#!/usr/bin/env python3
"""
Tour Rating Service (LOCAL-670)

A listener rates a TOUR from 1 to 10 (whole numbers). One rating per
(user, tour); a later rating REPLACES the earlier one. This is the per-TOUR
judgement Michael asked for — distinct from, and alongside, the per-STOP thumbs
in swipe_preference_service / user_stop_feedback, which are unchanged.

Shown-score rule (D647, Michael 2026-10-10):
  * 0 ratings   → 7.5, label "New".
  * 1–3 ratings → the AVERAGE of (7.5 plus the real ratings).
                  e.g. one 9  → mean(7.5, 9)        = 8.25 → shown 8.3
                       7.5 & 9 example from the brief: mean(7.5, 9) → 8.3.
  * ≥ 4 ratings → the MEDIAN of the real ratings only (the 7.5 prior dropped).
                  "mean" in Michael's words, read by LEAD as the robust middle
                  value so one angry 1 or one fake 10 cannot swing a tour.
  * Always returned with the count and a label, e.g. "8.3 · 2 ratings",
    "7.5 · New".

Translation mapping: a translation row (audio_tours.original_tour_id set, e.g.
Russian 615 of tour 557) shares its SOURCE tour's ratings. Every read and write
first resolves the given tour id to its original, so ratings always key on the
ORIGINAL audio_tours.id.

Authorisation: only a user who has DOWNLOADED the tour should rate it. We check
the existing download record (tour_requests, keyed on secret_id). If no record
exists we still ALLOW the rating and log that fact — per the ticket, the rating
is never silently dropped.

This module provides:
  1. compute_score()        — the pure score rule (unit-testable, no DB)
  2. resolve_original_id()  — translation → original mapping
  3. record_rating()        — UPSERT one rating (replace on re-rate)
  4. get_rating()           — {score, count, label} for a tour
  5. register_rating_routes(app) — Flask routes for the orchestrator

Design decisions documented in SUBMISSION_LOCAL-670.md.
"""

import os
import sys
from decimal import Decimal, ROUND_HALF_UP

# Reuse the shared DB connection helper the other services use (tests/).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))
from db_connection import get_connection  # noqa: E402


# The automatic starting value when a tour has no ratings, and the prior that
# is blended in for the first few real ratings. Michael: "start the value from
# 7.5/10 if there are no valuations."
DEFAULT_SCORE = 7.5
# "Three and less show average [incl. the 7.5], more than 3 show mean [median
# of real only]." So the prior is included for counts 1..3 and dropped at >= 4.
MEDIAN_SWITCH_COUNT = 4


# ─── Pure score rule (no DB — unit-testable in isolation) ─────────────────────

def _round_half_up_1dp(value):
    """Round to one decimal place, half-up (so 8.25 → 8.3, matching the brief)."""
    return float(Decimal(str(value)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))


def _median(values):
    """Median of a non-empty list of numbers. Even count → mean of the two
    middle values. Returns a float."""
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return float(s[mid])
    return (float(s[mid - 1]) + float(s[mid])) / 2.0


def compute_score(ratings):
    """Compute the shown {score, count, label} from a list of REAL ratings.

    Parameters:
        ratings: list[int] — the real 1..10 ratings for the tour (may be empty).

    Returns:
        dict: {"score": float (1 dp), "count": int, "label": str}

    Rules (D647):
        0        → 7.5, "New"
        1..3     → average of (7.5 + ratings), rounded to 1 dp
        >= 4     → median of ratings only, rounded to 1 dp
    """
    count = len(ratings)

    if count == 0:
        return {"score": DEFAULT_SCORE, "count": 0, "label": "New"}

    if count < MEDIAN_SWITCH_COUNT:  # 1, 2, or 3 real ratings
        blended = [DEFAULT_SCORE] + [float(r) for r in ratings]
        score = _round_half_up_1dp(sum(blended) / len(blended))
    else:  # 4+ real ratings — median of the real ratings only
        score = _round_half_up_1dp(_median(ratings))

    label = f"{count} rating" if count == 1 else f"{count} ratings"
    return {"score": score, "count": count, "label": label}


# ─── Translation mapping ──────────────────────────────────────────────────────

def resolve_original_id(cur, tour_id):
    """Map a tour id to the ORIGINAL tour id its ratings key on.

    A translation row has audio_tours.original_tour_id set; its ratings belong
    to the source tour. An original row (or an id with no audio_tours row) maps
    to itself. Uses an already-open cursor so it composes inside a transaction.
    """
    try:
        cur.execute(
            "SELECT original_tour_id FROM audio_tours WHERE id = %s",
            (int(tour_id),),
        )
        row = cur.fetchone()
    except (TypeError, ValueError):
        return tour_id
    if row and row[0]:
        return int(row[0])
    return int(tour_id)


# ─── Download-record authorisation ────────────────────────────────────────────

def has_downloaded(cur, user_id, tour_id, original_id):
    """True if there is an existing download/request record for this user+tour.

    Uses tour_requests (keyed on secret_id), the record the orchestrator writes
    for every tour a user pulls. tour_requests.tour_id is a VARCHAR that holds
    either the numeric audio_tours id or the generation job id, so we match the
    requested id OR its resolved original, as text. Best-effort by design: a
    missing record does NOT block the rating (caller allows + logs).
    """
    try:
        cur.execute(
            """
            SELECT 1 FROM tour_requests
            WHERE secret_id = %s
              AND tour_id IN (%s, %s)
            LIMIT 1
            """,
            (user_id, str(tour_id), str(original_id)),
        )
        return cur.fetchone() is not None
    except Exception:  # noqa: BLE001 — authorisation check must never 500 the rating
        return False


# ─── Writes & reads ───────────────────────────────────────────────────────────

def record_rating(user_id, tour_id, rating):
    """Record (UPSERT) one user's rating of a tour.

    A re-rate replaces the earlier value via the UNIQUE(tour_id, user_id)
    constraint. Translations map to their original before writing. Returns the
    recomputed {score, count, label} plus authorisation info.

    Raises ValueError if rating is not a whole number in 1..10.
    """
    try:
        rating_int = int(rating)
    except (TypeError, ValueError):
        raise ValueError(f"rating must be an integer 1..10, got {rating!r}")
    if rating_int != float(rating):
        raise ValueError(f"rating must be a whole number 1..10, got {rating!r}")
    if not (1 <= rating_int <= 10):
        raise ValueError(f"rating must be in 1..10, got {rating_int}")

    conn = get_connection()
    try:
        cur = conn.cursor()
        original_id = resolve_original_id(cur, tour_id)
        authorized = has_downloaded(cur, user_id, tour_id, original_id)

        cur.execute(
            """
            INSERT INTO tour_ratings (tour_id, user_id, rating)
            VALUES (%s, %s, %s)
            ON CONFLICT (tour_id, user_id)
            DO UPDATE SET rating = EXCLUDED.rating,
                          updated_at = CURRENT_TIMESTAMP
            """,
            (original_id, user_id, rating_int),
        )
        conn.commit()

        result = _get_rating_with_cursor(cur, original_id)
        result["authorized"] = authorized
        result["original_tour_id"] = original_id
        return result
    finally:
        conn.close()


def _get_rating_with_cursor(cur, original_id):
    """Read all real ratings for an ORIGINAL tour id and compute the score."""
    cur.execute(
        "SELECT rating FROM tour_ratings WHERE tour_id = %s",
        (int(original_id),),
    )
    ratings = [int(r[0]) for r in cur.fetchall()]
    return compute_score(ratings)


def get_rating(tour_id):
    """Return {score, count, label} for a tour (translation → source)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        original_id = resolve_original_id(cur, tour_id)
        return _get_rating_with_cursor(cur, original_id)
    finally:
        conn.close()


# ─── Flask API routes ─────────────────────────────────────────────────────────

def register_rating_routes(app):
    """Register tour-rating endpoints on a Flask app (the orchestrator).

    Endpoints:
        POST /tour/<tour_id>/rating   {user_id, rating}  → record/replace
        GET  /tour/<tour_id>/rating                      → {score, count, label}
    """
    from flask import request, jsonify

    @app.route('/tour/<tour_id>/rating', methods=['POST'])
    def api_record_rating(tour_id):
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        user_id = data.get("user_id")
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        if "rating" not in data:
            return jsonify({"error": "rating is required"}), 400

        try:
            result = record_rating(
                user_id=user_id,
                tour_id=tour_id,
                rating=data["rating"],
            )
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500

        if not result.get("authorized"):
            # Per the ticket: allow the rating and LOG that no download record
            # was found, rather than refusing it.
            print(f"[RATING] no download record for user={user_id!r} "
                  f"tour={tour_id} (original={result.get('original_tour_id')}); "
                  f"rating allowed and logged.")
            sys.stdout.flush()

        return jsonify({"status": "ok", **result}), 200

    @app.route('/tour/<tour_id>/rating', methods=['GET'])
    def api_get_rating(tour_id):
        try:
            result = get_rating(tour_id)
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500
        return jsonify(result), 200
