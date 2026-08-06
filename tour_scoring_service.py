#!/usr/bin/env python3
"""
Tour In-Flight Scoring Service (LOCAL-306)

Scores every tour before delivery, persists the result to `tour_scores`.
Gates NOTHING — a catastrophic score still delivers unchanged.

Also re-scores after a client edit and reports the delta (facts moved,
classifications that changed band, sourced facts removed, unsourced claims
added). The delta evaluates the TOUR, never the user.

No LLM calls. No network. Pure rule-based scoring via tour_rubric_scorer.

Schema addition (additive only):
    CREATE TABLE tour_scores (...)
    See ensure_tour_scores_table() or migrations/create_tour_scores.sql.
"""
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

# --- Import the scorer (LOCAL-304/305 own it; we import, never modify) ------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tour_rubric_scorer import (
    parse_tour,
    analyze_stop,
    classify_stop,
    compute_score,
    detect_venue_identity,
    TourScore,
    StopAnalysis,
)

# --- DB connection: use tests/db_connection.py pattern ----------------------
# Import at function call time to allow tests to set env before first connect.

# Version string — bump when scoring logic changes (helps track which scorer
# produced which row). This is the LOCAL-306 integration version, not the
# rubric version (which lives in tour_rubric_scorer.py).
SCORER_VERSION = "LOCAL-306-v1"


def _get_code_sha():
    """SHA-256 of tour_rubric_scorer.py source, truncated to 12 hex chars."""
    scorer_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "tour_rubric_scorer.py"
    )
    try:
        with open(scorer_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:12]
    except Exception:
        return "unknown"


def _get_connection():
    """Get a psycopg2 connection via the shared db_connection helper."""
    # Add tests/ to path so we can import db_connection
    tests_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests")
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    from db_connection import get_connection
    return get_connection()


def ensure_tour_scores_table():
    """Create tour_scores table if it does not exist (additive schema only).

    This is idempotent — safe to call on every startup.
    """
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tour_scores (
                id              SERIAL PRIMARY KEY,
                tour_id         INTEGER,
                tour_name       TEXT,
                scored_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                code_sha        VARCHAR(12),
                n_requested     INTEGER NOT NULL,
                n_delivered     INTEGER NOT NULL,
                base_score      REAL NOT NULL,
                structural      REAL NOT NULL,
                correlation     REAL NOT NULL,
                venue_identity  REAL NOT NULL,
                total           REAL NOT NULL,
                per_stop        JSONB NOT NULL,
                scorer_version  VARCHAR(64) NOT NULL,
                scoring_ms      REAL,
                is_rescore      BOOLEAN NOT NULL DEFAULT FALSE,
                previous_score_id INTEGER,
                delta           JSONB
            );
        """)
        # Index for fast lookup by tour_id
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_tour_scores_tour_id
            ON tour_scores (tour_id);
        """)
        conn.commit()
        cur.close()
    finally:
        conn.close()


