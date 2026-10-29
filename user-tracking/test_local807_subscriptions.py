"""
test_local807_subscriptions.py — LOCAL-807: auto-renewing subscription lifecycle.

PURE tests (no network, no real Apple/Google):
  * Apple App Store Server Notifications v2: build a {"signedPayload": <JWS>}
    envelope whose payload carries nested signedTransactionInfo /
    signedRenewalInfo JWS, all signed with a THROWAWAY test PKI and verified
    against the injected test root — exactly the pattern test_local598_apple_jws
    uses. Each notificationType maps to the right lifecycle status.
  * Google RTDN: a base64 Pub/Sub message decoded and mapped, with a MOCK
    subscriptionsv2 client (no network, no service account).
  * The type->status PURE mappings (apple_type_to_status, GOOGLE_TYPE_TO_STATUS).
  * A tiny in-memory FAKE cursor proves apply_event is idempotent (a repeated
    notification uuid is a no-op) and maps an active subscription to its level,
    then drops back to the previous level on EXPIRED.

Run:
    cd user-tracking && python3 -m pytest test_local807_subscriptions.py -q
"""

import base64
import datetime
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import subscription_notifications as sn  # noqa: E402
from apple_jws_verifier import verify_and_decode_jws  # noqa: E402

# Reuse the throwaway-PKI + JWS-signing helpers from the 598 suite verbatim.
from test_local598_apple_jws import (  # noqa: E402
    _make_chain, _sign_jws, _root_pem, BUNDLE_ID,
)

PRODUCT = 'audioura.sub.monthly'


# ───────────────────────────────────────────────────────────────────────────
# Apple ASSN v2 envelope builder (signedPayload with nested JWS)
# ───────────────────────────────────────────────────────────────────────────
def _ms(dt):
    return int(dt.timestamp() * 1000)


def _build_apple_notification(chain, notification_type, subtype=None,
                              product_id=PRODUCT, original_txn='2000000111',
                              expires_in_days=30, uuid='uuid-abc',
                              auto_renew_status=1, bundle_id=BUNDLE_ID):
    """Return a {"signedPayload": <JWS>} dict for an ASSN v2 notification, with
    the nested transaction/renewal info signed by the same test leaf."""
    root_key, root_cert, inter_cert, leaf_key, leaf_cert = chain
    now = datetime.datetime.now(datetime.timezone.utc)
    expires = now + datetime.timedelta(days=expires_in_days)

    def sign(payload):
        return _sign_jws(leaf_key, leaf_cert, inter_cert, root_cert, payload)

    txn_info = {
        'transactionId': '2000000999',
        'originalTransactionId': original_txn,
        'productId': product_id,
        'bundleId': bundle_id,
        'type': 'Auto-Renewable Subscription',
        'expiresDate': _ms(expires),
        'signedDate': _ms(now),
    }
    renewal_info = {
        'originalTransactionId': original_txn,
        'autoRenewStatus': auto_renew_status,
        'autoRenewProductId': product_id,
        'signedDate': _ms(now),
    }
    envelope = {
        'notificationType': notification_type,
        'notificationUUID': uuid,
        'signedDate': _ms(now),
        'data': {
            'bundleId': bundle_id,
            'environment': 'Sandbox',
            'signedTransactionInfo': sign(txn_info),
            'signedRenewalInfo': sign(renewal_info),
        },
    }
    if subtype:
        envelope['subtype'] = subtype
    return {'signedPayload': sign(envelope)}, root_cert


