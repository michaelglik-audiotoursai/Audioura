#!/usr/bin/env python3
"""
Tour Reviews Service (LOCAL-672, D649)

"Reviews #4 — indicate the opinions of paid listeners" (Michael, 2026-10-10).
Builds on LOCAL-670's tour_ratings (1..10, 7.5 prior, median after 3, D647).

This module adds, on top of the per-TOUR rating:

  1. VERIFIED ratings. A rating is "verified" when its author has a store-
     verified `purchases` row that unlocked THIS tour. Until the per-tour unlock
     mapping exists (D624, pending Michael's tiers), a purchase of a LEVEL
     product also counts as verified for tours the user generated or downloaded
     while that level was active. The flag is stored on the rating
     (tour_ratings.verified, additive) and set by tour_rating_service at rating
     time; a refunded/revoked purchase un-verifies the rating (recompute helper
     here). On a PAID tour only verified ratings count toward the shown score;
     on a FREE tour all download-gated ratings count (LOCAL-670), verified marked.

  2. TEXT REVIEWS. Optional, <= 500 chars, attached to a rating. review_status =
     pending | approved | rejected. An AUTO-CHECK (profanity / URL / contact
     info) holds a flagged review as `pending` with a reason, else `approved`;
     no human is needed to approve, and the pending queue is visible to LEAD.
     GET /tour/<id>/reviews returns APPROVED reviews only, newest first, VERIFIED
     first, each with its rating, date, "Verified listener" when verified, and
     the curator reply.

  3. CURATOR REPLY. One per review, by the tour's creator, <= 300 chars, through
     the same auto-check.

  4. RANKING. A Bayesian list-ORDER key: (C*7.5 + sum(weighted ratings)) /
     (C + sum(weights)) with C = 3, verified weight 1.0, unverified 0.5, and a
     0.5 age/version weight for ratings older than 12 months or made before the
     tour's current version. The SHOWN score stays D647 (owned by map-delivery /
     tour_rating_service); this is only used to ORDER a "Top rated" list.

  5. PROTECTION. A creator cannot rate or review their own tour; a refunded
     purchase un-verifies its rating; ratings from users who never downloaded the
     tour are ignored.

  6. HELPFUL VOTES. One per (user, review); the count is shown. A user cannot
     vote on their own review.

Translation mapping mirrors tour_ratings/tour_listens: a translation row
(audio_tours.original_tour_id set) shares its SOURCE tour's reviews. Every read
and write resolves the given id to its original first, so reviews key on the
ORIGINAL audio_tours.id.

Design decisions documented in SUBMISSION_LOCAL-672.md.
"""

import os
import re
import sys

# Reuse the shared DB connection helper the other services use (tests/).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests'))
from db_connection import get_connection  # noqa: E402

# Reuse LOCAL-670's translation + download helpers so reviews key on exactly the
# same ORIGINAL id as ratings and honour the same download gate.
import tour_rating_service as rating_svc  # noqa: E402


# ─── Limits ───────────────────────────────────────────────────────────────────

REVIEW_MAX_CHARS = 500          # a short review, per the ticket
REPLY_MAX_CHARS = 300           # a short curator reply

# Bayesian ranking prior (item 4/11). C=3 so one 10 does not top the list.
RANK_PRIOR_COUNT = 3
RANK_PRIOR_SCORE = 7.5
# Weights (item 11). Verified ratings count fully; unverified count half; a
# rating older than 12 months OR made before the tour's current version is
# additionally halved.
WEIGHT_VERIFIED = 1.0
WEIGHT_UNVERIFIED = 0.5
WEIGHT_STALE = 0.5              # multiplied on top for old / pre-version ratings
STALE_AFTER_DAYS = 365         # "older than 12 months"


# ─── Self-healing DDL (identical to migration/sql/021_tour_reviews.sql) ───────
# So the service works whether or not the migration was run, exactly like
# tour_rating_service / tour_listens do.

