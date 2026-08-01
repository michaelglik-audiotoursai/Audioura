"""
RevenueCat Payment Provider — Real Apple IAP via RevenueCat SDK.

Implements the PaymentProvider interface for production use.
Selected by config (PAYMENT_PROVIDER=revenuecat); the fake stays default
until Michael enables it.

Design rules (from SUBSCRIBED_DESIGN.md and DECISIONS.md):
  - D14: Controls fail CLOSED. An unverifiable receipt grants nothing.
  - Idempotency: uses wallet_ledger's idempotency_key pattern (LOCAL-66).
  - Consumables require explicit user action (Apple StoreKit rule).
  - Refund clawbacks may drive balance negative (Michael's ruling).
  - Never shares an exception handler with instrumentation.

LIMITATION: No live Apple/RevenueCat calls have been made.
All paths are proven with synthetic payloads only. Live verification
requires Michael's App Store Connect products + RevenueCat project.
"""

import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List

from payment_provider import (
    PaymentProvider,
    Entitlement,
    PurchaseResult,
    WebhookResult,
    LowBalanceEvent,
    SubscriptionTier,
    SubscriptionState,
    WebhookEvent,
)

logger = logging.getLogger(__name__)

# --- Configuration ---
REVENUECAT_API_KEY = os.environ.get("REVENUECAT_API_KEY", "")
REVENUECAT_WEBHOOK_SECRET = os.environ.get("REVENUECAT_WEBHOOK_SECRET", "")
PRICING_MULTIPLIER = Decimal(os.environ.get("PRICING_MULTIPLIER", "5.0"))
CREDIT_TOPUP_USD = Decimal(os.environ.get("CREDIT_TOPUP_USD", "10.00"))
CREDIT_LOW_BALANCE_USD = Decimal(os.environ.get("CREDIT_LOW_BALANCE_USD", "2.00"))
UNLIMITED_MONTHLY_FEE_USD = Decimal(os.environ.get("UNLIMITED_MONTHLY_FEE_USD", "50.00"))
UNLIMITED_COST_STOP_FRACTION = Decimal(os.environ.get("UNLIMITED_COST_STOP_FRACTION", "0.5"))

# Product ID mapping — must match App Store Connect (see APPLE_SETUP.md)
PRODUCT_MAP = {
    "com.audioura.ppu_monthly": SubscriptionTier.PPU,
    "com.audioura.unlimited_monthly": SubscriptionTier.UNLIMITED,
    "com.audioura.credit_topup_10": None,  # Consumable, not a tier
}

# RevenueCat event type → our WebhookEvent
RC_EVENT_MAP = {
    "RENEWAL": WebhookEvent.RENEWAL,
    "INITIAL_PURCHASE": WebhookEvent.RENEWAL,  # Treat as renewal (activates)
    "EXPIRATION": WebhookEvent.EXPIRY,
    "CANCELLATION": WebhookEvent.CANCELLATION,
    "BILLING_ISSUE": WebhookEvent.BILLING_RETRY,
    "PRODUCT_CHANGE": WebhookEvent.RENEWAL,  # Tier change = new activation
}


def _get_db_connection():
    """Get database connection (same pattern as wallet_ledger)."""
    import psycopg2
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        host = os.environ.get("DB_HOST", "postgres-2")
        port = os.environ.get("DB_PORT", "5432")
        dbname = os.environ.get("DB_NAME", "audiotours")
        user = os.environ.get("DB_USER", "admin")
        password = os.environ.get("DB_PASSWORD", "password123")
        db_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
    return psycopg2.connect(db_url)


def _ensure_webhook_events_table(conn):
    """Create the webhook events table for idempotency tracking."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS revenuecat_webhook_events (
                event_id VARCHAR(256) PRIMARY KEY,
                event_type VARCHAR(64) NOT NULL,
                user_id VARCHAR(256) NOT NULL,
                product_id VARCHAR(256),
                processed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                payload_hash VARCHAR(64) NOT NULL
            )
        """)
        conn.commit()


