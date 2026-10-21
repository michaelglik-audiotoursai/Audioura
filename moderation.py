#!/usr/bin/env python3
"""moderation.py — LOCAL-728 / D691: the administrator's moderation CLI.

D691: members and organisers REPORT abuse to Audioura (the app's "Report to
Audioura" form and the tour "Report" both land in a reviewable queue). Only the
ADMINISTRATOR acts on those reports, and they do it HERE — a CLI next to
review_queue.py, run by the admin operator (Michael, through LEAD), never by an
app user. Every action writes one row to the admin_actions ledger.

    python3 moderation.py reports                 # open reports (community + tour)
    python3 moderation.py reports --status all     # every report
    python3 moderation.py bar   <community_id> <user_id> ["reason"] [--report N]
    python3 moderation.py unbar <community_id> <user_id> ["reason"]
    python3 moderation.py ban   <user_id> ["reason"] [--report N]
    python3 moderation.py unban <user_id> ["reason"]
    python3 moderation.py disable <community_id> ["reason"] [--report N]
    python3 moderation.py enable  <community_id> ["reason"]
    python3 moderation.py log [--limit 50]         # the admin_actions ledger

Reimbursement — ADMINISTRATOR ONLY (LOCAL-729 / D691 / D690 / D692). Only
Audioura reimburses a tour buyer, a community member or a plan purchaser; never
an app user. Every command writes EXACTLY ONE admin_actions ledger row. A
<device> may be given as the raw device id OR the public Support ID (AU-XXXX).

    python3 moderation.py grant-tour <device|support-id> <tour_id> <language> ["reason"]
    python3 moderation.py extend-pass <community_id> <device|support-id> <days> ["reason"]
    python3 moderation.py grant-pass  <device|support-id> <community_id> <length> ["reason"]
    python3 moderation.py add-plan-units <device|support-id> <n> ["reason"]
    python3 moderation.py extend-plan   <device|support-id> <days> ["reason"]
    python3 moderation.py refund-google <order_id> [--partial USD] ["reason"]
    python3 moderation.py apple-refund-message <device|support-id|order_id> ["reason"]
    python3 moderation.py support-id <device>       # show/allocate a device's Support ID
    python3 moderation.py ledger [--device D] [--limit 50]  # history (optionally one device)

Reimbursement rules (design §2, ClickUp wdvrdaz3tb):
  grant-tour  — one UNCONSUMED tour_unlocks row, store='admin_grant', the
                download gate honours it once and consumes it on download (as the
                recovery-code restore already does). No money.
  extend-pass — push an existing membership's expires_at out by N days.
  grant-pass  — create/extend a membership by the length's duration_days.
  add-plan-units — grant N more generations this pack (lower fresh_used, floor 0).
  extend-plan — push the plan's anniversary_at out by N days.
  refund-google — Android Publisher Orders refund (revoke), then local revoke via
                the existing void path; --partial USD refunds money WITHOUT
                revoking. The purchase receipt row is KEPT (D690). Needs the Play
                service account (GOOGLE_PLAY_SA_JSON); without it, a clear refusal.
  apple-refund-message — print the ready-to-send customer text
                (reportaproblem.apple.com) and mark the purchase refund_supported
                so the consumption answer (wdvrdaz2zf) can say we support it.

What each action does (the rules live here and in communities_api.py, which
shares the same tables):

  bar    — end the member's membership BY EXPIRY (never DELETE — D690: the row
           is the purchase record) and record an admin_bar so they cannot
           rejoin by code. Downloaded audio stays on the device (D658).
  ban    — ban the user from the SERVICE: no purchases, generation, joins or
           creation. Downloaded audio stays (D658: a ban blocks NEW access).
  disable/enable — the per-community off switch (communities.disabled).
  unbar/unban/enable — lift the matching action. A lifted ban keeps its row as
           history; an unbar deletes the bar row (community_blocks holds only
           bar rows). Every lift is itself a ledger row.

DB only — no model, no paid calls, no network. Nothing is ever DELETEd except a
community_blocks bar row (an unbar); memberships, purchases and tours are never
touched. `--actor` labels who ran the action in the ledger (default
'moderation.py').
"""
import argparse
import os
import sys

