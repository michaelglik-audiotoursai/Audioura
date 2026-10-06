"""
l2_seats.py — LOCAL-596 L2 seat lifecycle core (shared, framework-free).
========================================================================

Design of record: SUBSCRIPTION_LEVELS.md — "L2 seats and queue" (D613).

This is the SINGLE implementation of the L2 seat rules. It is deliberately
framework-free (no Flask, no boto3) so three callers share one source of truth:

  * subscription_levels.ensure_device  (install auto-grant, called by the
    user-api / orchestrator install path),
  * the user-api blueprint (queue join/leave, claim, /entitlements/me),
  * l2_seat_job.py (the hourly evict / expire / offer job).

NO TIER CONSTANTS. Every number is read at runtime:
  * seat cap (100) and inactivity days (7)  → plans.l2 (migration 012).
  * auto-grant threshold (50) and offer expiry hours (72) → l2_settings
    (migration 015).

A device "holds a seat" iff device_entitlement.level = 'l2'. Seats in use are
COUNTED, never stored, so there is no counter to drift.

Concurrency: install auto-grant and the job both take a transaction-scoped
Postgres advisory lock on a fixed key (_SEAT_LOCK_KEY) so seat decisions
serialize. Two installs at 49 seats can therefore never both pass.

Every function here takes a live psycopg2 cursor and runs inside the caller's
transaction — the caller owns commit/rollback. This lets the API and the job
compose seat operations atomically with their own writes.
"""

import os
import uuid
import logging

logger = logging.getLogger(__name__)

# Fixed advisory-lock key for all seat-granting decisions. Any 64-bit int is
# fine; it just has to be the SAME everywhere so grants serialize. Not a tier
# constant — it is an internal lock id, not a plan number.
_SEAT_LOCK_KEY = 596_000_001


# ───────────────────────────────────────────────────────────────────────────
# Settings + plan access (all numbers come from the DB)
# ───────────────────────────────────────────────────────────────────────────
def get_settings(cur):
    """Read the singleton l2_settings row → dict. FAIL-CLOSED: if the row is
    missing (migration 015 not applied), raise — callers must not silently fall
    back to a hardcoded number."""
    cur.execute("""
        SELECT auto_grant_threshold, offer_expiry_hours, max_offer_misses
        FROM l2_settings WHERE id = TRUE
    """)
    row = cur.fetchone()
    if not row:
        raise RuntimeError("l2_settings row missing — run migration 015")
    return {
        'auto_grant_threshold': row[0],
        'offer_expiry_hours': row[1],
        'max_offer_misses': row[2],
    }


def get_seat_cap(cur):
    """L2 seat cap from plans.l2.seat_cap (design: 100). None → treated as no
    cap, but the design always sets it; a missing row is a misconfiguration."""
    cur.execute("SELECT seat_cap FROM plans WHERE plan_id = 'l2'")
    row = cur.fetchone()
    return row[0] if row else None


def get_inactivity_days(cur):
    """L2 inactivity window from plans.l2.inactivity_days (design: 7)."""
    cur.execute("SELECT inactivity_days FROM plans WHERE plan_id = 'l2'")
    row = cur.fetchone()
    return row[0] if row else None


# ───────────────────────────────────────────────────────────────────────────
# Seat counting + queue inspection
# ───────────────────────────────────────────────────────────────────────────
def seats_in_use(cur):
    """Current L2 seat count = devices whose level is 'l2'. This counts referral
    seats automatically, because a referral grant sets level='l2' like any other
    seat (design: referral seats count against the 100 cap)."""
    cur.execute("SELECT COUNT(*) FROM device_entitlement WHERE level = 'l2'")
    return cur.fetchone()[0]


def seats_free(cur):
    """Seats available under the cap right now (never negative)."""
    cap = get_seat_cap(cur)
    if cap is None:
        return None  # no cap configured
    return max(0, cap - seats_in_use(cur))


def has_waiting_queue(cur):
    """True if any device is currently waiting in the FIFO queue."""
    cur.execute("SELECT 1 FROM l2_queue WHERE status = 'waiting' LIMIT 1")
    return cur.fetchone() is not None


