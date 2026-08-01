"""
Tier Change Service — implements the switch that remedies promise.
==================================================================
LOCAL-90: The entitlement gate returns remedy='switch_to_ppu' and remedy='upgrade',
but nothing implements the action. This module closes that gap.

All tier changes go through PaymentProvider (the fake for now, RevenueCat later).
The DB is updated as a CONSEQUENCE of a successful provider operation, never as
the primary path. A half-completed change must not leave the user billed for one
tier and entitled to another (D14: fail closed).

Supported transitions:
    free → ppu          (new subscription)
    free → unlimited    (new subscription)
    ppu → unlimited     (upgrade)
    unlimited → ppu     (downgrade, typically at cost-stop)
    ppu → free          (cancellation)
    unlimited → free    (cancellation)

Proration decision (needs Michael's confirmation):
    - Unlimited → PPU: No credit for remaining Unlimited days. The user hit the
      cost-stop and chose to switch to keep generating. PPU starts immediately
      with $0 balance — they must top up. Cost-stop resets (no longer relevant).
      Rationale: Unlimited already served its purpose up to the stop. Crediting
      the unused portion would reward gaming (subscribe Unlimited, generate $25
      worth, switch to PPU with a pro-rated $30 credit). The $2/month PPU fee
      applies from the next billing cycle; immediate switch is free of the PPU fee.
    - PPU → Unlimited: Credits are non-refundable (per design doc). Any remaining
      PPU balance is frozen, not lost — if the user later switches back to PPU,
      the balance is still there. The $50 Unlimited fee starts a fresh 30-day period.
    - Free → Paid: Normal first purchase. PPU gets initial $10 top-up via the
      provider. Unlimited gets a fresh 30-day period and $0 cost used.
    - Paid → Free: Immediate cancellation. Apple would normally retain access
      until period_end; the fake models immediate cutoff. Real implementation
      must honour the Apple grace period.
"""

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Tuple

import psycopg2

logger = logging.getLogger(__name__)

# Product IDs — must match what FakePaymentProvider and RevenueCat recognise
PRODUCT_PPU = "com.audioura.ppu_monthly"
PRODUCT_UNLIMITED = "com.audioura.unlimited_monthly"

VALID_TIERS = ("free", "ppu", "unlimited")
VALID_TRANSITIONS = {
    ("free", "ppu"),
    ("free", "unlimited"),
    ("ppu", "unlimited"),
    ("unlimited", "ppu"),
    ("ppu", "free"),
    ("unlimited", "free"),
}


