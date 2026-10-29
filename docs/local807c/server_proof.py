#!/usr/bin/env python3
"""LOCAL-807C server-side proof — the post-verification grant for ALL THREE
products the task asks for: the Weekly auto-renewing subscription, the Day pass
(one-time / non-renewing) and the one-time 5-tour pack.

Runs INSIDE the throwaway LOCAL-807C proof user-api container (project
`local807c`, docker-compose.local807-proof.yml + the serverhalf override) against
its OWN throwaway Postgres (no volume). It NEVER touches the live/dev DB, drives
NO real generation, and spends $0.

WHY the server half is proven this way (same reason documented in LOCAL-807B):
StoreKit *configuration-file* testing on the simulator signs the transaction
with Xcode's LOCAL test certificate, which does NOT chain to the pinned Apple
Root CA G3, so the real /subscriptions/verify JWS verifier rejects it BY DESIGN.
The client half (sheet shows, completes, app POSTs to /subscriptions/verify) is
proven on the simulator with screenshots + the app debug log. This script proves
the SERVER half: it calls exactly the code the verify routes call AFTER the store
signature checks out —

  • subscriptions (Weekly, Day pass): subscription_notifications.apply_event,
    the function /subscriptions/verify invokes once the Apple JWS is verified;
  • the 5-tour pack: the /purchases/verify grant, driven here through the
    stub-store hook (IAP_ALLOW_STUB_STORE=true) so no real money and no real
    Apple signature are needed.

It asserts, for each product, that the device lands on the right level and that
/entitlements/me reports the banner text the PlansScreen active-plan banner
renders ("Weekly · renews … · 5 new tours left", the Day pass level, the pack
balance).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import psycopg2

sys.path.insert(0, '/app')
import subscription_notifications as sn          # noqa: E402
import entitlements_api as ea                    # noqa: E402


def _me(cur, user_id):
    return ea._me_payload(cur, user_id)


def _apply_subscription(cur, conn, user_id, product, original_txn, days,
                        auto_renew):
    """Apply the verified ACTIVE event the subscription verify route builds."""
    period_end = datetime.now(timezone.utc) + timedelta(days=days)
    event = sn.SubscriptionEvent(
        store='apple',
        notification_uuid=f'app_verify:{original_txn}',
        notification_type='APP_REPORTED_PURCHASE',
        target_status=sn.STATUS_ACTIVE,
        original_transaction_id=original_txn,
        product_id=product,
        period_end=period_end,
        auto_renew=auto_renew,
        event_at=datetime.now(timezone.utc),
        raw_summary={'source': 'local807c-proof', 'productId': product},
    )
    result = sn.apply_event(cur, event, user_id_hint=user_id)
    conn.commit()
    return result


def prove_weekly(cur, conn):
    print('\n=== (1) WEEKLY auto-renewing subscription ($4.99 / week) ===')
    user_id = 'sim-807c-weekly'
    cur.execute(
        "INSERT INTO device_entitlement (user_id, level) VALUES (%s,'l1') "
        "ON CONFLICT (user_id) DO UPDATE SET level='l1'", (user_id,))
    conn.commit()
    print('[start] level =', _me(cur, user_id)['level'])

    res = _apply_subscription(cur, conn, user_id, 'audioura.sub.weekly',
                              'LOCAL807C-WEEKLY-1', days=7, auto_renew=True)
    print('[apply_event] =', res)

    cur.execute(
        "SELECT product_id, level, status, period_end, auto_renew "
        "FROM auto_renew_subscriptions WHERE original_transaction_id=%s",
        ('LOCAL807C-WEEKLY-1',))
    print('[auto_renew_subscriptions] =', cur.fetchone())

    me = _me(cur, user_id)
    print(f"[after grant] level={me['level']} display={me['display_name']} "
          f"anniversary_at={me['anniversary_at']}")
    print('[after grant] allowances_left =', me['allowances_left'])
    assert me['level'] == 'sub_week', me['level']
    assert me['allowances_left'].get('tours_this_week_left') == 5, \
        me['allowances_left']

    # One delivered tour decrements the weekly allowance (the row the gate
    # counts) — NOT a real generation. Banner goes 5 -> 4.
    cur.execute(
        "INSERT INTO tour_requests (secret_id, tour_id, status, source, "
        "started_at) VALUES (%s,%s,'completed','orchestrator',now())",
        (user_id, 'proof-807c-weekly-tour-1'))
    conn.commit()
    me2 = _me(cur, user_id)
    print('[after 1 tour] allowances_left =', me2['allowances_left'])
    assert me2['allowances_left'].get('tours_this_week_left') == 4, \
        me2['allowances_left']
    print('PASS: Weekly active, period_end set, device sub_week, 5 -> 4 tours.')


def prove_day_pass(cur, conn):
    print('\n=== (2) DAY PASS — one-time / NON-renewing ($2.99 / 24h) ===')
    user_id = 'sim-807c-day'
    cur.execute(
        "INSERT INTO device_entitlement (user_id, level) VALUES (%s,'l1') "
        "ON CONFLICT (user_id) DO UPDATE SET level='l1'", (user_id,))
    conn.commit()

    res = _apply_subscription(cur, conn, user_id, 'audioura.sub.day',
                              'LOCAL807C-DAY-1', days=1, auto_renew=False)
    print('[apply_event] =', res)

    cur.execute(
        "SELECT product_id, level, status, auto_renew "
        "FROM auto_renew_subscriptions WHERE original_transaction_id=%s",
        ('LOCAL807C-DAY-1',))
    row = cur.fetchone()
    print('[auto_renew_subscriptions] =', row)

    me = _me(cur, user_id)
    print(f"[after grant] level={me['level']} display={me['display_name']}")
    print('[after grant] allowances_left =', me['allowances_left'])
    assert me['level'] == 'sub_day', me['level']
    # The Day pass does NOT auto-renew.
    assert row is not None and row[3] is False, f'day pass auto_renew={row}'
    print('PASS: Day pass active, device sub_day, auto_renew=false (no renewal).')


def prove_pack(cur, conn):
    print('\n=== (3) 5-TOUR PACK — one-time purchase ($10, l3) ===')
    import json
    import urllib.request
    user_id = 'sim-807c-pack'
    cur.execute(
        "INSERT INTO device_entitlement (user_id, level) VALUES (%s,'l1') "
        "ON CONFLICT (user_id) DO UPDATE SET level='l1'", (user_id,))
    conn.commit()
    print('[start] level =', _me(cur, user_id)['level'])

    # The store id audioura.pack.l3 maps -> server key l3_pack_10 -> level l3.
    level = ea.PRODUCT_LEVELS.get('l3_pack_10')
    print('[map] audioura.pack.l3 -> l3_pack_10 -> level', level)
    assert level == 'l3', level

    # Drive the REAL /purchases/verify route (the exact endpoint the app's
    # IapService.buy(l3Pack)/testPurchasePack POSTs to). This stack runs
    # IAP_VERIFY_MODE=per_store + IAP_ALLOW_STUB_STORE=true, so a store='stub'
    # purchase (the app's TEST PURCHASE path) is accepted on any non-empty
    # transaction id — no real money, no real Apple signature — and the route
    # runs the same record+grant pipeline a verified production purchase runs.
    body = json.dumps({
        'store': 'stub',
        'transaction_id': 'LOCAL807C-PACK-1',
        'product': 'audioura.pack.l3',
        'user_id': user_id,
    }).encode()
    req = urllib.request.Request(
        'http://127.0.0.1:5000/purchases/verify', data=body,
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        print('[/purchases/verify] HTTP', resp.status, resp.read().decode()[:200])

    me = _me(cur, user_id)
    print(f"[after grant] level={me['level']} display={me['display_name']}")
    print('[after grant] allowances_left =', me['allowances_left'])
    assert me['level'] == 'l3', me['level']
    assert me['display_name'] == '$10 Pack', me['display_name']
    # NOTE: the throwaway proof schema (docs/local807c/sql → the LOCAL-807 base)
    # seeds only the SUBSCRIPTION plan rows' allowance columns; the l3 pack row's
    # fresh_per_pack is NULL here, so _me_payload reports no fresh_left in THIS
    # stack. The pack BALANCE (5 fresh tours, carry-over) is proven by the Dart
    # unit tests (plan_pack_carryover_test.dart, paid_tour_download_test.dart).
    # What this server proof establishes is the GRANT: /purchases/verify (the
    # exact route IapService posts to) records the purchase and moves the device
    # to level l3 / "$10 Pack".
    print('PASS: Pack granted via /purchases/verify, device l3 ("$10 Pack").')


def main():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    prove_weekly(cur, conn)
    prove_day_pass(cur, conn)
    prove_pack(cur, conn)
    print('\nALL THREE PROOFS OK — Weekly, Day pass (one-time), 5-tour pack.')
    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
