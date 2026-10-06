"""
Referral Engine — code generation + redemption tracking.
=========================================================
Generates deterministic referral codes and tracks redemptions in Postgres.

LOCAL-115: record_referral_redemption now returns "duplicate" on UNIQUE
constraint violation instead of raising, enabling graceful 409 responses.
"""
import hashlib
import logging

import psycopg2

logger = logging.getLogger(__name__)

# Base36 for short, readable codes
_BASE36 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def generate_referral_code(user_id: str) -> str:
    """Generate a deterministic 6-char referral code from user_id hash."""
    digest = hashlib.sha256(f"referral:{user_id}".encode()).digest()
    num = int.from_bytes(digest[:4], "big")
    chars = []
    for _ in range(6):
        chars.append(_BASE36[num % 36])
        num //= 36
    return "".join(chars)


def _ensure_tables(conn) -> None:
    """Create referral tables if not exist (idempotent)."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referral_codes (
                code VARCHAR(6) PRIMARY KEY,
                referrer_user_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                redemption_count INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referral_redemptions (
                id SERIAL PRIMARY KEY,
                referral_code VARCHAR(6) NOT NULL REFERENCES referral_codes(code),
                new_user_id TEXT NOT NULL,
                redeemed_at TIMESTAMP DEFAULT NOW()
            )
        """)
    conn.commit()


def store_referral(code: str, referrer_user_id: str, db_url: str) -> bool:
    """Store (upsert) a referral code. Returns True on success."""
    try:
        conn = psycopg2.connect(db_url)
        _ensure_tables(conn)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO referral_codes (code, referrer_user_id)
                VALUES (%s, %s)
                ON CONFLICT (code) DO NOTHING
            """, (code, referrer_user_id))
        conn.commit()
        conn.close()
        logger.info(f"Stored referral code {code} for user {referrer_user_id}")
        return True
    except Exception as e:
        logger.error(f"Error storing referral {code}: {e}")
        return False


def record_referral_redemption(code: str, new_user_id: str, db_url: str):
    """
    Record a redemption: increment count + insert redemption row.

    Returns:
      True      — success
      "duplicate" — UNIQUE constraint violation (same user already redeemed this code)
      False     — other error
    """
    conn = None
    try:
        conn = psycopg2.connect(db_url)
        _ensure_tables(conn)
        with conn.cursor() as cur:
            # Increment redemption count
            cur.execute(
                "UPDATE referral_codes SET redemption_count = redemption_count + 1 WHERE code = %s",
                (code,),
            )
            # Insert redemption record — may fail on UNIQUE(referral_code, new_user_id)
            cur.execute(
                "INSERT INTO referral_redemptions (referral_code, new_user_id) VALUES (%s, %s)",
                (code, new_user_id),
            )
        conn.commit()
        logger.info(f"Recorded redemption of {code} by {new_user_id}")
        return True
    except psycopg2.errors.UniqueViolation:
        # UNIQUE constraint on (referral_code, new_user_id) fired — duplicate redemption
        if conn:
            conn.rollback()
        logger.info(f"Duplicate redemption blocked by constraint: {code} by {new_user_id}")
        return "duplicate"
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error recording redemption {code}: {e}")
        return False
    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════════════════
# LOCAL-596: referral → L2 seat grant.
# ═══════════════════════════════════════════════════════════════════════════
# A redeemed referral grants the REDEEMER an L2 seat, counted against the 100
# cap and refused with a structured error when it is full. The REFERRER'S
# allowance (L3 3 lifetime, L4 5/month, Tester 3) gates how many referrals a
# device may hand out — every number comes from the referrer's `plans` row
# (referrals_allowed + referral_period), never a constant here.
#
# Structured result codes (LOCAL-580 contract), returned by
# redeem_referral_for_seat:
#     ok                       — seat granted to the redeemer
#     referral_duplicate       — this device already redeemed this code
#     referral_self            — self-referral (redeemer == referrer)
#     referral_unknown_code    — no such code
#     referral_allowance_spent — referrer has used their referral allowance
#     referral_seats_full      — the 100-seat L2 cap is full
# ═══════════════════════════════════════════════════════════════════════════
REDEEM_OK = 'ok'
REDEEM_DUPLICATE = 'referral_duplicate'
REDEEM_SELF = 'referral_self'
REDEEM_UNKNOWN = 'referral_unknown_code'
REDEEM_ALLOWANCE_SPENT = 'referral_allowance_spent'
REDEEM_SEATS_FULL = 'referral_seats_full'


def _referrer_level(cur, referrer_user_id):
    """The referrer's current device level (defaults to 'l1' if no row)."""
    cur.execute("SELECT level FROM device_entitlement WHERE user_id = %s", (referrer_user_id,))
    row = cur.fetchone()
    return row[0] if row else 'l1'


def _referral_allowance(cur, level):
    """(referrals_allowed, referral_period) for a level from plans. A level with
    0 / NULL allowed may not refer at all."""
    cur.execute(
        "SELECT referrals_allowed, referral_period FROM plans WHERE plan_id = %s",
        (level,),
    )
    row = cur.fetchone()
    if not row:
        return 0, None
    return (row[0] or 0), row[1]


def _referrer_redemptions_used(cur, referrer_user_id, period):
    """How many referrals this referrer has already spent in the current period.

    Counts successful redemptions across ALL of the referrer's codes (a device
    could, in principle, hold more than one code). 'lifetime' counts every
    redemption ever; 'month' counts those in the current calendar month.
    """
    if period == 'month':
        window = "AND rr.redeemed_at >= date_trunc('month', CURRENT_DATE)"
    else:  # 'lifetime' or NULL → all-time
        window = ""
    cur.execute(f"""
        SELECT COUNT(*)
        FROM referral_redemptions rr
        JOIN referral_codes rc ON rc.code = rr.referral_code
        WHERE rc.referrer_user_id = %s {window}
    """, (referrer_user_id,))
    return cur.fetchone()[0]


