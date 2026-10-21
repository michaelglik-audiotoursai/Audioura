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

# The admin bar reuses community_blocks with this kind (migration 046). Kept in
# sync with communities_api.BLOCK_ADMIN_BAR.
ADMIN_BAR = 'admin_bar'


def _conn():
    return psycopg2.connect(os.getenv(
        'DATABASE_URL', 'postgresql://admin:password123@localhost:5433/audiotours'))


def _log(cur, action, actor, target_user_id=None, target_community_id=None,
         reason=None, report_id=None):
    """Append one row to the admin_actions ledger (D691)."""
    cur.execute(
        """INSERT INTO admin_actions
               (action, actor, target_user_id, target_community_id, reason,
                report_id)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (action, actor, target_user_id, target_community_id, reason, report_id),
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
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
