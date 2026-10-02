#!/usr/bin/env python3
"""
LOCAL-161: Create test users for wallet balance visibility fixes.

States needed:
  1. free_positive  — Free tier, balance $10 (balance should now show)
  2. free_zero      — Free tier, balance $0 (balance should NOT show)
  3. ppu_negative   — PPU, balance -$0.50 (should render -$0.50 not $-0.50)
  4. ppu_healthy    — PPU, balance $10 (unchanged, regression guard)
  5. unlimited_mid  — Unlimited, cost-stop at 50% (unchanged, regression guard)

Run:
    python3 tests/test_local161_wallet_balance_visibility.py
"""

import os
import sys
import uuid
import json
import requests
from datetime import datetime
from decimal import Decimal

# ─── Path setup ──────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_PORT', '5433')
os.environ.setdefault('DB_NAME', 'audiotours')
os.environ.setdefault('DB_USER', 'admin')
os.environ.setdefault('DB_PASSWORD', 'password123')
os.environ.setdefault('DATABASE_URL', 'postgresql://admin:password123@localhost:5433/audiotours')

from db_connection import get_connection, check_db_available

# ─── Configuration ───────────────────────────────────────────────────────────
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://192.168.0.136:5102")
RUN_ID = uuid.uuid4().hex[:8]

USERS = {
    "free_positive":  f"test_161_free_pos_{RUN_ID}",
    "free_zero":      f"test_161_free_zero_{RUN_ID}",
    "ppu_negative":   f"test_161_ppu_neg_{RUN_ID}",
    "ppu_healthy":    f"test_161_ppu_healthy_{RUN_ID}",
    "unlimited_mid":  f"test_161_unlim_{RUN_ID}",
}


def api_get(path):
    r = requests.get(f"{ORCHESTRATOR_URL}{path}", timeout=10)
    return r.status_code, r.json() if r.status_code == 200 else r.text


def api_post(path, body):
    r = requests.post(f"{ORCHESTRATOR_URL}{path}", json=body, timeout=15)
    return r.status_code, r.json() if r.status_code == 200 else r.text


def create_user_in_db(user_id, plan='free'):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO users (secret_id, plan, created_at, updated_at)
            VALUES (%s, %s, NOW(), NOW())
            ON CONFLICT (secret_id) DO NOTHING
        """, (user_id, plan))
    conn.commit()
    conn.close()


def get_ledger_count(user_id):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM wallet_ledger WHERE user_id = %s", (user_id,))
        count = cur.fetchone()[0]
    conn.close()
    return count


def inject_charge(user_id, amount_cents, description="Simulated charge"):
    """Insert charge and update balance cache. amount_cents is positive (will be subtracted)."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT balance_cents FROM wallet_balance_cache WHERE user_id = %s
        """, (user_id,))
        row = cur.fetchone()
        if not row:
            print(f"  ⚠ No balance cache for {user_id}")
            conn.close()
            return None
        current = row[0]
        new_balance = current - amount_cents

        cur.execute("""
            INSERT INTO wallet_ledger (id, user_id, movement_type, amount_cents,
                balance_after_cents, description, idempotency_key, created_at)
            VALUES (gen_random_uuid(), %s, 'charge', %s, %s, %s, %s, NOW())
        """, (user_id, -amount_cents, new_balance, description,
              f"inject:{user_id}:{uuid.uuid4().hex[:12]}"))

        cur.execute("""
            UPDATE wallet_balance_cache SET balance_cents = %s, updated_at = NOW()
            WHERE user_id = %s
        """, (new_balance, user_id))

    conn.commit()
    conn.close()
    return new_balance


def inject_cost_ledger(user_id, our_cost_usd, job_id=None):
    """Insert cost_ledger + update monthly_cost_spent_cents for unlimited cost-stop."""
    if job_id is None:
        job_id = str(uuid.uuid4())
    our_cost_cents = int(Decimal(str(our_cost_usd)) * 100)
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO cost_ledger (id, operation_type, our_cost_usd, cache_hit,
                job_id, user_id, created_at)
            VALUES (gen_random_uuid(), 'tour_generate', %s, FALSE, %s, %s, NOW())
        """, (our_cost_usd, job_id, user_id))
        cur.execute("""
            UPDATE wallet_subscription
            SET monthly_cost_spent_cents = monthly_cost_spent_cents + %s
            WHERE user_id = %s
        """, (our_cost_cents, user_id))
    conn.commit()
    conn.close()


