"""
Referral Endpoints — POST /referral/create and POST /referral/redeem
=====================================================================
Flask blueprint for referral code creation and redemption.

Task [S52]: POST /referral/create — generate + store referral code, return URL.
             POST /referral/redeem — record redemption, return referrer info.

LOCAL-115: Added abuse controls:
  - Self-referral prevention (referrer_user_id != new_user_id)
  - Duplicate redemption guard (UNIQUE constraint + graceful 409 response)
  - In-process rate limiting (per-user sliding window)
"""
import os
import time
import logging
import threading
from collections import defaultdict

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

# ─── Rate Limiting Configuration ─────────────────────────────────────────────
# In-process sliding window: max requests per user per window.
# Keyed by user identifier (user_id for create, new_user_id for redeem).
# Falls back to IP if user identifier is unavailable.
RATE_LIMIT_MAX_REQUESTS = int(os.getenv('REFERRAL_RATE_LIMIT_MAX', '10'))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv('REFERRAL_RATE_LIMIT_WINDOW', '60'))

_rate_limit_lock = threading.Lock()
_rate_limit_store: dict = defaultdict(list)  # key -> list of timestamps


def _check_rate_limit(key: str) -> bool:
    """
    Sliding window rate limiter. Returns True if the request is allowed,
    False if the rate limit has been exceeded.

    Thread-safe via lock. In-process only — resets on container restart.
    """
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS

    with _rate_limit_lock:
        # Prune expired entries
        timestamps = _rate_limit_store[key]
        _rate_limit_store[key] = [t for t in timestamps if t > window_start]
        timestamps = _rate_limit_store[key]

        if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:
            return False

        timestamps.append(now)
        return True


def _get_rate_limit_key(identifier: str) -> str:
    """Build rate limit key from user identifier, falling back to IP."""
    if identifier:
        return f"user:{identifier}"
    # Fallback to client IP
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown')
    if ',' in ip:
        ip = ip.split(',')[0].strip()
    return f"ip:{ip}"


def _require_api_key():
    """Check X-API-Key header. Returns error response or None."""
    import hmac
    if not API_KEY:
        return jsonify({"error": "service_misconfigured"}), 503
    client_key = request.headers.get('X-API-Key', '')
    if not client_key or not hmac.compare_digest(client_key, API_KEY):
        return jsonify({"error": "unauthorized"}), 401
    return None


def _get_referrer_user_id(code: str):
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

    # Rate limit check (keyed by user_id)
    rate_key = _get_rate_limit_key(user_id)
    if not _check_rate_limit(rate_key):
        logger.warning(f"Rate limit exceeded for referral/create: {rate_key}")
        return jsonify({
            "error": "rate_limit_exceeded",
            "message": "Too many requests. Please try again later.",
            "retry_after_seconds": RATE_LIMIT_WINDOW_SECONDS,
        }), 429

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
             404 if code unknown.
             409 if already redeemed by this user.
             403 if self-referral attempt.
             429 if rate limited.
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

    # Rate limit check (keyed by new_user_id)
    rate_key = _get_rate_limit_key(new_user_id)
    if not _check_rate_limit(rate_key):
        logger.warning(f"Rate limit exceeded for referral/redeem: {rate_key}")
        return jsonify({
            "error": "rate_limit_exceeded",
            "message": "Too many requests. Please try again later.",
            "retry_after_seconds": RATE_LIMIT_WINDOW_SECONDS,
        }), 429

    # Check if code exists and get referrer
    referrer_user_id = _get_referrer_user_id(code)
    if referrer_user_id is None:
        return jsonify({"error": "Referral code not found"}), 404

    # ─── Self-referral prevention ─────────────────────────────────────────
    # Reject when the redeeming user is the code's owner.
    # Identity is based on the `secret_id` / `user_id` string passed by the
    # client. Limitation: a device reinstall can produce a new secret_id,
    # making the same physical user appear as two distinct identities. This
    # check catches the trivial case (same string) but cannot catch a user
    # who reinstalls and gets a new ID.
    if new_user_id == referrer_user_id:
        logger.warning(
            f"Self-referral attempt blocked: user={new_user_id} code={code}"
        )
        return jsonify({
            "error": "self_referral",
            "message": "You cannot redeem your own referral code.",
        }), 403

    # Record redemption (will fail gracefully on duplicate due to UNIQUE constraint)
    result = record_referral_redemption(code, new_user_id, DATABASE_URL)

    if result == "duplicate":
        logger.info(f"Duplicate redemption rejected: code={code} user={new_user_id}")
        return jsonify({
            "error": "already_redeemed",
            "message": "You have already redeemed this referral code.",
        }), 409

    if not result:
        return jsonify({"error": "Failed to record redemption"}), 500

    logger.info(f"Referral redeemed: code={code} new_user={new_user_id} referrer={referrer_user_id}")

    return jsonify({
        "redeemed": True,
        "referrer_user_id": referrer_user_id,
    }), 200
