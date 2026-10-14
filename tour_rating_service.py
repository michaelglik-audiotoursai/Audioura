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


def compute_score(ratings, prior=None):
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
    # [LOCAL-685] The tour's evaluated score (editor_score, 5.0–8.0) replaces the
    # flat 7.5 when it has one. Same rule as map-delivery's compute_rating.
    base = float(prior) if prior is not None else DEFAULT_SCORE

    if count == 0:
        return {"score": base, "count": 0,
                "label": "Audioura score" if prior is not None else "New"}

    if count < MEDIAN_SWITCH_COUNT:  # 1, 2, or 3 real ratings
        blended = [base] + [float(r) for r in ratings]
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

def _validate_rating(rating):
    """Validate a tour rating and return it as an int in 1..10.

    Raises ValueError if rating is not a whole number in 1..10. Shared by the
    route (pre-gate 400) and record_rating (defence in depth).
    """
    try:
        rating_int = int(rating)
    except (TypeError, ValueError):
        raise ValueError(f"rating must be an integer 1..10, got {rating!r}")
    if rating_int != float(rating):
        raise ValueError(f"rating must be a whole number 1..10, got {rating!r}")
    if not (1 <= rating_int <= 10):
        raise ValueError(f"rating must be in 1..10, got {rating_int}")
    return rating_int


def _compute_verified_and_creator(cur, user_id, original_id):
    """[LOCAL-672] Best-effort (verified_flag, is_creator) for a rating write.

    Delegates to tour_reviews_service for the verified rule (store-verified
    purchase that unlocked this tour, with the D624 level-purchase fallback) and
    the creator resolution. Imported LAZILY to avoid an import cycle (the reviews
    service imports this module). If the reviews module or its tables are not
    present (older deploy), verified degrades to False and is_creator to False —
    never raising, so LOCAL-670 rating behaviour is unchanged.
    """
    try:
        import tour_reviews_service as reviews_svc  # lazy: breaks the import cycle
    except Exception:  # noqa: BLE001
        return False, False
    try:
        creator = reviews_svc.resolve_tour_creator(cur, original_id)
    except Exception:  # noqa: BLE001
        creator = None
    is_creator = creator is not None and str(creator) == str(user_id)
    if is_creator:
        return False, True
    try:
        verified = reviews_svc.compute_verified(cur, user_id, original_id)
    except Exception:  # noqa: BLE001
        verified = False
    return bool(verified), False


def record_rating(user_id, tour_id, rating):
    """Record (UPSERT) one user's rating of a tour.

    A re-rate replaces the earlier value via the UNIQUE(tour_id, user_id)
    constraint. Translations map to their original before writing. Returns the
    recomputed {score, count, label} plus authorisation info.

    [LOCAL-672] Also computes and stores the `verified` flag (store-verified
    purchase that unlocked this tour; D624 level-purchase fallback) and enforces
    the "a creator cannot rate their own tour" protection. The verified flag is
    additive — a tour with no purchases just reads unverified, exactly as before.

    Raises ValueError if rating is not a whole number in 1..10, or if the rater
    is the tour's creator.
    """
    rating_int = _validate_rating(rating)

    conn = get_connection()
    try:
        cur = conn.cursor()
        # Ensure the verified column exists before we write it (self-healing,
        # idempotent — mirrors the reviews service and the 021 migration).
        try:
            cur.execute(
                "ALTER TABLE tour_ratings "
                "ADD COLUMN IF NOT EXISTS verified BOOLEAN NOT NULL DEFAULT FALSE"
            )
        except Exception:  # noqa: BLE001 — never block a rating on the DDL
            conn.rollback()
        original_id = resolve_original_id(cur, tour_id)
        authorized = has_downloaded(cur, user_id, tour_id, original_id)

        # [LOCAL-672] Protection: a creator cannot rate their own tour.
        verified, is_creator = _compute_verified_and_creator(cur, user_id, original_id)
        if is_creator:
            raise ValueError("a tour's creator cannot rate their own tour")

        cur.execute(
            """
            INSERT INTO tour_ratings (tour_id, user_id, rating, verified)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (tour_id, user_id)
            DO UPDATE SET rating = EXCLUDED.rating,
                          verified = EXCLUDED.verified,
                          updated_at = CURRENT_TIMESTAMP
            """,
            (original_id, user_id, rating_int, verified),
        )
        conn.commit()

        result = _get_rating_with_cursor(cur, original_id)
        result["authorized"] = authorized
        result["verified"] = verified
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
    # [LOCAL-685] The original's evaluated score, when scored.
    prior = None
    try:
        cur.execute("SELECT editor_score FROM audio_tours WHERE id = %s", (int(original_id),))
        row = cur.fetchone()
        if row and row[0] is not None:
            prior = float(row[0])
    except Exception:
        try:
            cur.connection.rollback()
        except Exception:
            pass
    return compute_score(ratings, prior=prior)


