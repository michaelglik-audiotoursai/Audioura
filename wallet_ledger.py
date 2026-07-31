"""
Wallet Ledger — user-facing billing record for Subscribed.
==========================================================
This is what the USER is charged and what they hold.
cost_ledger (LOCAL-60) is what things cost US; this is the user's wallet.

Design rules:
    1. Append-only. One row per movement. Never mutate a row.
    2. Money is integer cents. Never float.
    3. Balance is DERIVED from the ledger (SUM of amount_cents).
    4. A cache exists for read speed; it is rebuildable from the ledger.
    5. Refund clawbacks may drive balance negative. Record it; don't clamp.
    6. Every write carries a caller-supplied idempotency key (no double-credit).
    7. Zero balance stops service (no debt from ordinary consumption).
    8. Unlimited tier has no balance; tracks our-cost against cost-stop instead.

Movement types:
    topup               — user purchased credits ($10.00 = 1000 cents)
    charge              — usage debit (our_cost × PRICING_MULTIPLIER)
    refund_clawback     — Apple refund reversal (negative, may go below 0)
    monthly_fee         — $2/month Pay-Per-Use subscription fee
    monthly_fee_unlimited — $50/month Unlimited subscription fee
"""

import json
import logging
import os
import uuid
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from typing import Optional, Tuple, List, Dict

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

# --- Configuration (runtime-tunable, per SUBSCRIBED_DESIGN.md) ---
PRICING_MULTIPLIER = Decimal(os.environ.get("PRICING_MULTIPLIER", "5.0"))
PPU_MONTHLY_FEE_USD = Decimal(os.environ.get("PPU_MONTHLY_FEE_USD", "2.00"))
CREDIT_TOPUP_USD = Decimal(os.environ.get("CREDIT_TOPUP_USD", "10.00"))
CREDIT_LOW_BALANCE_USD = Decimal(os.environ.get("CREDIT_LOW_BALANCE_USD", "2.00"))
UNLIMITED_MONTHLY_FEE_USD = Decimal(os.environ.get("UNLIMITED_MONTHLY_FEE_USD", "50.00"))
UNLIMITED_COST_STOP_FRACTION = Decimal(os.environ.get("UNLIMITED_COST_STOP_FRACTION", "0.5"))
CACHE_HIT_COST_USD = Decimal("0.00")

# Derived
UNLIMITED_COST_STOP_USD = UNLIMITED_MONTHLY_FEE_USD * UNLIMITED_COST_STOP_FRACTION  # $25.00

VALID_MOVEMENT_TYPES = frozenset([
    "topup",
    "charge",
    "refund_clawback",
    "monthly_fee",
    "monthly_fee_unlimited",
])