def redeem_referral_for_seat(code: str, new_user_id: str, db_url: str):
    """Redeem a referral code and grant the redeemer an L2 seat.

    Enforces, atomically in one transaction:
      1. the code exists,
      2. it is not a self-referral,
      3. the referrer still has referral allowance in their period
         (plans.referrals_allowed / referral_period for the referrer's level),
      4. the redemption is not a duplicate (UNIQUE (referral_code, new_user_id)),
      5. an L2 seat is free under the 100 cap — seat grant goes through
         l2_seats.claim-style logic under the seat advisory lock.

    Order note: the allowance check happens BEFORE recording the redemption so a
    refused referral does not consume a redemption slot. The seat grant and the
    redemption row commit together, so a device is never charged a seat without
    a recorded redemption and vice versa.

    Returns a dict: {ok, code (REDEEM_* enum), message, referrer_user_id}.
    """
    import l2_seats
    conn = None
    try:
        conn = psycopg2.connect(db_url)
        _ensure_tables(conn)
        cur = conn.cursor()

        # 1. Code exists?
        cur.execute("SELECT referrer_user_id FROM referral_codes WHERE code = %s", (code,))
        row = cur.fetchone()
        if not row:
            conn.rollback()
            return {'ok': False, 'code': REDEEM_UNKNOWN,
                    'message': 'That referral code is not valid.',
                    'referrer_user_id': None}
        referrer_user_id = row[0]

        # 2. Self-referral?
        if new_user_id == referrer_user_id:
            conn.rollback()
            return {'ok': False, 'code': REDEEM_SELF,
                    'message': 'You cannot redeem your own referral code.',
                    'referrer_user_id': referrer_user_id}

        # Duplicate (already redeemed by this device)? Check up front for a clean
        # message; the UNIQUE constraint is still the race-proof backstop below.
        cur.execute("""
            SELECT 1 FROM referral_redemptions
            WHERE referral_code = %s AND new_user_id = %s
        """, (code, new_user_id))
        if cur.fetchone():
            conn.rollback()
            return {'ok': False, 'code': REDEEM_DUPLICATE,
                    'message': 'You have already redeemed this referral code.',
                    'referrer_user_id': referrer_user_id}

        # 3. Referrer allowance (from the referrer's plan row).
        level = _referrer_level(cur, referrer_user_id)
        allowed, period = _referral_allowance(cur, level)
        if allowed <= 0:
            conn.rollback()
            return {'ok': False, 'code': REDEEM_ALLOWANCE_SPENT,
                    'message': 'This referral code can no longer grant seats.',
                    'referrer_user_id': referrer_user_id}
        used = _referrer_redemptions_used(cur, referrer_user_id, period)
        if used >= allowed:
            conn.rollback()
            return {'ok': False, 'code': REDEEM_ALLOWANCE_SPENT,
                    'message': 'This referrer has used all of their referral invites.',
                    'referrer_user_id': referrer_user_id}

        # 5. Seat free under the cap? Serialize with the seat advisory lock so a
        #    referral grant cannot overshoot the cap against a racing install or
        #    claim (design: referral seats count against the 100 cap).
        l2_seats._acquire_seat_lock(cur)
        cap = l2_seats.get_seat_cap(cur)
        # If the redeemer already holds an L2 seat, the grant is a no-op but the
        # referral still counts; otherwise we need a free seat.
        cur.execute("SELECT level FROM device_entitlement WHERE user_id = %s", (new_user_id,))
        de = cur.fetchone()
        already_l2 = de is not None and de[0] == 'l2'
        if not already_l2 and cap is not None and l2_seats.seats_in_use(cur) >= cap:
            conn.rollback()
            return {'ok': False, 'code': REDEEM_SEATS_FULL,
                    'message': 'The free level is full right now, so this invite can’t be used yet.',
                    'referrer_user_id': referrer_user_id}

        # 4. Record the redemption (UNIQUE backstop) + 5. grant the seat.
        try:
            cur.execute(
                "UPDATE referral_codes SET redemption_count = redemption_count + 1 WHERE code = %s",
                (code,),
            )
            cur.execute(
                "INSERT INTO referral_redemptions (referral_code, new_user_id) VALUES (%s, %s)",
                (code, new_user_id),
            )
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            return {'ok': False, 'code': REDEEM_DUPLICATE,
                    'message': 'You have already redeemed this referral code.',
                    'referrer_user_id': referrer_user_id}

        cur.execute("""
            INSERT INTO device_entitlement (user_id, level, last_activity_at)
            VALUES (%s, 'l2', NOW())
            ON CONFLICT (user_id) DO UPDATE SET level = 'l2', updated_at = NOW()
        """, (new_user_id,))
        conn.commit()
        logger.info(f"Referral {code} redeemed by {new_user_id} → L2 seat (referrer {referrer_user_id}, {level})")
        return {'ok': True, 'code': REDEEM_OK,
                'message': 'Referral redeemed — you now have a free L2 seat.',
                'referrer_user_id': referrer_user_id}
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error redeeming referral {code} for seat: {e}")
        return {'ok': False, 'code': 'referral_error',
                'message': 'Could not redeem the referral right now. Please try again.',
                'referrer_user_id': None}
    finally:
        if conn:
            conn.close()