# ───────────────────────────────────────────────────────────────────────────
# In-memory fake DB cursor — enough SQL for apply_event/effective_level.
# ───────────────────────────────────────────────────────────────────────────
class FakeCursor:
    def __init__(self, plans, store):
        self.plans = plans          # {store_product_id: plan_id}
        self.store = store          # shared dict-of-tables state
        self._result = []

    def execute(self, sql, params=()):
        s = ' '.join(sql.split())
        self._result = []
        # plans.store_product_id -> plan_id
        if s.startswith('SELECT plan_id FROM plans WHERE store_product_id'):
            pid = self.plans.get(params[0])
            self._result = [(pid,)] if pid else []
        # dedupe check
        elif s.startswith('SELECT 1 FROM subscription_notifications'):
            key = (params[0], params[1])
            self._result = [(1,)] if key in self.store['notifs'] else []
        elif s.startswith('INSERT INTO subscription_notifications'):
            self.store['notifs'].add((params[0], params[1]))
        # existing subscription row
        elif s.startswith('SELECT user_id, level, previous_level, status FROM auto_renew_subscriptions'):
            row = self.store['subs'].get(params[0])
            self._result = [(row['user_id'], row['level'], row['previous_level'],
                             row['status'])] if row else []
        elif s.startswith('UPDATE auto_renew_subscriptions SET status'):
            (status, level, product_id, period_end, auto_renew, event_at, otx) = params
            row = self.store['subs'][otx]
            row.update(status=status, level=level, period_end=period_end)
        elif s.startswith('INSERT INTO auto_renew_subscriptions'):
            (user_id, store, product_id, level, otx, status, period_start,
             period_end, auto_renew, previous_level, last_event_at) = params
            self.store['subs'][otx] = dict(
                user_id=user_id, level=level, previous_level=previous_level,
                status=status, period_end=period_end, store=store)
        # effective_level scan
        elif s.startswith('SELECT level, status, period_end FROM auto_renew_subscriptions WHERE user_id'):
            uid = params[0]
            rows = [(r['level'], r['status'], r['period_end'])
                    for r in self.store['subs'].values() if r['user_id'] == uid]
            self._result = rows
        # device_entitlement reads/writes
        elif s.startswith('SELECT level FROM device_entitlement'):
            lvl = self.store['devices'].get(params[0])
            self._result = [(lvl,)] if lvl else []
        elif s.startswith('INSERT INTO device_entitlement'):
            self.store['devices'][params[0]] = params[1]
        else:
            raise AssertionError(f'unexpected SQL: {s[:80]}')

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)


def _store():
    return {'notifs': set(), 'subs': {}, 'devices': {}}


def _plans():
    return {
        'audioura.sub.day': 'sub_day',
        'audioura.sub.weekly': 'sub_week',
        'audioura.sub.monthly': 'sub_month',
        'audioura.sub.annual': 'sub_year',
    }


# ───────────────────────────────────────────────────────────────────────────
# 1. Pure type -> status mapping (Apple)
# ───────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('ntype,subtype,expected', [
    ('SUBSCRIBED', None, sn.STATUS_ACTIVE),
    ('DID_RENEW', None, sn.STATUS_ACTIVE),
    ('DID_FAIL_TO_RENEW', 'GRACE_PERIOD', sn.STATUS_GRACE),
    ('DID_FAIL_TO_RENEW', None, sn.STATUS_BILLING_RETRY),
    ('GRACE_PERIOD_EXPIRED', None, sn.STATUS_EXPIRED),
    ('EXPIRED', None, sn.STATUS_EXPIRED),
    ('REFUND', None, sn.STATUS_REFUNDED),
    ('REVOKE', None, sn.STATUS_REVOKED),
    ('DID_CHANGE_RENEWAL_STATUS', 'AUTO_RENEW_DISABLED', sn.STATUS_ACTIVE),
])
def test_apple_type_to_status(ntype, subtype, expected):
    status, _ = sn.apple_type_to_status(ntype, subtype)
    assert status == expected


def test_apple_unhandled_type_is_ignored_200():
    with pytest.raises(sn.SubscriptionNotificationError) as ei:
        sn.apple_type_to_status('SOMETHING_NEW', None)
    assert ei.value.http_status == 200


