#!/usr/bin/env python3
"""LOCAL-807B server-side live proof (tiny local test hook).

Runs INSIDE the proof user-api container against the throwaway proof DB. It does
NOT touch the live DB, drives NO real generation, and spends $0 — it exercises
the real LOCAL-807 entitlement-mapping code (subscription_notifications.apply_event,
the same function /subscriptions/verify calls after it verifies the Apple JWS)
to prove, server-side:

  (1) a verified Weekly subscription creates an auto_renew_subscriptions row
      (status=active, period_end set) and drives the device to level sub_week;
  (2) /entitlements/me then reports "5 new tours left" (the weekly allowance,
      the LOCAL-807B fix);
  (3) generating a tour decrements that allowance — simulated by inserting ONE
      delivered tour_requests row (source='orchestrator', status='completed'),
      the SAME rows the allowance gate counts — after which /entitlements/me
      reports "4 new tours left". No real tour is generated.

The Apple JWS crypto is deliberately skipped here: StoreKit configuration-file
testing on the simulator signs with Xcode's local test certificate, which does
not chain to the pinned Apple Root CA G3, so the real verifier rejects it (by
design). apply_event is exactly the post-verification core, so calling it with a
crafted active event proves the server half faithfully.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import psycopg2

sys.path.insert(0, '/app')
import subscription_notifications as sn  # noqa: E402

USER_ID = os.environ.get('PROOF_USER_ID', 'sim-live807')
PRODUCT = 'audioura.sub.weekly'          # -> plan sub_week (migration 060)
ORIGINAL_TXN = 'LOCAL807B-PROOF-WEEKLY-1'


def _me(cur):
    import entitlements_api as ea
    return ea._me_payload(cur, USER_ID)


def main():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()

    # Device starts on l1 (fresh device).
    cur.execute(
        "INSERT INTO device_entitlement (user_id, level) VALUES (%s, 'l1') "
        "ON CONFLICT (user_id) DO UPDATE SET level='l1'", (USER_ID,))
    conn.commit()
    print(f"[start] device {USER_ID} level =",
          _me(cur)['level'], "allowances =", _me(cur)['allowances_left'])

    # (1) Apply a verified ACTIVE Weekly subscription event — the exact object
    #     /subscriptions/verify builds after the Apple JWS checks out.
    period_end = datetime.now(timezone.utc) + timedelta(days=7)
    event = sn.SubscriptionEvent(
        store='apple',
        notification_uuid=f'app_verify:{ORIGINAL_TXN}',
        notification_type='APP_REPORTED_PURCHASE',
        target_status=sn.STATUS_ACTIVE,
        original_transaction_id=ORIGINAL_TXN,
        product_id=PRODUCT,
        period_end=period_end,
        auto_renew=True,
        event_at=datetime.now(timezone.utc),
        raw_summary={'source': 'proof', 'productId': PRODUCT},
    )
    result = sn.apply_event(cur, event, user_id_hint=USER_ID)
    conn.commit()
    print("[apply_event] result =", result)

    cur.execute(
        "SELECT user_id, store, product_id, level, original_transaction_id, "
        "status, period_end, auto_renew, previous_level "
        "FROM auto_renew_subscriptions WHERE original_transaction_id=%s",
        (ORIGINAL_TXN,))
    print("[auto_renew_subscriptions row] =", cur.fetchone())

    me = _me(cur)
    print(f"[after grant] level = {me['level']}  display = {me['display_name']}  "
          f"anniversary_at = {me['anniversary_at']}")
    print("[after grant] allowances_left =", me['allowances_left'])
    assert me['level'] == 'sub_week', me['level']
    assert me['allowances_left'].get('tours_this_week_left') == 5, me['allowances_left']

    # (3) Simulate ONE delivered generation — the row the allowance gate counts.
    #     NOT a real generation: no orchestrator call, no paid API, $0.
    cur.execute(
        "INSERT INTO tour_requests (secret_id, tour_id, status, source, started_at) "
        "VALUES (%s, %s, 'completed', 'orchestrator', now())",
        (USER_ID, 'proof-tour-1'))
    conn.commit()

    me2 = _me(cur)
    print("[after 1 tour] allowances_left =", me2['allowances_left'])
    assert me2['allowances_left'].get('tours_this_week_left') == 4, me2['allowances_left']

    print("\nPROOF OK: Weekly subscription active, period_end set, device on "
          "sub_week, weekly allowance 5 -> 4 after one delivered tour.")
    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
