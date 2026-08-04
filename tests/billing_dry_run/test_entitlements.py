"""
Test 5: Entitlements gate against audiotours_subscribed.

Exercises:
  - get_user_plan() against users/plans tables
  - _get_subscription_tier() against subscriptions table
  - get_tours_used_today() against tour_requests table
  - get_news_used_period() against article_requests + newsletters_article_link
  - _check_ppu_balance() integration
  - check_tour_quota() / check_news_quota() full paths
"""
import os
import sys
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5433")
os.environ.setdefault("DB_NAME", "audiotours_subscribed")
os.environ.setdefault("DB_USER", "admin")
os.environ.setdefault("DB_PASSWORD", "password123")
os.environ.setdefault("DATABASE_URL",
    "postgresql://admin:password123@localhost:5433/audiotours_subscribed")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import psycopg2


def get_conn():
    return psycopg2.connect(
        host="localhost", port=5433,
        dbname="audiotours_subscribed",
        user="admin", password="password123",
    )


def test_get_user_plan_free(test_user_id):
    """get_user_plan for a free-tier user."""
    from entitlements import get_user_plan
    plan = get_user_plan(test_user_id)
    assert plan["plan_id"] == "free", f"Expected 'free', got {plan['plan_id']}"
    assert plan["tours_per_day"] == 1
    assert plan["tour_max_poi"] == 30
    print(f"  get_user_plan (free) PASS: {plan}")


def test_get_user_plan_ppu(test_user_id):
    """get_user_plan for a PPU user."""
    from entitlements import get_user_plan
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET plan='ppu' WHERE secret_id=%s", (test_user_id,))
    conn.commit()
    cur.close()
    conn.close()

    plan = get_user_plan(test_user_id)
    assert plan["plan_id"] == "ppu", f"Expected 'ppu', got {plan['plan_id']}"
    assert plan["tours_per_day"] == 999
    print(f"  get_user_plan (ppu) PASS: {plan}")


def test_get_subscription_tier_active(test_user_id):
    """_get_subscription_tier finds an active subscription."""
    from entitlements import _get_subscription_tier

    conn = get_conn()
    cur = conn.cursor()
    # Ensure user has ppu plan
    cur.execute("UPDATE users SET plan='ppu' WHERE secret_id=%s", (test_user_id,))
    # Insert active subscription
    now = datetime.now()
    cur.execute("""
        INSERT INTO subscriptions (user_id, tier, state, period_start, period_end)
        VALUES (%s, 'ppu', 'active', %s, %s)
    """, (test_user_id, now - timedelta(days=15), now + timedelta(days=15)))
    conn.commit()
    cur.close()
    conn.close()

    tier = _get_subscription_tier(test_user_id)
    assert tier == "ppu", f"Expected 'ppu', got {tier}"
    print(f"  _get_subscription_tier (active) PASS: tier={tier}")


def test_get_tours_used_today(test_user_id):
    """get_tours_used_today counts correctly from tour_requests."""
    from entitlements import get_tours_used_today

    # Initially zero
    count = get_tours_used_today(test_user_id)
    assert count == 0, f"Expected 0, got {count}"

    # Insert a tour request for today
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tour_requests (secret_id, tour_id, status, source, started_at)
        VALUES (%s, 'tour-test-001', 'completed', 'orchestrator', NOW())
    """, (test_user_id,))
    conn.commit()
    cur.close()
    conn.close()

    count = get_tours_used_today(test_user_id)
    assert count == 1, f"Expected 1, got {count}"
    print(f"  get_tours_used_today PASS: {count}")


def test_get_news_used_period(test_user_id):
    """get_news_used_period — exercises article_requests + newsletters_article_link query.

    This was the key schema mismatch found by the dry run:
    entitlements.py queries newsletters_article_link which was missing from
    audiotours_subscribed (LOCAL-211 did not include it).
    Fixed by migration/sql/011_add_newsletters_article_link.sql.
    """
    from entitlements import get_news_used_period

    # With the fix applied, this should return 0 (no articles for test user)
    count = get_news_used_period(test_user_id, "week")
    assert count == 0, f"Expected 0 for fresh user, got {count}"
    print(f"  get_news_used_period PASS: count={count}")

    # Insert an article request and verify it counts
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO article_requests (secret_id, article_id, status, created_at)
        VALUES (%s, %s, 'completed', NOW())
    """, (test_user_id, f"art-{test_user_id[:8]}"))
    conn.commit()
    cur.close()
    conn.close()

    count = get_news_used_period(test_user_id, "week")
    assert count == 1, f"Expected 1 after inserting article, got {count}"
    print(f"  get_news_used_period after insert PASS: count={count}")


def test_check_tour_quota_ppu_integration(test_user_id):
    """Full check_tour_quota for PPU tier exercises the whole billing gate."""
    from entitlements import check_tour_quota
    from wallet_ledger import topup

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET plan='ppu' WHERE secret_id=%s", (test_user_id,))
    now = datetime.now()
    cur.execute("""
        INSERT INTO subscriptions (user_id, tier, state, period_start, period_end)
        VALUES (%s, 'ppu', 'active', %s, %s)
        ON CONFLICT DO NOTHING
    """, (test_user_id, now - timedelta(days=15), now + timedelta(days=15)))
    conn.commit()
    cur.close()
    conn.close()

    # Top up so balance check passes
    topup(test_user_id, Decimal("10.00"), f"topup-quota-{test_user_id}", "pay-q-001")

    result = check_tour_quota(test_user_id, requested_stops=10)
    assert result["allowed"] is True, f"Expected allowed, got {result}"
    assert result["plan"] == "ppu"
    print(f"  check_tour_quota (ppu, funded) PASS: {result}")


def test_check_tour_quota_ppu_overdraft_breach(test_user_id):
    """check_tour_quota refuses when balance would breach floor."""
    from entitlements import check_tour_quota
    from wallet_ledger import topup, charge

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET plan='ppu' WHERE secret_id=%s", (test_user_id,))
    now = datetime.now()
    cur.execute("""
        INSERT INTO subscriptions (user_id, tier, state, period_start, period_end)
        VALUES (%s, 'ppu', 'active', %s, %s)
        ON CONFLICT DO NOTHING
    """, (test_user_id, now - timedelta(days=15), now + timedelta(days=15)))
    conn.commit()
    cur.close()
    conn.close()

    # Don't top up — balance stays at 0. Tour projected cost is 40¢.
    # 0 - 40 = -40 → above -200 floor → ALLOWED (D41: finish what you started)
    # But we need to test refusal. Balance must be < floor + projected.
    # floor = -200, projected = 40 (tour). Refusal when balance - 40 < -200 → balance < -160.
    # Drive balance to -165¢ via topup/charge cycle
    topup(test_user_id, Decimal("1.00"), f"topup-breach-{test_user_id}", "pay-b-001")
    # balance = 100¢. Charge $2.65 = 265¢ → balance = -165¢
    charge(test_user_id, Decimal("2.65"), f"charge-breach-{test_user_id}",
           description="Drain for breach test")

    result = check_tour_quota(test_user_id, requested_stops=5)
    assert result["allowed"] is False, f"Expected refused, got {result}"
    assert result["reason"] == "overdraft_floor_breach"
    print(f"  check_tour_quota (breach) PASS: refused with reason={result['reason']}")

    print("\n  ✓ ENTITLEMENTS TESTS COMPLETED")