import psycopg2

# The reimbursement helpers live in user-tracking/ (support_id.py,
# google_play_refund.py) so the service can import them too; add that dir to the
# path so this repo-root CLI can import them as well (LOCAL-729).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'user-tracking'))

# The admin bar reuses community_blocks with this kind (migration 046). Kept in
# sync with communities_api.BLOCK_ADMIN_BAR.
ADMIN_BAR = 'admin_bar'

# Community pass lengths → duration_days (migration 029). Used by grant-pass.
PASS_DURATION_DAYS = {'day': 1, 'week': 7, 'month': 30, 'year': 365}


def _conn():
    return psycopg2.connect(os.getenv(
        'DATABASE_URL', 'postgresql://admin:password123@localhost:5433/audiotours'))


def _log(cur, action, actor, target_user_id=None, target_community_id=None,
         reason=None, report_id=None, amount_usd=None, transaction_id=None,
         store=None, target_tour_id=None):
    """Append EXACTLY ONE row to the admin_actions ledger (D691). The
    reimbursement columns (amount_usd, transaction_id, store, target_tour_id —
    migration 047) are NULL for a moderation action and set for a reimbursement.
    Written with a column-name INSERT so an un-migrated DB fails loudly rather
    than silently dropping the money fields."""
    cur.execute(
        """INSERT INTO admin_actions
               (action, actor, target_user_id, target_community_id, reason,
                report_id, amount_usd, transaction_id, store, target_tour_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (action, actor, target_user_id, target_community_id, reason, report_id,
         amount_usd, transaction_id, store, target_tour_id),
    )
    return cur.fetchone()[0]


def cmd_reports(cur, status):
    want_all = status == 'all'
    print(f'── Community reports ({status}) ──')
    if want_all:
        cur.execute(
            "SELECT id, community_id, reporter_user_id, reason, detail, status, "
            "created_at FROM community_reports ORDER BY created_at DESC")
    else:
        cur.execute(
            "SELECT id, community_id, reporter_user_id, reason, detail, status, "
            "created_at FROM community_reports WHERE status = %s "
            "ORDER BY created_at DESC", (status,))
    rows = cur.fetchall()
    if not rows:
        print('  (none)')
    for r in rows:
        print(f'  #{r[0]} community={r[1]} by={r[2] or "?"} '
              f'reason={r[3] or "-"} detail={r[4] or "-"} status={r[5]} '
              f'at={r[6]}')
    print(f'\n── Tour reports ({status}) ──')
    try:
        if want_all:
            cur.execute(
                "SELECT id, tour_id, tour_name, reason, reporter_user_id, "
                "status, created_at FROM tour_reports ORDER BY created_at DESC")
        else:
            cur.execute(
                "SELECT id, tour_id, tour_name, reason, reporter_user_id, "
                "status, created_at FROM tour_reports WHERE status = %s "
                "ORDER BY created_at DESC", (status,))
        trows = cur.fetchall()
    except Exception:  # noqa: BLE001 — tour_reports may be absent on an old DB
        cur.connection.rollback()
        trows = []
    if not trows:
        print('  (none)')
    for r in trows:
        print(f'  #{r[0]} tour={r[1]} "{r[2] or "?"}" reason={r[3] or "-"} '
              f'by={r[4] or "?"} status={r[5]} at={r[6]}')
    return 0


def cmd_bar(cur, conn, community_id, user_id, reason, actor, report_id):
    cur.execute("SELECT id FROM communities WHERE id = %s", (community_id,))
    if not cur.fetchone():
        print(f'No community with id {community_id}.')
        return 1
    # End the membership by expiry — NEVER delete it (D690).
    cur.execute(
        "UPDATE community_memberships SET expires_at = NOW(), updated_at = NOW() "
        "WHERE community_id = %s AND user_id = %s "
        "AND (expires_at IS NULL OR expires_at > NOW())",
        (community_id, user_id))
    ended = cur.rowcount
    cur.execute(
        """INSERT INTO community_blocks
               (community_id, blocker_user_id, blocked_user_id, kind, reason)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (community_id, blocker_user_id, blocked_user_id, kind)
           DO NOTHING""",
        (community_id, actor, user_id, ADMIN_BAR, reason))
    _log(cur, 'bar', actor, target_user_id=user_id,
         target_community_id=community_id, reason=reason, report_id=report_id)
    conn.commit()
    print(f'Barred {user_id} from community {community_id} '
          f'(membership ended: {ended}). Ledger written.')
    return 0


def cmd_unbar(cur, conn, community_id, user_id, reason, actor):
    cur.execute(
        "DELETE FROM community_blocks WHERE community_id = %s "
        "AND blocked_user_id = %s AND kind = %s",
        (community_id, user_id, ADMIN_BAR))
    removed = cur.rowcount
    _log(cur, 'unbar', actor, target_user_id=user_id,
         target_community_id=community_id, reason=reason)
    conn.commit()
    print(f'Unbarred {user_id} from community {community_id} '
          f'(removed {removed}). Ledger written.')
    return 0


def cmd_ban(cur, conn, user_id, reason, actor, report_id):
    cur.execute(
        """INSERT INTO service_bans (user_id, reason, report_id, banned_by)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (user_id) WHERE lifted_at IS NULL DO NOTHING""",
        (user_id, reason, report_id, actor))
    _log(cur, 'ban', actor, target_user_id=user_id, reason=reason,
         report_id=report_id)
    conn.commit()
    print(f'Banned {user_id} from the service. Downloaded audio stays (D658). '
          f'Ledger written.')
    return 0


def cmd_unban(cur, conn, user_id, reason, actor):
    cur.execute(
        "UPDATE service_bans SET lifted_at = NOW(), lifted_by = %s "
        "WHERE user_id = %s AND lifted_at IS NULL",
        (actor, user_id))
    lifted = cur.rowcount
    _log(cur, 'unban', actor, target_user_id=user_id, reason=reason)
    conn.commit()
    print(f'Unbanned {user_id} (lifted {lifted}). Ledger written.')
    return 0


def cmd_disable(cur, conn, community_id, reason, actor, report_id, enable):
    cur.execute("SELECT id FROM communities WHERE id = %s", (community_id,))
    if not cur.fetchone():
        print(f'No community with id {community_id}.')
        return 1
    cur.execute(
        "UPDATE communities SET disabled = %s, updated_at = NOW() WHERE id = %s",
        (not enable, community_id))
    _log(cur, 'enable_community' if enable else 'disable_community', actor,
         target_community_id=community_id, reason=reason, report_id=report_id)
    conn.commit()
    verb = 'Enabled' if enable else 'Disabled'
    print(f'{verb} community {community_id}. Ledger written.')
    return 0


def cmd_log(cur, limit):
    cur.execute(
        "SELECT id, action, actor, target_user_id, target_community_id, reason, "
        "report_id, created_at FROM admin_actions "
        "ORDER BY created_at DESC, id DESC LIMIT %s", (limit,))
    rows = cur.fetchall()
    if not rows:
        print('Ledger is empty.')
        return 0
    for r in rows:
        print(f'  #{r[0]} {r[1]} actor={r[2] or "?"} user={r[3] or "-"} '
              f'community={r[4] or "-"} reason={r[5] or "-"} '
              f'report={r[6] or "-"} at={r[7]}')
    return 0


# ─── Reimbursement (LOCAL-729 / D691 / D690 / D692) ──────────────────────────
# Each command writes EXACTLY ONE admin_actions row. A <device> argument may be
# the raw device id or a public Support ID (AU-XXXX), resolved by support_id.py.

def _resolve_device(cur, token):
    """Resolve a <device|support-id> argument to the device user_id, or None if
    an AU-... Support ID is unknown."""
    import support_id as _sid
    return _sid.resolve_to_user_id(cur, token)


def cmd_grant_tour(cur, conn, device, tour_id, language, reason, actor):
    """Re-grant a tour download: one UNCONSUMED tour_unlocks row with
    store='admin_grant'. The download gate honours an unconsumed row and
    consumes it on the next successful download (D660), exactly as a
    recovery-code restore does. No money changes hands."""
    user_id = _resolve_device(cur, device)
    if not user_id:
        print(f'Unknown Support ID / device: {device}')
        return 1
    # Resolve a translation id to its ORIGINAL (tour_unlocks.tour_id is an
    # original audio_tours.id); a grant for a language row still unlocks the
    # original, which is how a normal purchase records it.
    cur.execute(
        "SELECT COALESCE(original_tour_id, id) FROM audio_tours WHERE id = %s",
        (tour_id,))
    row = cur.fetchone()
    if not row:
        print(f'No tour with id {tour_id}.')
        return 1
    original_id = row[0]
    # Does the buyer already hold an ACTIVE (unconsumed) unlock? The partial
    # unique index would reject a duplicate; make that an explicit, friendly
    # no-op so a double-grant does not crash — but still write the ledger row so
    # the admin's action is recorded.
    cur.execute(
        "SELECT 1 FROM tour_unlocks WHERE user_id = %s AND tour_id = %s "
        "AND consumed_at IS NULL", (user_id, original_id))
    already = cur.fetchone() is not None
    if not already:
        cur.execute(
            """INSERT INTO tour_unlocks
                   (user_id, tour_id, transaction_id, store, price_usd)
               VALUES (%s, %s, NULL, 'admin_grant', 0)""",
            (user_id, original_id))
    _log(cur, 'grant_tour', actor, target_user_id=user_id,
         reason=reason, store='admin_grant', target_tour_id=original_id)
    conn.commit()
    note = 'already had an active unlock; ' if already else ''
    print(f'Granted tour {original_id} ({language}) to {user_id} '
          f'({note}store=admin_grant). Ledger written.')
    return 0


def cmd_extend_pass(cur, conn, community_id, device, days, reason, actor):
    """Extend an existing community membership by N days (expires_at only). A
    free (NULL-expiry) membership is pushed from NOW; a lapsed one from NOW too,
    so the member gets the full N days."""
    user_id = _resolve_device(cur, device)
    if not user_id:
        print(f'Unknown Support ID / device: {device}')
        return 1
    cur.execute(
        "SELECT expires_at FROM community_memberships "
        "WHERE community_id = %s AND user_id = %s", (community_id, user_id))
    row = cur.fetchone()
    if not row:
        print(f'{user_id} has no membership in community {community_id}. '
              f'Use grant-pass to create one.')
        return 1
    # Extend from the later of NOW and the current expiry so an active pass gains
    # the full N days on top, and a lapsed/free one restarts from now.
    cur.execute(
        "UPDATE community_memberships "
        "SET expires_at = GREATEST(COALESCE(expires_at, NOW()), NOW()) "
        "    + make_interval(days => %s), updated_at = NOW() "
        "WHERE community_id = %s AND user_id = %s",
        (days, community_id, user_id))
    _log(cur, 'extend_pass', actor, target_user_id=user_id,
         target_community_id=community_id, reason=reason)
    conn.commit()
    print(f'Extended {user_id}\'s pass in community {community_id} by {days} '
          f'day(s). Ledger written.')
    return 0


def cmd_grant_pass(cur, conn, device, community_id, length, reason, actor):
    """Grant (or extend) a community membership by the length's duration_days.
    One membership row per (user, community) — buying/granting again extends the
    expiry, it does not stack rows (uq_community_memberships)."""
    user_id = _resolve_device(cur, device)
    if not user_id:
        print(f'Unknown Support ID / device: {device}')
        return 1
    days = PASS_DURATION_DAYS.get(length)
    if days is None:
        print(f'Unknown length {length!r}; use day|week|month|year.')
        return 1
    cur.execute("SELECT id FROM communities WHERE id = %s", (community_id,))
    if not cur.fetchone():
        print(f'No community with id {community_id}.')
        return 1
    # Upsert: create from NOW + duration, or extend an existing membership from
    # the later of its expiry and NOW. store='admin_grant' marks a make-good.
    cur.execute(
        """INSERT INTO community_memberships
               (user_id, community_id, expires_at, store, created_at, updated_at)
           VALUES (%s, %s, NOW() + make_interval(days => %s), 'admin_grant',
                   NOW(), NOW())
           ON CONFLICT (user_id, community_id) DO UPDATE SET
               expires_at = GREATEST(
                   COALESCE(community_memberships.expires_at, NOW()), NOW())
                   + make_interval(days => %s),
               updated_at = NOW()""",
        (user_id, community_id, days, days))
    _log(cur, 'grant_pass', actor, target_user_id=user_id,
         target_community_id=community_id, reason=reason, store='admin_grant')
    conn.commit()
    print(f'Granted {user_id} a {length} pass ({days} day(s)) in community '
          f'{community_id}. Ledger written.')
    return 0


def cmd_add_plan_units(cur, conn, device, n, reason, actor):
    """Add N plan generation units this pack: lower fresh_used by N (floored at
    0), so the device may generate N more fresh tours in the current window
    (D613 allowance). Does not change the level or the anniversary."""
    user_id = _resolve_device(cur, device)
    if not user_id:
        print(f'Unknown Support ID / device: {device}')
        return 1
    cur.execute("SELECT fresh_used FROM device_entitlement WHERE user_id = %s",
                (user_id,))
    row = cur.fetchone()
    if not row:
        print(f'{user_id} has no device_entitlement row (no plan state).')
        return 1
    cur.execute(
        "UPDATE device_entitlement "
        "SET fresh_used = GREATEST(fresh_used - %s, 0), updated_at = NOW() "
        "WHERE user_id = %s", (n, user_id))
    _log(cur, 'add_plan_units', actor, target_user_id=user_id, reason=reason,
         amount_usd=None)
    conn.commit()
    print(f'Added {n} plan unit(s) to {user_id} (fresh_used lowered, floor 0). '
          f'Ledger written.')
    return 0


def cmd_extend_plan(cur, conn, device, days, reason, actor):
    """Extend the plan's current pack/anniversary by N days (anniversary_at
    only), so the device's monthly allowance window lasts longer (D613)."""
    user_id = _resolve_device(cur, device)
    if not user_id:
        print(f'Unknown Support ID / device: {device}')
        return 1
    cur.execute("SELECT anniversary_at FROM device_entitlement WHERE user_id = %s",
                (user_id,))
    row = cur.fetchone()
    if not row:
        print(f'{user_id} has no device_entitlement row (no plan state).')
        return 1
    cur.execute(
        "UPDATE device_entitlement "
        "SET anniversary_at = COALESCE(anniversary_at, NOW()) "
        "    + make_interval(days => %s), updated_at = NOW() "
        "WHERE user_id = %s", (days, user_id))
    _log(cur, 'extend_plan', actor, target_user_id=user_id, reason=reason)
    conn.commit()
    print(f'Extended {user_id}\'s plan window by {days} day(s). Ledger written.')
    return 0


