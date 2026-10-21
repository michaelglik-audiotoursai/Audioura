#!/usr/bin/env python3
"""google_play_refund.py — LOCAL-729 / D691 / D690 / D688: the Google Play refund
path for a reimbursement (design §2 A, ClickUp wdvrdaz3tb).

On Android — and ONLY Android — Audioura can send the money back itself. The
admin runs ``refund-google <order id> [--partial USD]``; this:

  1. calls the Google Play Developer API **Orders refund** on that order id
     (``POST .../orders/{orderId}:refund``) WITH ``revoke=true`` so Google both
     refunds the buyer AND revokes the entitlement; a ``--partial USD`` does a
     partial money refund WITHOUT revoking (the buyer keeps access for the part
     they paid), mirroring Play Console's full/partial choice; then

  2. reverses the grant LOCALLY via the existing void path
     (``reconcile_voided_purchases``) so the unlock/membership/level is removed
     on our side immediately, exactly as the out-of-band Voided Purchases poller
     (LOCAL-696) would later do. The ``purchases`` receipt row is KEPT, marked
     ``voided:`` (D690: never delete a purchase-bearing row).

The Google API is INJECTED (``api_client``) so a unit test drives it with a mock
and NO network / NO real refund (task requirement: mock only). When no api_client
is given, we build one from ``GOOGLE_PLAY_SA_JSON``; when the service account is
not configured we REFUSE with a clear, non-granting error — we never pretend a
refund happened.

Pure-ish: the DB reversal uses only local tables. The caller owns the commit.
"""
from __future__ import annotations

import os
from typing import Optional, Any

GOOGLE_API_BASE = os.getenv('GOOGLE_API_BASE',
                            'https://androidpublisher.googleapis.com')
GOOGLE_PACKAGE_NAME = os.getenv(
    'GOOGLE_PACKAGE_NAME', os.getenv('APPLE_BUNDLE_ID', 'com.audioura.audiotours'))
GOOGLE_PLAY_SA_JSON = os.getenv('GOOGLE_PLAY_SA_JSON', '')


class RefundNotConfigured(Exception):
    """Raised when a Google refund is requested but no service account is
    configured — the admin tool turns this into a clear refusal and grants /
    refunds nothing."""


class RefundApiError(Exception):
    """A non-2xx from the Google Orders refund call."""
    def __init__(self, status, message):
        super().__init__(f"google refund failed ({status}): {message}")
        self.status = status
        self.message = message


def _build_default_client():
    """Build a real Google Play API client from GOOGLE_PLAY_SA_JSON, or raise
    RefundNotConfigured when the service account path is unset."""
    if not GOOGLE_PLAY_SA_JSON:
        raise RefundNotConfigured(
            "GOOGLE_PLAY_SA_JSON is not set; the Play service account is "
            "required to refund a Google order (ClickUp wdvrdayzyj). No refund "
            "was issued.")
    # Import lazily so stub/test environments need no google libraries.
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from google_play_verifier import build_api_client  # noqa: E402
    client = build_api_client(GOOGLE_PLAY_SA_JSON, package_name=GOOGLE_PACKAGE_NAME)
    if client is None:
        raise RefundNotConfigured(
            "The Play service account could not be built; no refund was issued.")
    return client


def call_orders_refund(api_client, order_id, package_name=None, revoke=True):
    """Call the Google Play Developer API Orders refund on one order.

    Uses ``api_client.refund_order(...)`` when the client exposes it (our
    GooglePlayApiClient / a test mock). Returns the api_client's response (any
    truthy value, or None for the common 204 No Content). Raises RefundApiError
    on a non-2xx (the client is expected to raise/return an error the caller can
    see). NO local DB work here — pure API call, so a test asserts the exact
    call arguments.
    """
    pkg = package_name or GOOGLE_PACKAGE_NAME
    if not hasattr(api_client, 'refund_order'):
        raise RefundApiError(
            'client_unsupported',
            'the Google API client has no refund_order method')
    return api_client.refund_order(package_name=pkg, order_id=order_id,
                                   revoke=revoke)


def refund_order(cur, order_id, api_client: Optional[Any] = None,
                 partial_usd: Optional[float] = None, package_name=None,
                 now=None):
    """Refund a Google order and reverse the local grant.

    Steps:
      * FULL refund (partial_usd is None): call Orders refund with revoke=TRUE,
        then reverse the local grant via reconcile_voided_purchases (remove the
        unlock / expire the membership / reset the level) and mark the purchase
        voided. The receipt row is kept (D690).
      * PARTIAL refund (partial_usd given): call Orders refund with revoke=FALSE
        (the buyer keeps access for the part they still paid) and DO NOT reverse
        the local grant. The money amount is recorded by the caller in the
        ledger.

    `api_client` is injected for tests (mock, no network). When None, a real
    client is built from GOOGLE_PLAY_SA_JSON, raising RefundNotConfigured when
    absent. The caller owns the transaction (commit).

    Returns a summary dict:
        {'order_id', 'revoked': bool, 'partial_usd': float|None,
         'local_reversal': <reconcile summary>|None, 'refunded': True}
    """
    if not order_id:
        raise ValueError("order_id is required")
    client = api_client if api_client is not None else _build_default_client()
    revoke = partial_usd is None  # full refund revokes; partial keeps access

    # 1. The store refund (mocked in tests).
    call_orders_refund(client, order_id, package_name=package_name, revoke=revoke)

    # 2. The local reversal — only on a FULL (revoking) refund. Reuse the exact
    #    void path the out-of-band poller uses, so a refund-google and a
    #    store-initiated refund converge to the same local state. Import lazily
    #    to avoid a hard dependency when only the API call is exercised.
    local_reversal = None
    if revoke:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from google_play_voided_poller import reconcile_voided_purchases  # noqa: E402
        local_reversal = reconcile_voided_purchases(
            cur, [{'orderId': order_id}], now=now)

    return {
        'order_id': order_id,
        'revoked': revoke,
        'partial_usd': partial_usd,
        'local_reversal': local_reversal,
        'refunded': True,
    }
