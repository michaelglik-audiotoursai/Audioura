"""
RevenueCat Webhook Endpoint — receives Apple IAP events via RevenueCat.

Idempotent: same event_id delivered twice processes once (LOCAL-66 pattern).
D14: Unverifiable payload → 401, grants nothing.
Never shares exception handler with instrumentation.

Mounts on the orchestrator at /webhooks/revenuecat.
"""

import json
import logging
import os

from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

revenuecat_webhook_bp = Blueprint("revenuecat_webhook", __name__)


def _get_provider():
    """
    Get the active payment provider.
    Only returns the RevenueCat provider if configured; otherwise rejects.
    """
    provider_type = os.environ.get("PAYMENT_PROVIDER", "fake")
    if provider_type != "revenuecat":
        return None

    from revenuecat_payment_provider import RevenueCatPaymentProvider
    return RevenueCatPaymentProvider()


@revenuecat_webhook_bp.route("/webhooks/revenuecat", methods=["POST"])
def handle_revenuecat_webhook():
    """
    POST /webhooks/revenuecat

    Receives RevenueCat server-to-server notifications for:
      - Subscription renewals
      - Subscription expirations
      - Refunds (Apple-initiated)
      - Billing retry (payment failed)
      - Cancellations

    Idempotency: RevenueCat and Apple both retry delivery. The provider's
    handle_webhook() uses event_id as the idempotency key — a replayed
    event returns 200 without reprocessing.

    Security (D14):
      - Verifies the Authorization header matches our webhook secret.
      - If PAYMENT_PROVIDER != 'revenuecat', rejects with 404.
      - An unverifiable payload grants nothing.
    """
    # ─── D14: Verify this endpoint is enabled ────────────────────────────
    provider = _get_provider()
    if provider is None:
        # Payment provider is not RevenueCat — this endpoint should not exist
        logger.warning("[WEBHOOK] RevenueCat webhook called but PAYMENT_PROVIDER != 'revenuecat'")
        return jsonify({"error": "Not configured"}), 404

    # ─── D14: Verify webhook authenticity ────────────────────────────────
    # RevenueCat sends an Authorization header with the configured secret
    auth_header = request.headers.get("Authorization", "")
    expected_secret = os.environ.get("REVENUECAT_WEBHOOK_SECRET", "")

    if not expected_secret:
        # No secret configured — cannot verify, fail closed
        logger.error("[WEBHOOK] REVENUECAT_WEBHOOK_SECRET not set — rejecting webhook")
        return jsonify({"error": "Webhook secret not configured"}), 500

    # RevenueCat sends: Authorization: Bearer <secret>
    provided_secret = auth_header.replace("Bearer ", "").strip()
    if provided_secret != expected_secret:
        logger.error("[WEBHOOK] Invalid webhook authorization — rejecting")
        return jsonify({"error": "Unauthorized"}), 401

    # ─── Parse payload ───────────────────────────────────────────────────
    try:
        payload = request.get_json(force=True)
    except Exception as e:
        logger.error(f"[WEBHOOK] Failed to parse JSON body: {e}")
        return jsonify({"error": "Invalid JSON"}), 400

    if not payload or "event" not in payload:
        logger.error("[WEBHOOK] Missing 'event' in payload")
        return jsonify({"error": "Missing event"}), 400

    # ─── Process (idempotent) ────────────────────────────────────────────
    # This is a CONTROL path — it MUST NOT share exception handling with
    # any instrumentation or logging that fails open. (D14)
    try:
        result = provider.handle_webhook(payload)
    except Exception as e:
        # D14: Control fails CLOSED. Unknown error → no state change, 500.
        logger.error(f"[WEBHOOK] Unhandled exception in handle_webhook: {e}")
        return jsonify({"error": "Internal error"}), 500

    if result.handled:
        logger.info(
            f"[WEBHOOK] Processed: type={result.event_type}, "
            f"user={result.user_id}, details={result.details}"
        )
        return jsonify({
            "status": "ok",
            "event_type": result.event_type.value if result.event_type else None,
            "details": result.details,
        }), 200
    else:
        logger.warning(f"[WEBHOOK] Not handled: {result.details}")
        return jsonify({
            "status": "not_handled",
            "details": result.details,
        }), 400