def get_rating(tour_id):
    """Return {score, count, label} for a tour (translation → source)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        original_id = resolve_original_id(cur, tour_id)
        return _get_rating_with_cursor(cur, original_id)
    finally:
        conn.close()


# ─── Listened-stops gate (LOCAL-670B) ─────────────────────────────────────────
#
# Michael: "Can we not allow rating if people did not listen to at least 2
# stops ... similar to Audible." A tour rating is accepted only once the user
# has finished (heard to >= 80% or the end — the app decides that; the server
# only records the fact) at least REQUIRED_LISTENED_STOPS DISTINCT stops. A tour
# with fewer stops than that threshold requires ALL of its stops instead, so a
# 1-stop tour is rateable after that single stop.

REQUIRED_LISTENED_STOPS = 2


# Self-healing DDL, identical to migration/sql/020_tour_listens.sql, so the
# service works whether or not the migration was run (mirrors tour_ratings).
_TOUR_LISTENS_DDL = """
    CREATE TABLE IF NOT EXISTS tour_listens (
        id          SERIAL PRIMARY KEY,
        tour_id     INTEGER NOT NULL,
        user_id     VARCHAR(255) NOT NULL,
        stop_index  INTEGER NOT NULL CHECK (stop_index >= 0),
        created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_tour_listens_tour_user_stop UNIQUE (tour_id, user_id, stop_index)
    )
"""


def _ensure_tour_listens_table(cur):
    """Create tour_listens if absent. Idempotent; safe to call on every write."""
    cur.execute(_TOUR_LISTENS_DDL)


def tour_stops_count(cur, original_id):
    """The number of stops in a tour, or None if unknown.

    Reads audio_tours.stops_count for the ORIGINAL id. None (column NULL or no
    row) means "unknown"; the gate then falls back to the full threshold rather
    than lowering the bar for a tour whose length we cannot confirm.
    """
    try:
        cur.execute(
            "SELECT stops_count FROM audio_tours WHERE id = %s",
            (int(original_id),),
        )
        row = cur.fetchone()
    except Exception:  # noqa: BLE001
        return None
    if row and row[0] is not None:
        try:
            return int(row[0])
        except (TypeError, ValueError):
            return None
    return None


def required_listened_stops(cur, original_id):
    """How many distinct listened stops this tour needs before it can be rated.

    REQUIRED_LISTENED_STOPS (2) normally; but a tour with fewer stops than that
    requires ALL of its stops — so a 1-stop tour needs 1, a 0/unknown tour keeps
    the full 2. Never returns less than 1.
    """
    stops = tour_stops_count(cur, original_id)
    if stops is None or stops >= REQUIRED_LISTENED_STOPS:
        return REQUIRED_LISTENED_STOPS
    return max(1, stops)


def count_listened_stops(cur, user_id, original_id):
    """Distinct stops this user has finished on this (original) tour."""
    try:
        cur.execute(
            "SELECT COUNT(DISTINCT stop_index) FROM tour_listens "
            "WHERE tour_id = %s AND user_id = %s",
            (int(original_id), user_id),
        )
        row = cur.fetchone()
    except Exception:  # noqa: BLE001
        return 0
    return int(row[0]) if row and row[0] is not None else 0


def record_listen(user_id, tour_id, stop_index):
    """Record (idempotently) that a user finished one stop of a tour.

    Translations map to their original before writing, so listens key on the
    ORIGINAL id exactly like ratings. Re-finishing a stop UPSERTs onto the
    UNIQUE(tour_id, user_id, stop_index) constraint and never adds a duplicate.
    Returns {original_tour_id, stop_index, listened_count, required, enough}.

    Raises ValueError if stop_index is not a non-negative integer.
    """
    try:
        stop_int = int(stop_index)
    except (TypeError, ValueError):
        raise ValueError(f"stop_index must be a non-negative integer, got {stop_index!r}")
    if stop_int != float(stop_index) or stop_int < 0:
        raise ValueError(f"stop_index must be a non-negative integer, got {stop_index!r}")

    conn = get_connection()
    try:
        cur = conn.cursor()
        _ensure_tour_listens_table(cur)
        original_id = resolve_original_id(cur, tour_id)
        cur.execute(
            """
            INSERT INTO tour_listens (tour_id, user_id, stop_index)
            VALUES (%s, %s, %s)
            ON CONFLICT (tour_id, user_id, stop_index) DO NOTHING
            """,
            (original_id, user_id, stop_int),
        )
        conn.commit()

        listened = count_listened_stops(cur, user_id, original_id)
        required = required_listened_stops(cur, original_id)
        return {
            "original_tour_id": original_id,
            "stop_index": stop_int,
            "listened_count": listened,
            "required": required,
            "enough": listened >= required,
        }
    finally:
        conn.close()


def listened_status(user_id, tour_id):
    """Read-only {listened_count, required, enough} for a (user, tour)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        _ensure_tour_listens_table(cur)
        original_id = resolve_original_id(cur, tour_id)
        listened = count_listened_stops(cur, user_id, original_id)
        required = required_listened_stops(cur, original_id)
        return {
            "original_tour_id": original_id,
            "listened_count": listened,
            "required": required,
            "enough": listened >= required,
        }
    finally:
        conn.close()


