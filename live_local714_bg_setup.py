#!/usr/bin/env python3
"""live_local714_bg_setup.py — LOCAL-714 Android live-test DB setup/teardown.

Own harness, is_test rows ONLY, cleanup by captured id guarded by is_test.
NEVER touches a non-is_test row; never renames/stops any container.

setup:
  * captures BEFORE counts (audio_tours, community_memberships, is_test tours);
  * creates ONE is_test ORIGINAL community tour tagged to community 2, copying
    the audio_tour BYTEA + request_string from an existing downloadable is_test
    tour (704) so map-delivery /download-tour/<new id> serves REAL bytes;
  * grants the test DEVICE an ACTIVE community_memberships row for community 2;
  * prints the new tour id + AFTER counts.

teardown:
  * deletes exactly the created tour id (guarded is_test=TRUE) and the test
    membership (guarded by user_id + is_test tour linkage), prints FINAL counts.

Usage:
  python3 live_local714_bg_setup.py setup   USER-281301397
  python3 live_local714_bg_setup.py teardown USER-281301397 <tour_id>
"""
import os
import sys

import psycopg2

DB_URL = os.getenv("LIVE_DB_URL",
                   "postgresql://admin:password123@localhost:5433/audiotours")
COMMUNITY_ID = 2
SOURCE_TOUR_ID = 704  # an existing is_test, non-draft, downloadable tour


def counts(cur):
    cur.execute("SELECT count(*) FROM audio_tours")
    at = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM community_memberships")
    cm = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM audio_tours WHERE is_test = TRUE")
    att = cur.fetchone()[0]
    return at, cm, att


def setup(device):
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()
    before = counts(cur)
    print("BEFORE: audio_tours=%d community_memberships=%d is_test=%d" % before)

    # Create one is_test ORIGINAL community tour with REAL downloadable bytes
    # copied from the source is_test tour.
    cur.execute(
        """INSERT INTO audio_tours
               (tour_name, request_string, language, stops_count, short_title,
                community_id, community_visibility, audio_tour, is_test, draft,
                created_at)
           SELECT 'LOCAL714 BG Test Tour', request_string, 'en', 4,
                  'LOCAL714 — Background Tour', %s, 'members', audio_tour,
                  TRUE, FALSE, NOW()
             FROM audio_tours WHERE id = %s
           RETURNING id""",
        (COMMUNITY_ID, SOURCE_TOUR_ID),
    )
    tour_id = cur.fetchone()[0]

    # Grant the device an ACTIVE membership of community 2 (expires in the
    # future). transaction_id tagged so teardown can find it unambiguously.
    cur.execute(
        """INSERT INTO community_memberships
               (user_id, community_id, expires_at, transaction_id, store,
                product_id, created_at, updated_at)
           VALUES (%s, %s, NOW() + INTERVAL '30 days',
                   %s, 'test', 'local714.test', NOW(), NOW())""",
        (device, COMMUNITY_ID, "LOCAL714-TEST-%s" % tour_id),
    )
    conn.commit()
    after = counts(cur)
    print("AFTER CREATE: audio_tours=%d community_memberships=%d is_test=%d"
          % after)
    print("NEW_TOUR_ID=%d" % tour_id)
    print("MEMBERSHIP: %s active in community %d" % (device, COMMUNITY_ID))
    cur.close()
    conn.close()


def teardown(device, tour_id):
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()
    # Delete the membership we created (guarded by the test transaction_id).
    cur.execute(
        """DELETE FROM community_memberships
            WHERE user_id = %s AND transaction_id = %s""",
        (device, "LOCAL714-TEST-%s" % tour_id),
    )
    # Delete the tour ONLY if it is the is_test row we created.
    cur.execute(
        "DELETE FROM audio_tours WHERE id = %s AND is_test = TRUE", (int(tour_id),)
    )
    conn.commit()
    final = counts(cur)
    print("FINAL: audio_tours=%d community_memberships=%d is_test=%d" % final)
    cur.close()
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    cmd, device = sys.argv[1], sys.argv[2]
    if cmd == "setup":
        setup(device)
    elif cmd == "teardown":
        teardown(device, sys.argv[3])
    else:
        print("unknown command", cmd)
        sys.exit(2)