def cmd_refund_google(cur, conn, order_id, partial_usd, reason, actor):
    """Refund a Google order (Android Publisher Orders refund, with revoke on a
    full refund), then reverse the local grant via the existing void path. The
    purchase receipt row is KEPT, marked voided (D690). Needs the Play service
    account; without it, a clear refusal and NO ledger row."""
    import google_play_refund as _gpr
    # Record the money amount against the purchase row if we have it (the
    # transaction_id == Google orderId) so the ledger amount reflects a full
    # refund too.
    cur.execute("SELECT amount, store FROM purchases WHERE transaction_id = %s",
                (order_id,))
    prow = cur.fetchone()
    purchase_amount = float(prow[0]) if prow and prow[0] is not None else None
    store = prow[1] if prow else 'google'
    try:
        summary = _gpr.refund_order(cur, order_id, api_client=None,
                                    partial_usd=partial_usd)
    except _gpr.RefundNotConfigured as e:
        # No service account → refuse clearly, grant/refund nothing, NO ledger.
        print(f'Refund NOT issued: {e}')
        return 2
    except _gpr.RefundApiError as e:
        print(f'Refund NOT issued: {e}')
        return 3
    amount = partial_usd if partial_usd is not None else purchase_amount
    _log(cur, 'refund_google', actor, reason=reason,
         amount_usd=amount, transaction_id=order_id, store=store)
    conn.commit()
    kind = f'partial ${partial_usd:.2f}' if partial_usd is not None else 'full'
    rev = summary.get('local_reversal')
    print(f'Refunded Google order {order_id} ({kind}; '
          f'revoked={summary["revoked"]}). Local reversal: {rev}. '
          f'Purchase row kept (D690). Ledger written.')
    return 0


