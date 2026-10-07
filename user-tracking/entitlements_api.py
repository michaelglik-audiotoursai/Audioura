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
# LEAD 2026-10-06: default 'apple' — a 'stub' default would grant a free pack to any
# POST /purchases/verify. Tests set IAP_VERIFY_MODE=stub explicitly.
IAP_VERIFY_MODE = os.getenv('IAP_VERIFY_MODE', 'apple')  # 'stub' | 'apple' | 'google'
RENEWAL_WARN_DAYS = int(os.getenv('RENEWAL_WARN_DAYS', '3'))

# [LOCAL-598] Apple verification config. The bundle id the JWS must carry; the
# path to the bundled Apple Root CA G3 we pin the x5c chain to.
APPLE_BUNDLE_ID = os.getenv('APPLE_BUNDLE_ID', 'com.audioura.audiotours')
APPLE_ROOT_CA_PATH = os.getenv(
    'APPLE_ROOT_CA_PATH',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'apple_root_ca_g3.pem'),
)

# [LOCAL-598B] Expected StoreKit environment. The signed transaction carries an
# `environment` claim; a Sandbox transaction must never grant on Production and
# vice-versa. 'Sandbox' locally, 'Production' once live. Empty disables the
# check (we pass None), which keeps older stub tests working.
APPLE_IAP_ENVIRONMENT = os.getenv('APPLE_IAP_ENVIRONMENT', '')

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


def _unauthenticated_entitlements_allowed():
    """[LOCAL-598B] True iff the local-only unauthenticated bypass is engaged.

    Read live (not cached at import) so tests can toggle it. The flag is only
    ever consulted when GATEWAY_API_KEY is empty — see _require_api_key."""
    return os.getenv('ALLOW_UNAUTHENTICATED_ENTITLEMENTS', '').lower() in ('true', '1', 'yes')


def _require_api_key():
    """X-API-Key header check — identical pattern to referral_endpoints.

    [LOCAL-598B] The Mac Mini LOCAL stack has no GATEWAY_API_KEY, and the app in
    local server mode sends no X-API-Key (endpoints.dart apiHeaders only adds
    Content-Type locally). So every entitlements/queue call returned 503
    service_misconfigured and the Plan screen, app-open and queue could not be
    tested on Michael's phone against the Mac Mini.

    Following the ST-4 ALLOW_UNAUTHENTICATED_SHARING precedent exactly: when —
    and ONLY when — GATEWAY_API_KEY is empty, honour ALLOW_UNAUTHENTICATED_
    ENTITLEMENTS=true to serve the request unauthenticated. This is NOT a silent
    fail-open: the bypass opens only when someone has explicitly set the flag,
    it is documented as local development only, it is set in the LOCAL compose
    file and nowhere else, and it NEVER defaults on. Cloud has a real
    GATEWAY_API_KEY, so this branch is never reached there and the fail-closed
    503 remains for any deployment that is genuinely misconfigured."""
    if not API_KEY:
        if _unauthenticated_entitlements_allowed():
            return None
        return jsonify({"error": "service_misconfigured"}), 503
    client_key = request.headers.get('X-API-Key', '')
    if not client_key or not hmac.compare_digest(client_key, API_KEY):
        return jsonify({"error": "unauthorized"}), 401
    return None


# [LOCAL-598B] Loud startup warning when the local-only bypass is engaged, so an
# operator who leaves it on in the wrong place sees it immediately in the logs.
# Only fires in the exact bypass condition: no key AND flag on.
if not API_KEY and _unauthenticated_entitlements_allowed():
    logger.warning(
        "[LOCAL-598B] ALLOW_UNAUTHENTICATED_ENTITLEMENTS is ON and "
        "GATEWAY_API_KEY is empty: the entitlements/queue API is serving "
        "UNAUTHENTICATED requests. This is for LOCAL DEVELOPMENT ONLY. Never "
        "enable this where the API is reachable from untrusted networks.")


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
              'can_sell', 'price_usd', 'inactivity_days', 'display_name', 'hidden']


def _get_plan(cur, level):
    cur.execute("""
        SELECT plan_id, tours_per_day, tours_per_month, fresh_per_pack,
               edits_per_pack, ops_per_pack, max_stops, max_new_stops_per_edit,
               by_reference_only, referrals_allowed, referral_period, seat_cap,
               can_sell, price_usd, inactivity_days, display_name, hidden
        FROM plans WHERE plan_id = %s
    """, (level,))
    row = cur.fetchone()
    return dict(zip(_PLAN_COLS, row)) if row else None


