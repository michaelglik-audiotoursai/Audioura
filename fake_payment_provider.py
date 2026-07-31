"""
FakePaymentProvider — Deterministic, scriptable implementation for testing.

Exercises every path: purchase, renewal, expiry, refund/clawback, restore,
low-balance event. Designed so that swapping in RevenueCat later touches
only one file (the real provider that replaces this one).

Usage in tests:
    provider = FakePaymentProvider()
    provider.purchase_subscription("user123", "com.audioura.ppu_monthly")
    provider.record_usage("user123", "tour_generation", 0.069)
    ent = provider.get_entitlement("user123")
    assert ent.tier == SubscriptionTier.PPU
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from dataclasses import dataclass, field

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


# Configuration — matches SUBSCRIBED_DESIGN.md, all runtime-tunable
PRICING_MULTIPLIER = 5.0
PPU_MONTHLY_FEE_USD = 2.00
CREDIT_TOPUP_USD = 10.00
CREDIT_LOW_BALANCE_USD = 2.00
UNLIMITED_MONTHLY_FEE_USD = 50.00
UNLIMITED_COST_STOP_FRACTION = 0.5
CACHE_HIT_COST_USD = 0.00


@dataclass
class UserSubscriptionRecord:
    """In-memory subscription state for one user."""
    user_id: str
    tier: SubscriptionTier = SubscriptionTier.FREE
    state: SubscriptionState = SubscriptionState.ACTIVE
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    provider_subscription_id: Optional[str] = None
    # PPU
    credit_balance_usd: float = 0.0
    # Unlimited
    cost_used_this_period_usd: float = 0.0
    # Ledger
    transactions: List[dict] = field(default_factory=list)
    # Low balance events pending
    pending_low_balance_events: List[LowBalanceEvent] = field(default_factory=list)


class FakePaymentProvider(PaymentProvider):
    """
    In-memory fake payment provider for testing.
    
    Deterministic: no randomness, no timers. Time can be controlled
    via advance_time() for testing renewal/expiry cycles.
    
    Scriptable: inject_webhook() lets tests simulate Apple server events.
    """

    def __init__(self, now: Optional[datetime] = None):
        self._users: Dict[str, UserSubscriptionRecord] = {}
        self._now = now or datetime.utcnow()
        # Restore index: maps provider_subscription_id -> user_id
        self._restore_index: Dict[str, str] = {}

    @property
    def now(self) -> datetime:
        return self._now

    def advance_time(self, delta: timedelta):
        """Advance the fake clock. Use in tests to trigger expirations."""
        self._now = self._now + delta

    def set_time(self, t: datetime):
        """Set the fake clock to a specific time."""
        self._now = t

    def _get_or_create_user(self, user_id: str) -> UserSubscriptionRecord:
        if user_id not in self._users:
            self._users[user_id] = UserSubscriptionRecord(user_id=user_id)
        return self._users[user_id]

    def _txn_id(self) -> str:
        return f"fake_txn_{uuid.uuid4().hex[:12]}"

    def _sub_id(self) -> str:
        return f"fake_sub_{uuid.uuid4().hex[:12]}"

    # --- Interface implementation ---

    def get_entitlement(self, user_id: str) -> Entitlement:
        rec = self._get_or_create_user(user_id)

        # Check if subscription has expired (time-based)
        if rec.tier != SubscriptionTier.FREE and rec.period_end:
            if self._now >= rec.period_end and rec.state == SubscriptionState.ACTIVE:
                rec.state = SubscriptionState.LAPSED

        cost_stop = None
        if rec.tier == SubscriptionTier.UNLIMITED:
            cost_stop = UNLIMITED_MONTHLY_FEE_USD * UNLIMITED_COST_STOP_FRACTION

        return Entitlement(
            user_id=user_id,
            tier=rec.tier,
            state=rec.state,
            period_start=rec.period_start,
            period_end=rec.period_end,
            provider_subscription_id=rec.provider_subscription_id,
            credit_balance_usd=rec.credit_balance_usd if rec.tier == SubscriptionTier.PPU else None,
            cost_used_this_period_usd=rec.cost_used_this_period_usd if rec.tier == SubscriptionTier.UNLIMITED else None,
            cost_stop_usd=cost_stop,
        )

    def purchase_subscription(self, user_id: str, product_id: str) -> PurchaseResult:
        rec = self._get_or_create_user(user_id)
        txn_id = self._txn_id()
        sub_id = self._sub_id()

        if product_id == "com.audioura.ppu_monthly":
            new_tier = SubscriptionTier.PPU
        elif product_id == "com.audioura.unlimited_monthly":
            new_tier = SubscriptionTier.UNLIMITED
        else:
            return PurchaseResult(success=False, error=f"Unknown product: {product_id}")

        rec.tier = new_tier
        rec.state = SubscriptionState.ACTIVE
        rec.period_start = self._now
        rec.period_end = self._now + timedelta(days=30)
        rec.provider_subscription_id = sub_id
        rec.cost_used_this_period_usd = 0.0

        # PPU gets initial credit top-up included
        if new_tier == SubscriptionTier.PPU:
            rec.credit_balance_usd = CREDIT_TOPUP_USD

        self._restore_index[sub_id] = user_id

        rec.transactions.append({
            "type": "subscription_purchase",
            "transaction_id": txn_id,
            "product_id": product_id,
            "tier": new_tier.value,
            "timestamp": self._now.isoformat(),
            "amount_usd": PPU_MONTHLY_FEE_USD if new_tier == SubscriptionTier.PPU else UNLIMITED_MONTHLY_FEE_USD,
        })

        return PurchaseResult(
            success=True,
            transaction_id=txn_id,
            new_tier=new_tier,
            new_balance_usd=rec.credit_balance_usd if new_tier == SubscriptionTier.PPU else None,
        )

    def purchase_consumable(self, user_id: str, product_id: str) -> PurchaseResult:
        rec = self._get_or_create_user(user_id)

        if rec.tier != SubscriptionTier.PPU:
            return PurchaseResult(
                success=False,
                error="Credit top-up only available for Pay-Per-Use subscribers"
            )

        if product_id != "com.audioura.credit_topup_10":
            return PurchaseResult(success=False, error=f"Unknown consumable: {product_id}")

        txn_id = self._txn_id()
        rec.credit_balance_usd += CREDIT_TOPUP_USD

        rec.transactions.append({
            "type": "consumable_purchase",
            "transaction_id": txn_id,
            "product_id": product_id,
            "amount_usd": CREDIT_TOPUP_USD,
            "new_balance_usd": rec.credit_balance_usd,
            "timestamp": self._now.isoformat(),
        })

        # Clear any pending low-balance events since they topped up
        rec.pending_low_balance_events.clear()

        return PurchaseResult(
            success=True,
            transaction_id=txn_id,
            new_balance_usd=rec.credit_balance_usd,
        )

    def restore_purchases(self, user_id: str) -> PurchaseResult:
        rec = self._get_or_create_user(user_id)

        # Look for any active subscription in the restore index
        # In the fake, we simulate restore by checking if the user had a sub before
        for sub_id, original_user_id in self._restore_index.items():
            if original_user_id == user_id:
                # Found a subscription to restore
                original = self._users.get(original_user_id)
                if original and original.state == SubscriptionState.ACTIVE:
                    rec.tier = original.tier
                    rec.state = original.state
                    rec.period_start = original.period_start
                    rec.period_end = original.period_end
                    rec.provider_subscription_id = sub_id
                    rec.credit_balance_usd = original.credit_balance_usd
                    rec.cost_used_this_period_usd = original.cost_used_this_period_usd

                    rec.transactions.append({
                        "type": "restore",
                        "provider_subscription_id": sub_id,
                        "tier": rec.tier.value,
                        "timestamp": self._now.isoformat(),
                    })

                    return PurchaseResult(
                        success=True,
                        transaction_id=self._txn_id(),
                        new_tier=rec.tier,
                        new_balance_usd=rec.credit_balance_usd if rec.tier == SubscriptionTier.PPU else None,
                    )

        return PurchaseResult(success=False, error="No purchases to restore")

    def handle_webhook(self, payload: dict) -> WebhookResult:
        event_type_str = payload.get("event_type")
        user_id = payload.get("user_id")
        
        if not event_type_str or not user_id:
            return WebhookResult(handled=False, details="Missing event_type or user_id")

        try:
            event_type = WebhookEvent(event_type_str)
        except ValueError:
            return WebhookResult(handled=False, details=f"Unknown event type: {event_type_str}")

        rec = self._get_or_create_user(user_id)

        if event_type == WebhookEvent.RENEWAL:
            if rec.tier == SubscriptionTier.FREE:
                return WebhookResult(handled=False, details="Cannot renew free tier")
            rec.state = SubscriptionState.ACTIVE
            rec.period_start = self._now
            rec.period_end = self._now + timedelta(days=30)
            rec.cost_used_this_period_usd = 0.0  # Reset period cost
            rec.transactions.append({
                "type": "renewal",
                "tier": rec.tier.value,
                "timestamp": self._now.isoformat(),
            })
            return WebhookResult(handled=True, event_type=event_type, user_id=user_id, details="Renewed")

        elif event_type == WebhookEvent.EXPIRY:
            rec.state = SubscriptionState.LAPSED
            rec.transactions.append({
                "type": "expiry",
                "tier": rec.tier.value,
                "timestamp": self._now.isoformat(),
            })
            return WebhookResult(handled=True, event_type=event_type, user_id=user_id, details="Expired")

        elif event_type == WebhookEvent.REFUND:
            # Apple grants refunds directly. Record clawback.
            # Balance CAN go negative — design decision per SUBSCRIBED_DESIGN.md.
            refund_amount = payload.get("refund_amount_usd", CREDIT_TOPUP_USD)
            if rec.tier == SubscriptionTier.PPU:
                rec.credit_balance_usd -= refund_amount
            rec.transactions.append({
                "type": "refund_clawback",
                "amount_usd": -refund_amount,
                "resulting_balance_usd": rec.credit_balance_usd,
                "timestamp": self._now.isoformat(),
            })
            return WebhookResult(
                handled=True, event_type=event_type, user_id=user_id,
                details=f"Clawback recorded: -{refund_amount}, balance={rec.credit_balance_usd}"
            )

        elif event_type == WebhookEvent.BILLING_RETRY:
            rec.state = SubscriptionState.BILLING_RETRY
            rec.transactions.append({
                "type": "billing_retry",
                "tier": rec.tier.value,
                "timestamp": self._now.isoformat(),
            })
            return WebhookResult(handled=True, event_type=event_type, user_id=user_id, details="Billing retry")

        elif event_type == WebhookEvent.CANCELLATION:
            rec.state = SubscriptionState.CANCELLED
            rec.transactions.append({
                "type": "cancellation",
                "tier": rec.tier.value,
                "timestamp": self._now.isoformat(),
            })
            return WebhookResult(handled=True, event_type=event_type, user_id=user_id, details="Cancelled")

        return WebhookResult(handled=False, details=f"Unhandled event type: {event_type_str}")

    def get_low_balance_events(self, user_id: str) -> List[LowBalanceEvent]:
        rec = self._get_or_create_user(user_id)
        return list(rec.pending_low_balance_events)

    def record_usage(self, user_id: str, operation_type: str, our_cost_usd: float) -> Optional[LowBalanceEvent]:
        rec = self._get_or_create_user(user_id)

        if rec.tier == SubscriptionTier.FREE:
            # Free tier: no balance tracking (uses quota-based entitlements)
            return None

        user_charge = our_cost_usd * PRICING_MULTIPLIER

        if rec.tier == SubscriptionTier.PPU:
            rec.credit_balance_usd -= user_charge
            rec.transactions.append({
                "type": "usage_debit",
                "operation": operation_type,
                "our_cost_usd": our_cost_usd,
                "user_charge_usd": user_charge,
                "resulting_balance_usd": rec.credit_balance_usd,
                "timestamp": self._now.isoformat(),
            })

            # Check low-balance threshold
            if rec.credit_balance_usd < CREDIT_LOW_BALANCE_USD:
                event = LowBalanceEvent(
                    user_id=user_id,
                    current_balance_usd=rec.credit_balance_usd,
                    threshold_usd=CREDIT_LOW_BALANCE_USD,
                    timestamp=self._now,
                )
                rec.pending_low_balance_events.append(event)
                return event

        elif rec.tier == SubscriptionTier.UNLIMITED:
            rec.cost_used_this_period_usd += our_cost_usd
            rec.transactions.append({
                "type": "usage_track",
                "operation": operation_type,
                "our_cost_usd": our_cost_usd,
                "period_total_usd": rec.cost_used_this_period_usd,
                "timestamp": self._now.isoformat(),
            })

        return None

    # --- Test helpers (not part of the interface) ---

    def get_transactions(self, user_id: str) -> List[dict]:
        """Get full transaction history for a user. Test inspection only."""
        rec = self._get_or_create_user(user_id)
        return list(rec.transactions)

    def get_balance(self, user_id: str) -> float:
        """Get current credit balance. Test helper."""
        rec = self._get_or_create_user(user_id)
        return rec.credit_balance_usd

    def simulate_restore_on_new_device(self, user_id: str) -> PurchaseResult:
        """
        Simulate the user restoring on a new device.
        In a real provider, this queries Apple/RevenueCat for the user's
        subscription tied to their Apple ID.
        """
        return self.restore_purchases(user_id)
