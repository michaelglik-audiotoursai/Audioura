"""
PaymentProvider — Abstract interface for subscription & consumable IAP.

Design of record: SUBSCRIBED_DESIGN.md

This interface covers:
  - Entitlement queries (what plan is the user on, what's their balance)
  - Subscription purchases (ppu, unlimited)
  - Consumable purchases (credit top-ups — explicit user action only)
  - Purchase restoration (device migration)
  - Webhook handling (renewals, expirations, refunds, billing retry)

Apple constraint (non-negotiable):
  Consumables cannot auto-charge. Every credit top-up requires explicit user
  authentication. The interface exposes a low_balance event that triggers a
  REMINDER — never a silent debit.

Swapping in RevenueCat later must touch ONE file (the concrete implementation).
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List


# ─── Shared constants ────────────────────────────────────────────────────────
# Apple billing retry grace period — Apple retries for up to 16 days after
# a failed renewal. Access continues during this window.
# Source: Apple Developer docs "Billing retry" / "Billing Grace Period" (2024).
# This is THE single source of truth — providers and the gate both import it.
BILLING_RETRY_GRACE_DAYS = int(os.environ.get("BILLING_RETRY_GRACE_DAYS", "16"))


class SubscriptionTier(str, Enum):
    FREE = "free"
    PPU = "ppu"          # Pay-Per-Use
    UNLIMITED = "unlimited"


class SubscriptionState(str, Enum):
    ACTIVE = "active"
    LAPSED = "lapsed"        # expired, not renewed
    CANCELLED = "cancelled"  # user cancelled, may still be in grace
    BILLING_RETRY = "billing_retry"  # payment failed, retrying


class WebhookEvent(str, Enum):
    RENEWAL = "renewal"
    EXPIRY = "expiry"
    REFUND = "refund"
    BILLING_RETRY = "billing_retry"
    CANCELLATION = "cancellation"


@dataclass
class Entitlement:
    """Current subscription state for a user."""
    user_id: str
    tier: SubscriptionTier
    state: SubscriptionState
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    provider_subscription_id: Optional[str] = None
    # PPU fields
    credit_balance_usd: Optional[float] = None
    # Unlimited fields
    cost_used_this_period_usd: Optional[float] = None
    cost_stop_usd: Optional[float] = None


@dataclass
class PurchaseResult:
    """Result of a purchase operation."""
    success: bool
    transaction_id: Optional[str] = None
    error: Optional[str] = None
    new_tier: Optional[SubscriptionTier] = None
    new_balance_usd: Optional[float] = None


@dataclass
class WebhookResult:
    """Result of processing a webhook."""
    handled: bool
    event_type: Optional[WebhookEvent] = None
    user_id: Optional[str] = None
    details: Optional[str] = None


@dataclass
class LowBalanceEvent:
    """Emitted when PPU balance drops below threshold. Triggers a REMINDER only."""
    user_id: str
    current_balance_usd: float
    threshold_usd: float
    timestamp: datetime = field(default_factory=datetime.utcnow)


class PaymentProvider(ABC):
    """
    Abstract payment provider interface.
    
    Implementations:
      - FakePaymentProvider (this repo, for testing)
      - RevenueCatProvider (future, one file)
    """

    @abstractmethod
    def get_entitlement(self, user_id: str) -> Entitlement:
        """
        Get the user's current subscription entitlement.
        
        For free users: returns tier=FREE, state=ACTIVE, no period info.
        For PPU: includes credit_balance_usd.
        For Unlimited: includes cost_used_this_period_usd and cost_stop_usd.
        """
        ...

    @abstractmethod
    def purchase_subscription(self, user_id: str, product_id: str) -> PurchaseResult:
        """
        Purchase or upgrade a subscription (ppu or unlimited).
        
        product_id maps to: 'com.audioura.ppu_monthly', 'com.audioura.unlimited_monthly'
        These are auto-renewable subscriptions.
        """
        ...

    @abstractmethod
    def purchase_consumable(self, user_id: str, product_id: str) -> PurchaseResult:
        """
        Purchase a credit top-up (consumable IAP).
        
        Apple constraint: This MUST be triggered by explicit user action with
        authentication. Never call this automatically.
        
        product_id: 'com.audioura.credit_topup_10'
        """
        ...

    @abstractmethod
    def restore_purchases(self, user_id: str) -> PurchaseResult:
        """
        Restore purchases on a new device.
        
        Queries the provider for any active subscriptions associated with
        the user's Apple ID and restores them locally.
        """
        ...

    @abstractmethod
    def handle_webhook(self, payload: dict) -> WebhookResult:
        """
        Handle a server-to-server webhook from the payment provider.
        
        Events:
          - renewal: subscription renewed, extend period
          - expiry: subscription expired, transition to lapsed
          - refund: Apple granted refund, record clawback (balance may go negative)
          - billing_retry: payment failed, mark billing_retry state
        """
        ...

    @abstractmethod
    def get_low_balance_events(self, user_id: str) -> List[LowBalanceEvent]:
        """
        Check if the user has pending low-balance events that need reminders.
        
        This is a QUERY, not an action. The app layer decides how to send
        the reminder (push notification, in-app banner, etc).
        """
        ...

    @abstractmethod
    def record_usage(self, user_id: str, operation_type: str, our_cost_usd: float) -> Optional[LowBalanceEvent]:
        """
        Record a usage event and debit the user's balance (PPU) or track
        cost accumulation (Unlimited).
        
        For PPU: deducts our_cost_usd * PRICING_MULTIPLIER from balance.
                 Returns LowBalanceEvent if balance drops below threshold.
        For Unlimited: adds our_cost_usd to period cost tracker.
                       Returns None (cost stop is checked elsewhere).
        For Free: no-op (free tier has no balance).
        
        operation_type: 'tour_generation', 'news_article', 'translation', etc.
        our_cost_usd: the actual cost to us (NOT the multiplied user price).
        """
        ...
