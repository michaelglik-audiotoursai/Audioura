#!/usr/bin/env python3
"""live_local713_new_tours.py — LOCAL-713 live test (own harness, spare port).

Runs the REAL /communities/new-tours endpoint against the shared dev DB
(read-only except for ONE is_test tour row + ONE test membership that are
created and then DELETED here). It:

  1. captures the BEFORE counts (audio_tours, community_memberships) and the
     is_test=true audio_tours count;
  2. creates one is_test ORIGINAL tour tagged to community 2 + a finished es
     translation of it, and an ACTIVE test membership for a test device;
  3. starts a throwaway Flask app on a SPARE port that mounts communities_api,
     pointed at the DB via DATABASE_URL, with no gateway key required;
  4. GETs /communities/new-tours for the test device and prints the JSON;
  5. captures the AFTER counts;
  6. DELETES exactly the rows it created (by captured ids) and prints the
     FINAL counts, proving the DB is left as it was found.

NEVER touches a non-is_test row. Own harness only — it does not rename or stop
any audioura-* container; it just reads/writes the two test rows and removes
them.
"""
import os
import sys
import json
import time
import threading
import urllib.request
import urllib.parse

import psycopg2

_HERE = os.path.dirname(os.path.abspath(__file__))
_UT = os.path.join(_HERE, "user-tracking")
sys.path.insert(0, _UT)

DB_URL = os.getenv("LIVE_DB_URL",
                   "postgresql://admin:password123@localhost:5433/audiotours")
SPARE_PORT = int(os.getenv("LIVE_PORT", "5099"))
TEST_DEVICE = "LOCAL713-TEST-DEVICE"
COMMUNITY_ID = 2


def counts(cur):
    cur.execute("SELECT count(*) FROM audio_tours")
    at = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM community_memberships")
    cm = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM audio_tours WHERE is_test = TRUE")
    at_test = cur.fetchone()[0]
    return at, cm, at_test


def main():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()

    before = counts(cur)
    print("BEFORE: audio_tours=%d  community_memberships=%d  is_test audio_tours=%d"
          % before)

    created_tour_ids = []
    created_membership = False
    try:
        # ── 1. Create one is_test ORIGINAL tour tagged to community 2 ────────
        cur.execute(
            """INSERT INTO audio_tours
                   (tour_name, request_string, language, stops_count,
                    short_title, community_id, community_visibility, is_test,
                    draft, created_at)
               VALUES (%s, %s, 'en', 4, %s, %s, 'members', TRUE, FALSE, NOW())
               RETURNING id""",
            ("LOCAL713 Test Tour", "local713 test", "LOCAL713 — Walking Tour",
             COMMUNITY_ID),
        )
        original_id = cur.fetchone()[0]
        created_tour_ids.append(original_id)

        # A finished (non-draft) es TRANSLATION of it, so languages == [en, es].
        cur.execute(
            """INSERT INTO audio_tours
                   (tour_name, request_string, language, stops_count,
                    original_tour_id, is_test, draft, created_at)
               VALUES (%s, %s, 'es', 4, %s, TRUE, FALSE, NOW())
               RETURNING id""",
            ("LOCAL713 Test Tour (es)", "local713 test es", original_id),
        )
        translation_id = cur.fetchone()[0]
        created_tour_ids.append(translation_id)

        # ── 2. An ACTIVE test membership for the test device ─────────────────
        cur.execute(
            """INSERT INTO community_memberships
                   (user_id, community_id, expires_at, transaction_id, store,
                    product_id, price_usd)
               VALUES (%s, %s, NOW() + INTERVAL '30 days', %s, 'stub',
                       'audioura.pass.test', 1.0)
               ON CONFLICT (user_id, community_id) DO UPDATE SET
                   expires_at = EXCLUDED.expires_at""",
            (TEST_DEVICE, COMMUNITY_ID, "LOCAL713-TEST-TXN"),
        )
        created_membership = True
        conn.commit()
        print("CREATED: original tour id=%d, es translation id=%d, membership for %s"
              % (original_id, translation_id, TEST_DEVICE))

        after_create = counts(cur)
        print("AFTER CREATE: audio_tours=%d  community_memberships=%d  is_test audio_tours=%d"
              % after_create)

        # ── 3. Start the throwaway Flask app on a spare port ─────────────────
        os.environ["DATABASE_URL"] = DB_URL
        os.environ["ALLOW_UNAUTHENTICATED_ENTITLEMENTS"] = "true"
        os.environ["GATEWAY_API_KEY"] = ""

        from flask import Flask
        import communities_api

        app = Flask(__name__)
        app.register_blueprint(communities_api.communities_bp)

        def run():
            app.run(host="127.0.0.1", port=SPARE_PORT, debug=False,
                    use_reloader=False)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        time.sleep(1.5)  # let the server bind

        # ── 4. Hit the endpoint and print the JSON ───────────────────────────
        url = ("http://127.0.0.1:%d/communities/new-tours?user_id=%s&since="
               % (SPARE_PORT, TEST_DEVICE))
        print("\nGET " + url)
        with urllib.request.urlopen(url, timeout=10) as r:
            body = r.read().decode()
        print("HTTP %d" % r.status)
        parsed = json.loads(body)
        print(json.dumps(parsed, indent=2))

        # A quick assert: our test tour appears with languages [en, es].
        ours = [t for t in parsed.get("tours", [])
                if t.get("tour_id") == original_id]
        assert ours, "test tour not returned by the endpoint!"
        assert ours[0]["languages"] == ["en", "es"], \
            "languages wrong: %r" % ours[0]["languages"]
        assert ours[0]["community_id"] == COMMUNITY_ID
        assert ours[0]["short_title"] == "LOCAL713 — Walking Tour"
        print("\nASSERT OK: test tour returned with languages [en, es], "
              "community_id=%d, short_title carried." % COMMUNITY_ID)

        # Also show the 'since' round trip: using the server_time as since now
        # returns nothing new (the tour is not created strictly after it).
        st = parsed.get("server_time")
        url2 = ("http://127.0.0.1:%d/communities/new-tours?user_id=%s&since=%s"
                % (SPARE_PORT, TEST_DEVICE, urllib.parse.quote(st)))
        with urllib.request.urlopen(url2, timeout=10) as r2:
            body2 = r2.read().decode()
        parsed2 = json.loads(body2)
        ours2 = [t for t in parsed2.get("tours", [])
                 if t.get("tour_id") == original_id]
        print("SINCE=server_time → our tour present again? %s (expected False)"
              % bool(ours2))

        after = counts(cur)
        # refresh the connection's view (another connection wrote nothing; the
        # endpoint is read-only, so counts match after_create).
        conn.rollback()
        print("\nAFTER ENDPOINT (read-only): audio_tours=%d  "
              "community_memberships=%d  is_test audio_tours=%d" % after)

    finally:
        # ── 6. Clean up exactly what we created ──────────────────────────────
        if created_tour_ids:
            cur.execute("DELETE FROM audio_tours WHERE id = ANY(%s) AND is_test = TRUE",
                        (created_tour_ids,))
        if created_membership:
            cur.execute("DELETE FROM community_memberships WHERE user_id = %s AND community_id = %s",
                        (TEST_DEVICE, COMMUNITY_ID))
        conn.commit()
        final = counts(cur)
        print("\nFINAL (after cleanup): audio_tours=%d  community_memberships=%d  "
              "is_test audio_tours=%d" % final)
        print("MATCHES BEFORE? %s" % (final == before))
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