def main():
    print("=" * 70)
    print("LOCAL-161: Create test users for wallet balance visibility")
    print("=" * 70)
    print(f"  Run ID:       {RUN_ID}")
    print(f"  Orchestrator: {ORCHESTRATOR_URL}")
    print(f"  Time:         {datetime.now().isoformat()}")
    print()

    # ─── Connectivity ────────────────────────────────────────────────────
    if not check_db_available():
        print("ERROR: Database not available")
        sys.exit(7)

    try:
        r = requests.get(f"{ORCHESTRATOR_URL}/health", timeout=5)
        if r.status_code != 200:
            print(f"ERROR: Orchestrator unhealthy: {r.status_code}")
            sys.exit(7)
    except Exception as e:
        print(f"ERROR: Orchestrator unreachable: {e}")
        sys.exit(7)
    print("  Infrastructure: DB ✓  Orchestrator ✓\n")

    # ═══════════════════════════════════════════════════════════════════════
    # 1. Free tier, positive balance ($10)
    # Approach: create user, topup works directly on free tier per LOCAL-158
    # ═══════════════════════════════════════════════════════════════════════
    print("─" * 60)
    print("USER 1: Free tier, positive balance ($10)")
    user = USERS["free_positive"]
    print(f"  ID: {user}")
    create_user_in_db(user, plan='free')
    status, resp = api_post(f"/wallet/{user}/topup", {"product_id": "credit_topup_10"})
    print(f"  Top-up: {status} → {json.dumps(resp) if isinstance(resp, dict) else resp}")
    status, wallet = api_get(f"/wallet/{user}")
    print(f"  Wallet: {json.dumps(wallet)}")
    assert wallet.get("plan") == "free", f"Expected free, got {wallet.get('plan')}"
    assert wallet.get("balance_usd") == 10.0, f"Expected 10.0, got {wallet.get('balance_usd')}"
    print(f"  ✓ Free tier with $10 balance")
    print(f"  Ledger rows: {get_ledger_count(user)}")
    print()

    # ═══════════════════════════════════════════════════════════════════════
    # 2. Free tier, zero balance
    # ═══════════════════════════════════════════════════════════════════════
    print("─" * 60)
    print("USER 2: Free tier, zero balance")
    user = USERS["free_zero"]
    print(f"  ID: {user}")
    create_user_in_db(user, plan='free')
    status, wallet = api_get(f"/wallet/{user}")
    print(f"  Wallet: {json.dumps(wallet)}")
    assert wallet.get("plan") == "free"
    assert wallet.get("balance_usd") == 0.0
    print(f"  ✓ Free tier with $0 balance")
    print(f"  Ledger rows: {get_ledger_count(user)}")
    print()

    # ═══════════════════════════════════════════════════════════════════════
    # 3. PPU, negative balance (-$0.50)
    # Approach: change-tier to ppu (grants $10), then inject charge $10.50
    # ═══════════════════════════════════════════════════════════════════════
    print("─" * 60)
    print("USER 3: PPU, negative balance (-$0.50)")
    user = USERS["ppu_negative"]
    print(f"  ID: {user}")
    create_user_in_db(user, plan='free')
    status, resp = api_post(f"/wallet/{user}/change-tier", {"target_tier": "ppu"})
    print(f"  Change-tier to PPU: {status} → {json.dumps(resp) if isinstance(resp, dict) else resp}")
    if status != 200:
        print(f"  ⚠ change-tier failed, checking state...")
    # Verify current state
    status, wallet = api_get(f"/wallet/{user}")
    print(f"  Wallet after tier change: plan={wallet.get('plan')}, balance={wallet.get('balance_usd')}")

    # If change-tier gave $10, drain to -$0.50 (charge 1050¢)
    # If it failed but topup worked (balance $0), topup first then drain
    current_balance = wallet.get("balance_usd", 0)
    if wallet.get("plan") != "ppu":
        # Fallback: set plan directly in DB and topup
        print(f"  → Fallback: setting plan=ppu in DB directly")
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET plan = 'ppu' WHERE secret_id = %s", (user,))
            # Ensure wallet_subscription exists
            cur.execute("""
                INSERT INTO wallet_subscription (id, user_id, plan, status, created_at, updated_at,
                    period_start, period_end, monthly_cost_spent_cents)
                VALUES (gen_random_uuid(), %s, 'ppu', 'active', NOW(), NOW(),
                    NOW(), NOW() + INTERVAL '30 days', 0)
                ON CONFLICT (user_id) DO UPDATE SET plan = 'ppu', status = 'active',
                    period_start = NOW(), period_end = NOW() + INTERVAL '30 days'
            """, (user,))
            # Ensure balance cache exists
            cur.execute("""
                INSERT INTO wallet_balance_cache (user_id, balance_cents, updated_at)
                VALUES (%s, 0, NOW())
                ON CONFLICT (user_id) DO NOTHING
            """, (user,))
        conn.commit()
        conn.close()
        # Top up $10
        status, resp = api_post(f"/wallet/{user}/topup", {"product_id": "credit_topup_10"})
        print(f"  Top-up after DB fix: {status}")
        status, wallet = api_get(f"/wallet/{user}")
        current_balance = wallet.get("balance_usd", 0)
        print(f"  After fix: plan={wallet.get('plan')}, balance={current_balance}")

    # Now drain to -$0.50 from current balance
    drain_cents = int((current_balance + 0.50) * 100)
    new_bal = inject_charge(user, drain_cents, "Overcharge (test negative)")
    print(f"  Injected charge {drain_cents}¢ → balance = {new_bal}¢")

    status, wallet = api_get(f"/wallet/{user}")
    print(f"  Final wallet: {json.dumps(wallet)}")
    assert wallet.get("balance_usd") == -0.5 or abs(wallet.get("balance_usd", 0) - (-0.5)) < 0.01, \
        f"Expected -0.5, got {wallet.get('balance_usd')}"
    print(f"  ✓ PPU with -$0.50 balance")
    print(f"  Ledger rows: {get_ledger_count(user)}")
    print()

    # ═══════════════════════════════════════════════════════════════════════
    # 4. PPU, healthy balance ($10) — regression guard
    # change-tier to ppu grants $10 automatically, no separate topup needed
    # ═══════════════════════════════════════════════════════════════════════
    print("─" * 60)
    print("USER 4: PPU, healthy balance ($10)")
    user = USERS["ppu_healthy"]
    print(f"  ID: {user}")
    create_user_in_db(user, plan='free')
    status, resp = api_post(f"/wallet/{user}/change-tier", {"target_tier": "ppu"})
    print(f"  Change-tier to PPU: {status}")
    if status != 200:
        # Fallback: set plan in DB directly + inject $10
        print(f"  → Fallback: setting plan=ppu in DB directly")
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET plan = 'ppu' WHERE secret_id = %s", (user,))
            cur.execute("""
                INSERT INTO wallet_subscription (id, user_id, plan, status, created_at, updated_at,
                    period_start, period_end, monthly_cost_spent_cents)
                VALUES (gen_random_uuid(), %s, 'ppu', 'active', NOW(), NOW(),
                    NOW(), NOW() + INTERVAL '30 days', 0)
                ON CONFLICT (user_id) DO UPDATE SET plan = 'ppu', status = 'active',
                    period_start = NOW(), period_end = NOW() + INTERVAL '30 days'
            """, (user,))
            cur.execute("""
                INSERT INTO wallet_balance_cache (user_id, balance_cents, updated_at)
                VALUES (%s, 1000, NOW())
                ON CONFLICT (user_id) DO UPDATE SET balance_cents = 1000
            """, (user,))
        conn.commit()
        conn.close()
    status, wallet = api_get(f"/wallet/{user}")
    print(f"  Wallet: {json.dumps(wallet)}")
    assert wallet.get("plan") == "ppu", f"Expected ppu, got {wallet.get('plan')}"
    assert wallet.get("balance_usd") == 10.0, f"Expected 10.0, got {wallet.get('balance_usd')}"
    print(f"  ✓ PPU with $10 balance")
    print(f"  Ledger rows: {get_ledger_count(user)}")
    print()

    # ═══════════════════════════════════════════════════════════════════════
    # 5. Unlimited, cost-stop at 50% — regression guard
    # ═══════════════════════════════════════════════════════════════════════
    print("─" * 60)
    print("USER 5: Unlimited, cost-stop at 50%")
    user = USERS["unlimited_mid"]
    print(f"  ID: {user}")
    create_user_in_db(user, plan='free')
    status, resp = api_post(f"/wallet/{user}/change-tier", {"target_tier": "unlimited"})
    print(f"  Change-tier to unlimited: {status}")
    if status != 200:
        # Fallback: set plan in DB directly
        print(f"  → Fallback: setting plan=unlimited in DB directly")
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET plan = 'unlimited' WHERE secret_id = %s", (user,))
            cur.execute("""
                INSERT INTO wallet_subscription (id, user_id, plan, status, created_at, updated_at,
                    period_start, period_end, monthly_cost_spent_cents, cost_stop_usd)
                VALUES (gen_random_uuid(), %s, 'unlimited', 'active', NOW(), NOW(),
                    NOW(), NOW() + INTERVAL '30 days', 0, 25.00)
                ON CONFLICT (user_id) DO UPDATE SET plan = 'unlimited', status = 'active',
                    period_start = NOW(), period_end = NOW() + INTERVAL '30 days',
                    cost_stop_usd = 25.00, monthly_cost_spent_cents = 0
            """, (user,))
            cur.execute("""
                INSERT INTO wallet_balance_cache (user_id, balance_cents, updated_at)
                VALUES (%s, 0, NOW())
                ON CONFLICT (user_id) DO NOTHING
            """, (user,))
        conn.commit()
        conn.close()

    # Inject cost to get 50% ($12.50 of $25 limit)
    inject_cost_ledger(user, 12.50)
    print(f"  Injected $12.50 cost → 50% of $25 limit")
    status, wallet = api_get(f"/wallet/{user}")
    print(f"  Wallet: {json.dumps(wallet)}")
    assert wallet.get("plan") == "unlimited", f"Expected unlimited, got {wallet.get('plan')}"
    cost_stop = wallet.get("cost_stop_progress")
    if cost_stop:
        print(f"  ✓ Unlimited with cost-stop: ${cost_stop['used_usd']:.2f} / ${cost_stop['limit_usd']:.2f}")
    else:
        print(f"  ⚠ cost_stop_progress is null — may need DB adjustment")
    print(f"  Ledger rows: {get_ledger_count(user)}")
    print()

    # ═══════════════════════════════════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════════════════════════════════
    print("=" * 70)
    print("ALL USERS CREATED")
    print("=" * 70)
    print(f"\n  RUN_ID = {RUN_ID}\n")
    for label, uid in USERS.items():
        count = get_ledger_count(uid)
        print(f"  {label:20s} → {uid} (ledger: {count})")
    print()
    print(f"  Flutter command:")
    print(f"  cd audio_tour_app && flutter test integration_test/wallet_balance_visibility_test.dart \\")
    print(f"    --dart-define=WALLET_DEBUG_PORT=5102 \\")
    print(f"    --dart-define=DEBUG_SERVER_IP=192.168.0.136 \\")
    print(f"    --dart-define=LOCAL161_RUN_ID={RUN_ID} \\")
    print(f"    -d macos")
    print()


if __name__ == "__main__":
    main()
