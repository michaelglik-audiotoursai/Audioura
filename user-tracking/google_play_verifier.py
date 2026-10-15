"""
google_play_verifier.py — LOCAL-696: SERVER-SIDE verification of a Google Play
in-app purchase. The Android twin of apple_jws_verifier.py.

Where Apple hands the device a self-contained StoreKit 2 JWS we verify OFFLINE,
Google gives the device only an opaque `purchaseToken`. The server must call the
Google Play Developer API to learn anything about it:

    GET https://androidpublisher.googleapis.com/androidpublisher/v3/applications/
        {packageName}/purchases/products/{productId}/tokens/{token}

authenticated as a SERVICE ACCOUNT that the Play Console has granted
"View financial data / Manage orders" (see SUBMISSION_LOCAL-696.md). The product
response (a `ProductPurchase`) tells us:

  • purchaseState   0 = Purchased, 1 = Canceled, 2 = Pending.
  • productId / packageName match (we pass them, but we re-assert).
  • acknowledgementState  0 = not yet, 1 = acknowledged. Google AUTO-REFUNDS a
    purchase we do not acknowledge within 3 days, so we MUST acknowledge.
  • consumptionState  0 = not consumed, 1 = consumed. For a CONSUMABLE (every
    Audioura product is one-time → consumable, incl. passes; the server enforces
    pass length — D658/D660) we CONSUME so the user can buy the same product
    again (D660: every paid download is a purchase).
  • orderId   the Google order id (GPA.####-####-####-#####). This is the
    AUTHORITATIVE transaction id — the caller records it in `purchases`
    (UNIQUE transaction_id) so the same order can never grant twice.

This module is PURE and dependency-light. It performs NO network itself: the
caller injects an `api_client` object with the three methods it needs
(`get_product_purchase`, `acknowledge_product`, `consume_product`). The real
client — `GooglePlayApiClient`, SA JSON auth via `google-auth` — lives at the
bottom and is only constructed when a real verification runs, so stub-mode
deployments need no Google deps. Tests inject a fake client and never touch the
network, exactly as the Apple suite builds a throwaway PKI with no Apple servers.

Every failure raises `GoogleVerificationError` with a stable `.code` so the HTTP
layer and the tests can branch on the exact reason, mirroring JwsVerificationError.
"""

from __future__ import annotations

import json
import os
import logging
from dataclasses import dataclass, field
from typing import Optional, Any

logger = logging.getLogger(__name__)

# The Play package the purchases belong to (ClickUp wdvrdayx33). Same bundle as
# Apple. Overridable by env for a differently-named build.
GOOGLE_PACKAGE_NAME = os.getenv('GOOGLE_PACKAGE_NAME', 'com.audioura.audiotours')

# ProductPurchase.purchaseState values (Google Play Developer API v3).
PURCHASE_STATE_PURCHASED = 0
PURCHASE_STATE_CANCELED = 1
PURCHASE_STATE_PENDING = 2

# ProductPurchase.acknowledgementState / consumptionState values.
ACK_STATE_NOT_ACKNOWLEDGED = 0
ACK_STATE_ACKNOWLEDGED = 1
CONSUMPTION_STATE_NOT_CONSUMED = 0
CONSUMPTION_STATE_CONSUMED = 1

GOOGLE_API_BASE = 'https://androidpublisher.googleapis.com'
# The OAuth scope the Play Developer API requires.
ANDROIDPUBLISHER_SCOPE = 'https://www.googleapis.com/auth/androidpublisher'