APPLE_REFUND_TEXT = (
    "Hi — thanks for reaching out. Apple handles refunds for in-app purchases, "
    "so please request one at https://reportaproblem.apple.com using the Apple "
    "ID that made the purchase. We've recorded that Audioura supports this "
    "refund, so if Apple asks us we'll confirm it. Sorry for the trouble!")


def cmd_apple_refund_message(cur, conn, token, reason, actor):
    """Print the ready-to-send customer text (reportaproblem.apple.com) and mark
    the buyer's Apple purchase(s) refund_supported, so the consumption answer
    (App Store Server Notifications, wdvrdaz2zf) can tell Apple we support it.
    `token` may be an order/transaction id, a Support ID, or a device id."""
    import support_id as _sid
    marked = 0
    target_user = None
    txid = None
    if _sid.is_support_id(token) or token.startswith('USER-'):
        # A device: mark all of that device's Apple purchases.
        target_user = _sid.resolve_to_user_id(cur, token)
        if not target_user:
            print(f'Unknown Support ID / device: {token}')
            return 1
        cur.execute(
            "UPDATE purchases SET refund_supported = TRUE "
            "WHERE user_id = %s AND store = 'apple'", (target_user,))
        marked = cur.rowcount
    else:
        # An order/transaction id: mark that one purchase.
        txid = token
        cur.execute(
            "UPDATE purchases SET refund_supported = TRUE "
            "WHERE transaction_id = %s", (token,))
        marked = cur.rowcount
        cur.execute("SELECT user_id FROM purchases WHERE transaction_id = %s",
                    (token,))
        r = cur.fetchone()
        target_user = r[0] if r else None
    _log(cur, 'apple_refund_support', actor, target_user_id=target_user,
         reason=reason, transaction_id=txid, store='apple')
    conn.commit()
    print('── Send this to the customer ──')
    print(APPLE_REFUND_TEXT)
    print(f'── (marked {marked} Apple purchase(s) refund_supported). '
          f'Ledger written. ──')
    return 0


