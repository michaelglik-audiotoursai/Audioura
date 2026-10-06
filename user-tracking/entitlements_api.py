"""
entitlements_api.py — LOCAL-595 user-api endpoints for subscription levels.
============================================================================

Self-contained Flask blueprint for the user-api service (user-tracking/app.py).
It is self-contained ON PURPOSE: the user-api container's build context is
./user-tracking, so it cannot import the repo-root subscription_levels.py. The
device-state and anniversary logic here MIRRORS subscription_levels.py exactly
(same tables, same arithmetic). The repo-root module remains the authority used
by the orchestrator and editing service; this blueprint is the HTTP surface.

Endpoints (auth: X-API-Key == GATEWAY_API_KEY, the existing referral pattern):

  GET  /entitlements/me?user_id=...     -> level, allowances left, anniversary,
                                           warn_renewal, renewal_prompt
  POST /entitlements/app-open  {user_id}        -> record activity, renewal_prompt
  POST /entitlements/lapse     {user_id}        -> drop to L1
  POST /purchases/verify {store, transaction_id, product, user_id}
        -> verify via the IAP verifier (sandbox stub when IAP_VERIFY_MODE=stub),
           idempotent on transaction_id; a verified L3/L4 purchase sets the
           level, resets the pack and sets the anniversary.

Real Apple/Google verification lands in LOCAL-598; this ships the interface and
the stub only.
"""

import os
import hmac
import logging
import calendar
from datetime import datetime, date, timedelta

import psycopg2
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

entitlements_bp = Blueprint('entitlements', __name__)

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://admin:password123@localhost:5432/audiotours')
API_KEY = os.getenv('GATEWAY_API_KEY', '')
IAP_VERIFY_MODE = os.getenv('IAP_VERIFY_MODE', 'stub')  # 'stub' | 'apple' | 'google'
RENEWAL_WARN_DAYS = int(os.getenv('RENEWAL_WARN_DAYS', '3'))

# [LOCAL-598] Apple verification config. The bundle id the JWS must carry; the
# path to the bundled Apple Root CA G3 we pin the x5c chain to.
APPLE_BUNDLE_ID = os.getenv('APPLE_BUNDLE_ID', 'com.audioura.audiotours')
APPLE_ROOT_CA_PATH = os.getenv(
    'APPLE_ROOT_CA_PATH',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'apple_root_ca_g3.pem'),
)

# product -> level mapping. Data, not logic: a new product is one dict entry.
# Keys are the SERVER product keys.
PRODUCT_LEVELS = {
    'l3_pack_10': 'l3',
    'l4_round_25': 'l4',
}

# [LOCAL-598] The app/StoreKit product ids (App Store Connect / StoreKit config
# file) mapped to the server product keys above. The device sends the STORE id
# in `product`; we accept either the store id or the server key so the stub and
# apple paths share one endpoint. A new product is one more dict entry.
STORE_PRODUCT_IDS = {
    'audioura.pack.l3': 'l3_pack_10',
    'audioura.round.l4': 'l4_round_25',
}

# Reverse: server key -> expected store productId (for the apple JWS check).
SERVER_TO_STORE_PRODUCT = {v: k for k, v in STORE_PRODUCT_IDS.items()}


def _normalize_product(product):
    """Accept either a store product id (audioura.pack.l3) or a server product
    key (l3_pack_10); return the SERVER key, or None if unknown."""
    if product in PRODUCT_LEVELS:
        return product
    return STORE_PRODUCT_IDS.get(product)


def _get_db():
    return psycopg2.connect(DATABASE_URL)


def _require_api_key():
    """X-API-Key header check — identical pattern to referral_endpoints."""
    if not API_KEY:
        return jsonify({"error": "service_misconfigured"}), 503
    client_key = request.headers.get('X-API-Key', '')
    if not client_key or not hmac.compare_digest(client_key, API_KEY):
        return jsonify({"error": "unauthorized"}), 401
    return None


# ───────────────────────────────────────────────────────────────────────────
# Anniversary arithmetic (mirror of subscription_levels.add_one_calendar_month)
# ───────────────────────────────────────────────────────────────────────────
def add_one_calendar_month(when):
    is_dt = isinstance(when, datetime)
    y, m, d = when.year, when.month, when.day
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    last_day = calendar.monthrange(ny, nm)[1]
    nd = min(d, last_day)
    return when.replace(year=ny, month=nm, day=nd) if is_dt else date(ny, nm, nd)


