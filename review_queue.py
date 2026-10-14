#!/usr/bin/env python3
"""review_queue.py — LOCAL-687 / D656: the human review gate before public listing.

tour_content_rating.py marks every tour that is NOT clearly general as
review_status 'pending' (mature or not_allowed). Those tours are hidden from
every listing until a human — LEAD or Michael — looks at them here and either
approves (it lists per its rating: a mature tour then shows to confirmed-18+
listeners) or rejects (it stays hidden).

    python3 review_queue.py list                 # every pending tour
    python3 review_queue.py approve 557           # review_status -> approved
    python3 review_queue.py reject 557 "explicit" # review_status -> rejected, reason stored

`list` prints, for each pending tour: id, name, rating, the model's reason, and
the first 600 characters of the tour text so the reviewer can judge without
opening anything else.

DB only (no model, no paid calls). Approve/reject are the only writes; nothing
is ever DELETEd.
"""
import argparse
import os
import sys
from datetime import datetime, timezone

import psycopg2

PREVIEW_CHARS = 600


def _conn():
    return psycopg2.connect(os.getenv(
        'DATABASE_URL', 'postgresql://admin:password123@localhost:5433/audiotours'))


def cmd_list(cur):
    cur.execute("""
        SELECT id, tour_name, content_rating, content_rating_reason, tour_content
        FROM audio_tours
        WHERE review_status = 'pending'
        ORDER BY content_rated_at NULLS LAST, id
    """)
    rows = cur.fetchall()
    if not rows:
        print('Review queue is empty — nothing pending.')
        return 0
    print(f'{len(rows)} tour(s) pending review:\n')
    for tid, name, rating, reason, content in rows:
        preview = (content or '').strip().replace('\n', ' ')
        if len(preview) > PREVIEW_CHARS:
            preview = preview[:PREVIEW_CHARS] + '…'
        print('=' * 72)
        print(f'  id      : {tid}')
        print(f'  name    : {name}')
        print(f'  rating  : {rating}')
        print(f'  reason  : {reason or "(none)"}')
        print(f'  preview : {preview or "(no text)"}')
    print('=' * 72)
    print('\napprove with:  python3 review_queue.py approve <id>')
    print('reject  with:  python3 review_queue.py reject <id> "reason"')
    return 0


def _set_status(cur, conn, tid, status, reason=None):
    cur.execute("SELECT id, tour_name, content_rating, review_status FROM audio_tours WHERE id = %s", (tid,))
    row = cur.fetchone()
    if not row:
        print(f'No tour with id {tid}.')
        return 1
    _, name, rating, current = row
    if status == 'rejected' and reason:
        cur.execute("""UPDATE audio_tours SET review_status = %s, content_rating_reason = %s,
                       content_rated_at = %s WHERE id = %s""",
                    (status, reason, datetime.now(timezone.utc), tid))
    else:
        cur.execute("""UPDATE audio_tours SET review_status = %s, content_rated_at = %s
                       WHERE id = %s""",
                    (status, datetime.now(timezone.utc), tid))
    conn.commit()
    note = ''
    if status == 'approved' and rating == 'mature':
        note = ' (lists to confirmed-18+ listeners)'
    elif status == 'approved':
        note = ' (lists for everyone)'
    elif status == 'rejected':
        note = ' (stays hidden)'
    print(f'Tour {tid} "{name}" [{rating}]: {current or "pending"} -> {status}{note}')
    return 0


def main():
    ap = argparse.ArgumentParser(description='Content-rating review queue (LOCAL-687).')
    sub = ap.add_subparsers(dest='command', required=True)
    sub.add_parser('list', help='show every tour pending review')
    p_app = sub.add_parser('approve', help='approve a tour (lists per its rating)')
    p_app.add_argument('id', type=int)
    p_rej = sub.add_parser('reject', help='reject a tour (stays hidden)')
    p_rej.add_argument('id', type=int)
    p_rej.add_argument('reason', nargs='?', default='', help='why it was rejected')
    a = ap.parse_args()

    conn = _conn()
    cur = conn.cursor()
    try:
        if a.command == 'list':
            return cmd_list(cur)
        if a.command == 'approve':
            return _set_status(cur, conn, a.id, 'approved')
        if a.command == 'reject':
            return _set_status(cur, conn, a.id, 'rejected', reason=a.reason or None)
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