def cmd_support_id(cur, conn, device):
    """Show (allocating if needed) a device's public Support ID."""
    import support_id as _sid
    sid = _sid.ensure_support_id(cur, device)
    conn.commit()
    print(f'{device} → Support ID {sid}')
    return 0


def cmd_ledger(cur, device, limit):
    """The admin_actions ledger, newest first, optionally for ONE device
    (accepts a Support ID or a device id). Reimbursement rows show the money and
    purchase columns."""
    user_id = None
    if device:
        import support_id as _sid
        user_id = _sid.resolve_to_user_id(cur, device)
        if not user_id:
            print(f'Unknown Support ID / device: {device}')
            return 1
    if user_id:
        cur.execute(
            "SELECT id, action, actor, target_user_id, target_community_id, "
            "reason, report_id, amount_usd, transaction_id, store, "
            "target_tour_id, created_at FROM admin_actions "
            "WHERE target_user_id = %s ORDER BY created_at DESC, id DESC "
            "LIMIT %s", (user_id, limit))
    else:
        cur.execute(
            "SELECT id, action, actor, target_user_id, target_community_id, "
            "reason, report_id, amount_usd, transaction_id, store, "
            "target_tour_id, created_at FROM admin_actions "
            "ORDER BY created_at DESC, id DESC LIMIT %s", (limit,))
    rows = cur.fetchall()
    if not rows:
        print('Ledger is empty.')
        return 0
    for r in rows:
        money = f' ${r[7]}' if r[7] is not None else ''
        txn = f' txn={r[8]}' if r[8] else ''
        store = f' store={r[9]}' if r[9] else ''
        tour = f' tour={r[10]}' if r[10] else ''
        print(f'  #{r[0]} {r[1]} actor={r[2] or "?"} user={r[3] or "-"} '
              f'community={r[4] or "-"} reason={r[5] or "-"} '
              f'report={r[6] or "-"}{money}{txn}{store}{tour} at={r[11]}')
    return 0