# ───────────────────────────────────────────────────────────────────────────
# 2. Apple notification: verify the signed envelope + nested JWS end to end
# ───────────────────────────────────────────────────────────────────────────
def test_apple_notification_parses_and_verifies():
    chain = _make_chain()
    body, root_cert = _build_apple_notification(chain, 'SUBSCRIBED')
    event = sn.parse_apple_notification(
        body, root_ca_pem=_root_pem(root_cert), expected_bundle_id=BUNDLE_ID)
    assert event.store == 'apple'
    assert event.target_status == sn.STATUS_ACTIVE
    assert event.original_transaction_id == '2000000111'
    assert event.product_id == PRODUCT
    assert event.notification_uuid == 'uuid-abc'
    assert event.period_end is not None


def test_apple_notification_forged_root_rejected():
    chain = _make_chain()
    body, _ = _build_apple_notification(chain, 'DID_RENEW')
    # Pin to a DIFFERENT root than the one that signed the envelope.
    other = _make_chain()
    with pytest.raises(sn.SubscriptionNotificationError) as ei:
        sn.parse_apple_notification(
            body, root_ca_pem=_root_pem(other[1]), expected_bundle_id=BUNDLE_ID)
    assert ei.value.http_status == 401
    assert 'root_not_apple' in ei.value.code


def test_apple_notification_wrong_bundle_rejected():
    chain = _make_chain()
    body, root_cert = _build_apple_notification(chain, 'SUBSCRIBED',
                                                bundle_id='com.evil.app')
    with pytest.raises(sn.SubscriptionNotificationError) as ei:
        sn.parse_apple_notification(
            body, root_ca_pem=_root_pem(root_cert), expected_bundle_id=BUNDLE_ID)
    assert ei.value.code == 'apple_bundle_mismatch'


def test_apple_notification_no_signed_payload():
    with pytest.raises(sn.SubscriptionNotificationError) as ei:
        sn.parse_apple_notification({}, root_ca_pem=b'', expected_bundle_id=BUNDLE_ID)
    assert ei.value.code == 'apple_no_signed_payload'


# ───────────────────────────────────────────────────────────────────────────
# 3. apply_event: idempotency + entitlement mapping + drop-back on expiry
# ───────────────────────────────────────────────────────────────────────────
def test_apply_event_grants_level_and_is_idempotent():
    chain = _make_chain()
    store = _store()
    # Device starts on l2 (Free) so previous_level is captured as l2.
    store['devices']['device-1'] = 'l2'
    body, root_cert = _build_apple_notification(chain, 'SUBSCRIBED', uuid='n1')
    event = sn.parse_apple_notification(
        body, root_ca_pem=_root_pem(root_cert), expected_bundle_id=BUNDLE_ID)

    cur = FakeCursor(_plans(), store)
    res = sn.apply_event(cur, event, user_id_hint='device-1')
    assert res['applied'] and not res['duplicate']
    assert res['level'] == 'sub_month'
    # Device now on the subscription level.
    assert store['devices']['device-1'] == 'sub_month'
    # The subscription row remembers l2 as the drop-back level.
    assert store['subs']['2000000111']['previous_level'] == 'l2'

    # Re-applying the SAME notification uuid is a no-op.
    res2 = sn.apply_event(cur, event, user_id_hint='device-1')
    assert res2['duplicate'] is True
    assert store['devices']['device-1'] == 'sub_month'


def test_apply_event_expiry_drops_to_previous_level():
    chain = _make_chain()
    store = _store()
    store['devices']['device-2'] = 'l2'
    # First SUBSCRIBED.
    body1, root_cert = _build_apple_notification(
        chain, 'SUBSCRIBED', uuid='sub1', original_txn='tx-2')
    ev1 = sn.parse_apple_notification(
        body1, root_ca_pem=_root_pem(root_cert), expected_bundle_id=BUNDLE_ID)
    cur = FakeCursor(_plans(), store)
    sn.apply_event(cur, ev1, user_id_hint='device-2')
    assert store['devices']['device-2'] == 'sub_month'

    # Then EXPIRED -> drops back to l2.
    body2, _ = _build_apple_notification(
        chain, 'EXPIRED', uuid='exp1', original_txn='tx-2')
    ev2 = sn.parse_apple_notification(
        body2, root_ca_pem=_root_pem(root_cert), expected_bundle_id=BUNDLE_ID)
    res = sn.apply_event(cur, ev2, user_id_hint='device-2')
    assert res['level'] == 'l2'
    assert store['devices']['device-2'] == 'l2'


