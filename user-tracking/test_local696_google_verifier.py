"""
test_local696_google_verifier.py — LOCAL-696: tests for the Google Play purchase
verifier (google_play_verifier.verify_product_purchase) and the voided-purchase
reconcile core (google_play_voided_poller.reconcile_voided_purchases).

The Apple suite builds a throwaway PKI and signs JWS so it needs no Apple
servers; the Google suite does the equivalent — a FAKE api_client that returns
hand-built ProductPurchase dicts and records which acknowledge/consume calls
were made, so the whole positive + negative matrix runs with NO network and NO
service-account file. The verifier is PURE (it performs no network itself), so
injecting the fake client is all it takes.

Covered (the ticket's test list, verifier half):
  • purchased  -> granted, AND acknowledged, AND consumed;
  • pending    -> refused (purchase_pending);
  • canceled   -> refused (purchase_canceled);
  • wrong product (response/path/expected mismatch) -> refused (product_mismatch);
  • replayed token (already acknowledged+consumed) -> still verifies, no double
    acknowledge/consume (idempotent at the store layer);
  • a 404 from Google (forged token) -> refused (token_not_found);
  • a 401/403 from Google (bad SA)    -> refused (google_auth_failed);
  • missing token / missing order id  -> refused.

The 'missing SA -> 503' and 'voided -> unlock removed' end-to-end cases live in
tests/test_local696_google_play.py (they exercise the HTTP layer + DB). This
file also unit-tests the reconcile core with a tiny in-memory cursor so the
reversal logic is covered even with no database.

Run:
    cd user-tracking && python3 -m pytest test_local696_google_verifier.py -q
or (no pytest):
    cd user-tracking && python3 test_local696_google_verifier.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google_play_verifier import (  # noqa: E402
    verify_product_purchase, GoogleVerificationError, GoogleApiError,
    PURCHASE_STATE_PURCHASED, PURCHASE_STATE_PENDING, PURCHASE_STATE_CANCELED,
    ACK_STATE_NOT_ACKNOWLEDGED, ACK_STATE_ACKNOWLEDGED,
    CONSUMPTION_STATE_NOT_CONSUMED, CONSUMPTION_STATE_CONSUMED,
)

PRODUCT_ID = 'audioura.tour.tier3'
ORDER_ID = 'GPA.1234-5678-9012-34567'
TOKEN = 'opaque-purchase-token-abc'


# ───────────────────────────────────────────────────────────────────────────
# Fake Google Play API client — no network, records calls.
# ───────────────────────────────────────────────────────────────────────────
class FakeApiClient:
    """A stand-in for GooglePlayApiClient. `product_response` is the dict
    get_product_purchase returns; set `get_error`/`ack_error`/`consume_error` to
    a GoogleApiError (or any Exception) to force that call to fail. Records every
    acknowledge/consume so a test can assert the happy path did both."""

    def __init__(self, product_response=None, get_error=None,
                 ack_error=None, consume_error=None):
        self.product_response = product_response
        self.get_error = get_error
        self.ack_error = ack_error
        self.consume_error = consume_error
        self.acknowledged = []
        self.consumed = []

    def get_product_purchase(self, package_name, product_id, token):
        if self.get_error is not None:
            raise self.get_error
        return dict(self.product_response or {})

    def acknowledge_product(self, package_name, product_id, token):
        if self.ack_error is not None:
            raise self.ack_error
        self.acknowledged.append((product_id, token))

    def consume_product(self, package_name, product_id, token):
        if self.consume_error is not None:
            raise self.consume_error
        self.consumed.append((product_id, token))


def _purchase(**over):
    base = {
        'orderId': ORDER_ID,
        'productId': PRODUCT_ID,
        'purchaseState': PURCHASE_STATE_PURCHASED,
        'acknowledgementState': ACK_STATE_NOT_ACKNOWLEDGED,
        'consumptionState': CONSUMPTION_STATE_NOT_CONSUMED,
    }
    base.update(over)
    return base


# ───────────────────────────────────────────────────────────────────────────
# Happy path
# ───────────────────────────────────────────────────────────────────────────
def test_purchased_grants_acknowledges_and_consumes():
    client = FakeApiClient(product_response=_purchase())
    result = verify_product_purchase(
        client, product_id=PRODUCT_ID, purchase_token=TOKEN,
        expected_product_id=PRODUCT_ID)
    assert result.order_id == ORDER_ID
    assert result.product_id == PRODUCT_ID
    assert result.purchase_state == PURCHASE_STATE_PURCHASED
    assert result.acknowledged is True
    assert result.consumed is True
    # The verifier actually CALLED acknowledge and consume on the store.
    assert client.acknowledged == [(PRODUCT_ID, TOKEN)]
    assert client.consumed == [(PRODUCT_ID, TOKEN)]


def test_already_acknowledged_and_consumed_is_idempotent():
    # A replayed token that Google already shows acknowledged+consumed still
    # verifies, and the verifier does NOT acknowledge/consume a second time.
    client = FakeApiClient(product_response=_purchase(
        acknowledgementState=ACK_STATE_ACKNOWLEDGED,
        consumptionState=CONSUMPTION_STATE_CONSUMED))
    result = verify_product_purchase(
        client, product_id=PRODUCT_ID, purchase_token=TOKEN,
        expected_product_id=PRODUCT_ID)
    assert result.order_id == ORDER_ID
    assert result.acknowledged is True
    assert result.consumed is True
    assert client.acknowledged == []  # not re-acknowledged
    assert client.consumed == []       # not re-consumed


# ───────────────────────────────────────────────────────────────────────────
# Refusals by purchaseState
# ───────────────────────────────────────────────────────────────────────────
def test_pending_refused():
    client = FakeApiClient(product_response=_purchase(
        purchaseState=PURCHASE_STATE_PENDING))
    try:
        verify_product_purchase(client, product_id=PRODUCT_ID,
                                purchase_token=TOKEN)
        assert False, 'expected GoogleVerificationError'
    except GoogleVerificationError as e:
        assert e.code == 'purchase_pending', e.code
    # Never acknowledged or consumed a pending purchase.
    assert client.acknowledged == [] and client.consumed == []


def test_canceled_refused():
    client = FakeApiClient(product_response=_purchase(
        purchaseState=PURCHASE_STATE_CANCELED))
    try:
        verify_product_purchase(client, product_id=PRODUCT_ID,
                                purchase_token=TOKEN)
        assert False, 'expected GoogleVerificationError'
    except GoogleVerificationError as e:
        assert e.code == 'purchase_canceled', e.code


# ───────────────────────────────────────────────────────────────────────────
# Product mismatch
# ───────────────────────────────────────────────────────────────────────────
def test_response_product_mismatch_refused():
    # Google says the token is for a DIFFERENT product than we asked about.
    client = FakeApiClient(product_response=_purchase(
        productId='audioura.tour.tier1'))
    try:
        verify_product_purchase(client, product_id=PRODUCT_ID,
                                purchase_token=TOKEN)
        assert False, 'expected GoogleVerificationError'
    except GoogleVerificationError as e:
        assert e.code == 'product_mismatch', e.code


def test_expected_product_mismatch_refused():
    # The response matches the path product, but the server EXPECTED a different
    # product (a cheaper token replayed against an expensive grant).
    client = FakeApiClient(product_response=_purchase())
    try:
        verify_product_purchase(
            client, product_id=PRODUCT_ID, purchase_token=TOKEN,
            expected_product_id='audioura.tour.usd50')
        assert False, 'expected GoogleVerificationError'
    except GoogleVerificationError as e:
        assert e.code == 'product_mismatch', e.code


# ───────────────────────────────────────────────────────────────────────────
# API/transport failures mapped to stable codes
# ───────────────────────────────────────────────────────────────────────────
def test_token_not_found_refused():
    client = FakeApiClient(get_error=GoogleApiError(404, 'Not Found'))
    try:
        verify_product_purchase(client, product_id=PRODUCT_ID,
                                purchase_token=TOKEN)
        assert False, 'expected GoogleVerificationError'
    except GoogleVerificationError as e:
        assert e.code == 'token_not_found', e.code


def test_auth_failed_refused():
    client = FakeApiClient(get_error=GoogleApiError(401, 'Unauthorized'))
    try:
        verify_product_purchase(client, product_id=PRODUCT_ID,
                                purchase_token=TOKEN)
        assert False, 'expected GoogleVerificationError'
    except GoogleVerificationError as e:
        assert e.code == 'google_auth_failed', e.code


def test_acknowledge_failure_refused():
    client = FakeApiClient(product_response=_purchase(),
                           ack_error=GoogleApiError(500, 'server error'))
    try:
        verify_product_purchase(client, product_id=PRODUCT_ID,
                                purchase_token=TOKEN)
        assert False, 'expected GoogleVerificationError'
    except GoogleVerificationError as e:
        assert e.code == 'acknowledge_failed', e.code


def test_consume_failure_refused():
    client = FakeApiClient(product_response=_purchase(),
                           consume_error=GoogleApiError(500, 'server error'))
    try:
        verify_product_purchase(client, product_id=PRODUCT_ID,
                                purchase_token=TOKEN)
        assert False, 'expected GoogleVerificationError'
    except GoogleVerificationError as e:
        assert e.code == 'consume_failed', e.code


# ───────────────────────────────────────────────────────────────────────────
# Missing fields
# ───────────────────────────────────────────────────────────────────────────
def test_missing_token_refused():
    client = FakeApiClient(product_response=_purchase())
    try:
        verify_product_purchase(client, product_id=PRODUCT_ID, purchase_token='')
        assert False, 'expected GoogleVerificationError'
    except GoogleVerificationError as e:
        assert e.code == 'missing_purchase_token', e.code


def test_missing_order_id_refused():
    client = FakeApiClient(product_response=_purchase(orderId=None))
    try:
        verify_product_purchase(client, product_id=PRODUCT_ID,
                                purchase_token=TOKEN)
        assert False, 'expected GoogleVerificationError'
    except GoogleVerificationError as e:
        assert e.code == 'no_order_id', e.code


def test_no_consume_when_disabled():
    # acknowledge-only mode (consume=False): acknowledges but does not consume.
    client = FakeApiClient(product_response=_purchase())
    result = verify_product_purchase(
        client, product_id=PRODUCT_ID, purchase_token=TOKEN, consume=False)
    assert result.acknowledged is True
    assert client.acknowledged == [(PRODUCT_ID, TOKEN)]
    assert client.consumed == []
    assert result.consumed is False


# ═══════════════════════════════════════════════════════════════════════════
# Voided-purchase reconcile core — in-memory cursor, no DB.
# ═══════════════════════════════════════════════════════════════════════════
import google_play_voided_poller as voided  # noqa: E402


class FakeCursor:
    """A tiny stand-in cursor the reconcile core drives. It models exactly the
    SQL the core issues: the purchase lookup (by transaction_id, by raw_status
    LIKE), the three reversal UPDATE/DELETEs (reporting rowcount), and the
    ledger raw_status UPDATE. State lives in the parent FakeDB."""

    def __init__(self, db):
        self.db = db
        self.rowcount = 0
        self._result = None

    def execute(self, sql, params=()):
        s = ' '.join(sql.split())
        self._result = None
        self.rowcount = 0
        if s.startswith('SELECT id, store, product, user_id, raw_status FROM purchases WHERE transaction_id'):
            self._result = self.db.purchase_by_txid(params[0])
        elif s.startswith('SELECT id, store, product, user_id, raw_status FROM purchases WHERE raw_status LIKE'):
            self._result = self.db.purchase_by_status_like(params[0])
        elif s.startswith('DELETE FROM tour_unlocks WHERE user_id'):
            self.rowcount = self.db.delete_unlock(params[0], params[1])
        elif s.startswith('UPDATE community_memberships SET expires_at'):
            self.rowcount = self.db.expire_membership(params[0], params[1], params[2])
        elif s.startswith('UPDATE device_entitlement SET level'):
            self.rowcount = self.db.reset_level(params[0])
        elif s.startswith('UPDATE purchases SET raw_status'):
            self.db.set_status(params[1], params[0])
            self.rowcount = 1
        else:
            raise AssertionError(f'unexpected SQL: {s}')

    def fetchone(self):
        return self._result


class FakeDB:
    """In-memory stand-in for the grant tables, keyed as the real schema is."""

    def __init__(self):
        # purchases: id -> {store, product, user_id, raw_status, transaction_id}
        self.purchases = {}
        self.unlocks = []        # [(user_id, tour_id, transaction_id)]
        self.memberships = []    # [{user_id, transaction_id, expires_at}]
        self.levels = {}         # user_id -> level

    def cursor(self):
        return FakeCursor(self)

    def add_purchase(self, pid, store, product, user_id, raw_status, txid):
        self.purchases[pid] = {
            'store': store, 'product': product, 'user_id': user_id,
            'raw_status': raw_status, 'transaction_id': txid}

    def purchase_by_txid(self, txid):
        for pid, p in self.purchases.items():
            if p['transaction_id'] == txid:
                return (pid, p['store'], p['product'], p['user_id'], p['raw_status'])
        return None

    def purchase_by_status_like(self, like):
        needle = like.strip('%')
        for pid, p in self.purchases.items():
            if needle and needle in (p['raw_status'] or ''):
                return (pid, p['store'], p['product'], p['user_id'], p['raw_status'])
        return None

    def delete_unlock(self, user_id, txid):
        before = len(self.unlocks)
        self.unlocks = [u for u in self.unlocks
                        if not (u[0] == user_id and u[2] == txid)]
        return before - len(self.unlocks)

    def expire_membership(self, now, user_id, txid):
        n = 0
        for m in self.memberships:
            if m['user_id'] == user_id and m['transaction_id'] == txid:
                m['expires_at'] = now
                n += 1
        return n

    def reset_level(self, user_id):
        if user_id in self.levels:
            self.levels[user_id] = 'l1'
            return 1
        return 0

    def set_status(self, pid, status):
        if pid in self.purchases:
            self.purchases[pid]['raw_status'] = status


def test_reconcile_removes_tour_unlock():
    db = FakeDB()
    db.add_purchase(1, 'google', 'audioura.tour.tier3', 'U1',
                    f'google_verified:{ORDER_ID}', ORDER_ID)
    db.unlocks.append(('U1', 42, ORDER_ID))
    cur = db.cursor()
    summary = voided.reconcile_voided_purchases(
        cur, [{'orderId': ORDER_ID, 'purchaseToken': TOKEN}])
    assert summary['reversed']['tour_unlock'] == 1
    assert db.unlocks == []  # the unlock was removed
    # The ledger row is marked voided (audit), not deleted.
    assert db.purchases[1]['raw_status'].startswith('voided:tour_unlock:')


def test_reconcile_expires_membership():
    db = FakeDB()
    db.add_purchase(2, 'google', 'audioura.pass.usd5', 'U2',
                    f'google_verified:{ORDER_ID}', ORDER_ID)
    db.memberships.append({'user_id': 'U2', 'transaction_id': ORDER_ID,
                           'expires_at': None})
    cur = db.cursor()
    summary = voided.reconcile_voided_purchases(cur, [{'orderId': ORDER_ID}])
    assert summary['reversed']['membership'] == 1
    assert db.memberships[0]['expires_at'] is not None  # expired now


def test_reconcile_drops_level():
    db = FakeDB()
    db.add_purchase(3, 'google', 'l3_pack_10', 'U3',
                    f'google_verified:{ORDER_ID}', ORDER_ID)
    db.levels['U3'] = 'l3'
    cur = db.cursor()
    summary = voided.reconcile_voided_purchases(cur, [{'orderId': ORDER_ID}])
    assert summary['reversed']['level'] == 1
    assert db.levels['U3'] == 'l1'


def test_reconcile_idempotent_and_unmatched():
    db = FakeDB()
    # Already voided → counted already_voided, not reversed again.
    db.add_purchase(4, 'google', 'audioura.tour.tier3', 'U4',
                    'voided:tour_unlock:google_verified:GPA.old', 'GPA.old')
    cur = db.cursor()
    s1 = voided.reconcile_voided_purchases(cur, [{'orderId': 'GPA.old'}])
    assert s1['already_voided'] == 1
    # A void for a purchase we never recorded → unmatched (harmless skip).
    s2 = voided.reconcile_voided_purchases(cur, [{'orderId': 'GPA.unknown'}])
    assert s2['unmatched'] == 1


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items())
             if k.startswith('test_') and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'PASS {t.__name__}')
        except AssertionError as e:
            failed += 1
            print(f'FAIL {t.__name__}: {e}')
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f'ERROR {t.__name__}: {type(e).__name__}: {e}')
    print(f'\n{len(tests) - failed}/{len(tests)} passed')
    sys.exit(1 if failed else 0)