def main():
    ap = argparse.ArgumentParser(
        description='Admin-only moderation CLI (LOCAL-728 / D691).')
    ap.add_argument('--actor', default='moderation.py',
                    help='who is running the action (recorded in the ledger)')
    sub = ap.add_subparsers(dest='command', required=True)

    p_r = sub.add_parser('reports', help='list reports (community + tour)')
    p_r.add_argument('--status', default='open',
                     choices=['open', 'reviewed', 'dismissed', 'all'])

    p_bar = sub.add_parser('bar', help='bar a user from one community')
    p_bar.add_argument('community_id', type=int)
    p_bar.add_argument('user_id')
    p_bar.add_argument('reason', nargs='?', default='')
    p_bar.add_argument('--report', type=int, default=None)

    p_unbar = sub.add_parser('unbar', help='lift a community bar')
    p_unbar.add_argument('community_id', type=int)
    p_unbar.add_argument('user_id')
    p_unbar.add_argument('reason', nargs='?', default='')

    p_ban = sub.add_parser('ban', help='ban a user from the service')
    p_ban.add_argument('user_id')
    p_ban.add_argument('reason', nargs='?', default='')
    p_ban.add_argument('--report', type=int, default=None)

    p_unban = sub.add_parser('unban', help='lift a service ban')
    p_unban.add_argument('user_id')
    p_unban.add_argument('reason', nargs='?', default='')

    p_dis = sub.add_parser('disable', help='disable a community (off switch)')
    p_dis.add_argument('community_id', type=int)
    p_dis.add_argument('reason', nargs='?', default='')
    p_dis.add_argument('--report', type=int, default=None)

    p_en = sub.add_parser('enable', help='re-enable a community')
    p_en.add_argument('community_id', type=int)
    p_en.add_argument('reason', nargs='?', default='')

    p_log = sub.add_parser('log', help='show the admin_actions ledger')
    p_log.add_argument('--limit', type=int, default=50)

    # ── Reimbursement subcommands (LOCAL-729) ────────────────────────────────
    p_gt = sub.add_parser('grant-tour',
                          help='re-grant a tour download (free unlock)')
    p_gt.add_argument('device', help='device id or Support ID (AU-XXXX)')
    p_gt.add_argument('tour_id', type=int)
    p_gt.add_argument('language')
    p_gt.add_argument('reason', nargs='?', default='')

    p_ep = sub.add_parser('extend-pass',
                          help='extend a membership by N days (expires_at only)')
    p_ep.add_argument('community_id', type=int)
    p_ep.add_argument('device', help='device id or Support ID (AU-XXXX)')
    p_ep.add_argument('days', type=int)
    p_ep.add_argument('reason', nargs='?', default='')

    p_gp = sub.add_parser('grant-pass',
                          help='grant/extend a community pass by its length')
    p_gp.add_argument('device', help='device id or Support ID (AU-XXXX)')
    p_gp.add_argument('community_id', type=int)
    p_gp.add_argument('length', choices=['day', 'week', 'month', 'year'])
    p_gp.add_argument('reason', nargs='?', default='')

    p_apu = sub.add_parser('add-plan-units',
                           help='grant N more generations this pack (D613)')
    p_apu.add_argument('device', help='device id or Support ID (AU-XXXX)')
    p_apu.add_argument('n', type=int)
    p_apu.add_argument('reason', nargs='?', default='')

    p_xpl = sub.add_parser('extend-plan',
                           help="extend the plan's window by N days (D613)")
    p_xpl.add_argument('device', help='device id or Support ID (AU-XXXX)')
    p_xpl.add_argument('days', type=int)
    p_xpl.add_argument('reason', nargs='?', default='')

    p_rg = sub.add_parser('refund-google',
                          help='refund a Google order (Orders refund + revoke)')
    p_rg.add_argument('order_id')
    p_rg.add_argument('--partial', type=float, default=None,
                      metavar='USD', help='partial money refund, keeps access')
    p_rg.add_argument('reason', nargs='?', default='')

    p_arm = sub.add_parser('apple-refund-message',
                           help='print the Apple refund text + mark supported')
    p_arm.add_argument('target',
                       help='order/transaction id, Support ID, or device id')
    p_arm.add_argument('reason', nargs='?', default='')

    p_sid = sub.add_parser('support-id',
                           help="show/allocate a device's public Support ID")
    p_sid.add_argument('device')

    p_led = sub.add_parser('ledger',
                           help='reimbursement/moderation history')
    p_led.add_argument('--device', default=None,
                       help='one device id or Support ID (AU-XXXX)')
    p_led.add_argument('--limit', type=int, default=50)

    a = ap.parse_args()
    actor = a.actor

    conn = _conn()
    cur = conn.cursor()
    try:
        if a.command == 'reports':
            return cmd_reports(cur, a.status)
        if a.command == 'bar':
            return cmd_bar(cur, conn, a.community_id, a.user_id,
                           a.reason or None, actor, a.report)
        if a.command == 'unbar':
            return cmd_unbar(cur, conn, a.community_id, a.user_id,
                             a.reason or None, actor)
        if a.command == 'ban':
            return cmd_ban(cur, conn, a.user_id, a.reason or None, actor,
                           a.report)
        if a.command == 'unban':
            return cmd_unban(cur, conn, a.user_id, a.reason or None, actor)
        if a.command == 'disable':
            return cmd_disable(cur, conn, a.community_id, a.reason or None,
                               actor, a.report, enable=False)
        if a.command == 'enable':
            return cmd_disable(cur, conn, a.community_id, a.reason or None,
                               actor, None, enable=True)
        if a.command == 'log':
            return cmd_log(cur, a.limit)
        # ── Reimbursement dispatch (LOCAL-729) ───────────────────────────────
        if a.command == 'grant-tour':
            return cmd_grant_tour(cur, conn, a.device, a.tour_id, a.language,
                                  a.reason or None, actor)
        if a.command == 'extend-pass':
            return cmd_extend_pass(cur, conn, a.community_id, a.device, a.days,
                                   a.reason or None, actor)
        if a.command == 'grant-pass':
            return cmd_grant_pass(cur, conn, a.device, a.community_id, a.length,
                                  a.reason or None, actor)
        if a.command == 'add-plan-units':
            return cmd_add_plan_units(cur, conn, a.device, a.n,
                                      a.reason or None, actor)
        if a.command == 'extend-plan':
            return cmd_extend_plan(cur, conn, a.device, a.days,
                                   a.reason or None, actor)
        if a.command == 'refund-google':
            return cmd_refund_google(cur, conn, a.order_id, a.partial,
                                     a.reason or None, actor)
        if a.command == 'apple-refund-message':
            return cmd_apple_refund_message(cur, conn, a.target,
                                            a.reason or None, actor)
        if a.command == 'support-id':
            return cmd_support_id(cur, conn, a.device)
        if a.command == 'ledger':
            return cmd_ledger(cur, a.device, a.limit)
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