def _is_renewal_due(anniversary_at, now):
    return anniversary_at is not None and now >= anniversary_at


def _warn_renewal(anniversary_at, now, days=RENEWAL_WARN_DAYS):
    if anniversary_at is None or now >= anniversary_at:
        return False
    return now >= (anniversary_at - timedelta(days=days))


# ───────────────────────────────────────────────────────────────────────────
# Device state helpers
# ───────────────────────────────────────────────────────────────────────────
_DEV_COLS = ['user_id', 'level', 'pack_started_at', 'anniversary_at',
             'fresh_used', 'edits_used', 'ops_used', 'last_activity_at']


def _get_device_state(cur, user_id):
    cur.execute("""
        SELECT user_id, level, pack_started_at, anniversary_at,
               fresh_used, edits_used, ops_used, last_activity_at
        FROM device_entitlement WHERE user_id = %s
    """, (user_id,))
    row = cur.fetchone()
    if not row:
        return {'user_id': user_id, 'level': 'l1', 'pack_started_at': None,
                'anniversary_at': None, 'fresh_used': 0, 'edits_used': 0,
                'ops_used': 0, 'last_activity_at': None}
    return dict(zip(_DEV_COLS, row))


_PLAN_COLS = ['plan_id', 'tours_per_day', 'tours_per_month', 'fresh_per_pack',
              'edits_per_pack', 'ops_per_pack', 'max_stops', 'max_new_stops_per_edit',
              'by_reference_only', 'referrals_allowed', 'referral_period', 'seat_cap',
              'can_sell', 'price_usd', 'inactivity_days']


def _get_plan(cur, level):
    cur.execute("""
        SELECT plan_id, tours_per_day, tours_per_month, fresh_per_pack,
               edits_per_pack, ops_per_pack, max_stops, max_new_stops_per_edit,
               by_reference_only, referrals_allowed, referral_period, seat_cap,
               can_sell, price_usd, inactivity_days
        FROM plans WHERE plan_id = %s
    """, (level,))
    row = cur.fetchone()
    return dict(zip(_PLAN_COLS, row)) if row else None


def _allowances_left(cur, state, plan):
    """Compute remaining allowances for the current level, as a dict the app can
    render. Period levels (L2/Tester) report remaining day/month fresh counts;
    pack levels (L3/L4) report remaining pack units."""
    out = {}
    level = state['level']
    if plan is None:
        return out
    # Period caps (count tour_requests written by the orchestrator).
    if plan['tours_per_day'] is not None and plan['tours_per_day'] < 999:
        cur.execute("""SELECT COUNT(*) FROM tour_requests
                       WHERE secret_id=%s AND source='orchestrator'
                         AND started_at::date = CURRENT_DATE""", (state['user_id'],))
        used_day = cur.fetchone()[0]
        out['tours_today_left'] = max(0, plan['tours_per_day'] - used_day)
    if plan['tours_per_month'] is not None:
        cur.execute("""SELECT COUNT(*) FROM tour_requests
                       WHERE secret_id=%s AND source='orchestrator'
                         AND started_at >= date_trunc('month', CURRENT_DATE)""",
                    (state['user_id'],))
        used_month = cur.fetchone()[0]
        out['tours_this_month_left'] = max(0, plan['tours_per_month'] - used_month)
    if plan['fresh_per_pack'] is not None:
        out['fresh_left'] = max(0, plan['fresh_per_pack'] - state['fresh_used'])
    if plan['edits_per_pack'] is not None:
        out['edits_left'] = max(0, plan['edits_per_pack'] - state['edits_used'])
    if plan['ops_per_pack'] is not None:
        out['ops_left'] = max(0, plan['ops_per_pack'] - state['ops_used'])
    return out


def _me_payload(cur, user_id, now=None):
    now = now or datetime.utcnow()
    state = _get_device_state(cur, user_id)
    plan = _get_plan(cur, state['level'])
    ann = state['anniversary_at']
    renewal_due = _is_renewal_due(ann, now)
    return {
        'user_id': user_id,
        'level': state['level'],
        'anniversary_at': ann.isoformat() if ann else None,
        'allowances_left': _allowances_left(cur, state, plan),
        'warn_renewal': _warn_renewal(ann, now),
        'renewal_prompt': renewal_due,
        'can_sell': bool(plan['can_sell']) if plan else False,
    }