def check_listened_enough(user_id, tour_id):
    """Gate helper for the rating POST: (enough, info) in one connection.

    info is {listened_count, required, enough, original_tour_id}. Opened on its
    own connection so record_rating keeps its own transaction boundary.
    """
    info = listened_status(user_id, tour_id)
    return info["enough"], info


# ─── Batch sync (LOCAL-670C) ──────────────────────────────────────────────────
#
# Michael (2026-10-10): tours play fully offline, so the app records "listened",
# ratings, reviews and per-stop thumbs LOCALLY and ships them in one batch when a
# connection returns:  POST /sync { user_id, items:[…] }.
#
# Each item carries a client-generated UUID; the batch is IDEMPOTENT on it — a
# retried item (dropped connection after the server committed) is a no-op that
# reports "duplicate". The 670B listened-stops gate counts listens in the SAME
# batch, so an offline listen-then-rate pair is accepted together: we apply all
# `listened` items first, then evaluate each `rating` against the now-updated DB.
#
# Rejections (per-item, returned inside a 2xx so the client can drop exactly the
# bad item): a timestamp more than SYNC_MAX_FUTURE_SKEW in the future, or a
# `listened` event for a stop the tour does not have. A translation id maps to
# its SOURCE (670B rule). D650: a `thumb` is an INTERNAL signal — it updates
# personalization / stop quality only and is NEVER mixed into the tour score.

from datetime import datetime, timedelta, timezone  # noqa: E402

# A client clock up to this far ahead of the server is tolerated (clock drift);
# beyond it the timestamp is rejected as implausible/future.
SYNC_MAX_FUTURE_SKEW = timedelta(minutes=10)


# Self-healing idempotency ledger: one row per processed client UUID. Lets a
# retried batch skip already-applied items uniformly across all item types
# (thumbs have no natural unique key, so this is what makes them idempotent).
_SYNC_ITEMS_DDL = """
    CREATE TABLE IF NOT EXISTS sync_items (
        client_uuid  VARCHAR(64) PRIMARY KEY,
        user_id      VARCHAR(255) NOT NULL,
        item_type    VARCHAR(32) NOT NULL,
        processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
"""

# Self-healing store for text reviews arriving through the offline outbox
# (LOCAL-672 lands the curated review UI later; the outbox can already carry a
# review today, and "nothing is lost" is the rule). Deliberately a DISTINCT
# table from any existing `tour_reviews` so we never collide with another
# feature's schema. One review per (tour, user); a later review replaces the
# earlier one.
_TOUR_REVIEWS_DDL = """
    CREATE TABLE IF NOT EXISTS tour_review_sync (
        id         SERIAL PRIMARY KEY,
        tour_id    INTEGER NOT NULL,
        user_id    VARCHAR(255) NOT NULL,
        review     TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_tour_review_sync_tour_user UNIQUE (tour_id, user_id)
    )
"""


def _ensure_sync_tables(cur):
    """Create the sync ledger + reviews table if absent. Idempotent."""
    cur.execute(_SYNC_ITEMS_DDL)
    cur.execute(_TOUR_REVIEWS_DDL)


def _parse_created_at(value):
    """Parse an ISO-8601 timestamp to an aware UTC datetime, or None if absent/
    unparseable. A trailing 'Z' (what the app sends) is accepted."""
    if not value:
        return None
    try:
        s = str(value).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _is_future_skew(created_at, now=None):
    """True if [created_at] is more than SYNC_MAX_FUTURE_SKEW ahead of now."""
    if created_at is None:
        return False  # a missing timestamp is not "in the future"
    now = now or datetime.now(timezone.utc)
    return created_at - now > SYNC_MAX_FUTURE_SKEW