def _usd_to_cents(usd: Decimal) -> int:
    """Convert USD Decimal to integer cents. Always rounds half-up."""
    return int((usd * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _cents_to_usd(cents: int) -> Decimal:
    """Convert integer cents to USD Decimal."""
    return Decimal(cents) / Decimal(100)


def _get_db_connection():
    """Get database connection."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        host = os.environ.get("DB_HOST", "postgres-2")
        port = os.environ.get("DB_PORT", "5432")
        dbname = os.environ.get("DB_NAME", "audiotours")
        user = os.environ.get("DB_USER", "admin")
        password = os.environ.get("DB_PASSWORD", "password123")
        db_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
    return psycopg2.connect(db_url)


def _ensure_tables(conn) -> None:
    """Create wallet tables if not present (idempotent, for dev convenience).
    Production should use migration/sql/006_wallet_ledger.sql.
    """
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS wallet_ledger (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id VARCHAR(128) NOT NULL,
                movement_type VARCHAR(64) NOT NULL,
                amount_cents INTEGER NOT NULL,
                balance_after_cents INTEGER NOT NULL,
                idempotency_key VARCHAR(256) NOT NULL,
                description TEXT,
                reference_id VARCHAR(256),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_wallet_ledger_idempotency
            ON wallet_ledger (idempotency_key)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_wallet_ledger_user_time
            ON wallet_ledger (user_id, created_at DESC)
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS wallet_balance_cache (
                user_id VARCHAR(128) PRIMARY KEY,
                balance_cents INTEGER NOT NULL DEFAULT 0,
                last_ledger_id UUID,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS wallet_subscription (
                user_id VARCHAR(128) PRIMARY KEY,
                tier VARCHAR(32) NOT NULL DEFAULT 'free',
                period_start TIMESTAMPTZ,
                period_end TIMESTAMPTZ,
                monthly_cost_spent_cents INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    conn.commit()


# ============================================================
# CORE LEDGER OPERATIONS
# ============================================================

def record_movement(
    user_id: str,
    movement_type: str,
    amount_cents: int,
    idempotency_key: str,
    description: Optional[str] = None,
    reference_id: Optional[str] = None,
) -> Tuple[Optional[str], int]:
    """Record a wallet movement (append-only).

    Args:
        user_id: The user whose wallet this affects.
        movement_type: One of VALID_MOVEMENT_TYPES.
        amount_cents: Positive = credit, negative = debit. Integer cents.
        idempotency_key: Caller-supplied. Same key twice = no-op (returns existing row).
        description: Human-readable label, e.g. "Tour: French Riviera biking — $0.35"
        reference_id: Correlation ID (job_id, payment_id, subscription_id).

    Returns:
        Tuple of (row_id_or_None, balance_after_cents).
        On idempotent duplicate, returns (existing_row_id, existing_balance_after).
        On failure, returns (None, current_balance).
    """
    if movement_type not in VALID_MOVEMENT_TYPES:
        logger.error(f"[WALLET] Invalid movement_type: {movement_type}")
        return None, get_balance_cents(user_id)

    conn = _get_db_connection()
    try:
        _ensure_tables(conn)

        # Check idempotency: if this key already exists, return the existing row
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, balance_after_cents FROM wallet_ledger WHERE idempotency_key = %s",
                (idempotency_key,),
            )
            existing = cur.fetchone()
            if existing:
                conn.close()
                logger.info(
                    f"[WALLET] IDEMPOTENT_SKIP | key={idempotency_key} | "
                    f"existing_row={existing[0]} | balance={existing[1]}"
                )
                return str(existing[0]), existing[1]

        # Calculate new balance: use advisory lock to prevent race condition
        with conn.cursor() as cur:
            # Advisory lock based on hash of user_id (prevents concurrent writes for same user)
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (user_id,))

            cur.execute(
                "SELECT COALESCE(SUM(amount_cents), 0) FROM wallet_ledger WHERE user_id = %s",
                (user_id,),
            )
            current_balance = cur.fetchone()[0]
            new_balance = current_balance + amount_cents

            row_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO wallet_ledger
                    (id, user_id, movement_type, amount_cents, balance_after_cents,
                     idempotency_key, description, reference_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row_id, user_id, movement_type, amount_cents, new_balance,
                    idempotency_key, description, reference_id,
                    datetime.now(timezone.utc),
                ),
            )

            # Update balance cache
            cur.execute(
                """
                INSERT INTO wallet_balance_cache (user_id, balance_cents, last_ledger_id, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    balance_cents = EXCLUDED.balance_cents,
                    last_ledger_id = EXCLUDED.last_ledger_id,
                    updated_at = EXCLUDED.updated_at
                """,
                (user_id, new_balance, row_id, datetime.now(timezone.utc)),
            )

        conn.commit()
        conn.close()

        logger.info(
            f"[WALLET] {movement_type} | {amount_cents:+d}¢ | "
            f"balance={new_balance}¢ | user={user_id} | key={idempotency_key}"
        )
        return row_id, new_balance

    except psycopg2.errors.UniqueViolation:
        # Race condition: another thread inserted with same idempotency_key
        conn.rollback()
        conn.close()
        logger.info(f"[WALLET] IDEMPOTENT_RACE | key={idempotency_key}")
        # Re-fetch the existing row
        conn2 = _get_db_connection()
        with conn2.cursor() as cur:
            cur.execute(
                "SELECT id, balance_after_cents FROM wallet_ledger WHERE idempotency_key = %s",
                (idempotency_key,),
            )
            existing = cur.fetchone()
        conn2.close()
        if existing:
            return str(existing[0]), existing[1]
        return None, get_balance_cents(user_id)

    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"[WALLET] record_movement failed: {e}")
        return None, get_balance_cents(user_id)


def get_balance_cents(user_id: str) -> int:
    """Get user's current wallet balance in cents (from cache, falls back to ledger)."""
    conn = _get_db_connection()
    try:
        _ensure_tables(conn)
        with conn.cursor() as cur:
            # Try cache first
            cur.execute(
                "SELECT balance_cents FROM wallet_balance_cache WHERE user_id = %s",
                (user_id,),
            )
            cached = cur.fetchone()
            if cached is not None:
                conn.close()
                return cached[0]

            # Derive from ledger
            cur.execute(
                "SELECT COALESCE(SUM(amount_cents), 0) FROM wallet_ledger WHERE user_id = %s",
                (user_id,),
            )
            balance = cur.fetchone()[0]
        conn.close()
        return balance

    except Exception as e:
        logger.error(f"[WALLET] get_balance_cents failed: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return 0


def rebuild_balance_from_ledger(user_id: str) -> int:
    """Rebuild balance by summing all ledger rows. Updates the cache.
    Used for verification and cache repair.
    """
    conn = _get_db_connection()
    try:
        _ensure_tables(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(amount_cents), 0) FROM wallet_ledger WHERE user_id = %s",
                (user_id,),
            )
            rebuilt_balance = cur.fetchone()[0]

            # Get last ledger row ID
            cur.execute(
                "SELECT id FROM wallet_ledger WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            )
            last_row = cur.fetchone()
            last_id = last_row[0] if last_row else None

            # Update cache
            cur.execute(
                """
                INSERT INTO wallet_balance_cache (user_id, balance_cents, last_ledger_id, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    balance_cents = EXCLUDED.balance_cents,
                    last_ledger_id = EXCLUDED.last_ledger_id,
                    updated_at = EXCLUDED.updated_at
                """,
                (user_id, rebuilt_balance, last_id, datetime.now(timezone.utc)),
            )
        conn.commit()
        conn.close()
        return rebuilt_balance

    except Exception as e:
        logger.error(f"[WALLET] rebuild_balance failed: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return 0


# ============================================================
# HIGH-LEVEL OPERATIONS
# ============================================================

def topup(
    user_id: str,
    amount_usd: Decimal,
    idempotency_key: str,
    payment_id: Optional[str] = None,
) -> Tuple[Optional[str], int]:
    """Record a credit top-up.

    Args:
        user_id: User receiving credit.
        amount_usd: Amount in USD (e.g. Decimal("10.00")).
        idempotency_key: From the payment provider (prevents double-credit on retry).
        payment_id: Payment/transaction reference.

    Returns:
        (row_id, new_balance_cents)
    """
    cents = _usd_to_cents(amount_usd)
    return record_movement(
        user_id=user_id,
        movement_type="topup",
        amount_cents=cents,
        idempotency_key=idempotency_key,
        description=f"Credit top-up: ${amount_usd:.2f}",
        reference_id=payment_id,
    )


def charge(
    user_id: str,
    charge_usd: Decimal,
    idempotency_key: str,
    description: Optional[str] = None,
    job_id: Optional[str] = None,
) -> Tuple[Optional[str], int, bool]:
    """Charge the user's wallet. The charge_usd is already the user-facing price
    (our_cost × multiplier, computed by the pricing layer in LOCAL-65).

    This function does NOT apply the ×5 multiplier. It takes the final charge amount.

    Args:
        user_id: User to charge.
        charge_usd: Amount to debit in USD (already includes markup).
        idempotency_key: Unique key for this charge operation.
        description: Human-readable, e.g. "Tour: French Riviera biking — $0.35"
        job_id: Correlation ID.

    Returns:
        (row_id, new_balance_cents, was_zero_stop_triggered)
    """
    # Check balance before charge
    current_balance = get_balance_cents(user_id)
    charge_cents = _usd_to_cents(charge_usd)

    # Zero-balance stop: if balance is already 0 or less, block the charge
    # Note: negative balance from clawback does NOT block — only zero from normal use
    # Decision D3: zero balance = hard stop. No debt from ordinary consumption.
    if current_balance <= 0:
        logger.warning(
            f"[WALLET] ZERO_STOP | user={user_id} | balance={current_balance}¢ | "
            f"attempted_charge={charge_cents}¢ | BLOCKED"
        )
        return None, current_balance, True

    # If this charge would go negative, also block (no debt from normal consumption)
    if current_balance - charge_cents < 0:
        logger.warning(
            f"[WALLET] INSUFFICIENT_BALANCE | user={user_id} | balance={current_balance}¢ | "
            f"attempted_charge={charge_cents}¢ | BLOCKED"
        )
        return None, current_balance, True

    row_id, new_balance = record_movement(
        user_id=user_id,
        movement_type="charge",
        amount_cents=-charge_cents,
        idempotency_key=idempotency_key,
        description=description,
        reference_id=job_id,
    )

    return row_id, new_balance, False


def refund_clawback(
    user_id: str,
    amount_usd: Decimal,
    idempotency_key: str,
    description: Optional[str] = None,
    reference_id: Optional[str] = None,
) -> Tuple[Optional[str], int]:
    """Record a refund clawback (Apple refund reversal).
    This MAY drive the balance negative. That is correct behavior.
    Michael: "No Problem. That only impacts how we calculate corporate revenue vs. cashflow."
    """
    cents = _usd_to_cents(amount_usd)
    return record_movement(
        user_id=user_id,
        movement_type="refund_clawback",
        amount_cents=-cents,  # Negative: we're taking back money
        idempotency_key=idempotency_key,
        description=description or f"Refund clawback: ${amount_usd:.2f}",
        reference_id=reference_id,
    )


def monthly_fee(
    user_id: str,
    tier: str,
    idempotency_key: str,
) -> Tuple[Optional[str], int]:
    """Record monthly subscription fee as a visible transaction in the Wallet.

    Per D20: the fee is billed by Apple against the card (auto-renewable subscription).
    It must NOT reduce the credit balance. We record a $0 movement so the fee appears
    in the transaction list for transparency, but balance_cents is unchanged.

    The user sees: "Monthly fee (Pay-Per-Use): $2.00 — billed by Apple"
    The balance does not move.

    Args:
        tier: 'ppu' ($2) or 'unlimited' ($50)
    """
    if tier == "ppu":
        fee_usd = PPU_MONTHLY_FEE_USD
        movement = "monthly_fee"
        desc = f"Monthly fee (Pay-Per-Use): ${fee_usd:.2f} — billed by Apple"
    elif tier == "unlimited":
        fee_usd = UNLIMITED_MONTHLY_FEE_USD
        movement = "monthly_fee_unlimited"
        desc = f"Monthly fee (Unlimited): ${fee_usd:.2f} — billed by Apple"
    else:
        logger.error(f"[WALLET] Invalid tier for monthly_fee: {tier}")
        return None, get_balance_cents(user_id)

    # D20: Record with amount_cents=0 so balance is unchanged.
    # The fee is visible in the transaction list but does not debit the wallet.
    return record_movement(
        user_id=user_id,
        movement_type=movement,
        amount_cents=0,
        idempotency_key=idempotency_key,
        description=desc,
    )


# ============================================================
# UNLIMITED TIER — COST-STOP TRACKING
# ============================================================

def check_unlimited_cost_stop(user_id: str, additional_cost_usd: Decimal = Decimal("0")) -> Dict:
    """Check whether an unlimited-tier user has hit their monthly cost stop.

    The cost stop = UNLIMITED_MONTHLY_FEE_USD × UNLIMITED_COST_STOP_FRACTION = $25.
    It is based on OUR cost (from cost_ledger), not user charges.

    Returns:
        {
            "breached": bool,
            "current_cost_usd": Decimal,
            "limit_usd": Decimal,
            "message": str or None,  -- non-None if breached (per D4)
        }
    """
    conn = _get_db_connection()
    try:
        _ensure_tables(conn)
        with conn.cursor() as cur:
            # Get subscription period for this user
            cur.execute(
                "SELECT period_start, monthly_cost_spent_cents FROM wallet_subscription WHERE user_id = %s",
                (user_id,),
            )
            sub = cur.fetchone()
            if not sub:
                conn.close()
                return {
                    "breached": False,
                    "current_cost_usd": Decimal("0"),
                    "limit_usd": UNLIMITED_COST_STOP_USD,
                    "message": None,
                }

            current_cost_cents = sub[1]
            current_cost_usd = _cents_to_usd(current_cost_cents)
            projected = current_cost_usd + additional_cost_usd

            breached = projected >= UNLIMITED_COST_STOP_USD

            message = None
            if breached:
                message = (
                    f"Your Unlimited plan has reached its monthly usage limit. "
                    f"We've spent ${current_cost_usd:.2f} of the ${UNLIMITED_COST_STOP_USD:.2f} "
                    f"monthly allowance on your behalf. "
                    f"You can switch to Pay-Per-Use for the rest of this month to continue "
                    f"generating new content, or wait for your plan to reset at the start "
                    f"of your next billing period."
                )

        conn.close()
        return {
            "breached": breached,
            "current_cost_usd": current_cost_usd,
            "limit_usd": UNLIMITED_COST_STOP_USD,
            "message": message,
        }

    except Exception as e:
        logger.error(f"[WALLET] check_unlimited_cost_stop failed: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return {
            "breached": False,
            "current_cost_usd": Decimal("0"),
            "limit_usd": UNLIMITED_COST_STOP_USD,
            "message": None,
        }


def record_unlimited_cost(user_id: str, our_cost_usd: Decimal) -> Dict:
    """Record our-cost against the unlimited tier's monthly cost-stop.
    Call this after each operation for unlimited-tier users.

    Returns the result of check_unlimited_cost_stop (with the new total).
    """
    cost_cents = _usd_to_cents(our_cost_usd)

    conn = _get_db_connection()
    try:
        _ensure_tables(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE wallet_subscription
                SET monthly_cost_spent_cents = monthly_cost_spent_cents + %s,
                    updated_at = %s
                WHERE user_id = %s
                RETURNING monthly_cost_spent_cents
                """,
                (cost_cents, datetime.now(timezone.utc), user_id),
            )
            result = cur.fetchone()
            if not result:
                # No subscription row — create one (unlimited tier assumed from caller)
                cur.execute(
                    """
                    INSERT INTO wallet_subscription (user_id, tier, monthly_cost_spent_cents, updated_at)
                    VALUES (%s, 'unlimited', %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        monthly_cost_spent_cents = wallet_subscription.monthly_cost_spent_cents + %s,
                        updated_at = EXCLUDED.updated_at
                    RETURNING monthly_cost_spent_cents
                    """,
                    (user_id, cost_cents, datetime.now(timezone.utc), cost_cents),
                )
                result = cur.fetchone()

        conn.commit()
        conn.close()

        return check_unlimited_cost_stop(user_id)

    except Exception as e:
        logger.error(f"[WALLET] record_unlimited_cost failed: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return check_unlimited_cost_stop(user_id)


# ============================================================
# LOW BALANCE REMINDER
# ============================================================

def check_low_balance(user_id: str) -> Optional[str]:
    """Check if user's balance is below the reminder threshold.
    Returns a reminder message if low, None otherwise.

    Per Apple constraint: no auto-charge. Send reminder; user taps to purchase.
    """
    balance_cents = get_balance_cents(user_id)
    threshold_cents = _usd_to_cents(CREDIT_LOW_BALANCE_USD)

    if balance_cents <= threshold_cents:
        balance_usd = _cents_to_usd(balance_cents)
        return (
            f"Your balance is ${balance_usd:.2f}. "
            f"Top up ${CREDIT_TOPUP_USD:.2f} to continue using audio tours and articles."
        )
    return None


# ============================================================
# TRANSACTION HISTORY (for Settings → Wallet UI)
# ============================================================

def get_transaction_history(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict]:
    """Get user's transaction history for the wallet UI.
    Returns human-readable records, newest first.
    """
    conn = _get_db_connection()
    try:
        _ensure_tables(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT movement_type, amount_cents, balance_after_cents,
                       description, reference_id, created_at
                FROM wallet_ledger
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (user_id, limit, offset),
            )
            rows = cur.fetchall()
        conn.close()

        return [
            {
                "type": r[0],
                "amount_usd": f"${abs(r[1]) / 100:.2f}",
                "direction": "credit" if r[1] > 0 else "debit",
                "balance_after_usd": f"${r[2] / 100:.2f}" if r[2] >= 0 else f"-${abs(r[2]) / 100:.2f}",
                "description": r[3],
                "reference_id": r[4],
                "date": r[5].isoformat() if r[5] else None,
            }
            for r in rows
        ]

    except Exception as e:
        logger.error(f"[WALLET] get_transaction_history failed: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return []