def score_tour_text(tour_text, n_requested, tour_id=None, tour_name=None,
                    is_rescore=False, previous_score_id=None, delta=None):
    """Score a tour and persist the result. Returns the TourScore and row ID.

    Args:
        tour_text: The complete assembled tour text (post all gates).
        n_requested: Number of stops requested.
        tour_id: Database ID of the tour (may be None if not yet stored).
        tour_name: Human name of the tour.
        is_rescore: True if this is a re-score after an edit.
        previous_score_id: ID of the previous score row (for re-scores).
        delta: Dict describing what changed (for re-scores).

    Returns:
        (TourScore, row_id, scoring_ms) or (None, None, 0.0) on failure.
    """
    if not tour_text or not tour_text.strip():
        print("[SCORING] Skipped: empty tour_text")
        return None, None, 0.0

    t0 = time.perf_counter()

    # Parse and score
    stops_parsed = parse_tour(tour_text)
    if not stops_parsed:
        print("[SCORING] Skipped: no stops parsed from tour_text")
        return None, None, 0.0

    all_stops = stops_parsed  # needed for cross-stop analysis
    stop_analyses = []
    for stop in stops_parsed:
        sa = analyze_stop(stop, all_stops)
        cls, evidence = classify_stop(sa)
        sa.classification = cls
        sa.classification_evidence = evidence
        stop_analyses.append(sa)

    venue_facts = detect_venue_identity(tour_text)
    tour_score = compute_score(stop_analyses, n_requested, venue_facts)

    scoring_ms = (time.perf_counter() - t0) * 1000.0

    # Build per_stop JSON
    per_stop_data = []
    for sa in stop_analyses:
        per_stop_data.append({
            "index": sa.index,
            "title": sa.title,
            "classification": sa.classification,
            "facts": sa.distinct_fact_count,
            "sentences": sa.content_sentences,
            "density": round(sa.fact_density, 3),
            "filler": round(sa.generic_filler_fraction, 3),
            "groundedness": round(sa.groundedness_fraction, 3),
        })

    code_sha = _get_code_sha()

    # Persist
    row_id = None
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tour_scores (
                tour_id, tour_name, code_sha,
                n_requested, n_delivered,
                base_score, structural, correlation, venue_identity, total,
                per_stop, scorer_version, scoring_ms,
                is_rescore, previous_score_id, delta
            ) VALUES (
                %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s
            ) RETURNING id;
        """, (
            tour_id, tour_name, code_sha,
            tour_score.n_requested, tour_score.n_delivered,
            round(tour_score.base_score, 2),
            round(tour_score.structural_surcharge, 2),
            round(tour_score.correlation_bonus, 2),
            round(tour_score.venue_identity_bonus, 2),
            round(tour_score.total_score, 2),
            json.dumps(per_stop_data),
            SCORER_VERSION,
            round(scoring_ms, 2),
            is_rescore,
            previous_score_id,
            json.dumps(delta) if delta else None,
        ))
        row_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[SCORING] WARNING: Could not persist score: {e}")
        # Scoring failure must NOT block delivery (LOCAL-306 rule)

    print(
        f"[SCORING] tour_id={tour_id} total={tour_score.total_score:.1f} "
        f"({tour_score.n_delivered}/{tour_score.n_requested} stops) "
        f"base={tour_score.base_score:.1f} structural={tour_score.structural_surcharge:.1f} "
        f"correlation={tour_score.correlation_bonus:.1f} venue_id={tour_score.venue_identity_bonus:.1f} "
        f"time={scoring_ms:.1f}ms row_id={row_id}"
    )

    return tour_score, row_id, scoring_ms


def compute_edit_delta(original_text, edited_text, n_requested):
    """Compute a factual delta between original and edited tour text.

    Returns a dict describing what moved — never a verdict on the user.

    The delta contains:
      - facts_before / facts_after (per stop)
      - classifications_changed (stops that changed band)
      - sourced_facts_removed (facts present in original, absent in edit)
      - unsourced_claims_added (claims in edit not present in original)

    Wording constraint: the delta describes the TOUR's change, not the user's
    quality. "This edit removed 3 sourced facts" is useful. "Your edit scored
    62" is presumptuous.
    """
    # Score both versions
    orig_stops = parse_tour(original_text)
    edit_stops = parse_tour(edited_text)

    if not orig_stops or not edit_stops:
        return None

    # Analyze original
    orig_analyses = []
    for stop in orig_stops:
        sa = analyze_stop(stop, orig_stops)
        cls, ev = classify_stop(sa)
        sa.classification = cls
        sa.classification_evidence = ev
        orig_analyses.append(sa)

    # Analyze edited
    edit_analyses = []
    for stop in edit_stops:
        sa = analyze_stop(stop, edit_stops)
        cls, ev = classify_stop(sa)
        sa.classification = cls
        sa.classification_evidence = ev
        edit_analyses.append(sa)

    # Build per-stop comparison (match by index)
    per_stop_delta = []
    classifications_changed = []
    total_facts_removed = 0
    total_facts_added = 0

    # Map original stops by index for lookup
    orig_by_index = {sa.index: sa for sa in orig_analyses}
    edit_by_index = {sa.index: sa for sa in edit_analyses}

    all_indices = sorted(set(list(orig_by_index.keys()) + list(edit_by_index.keys())))

    for idx in all_indices:
        orig_sa = orig_by_index.get(idx)
        edit_sa = edit_by_index.get(idx)

        entry = {"index": idx}
        if orig_sa:
            entry["title_before"] = orig_sa.title
            entry["facts_before"] = orig_sa.distinct_fact_count
            entry["classification_before"] = orig_sa.classification
        if edit_sa:
            entry["title_after"] = edit_sa.title
            entry["facts_after"] = edit_sa.distinct_fact_count
            entry["classification_after"] = edit_sa.classification

        # Classification band change
        if orig_sa and edit_sa and orig_sa.classification != edit_sa.classification:
            classifications_changed.append({
                "index": idx,
                "title": orig_sa.title,
                "before": orig_sa.classification,
                "after": edit_sa.classification,
            })

        # Fact count changes
        if orig_sa and edit_sa:
            diff = edit_sa.distinct_fact_count - orig_sa.distinct_fact_count
            if diff < 0:
                total_facts_removed += abs(diff)
            elif diff > 0:
                total_facts_added += diff

        per_stop_delta.append(entry)

    delta = {
        "per_stop": per_stop_delta,
        "classifications_changed": classifications_changed,
        "sourced_facts_removed": total_facts_removed,
        "unsourced_claims_added": total_facts_added,
        "stops_before": len(orig_analyses),
        "stops_after": len(edit_analyses),
    }

    return delta


def score_edited_tour(original_text, edited_text, n_requested,
                      tour_id=None, tour_name=None, original_score_id=None):
    """Score an edited tour and record the delta.

    This produces a second tour_scores row (is_rescore=True) linked to the
    original via previous_score_id.

    Returns (TourScore, row_id, delta, scoring_ms).
    """
    delta = compute_edit_delta(original_text, edited_text, n_requested)

    tour_score, row_id, scoring_ms = score_tour_text(
        edited_text,
        n_requested,
        tour_id=tour_id,
        tour_name=tour_name,
        is_rescore=True,
        previous_score_id=original_score_id,
        delta=delta,
    )

    if delta:
        # Log the delta (no verdict on the user)
        print(
            f"[SCORING DELTA] tour_id={tour_id}: "
            f"sourced facts removed={delta['sourced_facts_removed']}, "
            f"unsourced claims added={delta['unsourced_claims_added']}, "
            f"classifications changed={len(delta['classifications_changed'])}"
        )

    return tour_score, row_id, delta, scoring_ms


def update_tour_id_on_score(score_row_id, tour_id):
    """Backfill tour_id on a score row after the tour is stored.

    The scoring happens before store_audio_tour() creates the row, so the
    tour_id is not yet known. This backfills it after storage succeeds.
    """
    if not score_row_id or not tour_id:
        return
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE tour_scores SET tour_id = %s WHERE id = %s",
            (tour_id, score_row_id)
        )
        conn.commit()
        cur.close()
        conn.close()
        print(f"[SCORING] Backfilled tour_id={tour_id} on score row {score_row_id}")
    except Exception as e:
        print(f"[SCORING] WARNING: Could not backfill tour_id: {e}")


def get_latest_score_for_tour(tour_id):
    """Get the most recent score row ID for a given tour_id."""
    if not tour_id:
        return None
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM tour_scores WHERE tour_id = %s ORDER BY scored_at DESC LIMIT 1",
            (tour_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None
