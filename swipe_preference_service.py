#!/usr/bin/env python3
"""
Swipe-to-Sway Preference Engine (LOCAL-101)

Implements Michael's Beta-count preference model from STORY_QUALITY_DESIGN.md §2c:
- Captures like/dislike swipes per stop
- Maintains a per-user preference vector across 3 content axes
- Biases (not filters) stop ordering toward preferred content classes
- Cold start is neutral: new users get today's behaviour exactly

This module provides:
  1. record_feedback()     — store a swipe, update preference vector
  2. get_user_prefs()      — retrieve current preference vector
  3. bias_stop_ordering()  — reorder stops using preference + quality scores
  4. Flask routes          — REST API for mobile consumption

Design decisions documented in SUBMISSION_LOCAL-101.md.
"""

import sys
import os
from decimal import Decimal, ROUND_HALF_UP

# Add parent to path for tests/db_connection
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))
from db_connection import get_connection


# ─── Core Model ──────────────────────────────────────────────────────────────

def record_feedback(user_id, tour_id, job_id, stop_index, swipe,
                    class_details, class_historic, class_social, i_con):
    """
    Record a like/dislike and update the user's preference vector.

    Parameters:
        user_id: str — user's secret_id
        tour_id: int|None — audio_tours.id
        job_id: str|None — generation job_id (links to stop_metrics)
        stop_index: int — which stop (0-indexed)
        swipe: int — +1 (like) or -1 (dislike)
        class_details, class_historic, class_social: float — class distribution (sum≈1)
        i_con: float — informational-context score (0-5)

    Returns:
        dict with the updated preference vector

    The Beta-count update rule (§2c):
        Like:    α_k += c_k * 1.0  (full weight regardless of i_con)
        Dislike: β_k += c_k * (i_con / 5)
                 (low-info dislikes blame the writing, not the topic)
    """
    if swipe not in (-1, 1):
        raise ValueError(f"swipe must be -1 or 1, got {swipe}")

    conn = get_connection()
    try:
        cur = conn.cursor()

        # 1. Insert raw feedback
        cur.execute("""
            INSERT INTO user_stop_feedback
                (user_id, tour_id, job_id, stop_index, swipe,
                 class_details, class_historic, class_social, i_con)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, tour_id, job_id, stop_index, swipe,
              class_details, class_historic, class_social, i_con))

        # 2. Ensure user_class_prefs row exists (cold start = all 1.0)
        cur.execute("""
            INSERT INTO user_class_prefs (user_id)
            VALUES (%s)
            ON CONFLICT (user_id) DO NOTHING
        """, (user_id,))

        # 3. Fetch current alpha/beta
        cur.execute("""
            SELECT alpha_details, beta_details,
                   alpha_historic, beta_historic,
                   alpha_social, beta_social, swipe_count
            FROM user_class_prefs
            WHERE user_id = %s
        """, (user_id,))
        row = cur.fetchone()
        alpha_d, beta_d = float(row[0]), float(row[1])
        alpha_h, beta_h = float(row[2]), float(row[3])
        alpha_s, beta_s = float(row[4]), float(row[5])
        swipe_count = row[6]

        # 4. Apply Beta-count update (§2c)
        c = [float(class_details), float(class_historic), float(class_social)]
        icon_weight = float(i_con) / 5.0  # dislike weight; likes use 1.0

        if swipe == 1:  # LIKE — full weight
            alpha_d += c[0] * 1.0
            alpha_h += c[1] * 1.0
            alpha_s += c[2] * 1.0
        else:  # DISLIKE — weighted by i_con/5
            beta_d += c[0] * icon_weight
            beta_h += c[1] * icon_weight
            beta_s += c[2] * icon_weight

        # 5. Derive p_k = α_k / (α_k + β_k)
        pref_d = alpha_d / (alpha_d + beta_d)
        pref_h = alpha_h / (alpha_h + beta_h)
        pref_s = alpha_s / (alpha_s + beta_s)

        # 6. Persist
        cur.execute("""
            UPDATE user_class_prefs
            SET alpha_details = %s, beta_details = %s,
                alpha_historic = %s, beta_historic = %s,
                alpha_social = %s, beta_social = %s,
                pref_details = %s, pref_historic = %s, pref_social = %s,
                swipe_count = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
        """, (alpha_d, beta_d, alpha_h, beta_h, alpha_s, beta_s,
              pref_d, pref_h, pref_s, swipe_count + 1, user_id))

        conn.commit()

        return {
            "user_id": user_id,
            "pref_details": round(pref_d, 4),
            "pref_historic": round(pref_h, 4),
            "pref_social": round(pref_s, 4),
            "confidence": {
                "details": round(alpha_d + beta_d - 2, 2),
                "historic": round(alpha_h + beta_h - 2, 2),
                "social": round(alpha_s + beta_s - 2, 2),
            },
            "swipe_count": swipe_count + 1
        }
    finally:
        conn.close()


def get_user_prefs(user_id):
    """
    Retrieve current preference vector for a user.

    Returns None if user has no preference history (cold start).
    Returns dict with p_k values and confidence (interpretable numbers).
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT alpha_details, beta_details,
                   alpha_historic, beta_historic,
                   alpha_social, beta_social,
                   pref_details, pref_historic, pref_social,
                   swipe_count, updated_at
            FROM user_class_prefs
            WHERE user_id = %s
        """, (user_id,))
        row = cur.fetchone()
        if row is None:
            return None  # Cold start — no history

        return {
            "user_id": user_id,
            "pref_details": float(row[6]),
            "pref_historic": float(row[7]),
            "pref_social": float(row[8]),
            "alpha_beta": {
                "details": {"alpha": float(row[0]), "beta": float(row[1])},
                "historic": {"alpha": float(row[2]), "beta": float(row[3])},
                "social": {"alpha": float(row[4]), "beta": float(row[5])},
            },
            "confidence": {
                "details": round(float(row[0]) + float(row[1]) - 2, 2),
                "historic": round(float(row[2]) + float(row[3]) - 2, 2),
                "social": round(float(row[4]) + float(row[5]) - 2, 2),
            },
            "swipe_count": row[9],
            "updated_at": row[10].isoformat() if row[10] else None,
            "interpretation": _interpret_prefs(float(row[6]), float(row[7]), float(row[8]))
        }
    finally:
        conn.close()


def _interpret_prefs(pref_d, pref_h, pref_s):
    """
    Human-readable interpretation of the preference vector.
    Michael's requirement: "prefers historical, dislikes social" — not opaque.
    """
    labels = {"details": pref_d, "historic": pref_h, "social": pref_s}
    parts = []
    for name, p in sorted(labels.items(), key=lambda x: -x[1]):
        if p > 0.6:
            parts.append(f"prefers {name} ({p:.2f})")
        elif p < 0.4:
            parts.append(f"dislikes {name} ({p:.2f})")
        else:
            parts.append(f"neutral on {name} ({p:.2f})")
    return "; ".join(parts)


def bias_stop_ordering(stops, user_id=None, preference_weight=0.3):
    """
    Reorder stops using preference bias. BIAS, not filter.

    Parameters:
        stops: list of dicts, each with at minimum:
            - stop_index: int
            - stop_title: str
            - i_con: float
            - class_details, class_historic, class_social: float
        user_id: str|None — if None or no prefs, returns original order (cold start)
        preference_weight: float — how much preference influences ordering (0-1)
            0.0 = today's behaviour (quality-only)
            1.0 = preference dominates (dangerous — monoculture)
            0.3 = default — meaningful bias while preserving quality primacy

    Returns:
        list of stops in biased order, each augmented with:
            - quality_score: float (i_con normalized)
            - preference_score: float (alignment with user prefs)
            - combined_score: float (weighted blend)
            - rank_change: int (positions moved from quality-only ordering)

    Design constraints (from task spec):
        - Quality ranks first: a RICH stop the user dislikes beats a THIN stop they like
        - Disliked class still appears: bias, never zero
        - Cold start = neutral: identical to today's output
    """
    if not stops:
        return []

    # Cold start: no user or no prefs → return quality-ordered (today's behavior)
    prefs = None
    if user_id:
        prefs = get_user_prefs(user_id)

    if prefs is None or prefs.get("swipe_count", 0) == 0:
        # No personalization — order by quality (i_con) descending
        quality_ordered = sorted(stops, key=lambda s: float(s.get("i_con", 0)), reverse=True)
        for i, s in enumerate(quality_ordered):
            s["quality_score"] = float(s.get("i_con", 0)) / 5.0
            s["preference_score"] = 0.5  # neutral
            s["combined_score"] = s["quality_score"]
            s["rank_change"] = 0
        return quality_ordered

    # Has preferences — compute biased ordering
    p_d = prefs["pref_details"]
    p_h = prefs["pref_historic"]
    p_s = prefs["pref_social"]

    # Step 1: Quality-only order (baseline for rank_change computation)
    quality_ordered = sorted(
        range(len(stops)),
        key=lambda i: float(stops[i].get("i_con", 0)),
        reverse=True
    )
    quality_ranks = {idx: rank for rank, idx in enumerate(quality_ordered)}

    # Step 2: Score each stop
    scored = []
    for i, stop in enumerate(stops):
        icon = float(stop.get("i_con", 0))
        c_d = float(stop.get("class_details", 0.333))
        c_h = float(stop.get("class_historic", 0.333))
        c_s = float(stop.get("class_social", 0.333))

        # Quality score: i_con normalized to [0,1]
        quality_score = icon / 5.0

        # Preference score: Σ c_k * p_k (§2c formula)
        # This ranges from ~0 to ~1 depending on alignment
        preference_score = c_d * p_d + c_h * p_h + c_s * p_s

        # Combined: quality dominates (1 - weight), preference adds (weight)
        combined = (1 - preference_weight) * quality_score + preference_weight * preference_score

        scored.append({
            **stop,
            "quality_score": round(quality_score, 4),
            "preference_score": round(preference_score, 4),
            "combined_score": round(combined, 4),
            "_original_index": i,
        })

    # Step 3: Sort by combined score (descending)
    scored.sort(key=lambda s: s["combined_score"], reverse=True)

    # Step 4: Compute rank_change relative to quality-only ordering
    for new_rank, stop in enumerate(scored):
        orig_idx = stop["_original_index"]
        old_rank = quality_ranks[orig_idx]
        stop["rank_change"] = old_rank - new_rank  # positive = promoted
        del stop["_original_index"]

    return scored


# ─── Flask API Routes ────────────────────────────────────────────────────────

def register_preference_routes(app):
    """
    Register swipe-to-sway preference endpoints on a Flask app.

    Endpoints:
        POST /user/<user_id>/stop-feedback   — record a like/dislike
        GET  /user/<user_id>/preferences     — get preference vector
        POST /stops/biased-order             — get biased stop ordering for a user
    """
    from flask import request, jsonify

    @app.route('/user/<user_id>/stop-feedback', methods=['POST'])
    def api_record_feedback(user_id):
        """
        Record a swipe (like/dislike) on a stop.

        Request body:
        {
            "tour_id": 14,                  // int, optional
            "job_id": "abc-123",            // str, optional
            "stop_index": 2,                // int, required
            "swipe": 1,                     // int, required: +1=like, -1=dislike
            "class_details": 0.30,          // float, required
            "class_historic": 0.50,         // float, required
            "class_social": 0.20,           // float, required
            "i_con": 4.2                    // float, required (0-5)
        }

        Response 200:
        {
            "status": "ok",
            "prefs": { "pref_details": 0.52, "pref_historic": 0.55, ... }
        }
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        required = ["stop_index", "swipe", "class_details", "class_historic", "class_social", "i_con"]
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({"error": f"Missing fields: {missing}"}), 400

        swipe = data["swipe"]
        if swipe not in (-1, 1):
            return jsonify({"error": "swipe must be -1 or 1"}), 400

        try:
            result = record_feedback(
                user_id=user_id,
                tour_id=data.get("tour_id"),
                job_id=data.get("job_id"),
                stop_index=data["stop_index"],
                swipe=swipe,
                class_details=data["class_details"],
                class_historic=data["class_historic"],
                class_social=data["class_social"],
                i_con=data["i_con"],
            )
            return jsonify({"status": "ok", "prefs": result}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/user/<user_id>/preferences', methods=['GET'])
    def api_get_preferences(user_id):
        """
        Get the user's current preference vector.

        Response 200 (has history):
        {
            "user_id": "abc",
            "pref_details": 0.52,
            "pref_historic": 0.71,
            "pref_social": 0.33,
            "confidence": { "details": 1.5, "historic": 2.1, "social": 1.8 },
            "interpretation": "prefers historic (0.71); neutral on details (0.52); dislikes social (0.33)",
            "swipe_count": 8
        }

        Response 200 (cold start):
        {
            "user_id": "abc",
            "cold_start": true,
            "pref_details": 0.5,
            "pref_historic": 0.5,
            "pref_social": 0.5,
            "interpretation": "No swipe history — neutral preferences (today's behavior)"
        }
        """
        prefs = get_user_prefs(user_id)
        if prefs is None:
            return jsonify({
                "user_id": user_id,
                "cold_start": True,
                "pref_details": 0.5,
                "pref_historic": 0.5,
                "pref_social": 0.5,
                "interpretation": "No swipe history — neutral preferences (today's behavior)"
            }), 200
        return jsonify(prefs), 200

    @app.route('/stops/biased-order', methods=['POST'])
    def api_biased_order():
        """
        Reorder stops according to user preferences.

        Request body:
        {
            "user_id": "abc",               // str, required
            "stops": [                      // array, required
                {
                    "stop_index": 0,
                    "stop_title": "Promenade des Anglais",
                    "i_con": 4.2,
                    "class_details": 0.26,
                    "class_historic": 0.42,
                    "class_social": 0.32
                },
                ...
            ],
            "preference_weight": 0.3        // float, optional (0-1, default 0.3)
        }

        Response 200:
        {
            "user_id": "abc",
            "ordering": [ ... stops in biased order with scores ... ],
            "personalized": true/false,
            "preference_vector": { "details": 0.52, "historic": 0.71, "social": 0.33 }
        }
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        user_id = data.get("user_id")
        stops = data.get("stops")
        if not user_id or not stops:
            return jsonify({"error": "user_id and stops are required"}), 400

        weight = data.get("preference_weight", 0.3)

        result = bias_stop_ordering(stops, user_id=user_id, preference_weight=weight)

        prefs = get_user_prefs(user_id)
        personalized = prefs is not None and prefs.get("swipe_count", 0) > 0

        response = {
            "user_id": user_id,
            "ordering": result,
            "personalized": personalized,
        }
        if personalized:
            response["preference_vector"] = {
                "details": prefs["pref_details"],
                "historic": prefs["pref_historic"],
                "social": prefs["pref_social"],
            }
        else:
            response["preference_vector"] = {"details": 0.5, "historic": 0.5, "social": 0.5}

        return jsonify(response), 200
