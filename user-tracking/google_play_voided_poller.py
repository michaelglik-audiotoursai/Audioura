"""
google_play_voided_poller.py — LOCAL-696: the REFUND path for Google Play.

Apple's refund handling is at verify time: a StoreKit 2 JWS that carries a
`revocationDate` never grants (apple_jws_verifier → transaction_revoked). But a
refund usually happens AFTER a purchase was already verified and granted, and
Google surfaces those out-of-band via the Play Developer API's
`purchases.voidedpurchases.list` feed (refunds, chargebacks, revocations). This
poller reads that feed and REVERSES each grant we previously made, mirroring the
spirit of Apple's refund handling (remove the unlock / end the membership /
drop a level pack).

Design:
  • PURE core: `reconcile_voided_purchases(cur, voided_items, now=...)` takes an
    already-fetched list of voided items (each a dict from the Google feed) and
    reverses whatever each one granted, using ONLY the local tables. It performs
    NO network, so a test drives it with a hand-built list and asserts the DB.
  • `run_poller()` wires the real GooglePlayApiClient (SA JSON via
    GOOGLE_PLAY_SA_JSON) to page the feed and hand the items to the core. It is
    what a cron/systemd timer calls; it never runs in a request.

A voided item carries `orderId` and/or `purchaseToken`. We recorded the Google
orderId as purchases.transaction_id (and the token inside raw_status), so we match
a void to its purchase by orderId first, then by token. Reversal is idempotent:
re-voiding an already-reversed purchase is a no-op. The `purchases` row is marked
(raw_status prefixed 'voided:') and left in place as an audit trail — we never
DELETE a ledger row.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import Optional, Any

logger = logging.getLogger(__name__)

GOOGLE_PACKAGE_NAME = os.getenv('GOOGLE_PACKAGE_NAME',
                                os.getenv('APPLE_BUNDLE_ID', 'com.audioura.audiotours'))
GOOGLE_PLAY_SA_JSON = os.getenv('GOOGLE_PLAY_SA_JSON', '')


def _find_purchase(cur, order_id, purchase_token):
    """Find the purchases ledger row a voided item refers to. Match on the Google
    orderId we stored as transaction_id first; fall back to the purchaseToken
    embedded in raw_status (google_verified:<orderId> stores the orderId, and the
    token was the client input — we also scan raw_status LIKE for the token to be
    robust). Returns (id, store, product, user_id, raw_status) or None."""
    if order_id:
        cur.execute(
            "SELECT id, store, product, user_id, raw_status "
            "FROM purchases WHERE transaction_id = %s", (order_id,))
        row = cur.fetchone()
        if row:
            return row
    if purchase_token:
        cur.execute(
            "SELECT id, store, product, user_id, raw_status "
            "FROM purchases WHERE raw_status LIKE %s LIMIT 1",
            (f'%{purchase_token}%',))
        row = cur.fetchone()
        if row:
            return row
    return None


def _is_tour_product(product):
    """A tour price-tier store product id (audioura.tour.*)."""
    return isinstance(product, str) and product.startswith('audioura.tour.')


def _is_pass_product(product):
    """A community pass store product id (audioura.pass.*)."""
    return isinstance(product, str) and product.startswith('audioura.pass.')


def _reverse_one(cur, purchase_row, order_id, now):
    """Reverse the grant a single voided purchase made. Returns a short string
    describing what was reversed ('tour_unlock' | 'membership' | 'level' |
    'already_voided' | 'nothing'). Idempotent."""
    pid, store, product, user_id, raw_status = purchase_row

    # Already reversed? (idempotent re-run of the poller).
    if isinstance(raw_status, str) and raw_status.startswith('voided:'):
        return 'already_voided'

    txid = order_id

    reversed_kind = 'nothing'
    if _is_tour_product(product):
        # Remove the tour unlock this purchase granted. Match the exact
        # transaction so we never revoke a DIFFERENT (still-valid) purchase of
        # the same tour by the same user.
        cur.execute(
            "DELETE FROM tour_unlocks WHERE user_id = %s AND transaction_id = %s",
            (user_id, txid))
        if cur.rowcount > 0:
            reversed_kind = 'tour_unlock'
    elif _is_pass_product(product):
        # End the community membership this pass granted: expire it NOW so new
        # content is blocked immediately (downloaded audio stays on the device —
        # D658). Only the membership whose transaction matches is touched.
        cur.execute(
            "UPDATE community_memberships SET expires_at = %s, updated_at = NOW() "
            "WHERE user_id = %s AND transaction_id = %s",
            (now, user_id, txid))
        if cur.rowcount > 0:
            reversed_kind = 'membership'
    else:
        # A LEVEL pack (l3_pack_10 / l4_round_25): drop the device back to L1 and
        # clear the pack/anniversary, mirroring entitlements_api.lapse. Only if
        # this purchase is the one that set the current level (we cannot know the
        # exact history, so we reset to L1 — the safe, non-granting direction).
        cur.execute(
            "UPDATE device_entitlement SET level = 'l1', pack_started_at = NULL, "
            "anniversary_at = NULL, fresh_used = 0, edits_used = 0, ops_used = 0, "
            "updated_at = NOW() WHERE user_id = %s", (user_id,))
        if cur.rowcount > 0:
            reversed_kind = 'level'

    # Mark the ledger row voided (audit; never DELETE the ledger row). Prefix the
    # existing raw_status so the original verify status is preserved.
    new_status = f'voided:{reversed_kind}:{raw_status or ""}'
    cur.execute("UPDATE purchases SET raw_status = %s WHERE id = %s",
                (new_status[:2000], pid))
    return reversed_kind


def reconcile_voided_purchases(cur, voided_items, now=None):
    """Reverse every grant named by `voided_items` (the Google voided-purchases
    feed). PURE: uses only the local DB, no network. Returns a summary dict:

        {'reversed': {'tour_unlock': n, 'membership': n, 'level': n},
         'already_voided': n, 'unmatched': n, 'processed': n}

    `voided_items` is a list of dicts; each may carry 'orderId' and
    'purchaseToken' (Google's VoidedPurchase shape). An item we cannot match to
    a ledger row is counted 'unmatched' (a void for a purchase this server never
    recorded — e.g. a different environment — is harmless to skip).

    Idempotent: an item whose purchase is already marked voided is counted
    'already_voided' and left alone. The caller owns the transaction (commit)."""
    now = now or datetime.utcnow()
    summary = {
        'reversed': {'tour_unlock': 0, 'membership': 0, 'level': 0},
        'already_voided': 0,
        'unmatched': 0,
        'processed': 0,
    }
    for item in voided_items or []:
        summary['processed'] += 1
        order_id = item.get('orderId') if isinstance(item, dict) else None
        token = item.get('purchaseToken') if isinstance(item, dict) else None
        row = _find_purchase(cur, order_id, token)
        if row is None:
            summary['unmatched'] += 1
            continue
        # The reversal targets the authoritative order id: the feed's orderId
        # when present, else the one recorded in the matched row's raw_status
        # (google_verified:<orderId>) — needed when the match was by token only.
        effective_order = order_id or _order_from_status(row[4])
        kind = _reverse_one(cur, row, effective_order, now)
        if kind == 'already_voided':
            summary['already_voided'] += 1
        elif kind in summary['reversed']:
            summary['reversed'][kind] += 1
    return summary


def _order_from_status(raw_status):
    """Extract the authoritative order id from a 'google_verified:<orderId>'
    raw_status so a void matched only by token can still target the right
    transaction_id in the grant tables. Returns None when absent."""
    if isinstance(raw_status, str) and raw_status.startswith('google_verified:'):
        return raw_status.split(':', 1)[1]
    return None


# ───────────────────────────────────────────────────────────────────────────
# Real poller — pages the Google feed and reconciles. Called by a timer/cron.
# ───────────────────────────────────────────────────────────────────────────
def _get_db():
    import psycopg2
    database_url = os.getenv(
        'DATABASE_URL', 'postgresql://admin:password123@localhost:5432/audiotours')
    return psycopg2.connect(database_url)


def fetch_voided_items(api_client, package_name=None, start_time_millis=None,
                       max_pages=20):
    """Page the whole voided-purchases feed via the injected api_client and
    return a flat list of voided items. NO DB. `max_pages` caps pagination."""
    pkg = package_name or GOOGLE_PACKAGE_NAME
    items = []
    token = None
    for _ in range(max_pages):
        page = api_client.list_voided_purchases(
            package_name=pkg, start_time_millis=start_time_millis, token=token)
        if not isinstance(page, dict):
            break
        items.extend(page.get('voidedPurchases') or [])
        token = (page.get('tokenPagination') or {}).get('nextPageToken')
        if not token:
            break
    return items


def run_poller(api_client: Optional[Any] = None, start_time_millis=None):
    """Fetch the voided-purchases feed and reverse each grant. Builds the real
    GooglePlayApiClient from GOOGLE_PLAY_SA_JSON when no client is injected; a
    missing SA is a clean no-op (logs and returns), never an error. Returns the
    reconcile summary dict."""
    if api_client is None:
        if not GOOGLE_PLAY_SA_JSON:
            logger.warning(
                "[LOCAL-696] voided poller: GOOGLE_PLAY_SA_JSON not set; skipping.")
            return {'skipped': 'google_verify_unconfigured'}
        from google_play_verifier import build_api_client
        api_client = build_api_client(GOOGLE_PLAY_SA_JSON,
                                      package_name=GOOGLE_PACKAGE_NAME)

    items = fetch_voided_items(api_client, start_time_millis=start_time_millis)
    conn = _get_db()
    try:
        cur = conn.cursor()
        summary = reconcile_voided_purchases(cur, items)
        conn.commit()
        cur.close()
        logger.info(f"[LOCAL-696] voided poller reconciled: {summary}")
        return summary
    finally:
        conn.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print(run_poller())