_VERIFIED_COLUMN_DDL = (
    "ALTER TABLE tour_ratings "
    "ADD COLUMN IF NOT EXISTS verified BOOLEAN NOT NULL DEFAULT FALSE"
)

_TOUR_REVIEWS_DDL = """
    CREATE TABLE IF NOT EXISTS tour_reviews (
        id              SERIAL PRIMARY KEY,
        tour_id         INTEGER NOT NULL,
        user_id         VARCHAR(255) NOT NULL,
        review_text     TEXT NOT NULL CHECK (char_length(review_text) <= 500),
        review_status   VARCHAR(16) NOT NULL DEFAULT 'pending'
                        CHECK (review_status IN ('pending', 'approved', 'rejected')),
        status_reason   TEXT,
        reply_text      TEXT CHECK (reply_text IS NULL OR char_length(reply_text) <= 300),
        reply_status    VARCHAR(16)
                        CHECK (reply_status IS NULL OR reply_status IN ('pending', 'approved', 'rejected')),
        reply_reason    TEXT,
        reply_user_id   VARCHAR(255),
        created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        reply_at        TIMESTAMP,
        CONSTRAINT uq_tour_reviews_tour_user UNIQUE (tour_id, user_id)
    )
"""

_REVIEW_VOTES_DDL = """
    CREATE TABLE IF NOT EXISTS review_helpful_votes (
        id          SERIAL PRIMARY KEY,
        review_id   INTEGER NOT NULL REFERENCES tour_reviews(id) ON DELETE CASCADE,
        user_id     VARCHAR(255) NOT NULL,
        created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_review_helpful_votes_review_user UNIQUE (review_id, user_id)
    )
"""


def _ensure_schema(cur):
    """Create the reviews objects + the verified column if absent. Idempotent;
    safe to call on every write."""
    cur.execute(_VERIFIED_COLUMN_DDL)
    cur.execute(_TOUR_REVIEWS_DDL)
    cur.execute(_REVIEW_VOTES_DDL)


# ─── Moderation auto-check (profanity / URL / contact info) ───────────────────
#
# A deliberately conservative, offline, no-paid-calls filter. It never silently
# rejects — a hit HOLDS the text as `pending` with a reason so LEAD can see it;
# a clean text is `approved` immediately. Michael: "checked before it shows … no
# human needed now, the queue is visible to LEAD."

# A small, intentionally mild profanity set. Matched as whole words,
# case-insensitively. Kept short on purpose — this is a hold-for-review signal,
# not a comprehensive censor; LEAD sees everything held.
_PROFANITY = {
    "fuck", "shit", "bitch", "asshole", "cunt", "bastard", "dick", "piss",
}

# URLs: http(s)://…, www.…, or a bare domain like foo.com/path. Catches the
# common "visit my site" spam without needing a scheme.
_URL_RE = re.compile(
    r"(https?://|www\.)\S+"
    r"|\b[a-z0-9][a-z0-9-]*\.(com|net|org|io|co|info|biz|ru|de|uk|me|app|shop)\b"
    r"(/\S*)?",
    re.IGNORECASE,
)

# Contact info: an email, or a phone-like run of >= 7 digits (allowing spaces,
# dashes, dots, parens and a leading +).
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_RE = re.compile(r"(?:\+?\d[\s().-]*){7,}\d")

_WORD_RE = re.compile(r"[a-zA-Z']+")


def moderate_text(text):
    """Auto-check a review/reply. Returns (status, reason).

    status is 'approved' for clean text, else 'pending' with reason one of
    'profanity' | 'url' | 'contact' (the FIRST that fires, in that order).
    Never returns 'rejected': a hold is human-visible, not a silent drop — a
    human (LEAD) may later reject from the queue, which this service also
    supports via set_review_status, but the AUTO path only approves or holds.
    """
    t = text or ""

    words = {w.lower() for w in _WORD_RE.findall(t)}
    if words & _PROFANITY:
        return "pending", "profanity"

    if _URL_RE.search(t):
        return "pending", "url"

    if _EMAIL_RE.search(t) or _PHONE_RE.search(t):
        return "pending", "contact"

    return "approved", ""


