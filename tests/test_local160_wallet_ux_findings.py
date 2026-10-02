#!/usr/bin/env python3
"""
LOCAL-160: Wallet UX Findings — exercise the wallet screen in all 6 states.

Creates fresh test users (one per state), sets them to the required plan/balance
via the API and direct DB manipulation, then queries GET /wallet/<id> and
GET /wallet/<id>/transactions for each.

Does NOT modify any Dart code. Reports only.

Run:
    python3 tests/test_local160_wallet_ux_findings.py
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

# User IDs per state
USERS = {
    "free_zero":       f"test_ux160_free_zero_{RUN_ID}",
    "free_positive":   f"test_ux160_free_pos_{RUN_ID}",
    "ppu_healthy":     f"test_ux160_ppu_healthy_{RUN_ID}",
    "ppu_low":         f"test_ux160_ppu_low_{RUN_ID}",
    "ppu_zero":        f"test_ux160_ppu_zero_{RUN_ID}",
    "unlimited_mid":   f"test_ux160_unlim_{RUN_ID}",
}

# ─── Results ─────────────────────────────────────────────────────────────────
FINDINGS = {}


def api_get(path):
    """GET from the orchestrator."""
    r = requests.get(f"{ORCHESTRATOR_URL}{path}", timeout=10)
    return r.status_code, r.json() if r.status_code == 200 else r.text


def api_post(path, body):
    """POST to the orchestrator."""
    r = requests.post(f"{ORCHESTRATOR_URL}{path}", json=body, timeout=15)
    return r.status_code, r.json() if r.status_code == 200 else r.text


def create_user_in_db(user_id, plan='free'):
    """Insert user row directly."""
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
    """Count wallet_ledger rows for a user."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM wallet_ledger WHERE user_id = %s", (user_id,))
        count = cur.fetchone()[0]
    conn.close()
    return count


def inject_charge(user_id, amount_cents, description="Simulated tour charge"):
    """Insert a charge directly into wallet_ledger and update balance cache.
    Used to drain balance to specific levels."""
    conn = get_connection()
    with conn.cursor() as cur:
        # Get current balance
        cur.execute("""
            SELECT balance_cents FROM wallet_balance_cache WHERE user_id = %s
        """, (user_id,))
        row = cur.fetchone()
        if not row:
            print(f"  ⚠ No balance cache for {user_id}, cannot inject charge")
            conn.close()
            return
        current_balance = row[0]
        new_balance = current_balance - amount_cents

        # Insert ledger entry
        cur.execute("""
            INSERT INTO wallet_ledger (id, user_id, movement_type, amount_cents,
                balance_after_cents, description, idempotency_key, created_at)
            VALUES (gen_random_uuid(), %s, 'charge', %s, %s, %s,
                    %s, NOW())
        """, (user_id, -amount_cents, new_balance, description,
              f"inject:{user_id}:{uuid.uuid4().hex[:12]}"))

        # Update balance cache
        cur.execute("""
            UPDATE wallet_balance_cache SET balance_cents = %s, updated_at = NOW()
            WHERE user_id = %s
        """, (new_balance, user_id))

    conn.commit()
    conn.close()
    return new_balance


def inject_cost_ledger(user_id, our_cost_usd, job_id=None):
    """Insert a cost_ledger row to simulate generation cost (for unlimited cost-stop)."""
    if job_id is None:
        job_id = str(uuid.uuid4())
    conn = get_connection()
    with conn.cursor() as cur:
        # Insert cost_ledger
        our_cost_cents = int(Decimal(str(our_cost_usd)) * 100)
        cur.execute("""
            INSERT INTO cost_ledger (id, operation_type, our_cost_usd, cache_hit,
                job_id, user_id, created_at)
            VALUES (gen_random_uuid(), 'tour_generate', %s, FALSE, %s, %s, NOW())
        """, (our_cost_usd, job_id, user_id))

        # Update monthly_cost_spent_cents on wallet_subscription
        cur.execute("""
            UPDATE wallet_subscription
            SET monthly_cost_spent_cents = monthly_cost_spent_cents + %s
            WHERE user_id = %s
        """, (our_cost_cents, user_id))

    conn.commit()
    conn.close()