# ───────────────────────────────────────────────────────────────────────────
# IAP verifier interface + sandbox stub + offline Apple verification
# ───────────────────────────────────────────────────────────────────────────
class VerificationResult:
    def __init__(self, ok, raw_status, amount=None):
        self.ok = ok
        self.raw_status = raw_status
        self.amount = amount


_PLAN_AMOUNTS = {'l3_pack_10': 10.00, 'l4_round_25': 25.00}


def _load_apple_root_ca():
    with open(APPLE_ROOT_CA_PATH, 'rb') as f:
        return f.read()


def verify_purchase(store, transaction_id, product, signed_transaction=None):
    """Verify an IAP against the store. IAP_VERIFY_MODE selects the backend.

    Args:
        store: 'apple' (or 'google', not implemented).
        transaction_id: the store transaction id (used by the stub and for the
            idempotency check at the call site).
        product: the SERVER product key (l3_pack_10 / l4_round_25).
        signed_transaction: the StoreKit 2 JWS (required for apple mode).

    stub   : accept any non-empty transaction_id (sandbox). No crypto.
    apple  : verify the StoreKit 2 JWS OFFLINE — x5c chain pinned to Apple Root
             CA G3, ES256 signature, bundleId, productId and type==Consumable.
             No API key, no network. The verified transactionId from the JWS is
             authoritative; it is returned in raw_status for the caller.
    """
    if IAP_VERIFY_MODE == 'stub':
        if not transaction_id:
            return VerificationResult(False, 'stub_rejected_empty_transaction')
        return VerificationResult(True, 'stub_verified', _PLAN_AMOUNTS.get(product))

    if IAP_VERIFY_MODE == 'apple':
        if store != 'apple':
            return VerificationResult(False, f'apple_mode_wrong_store:{store}')
        if not signed_transaction:
            return VerificationResult(False, 'apple_missing_signed_transaction')
        try:
            # Imported lazily so stub-mode deployments need no crypto dep.
            from apple_jws_verifier import (
                verify_signed_transaction, JwsVerificationError,
            )
        except Exception as e:  # pragma: no cover - import-time safety
            logger.error(f"[LOCAL-598] apple verifier import failed: {e}")
            return VerificationResult(False, f'apple_verifier_unavailable:{e}')

        expected_store_product = SERVER_TO_STORE_PRODUCT.get(product)
        try:
            root_pem = _load_apple_root_ca()
            verified = verify_signed_transaction(
                signed_transaction,
                root_ca_pem=root_pem,
                expected_bundle_id=APPLE_BUNDLE_ID,
                expected_product_id=expected_store_product,
                required_type='Consumable',
            )
        except JwsVerificationError as e:
            logger.warning(f"[LOCAL-598] apple verify failed: {e.code}")
            return VerificationResult(False, f'apple_{e.code}')
        except Exception as e:
            logger.error(f"[LOCAL-598] apple verify error: {e}")
            return VerificationResult(False, f'apple_error:{e}')

        # The JWS is authoritative: trust the transactionId FROM the signed
        # transaction, not the client-supplied one. Report it so the caller
        # records/idempotency-checks the verified id.
        return VerificationResult(
            True, f'apple_verified:{verified.transaction_id}',
            _PLAN_AMOUNTS.get(product))

    # google / other: not implemented in LOCAL-598 (out of scope).
    return VerificationResult(False, f'verify_mode_not_implemented:{IAP_VERIFY_MODE}')


# ───────────────────────────────────────────────────────────────────────────
# Endpoints
# ───────────────────────────────────────────────────────────────────────────
@entitlements_bp.route('/entitlements/me', methods=['GET'])
def entitlements_me():
    err = _require_api_key()
    if err:
        return err
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    conn = _get_db()
    try:
        cur = conn.cursor()
        payload = _me_payload(cur, user_id)
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()


@entitlements_bp.route('/entitlements/app-open', methods=['POST'])
def entitlements_app_open():
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    conn = _get_db()
    try:
        cur = conn.cursor()
        # Record activity; create at L1 if the device is new.
        cur.execute("""
            INSERT INTO device_entitlement (user_id, level, last_activity_at)
            VALUES (%s, 'l1', NOW())
            ON CONFLICT (user_id) DO UPDATE
                SET last_activity_at = NOW(), updated_at = NOW()
        """, (user_id,))
        conn.commit()
        payload = _me_payload(cur, user_id)
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()


