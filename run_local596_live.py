#!/usr/bin/env python3
"""run_local596_live.py — LOCAL-596 live walkthrough (test DB + stub user-api).

Walks the whole L2 seat lifecycle end to end:
  * show Michael's PRODUCTION row before (must be unaffected),
  * fill the seats to 99 with synthetic LOCAL596- devices,
  * install a new device -> L1 (seats >= auto-grant threshold),
  * that device joins the FIFO queue (via the stub user-api HTTP endpoint),
  * age one existing L2 seat 8 days,
  * run the hourly job (l2_seat_job) -> evict the idle seat, offer the freed
    seat to the queue head,
  * the device claims the offer (via the stub HTTP endpoint) -> L2,
  * clean up ONLY the exact LOCAL596- ids captured here, report counts
    before/after,
  * show Michael's PRODUCTION row after (unchanged).

HTTP calls go to the stub container `local596-user-api` (never an audioura-*
container). Seat-filling and ageing are DB writes to audiotours_test. $0 spend.
"""
import os
import sys
import json
import uuid
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))

import psycopg2

TEST_DB = 'postgresql://admin:password123@localhost:5433/audiotours_test'
STUB = 'local596-user-api'          # stub container name on development_default
NET = 'development_default'
KEY = 'local596-key'
PREFIX = 'LOCAL596-LIVE-'

os.environ['DATABASE_URL'] = TEST_DB
import l2_seats
import l2_seat_job

created_ids = []  # EXACT cleanup list


def db():
    return psycopg2.connect(TEST_DB)


def curl(method, path, body=None):
    """HTTP to the stub via a throwaway curl container on the same docker net."""
    args = ['docker', 'run', '--rm', '--network', NET, 'curlimages/curl:latest',
            '-s', '-X', method, f'http://{STUB}:5000{path}',
            '-H', f'X-API-Key: {KEY}', '-H', 'Content-Type: application/json']
    if body is not None:
        args += ['-d', json.dumps(body)]
    out = subprocess.check_output(args, text=True)
    return json.loads(out) if out.strip() else {}


def michael_prod():
    out = subprocess.check_output(
        ['docker', 'exec', 'development-postgres-2-1', 'psql', '-U', 'admin',
         '-d', 'audiotours', '-tA', '-c',
         "SELECT user_id, level FROM device_entitlement WHERE user_id='USER-1073427300';"],
        text=True)
    return out.strip()


def main():
    print("=" * 70)
    print("LOCAL-596 LIVE WALKTHROUGH")
    print("=" * 70)

    print("\n[0] Michael's PRODUCTION row BEFORE:", michael_prod())

    c = db(); cur = c.cursor()
    base = l2_seats.seats_in_use(cur)
    threshold = l2_seats.get_settings(cur)['auto_grant_threshold']
    cap = l2_seats.get_seat_cap(cur)
    print(f"\n[1] Baseline: seats_in_use={base}, threshold={threshold}, cap={cap}")

    # Fill to 99 seats using synthetic LOCAL596- devices.
    need = 99 - base
    print(f"[2] Filling to 99 seats ({need} synthetic L2 devices)...")
    for i in range(max(0, need)):
        u = PREFIX + f'FILL{i:03d}-' + uuid.uuid4().hex[:6]
        created_ids.append(u)
        cur.execute("INSERT INTO device_entitlement (user_id,level,last_activity_at) VALUES (%s,'l2',NOW())", (u,))
    c.commit()
    print(f"    seats_in_use now = {l2_seats.seats_in_use(cur)}")

    # Install a new device -> expect L1 (99 >= threshold 50).
    newbie = PREFIX + 'NEWBIE-' + uuid.uuid4().hex[:8]
    created_ids.append(newbie)
    lvl = l2_seats.grant_on_install(cur, newbie); c.commit()
    print(f"\n[3] Install {newbie} -> level={lvl} (expected l1: seats>=threshold)")
    assert lvl == 'l1', f"expected l1, got {lvl}"

    # Newbie joins the queue via the stub HTTP endpoint.
    j = curl('POST', '/l2/queue/join', {'user_id': newbie})
    print(f"[4] Join via stub API -> queue_position={j.get('queue_position')}")
    assert j.get('queue_position') == 1

    # Age one existing L2 seat 8 days (pick one of our FILL devices).
    aged = created_ids[0]
    cur.execute("UPDATE device_entitlement SET last_activity_at = NOW() - INTERVAL '8 days' WHERE user_id=%s", (aged,))
    c.commit()
    print(f"\n[5] Aged seat {aged} to 8 days idle")

    # Run the hourly job: evict the idle seat, offer the freed seat to the head.
    summary = l2_seat_job.run_once(conn=c, quiet=True)
    print(f"[6] Job ran. evicted={aged in summary['evicted']}, "
          f"offered_to_newbie={any(u==newbie for (u,_c) in summary['offered'])}")
    assert aged in summary['evicted']
    offered_codes = {u: code for (u, code) in summary['offered']}
    assert newbie in offered_codes
    code = offered_codes[newbie]
    print(f"    offer code for newbie = {code}")

    # Newbie claims the offer via the stub HTTP endpoint -> L2.
    claim = curl('POST', '/l2/claim', {'user_id': newbie, 'code': code})
    print(f"[7] Claim via stub API -> level={claim.get('level')}")
    assert claim.get('level') == 'l2'

    # Final seat count.
    final_seats = l2_seats.seats_in_use(cur)
    print(f"\n[8] Final seats_in_use={final_seats} (99 - 1 evicted + 1 claimed = 99)")

    # Report counts and clean up ONLY our exact ids.
    print(f"\n[9] Cleanup: removing exactly {len(created_ids)} LOCAL596- ids")
    before_rows = l2_seats.seats_in_use(cur)
    for u in created_ids:
        cur.execute("DELETE FROM l2_offers WHERE user_id=%s", (u,))
        cur.execute("DELETE FROM l2_queue WHERE user_id=%s", (u,))
        cur.execute("DELETE FROM device_entitlement WHERE user_id=%s", (u,))
    c.commit()
    after_rows = l2_seats.seats_in_use(cur)
    print(f"    seats_in_use before cleanup={before_rows}, after cleanup={after_rows} (back to baseline {base})")
    # Prove no LOCAL596- rows remain anywhere.
    cur.execute("SELECT COUNT(*) FROM device_entitlement WHERE user_id LIKE 'LOCAL596-%'")
    de_left = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM l2_queue WHERE user_id LIKE 'LOCAL596-%'")
    q_left = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM l2_offers WHERE user_id LIKE 'LOCAL596-%'")
    o_left = cur.fetchone()[0]
    print(f"    residual LOCAL596- rows: device_entitlement={de_left}, l2_queue={q_left}, l2_offers={o_left}")
    assert de_left == 0 and q_left == 0 and o_left == 0

    cur.close(); c.close()

    print("\n[10] Michael's PRODUCTION row AFTER:", michael_prod())
    print("\n" + "=" * 70)
    print("WALKTHROUGH COMPLETE — all assertions passed, $0 spend")
    print("=" * 70)


if __name__ == '__main__':
    main()
