"""
Referral Endpoints — POST /referral/create and POST /referral/redeem
=====================================================================
Flask blueprint for referral code creation and redemption.

Task [S52]: POST /referral/create — generate + store referral code, return URL.
             POST /referral/redeem — record redemption, return referrer info.
"""
import os
import logging

from flask import Blueprint, request, jsonify

from referral_engine import (
    generate_referral_code,
    store_referral,
    record_referral_redemption,
)

logger = logging.getLogger(__name__)

referral_bp = Blueprint('referral', __name__)

# Database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://admin:admin@localhost:5432/audiotours')

# Base URL for referral links
REFERRAL_BASE_URL = os.getenv('REFERRAL_BASE_URL', 'https://audioura.io')

# API key for authentication
API_KEY = os.getenv('GATEWAY_API_KEY', '')


def _require_api_key():
    """Check X-API-Key header. Returns error response or None."""
    import hmac
    if not API_KEY:
        return jsonify({"error": "service_misconfigured"}), 503
    client_key = request.headers.get('X-API-Key', '')
    if not client_key or not hmac.compare_digest(client_key, API_KEY):
        return jsonify({"error": "unauthorized"}), 401
    return None


def _get_referrer_user_id(code: str) -> str | None:
    """Look up the referrer_user_id for a code. Returns None if not found."""
    import psycopg2
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT referrer_user_id FROM referral_codes WHERE code = %s",
                (code,),
            )
            row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"Error looking up referral code {code}: {e}")
        return None


@referral_bp.route('/referral/create', methods=['POST'])
def create_referral():
    """Create a referral code for a user.

    Body: {"user_id": "..."}
    Returns: 200 {"referral_code": "ABC123", "referral_url": "https://audioura.io/join/ABC123"}
    Requires API key.
    """
    err = _require_api_key()
    if err:
        return err

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    # Generate deterministic referral code
    code = generate_referral_code(user_id)

    # Store in database
    success = store_referral(code, user_id, DATABASE_URL)
    if not success:
        return jsonify({"error": "Failed to store referral code"}), 500

    referral_url = f"{REFERRAL_BASE_URL.rstrip('/')}/join/{code}"
    logger.info(f"Referral created: user_id={user_id} code={code}")

    return jsonify({
        "referral_code": code,
        "referral_url": referral_url,
    }), 200


@referral_bp.route('/referral/redeem', methods=['POST'])
def redeem_referral():
    """Redeem a referral code.

    Body: {"referral_code": "ABC123", "new_user_id": "..."}
    Returns: 200 {"redeemed": true, "referrer_user_id": "..."}
             or 404 if code unknown.
    Requires API key.
    """
    err = _require_api_key()
    if err:
        return err

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    code = data.get('referral_code')
    new_user_id = data.get('new_user_id')

    if not code or not new_user_id:
        return jsonify({"error": "referral_code and new_user_id are required"}), 400

    # Check if code exists
    referrer_user_id = _get_referrer_user_id(code)
    if referrer_user_id is None:
        return jsonify({"error": "Referral code not found"}), 404

    # Record redemption
    success = record_referral_redemption(code, new_user_id, DATABASE_URL)
    if not success:
        return jsonify({"error": "Failed to record redemption"}), 500

    logger.info(f"Referral redeemed: code={code} new_user={new_user_id} referrer={referrer_user_id}")

    return jsonify({
        "redeemed": True,
        "referrer_user_id": referrer_user_id,
    }), 200