# ─── Creator resolution + paid/free classification ────────────────────────────

def resolve_tour_creator(cur, original_id):
    """Best-effort: the user id that CREATED this (original) tour, or None.

    The ticket says "the tour's creator (audio_tours creator/user id)". The
    schema has no explicit creator column yet, so we resolve in this order:
      1. An optional additive audio_tours.creator_user_id column, if a future
         migration adds one (honoured the moment it exists — forward-compatible).
      2. The EARLIEST tour_requests.secret_id for this tour id (the user who
         first generated/requested it). tour_requests.tour_id is VARCHAR and may
         hold the numeric id, so we match it as text.
    Returns None when neither is available (then the two protections simply do
    not fire — they never block a legitimate rating/review).
    """
    # 1. Optional explicit column.
    try:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'audio_tours' AND column_name = 'creator_user_id'"
        )
        if cur.fetchone() is not None:
            cur.execute(
                "SELECT creator_user_id FROM audio_tours WHERE id = %s",
                (int(original_id),),
            )
            row = cur.fetchone()
            if row and row[0]:
                return str(row[0])
    except Exception:  # noqa: BLE001 — resolution must never 500 a request
        pass

    # 2. Earliest requester of the tour.
    try:
        cur.execute(
            """
            SELECT secret_id FROM tour_requests
            WHERE tour_id = %s AND secret_id IS NOT NULL
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (str(original_id),),
        )
        row = cur.fetchone()
        if row and row[0]:
            return str(row[0])
    except Exception:  # noqa: BLE001
        pass
    return None


def is_paid_tour(cur, original_id):
    """True if this (original) tour is PAID, else False.

    D624 (per-tour unlock mapping) is pending Michael's tiers, so there is no
    per-tour price flag in the schema today. We therefore resolve in this order:
      1. An optional additive audio_tours.is_paid boolean, if a future migration
         adds one (honoured immediately — forward-compatible).
      2. Otherwise FALSE — every tour is treated as FREE for counting, which is
         exactly LOCAL-670's behaviour and never wrongly restricts a score while
         the paid mapping is absent.
    The moment an is_paid column (or value) exists, paid tours switch to the
    verified-only counting rule with no further code change.
    """
    try:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'audio_tours' AND column_name = 'is_paid'"
        )
        if cur.fetchone() is not None:
            cur.execute(
                "SELECT is_paid FROM audio_tours WHERE id = %s",
                (int(original_id),),
            )
            row = cur.fetchone()
            return bool(row and row[0])
    except Exception:  # noqa: BLE001
        pass
    return False


# ─── Verified logic ───────────────────────────────────────────────────────────

def _has_table(cur, table_name):
    try:
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
            (table_name,),
        )
        return cur.fetchone() is not None
    except Exception:  # noqa: BLE001
        return False


# A purchase whose raw_status marks it refunded/revoked no longer verifies a
# rating. Matched case-insensitively as a substring so 'REFUNDED', 'revoked',
# 'chargeback: refund' all count.
_REFUND_MARKERS = ("refund", "revoke", "chargeback")


def _is_refunded_status(raw_status):
    if not raw_status:
        return False
    s = str(raw_status).lower()
    return any(m in s for m in _REFUND_MARKERS)


def compute_verified(cur, user_id, original_id):
    """Decide whether a rating by user_id of tour original_id is VERIFIED.

    Rule (D649 + D624 fallback):
      * A purchases row for this user that unlocked THIS tour (product encodes
        the tour id, e.g. 'tour_<id>') and is NOT refunded/revoked → verified.
      * Else, until the per-tour mapping exists: ANY non-refunded LEVEL purchase
        by this user (product starting 'l', e.g. 'l3_pack_10') combined with a
        download/generation record for this tour → verified (a paying user who
        actually unlocked the tour).
      * No purchases table, or no qualifying purchase → NOT verified.

    This is intentionally forgiving in the fallback direction only: it requires
    BOTH a real purchase AND that the user actually has the tour. It never marks
    a non-purchasing user verified.
    """
    if not _has_table(cur, "purchases"):
        return False

    # 1. Direct per-tour purchase (future mapping): product references the tour.
    tour_products = (f"tour_{original_id}", f"tour-{original_id}", str(original_id))
    try:
        cur.execute(
            "SELECT product, raw_status FROM purchases WHERE user_id = %s",
            (user_id,),
        )
        rows = cur.fetchall()
    except Exception:  # noqa: BLE001
        return False

    has_level_purchase = False
    for product, raw_status in rows:
        if _is_refunded_status(raw_status):
            continue
        p = (product or "").lower()
        # Direct unlock of this tour.
        if p in [tp.lower() for tp in tour_products] or p.endswith(f"_{original_id}"):
            return True
        # A level product (l1/l2/l3/l4...). Keep for the fallback below.
        if p.startswith("l") and len(p) >= 2 and p[1].isdigit():
            has_level_purchase = True

    # 2. D624 fallback: a level purchase + the user actually has this tour.
    if has_level_purchase:
        try:
            if rating_svc.has_downloaded(cur, user_id, original_id, original_id):
                return True
        except Exception:  # noqa: BLE001
            return False
    return False


def set_rating_verified(cur, user_id, original_id, verified):
    """Write the verified flag onto an existing rating row (no-op if none)."""
    cur.execute(
        "UPDATE tour_ratings SET verified = %s WHERE tour_id = %s AND user_id = %s",
        (bool(verified), int(original_id), user_id),
    )


def recompute_verified_for_user(user_id):
    """Recompute the verified flag on ALL of a user's ratings.

    Call after a purchase changes (new purchase, or a refund/revoke). A refund
    that leaves no qualifying purchase flips the affected ratings back to
    unverified — the ticket's "a refunded purchase un-verifies its rating".
    Returns the number of rating rows updated.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        _ensure_schema(cur)
        cur.execute(
            "SELECT DISTINCT tour_id FROM tour_ratings WHERE user_id = %s",
            (user_id,),
        )
        tour_ids = [int(r[0]) for r in cur.fetchall()]
        updated = 0
        for tid in tour_ids:
            verified = compute_verified(cur, user_id, tid)
            set_rating_verified(cur, user_id, tid, verified)
            updated += 1
        conn.commit()
        return updated
    finally:
        conn.close()


# ─── Review CRUD ────────────────────────────────────────────────────────────

def _validate_review_text(text):
    if text is None:
        raise ValueError("review_text is required")
    t = str(text).strip()
    if not t:
        raise ValueError("review_text must not be empty")
    if len(t) > REVIEW_MAX_CHARS:
        raise ValueError(f"review_text must be <= {REVIEW_MAX_CHARS} characters")
    return t


def _validate_reply_text(text):
    if text is None:
        raise ValueError("reply_text is required")
    t = str(text).strip()
    if not t:
        raise ValueError("reply_text must not be empty")
    if len(t) > REPLY_MAX_CHARS:
        raise ValueError(f"reply_text must be <= {REPLY_MAX_CHARS} characters")
    return t


def submit_review(user_id, tour_id, review_text):
    """Create or replace a user's text review of a tour.

    Requires an existing rating by this user (a review is attached to a rating,
    per the ticket). A creator cannot review their own tour. Runs the auto-check
    and stores the resulting status + reason. A re-review UPSERTs (replaces text,
    re-runs the check, resets any reply). Returns the stored review dict.

    Raises ValueError on bad input / missing rating / creator-self-review.
    """
    text = _validate_review_text(review_text)

    conn = get_connection()
    try:
        cur = conn.cursor()
        _ensure_schema(cur)
        original_id = rating_svc.resolve_original_id(cur, tour_id)

        # Protection: a creator cannot review their own tour.
        creator = resolve_tour_creator(cur, original_id)
        if creator is not None and str(creator) == str(user_id):
            raise ValueError("a tour's creator cannot review their own tour")

        # A review must be attached to a rating by this user (ticket §2).
        cur.execute(
            "SELECT 1 FROM tour_ratings WHERE tour_id = %s AND user_id = %s",
            (int(original_id), user_id),
        )
        if cur.fetchone() is None:
            raise ValueError("rate the tour before adding a review")

        status, reason = moderate_text(text)

        cur.execute(
            """
            INSERT INTO tour_reviews (tour_id, user_id, review_text, review_status, status_reason)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (tour_id, user_id)
            DO UPDATE SET review_text = EXCLUDED.review_text,
                          review_status = EXCLUDED.review_status,
                          status_reason = EXCLUDED.status_reason,
                          updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (int(original_id), user_id, text, status, reason),
        )
        review_id = cur.fetchone()[0]
        conn.commit()
        return {
            "id": review_id,
            "tour_id": original_id,
            "user_id": user_id,
            "review_text": text,
            "review_status": status,
            "status_reason": reason,
        }
    finally:
        conn.close()


def reply_to_review(user_id, review_id, reply_text):
    """Add the ONE curator reply to a review.

    Only the tour's creator may reply, and only once (a second reply is
    refused). The reply goes through the same auto-check. Returns the stored
    reply dict.

    Raises ValueError on bad input / not-creator / already-replied / no review.
    """
    text = _validate_reply_text(reply_text)

    conn = get_connection()
    try:
        cur = conn.cursor()
        _ensure_schema(cur)

        cur.execute(
            "SELECT tour_id, reply_text FROM tour_reviews WHERE id = %s",
            (int(review_id),),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError("review not found")
        tour_id, existing_reply = row

        # Only the tour's creator may reply.
        creator = resolve_tour_creator(cur, tour_id)
        if creator is None or str(creator) != str(user_id):
            raise ValueError("only the tour's creator may reply to a review")

        # One reply per review.
        if existing_reply is not None:
            raise ValueError("a review already has a curator reply")

        status, reason = moderate_text(text)
        cur.execute(
            """
            UPDATE tour_reviews
            SET reply_text = %s, reply_status = %s, reply_reason = %s,
                reply_user_id = %s, reply_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (text, status, reason, user_id, int(review_id)),
        )
        conn.commit()
        return {
            "id": int(review_id),
            "reply_text": text,
            "reply_status": status,
            "reply_reason": reason,
            "reply_user_id": user_id,
        }
    finally:
        conn.close()