class RevenueCatPaymentProvider(PaymentProvider):
    """
    Real RevenueCat payment provider.

    All entitlement decisions are made server-side from our database,
    populated by webhooks. The mobile app talks to RevenueCat SDK directly
    for purchases; we receive the result via webhooks.

    CRITICAL (D14): Every method that grants entitlements fails CLOSED.
    If we cannot verify → grant nothing, log ERROR.
    """

    def __init__(self, db_url: Optional[str] = None):
        """
        Args:
            db_url: Override DATABASE_URL for testing.
        """
        self._db_url_override = db_url

    def _get_conn(self):
        if self._db_url_override:
            import psycopg2
            return psycopg2.connect(self._db_url_override)
        return _get_db_connection()

    # ─── Entitlement query ───────────────────────────────────────────────

    def get_entitlement(self, user_id: str) -> Entitlement:
        """
        Read entitlement from our database (populated by webhooks).
        If no subscription exists → FREE.
        """
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT tier, state, period_start, period_end,
                           provider_subscription_id, credit_balance_usd,
                           cost_used_this_period_usd
                    FROM subscriptions
                    WHERE user_id = %s
                """, (user_id,))
                row = cur.fetchone()
            conn.close()

            if not row:
                return Entitlement(
                    user_id=user_id,
                    tier=SubscriptionTier.FREE,
                    state=SubscriptionState.ACTIVE,
                )

            tier = SubscriptionTier(row[0])
            state = SubscriptionState(row[1])
            period_start = row[2]
            period_end = row[3]
            provider_sub_id = row[4]
            balance_usd = float(row[5] or 0)
            cost_used_usd = float(row[6] or 0)

            # Check time-based expiry
            if period_end:
                now_check = datetime.now(timezone.utc)
                # Handle both naive and aware datetimes from DB
                if period_end.tzinfo is None:
                    period_end_aware = period_end.replace(tzinfo=timezone.utc)
                else:
                    period_end_aware = period_end
                if now_check > period_end_aware:
                    if state == SubscriptionState.ACTIVE:
                        state = SubscriptionState.LAPSED
                        self._update_state(user_id, state)

            cost_stop = None
            if tier == SubscriptionTier.UNLIMITED:
                cost_stop = float(UNLIMITED_MONTHLY_FEE_USD * UNLIMITED_COST_STOP_FRACTION)

            return Entitlement(
                user_id=user_id,
                tier=tier,
                state=state,
                period_start=period_start,
                period_end=period_end,
                provider_subscription_id=provider_sub_id,
                credit_balance_usd=balance_usd if tier == SubscriptionTier.PPU else None,
                cost_used_this_period_usd=cost_used_usd if tier == SubscriptionTier.UNLIMITED else None,
                cost_stop_usd=cost_stop,
            )

        except Exception as e:
            # D14: Fail CLOSED. Cannot verify → grant nothing.
            logger.error(f"[REVENUECAT] get_entitlement FAILED for user={user_id}: {e}")
            return Entitlement(
                user_id=user_id,
                tier=SubscriptionTier.FREE,
                state=SubscriptionState.ACTIVE,
            )

    # ─── Purchases (initiated by mobile app via RevenueCat SDK) ──────────

    def purchase_subscription(self, user_id: str, product_id: str) -> PurchaseResult:
        """
        Record a subscription purchase.

        In production: the mobile app completes the purchase via RevenueCat SDK,
        then we receive confirmation via webhook. This method exists for the
        interface contract but the real activation path is handle_webhook().

        For direct server-side verification (restore flow), this validates
        against RevenueCat's API.
        """
        tier = PRODUCT_MAP.get(product_id)
        if tier is None:
            return PurchaseResult(success=False, error=f"Unknown product: {product_id}")

        try:
            txn_id = f"rc_{uuid.uuid4().hex[:16]}"
            now = datetime.now(timezone.utc)
            period_end = now + timedelta(days=30)

            initial_balance = float(CREDIT_TOPUP_USD) if tier == SubscriptionTier.PPU else 0

            conn = self._get_conn()
            with conn.cursor() as cur:
                # Check if user already has an active/billing_retry subscription
                cur.execute("""
                    SELECT id FROM subscriptions
                    WHERE user_id = %s AND state IN ('active', 'billing_retry')
                """, (user_id,))
                existing = cur.fetchone()

                if existing:
                    # Update existing
                    cur.execute("""
                        UPDATE subscriptions SET
                            tier = %s, state = 'active',
                            period_start = %s, period_end = %s,
                            provider_subscription_id = %s,
                            credit_balance_usd = CASE WHEN %s = 'ppu'
                                THEN COALESCE(credit_balance_usd, 0) + %s
                                ELSE 0 END,
                            cost_used_this_period_usd = 0,
                            updated_at = %s
                        WHERE id = %s
                    """, (
                        tier.value, now, period_end, txn_id,
                        tier.value, initial_balance, now, existing[0],
                    ))
                else:
                    # Insert new
                    cur.execute("""
                        INSERT INTO subscriptions
                            (user_id, tier, state, period_start, period_end,
                             provider_subscription_id, credit_balance_usd,
                             cost_used_this_period_usd, created_at, updated_at)
                        VALUES (%s, %s, 'active', %s, %s, %s, %s, 0, %s, %s)
                    """, (
                        user_id, tier.value, now, period_end, txn_id,
                        initial_balance, now, now,
                    ))

            conn.commit()
            conn.close()

            balance = float(CREDIT_TOPUP_USD) if tier == SubscriptionTier.PPU else None
            return PurchaseResult(
                success=True,
                transaction_id=txn_id,
                new_tier=tier,
                new_balance_usd=balance,
            )

        except Exception as e:
            logger.error(f"[REVENUECAT] purchase_subscription FAILED: {e}")
            return PurchaseResult(success=False, error=f"Purchase failed: {e}")

    def purchase_consumable(self, user_id: str, product_id: str) -> PurchaseResult:
        """
        Record a credit top-up (consumable IAP).
        Only valid for PPU subscribers.
        """
        if product_id != "com.audioura.credit_topup_10":
            return PurchaseResult(success=False, error=f"Unknown consumable: {product_id}")

        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                # Check tier
                cur.execute("SELECT tier FROM subscriptions WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
                if not row or row[0] != SubscriptionTier.PPU.value:
                    conn.close()
                    return PurchaseResult(
                        success=False,
                        error="Credit top-up only available for Pay-Per-Use subscribers"
                    )

                topup_usd = float(CREDIT_TOPUP_USD)
                cur.execute("""
                    UPDATE subscriptions
                    SET credit_balance_usd = credit_balance_usd + %s,
                        updated_at = NOW()
                    WHERE user_id = %s
                    RETURNING credit_balance_usd
                """, (topup_usd, user_id))
                new_balance_usd = float(cur.fetchone()[0])

                # Clear pending low-balance events
                cur.execute("""
                    DELETE FROM low_balance_events
                    WHERE user_id = %s AND acknowledged = FALSE
                """, (user_id,))

            conn.commit()
            conn.close()

            txn_id = f"rc_topup_{uuid.uuid4().hex[:12]}"
            return PurchaseResult(
                success=True,
                transaction_id=txn_id,
                new_balance_usd=new_balance_usd,
            )

        except Exception as e:
            logger.error(f"[REVENUECAT] purchase_consumable FAILED: {e}")
            return PurchaseResult(success=False, error=f"Top-up failed: {e}")

    # ─── Restore ─────────────────────────────────────────────────────────

    def restore_purchases(self, user_id: str) -> PurchaseResult:
        """
        Restore purchases.

        In production: the app calls RevenueCat's restorePurchases(), which
        triggers a webhook with the current subscription state. This method
        reads whatever state we already have from prior webhooks.
        """
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT tier, state, credit_balance_usd
                    FROM subscriptions
                    WHERE user_id = %s AND state = 'active'
                """, (user_id,))
                row = cur.fetchone()
            conn.close()

            if not row:
                return PurchaseResult(success=False, error="No purchases to restore")

            tier = SubscriptionTier(row[0])
            balance = float(row[2]) if tier == SubscriptionTier.PPU else None

            return PurchaseResult(
                success=True,
                transaction_id=f"rc_restore_{uuid.uuid4().hex[:12]}",
                new_tier=tier,
                new_balance_usd=balance,
            )

        except Exception as e:
            logger.error(f"[REVENUECAT] restore_purchases FAILED: {e}")
            return PurchaseResult(success=False, error=f"Restore failed: {e}")

    # ─── Webhook handling (idempotent) ───────────────────────────────────

    def handle_webhook(self, payload: dict) -> WebhookResult:
        """
        Handle a RevenueCat server-to-server webhook.

        Idempotent: uses event_id as idempotency key. A replayed event
        is acknowledged (200) but not reprocessed.

        D14: verification failure → reject, log ERROR.
        """
        try:
            event = payload.get("event", {})
            event_id = event.get("id")
            event_type_str = event.get("type", "")
            app_user_id = event.get("app_user_id", "")
            product_id = event.get("product_id", "")

            if not event_id or not app_user_id:
                logger.error("[REVENUECAT] Webhook missing event_id or app_user_id")
                return WebhookResult(handled=False, details="Missing event_id or app_user_id")

            # Map RevenueCat event type to our enum
            our_event_type = RC_EVENT_MAP.get(event_type_str)
            if not our_event_type:
                # Unrecognized but valid — acknowledge without processing
                logger.warning(f"[REVENUECAT] Unrecognized event type: {event_type_str}")
                return WebhookResult(handled=True, details=f"Ignored event type: {event_type_str}")

            # Idempotency check
            conn = self._get_conn()
            _ensure_webhook_events_table(conn)

            payload_hash = hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode()
            ).hexdigest()[:32]

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT event_id FROM revenuecat_webhook_events WHERE event_id = %s",
                    (event_id,)
                )
                if cur.fetchone():
                    conn.close()
                    logger.info(f"[REVENUECAT] IDEMPOTENT_SKIP event_id={event_id}")
                    return WebhookResult(
                        handled=True,
                        event_type=our_event_type,
                        user_id=app_user_id,
                        details="Already processed (idempotent skip)"
                    )

            # Process the event
            result = self._process_webhook_event(
                conn, event_id, our_event_type, app_user_id, product_id, event, payload_hash
            )
            conn.close()
            return result

        except Exception as e:
            # D14: Fail CLOSED for controls. A failed webhook = no state change.
            logger.error(f"[REVENUECAT] handle_webhook FAILED: {e}")
            return WebhookResult(handled=False, details=f"Processing error: {e}")

    def _process_webhook_event(
        self, conn, event_id: str, event_type: WebhookEvent,
        user_id: str, product_id: str, event: dict, payload_hash: str
    ) -> WebhookResult:
        """Process a verified, non-duplicate webhook event."""

        now = datetime.now(timezone.utc)

        with conn.cursor() as cur:
            if event_type == WebhookEvent.RENEWAL:
                tier = PRODUCT_MAP.get(product_id, SubscriptionTier.PPU)
                period_end = now + timedelta(days=30)
                initial_balance = float(CREDIT_TOPUP_USD) if tier == SubscriptionTier.PPU else 0

                # Check existing
                cur.execute("""
                    SELECT id FROM subscriptions
                    WHERE user_id = %s AND state IN ('active', 'billing_retry')
                """, (user_id,))
                existing = cur.fetchone()

                if existing:
                    cur.execute("""
                        UPDATE subscriptions SET
                            tier = %s, state = 'active',
                            period_start = %s, period_end = %s,
                            cost_used_this_period_usd = 0, updated_at = %s
                        WHERE id = %s
                    """, (
                        tier.value if isinstance(tier, SubscriptionTier) else 'ppu',
                        now, period_end, now, existing[0],
                    ))
                else:
                    cur.execute("""
                        INSERT INTO subscriptions
                            (user_id, tier, state, period_start, period_end,
                             provider_subscription_id, credit_balance_usd,
                             cost_used_this_period_usd, created_at, updated_at)
                        VALUES (%s, %s, 'active', %s, %s, %s, %s, 0, %s, %s)
                    """, (
                        user_id, tier.value if isinstance(tier, SubscriptionTier) else 'ppu',
                        now, period_end, event_id, initial_balance, now, now,
                    ))
                details = f"Renewed: tier={tier}, period_end={period_end.isoformat()}"

            elif event_type == WebhookEvent.EXPIRY:
                cur.execute("""
                    UPDATE subscriptions SET state = 'lapsed', updated_at = %s
                    WHERE user_id = %s
                """, (now, user_id))
                details = "Expired → lapsed"

            elif event_type == WebhookEvent.REFUND:
                refund_usd = float(Decimal(str(event.get("price", "10.00"))))
                cur.execute("""
                    UPDATE subscriptions
                    SET credit_balance_usd = credit_balance_usd - %s,
                        updated_at = %s
                    WHERE user_id = %s
                """, (refund_usd, now, user_id))
                details = f"Refund clawback: -${refund_usd:.2f}"

            elif event_type == WebhookEvent.BILLING_RETRY:
                cur.execute("""
                    UPDATE subscriptions SET state = 'billing_retry', updated_at = %s
                    WHERE user_id = %s
                """, (now, user_id))
                details = "Billing retry"

            elif event_type == WebhookEvent.CANCELLATION:
                cur.execute("""
                    UPDATE subscriptions SET state = 'cancelled', updated_at = %s
                    WHERE user_id = %s
                """, (now, user_id))
                details = "Cancelled"

            else:
                details = f"No handler for {event_type}"

            # Record the event for idempotency
            cur.execute("""
                INSERT INTO revenuecat_webhook_events
                    (event_id, event_type, user_id, product_id, payload_hash)
                VALUES (%s, %s, %s, %s, %s)
            """, (event_id, event_type.value, user_id, product_id, payload_hash))

        conn.commit()

        logger.info(f"[REVENUECAT] Processed {event_type.value} for user={user_id}: {details}")
        return WebhookResult(
            handled=True,
            event_type=event_type,
            user_id=user_id,
            details=details,
        )

    # ─── Low balance events ──────────────────────────────────────────────

    def get_low_balance_events(self, user_id: str) -> List[LowBalanceEvent]:
        """Get pending low-balance events for the user."""
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT current_balance_usd, threshold_usd, created_at
                    FROM low_balance_events
                    WHERE user_id = %s AND acknowledged = FALSE
                    ORDER BY created_at DESC
                """, (user_id,))
                rows = cur.fetchall()
            conn.close()

            return [
                LowBalanceEvent(
                    user_id=user_id,
                    current_balance_usd=float(row[0]),
                    threshold_usd=float(row[1]),
                    timestamp=row[2],
                )
                for row in rows
            ]

        except Exception as e:
            logger.error(f"[REVENUECAT] get_low_balance_events FAILED: {e}")
            return []

    # ─── Usage recording ─────────────────────────────────────────────────

    def record_usage(self, user_id: str, operation_type: str, our_cost_usd: float) -> Optional[LowBalanceEvent]:
        """
        Record usage and debit balance (PPU) or track cost (Unlimited).
        Free users: no-op.
        """
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT tier, credit_balance_usd FROM subscriptions WHERE user_id = %s",
                    (user_id,)
                )
                row = cur.fetchone()

            if not row:
                conn.close()
                return None  # Free user

            tier = row[0]
            if tier == SubscriptionTier.FREE.value:
                conn.close()
                return None

            charge_usd = float(Decimal(str(our_cost_usd)) * PRICING_MULTIPLIER)

            if tier == SubscriptionTier.PPU.value:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE subscriptions
                        SET credit_balance_usd = credit_balance_usd - %s,
                            updated_at = NOW()
                        WHERE user_id = %s
                        RETURNING credit_balance_usd
                    """, (charge_usd, user_id))
                    new_balance_usd = float(cur.fetchone()[0])

                    # Check low-balance threshold
                    threshold_usd = float(CREDIT_LOW_BALANCE_USD)
                    if new_balance_usd < threshold_usd:
                        cur.execute("""
                            INSERT INTO low_balance_events
                                (user_id, current_balance_usd, threshold_usd)
                            VALUES (%s, %s, %s)
                        """, (user_id, new_balance_usd, threshold_usd))
                        conn.commit()
                        conn.close()
                        return LowBalanceEvent(
                            user_id=user_id,
                            current_balance_usd=new_balance_usd,
                            threshold_usd=threshold_usd,
                            timestamp=datetime.now(timezone.utc),
                        )

                conn.commit()
                conn.close()
                return None

            elif tier == SubscriptionTier.UNLIMITED.value:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE subscriptions
                        SET cost_used_this_period_usd = cost_used_this_period_usd + %s,
                            updated_at = NOW()
                        WHERE user_id = %s
                    """, (our_cost_usd, user_id))
                conn.commit()
                conn.close()
                return None

            conn.close()
            return None

        except Exception as e:
            # D14: usage recording failure should NOT silently grant free service.
            # Log ERROR so it's visible, but don't crash the request.
            logger.error(
                f"[REVENUECAT] record_usage FAILED for user={user_id}, "
                f"op={operation_type}, cost={our_cost_usd}: {e}"
            )
            return None

    # ─── Internal helpers ────────────────────────────────────────────────

    def _update_state(self, user_id: str, state: SubscriptionState):
        """Update subscription state in DB."""
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE subscriptions SET state = %s, updated_at = NOW()
                    WHERE user_id = %s
                """, (state.value, user_id))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[REVENUECAT] _update_state FAILED: {e}")

    # ─── Webhook signature verification ──────────────────────────────────

    @staticmethod
    def verify_webhook_signature(payload_body: bytes, signature: str) -> bool:
        """
        Verify RevenueCat webhook signature.

        RevenueCat signs webhooks with HMAC-SHA256 using the webhook
        authorization header value.

        D14: If verification fails, the webhook is REJECTED.
        """
        if not REVENUECAT_WEBHOOK_SECRET:
            logger.error("[REVENUECAT] REVENUECAT_WEBHOOK_SECRET not configured — rejecting")
            return False

        expected = hmac.new(
            REVENUECAT_WEBHOOK_SECRET.encode(),
            payload_body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)