def test_effective_level_reads_entitling_subscription():
    store = _store()
    cur = FakeCursor(_plans(), store)
    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=10)
    store['subs']['tx-9'] = dict(user_id='d9', level='sub_week',
                                 previous_level='l1', status=sn.STATUS_ACTIVE,
                                 period_end=future, store='apple')
    assert sn.effective_level(cur, 'd9') == 'sub_week'
    # Expired subscription does not grant.
    store['subs']['tx-9']['status'] = sn.STATUS_EXPIRED
    assert sn.effective_level(cur, 'd9') is None


# ───────────────────────────────────────────────────────────────────────────
# 4. Google RTDN (mock subscriptionsv2 client — no network)
# ───────────────────────────────────────────────────────────────────────────
class _FakeGoogleClient:
    def __init__(self, expiry_iso, state='SUBSCRIPTION_STATE_ACTIVE'):
        self.expiry_iso = expiry_iso
        self.state = state

    def get_subscription_v2(self, package_name, token):
        return {
            'subscriptionState': self.state,
            'lineItems': [{'productId': 'audioura.sub.monthly',
                           'expiryTime': self.expiry_iso}],
        }


def _rtdn_body(ntype, token='tok-1', message_id='m1',
               product='audioura.sub.monthly'):
    data = {
        'version': '1.0',
        'packageName': 'com.audioura.audiotours',
        'subscriptionNotification': {
            'version': '1.0',
            'notificationType': ntype,
            'purchaseToken': token,
            'subscriptionId': product,
        },
    }
    encoded = base64.b64encode(json.dumps(data).encode()).decode()
    return {'message': {'data': encoded, 'messageId': message_id}}


def test_google_rtdn_renewed_maps_active():
    client = _FakeGoogleClient('2030-01-01T00:00:00Z')
    body = _rtdn_body(2)  # SUBSCRIPTION_RENEWED
    event = sn.parse_google_rtdn(body, api_client=client,
                                 package_name='com.audioura.audiotours')
    assert event.store == 'google'
    assert event.target_status == sn.STATUS_ACTIVE
    assert event.original_transaction_id == 'tok-1'
    assert event.product_id == 'audioura.sub.monthly'
    assert event.period_end is not None


def test_google_rtdn_expired_maps_expired():
    client = _FakeGoogleClient('2020-01-01T00:00:00Z',
                               state='SUBSCRIPTION_STATE_EXPIRED')
    body = _rtdn_body(13)  # SUBSCRIPTION_EXPIRED
    event = sn.parse_google_rtdn(body, api_client=client,
                                 package_name='com.audioura.audiotours')
    assert event.target_status == sn.STATUS_EXPIRED


def test_google_rtdn_unhandled_type_ignored_200():
    body = _rtdn_body(999)
    with pytest.raises(sn.SubscriptionNotificationError) as ei:
        sn.parse_google_rtdn(body, api_client=None)
    assert ei.value.http_status == 200


def test_google_rtdn_no_message_data():
    with pytest.raises(sn.SubscriptionNotificationError) as ei:
        sn.parse_google_rtdn({}, api_client=None)
    assert ei.value.code == 'google_no_message_data'


def test_google_rtdn_applies_and_grants_level():
    store = _store()
    store['devices']['gdev'] = 'l1'
    client = _FakeGoogleClient('2030-01-01T00:00:00Z')
    body = _rtdn_body(4, token='gtok')  # SUBSCRIPTION_PURCHASED
    event = sn.parse_google_rtdn(body, api_client=client,
                                 package_name='com.audioura.audiotours')
    cur = FakeCursor(_plans(), store)
    res = sn.apply_event(cur, event, user_id_hint='gdev')
    assert res['level'] == 'sub_month'
    assert store['devices']['gdev'] == 'sub_month'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))