def _already_processed(cur, client_uuid):
    cur.execute("SELECT 1 FROM sync_items WHERE client_uuid = %s", (client_uuid,))
    return cur.fetchone() is not None


def _mark_processed(cur, client_uuid, user_id, item_type):
    cur.execute(
        """
        INSERT INTO sync_items (client_uuid, user_id, item_type)
        VALUES (%s, %s, %s)
        ON CONFLICT (client_uuid) DO NOTHING
        """,
        (client_uuid, user_id, item_type),
    )


def _sync_order_rank(item_type):
    """Apply listens before the ratings that depend on them (gate counts them
    in-batch); thumbs/reviews in between."""
    if item_type == "listened":
        return 0
    if item_type == "rating":
        return 2
    return 1


def _apply_sync_item(cur, item, batch_user_id):
    """Apply one validated, not-yet-processed item on an OPEN cursor.

    Returns the status string: 'accepted' or 'invalid'. The caller commits and
    records the client_uuid. Validation (future skew, nonexistent stop) is done
    here so the whole batch shares one connection/transaction and a rating sees
    this batch's listens.
    """
    item_type = item.get("type")
    user_id = item.get("user_id") or batch_user_id
    tour_id = item.get("tour_id")
    created_at = _parse_created_at(item.get("created_at"))

    # Reject implausible future timestamps (clock skew guard) for every type.
    if _is_future_skew(created_at):
        return "invalid"

    original_id = resolve_original_id(cur, tour_id) if tour_id is not None else None

    if item_type == "listened":
        stop_index = item.get("stop_index")
        try:
            stop_int = int(stop_index)
        except (TypeError, ValueError):
            return "invalid"
        if stop_int < 0:
            return "invalid"
        # Reject a listen for a stop the tour does not have. stops_count may be
        # unknown (None) — then we cannot disprove it, so we accept (same
        # permissive stance the gate takes on unknown length).
        stops = tour_stops_count(cur, original_id)
        if stops is not None and stop_int >= stops:
            return "invalid"
        cur.execute(
            """
            INSERT INTO tour_listens (tour_id, user_id, stop_index)
            VALUES (%s, %s, %s)
            ON CONFLICT (tour_id, user_id, stop_index) DO NOTHING
            """,
            (original_id, user_id, stop_int),
        )
        return "accepted"

    if item_type == "rating":
        try:
            rating_int = _validate_rating(item.get("rating"))
        except ValueError:
            return "invalid"
        # 670B gate, now counting THIS batch's already-applied listens.
        listened = count_listened_stops(cur, user_id, original_id)
        required = required_listened_stops(cur, original_id)
        if listened < required:
            # Not enough listened even with this batch — reject so the client
            # drops it (it cannot become valid later from the same payload).
            return "invalid"
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
        return "accepted"

    if item_type == "thumb":
        # D650: internal signal only — personalization / stop quality, NEVER the
        # tour score. Recorded into user_stop_feedback via swipe_preference.
        swipe = item.get("swipe")
        if swipe not in (-1, 1):
            return "invalid"
        stop_index = item.get("stop_index")
        try:
            stop_int = int(stop_index)
        except (TypeError, ValueError):
            return "invalid"
        if stop_int < 0:
            return "invalid"
        try:
            from swipe_preference_service import record_feedback
            record_feedback(
                user_id=user_id,
                tour_id=original_id,
                job_id=item.get("job_id"),
                stop_index=stop_int,
                swipe=swipe,
                class_details=float(item.get("class_details", 0.333)),
                class_historic=float(item.get("class_historic", 0.333)),
                class_social=float(item.get("class_social", 0.333)),
                i_con=float(item.get("i_con", 3.0)),
            )
        except Exception:  # noqa: BLE001 — a thumb must never fail the batch
            return "invalid"
        return "accepted"

    if item_type == "review":
        review = item.get("review")
        if not isinstance(review, str) or not review.strip():
            return "invalid"
        cur.execute(
            """
            INSERT INTO tour_review_sync (tour_id, user_id, review)
            VALUES (%s, %s, %s)
            ON CONFLICT (tour_id, user_id)
            DO UPDATE SET review = EXCLUDED.review,
                          updated_at = CURRENT_TIMESTAMP
            """,
            (original_id, user_id, review),
        )
        return "accepted"

    # Unknown type — reject so the client drops it rather than retrying forever.
    return "invalid"