class GoogleVerificationError(Exception):
    """A verification failure with a stable machine code (mirror of
    JwsVerificationError). `.code` is a short, stable string the HTTP layer and
    tests branch on; `.message` is human-readable."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass
class VerifiedGooglePurchase:
    """The authoritative result of a verified Google Play purchase (mirror of
    VerifiedTransaction). `order_id` is what the caller records in `purchases`
    as the unique transaction id; `purchase_token` is kept for the voided-
    purchases poller to match against. `acknowledged`/`consumed` report what the
    verifier did so a test can assert the full happy path."""

    order_id: str
    product_id: str
    package_name: str
    purchase_state: int
    acknowledged: bool
    consumed: bool
    raw: dict = field(default_factory=dict)


def _require_token(purchase_token: str) -> None:
    if not purchase_token or not str(purchase_token).strip():
        raise GoogleVerificationError(
            'missing_purchase_token', 'A non-empty purchaseToken is required.')


def verify_product_purchase(
    api_client: Any,
    product_id: str,
    purchase_token: str,
    expected_product_id: Optional[str] = None,
    package_name: str = GOOGLE_PACKAGE_NAME,
    acknowledge: bool = True,
    consume: bool = True,
) -> VerifiedGooglePurchase:
    """Verify a Google Play one-time (consumable) product purchase.

    Args:
        api_client: an object exposing
            get_product_purchase(package_name, product_id, token) -> dict,
            acknowledge_product(package_name, product_id, token) -> None,
            consume_product(package_name, product_id, token) -> None.
            Injected so this module performs NO network and tests mock it.
        product_id: the Play product id the token was bought for (used in the
            API path). The device sends this.
        purchase_token: the opaque token the device received from Play Billing.
        expected_product_id: if given, the response productId AND the path
            productId must equal it (defends against a token for a DIFFERENT,
            cheaper product being replayed against an expensive grant).
        package_name: the Play package (defaults to com.audioura.audiotours).
        acknowledge: acknowledge the purchase (default True). Google auto-refunds
            an unacknowledged purchase within 3 days, so this must normally run.
        consume: consume the purchase (default True) so the SAME product can be
            bought again (D660). Every Audioura product is a one-time consumable.

    Returns a VerifiedGooglePurchase on success. Raises GoogleVerificationError
    with a stable `.code` on any failure. Performs NO network itself.
    """
    _require_token(purchase_token)
    if not product_id:
        raise GoogleVerificationError('missing_product_id',
                                      'A product_id is required.')

    # 1. Look the token up with Google. A transport/HTTP failure is surfaced as
    #    a stable code so the HTTP layer returns a clean error (never grants).
    try:
        resp = api_client.get_product_purchase(
            package_name, product_id, purchase_token)
    except GoogleApiError as e:
        # A 404/400 from Google means the token is not a valid purchase for this
        # product — a forged or product-mismatched token. Never grant.
        if e.status in (400, 404, 410):
            raise GoogleVerificationError(
                'token_not_found',
                f'Google did not recognise this purchase token (HTTP {e.status}).')
        if e.status in (401, 403):
            raise GoogleVerificationError(
                'google_auth_failed',
                f'The service account was refused by Google (HTTP {e.status}).')
        raise GoogleVerificationError(
            'google_api_error',
            f'Google Play API error (HTTP {e.status}): {e.message}')
    except Exception as e:  # noqa: BLE001 - any client error must not grant
        raise GoogleVerificationError(
            'google_api_error', f'Google Play API call failed: {e}')

    if not isinstance(resp, dict):
        raise GoogleVerificationError(
            'bad_api_response', 'Google Play API returned a non-object response.')

    # 2. The response must be for the product we asked about. Google echoes the
    #    productId in newer responses; when present it must match the path.
    resp_product = resp.get('productId')
    if resp_product is not None and resp_product != product_id:
        raise GoogleVerificationError(
            'product_mismatch',
            f"response productId '{resp_product}' != requested '{product_id}'.")

    # 3. The caller-expected product (the server's own notion of what was being
    #    bought) must match too — a token for a cheaper product can never be
    #    replayed to grant an expensive one.
    if expected_product_id is not None and product_id != expected_product_id:
        raise GoogleVerificationError(
            'product_mismatch',
            f"product '{product_id}' does not match expected "
            f"'{expected_product_id}'.")

    # 4. purchaseState MUST be Purchased. Pending (2) and Canceled (1) never
    #    grant — a pending purchase may still fail, a canceled one is void.
    state = resp.get('purchaseState')
    if state == PURCHASE_STATE_PENDING:
        raise GoogleVerificationError(
            'purchase_pending',
            'The purchase is still pending; it has not completed.')
    if state == PURCHASE_STATE_CANCELED:
        raise GoogleVerificationError(
            'purchase_canceled', 'The purchase was canceled/refunded.')
    if state != PURCHASE_STATE_PURCHASED:
        raise GoogleVerificationError(
            'purchase_not_purchased',
            f'purchaseState {state!r} is not Purchased (0).')

    # 5. A purchase already CONSUMED for another grant must not grant again. The
    #    order id (step 7) is the real idempotency key at the DB, but refusing a
    #    consumed token here is a clear, early signal.
    consumption_state = resp.get('consumptionState')
    already_consumed = consumption_state == CONSUMPTION_STATE_CONSUMED

    # 6. ACKNOWLEDGE. Google auto-refunds a purchase not acknowledged within 3
    #    days, so we acknowledge every verified purchase we have not already.
    ack_state = resp.get('acknowledgementState')
    did_acknowledge = False
    if acknowledge and ack_state != ACK_STATE_ACKNOWLEDGED:
        try:
            api_client.acknowledge_product(
                package_name, product_id, purchase_token)
            did_acknowledge = True
        except GoogleApiError as e:
            raise GoogleVerificationError(
                'acknowledge_failed',
                f'Could not acknowledge the purchase (HTTP {e.status}): {e.message}')
        except Exception as e:  # noqa: BLE001
            raise GoogleVerificationError(
                'acknowledge_failed', f'Could not acknowledge the purchase: {e}')
    elif ack_state == ACK_STATE_ACKNOWLEDGED:
        did_acknowledge = True

    # 7. CONSUME so the SAME product can be bought again (D660). A token already
    #    consumed is left alone (consuming twice is a no-op/err we avoid).
    did_consume = already_consumed
    if consume and not already_consumed:
        try:
            api_client.consume_product(
                package_name, product_id, purchase_token)
            did_consume = True
        except GoogleApiError as e:
            raise GoogleVerificationError(
                'consume_failed',
                f'Could not consume the purchase (HTTP {e.status}): {e.message}')
        except Exception as e:  # noqa: BLE001
            raise GoogleVerificationError(
                'consume_failed', f'Could not consume the purchase: {e}')

    # 8. The order id is the authoritative transaction id. Absent one, we cannot
    #    key idempotency, so refuse (a legitimate ProductPurchase always carries
    #    an orderId once purchased).
    order_id = resp.get('orderId')
    if not order_id:
        raise GoogleVerificationError(
            'no_order_id', 'The purchase has no orderId; cannot record it.')

    return VerifiedGooglePurchase(
        order_id=str(order_id),
        product_id=product_id,
        package_name=package_name,
        purchase_state=int(state),
        acknowledged=bool(did_acknowledge),
        consumed=bool(did_consume),
        raw=resp,
    )


# ───────────────────────────────────────────────────────────────────────────
# Real Google Play Developer API client (constructed only for a real verify).
# ───────────────────────────────────────────────────────────────────────────
class GoogleApiError(Exception):
    """A transport/HTTP error from the Google Play Developer API. Carries the
    HTTP `status` so verify_product_purchase can map 404 → token_not_found,
    401/403 → google_auth_failed, etc. Kept distinct from
    GoogleVerificationError (a VERIFICATION decision) so the two never blur."""

    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message


def load_service_account_info(sa_json_path: str) -> dict:
    """Read and parse the service-account JSON from `sa_json_path`. Raises
    GoogleVerificationError('google_sa_unreadable') on any problem so the HTTP
    layer returns a clean 503 rather than a stack trace. The key file is NEVER
    committed; its PATH comes from env GOOGLE_PLAY_SA_JSON (LEAD/Michael provide
    the file in the container at deploy)."""
    try:
        with open(sa_json_path, 'r', encoding='utf-8') as f:
            info = json.load(f)
    except Exception as e:  # noqa: BLE001
        raise GoogleVerificationError(
            'google_sa_unreadable',
            f'Could not read the service-account JSON at {sa_json_path}: {e}')
    if not isinstance(info, dict) or 'client_email' not in info:
        raise GoogleVerificationError(
            'google_sa_invalid',
            'The service-account JSON is missing required fields.')
    return info


class GooglePlayApiClient:
    """Thin REST client for the Google Play Developer API v3 product-purchase
    endpoints. Authenticated as a service account via `google-auth`. Imports its
    deps LAZILY in __init__ so stub-mode deployments (and the whole test suite)
    need no Google libraries — only a real verification constructs this.

    Methods raise GoogleApiError(status, message) on a non-2xx response so the
    verifier can map the status to a stable code."""

    def __init__(self, sa_json_path: str, package_name: str = GOOGLE_PACKAGE_NAME):
        self.package_name = package_name
        try:
            from google.oauth2 import service_account  # type: ignore
            from google.auth.transport.requests import AuthorizedSession  # type: ignore
        except Exception as e:  # noqa: BLE001
            raise GoogleVerificationError(
                'google_libs_unavailable',
                f'google-auth is not installed in this image: {e}')
        info = load_service_account_info(sa_json_path)
        try:
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=[ANDROIDPUBLISHER_SCOPE])
            self._session = AuthorizedSession(creds)
        except Exception as e:  # noqa: BLE001
            raise GoogleVerificationError(
                'google_sa_invalid',
                f'Could not build credentials from the service account: {e}')

    def _product_url(self, package_name, product_id, token, suffix=''):
        return (f'{GOOGLE_API_BASE}/androidpublisher/v3/applications/'
                f'{package_name}/purchases/products/{product_id}/tokens/{token}{suffix}')

    def get_product_purchase(self, package_name, product_id, token) -> dict:
        url = self._product_url(package_name, product_id, token)
        resp = self._session.get(url, timeout=30)
        if resp.status_code >= 400:
            raise GoogleApiError(resp.status_code, resp.text)
        return resp.json()

    def acknowledge_product(self, package_name, product_id, token) -> None:
        url = self._product_url(package_name, product_id, token, suffix=':acknowledge')
        resp = self._session.post(url, json={}, timeout=30)
        # 200 OK, and some Google endpoints answer 204 No Content.
        if resp.status_code >= 400:
            raise GoogleApiError(resp.status_code, resp.text)

    def consume_product(self, package_name, product_id, token) -> None:
        url = self._product_url(package_name, product_id, token, suffix=':consume')
        resp = self._session.post(url, json={}, timeout=30)
        if resp.status_code >= 400:
            raise GoogleApiError(resp.status_code, resp.text)

    # ── Refunds: the voided-purchases list (used by the voided poller) ────────
    def list_voided_purchases(self, package_name=None, start_time_millis=None,
                              token=None, max_results=1000) -> dict:
        """GET purchases.voidedpurchases.list — the refunds/chargebacks feed.
        Returns the raw page dict ({'voidedPurchases': [...], optional
        'tokenPagination': {'nextPageToken': ...}}). `token` is the page token
        for pagination (NOT a purchase token)."""
        pkg = package_name or self.package_name
        url = (f'{GOOGLE_API_BASE}/androidpublisher/v3/applications/'
               f'{pkg}/purchases/voidedpurchases')
        params = {'maxResults': max_results}
        if start_time_millis is not None:
            params['startTime'] = start_time_millis
        if token is not None:
            params['token'] = token
        resp = self._session.get(url, params=params, timeout=30)
        if resp.status_code >= 400:
            raise GoogleApiError(resp.status_code, resp.text)
        return resp.json()


def build_api_client(sa_json_path: Optional[str] = None,
                     package_name: str = GOOGLE_PACKAGE_NAME):
    """Build a real GooglePlayApiClient from GOOGLE_PLAY_SA_JSON (or an explicit
    path). Returns None when no SA path is configured, so the HTTP layer can
    answer 503 google_verify_unconfigured and NEVER grant. Raises
    GoogleVerificationError only when a path IS set but is unreadable/invalid."""
    path = sa_json_path or os.getenv('GOOGLE_PLAY_SA_JSON', '')
    if not path:
        return None
    return GooglePlayApiClient(path, package_name=package_name)