def queue_position(cur, user_id):
    """1-based FIFO position of a waiting device, or None if it is not waiting.
    Position counts only 'waiting' rows ordered by joined_at (offered devices
    have left the waiting line)."""
    cur.execute("SELECT status, joined_at FROM l2_queue WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    if not row or row[0] != 'waiting':
        return None
    joined_at = row[1]
    cur.execute("""
        SELECT COUNT(*) FROM l2_queue
        WHERE status = 'waiting' AND joined_at <= %s
    """, (joined_at,))
    return cur.fetchone()[0]


def _acquire_seat_lock(cur):
    """Take the transaction-scoped advisory lock that serializes seat grants.
    Released automatically at COMMIT/ROLLBACK — the caller must be in a
    transaction (psycopg2 is, by default)."""
    cur.execute("SELECT pg_advisory_xact_lock(%s)", (_SEAT_LOCK_KEY,))


# ───────────────────────────────────────────────────────────────────────────
# Install auto-grant
# ───────────────────────────────────────────────────────────────────────────
def grant_on_install(cur, user_id):
    """Decide and apply the install level for a NEW device, atomically.

    Rule (design): auto-grant L2 only if seats in use < auto_grant_threshold
    (50) AND the queue has no waiting entry. Otherwise grant L1.

    Concurrency: holds the seat advisory lock for the count-and-insert so two
    parallel installs at 49 seats cannot both pass. Idempotent on user_id — a
    device that already has a row keeps its existing level (we never downgrade
    an existing device on a re-install call).

    Returns the resulting level string ('l2' or 'l1'). The caller owns the
    transaction and must COMMIT.
    """
    # If the device already exists, do not change it (ON CONFLICT DO NOTHING
    # semantics): return its current level.
    cur.execute("SELECT level FROM device_entitlement WHERE user_id = %s", (user_id,))
    existing = cur.fetchone()
    if existing:
        return existing[0]

    _acquire_seat_lock(cur)

    # Re-check inside the lock (another install may have just taken the row).
    cur.execute("SELECT level FROM device_entitlement WHERE user_id = %s", (user_id,))
    existing = cur.fetchone()
    if existing:
        return existing[0]

    settings = get_settings(cur)
    threshold = settings['auto_grant_threshold']
    in_use = seats_in_use(cur)
    waiting = has_waiting_queue(cur)

    level = 'l2' if (in_use < threshold and not waiting) else 'l1'

    cur.execute("""
        INSERT INTO device_entitlement (user_id, level, last_activity_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (user_id) DO NOTHING
    """, (user_id, level))

    # If the row was created by a racing transaction between our check and
    # insert (shouldn't happen under the lock, but belt-and-braces), read back
    # the authoritative level.
    cur.execute("SELECT level FROM device_entitlement WHERE user_id = %s", (user_id,))
    return cur.fetchone()[0]


# ───────────────────────────────────────────────────────────────────────────
# Queue join / leave  (API surface)
# ───────────────────────────────────────────────────────────────────────────
def join_queue(cur, user_id):
    """Add a device to the FIFO queue (idempotent). Only L1 devices may join —
    the caller is expected to have checked the level, but we also refuse here if
    the device already holds an L2 seat.

    Returns a dict: {'joined': bool, 'status': str, 'position': int|None,
                     'reason': str|None}.
    Re-joining while already 'waiting' or 'offered' is a no-op that reports the
    current position. A terminal row (claimed/expired/left) is reset to waiting
    with a fresh joined_at (back of the line).
    """
    cur.execute("SELECT level FROM device_entitlement WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    level = row[0] if row else 'l1'
    if level == 'l2':
        return {'joined': False, 'status': None, 'position': None,
                'reason': 'already_l2'}

    cur.execute("SELECT status FROM l2_queue WHERE user_id = %s", (user_id,))
    existing = cur.fetchone()
    if existing and existing[0] in ('waiting', 'offered'):
        # Already in line (or holding an offer) — idempotent no-op.
        return {'joined': True, 'status': existing[0],
                'position': queue_position(cur, user_id), 'reason': None}

    # New row, or re-join after a terminal state → fresh waiting row at the tail.
    cur.execute("""
        INSERT INTO l2_queue (user_id, joined_at, status, offer_misses)
        VALUES (%s, NOW(), 'waiting', 0)
        ON CONFLICT (user_id) DO UPDATE SET
            status = 'waiting', joined_at = NOW(), offer_misses = 0,
            updated_at = NOW()
    """, (user_id,))
    return {'joined': True, 'status': 'waiting',
            'position': queue_position(cur, user_id), 'reason': None}


def leave_queue(cur, user_id):
    """Mark a device's queue row 'left' (idempotent). Any live offer it holds is
    expired too, so the seat it was offered is freed for the next waiter on the
    next job run. Returns {'left': bool}."""
    cur.execute("""
        UPDATE l2_queue SET status = 'left', updated_at = NOW()
        WHERE user_id = %s AND status IN ('waiting', 'offered')
    """, (user_id,))
    left = cur.rowcount > 0
    cur.execute("""
        UPDATE l2_offers SET status = 'expired'
        WHERE user_id = %s AND status = 'offered'
    """, (user_id,))
    return {'left': left}


# ───────────────────────────────────────────────────────────────────────────
# Pending-offer inspection + claim  (API surface)
# ───────────────────────────────────────────────────────────────────────────
def pending_offer(cur, user_id, now_sql="NOW()"):
    """Return the device's live (offered, unexpired) offer as
    {'code', 'expires_at'} or None. 'Live' = status 'offered' AND expires_at in
    the future. The latest such offer wins."""
    cur.execute(f"""
        SELECT code, expires_at FROM l2_offers
        WHERE user_id = %s AND status = 'offered' AND expires_at > {now_sql}
        ORDER BY offered_at DESC LIMIT 1
    """, (user_id,))
    row = cur.fetchone()
    if not row:
        return None
    return {'code': row[0], 'expires_at': row[1]}


# Structured refusal codes for claim (LOCAL-580 contract).
CLAIM_OK = 'ok'
CLAIM_BAD_CODE = 'claim_invalid_code'
CLAIM_EXPIRED = 'claim_expired'
CLAIM_WRONG_DEVICE = 'claim_wrong_device'
CLAIM_SEATS_FULL = 'claim_seats_full'


def claim_seat(cur, user_id, code):
    """Attempt to claim an L2 seat with an offer code, atomically.

    Validates, in order, that the code: exists; belongs to THIS device; is still
    'offered' (not already claimed/expired); is unexpired; and that a seat is
    free under the 100 cap. On success promotes the device to L2, marks the
    offer 'claimed' and the queue row 'claimed'.

    Holds the seat advisory lock across the free-seat check and the grant so a
    claim cannot overshoot the cap against a racing install/claim.

    Returns {'ok': bool, 'code': <CLAIM_* enum>, 'message': str}.
    The caller owns the transaction and must COMMIT on ok.
    """
    if not code or not str(code).strip():
        return {'ok': False, 'code': CLAIM_BAD_CODE,
                'message': 'No claim code was provided.'}

    cur.execute("""
        SELECT user_id, status, expires_at FROM l2_offers WHERE code = %s
    """, (code,))
    row = cur.fetchone()
    if not row:
        return {'ok': False, 'code': CLAIM_BAD_CODE,
                'message': 'That claim code is not valid.'}

    offer_user, offer_status, expires_at = row

    # Belongs to this device?
    if offer_user != user_id:
        return {'ok': False, 'code': CLAIM_WRONG_DEVICE,
                'message': 'That claim code belongs to a different device.'}

    # Still offerable? (not already claimed, not already marked expired)
    if offer_status != 'offered':
        return {'ok': False, 'code': CLAIM_EXPIRED,
                'message': 'That claim offer is no longer available.'}

    # Unexpired? Compare in the DB to avoid clock skew.
    cur.execute("SELECT %s < NOW()", (expires_at,))
    if cur.fetchone()[0]:
        # Lazily mark it expired so inspection is consistent.
        cur.execute("UPDATE l2_offers SET status = 'expired' WHERE code = %s", (code,))
        return {'ok': False, 'code': CLAIM_EXPIRED,
                'message': 'That claim offer has expired.'}

    # Seat available under the cap? Serialize with the lock.
    _acquire_seat_lock(cur)
    cap = get_seat_cap(cur)
    if cap is not None and seats_in_use(cur) >= cap:
        return {'ok': False, 'code': CLAIM_SEATS_FULL,
                'message': 'All free seats are taken right now. You keep your place in line.'}

    # Grant the seat: promote to L2, mark the offer + queue row claimed.
    cur.execute("""
        INSERT INTO device_entitlement (user_id, level, last_activity_at)
        VALUES (%s, 'l2', NOW())
        ON CONFLICT (user_id) DO UPDATE SET level = 'l2', updated_at = NOW()
    """, (user_id,))
    cur.execute("""
        UPDATE l2_offers SET status = 'claimed', claimed_at = NOW() WHERE code = %s
    """, (code,))
    cur.execute("""
        UPDATE l2_queue SET status = 'claimed', updated_at = NOW() WHERE user_id = %s
    """, (user_id,))
    return {'ok': True, 'code': CLAIM_OK, 'message': 'Seat claimed. Welcome to the free level.'}


# ───────────────────────────────────────────────────────────────────────────
# Job primitives: evict idle, expire offers, offer free seats
# ───────────────────────────────────────────────────────────────────────────
def new_offer_code():
    """A short, unique, URL-safe offer code."""
    return 'L2OF-' + uuid.uuid4().hex[:12].upper()


def evict_idle(cur):
    """Drop L2 devices idle >= inactivity_days (plans.l2) to L1 and free their
    seats. Idle = last_activity_at older than the window (any app-open / listen /
    download / article updates last_activity_at via record_activity, resetting
    the clock). Boundary is INCLUSIVE at exactly N days.

    Returns the list of evicted user_ids. Idempotent: a device already at L1 is
    not matched.
    """
    days = get_inactivity_days(cur)
    if not days or days <= 0:
        return []  # no inactivity window configured → never evict
    cur.execute("""
        UPDATE device_entitlement
        SET level = 'l1', pack_started_at = NULL, anniversary_at = NULL,
            fresh_used = 0, edits_used = 0, ops_used = 0, updated_at = NOW()
        WHERE level = 'l2'
          AND last_activity_at IS NOT NULL
          AND last_activity_at <= NOW() - (%s || ' days')::interval
        RETURNING user_id
    """, (days,))
    return [r[0] for r in cur.fetchall()]


def expire_offers(cur):
    """Expire offers past their 72 h window. An expired offer:
      * is marked 'expired',
      * returns its device to the queue tail (status 'waiting', fresh joined_at)
        with offer_misses incremented — UNLESS it has now missed
        max_offer_misses offers, in which case the queue row becomes 'expired'
        (the device drops out and must re-join).
    Idempotent: only 'offered' rows past expires_at are touched.

    Returns a dict {'expired': n, 'requeued': [ids], 'dropped': [ids]}.
    """
    settings = get_settings(cur)
    max_misses = settings['max_offer_misses']

    cur.execute("""
        SELECT user_id, code FROM l2_offers
        WHERE status = 'offered' AND expires_at <= NOW()
    """)
    stale = cur.fetchall()
    requeued, dropped = [], []
    for user_id, code in stale:
        cur.execute("UPDATE l2_offers SET status = 'expired' WHERE code = %s", (code,))
        # Bump the miss counter on the queue row.
        cur.execute("""
            UPDATE l2_queue SET offer_misses = offer_misses + 1, updated_at = NOW()
            WHERE user_id = %s AND status = 'offered'
            RETURNING offer_misses
        """, (user_id,))
        row = cur.fetchone()
        if row is None:
            # Queue row not in 'offered' (e.g. the device left) — nothing to requeue.
            continue
        misses = row[0]
        if misses >= max_misses:
            cur.execute("""
                UPDATE l2_queue SET status = 'expired', updated_at = NOW()
                WHERE user_id = %s
            """, (user_id,))
            dropped.append(user_id)
        else:
            cur.execute("""
                UPDATE l2_queue SET status = 'waiting', joined_at = NOW(), updated_at = NOW()
                WHERE user_id = %s
            """, (user_id,))
            requeued.append(user_id)
    return {'expired': len(stale), 'requeued': requeued, 'dropped': dropped}


def offer_free_seats(cur):
    """For each currently free seat under the cap, offer the first waiting device
    a claim. Each offer gets a unique code and an expires_at = NOW() + the
    offer-expiry setting (72 h). The device's queue row flips to 'offered'.

    Only devices with NO live offer are offered (a device already holding an
    'offered' row occupies no seat but is waiting on its own offer, so it is not
    offered again). Idempotent and concurrency-safe under the seat lock: running
    it twice back-to-back makes no second offer because the first run flipped the
    rows to 'offered'.

    Returns the list of (user_id, code) offered this run.
    """
    _acquire_seat_lock(cur)
    settings = get_settings(cur)
    expiry_hours = settings['offer_expiry_hours']
    cap = get_seat_cap(cur)
    if cap is None:
        return []

    in_use = seats_in_use(cur)
    # Outstanding offers also effectively reserve a seat (the device will claim
    # it), so subtract live offers from the free count to avoid over-offering.
    cur.execute("SELECT COUNT(*) FROM l2_offers WHERE status = 'offered' AND expires_at > NOW()")
    live_offers = cur.fetchone()[0]
    free = max(0, cap - in_use - live_offers)
    if free <= 0:
        return []

    cur.execute("""
        SELECT user_id FROM l2_queue
        WHERE status = 'waiting'
        ORDER BY joined_at ASC
        LIMIT %s
    """, (free,))
    waiters = [r[0] for r in cur.fetchall()]

    offered = []
    for user_id in waiters:
        code = new_offer_code()
        cur.execute("""
            INSERT INTO l2_offers (user_id, code, offered_at, expires_at, status)
            VALUES (%s, %s, NOW(), NOW() + (%s || ' hours')::interval, 'offered')
        """, (user_id, code, expiry_hours))
        cur.execute("""
            UPDATE l2_queue SET status = 'offered', updated_at = NOW()
            WHERE user_id = %s
        """, (user_id,))
        offered.append((user_id, code))
    return offered


def run_seat_cycle(cur):
    """One full idempotent seat-maintenance cycle, in order:
        1. evict idle L2 devices (frees seats),
        2. expire stale offers (frees seats, requeues/drops devices),
        3. offer the freed seats to the head of the queue.
    Returns a summary dict. The caller owns the transaction and must COMMIT.
    """
    evicted = evict_idle(cur)
    expired = expire_offers(cur)
    offered = offer_free_seats(cur)
    return {
        'evicted': evicted,
        'offers_expired': expired['expired'],
        'requeued': expired['requeued'],
        'dropped': expired['dropped'],
        'offered': offered,
    }