@entitlements_bp.route('/entitlements/lapse', methods=['POST'])
def entitlements_lapse():
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    conn = _get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO device_entitlement (user_id, level, last_activity_at)
            VALUES (%s, 'l1', NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                level = 'l1', pack_started_at = NULL, anniversary_at = NULL,
                fresh_used = 0, edits_used = 0, ops_used = 0, updated_at = NOW()
        """, (user_id,))
        conn.commit()
        payload = _me_payload(cur, user_id)
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()


@entitlements_bp.route('/purchases/verify', methods=['POST'])
def purchases_verify():
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    store = data.get('store')
    transaction_id = data.get('transaction_id')
    product = data.get('product')
    user_id = data.get('user_id')
    # [LOCAL-598] StoreKit 2 JWS signed transaction (apple mode). Optional in
    # stub mode so existing sandbox tests keep working.
    signed_transaction = data.get('signed_transaction')
    if not all([store, transaction_id, product, user_id]):
        return jsonify({
            "error": "missing_fields",
            "message": "store, transaction_id, product and user_id are all required.",
        }), 400

    # Accept either the store product id (audioura.pack.l3) or the server key
    # (l3_pack_10). Normalize to the server key for the level mapping.
    server_product = _normalize_product(product)
    level = PRODUCT_LEVELS.get(server_product) if server_product else None
    if level is None:
        return jsonify({
            "error": "unknown_product",
            "message": f"Unknown product '{product}'.",
        }), 400

    conn = _get_db()
    try:
        cur = conn.cursor()

        # Idempotency (first pass): the client-supplied transaction_id can
        # never grant twice. In apple mode the JWS yields the authoritative id
        # which we re-check below before recording.
        cur.execute("SELECT id FROM purchases WHERE transaction_id = %s", (transaction_id,))
        if cur.fetchone():
            cur.close()
            return jsonify({
                "error": "already_verified",
                "message": "This transaction has already been processed.",
                "transaction_id": transaction_id,
            }), 409

        # Verify with the store. apple mode verifies the JWS offline; stub
        # accepts any non-empty transaction_id.
        result = verify_purchase(
            store, transaction_id, server_product,
            signed_transaction=signed_transaction)
        if not result.ok:
            cur.close()
            return jsonify({
                "error": "verification_failed",
                "message": "The store could not verify this purchase.",
                "raw_status": result.raw_status,
            }), 402

        # In apple mode the verified transaction id (from the signed payload) is
        # authoritative — use it for recording and the uniqueness check, not the
        # client-supplied one. raw_status is 'apple_verified:<txid>'.
        effective_txid = transaction_id
        if isinstance(result.raw_status, str) and result.raw_status.startswith('apple_verified:'):
            effective_txid = result.raw_status.split(':', 1)[1]
            # Re-check idempotency on the authoritative id.
            cur.execute("SELECT id FROM purchases WHERE transaction_id = %s", (effective_txid,))
            if cur.fetchone():
                cur.close()
                return jsonify({
                    "error": "already_verified",
                    "message": "This transaction has already been processed.",
                    "transaction_id": effective_txid,
                }), 409

        # Record the purchase (UNIQUE transaction_id enforces idempotency even
        # under a race; catch the violation and report 409).
        try:
            cur.execute("""
                INSERT INTO purchases (transaction_id, store, product, user_id, amount, raw_status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (effective_txid, store, server_product, user_id, result.amount, result.raw_status))
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            cur2 = conn.cursor()
            payload = {"error": "already_verified",
                       "message": "This transaction has already been processed.",
                       "transaction_id": effective_txid}
            cur2.close()
            return jsonify(payload), 409

        # Grant the level: reset the pack and set the anniversary (paid now +
        # 1 calendar month, clamped). Paying early replaces the allowance.
        paid_at = datetime.utcnow()
        anniversary = add_one_calendar_month(paid_at)
        cur.execute("""
            INSERT INTO device_entitlement
                (user_id, level, pack_started_at, anniversary_at,
                 fresh_used, edits_used, ops_used, last_activity_at)
            VALUES (%s, %s, %s, %s, 0, 0, 0, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                level = EXCLUDED.level,
                pack_started_at = EXCLUDED.pack_started_at,
                anniversary_at = EXCLUDED.anniversary_at,
                fresh_used = 0, edits_used = 0, ops_used = 0, updated_at = NOW()
        """, (user_id, level, paid_at, anniversary))
        conn.commit()

        payload = _me_payload(cur, user_id)
        payload['verified'] = True
        payload['transaction_id'] = effective_txid
        payload['granted_level'] = level
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()
