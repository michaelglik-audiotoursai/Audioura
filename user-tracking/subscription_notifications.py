"""
subscription_notifications.py — LOCAL-807: AUTO-RENEWING subscription lifecycle
for the user-api (Apple App Store Server Notifications v2, Google RTDN), and the
entitlement mapping an active subscription drives.

WHERE THE ONE-TIME PURCHASE PATH ENDS AND THIS BEGINS
-----------------------------------------------------
entitlements_api.verify_purchase / _google_verify handle CONSUMABLE one-time
products (packs, tours, the day pass). An AUTO-RENEWING subscription is a
different lifecycle: the store tells the SERVER about renewals, failures, grace
periods, refunds and cancellations through SERVER NOTIFICATIONS, long after the
original purchase. This module owns that lifecycle:

  • Apple App Store Server Notifications v2 (ASSN v2): a POST whose body is
    {"signedPayload": "<JWS>"}. The JWS payload carries notificationType,
    subtype, notificationUUID and a `data` object with nested
    signedTransactionInfo / signedRenewalInfo JWS. We verify every JWS against
    the SAME pinned Apple Root CA G3 as the purchase path
    (apple_jws_verifier.verify_and_decode_jws), so a forged notification is
    rejected exactly like a forged transaction.

  • Google Real-time developer notifications (RTDN): a Pub/Sub push whose body is
    {"message": {"data": "<base64 JSON>", "messageId": ...}}. The JSON carries a
    subscriptionNotification with a notificationType and a purchaseToken. The
    authoritative state comes from purchases.subscriptionsv2.get (added to
    google_play_verifier). GATED behind GOOGLE_SUBS_ENABLED — code + tests land
    now, live only after the audioura-play-verify permission (403) is fixed.

IDEMPOTENCY
-----------
Stores re-deliver on any non-2xx, and Pub/Sub is at-least-once, so every event
MUST be applied at most once. We dedupe by the notification's UNIQUE id
(Apple notificationUUID / Google messageId) in subscription_notifications
(migration 060), and the subscription row itself is keyed by the store's
ORIGINAL transaction id / purchase token. Applying the same event twice is a
no-op.

ENTITLEMENT MAPPING (D733 §4)
-----------------------------
An ACTIVE (or in-grace) subscription maps the device to its level
(plans.store_product_id -> plan_id, with tours_per_month / tours_per_week set in
the DB). The existing allowance code then gates exactly as for any level. When
the subscription expires/revokes/refunds, the device drops back to the
`previous_level` captured when the subscription first became active.

This module is DB-light and PURE where it can be: the notification PARSING and
the type->effect MAPPING are pure functions (unit-tested with no DB and no
network); only apply_* touch the DB through an injected cursor.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any

logger = logging.getLogger(__name__)


# ───────────────────────────────────────────────────────────────────────────
# Lifecycle status model — the six states migration 060 allows.
# ───────────────────────────────────────────────────────────────────────────
STATUS_ACTIVE = 'active'
STATUS_GRACE = 'grace'
STATUS_BILLING_RETRY = 'billing_retry'
STATUS_EXPIRED = 'expired'
STATUS_REVOKED = 'revoked'
STATUS_REFUNDED = 'refunded'

# The statuses that GRANT the subscription level (the device is entitled).
ENTITLING_STATUSES = frozenset({STATUS_ACTIVE, STATUS_GRACE, STATUS_BILLING_RETRY})


class SubscriptionNotificationError(Exception):
    """A notification could not be processed. `.code` is stable for the HTTP
    layer and tests; `.http_status` is the status the endpoint should return
    (400 for a malformed body, 401/403 for a verification failure so the store
    does NOT keep re-delivering a forged one, 503 when unconfigured)."""

    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.http_status = http_status


@dataclass
class SubscriptionEvent:
    """The normalised result of parsing+verifying one store notification. Store-
    agnostic: both the Apple and Google paths produce this shape, so apply_event
    is written once."""
    store: str
    notification_uuid: str
    notification_type: str
    target_status: str
    original_transaction_id: str
    product_id: Optional[str] = None
    period_end: Optional[datetime] = None
    auto_renew: Optional[bool] = None
    event_at: Optional[datetime] = None
    raw_summary: dict = field(default_factory=dict)


# ───────────────────────────────────────────────────────────────────────────
# Apple ASSN v2 — notificationType/subtype -> target lifecycle status.
# Pure mapping (D733 §2: SUBSCRIBED, DID_RENEW, DID_FAIL_TO_RENEW,
# GRACE_PERIOD_EXPIRED, EXPIRED, REFUND, REVOKE, DID_CHANGE_RENEWAL_STATUS).
# Returns (target_status, auto_renew_override) — auto_renew_override is None
# when the event does not change the renewal flag.
# ───────────────────────────────────────────────────────────────────────────
def apple_type_to_status(notification_type: str,
                         subtype: Optional[str]) -> tuple[str, Optional[bool]]:
    nt = (notification_type or '').upper()
    st = (subtype or '').upper()

    if nt == 'SUBSCRIBED':
        return STATUS_ACTIVE, True
    if nt == 'DID_RENEW':
        # A successful renewal (possibly recovering from billing retry).
        return STATUS_ACTIVE, True
    if nt == 'DID_FAIL_TO_RENEW':
        # GRACE_PERIOD subtype: still entitled during grace; otherwise the
        # subscription has entered billing retry (still entitled per Apple until
        # it finally expires, but flagged).
        if st == 'GRACE_PERIOD':
            return STATUS_GRACE, None
        return STATUS_BILLING_RETRY, None
    if nt == 'GRACE_PERIOD_EXPIRED':
        return STATUS_EXPIRED, False
    if nt == 'EXPIRED':
        return STATUS_EXPIRED, False
    if nt == 'REFUND':
        return STATUS_REFUNDED, False
    if nt == 'REVOKE':
        return STATUS_REVOKED, False
    if nt == 'DID_CHANGE_RENEWAL_STATUS':
        # AUTO_RENEW_DISABLED / _ENABLED — the user toggled renewal; still
        # entitled until period_end, only the flag changes.
        if st == 'AUTO_RENEW_DISABLED':
            return STATUS_ACTIVE, False
        if st == 'AUTO_RENEW_ENABLED':
            return STATUS_ACTIVE, True
        return STATUS_ACTIVE, None
    if nt in ('DID_CHANGE_RENEWAL_PREF', 'PRICE_INCREASE', 'RENEWAL_EXTENDED',
              'OFFER_REDEEMED'):
        # Still entitled; these do not change the entitling state on their own.
        return STATUS_ACTIVE, None
    # Unknown/other notification type: do not change entitlement.
    raise SubscriptionNotificationError(
        'apple_unhandled_type',
        f'Unhandled Apple notificationType {notification_type!r}.',
        http_status=200)  # 200 so Apple does not re-deliver endlessly.


def _epoch_ms_to_dt(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    try:
        return datetime.fromtimestamp(float(raw) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def parse_apple_notification(body: dict, root_ca_pem: bytes,
                             expected_bundle_id: str,
                             verify_fn=None) -> SubscriptionEvent:
    """Parse + VERIFY an Apple ASSN v2 notification body into a SubscriptionEvent.

    body: the POSTed JSON, {"signedPayload": "<JWS>"}.
    root_ca_pem: the pinned Apple Root CA G3 PEM (same one the purchase path pins).
    expected_bundle_id: the app bundle id; the transaction bundleId must match.
    verify_fn: injectable JWS verifier (default apple_jws_verifier.
        verify_and_decode_jws) so tests sign with a test key + test root.

    Raises SubscriptionNotificationError on any malformed/forged input.
    """
    if verify_fn is None:
        from apple_jws_verifier import verify_and_decode_jws as verify_fn  # type: ignore

    if not isinstance(body, dict) or not body.get('signedPayload'):
        raise SubscriptionNotificationError(
            'apple_no_signed_payload', 'Body has no signedPayload.', 400)

    try:
        from apple_jws_verifier import JwsVerificationError
    except Exception:  # pragma: no cover
        JwsVerificationError = Exception  # type: ignore

    try:
        payload = verify_fn(body['signedPayload'], root_ca_pem)
    except JwsVerificationError as e:
        # A forged/garbled notification — reject so Apple surfaces the failure,
        # but with 401 (not 5xx) because the content, not our server, is at fault.
        raise SubscriptionNotificationError(
            f'apple_jws_{getattr(e, "code", "invalid")}',
            f'signedPayload failed verification: {e}', 401)

    notification_type = payload.get('notificationType')
    subtype = payload.get('subtype')
    notification_uuid = payload.get('notificationUUID')
    if not notification_uuid:
        raise SubscriptionNotificationError(
            'apple_no_uuid', 'Notification has no notificationUUID.', 400)

    data = payload.get('data') or {}
    signed_txn = data.get('signedTransactionInfo')
    signed_renewal = data.get('signedRenewalInfo')

    txn_info = {}
    if signed_txn:
        try:
            txn_info = verify_fn(signed_txn, root_ca_pem)
        except JwsVerificationError as e:
            raise SubscriptionNotificationError(
                f'apple_txn_jws_{getattr(e, "code", "invalid")}',
                f'signedTransactionInfo failed verification: {e}', 401)
        # The transaction bundleId must match ours — a notification for another
        # app must never touch our subscriptions.
        bundle = txn_info.get('bundleId')
        if bundle and bundle != expected_bundle_id:
            raise SubscriptionNotificationError(
                'apple_bundle_mismatch',
                f"notification bundleId {bundle!r} != {expected_bundle_id!r}.",
                401)

    renewal_info = {}
    if signed_renewal:
        try:
            renewal_info = verify_fn(signed_renewal, root_ca_pem)
        except JwsVerificationError as e:
            raise SubscriptionNotificationError(
                f'apple_renewal_jws_{getattr(e, "code", "invalid")}',
                f'signedRenewalInfo failed verification: {e}', 401)

    original_txn_id = (txn_info.get('originalTransactionId')
                       or renewal_info.get('originalTransactionId'))
    if not original_txn_id:
        raise SubscriptionNotificationError(
            'apple_no_original_txn', 'No originalTransactionId in notification.', 400)

    target_status, auto_renew_override = apple_type_to_status(
        notification_type, subtype)

    # auto_renew: an explicit renewal-status override wins; else the renewalInfo
    # autoRenewStatus (1 on / 0 off) when present.
    auto_renew = auto_renew_override
    if auto_renew is None and 'autoRenewStatus' in renewal_info:
        auto_renew = bool(renewal_info.get('autoRenewStatus'))

    period_end = _epoch_ms_to_dt(txn_info.get('expiresDate'))
    event_at = _epoch_ms_to_dt(payload.get('signedDate')) or datetime.now(timezone.utc)

    return SubscriptionEvent(
        store='apple',
        notification_uuid=str(notification_uuid),
        notification_type=str(notification_type),
        target_status=target_status,
        original_transaction_id=str(original_txn_id),
        product_id=txn_info.get('productId'),
        period_end=period_end,
        auto_renew=auto_renew,
        event_at=event_at,
        raw_summary={
            'notificationType': notification_type,
            'subtype': subtype,
            'productId': txn_info.get('productId'),
        },
    )


# ───────────────────────────────────────────────────────────────────────────
# Google RTDN — subscriptionNotification.notificationType -> target status.
# (Google's enum, v2: 1 RECOVERED, 2 RENEWED, 3 CANCELED, 4 PURCHASED,
#  5 ON_HOLD, 6 IN_GRACE_PERIOD, 7 RESTARTED, 10 PAUSED, 12 REVOKED, 13 EXPIRED.)
# Pure mapping.
# ───────────────────────────────────────────────────────────────────────────
GOOGLE_TYPE_TO_STATUS = {
    1: STATUS_ACTIVE,          # SUBSCRIPTION_RECOVERED
    2: STATUS_ACTIVE,          # SUBSCRIPTION_RENEWED
    3: STATUS_ACTIVE,          # SUBSCRIPTION_CANCELED (still entitled until end)
    4: STATUS_ACTIVE,          # SUBSCRIPTION_PURCHASED
    5: STATUS_BILLING_RETRY,   # SUBSCRIPTION_ON_HOLD
    6: STATUS_GRACE,           # SUBSCRIPTION_IN_GRACE_PERIOD
    7: STATUS_ACTIVE,          # SUBSCRIPTION_RESTARTED
    12: STATUS_REVOKED,        # SUBSCRIPTION_REVOKED
    13: STATUS_EXPIRED,        # SUBSCRIPTION_EXPIRED
}


def parse_google_rtdn(body: dict, api_client=None,
                      package_name: Optional[str] = None) -> SubscriptionEvent:
    """Parse a Google RTDN push body into a SubscriptionEvent, fetching the
    authoritative state from purchases.subscriptionsv2.get.

    body: {"message": {"data": "<base64 JSON>", "messageId": "..."}}.
    api_client: an object with get_subscription_v2(package_name, token) -> dict
        (google_play_verifier.GooglePlayApiClient). Injected so tests mock it.
    """
    if not isinstance(body, dict):
        raise SubscriptionNotificationError('google_bad_body', 'Body is not an object.', 400)
    message = body.get('message')
    if not isinstance(message, dict) or not message.get('data'):
        raise SubscriptionNotificationError(
            'google_no_message_data', 'RTDN body has no message.data.', 400)

    message_id = message.get('messageId') or message.get('message_id')
    if not message_id:
        raise SubscriptionNotificationError(
            'google_no_message_id', 'RTDN message has no messageId.', 400)

    try:
        decoded = json.loads(base64.b64decode(message['data']).decode('utf-8'))
    except Exception as e:
        raise SubscriptionNotificationError(
            'google_bad_data', f'Could not decode message.data: {e}', 400)

    sub_note = decoded.get('subscriptionNotification')
    if not isinstance(sub_note, dict):
        # Test / voided / one-time notifications are not subscription events.
        raise SubscriptionNotificationError(
            'google_not_subscription', 'No subscriptionNotification in RTDN.', 200)

    ntype = sub_note.get('notificationType')
    purchase_token = sub_note.get('purchaseToken')
    product_id = sub_note.get('subscriptionId')
    if not purchase_token:
        raise SubscriptionNotificationError(
            'google_no_token', 'subscriptionNotification has no purchaseToken.', 400)

    target_status = GOOGLE_TYPE_TO_STATUS.get(ntype)
    if target_status is None:
        raise SubscriptionNotificationError(
            'google_unhandled_type',
            f'Unhandled Google notificationType {ntype!r}.', 200)

    period_end = None
    auto_renew = None
    if api_client is not None:
        try:
            state = api_client.get_subscription_v2(package_name, purchase_token)
        except Exception as e:  # noqa: BLE001
            raise SubscriptionNotificationError(
                'google_subs_get_failed',
                f'subscriptionsv2.get failed: {e}', 502)
        # subscriptionsv2 shape: lineItems[].expiryTime (RFC3339), and the
        # top-level subscriptionState / canceled info.
        line_items = state.get('lineItems') or []
        if line_items:
            expiry = line_items[0].get('expiryTime')
            period_end = _parse_rfc3339(expiry)
            if not product_id:
                product_id = line_items[0].get('productId')
        ss = state.get('subscriptionState')
        auto_renew = ss not in ('SUBSCRIPTION_STATE_CANCELED',
                                'SUBSCRIPTION_STATE_EXPIRED')

    return SubscriptionEvent(
        store='google',
        notification_uuid=str(message_id),
        notification_type=f'google_{ntype}',
        target_status=target_status,
        original_transaction_id=str(purchase_token),
        product_id=product_id,
        period_end=period_end,
        auto_renew=auto_renew,
        event_at=datetime.now(timezone.utc),
        raw_summary={'notificationType': ntype, 'subscriptionId': product_id},
    )


def _parse_rfc3339(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        v = value.replace('Z', '+00:00')
        return datetime.fromisoformat(v)
    except (TypeError, ValueError):
        return None


# ───────────────────────────────────────────────────────────────────────────
# Entitlement effect: product id -> plan level (read from the DB — data, not a
# code map), and the device level the subscription should drive right now.
# ───────────────────────────────────────────────────────────────────────────
def level_for_store_product(cur, store_product_id: str) -> Optional[str]:
    """plans.store_product_id -> plan_id (migration 060). Returns None if no
    plan row claims this store product (an unknown/other product)."""
    if not store_product_id:
        return None
    cur.execute(
        "SELECT plan_id FROM plans WHERE store_product_id = %s LIMIT 1",
        (store_product_id,))
    row = cur.fetchone()
    return row[0] if row else None


def effective_level(cur, user_id: str, now: Optional[datetime] = None) -> Optional[str]:
    """The level the device's auto-renew subscription grants RIGHT NOW, or None
    if it has no entitling subscription. A row grants its level while its status
    is entitling (active/grace/billing_retry) AND its period_end is in the
    future (or unset). The most-recently-ending entitling subscription wins when
    a device somehow has more than one."""
    now = now or datetime.now(timezone.utc)
    cur.execute("""
        SELECT level, status, period_end
        FROM auto_renew_subscriptions
        WHERE user_id = %s
        ORDER BY period_end DESC NULLS LAST
    """, (user_id,))
    for level, status, period_end in cur.fetchall():
        if status not in ENTITLING_STATUSES:
            continue
        if period_end is not None:
            pe = period_end if period_end.tzinfo else period_end.replace(tzinfo=timezone.utc)
            if pe < now:
                continue
        return level
    return None


def apply_event(cur, event: SubscriptionEvent, user_id_hint: Optional[str] = None,
                now: Optional[datetime] = None) -> dict:
    """Apply a verified SubscriptionEvent to the DB, idempotently.

    Returns a small dict describing what happened (for the HTTP response and
    tests): {applied: bool, duplicate: bool, status, level, user_id}.

    Idempotency: if the notification uuid is already recorded, this is a no-op
    (duplicate=True). Otherwise it records the notification, upserts the
    auto_renew_subscriptions row (keyed on original_transaction_id), and — when
    the device is known — updates device_entitlement to the subscription level
    while entitling, or back to previous_level on expiry/revoke/refund.

    `user_id_hint` resolves the device for a brand-new subscription (the store
    notification itself carries no app user id; the app passes it to the server
    when it reports the purchase, and a SUBSCRIBED/PURCHASED notification can
    carry it via Apple's appAccountToken — not relied on here). For a renewal of
    an EXISTING subscription the user_id is read from the stored row.
    """
    now = now or datetime.now(timezone.utc)

    # 1. Dedupe on the notification uuid (migration 060 unique index).
    cur.execute(
        "SELECT 1 FROM subscription_notifications WHERE store=%s AND notification_uuid=%s",
        (event.store, event.notification_uuid))
    if cur.fetchone():
        return {'applied': False, 'duplicate': True,
                'status': event.target_status, 'user_id': None, 'level': None}

    cur.execute("""
        INSERT INTO subscription_notifications
            (store, notification_uuid, notification_type,
             original_transaction_id, raw)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (store, notification_uuid) DO NOTHING
    """, (event.store, event.notification_uuid, event.notification_type,
          event.original_transaction_id, json.dumps(event.raw_summary)[:4000]))

    # 2. Resolve the level this product maps to (DB-driven).
    level = level_for_store_product(cur, event.product_id) if event.product_id else None

    # 3. Find an existing subscription row (keyed on original txn id).
    cur.execute("""
        SELECT user_id, level, previous_level, status
        FROM auto_renew_subscriptions
        WHERE original_transaction_id = %s
    """, (event.original_transaction_id,))
    existing = cur.fetchone()

    if existing:
        row_user_id, row_level, row_prev, _row_status = existing
        user_id = row_user_id
        level = level or row_level
        previous_level = row_prev
        cur.execute("""
            UPDATE auto_renew_subscriptions
            SET status=%s, level=%s, product_id=COALESCE(%s, product_id),
                period_end=COALESCE(%s, period_end),
                auto_renew=COALESCE(%s, auto_renew),
                last_event_at=%s, updated_at=now()
            WHERE original_transaction_id=%s
        """, (event.target_status, level, event.product_id, event.period_end,
              event.auto_renew, event.event_at, event.original_transaction_id))
    else:
        # New subscription. The device is the hint (app-reported) when present.
        user_id = user_id_hint
        if not level:
            # We cannot map the product to a level; record the notification
            # (done above) but do not create an unmappable subscription row.
            return {'applied': True, 'duplicate': False,
                    'status': event.target_status, 'user_id': user_id,
                    'level': None, 'note': 'unmapped_product'}
        previous_level = None
        if user_id:
            prev = _current_device_level(cur, user_id)
            # previous_level is what to drop back to: never record a sub level
            # as the fallback.
            previous_level = prev if (prev and not str(prev).startswith('sub_')) else 'l1'
        cur.execute("""
            INSERT INTO auto_renew_subscriptions
                (user_id, store, product_id, level, original_transaction_id,
                 status, period_start, period_end, auto_renew, previous_level,
                 last_event_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (original_transaction_id) DO UPDATE SET
                status=EXCLUDED.status, period_end=EXCLUDED.period_end,
                auto_renew=EXCLUDED.auto_renew, last_event_at=EXCLUDED.last_event_at,
                updated_at=now()
        """, (user_id or '', event.store, event.product_id, level,
              event.original_transaction_id, event.target_status, event.event_at,
              event.period_end, event.auto_renew if event.auto_renew is not None else True,
              previous_level, event.event_at))

    # 4. Drive device_entitlement when we know the device.
    applied_level = None
    if user_id:
        if event.target_status in ENTITLING_STATUSES:
            _set_device_level(cur, user_id, level, anniversary_at=event.period_end)
            applied_level = level
        else:
            drop_to = previous_level or 'l1'
            _set_device_level(cur, user_id, drop_to, anniversary_at=None)
            applied_level = drop_to

    return {'applied': True, 'duplicate': False,
            'status': event.target_status, 'user_id': user_id,
            'level': applied_level}


# ───────────────────────────────────────────────────────────────────────────
# device_entitlement helpers (mirror of subscription_levels; the user-api owns
# this table). Kept tiny and additive — they only touch level + anniversary_at.
# ───────────────────────────────────────────────────────────────────────────
def _current_device_level(cur, user_id: str) -> Optional[str]:
    cur.execute("SELECT level FROM device_entitlement WHERE user_id=%s", (user_id,))
    row = cur.fetchone()
    return row[0] if row else None


def _set_device_level(cur, user_id: str, level: str,
                      anniversary_at: Optional[datetime] = None) -> None:
    """Set the device's current level (and the anniversary/period-end used by
    the plan screen). Creates the row if absent. Additive: leaves the pack/op
    counters untouched (a subscription level does not use them)."""
    cur.execute("""
        INSERT INTO device_entitlement (user_id, level, anniversary_at,
                                        last_activity_at, updated_at)
        VALUES (%s, %s, %s, now(), now())
        ON CONFLICT (user_id) DO UPDATE SET
            level=EXCLUDED.level,
            anniversary_at=EXCLUDED.anniversary_at,
            updated_at=now()
    """, (user_id, level, anniversary_at))