def process_sync_batch(user_id, items):
    """Process a batch of outbox items idempotently in ONE transaction.

    Applies listens before ratings so an offline listen-then-rate pair is
    accepted together. Returns {"results": [{client_uuid, status}, …]} where
    status ∈ accepted | duplicate | invalid. Items missing a client_uuid get a
    synthetic one in the response so the client can still correlate.
    """
    results = []
    conn = get_connection()
    try:
        cur = conn.cursor()
        _ensure_tour_listens_table(cur)
        _ensure_sync_tables(cur)

        ordered = sorted(
            list(items or []),
            key=lambda it: _sync_order_rank(it.get("type")),
        )

        for item in ordered:
            client_uuid = item.get("client_uuid")
            if not client_uuid:
                results.append({"client_uuid": None, "status": "invalid"})
                continue

            if _already_processed(cur, client_uuid):
                results.append({"client_uuid": client_uuid, "status": "duplicate"})
                continue

            status = _apply_sync_item(cur, item, user_id)
            if status == "accepted":
                _mark_processed(cur, client_uuid, user_id, item.get("type", "?"))
            results.append({"client_uuid": client_uuid, "status": status})

        conn.commit()
        return {"results": results}
    finally:
        conn.close()


# ─── Flask API routes ─────────────────────────────────────────────────────────

def register_rating_routes(app):
    """Register tour-rating endpoints on a Flask app (the orchestrator).

    Endpoints:
        POST /tour/<tour_id>/rating     {user_id, rating}      → record/replace
        GET  /tour/<tour_id>/rating                            → {score, count, label}
        POST /tour/<tour_id>/listened   {user_id, stop_index}  → record (idempotent)
        GET  /tour/<tour_id>/listened?user_id=...              → {listened_count, required, enough}
        POST /sync                      {user_id, items:[…]}   → {results:[{client_uuid,status}]}
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

        # Validate the rating VALUE before the listened gate, so malformed input
        # is a clean 400 regardless of listen history (a 403 "listen more" on a
        # rating of 99 would be misleading).
        try:
            _validate_rating(data["rating"])
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400

        # [LOCAL-670B] Listened-stops gate. A tour rating is refused with 403
        # until the user has finished >= 2 distinct stops (or all stops when the
        # tour has fewer than 2). The per-STOP thumbs are a different endpoint and
        # are unaffected — you can always rate a stop you heard.
        try:
            enough, listen_info = check_listened_enough(user_id, tour_id)
        except Exception as e:  # noqa: BLE001 — gate read must never 500 the request
            return jsonify({"error": str(e)}), 500
        if not enough:
            return jsonify({
                "error": "not_enough_listened",
                "message": (
                    f"Listen to at least {listen_info['required']} stops to rate "
                    f"this tour. You've heard {listen_info['listened_count']} so far."
                ),
                "listened_count": listen_info["listened_count"],
                "required": listen_info["required"],
            }), 403

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

    @app.route('/tour/<tour_id>/listened', methods=['POST'])
    def api_record_listen(tour_id):
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        user_id = data.get("user_id")
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        if "stop_index" not in data:
            return jsonify({"error": "stop_index is required"}), 400

        try:
            result = record_listen(
                user_id=user_id,
                tour_id=tour_id,
                stop_index=data["stop_index"],
            )
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500

        return jsonify({"status": "ok", **result}), 200

    @app.route('/tour/<tour_id>/listened', methods=['GET'])
    def api_listened_status(tour_id):
        user_id = request.args.get("user_id")
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        try:
            result = listened_status(user_id, tour_id)
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500
        return jsonify(result), 200

    @app.route('/sync', methods=['POST'])
    def api_sync():
        """[LOCAL-670C] Accept a batch of offline-recorded items.

        Body: { user_id, items: [ {client_uuid, type, created_at, …}, … ] }.
        Returns 200 with per-item verdicts:
            { "results": [ {client_uuid, status}, … ] }
        status ∈ accepted | duplicate | invalid. The client removes accepted +
        duplicate + invalid items and keeps anything not reported (e.g. after a
        5xx or network error) for a later retry. Idempotent on client_uuid.
        """
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        user_id = data.get("user_id")
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        items = data.get("items")
        if not isinstance(items, list):
            return jsonify({"error": "items must be a list"}), 400
        try:
            result = process_sync_batch(user_id, items)
        except Exception as e:  # noqa: BLE001 — a batch error must not lose items
            return jsonify({"error": str(e)}), 500
        return jsonify(result), 200
