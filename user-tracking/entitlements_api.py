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

# product -> level mapping. Data, not logic: a new product is one dict entry.
PRODUCT_LEVELS = {
    'l3_pack_10': 'l3',
    'l4_round_25': 'l4',
}


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
# IAP verifier interface + sandbox stub
# ───────────────────────────────────────────────────────────────────────────
class VerificationResult:
    def __init__(self, ok, raw_status, amount=None):
        self.ok = ok
        self.raw_status = raw_status
        self.amount = amount


def verify_purchase(store, transaction_id, product):
    """Verify an IAP against the store. IAP_VERIFY_MODE selects the backend.

    stub   : accept any non-empty transaction_id (sandbox). The real
             Apple App Store Server API / Google Play Developer API land in
             LOCAL-598 as additional branches here.
    """
    if IAP_VERIFY_MODE == 'stub':
        if not transaction_id:
            return VerificationResult(False, 'stub_rejected_empty_transaction')
        plan_amounts = {'l3_pack_10': 10.00, 'l4_round_25': 25.00}
        return VerificationResult(True, 'stub_verified', plan_amounts.get(product))
    # LOCAL-598: real verification
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
    if not all([store, transaction_id, product, user_id]):
        return jsonify({
            "error": "missing_fields",
            "message": "store, transaction_id, product and user_id are all required.",
        }), 400

    level = PRODUCT_LEVELS.get(product)
    if level is None:
        return jsonify({
            "error": "unknown_product",
            "message": f"Unknown product '{product}'.",
        }), 400

    conn = _get_db()
    try:
        cur = conn.cursor()

        # Idempotency: the same transaction_id can never grant twice.
        cur.execute("SELECT id FROM purchases WHERE transaction_id = %s", (transaction_id,))
        if cur.fetchone():
            cur.close()
            return jsonify({
                "error": "already_verified",
                "message": "This transaction has already been processed.",
                "transaction_id": transaction_id,
            }), 409

        # Verify with the store (sandbox stub by default).
        result = verify_purchase(store, transaction_id, product)
        if not result.ok:
            cur.close()
            return jsonify({
                "error": "verification_failed",
                "message": "The store could not verify this purchase.",
                "raw_status": result.raw_status,
            }), 402

        # Record the purchase (UNIQUE transaction_id enforces idempotency even
        # under a race; catch the violation and report 409).
        try:
            cur.execute("""
                INSERT INTO purchases (transaction_id, store, product, user_id, amount, raw_status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (transaction_id, store, product, user_id, result.amount, result.raw_status))
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            cur2 = conn.cursor()
            payload = {"error": "already_verified",
                       "message": "This transaction has already been processed.",
                       "transaction_id": transaction_id}
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
        payload['transaction_id'] = transaction_id
        payload['granted_level'] = level
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()