def set_review_status(review_id, status):
    """LEAD moderation action: approve or reject a held review. (The queue is
    visible to LEAD; this is how a human resolves a `pending` item.)"""
    if status not in ("approved", "rejected", "pending"):
        raise ValueError("status must be approved | rejected | pending")
    conn = get_connection()
    try:
        cur = conn.cursor()
        _ensure_schema(cur)
        cur.execute(
            "UPDATE tour_reviews SET review_status = %s, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = %s",
            (status, int(review_id)),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ─── Helpful votes ────────────────────────────────────────────────────────────

def vote_helpful(user_id, review_id):
    """Record one "helpful" vote by user_id on a review.

    A user cannot vote on their OWN review. Re-voting is idempotent. Returns the
    new helpful count for the review.

    Raises ValueError on self-vote / no review.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        _ensure_schema(cur)

        cur.execute("SELECT user_id FROM tour_reviews WHERE id = %s", (int(review_id),))
        row = cur.fetchone()
        if row is None:
            raise ValueError("review not found")
        author = row[0]
        if str(author) == str(user_id):
            raise ValueError("you cannot vote on your own review")

        cur.execute(
            """
            INSERT INTO review_helpful_votes (review_id, user_id)
            VALUES (%s, %s)
            ON CONFLICT (review_id, user_id) DO NOTHING
            """,
            (int(review_id), user_id),
        )
        conn.commit()
        return helpful_count(cur, review_id)
    finally:
        conn.close()


def helpful_count(cur, review_id):
    """How many helpful votes a review has."""
    cur.execute(
        "SELECT COUNT(*) FROM review_helpful_votes WHERE review_id = %s",
        (int(review_id),),
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


# ─── Read: approved reviews for a tour ────────────────────────────────────────

# Review sort orders (item 10): Top (helpful, then verified, then recency),
# Most recent, Critical (<= 6 first). The band filter (item 10) selects reviews
# whose rating falls in one of the five distribution bands.
_SORT_TOP = "top"
_SORT_RECENT = "recent"
_SORT_CRITICAL = "critical"

# Five bands (item 8): 9-10, 7-8, 5-6, 3-4, 1-2. Keyed by their low bound.
_BANDS = [(9, 10), (7, 8), (5, 6), (3, 4), (1, 2)]


def _band_of(rating):
    for lo, hi in _BANDS:
        if lo <= rating <= hi:
            return f"{lo}-{hi}"
    return None


def get_reviews(tour_id, sort="top", band=None):
    """APPROVED reviews for a tour, each with its rating, date, verified flag,
    helpful count and the (approved) curator reply.

    sort: 'top' (helpful desc, then verified first, then newest),
          'recent' (newest first),
          'critical' (rating <= 6 first, then newest).
    band: optional '9-10' | '7-8' | '5-6' | '3-4' | '1-2' — only reviews whose
          rating is in that band (item 10's tap-a-bar filter).

    A reply is only included when its own moderation status is 'approved'.
    """
    sort = (sort or _SORT_TOP).lower()
    conn = get_connection()
    try:
        cur = conn.cursor()
        _ensure_schema(cur)
        original_id = rating_svc.resolve_original_id(cur, tour_id)

        # Join the author's rating (value + verified) and the helpful count. Only
        # approved reviews are returned (ticket §2).
        cur.execute(
            """
            SELECT rv.id, rv.user_id, rv.review_text, rv.created_at,
                   tr.rating, COALESCE(tr.verified, FALSE) AS verified,
                   rv.reply_text, rv.reply_status, rv.reply_at,
                   (SELECT COUNT(*) FROM review_helpful_votes v WHERE v.review_id = rv.id) AS helpful
            FROM tour_reviews rv
            JOIN tour_ratings tr
              ON tr.tour_id = rv.tour_id AND tr.user_id = rv.user_id
            WHERE rv.tour_id = %s AND rv.review_status = 'approved'
            """,
            (int(original_id),),
        )
        rows = cur.fetchall()

        reviews = []
        for (rid, uid, text, created_at, rating, verified,
             reply_text, reply_status, reply_at, helpful) in rows:
            rating = int(rating)
            if band is not None and _band_of(rating) != band:
                continue
            include_reply = reply_text is not None and reply_status == "approved"
            reviews.append({
                "id": rid,
                "rating": rating,
                "verified": bool(verified),
                "verified_listener": bool(verified),
                "review_text": text,
                "date": _iso(created_at),
                "helpful_count": int(helpful or 0),
                "band": _band_of(rating),
                "reply": ({
                    "text": reply_text,
                    "date": _iso(reply_at),
                } if include_reply else None),
            })

        reviews = _sort_reviews(reviews, sort)
        return reviews
    finally:
        conn.close()


def _sort_reviews(reviews, sort):
    """Apply the chosen order (item 10). Returns a new sorted list."""
    if sort == _SORT_RECENT:
        return sorted(reviews, key=lambda r: (r["date"] or ""), reverse=True)
    if sort == _SORT_CRITICAL:
        # Critical first (<= 6), then by recency within each group.
        return sorted(
            reviews,
            key=lambda r: (0 if r["rating"] <= 6 else 1, _neg_date(r["date"])),
        )
    # Default 'top': helpful desc, verified first, then recency.
    return sorted(
        reviews,
        key=lambda r: (-r["helpful_count"], 0 if r["verified"] else 1,
                       _neg_date(r["date"])),
    )


def _neg_date(iso):
    """A sort key that puts the NEWEST date first within a tuple sort (where the
    rest of the tuple sorts ascending). Uses string compare on the ISO date."""
    return "" if not iso else "".join(chr(255 - ord(c)) if ord(c) < 255 else c for c in iso)


def _iso(stamp):
    if stamp is None:
        return None
    try:
        return stamp.date().isoformat()
    except AttributeError:
        return str(stamp)[:10]


# ─── Moderation queue (visible to LEAD) ───────────────────────────────────────

def get_pending_reviews(limit=100):
    """All reviews (and replies) still pending the human queue, oldest first."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        _ensure_schema(cur)
        cur.execute(
            """
            SELECT id, tour_id, user_id, review_text, status_reason, created_at,
                   reply_text, reply_status, reply_reason
            FROM tour_reviews
            WHERE review_status = 'pending' OR reply_status = 'pending'
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (int(limit),),
        )
        out = []
        for (rid, tid, uid, text, reason, created_at,
             reply_text, reply_status, reply_reason) in cur.fetchall():
            out.append({
                "id": rid,
                "tour_id": tid,
                "user_id": uid,
                "review_text": text,
                "status_reason": reason,
                "date": _iso(created_at),
                "reply_pending": reply_status == "pending",
                "reply_text": reply_text,
                "reply_reason": reply_reason,
            })
        return out
    finally:
        conn.close()


# ─── Rating distribution (item 8) ─────────────────────────────────────────────

def get_distribution(tour_id):
    """The share of ratings in the five bands (item 8), as counts + percentages.

    Source set (ticket §8): verified ratings on a PAID tour; all COUNTED ratings
    on a FREE tour (LOCAL-670 counts every download-gated rating on a free tour).
    Returns {total, bands: [{band, count, percent}, ...]} with bands ordered
    9-10, 7-8, 5-6, 3-4, 1-2.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        _ensure_schema(cur)
        original_id = rating_svc.resolve_original_id(cur, tour_id)
        paid = is_paid_tour(cur, original_id)

        if paid:
            cur.execute(
                "SELECT rating FROM tour_ratings WHERE tour_id = %s AND verified = TRUE",
                (int(original_id),),
            )
        else:
            cur.execute(
                "SELECT rating FROM tour_ratings WHERE tour_id = %s",
                (int(original_id),),
            )
        ratings = [int(r[0]) for r in cur.fetchall()]
        return _distribution_from_ratings(ratings)
    finally:
        conn.close()


def _distribution_from_ratings(ratings):
    total = len(ratings)
    counts = {f"{lo}-{hi}": 0 for lo, hi in _BANDS}
    for r in ratings:
        b = _band_of(r)
        if b is not None:
            counts[b] += 1
    bands = []
    for lo, hi in _BANDS:
        key = f"{lo}-{hi}"
        c = counts[key]
        percent = round((c / total) * 100) if total else 0
        bands.append({"band": key, "count": c, "percent": percent})
    return {"total": total, "bands": bands}


# ─── Bayesian ranking (items 4 & 11) — list ORDER key only ────────────────────

def rank_score(rated_rows, now=None, current_version_date=None):
    """Bayesian list-ORDER key for a tour (items 4 & 11). NOT the shown score.

    rated_rows: list of dicts/tuples, each describing one rating:
        {"rating": int, "verified": bool, "created_at": datetime|None}
    (a tuple (rating, verified, created_at) is also accepted).

    score = (C*prior + sum(w_i * rating_i)) / (C + sum(w_i)), C = 3, prior = 7.5.
    w_i = (1.0 if verified else 0.5) * (0.5 if the rating is "stale" else 1.0),
    where stale = created_at older than 12 months, OR created_at before the
    tour's current version date (a rating of an older version of the tour).

    With no ratings this returns the prior (7.5), so a brand-new tour sorts in
    the middle, not the top or bottom.
    """
    import datetime as _dt
    if now is None:
        now = _dt.datetime.now()

    num = RANK_PRIOR_COUNT * RANK_PRIOR_SCORE
    den = float(RANK_PRIOR_COUNT)

    for row in (rated_rows or []):
        if isinstance(row, dict):
            rating = row.get("rating")
            verified = bool(row.get("verified"))
            created_at = row.get("created_at")
        else:
            rating, verified, created_at = (list(row) + [None, None])[:3]
            verified = bool(verified)
        if rating is None:
            continue
        rating = int(rating)

        w = WEIGHT_VERIFIED if verified else WEIGHT_UNVERIFIED
        if _is_stale(created_at, now, current_version_date):
            w *= WEIGHT_STALE

        num += w * rating
        den += w

    if den <= 0:
        return RANK_PRIOR_SCORE
    return num / den


def _is_stale(created_at, now, current_version_date):
    """A rating is stale if it is older than 12 months OR predates the tour's
    current version. Missing created_at → not stale (we cannot prove it is)."""
    if created_at is None:
        return False
    try:
        age_days = (now - created_at).days
    except Exception:  # noqa: BLE001 — mixed date/datetime etc.
        return False
    if age_days > STALE_AFTER_DAYS:
        return True
    if current_version_date is not None:
        try:
            if created_at < current_version_date:
                return True
        except Exception:  # noqa: BLE001
            return False
    return False


# ─── Flask API routes ─────────────────────────────────────────────────────────

def register_review_routes(app):
    """Register review/reply/vote/distribution endpoints on a Flask app.

    Endpoints:
        GET  /tour/<tour_id>/reviews?sort=&band=     → approved reviews
        POST /tour/<tour_id>/review  {user_id, review_text}        → submit/replace
        GET  /tour/<tour_id>/distribution            → rating distribution bands
        POST /review/<review_id>/reply  {user_id, reply_text}      → curator reply
        POST /review/<review_id>/helpful {user_id}                 → helpful vote
        GET  /reviews/pending                        → LEAD moderation queue
        POST /review/<review_id>/moderate {status}   → LEAD approve/reject
    """
    from flask import request, jsonify

    @app.route('/tour/<tour_id>/reviews', methods=['GET'])
    def api_get_reviews(tour_id):
        sort = request.args.get('sort', 'top')
        band = request.args.get('band') or None
        try:
            reviews = get_reviews(tour_id, sort=sort, band=band)
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500
        return jsonify({"reviews": reviews, "count": len(reviews)}), 200

    @app.route('/tour/<tour_id>/review', methods=['POST'])
    def api_submit_review(tour_id):
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        user_id = data.get("user_id")
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        try:
            result = submit_review(user_id, tour_id, data.get("review_text"))
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500
        return jsonify({"status": "ok", **result}), 200

    @app.route('/tour/<tour_id>/distribution', methods=['GET'])
    def api_get_distribution(tour_id):
        try:
            result = get_distribution(tour_id)
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500
        return jsonify(result), 200

    @app.route('/review/<int:review_id>/reply', methods=['POST'])
    def api_reply_to_review(review_id):
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        user_id = data.get("user_id")
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        try:
            result = reply_to_review(user_id, review_id, data.get("reply_text"))
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500
        return jsonify({"status": "ok", **result}), 200

    @app.route('/review/<int:review_id>/helpful', methods=['POST'])
    def api_vote_helpful(review_id):
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        user_id = data.get("user_id")
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        try:
            count = vote_helpful(user_id, review_id)
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500
        return jsonify({"status": "ok", "helpful_count": count}), 200

    @app.route('/reviews/pending', methods=['GET'])
    def api_pending_reviews():
        try:
            limit = int(request.args.get('limit', 100))
        except (TypeError, ValueError):
            limit = 100
        try:
            result = get_pending_reviews(limit=limit)
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500
        return jsonify({"reviews": result, "count": len(result)}), 200

    @app.route('/review/<int:review_id>/moderate', methods=['POST'])
    def api_moderate_review(review_id):
        data = request.get_json(silent=True) or {}
        status = data.get("status")
        try:
            updated = set_review_status(review_id, status)
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:  # noqa: BLE001
            return jsonify({"error": str(e)}), 500
        return jsonify({"status": "ok", "updated": updated}), 200