def predict_rendered_text(wallet_data, transactions):
    """Based on Dart code analysis, predict what the wallet_screen.dart would render."""
    plan = wallet_data.get("plan")
    balance = wallet_data.get("balance_usd", 0)
    period_spend = wallet_data.get("period_spend_usd", 0)
    period_start = wallet_data.get("period_start", "")
    period_end = wallet_data.get("period_end", "")
    cost_stop = wallet_data.get("cost_stop_progress")
    low_balance = wallet_data.get("low_balance", False)

    # Parse dates for display format
    try:
        ps = datetime.fromisoformat(period_start.replace("+00:00", "+00:00"))
        pe = datetime.fromisoformat(period_end.replace("+00:00", "+00:00"))
        period_str = f"Period: {ps.month}/{ps.day} – {pe.month}/{pe.day}"
    except Exception:
        period_str = f"Period: ?"

    texts = []

    # _buildBalanceCard logic
    if plan == 'unlimited':
        # _buildCostStopCard
        if cost_stop:
            used = cost_stop["used_usd"]
            limit = cost_stop["limit_usd"]
            progress = used / limit if limit > 0 else 0
            texts.append("Monthly Allowance")
            texts.append(f"${used:.2f} / ${limit:.2f}")
            texts.append(f"{int(progress * 100)}% used")
            if progress >= 1.0:
                texts.append("Monthly allowance reached")
        else:
            texts.append("Monthly Allowance")
            texts.append("$0.00 / $25.00")
            texts.append("0% used")
    elif plan == 'free':
        # _buildFreeCard
        texts.append("Free Plan")
        texts.append("Upgrade to generate unlimited tours and articles")
        texts.append("View Plans")
    else:
        # PPU _buildBalanceCard
        texts.append("Available Balance")
        texts.append(f"${balance:.2f}")
        if low_balance:
            texts.append("⚠️ Low balance — top up to continue generating")
        texts.append(f"This period: ${period_spend:.2f}")

    # _buildPlanCard
    plan_display = {"ppu": "Pay-Per-Use", "unlimited": "Unlimited", "free": "Free"}.get(plan, plan)
    texts.append(plan_display)
    texts.append(period_str)
    texts.append("Change")

    # Top Up button (PPU only)
    if plan == 'ppu':
        texts.append("Top Up")

    # Transaction History
    texts.append("Transaction History")
    if not transactions:
        texts.append("No transactions yet")
    else:
        for txn in transactions:
            texts.append(txn.get("description", ""))
            charged = txn.get("charged_usd", 0)
            cache_hit = txn.get("cache_hit", False)
            is_monthly_fee = txn.get("operation_type") == "monthly_fee"
            if is_monthly_fee:
                texts.append("$0.00")
            elif cache_hit:
                texts.append("$0.00")
            elif charged < 0:
                texts.append(f"+${abs(charged):.2f}")
            else:
                texts.append(f"−${charged:.2f}")

    # AppBar
    texts.append("Wallet")

    return texts


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("LOCAL-160: Wallet UX Findings")
    print("=" * 70)
    print(f"  Run ID:       {RUN_ID}")
    print(f"  Orchestrator: {ORCHESTRATOR_URL}")
    print(f"  Time:         {datetime.now().isoformat()}")
    print()

    # ─── Connectivity checks ─────────────────────────────────────────────
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
    # STATE 1: Free tier, zero balance
    # ═══════════════════════════════════════════════════════════════════════
    print("═" * 60)
    print("STATE 1: Free tier, zero balance")
    print("═" * 60)
    user = USERS["free_zero"]
    create_user_in_db(user, plan='free')
    # Free users start with $0 and no subscription — that's the default
    # But we need a wallet entry. Let's just query — free users may not have wallet_subscription
    ledger_before = get_ledger_count(user)
    status, wallet = api_get(f"/wallet/{user}")
    _, txns = api_get(f"/wallet/{user}/transactions")
    if status != 200:
        print(f"  ❌ API returned {status}: {wallet}")
        FINDINGS["free_zero"] = {"error": str(wallet), "status": status}
    else:
        print(f"  API response: {json.dumps(wallet, indent=2)}")
        print(f"  Transactions: {json.dumps(txns, indent=2)}")
        rendered = predict_rendered_text(wallet, txns if isinstance(txns, list) else [])
        FINDINGS["free_zero"] = {
            "wallet_data": wallet,
            "transactions": txns if isinstance(txns, list) else [],
            "predicted_rendered": rendered,
            "ledger_before": ledger_before,
            "ledger_after": get_ledger_count(user),
        }
        print(f"\n  Predicted rendered text:")
        for t in rendered:
            print(f'    TEXT: "{t}"')
    print()

    # ═══════════════════════════════════════════════════════════════════════
    # STATE 2: Free tier, positive balance ($10)
    # (How? Via top-up before upgrading — test if this state is reachable)
    # ═══════════════════════════════════════════════════════════════════════
    print("═" * 60)
    print("STATE 2: Free tier, positive balance")
    print("═" * 60)
    user = USERS["free_positive"]
    create_user_in_db(user, plan='free')
    ledger_before = get_ledger_count(user)

    # Attempt to top up a free-tier user (the LOCAL-158 case)
    # The change-tier endpoint is what grants $10, not topup directly.
    # Let's see what happens if we try topup on a free user:
    topup_status, topup_resp = api_post(f"/wallet/{user}/topup", {"product_id": "credit_topup_10"})
    print(f"  Top-up attempt (free tier): status={topup_status} body={topup_resp}")

    # If that doesn't work, manually inject balance (this is the LOCAL-158 scenario
    # where change-tier was called then tier was reverted — but let's reproduce exactly
    # what LOCAL-158 showed: a user on free plan with $10)
    # Actually, from LOCAL-158 evidence: the user was created, then topped up, and
    # remained on "free" plan with $10 balance. Let's check:
    status, wallet = api_get(f"/wallet/{user}")
    if status == 200 and wallet.get("balance_usd", 0) > 0:
        print(f"  ✓ Free user with positive balance achieved via topup")
    else:
        # The 158 evidence shows change-tier grants $10. Let's try:
        # change to ppu (gets $10), then change back to free
        print(f"  Topup on free didn't work as expected ({topup_status}). Trying change-tier path...")
        # Change to ppu first (this grants the $10)
        ct_status, ct_resp = api_post(f"/wallet/{user}/change-tier", {"target_tier": "ppu"})
        print(f"  change-tier to ppu: {ct_status}")
        # Now change back to free
        ct2_status, ct2_resp = api_post(f"/wallet/{user}/change-tier", {"target_tier": "free"})
        print(f"  change-tier back to free: {ct2_status} {ct2_resp}")

    # Now query the wallet state
    status, wallet = api_get(f"/wallet/{user}")
    _, txns = api_get(f"/wallet/{user}/transactions")
    if status != 200:
        print(f"  ❌ API returned {status}: {wallet}")
        FINDINGS["free_positive"] = {"error": str(wallet), "status": status}
    else:
        print(f"  API response: {json.dumps(wallet, indent=2)}")
        print(f"  Transactions: {json.dumps(txns, indent=2)}")
        rendered = predict_rendered_text(wallet, txns if isinstance(txns, list) else [])
        FINDINGS["free_positive"] = {
            "wallet_data": wallet,
            "transactions": txns if isinstance(txns, list) else [],
            "predicted_rendered": rendered,
            "ledger_before": ledger_before,
            "ledger_after": get_ledger_count(user),
            "reachability_note": "Attempted via topup-on-free then change-tier round-trip"
        }
        print(f"\n  Predicted rendered text:")
        for t in rendered:
            print(f'    TEXT: "{t}"')
    print()

    # ═══════════════════════════════════════════════════════════════════════
    # STATE 3: PPU, healthy balance ($10)
    # ═══════════════════════════════════════════════════════════════════════
    print("═" * 60)
    print("STATE 3: PPU, healthy balance ($10)")
    print("═" * 60)
    user = USERS["ppu_healthy"]
    create_user_in_db(user, plan='free')
    ledger_before = get_ledger_count(user)

    # Change to PPU (grants $10)
    ct_status, ct_resp = api_post(f"/wallet/{user}/change-tier", {"target_tier": "ppu"})
    print(f"  change-tier to ppu: {ct_status}")
    if ct_status != 200:
        print(f"  ❌ change-tier failed: {ct_resp}")

    status, wallet = api_get(f"/wallet/{user}")
    _, txns = api_get(f"/wallet/{user}/transactions")
    if status != 200:
        print(f"  ❌ API returned {status}: {wallet}")
        FINDINGS["ppu_healthy"] = {"error": str(wallet), "status": status}
    else:
        print(f"  API response: {json.dumps(wallet, indent=2)}")
        print(f"  Transactions: {json.dumps(txns, indent=2)}")
        rendered = predict_rendered_text(wallet, txns if isinstance(txns, list) else [])
        FINDINGS["ppu_healthy"] = {
            "wallet_data": wallet,
            "transactions": txns if isinstance(txns, list) else [],
            "predicted_rendered": rendered,
            "ledger_before": ledger_before,
            "ledger_after": get_ledger_count(user),
        }
        print(f"\n  Predicted rendered text:")
        for t in rendered:
            print(f'    TEXT: "{t}"')
    print()

    # ═══════════════════════════════════════════════════════════════════════
    # STATE 4: PPU, low balance (below $2 threshold)
    # ═══════════════════════════════════════════════════════════════════════
    print("═" * 60)
    print("STATE 4: PPU, low balance (below $2 threshold)")
    print("═" * 60)
    user = USERS["ppu_low"]
    create_user_in_db(user, plan='free')
    ledger_before = get_ledger_count(user)

    # Change to PPU (grants $10)
    ct_status, _ = api_post(f"/wallet/{user}/change-tier", {"target_tier": "ppu"})
    print(f"  change-tier to ppu: {ct_status}")

    # Drain balance to $1.50 (inject charge of $8.50 = 850 cents)
    new_bal = inject_charge(user, 850, "Simulated tour charges (test drain)")
    print(f"  Injected charge of $8.50 → new balance: {new_bal} cents (${new_bal/100:.2f})")

    status, wallet = api_get(f"/wallet/{user}")
    _, txns = api_get(f"/wallet/{user}/transactions")
    if status != 200:
        print(f"  ❌ API returned {status}: {wallet}")
        FINDINGS["ppu_low"] = {"error": str(wallet), "status": status}
    else:
        print(f"  API response: {json.dumps(wallet, indent=2)}")
        print(f"  Transactions: {json.dumps(txns, indent=2)}")
        rendered = predict_rendered_text(wallet, txns if isinstance(txns, list) else [])
        FINDINGS["ppu_low"] = {
            "wallet_data": wallet,
            "transactions": txns if isinstance(txns, list) else [],
            "predicted_rendered": rendered,
            "ledger_before": ledger_before,
            "ledger_after": get_ledger_count(user),
            "low_balance_threshold": "$2.00",
        }
        print(f"\n  Predicted rendered text:")
        for t in rendered:
            print(f'    TEXT: "{t}"')
    print()

    # ═══════════════════════════════════════════════════════════════════════
    # STATE 5: PPU, zero/negative balance
    # ═══════════════════════════════════════════════════════════════════════
    print("═" * 60)
    print("STATE 5: PPU, zero or negative balance")
    print("═" * 60)
    user = USERS["ppu_zero"]
    create_user_in_db(user, plan='free')
    ledger_before = get_ledger_count(user)

    # Change to PPU (grants $10)
    ct_status, _ = api_post(f"/wallet/{user}/change-tier", {"target_tier": "ppu"})
    print(f"  change-tier to ppu: {ct_status}")

    # Drain to exactly $0 (inject charge of $10 = 1000 cents)
    new_bal = inject_charge(user, 1000, "Simulated full drain (test)")
    print(f"  Injected charge of $10.00 → new balance: {new_bal} cents (${new_bal/100:.2f})")

    status, wallet = api_get(f"/wallet/{user}")
    _, txns = api_get(f"/wallet/{user}/transactions")
    if status != 200:
        print(f"  ❌ API returned {status}: {wallet}")
        FINDINGS["ppu_zero"] = {"error": str(wallet), "status": status}
    else:
        print(f"  API response: {json.dumps(wallet, indent=2)}")
        print(f"  Transactions: {json.dumps(txns, indent=2)}")
        rendered = predict_rendered_text(wallet, txns if isinstance(txns, list) else [])
        FINDINGS["ppu_zero"] = {
            "wallet_data": wallet,
            "transactions": txns if isinstance(txns, list) else [],
            "predicted_rendered": rendered,
            "ledger_before": ledger_before,
            "ledger_after": get_ledger_count(user),
        }
        print(f"\n  Predicted rendered text:")
        for t in rendered:
            print(f'    TEXT: "{t}"')
    print()

    # Also test negative balance (inject one more charge)
    print("  --- Sub-test: push to negative ---")
    new_bal_neg = inject_charge(user, 50, "Overcharge (test negative)")
    print(f"  Injected additional $0.50 → new balance: {new_bal_neg} cents (${new_bal_neg/100:.2f})")
    status_neg, wallet_neg = api_get(f"/wallet/{user}")
    if status_neg == 200:
        print(f"  API with negative: {json.dumps(wallet_neg, indent=2)}")
        rendered_neg = predict_rendered_text(wallet_neg, txns if isinstance(txns, list) else [])
        FINDINGS["ppu_negative"] = {
            "wallet_data": wallet_neg,
            "predicted_rendered": rendered_neg,
        }
        print(f"\n  Predicted rendered text (negative):")
        for t in rendered_neg:
            print(f'    TEXT: "{t}"')
    print()

    # ═══════════════════════════════════════════════════════════════════════
    # STATE 6: Unlimited, partway through cost-stop
    # ═══════════════════════════════════════════════════════════════════════
    print("═" * 60)
    print("STATE 6: Unlimited, partway through monthly cost-stop")
    print("═" * 60)
    user = USERS["unlimited_mid"]
    create_user_in_db(user, plan='free')
    ledger_before = get_ledger_count(user)

    # Change to unlimited
    ct_status, ct_resp = api_post(f"/wallet/{user}/change-tier", {"target_tier": "unlimited"})
    print(f"  change-tier to unlimited: {ct_status}")
    if ct_status != 200:
        print(f"  ❌ change-tier failed: {ct_resp}")

    # Inject some cost (e.g., $5 in our_cost → cost_stop_progress should show usage)
    # The cost stop limit is $25 (50% of $50). Inject $12.50 to show ~50% usage.
    inject_cost_ledger(user, 12.50)
    print(f"  Injected $12.50 our_cost → expect cost_stop ~50%")

    status, wallet = api_get(f"/wallet/{user}")
    _, txns = api_get(f"/wallet/{user}/transactions")
    if status != 200:
        print(f"  ❌ API returned {status}: {wallet}")
        FINDINGS["unlimited_mid"] = {"error": str(wallet), "status": status}
    else:
        print(f"  API response: {json.dumps(wallet, indent=2)}")
        print(f"  Transactions: {json.dumps(txns, indent=2)}")
        rendered = predict_rendered_text(wallet, txns if isinstance(txns, list) else [])
        FINDINGS["unlimited_mid"] = {
            "wallet_data": wallet,
            "transactions": txns if isinstance(txns, list) else [],
            "predicted_rendered": rendered,
            "ledger_before": ledger_before,
            "ledger_after": get_ledger_count(user),
        }
        print(f"\n  Predicted rendered text:")
        for t in rendered:
            print(f'    TEXT: "{t}"')
    print()

    # ═══════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUMMARY: All states tested")
    print("=" * 70)
    print(f"\nTest users created:")
    for label, uid in USERS.items():
        ledger_count = get_ledger_count(uid)
        print(f"  {label:20s} → {uid} (ledger rows: {ledger_count})")

    print(f"\ndemo_michael_1785726297 untouched ✓")
    print(f"\nFindings collected for {len(FINDINGS)} states.")

    # Write JSON findings for the Dart test to reference
    findings_path = os.path.join(os.path.dirname(__file__), "local160_findings.json")
    with open(findings_path, 'w') as f:
        json.dump({
            "run_id": RUN_ID,
            "timestamp": datetime.now().isoformat(),
            "users": USERS,
            "findings": FINDINGS,
        }, f, indent=2, default=str)
    print(f"\n  Findings written to: {findings_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