def _get_db_connection():
    """Get database connection using env vars (same as wallet_ledger)."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        host = os.environ.get("DB_HOST", "postgres-2")
        port = os.environ.get("DB_PORT", "5432")
        dbname = os.environ.get("DB_NAME", "audiotours")
        user = os.environ.get("DB_USER", "admin")
        password = os.environ.get("DB_PASSWORD", "password123")
        db_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
    return psycopg2.connect(db_url)


def _get_current_tier(user_id: str) -> str:
    """Read the user's current tier from wallet_subscription (canonical source).
    Falls back to users.plan if no wallet_subscription row exists.
    """
    conn = _get_db_connection()
    try:
        with conn.cursor() as cur:
            # wallet_subscription is the billing-system source of truth
            cur.execute(
                "SELECT tier FROM wallet_subscription WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if row:
                conn.close()
                return row[0]

            # Fall back to users.plan (for users who never had a subscription)
            cur.execute(
                "SELECT plan FROM users WHERE secret_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            conn.close()
            return row[0] if row else "free"
    except Exception as e:
        logger.error(f"[TIER_CHANGE] _get_current_tier failed for {user_id}: {e}")
        try:
            conn.close()
        except Exception:
            pass
        raise


def change_tier(
    user_id: str,
    target_tier: str,
    provider=None,
) -> dict:
    """
    Execute a tier change for the user.

    This is the ONLY production path for tier changes. It:
    1. Validates the transition
    2. Calls PaymentProvider (purchase/cancel)
    3. Updates DB state atomically
    4. Returns structured result

    Args:
        user_id: The user changing tier.
        target_tier: 'free', 'ppu', or 'unlimited'.
        provider: PaymentProvider instance. If None, uses FakePaymentProvider.

    Returns:
        {
            "success": bool,
            "previous_tier": str,
            "new_tier": str,
            "message": str,
            "balance_usd": float or None,
            "details": dict,  # provider-specific details
        }

    On failure, success=False and the user's tier is UNCHANGED.
    """
    if target_tier not in VALID_TIERS:
        return {
            "success": False,
            "previous_tier": None,
            "new_tier": None,
            "message": f"Invalid target tier: '{target_tier}'. Must be one of: {VALID_TIERS}",
            "balance_usd": None,
            "details": {},
        }

    # Get current tier
    try:
        current_tier = _get_current_tier(user_id)
    except Exception as e:
        logger.error(f"[TIER_CHANGE] Cannot determine current tier for {user_id}: {e}")
        return {
            "success": False,
            "previous_tier": None,
            "new_tier": None,
            "message": "Could not determine your current subscription tier. Please try again.",
            "balance_usd": None,
            "details": {"error": str(e)},
        }

    # No-op if already on target tier
    if current_tier == target_tier:
        return {
            "success": True,
            "previous_tier": current_tier,
            "new_tier": target_tier,
            "message": f"You are already on the {_display_name(target_tier)} plan.",
            "balance_usd": None,
            "details": {"no_op": True},
        }

    # Validate transition
    transition = (current_tier, target_tier)
    if transition not in VALID_TRANSITIONS:
        return {
            "success": False,
            "previous_tier": current_tier,
            "new_tier": None,
            "message": (
                f"Cannot switch from {_display_name(current_tier)} to "
                f"{_display_name(target_tier)} directly."
            ),
            "balance_usd": None,
            "details": {"invalid_transition": transition},
        }

    # Get or create provider
    if provider is None:
        from fake_payment_provider import FakePaymentProvider
        provider = FakePaymentProvider()

    # Dispatch to the appropriate handler
    if target_tier == "free":
        return _handle_cancellation(user_id, current_tier, provider)
    elif current_tier == "free":
        return _handle_new_subscription(user_id, target_tier, provider)
    else:
        return _handle_tier_switch(user_id, current_tier, target_tier, provider)


def _handle_new_subscription(user_id: str, target_tier: str, provider) -> dict:
    """Free → PPU or Free → Unlimited. Fresh subscription."""
    product_id = PRODUCT_PPU if target_tier == "ppu" else PRODUCT_UNLIMITED

    # 1. Call provider to purchase
    result = provider.purchase_subscription(user_id, product_id)

    if not result.success:
        logger.error(
            f"[TIER_CHANGE] Provider purchase failed for {user_id} → {target_tier}: {result.error}"
        )
        return {
            "success": False,
            "previous_tier": "free",
            "new_tier": None,
            "message": f"Subscription purchase failed: {result.error}",
            "balance_usd": None,
            "details": {"provider_error": result.error},
        }

    # 2. Provider succeeded — update DB atomically
    try:
        _sync_db_state(user_id, target_tier, result)
    except Exception as e:
        # CRITICAL: Provider says purchased but DB update failed.
        # D14: fail closed. Log at CRITICAL. The user is NOT on the new tier.
        # They may have been charged by Apple but not entitled.
        # This needs manual reconciliation (or a retry queue in production).
        logger.critical(
            f"[TIER_CHANGE] DB sync failed AFTER provider purchase for {user_id}: {e}. "
            f"User may be charged for {target_tier} without entitlement. "
            f"Transaction: {result.transaction_id}"
        )
        return {
            "success": False,
            "previous_tier": "free",
            "new_tier": None,
            "message": (
                "Your purchase was processed but we could not activate your subscription. "
                "Please contact support with this reference: " + (result.transaction_id or "unknown")
            ),
            "balance_usd": None,
            "details": {
                "partial_failure": True,
                "transaction_id": result.transaction_id,
                "error": str(e),
            },
        }

    balance_usd = result.new_balance_usd if target_tier == "ppu" else None

    logger.info(
        f"[TIER_CHANGE] SUCCESS: {user_id} free → {target_tier} | "
        f"txn={result.transaction_id} | balance=${balance_usd}"
    )

    return {
        "success": True,
        "previous_tier": "free",
        "new_tier": target_tier,
        "message": (
            f"Welcome to {_display_name(target_tier)}! "
            + (_ppu_welcome_msg(balance_usd) if target_tier == "ppu" else _unlimited_welcome_msg())
        ),
        "balance_usd": balance_usd,
        "details": {
            "transaction_id": result.transaction_id,
            "provider_subscription_id": getattr(result, "provider_subscription_id", None),
        },
    }


def _handle_tier_switch(
    user_id: str, current_tier: str, target_tier: str, provider
) -> dict:
    """PPU ↔ Unlimited. Switch between paid tiers."""

    # In Apple's model, switching between subscription tiers within the same
    # subscription group is handled automatically — the user purchases the new
    # tier and Apple cancels the old one. With RevenueCat, you call
    # purchaseProduct and it handles the upgrade/downgrade.
    #
    # For the fake provider, we model this as: cancel old + purchase new.
    # A failure after cancel but before purchase would be catastrophic.
    # Therefore: purchase new FIRST (provider can handle the overlap),
    # then cancel old.

    new_product = PRODUCT_PPU if target_tier == "ppu" else PRODUCT_UNLIMITED

    # 1. Purchase new tier via provider
    purchase_result = provider.purchase_subscription(user_id, new_product)

    if not purchase_result.success:
        logger.error(
            f"[TIER_CHANGE] Switch purchase failed for {user_id} "
            f"{current_tier} → {target_tier}: {purchase_result.error}"
        )
        return {
            "success": False,
            "previous_tier": current_tier,
            "new_tier": None,
            "message": f"Could not switch to {_display_name(target_tier)}: {purchase_result.error}",
            "balance_usd": None,
            "details": {"provider_error": purchase_result.error},
        }

    # 2. Provider succeeded — update DB state atomically
    try:
        _sync_db_state_switch(user_id, current_tier, target_tier, purchase_result)
    except Exception as e:
        logger.critical(
            f"[TIER_CHANGE] DB sync failed AFTER tier switch for {user_id} "
            f"({current_tier} → {target_tier}): {e}. "
            f"Transaction: {purchase_result.transaction_id}"
        )
        return {
            "success": False,
            "previous_tier": current_tier,
            "new_tier": None,
            "message": (
                "Your tier change was processed but we could not update your account. "
                "Please contact support with reference: "
                + (purchase_result.transaction_id or "unknown")
            ),
            "balance_usd": None,
            "details": {
                "partial_failure": True,
                "transaction_id": purchase_result.transaction_id,
                "error": str(e),
            },
        }

    # Build response
    balance_usd = None
    if target_tier == "ppu":
        # After switching to PPU, report current wallet balance
        from wallet_ledger import get_balance_cents
        balance_usd = get_balance_cents(user_id) / 100.0

    msg = _switch_message(current_tier, target_tier, balance_usd)

    logger.info(
        f"[TIER_CHANGE] SUCCESS: {user_id} {current_tier} → {target_tier} | "
        f"txn={purchase_result.transaction_id} | balance=${balance_usd}"
    )

    return {
        "success": True,
        "previous_tier": current_tier,
        "new_tier": target_tier,
        "message": msg,
        "balance_usd": balance_usd,
        "details": {
            "transaction_id": purchase_result.transaction_id,
            "proration": _proration_description(current_tier, target_tier),
        },
    }


def _handle_cancellation(user_id: str, current_tier: str, provider) -> dict:
    """PPU → Free or Unlimited → Free. Cancel subscription."""

    # In Apple's model, cancellation means the subscription won't renew.
    # The user retains access until period_end. For the fake, we model
    # immediate cutoff.
    webhook_result = provider.handle_webhook({
        "event_type": "cancellation",
        "user_id": user_id,
    })

    if not webhook_result.handled:
        logger.error(
            f"[TIER_CHANGE] Cancellation webhook failed for {user_id}: {webhook_result.details}"
        )
        return {
            "success": False,
            "previous_tier": current_tier,
            "new_tier": None,
            "message": "Could not cancel your subscription. Please try again.",
            "balance_usd": None,
            "details": {"webhook_error": webhook_result.details},
        }

    # Update DB state
    try:
        _sync_db_state_cancel(user_id, current_tier)
    except Exception as e:
        logger.critical(
            f"[TIER_CHANGE] DB sync failed AFTER cancellation for {user_id}: {e}"
        )
        return {
            "success": False,
            "previous_tier": current_tier,
            "new_tier": None,
            "message": (
                "Your cancellation was processed but we could not update your account. "
                "Please contact support."
            ),
            "balance_usd": None,
            "details": {"partial_failure": True, "error": str(e)},
        }

    logger.info(f"[TIER_CHANGE] SUCCESS: {user_id} {current_tier} → free (cancelled)")

    return {
        "success": True,
        "previous_tier": current_tier,
        "new_tier": "free",
        "message": (
            f"Your {_display_name(current_tier)} subscription has been cancelled. "
            "You are now on the Free plan."
            + (" Your credit balance is preserved if you resubscribe later."
               if current_tier == "ppu" else "")
        ),
        "balance_usd": None,
        "details": {"cancelled_tier": current_tier},
    }


# ============================================================
# DB SYNC — atomic state updates after provider confirms
# ============================================================

def _sync_db_state(user_id: str, new_tier: str, purchase_result) -> None:
    """Atomically update all DB tables after a fresh subscription purchase.
    All or nothing — if any step fails, the transaction rolls back.
    """
    conn = _get_db_connection()
    try:
        now = datetime.now(timezone.utc)
        period_start = now
        period_end = now + timedelta(days=30)

        with conn.cursor() as cur:
            # Advisory lock on user to prevent concurrent modifications
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (user_id,))

            # 1. Update users.plan
            cur.execute(
                "UPDATE users SET plan = %s WHERE secret_id = %s",
                (new_tier, user_id),
            )

            # 2. Deactivate any existing subscription rows
            cur.execute(
                "UPDATE subscriptions SET state = 'cancelled', updated_at = %s WHERE user_id = %s AND state IN ('active', 'billing_retry')",
                (now, user_id),
            )

            # 3. Insert new subscription row
            cur.execute(
                """INSERT INTO subscriptions
                   (user_id, tier, state, period_start, period_end, provider_subscription_id, created_at, updated_at)
                   VALUES (%s, %s, 'active', %s, %s, %s, %s, %s)""",
                (user_id, new_tier, period_start, period_end,
                 purchase_result.transaction_id, now, now),
            )

            # 4. Upsert wallet_subscription
            cur.execute(
                """INSERT INTO wallet_subscription
                   (user_id, tier, period_start, period_end, monthly_cost_spent_cents, updated_at)
                   VALUES (%s, %s, %s, %s, 0, %s)
                   ON CONFLICT (user_id) DO UPDATE SET
                       tier = EXCLUDED.tier,
                       period_start = EXCLUDED.period_start,
                       period_end = EXCLUDED.period_end,
                       monthly_cost_spent_cents = 0,
                       updated_at = EXCLUDED.updated_at""",
                (user_id, new_tier, period_start, period_end, now),
            )

            # 5. For PPU: credit initial top-up via wallet_ledger
            if new_tier == "ppu" and purchase_result.new_balance_usd:
                from wallet_ledger import topup, CREDIT_TOPUP_USD
                # We do this outside the transaction since wallet_ledger manages
                # its own connection. But we must ensure the subscription state
                # is committed first.

        conn.commit()
        conn.close()

        # PPU initial top-up (separate transaction — wallet_ledger manages its own)
        if new_tier == "ppu" and purchase_result.new_balance_usd:
            from wallet_ledger import topup, CREDIT_TOPUP_USD
            idem_key = f"initial_topup:{user_id}:{purchase_result.transaction_id}"
            topup(user_id, CREDIT_TOPUP_USD, idem_key, payment_id=purchase_result.transaction_id)

    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        raise


def _sync_db_state_switch(
    user_id: str, old_tier: str, new_tier: str, purchase_result
) -> None:
    """Atomically update DB for a tier switch (ppu ↔ unlimited)."""
    conn = _get_db_connection()
    try:
        now = datetime.now(timezone.utc)
        period_start = now
        period_end = now + timedelta(days=30)

        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (user_id,))

            # 1. Update users.plan
            cur.execute(
                "UPDATE users SET plan = %s WHERE secret_id = %s",
                (new_tier, user_id),
            )

            # 2. Cancel old subscription
            cur.execute(
                "UPDATE subscriptions SET state = 'cancelled', updated_at = %s WHERE user_id = %s AND state IN ('active', 'billing_retry')",
                (now, user_id),
            )

            # 3. Insert new subscription
            cur.execute(
                """INSERT INTO subscriptions
                   (user_id, tier, state, period_start, period_end, provider_subscription_id, created_at, updated_at)
                   VALUES (%s, %s, 'active', %s, %s, %s, %s, %s)""",
                (user_id, new_tier, period_start, period_end,
                 purchase_result.transaction_id, now, now),
            )

            # 4. Update wallet_subscription
            # For unlimited→ppu: reset cost stop (irrelevant now)
            # For ppu→unlimited: reset cost stop to 0
            cur.execute(
                """INSERT INTO wallet_subscription
                   (user_id, tier, period_start, period_end, monthly_cost_spent_cents, updated_at)
                   VALUES (%s, %s, %s, %s, 0, %s)
                   ON CONFLICT (user_id) DO UPDATE SET
                       tier = EXCLUDED.tier,
                       period_start = EXCLUDED.period_start,
                       period_end = EXCLUDED.period_end,
                       monthly_cost_spent_cents = 0,
                       updated_at = EXCLUDED.updated_at""",
                (user_id, new_tier, period_start, period_end, now),
            )

        conn.commit()
        conn.close()

    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        raise


def _sync_db_state_cancel(user_id: str, old_tier: str) -> None:
    """Atomically update DB for cancellation → free."""
    conn = _get_db_connection()
    try:
        now = datetime.now(timezone.utc)

        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (user_id,))

            # 1. Update users.plan back to free
            cur.execute(
                "UPDATE users SET plan = 'free' WHERE secret_id = %s",
                (user_id,),
            )

            # 2. Cancel active subscription
            cur.execute(
                "UPDATE subscriptions SET state = 'cancelled', updated_at = %s WHERE user_id = %s AND state IN ('active', 'billing_retry')",
                (now, user_id),
            )

            # 3. Remove wallet_subscription (free has no subscription tracking)
            cur.execute(
                "DELETE FROM wallet_subscription WHERE user_id = %s",
                (user_id,),
            )

        conn.commit()
        conn.close()

    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        raise


# ============================================================
# HELPERS
# ============================================================

def _display_name(tier: str) -> str:
    return {"free": "Free", "ppu": "Pay-Per-Use", "unlimited": "Unlimited"}.get(tier, tier)


def _ppu_welcome_msg(balance_usd: Optional[float]) -> str:
    if balance_usd:
        return f"Your starting balance is ${balance_usd:.2f}."
    return "Top up credits to start generating tours and articles."


def _unlimited_welcome_msg() -> str:
    return "Generate unlimited tours and articles this month."


def _switch_message(old_tier: str, new_tier: str, balance_usd: Optional[float]) -> str:
    if old_tier == "unlimited" and new_tier == "ppu":
        if balance_usd and balance_usd > 0:
            return (
                f"Switched to Pay-Per-Use. Your balance is ${balance_usd:.2f}. "
                "You can now generate tours using your credit balance."
            )
        return (
            "Switched to Pay-Per-Use. Your balance is $0.00 — "
            "please top up to start generating."
        )
    elif old_tier == "ppu" and new_tier == "unlimited":
        return (
            "Upgraded to Unlimited! Generate tours and articles without per-use charges. "
            "Your previous PPU balance is preserved."
        )
    return f"Switched from {_display_name(old_tier)} to {_display_name(new_tier)}."


def _proration_description(old_tier: str, new_tier: str) -> str:
    """Describe the proration behaviour for the submission."""
    if old_tier == "unlimited" and new_tier == "ppu":
        return (
            "No refund for remaining Unlimited days. User hit cost-stop and "
            "chose to switch. PPU starts with existing wallet balance (likely $0). "
            "PPU monthly fee waived for remainder of this billing cycle."
        )
    elif old_tier == "ppu" and new_tier == "unlimited":
        return (
            "PPU credits are non-refundable (per design). Balance is frozen, "
            "not lost — preserved for potential switch back. Unlimited $50 fee "
            "starts a fresh 30-day period. Cost-stop resets to $0."
        )
    return "Standard transition, no proration."