def _visible_levels(cur):
    """[LOCAL-604 D619] The ordered list of VISIBLE plans for the plan page:
    only rows with hidden=false, in plan order (l1, l2, l3, l4; tester and admin
    are hidden). Each entry carries the fields the app needs to render a level
    row without hardcoding any of them:
        plan_id, display_name, price_usd, can_sell, referrals_allowed,
        referral_period, max_stops.
    Ordering: by a fixed plan rank so the app always shows Introduction, Free,
    $10 Pack, Curator in that order regardless of row insertion order."""
    cur.execute("""
        SELECT plan_id, display_name, price_usd, can_sell,
               referrals_allowed, referral_period, max_stops,
               tours_per_day, tours_per_month, fresh_per_pack, ops_per_pack,
               inactivity_days
        FROM plans
        WHERE COALESCE(hidden, FALSE) = FALSE
        ORDER BY CASE plan_id
                     WHEN 'l1' THEN 1 WHEN 'l2' THEN 2
                     WHEN 'l3' THEN 3 WHEN 'l4' THEN 4
                     ELSE 99 END,
                 plan_id
    """)
    out = []
    for r in cur.fetchall():
        (plan_id, display_name, price_usd, can_sell, referrals_allowed,
         referral_period, max_stops, tpd, tpm, fpp, opp, inactivity_days) = r
        out.append({
            'plan_id': plan_id,
            'display_name': display_name or plan_id,
            'price_usd': float(price_usd) if price_usd is not None else 0.0,
            'can_sell': bool(can_sell),
            'referrals_allowed': referrals_allowed or 0,
            'referral_period': referral_period,
            'max_stops': max_stops,
            'tours_per_day': tpd,
            'tours_per_month': tpm,
            'fresh_per_pack': fpp,
            'ops_per_pack': opp,
            # [LOCAL-610 req 3] passthrough so the plan page can show the Free
            # inactivity rule ("After N days…") with the Free level's own N even
            # when the current device is on another level.
            'inactivity_days': inactivity_days,
        })
    return out


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

    # [LOCAL-596] Queue + offer status for the L2 seat lifecycle. queue_position
    # is the device's 1-based place in the FIFO waiting line (None if it is not
    # waiting). pending_offer is its live, unexpired claim offer (None if it has
    # none). Both come from the shared seat core so the API and the job agree.
    queue_position = None
    pending_offer = None
    try:
        import l2_seats
        queue_position = l2_seats.queue_position(cur, user_id)
        offer = l2_seats.pending_offer(cur, user_id)
        if offer:
            pending_offer = {
                'code': offer['code'],
                'expires_at': offer['expires_at'].isoformat() if offer['expires_at'] else None,
            }
    except Exception as e:  # pragma: no cover - seat tables optional pre-015
        logger.warning(f"[LOCAL-596] queue/offer lookup failed for {user_id}: {e}")

    return {
        'user_id': user_id,
        'level': state['level'],
        # [LOCAL-604 D619] The current level's human display name (falls back to
        # the plan_id if unset), and the ordered list of VISIBLE levels for the
        # plan page (tester/admin excluded). The app renders names from here and
        # hardcodes nothing.
        'display_name': (plan.get('display_name') if plan else None) or state['level'],
        'levels': _visible_levels(cur),
        # [LOCAL-610 req 3] The current level's inactivity window, straight from
        # plans.inactivity_days (the SAME column l2_seat_job reads to evict idle
        # L2 devices). Passthrough only — no behaviour changes here. The plan
        # page shows "After N days without a visit…" using this N instead of a
        # hardcoded 7, so the copy can never drift from the DB value.
        'inactivity_days': (plan.get('inactivity_days') if plan else None),
        'anniversary_at': ann.isoformat() if ann else None,
        'allowances_left': _allowances_left(cur, state, plan),
        'warn_renewal': _warn_renewal(ann, now),
        'renewal_prompt': renewal_due,
        'can_sell': bool(plan['can_sell']) if plan else False,
        'queue_position': queue_position,
        'pending_offer': pending_offer,
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
                expected_environment=(APPLE_IAP_ENVIRONMENT or None),
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


# ───────────────────────────────────────────────────────────────────────────
# [LOCAL-596] L2 seat queue + claim endpoints
# ───────────────────────────────────────────────────────────────────────────
@entitlements_bp.route('/l2/queue/join', methods=['POST'])
def l2_queue_join():
    """Join the FIFO queue for a free L2 seat.

    Body: {"user_id": "...", "email": "..."}
    L1 only (a device already holding an L2 seat is refused). Idempotent: a
    device already waiting/holding an offer gets its current position back.
    [LOCAL-604 D619] An optional email is stored on the queue row so the offer
    code can be emailed when a seat frees; it is held only while queued/offered
    and nulled on claim, leave or expiry. Returns 200 {queue_position, status}
    on success, 409 if already L2.
    """
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    email = data.get('email')
    if email is not None:
        email = str(email).strip() or None

    import l2_seats
    conn = _get_db()
    try:
        cur = conn.cursor()
        result = l2_seats.join_queue(cur, user_id, email=email)
        conn.commit()
        if not result['joined'] and result.get('reason') == 'already_l2':
            cur.close()
            return jsonify({
                "error": "already_l2",
                "message": "This device already holds an L2 seat.",
            }), 409
        payload = _me_payload(cur, user_id)
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()


@entitlements_bp.route('/l2/queue/leave', methods=['POST'])
def l2_queue_leave():
    """Leave the FIFO queue (idempotent).

    Body: {"user_id": "..."}
    Marks the queue row 'left' and expires any live offer. Always 200.
    """
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    import l2_seats
    conn = _get_db()
    try:
        cur = conn.cursor()
        l2_seats.leave_queue(cur, user_id)
        conn.commit()
        payload = _me_payload(cur, user_id)
        cur.close()
        return jsonify(payload), 200
    finally:
        conn.close()


def _claim_referral(cur, user_id, code):
    """[LOCAL-604 D619] Cursor-based friend-invitation (referral) redemption for
    the single claim box. Mirrors referral_engine.redeem_referral_for_seat's
    checks (self, duplicate, referrer allowance by period, 100-seat cap) but
    composes inside the caller's transaction and cursor so the claim route works
    in the user-api container, whose build context cannot import repo-root
    referral_engine. The repo-root engine remains the authority for the
    /referral/redeem HTTP path; this is the same rules, cursor-style.

    Returns {'ok': bool, 'code': str, 'message': str, 'matched': bool}. matched
    is False when the code is not a referral code at all (so the caller can tell
    'no such code' from 'a referral code that was refused').
    """
    import l2_seats
    if not code or not str(code).strip():
        return {'ok': False, 'code': 'claim_invalid_code', 'matched': False,
                'message': 'No code was provided.'}

    # Referral codes live in referral_codes.code. Absent table (never created on
    # a fresh DB) → treat as "not a referral code".
    try:
        cur.execute("SELECT referrer_user_id FROM referral_codes WHERE code = %s", (code,))
    except Exception:
        return {'ok': False, 'code': 'claim_invalid_code', 'matched': False,
                'message': 'Not a referral code.'}
    row = cur.fetchone()
    if not row:
        return {'ok': False, 'code': 'claim_invalid_code', 'matched': False,
                'message': 'Not a referral code.'}
    referrer_user_id = row[0]

    if user_id == referrer_user_id:
        return {'ok': False, 'code': 'referral_self', 'matched': True,
                'message': 'You cannot redeem your own invitation code.'}

    cur.execute("""
        SELECT 1 FROM referral_redemptions
        WHERE referral_code = %s AND new_user_id = %s
    """, (code, user_id))
    if cur.fetchone():
        return {'ok': False, 'code': 'referral_duplicate', 'matched': True,
                'message': 'You have already used this invitation code.'}

    # Referrer allowance from the referrer's plan row.
    cur.execute("SELECT level FROM device_entitlement WHERE user_id = %s", (referrer_user_id,))
    lrow = cur.fetchone()
    ref_level = lrow[0] if lrow else 'l1'
    cur.execute("SELECT referrals_allowed, referral_period FROM plans WHERE plan_id = %s",
                (ref_level,))
    arow = cur.fetchone()
    allowed = (arow[0] or 0) if arow else 0
    period = arow[1] if arow else None
    if allowed <= 0:
        return {'ok': False, 'code': 'referral_allowance_spent', 'matched': True,
                'message': 'This invitation code can no longer grant seats.'}
    window = "AND rr.redeemed_at >= date_trunc('month', CURRENT_DATE)" if period == 'month' else ""
    cur.execute(f"""
        SELECT COUNT(*) FROM referral_redemptions rr
        JOIN referral_codes rc ON rc.code = rr.referral_code
        WHERE rc.referrer_user_id = %s {window}
    """, (referrer_user_id,))
    if cur.fetchone()[0] >= allowed:
        return {'ok': False, 'code': 'referral_allowance_spent', 'matched': True,
                'message': 'This inviter has used all of their invitations.'}

    # Seat free under the cap (referral seats count against the 100 cap).
    l2_seats._acquire_seat_lock(cur)
    cap = l2_seats.get_seat_cap(cur)
    cur.execute("SELECT level FROM device_entitlement WHERE user_id = %s", (user_id,))
    de = cur.fetchone()
    already_l2 = de is not None and de[0] == 'l2'
    if not already_l2 and cap is not None and l2_seats.seats_in_use(cur) >= cap:
        return {'ok': False, 'code': 'referral_seats_full', 'matched': True,
                'message': 'The free level is full right now, so this invite can’t be used yet.'}

    cur.execute("UPDATE referral_codes SET redemption_count = redemption_count + 1 WHERE code = %s",
                (code,))
    cur.execute("INSERT INTO referral_redemptions (referral_code, new_user_id) VALUES (%s, %s)",
                (code, user_id))
    cur.execute("""
        INSERT INTO device_entitlement (user_id, level, last_activity_at)
        VALUES (%s, 'l2', NOW())
        ON CONFLICT (user_id) DO UPDATE SET level = 'l2', updated_at = NOW()
    """, (user_id,))
    return {'ok': True, 'code': 'ok', 'matched': True,
            'message': 'Invitation redeemed — you now have a free seat.'}


@entitlements_bp.route('/l2/claim', methods=['POST'])
def l2_claim():
    """Claim a level/seat with a single code box ([LOCAL-604 D619]).

    Body: {"user_id": "...", "code": "..."}
    The server decides which of THREE code kinds the code is, in this order:
      1. LEVEL CODE (level_codes, sha256 hash) — LEAD's code that moves the
         device to ANY level (incl. tester/admin), reusable, revocable. A level
         switch to l3/l4 starts a test pack. 200 on success; a revoked level
         code is refused 403 (level_code_revoked).
      2. QUEUE-OFFER CODE (l2_offers) — the queue claim offer. Grants L2 under
         the cap. Structured refusals: claim_wrong_device (403),
         claim_expired (409), claim_seats_full (409).
      3. FRIEND INVITATION (referral) CODE (referral_codes) — grants L2 under
         the cap, gated by the referrer's allowance. Refusals: referral_self
         (403), referral_duplicate (409), referral_allowance_spent (409),
         referral_seats_full (409).
    If the code matches none, 400 claim_invalid_code.
    On success returns the refreshed /me payload with claimed=true.
    """
    err = _require_api_key()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    code = data.get('code')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    import l2_seats
    import level_codes
    conn = _get_db()
    try:
        cur = conn.cursor()

        # ── 1. Level code (checked first) ──────────────────────────────────
        lc = level_codes.claim_level_code(cur, user_id, code)
        if lc['ok']:
            conn.commit()
            payload = _me_payload(cur, user_id)
            payload['claimed'] = True
            payload['claim_kind'] = 'level_code'
            payload['granted_level'] = lc['level']
            cur.close()
            return jsonify(payload), 200
        if lc['code'] == level_codes.LEVEL_REVOKED:
            conn.rollback()
            cur.close()
            return jsonify({
                "error": lc['code'], "error_code": lc['code'],
                "message": lc['message'],
            }), 403
        # LEVEL_NOT_FOUND → fall through to the offer path.

        # ── 2. Queue-offer code ────────────────────────────────────────────
        result = l2_seats.claim_seat(cur, user_id, code)
        if result['ok']:
            conn.commit()
            payload = _me_payload(cur, user_id)
            payload['claimed'] = True
            payload['claim_kind'] = 'offer'
            cur.close()
            return jsonify(payload), 200
        # A genuine offer code that failed for a reason OTHER than "no such
        # code" is a real offer refusal — return it. CLAIM_BAD_CODE means the
        # code is not an offer code, so fall through to the referral path.
        if result['code'] != l2_seats.CLAIM_BAD_CODE:
            conn.rollback()
            status_map = {
                l2_seats.CLAIM_WRONG_DEVICE: 403,
                l2_seats.CLAIM_EXPIRED: 409,
                l2_seats.CLAIM_SEATS_FULL: 409,
            }
            http = status_map.get(result['code'], 400)
            cur.close()
            return jsonify({
                "error": result['code'], "error_code": result['code'],
                "message": result['message'],
            }), http

        # ── 3. Friend invitation (referral) code ───────────────────────────
        ref = _claim_referral(cur, user_id, code)
        if ref['ok']:
            conn.commit()
            payload = _me_payload(cur, user_id)
            payload['claimed'] = True
            payload['claim_kind'] = 'referral'
            cur.close()
            return jsonify(payload), 200
        if ref['matched']:
            conn.rollback()
            status_map = {
                'referral_self': 403,
                'referral_duplicate': 409,
                'referral_allowance_spent': 409,
                'referral_seats_full': 409,
            }
            http = status_map.get(ref['code'], 400)
            cur.close()
            return jsonify({
                "error": ref['code'], "error_code": ref['code'],
                "message": ref['message'],
            }), http

        # ── Matched nothing ────────────────────────────────────────────────
        conn.rollback()
        cur.close()
        return jsonify({
            "error": l2_seats.CLAIM_BAD_CODE,
            "error_code": l2_seats.CLAIM_BAD_CODE,
            "message": "That code is not valid.",
        }), 400
    finally:
        conn.close()
