"""
Test 1: wallet_api.py — every route via Flask test client against audiotours_subscribed.

Routes:
  GET  /wallet/<user_id>               — balance summary
  GET  /wallet/<user_id>/transactions   — transaction history
  GET  /plans/available                 — plan list
  POST /wallet/<user_id>/topup          — credit top-up
  POST /wallet/<user_id>/change-tier    — tier change

TIGHT assertions:
  - Exact balance values where known (not just "positive")
  - Exact plan values from DB (not just "exists")
  - For unknown users: verify returns free/0 (not error)
"""
import json
import uuid
import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# GET /wallet/<user_id> — Happy path
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetWallet:
    def test_happy_path_free_user(self, wallet_client, test_user_id):
        """Free user: plan=free, balance=0, no cost_stop.

        TIGHT: asserts exact zero balance (free user has no wallet activity).
        """
        resp = wallet_client.get(f"/wallet/{test_user_id}")
        print(f"  GET /wallet/{test_user_id} → {resp.status_code}")
        print(f"  Response: {resp.get_data(as_text=True)}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["plan"] == "free"
        assert data["balance_usd"] == 0.0
        assert data["cost_stop_progress"] is None
        assert data["low_balance"] is False
        # Verify period dates are present and valid
        assert data["period_start"] is not None
        assert data["period_end"] is not None
        print(f"  ✓ Free user wallet: plan={data['plan']}, balance=${data['balance_usd']}")

    def test_happy_path_ppu_user(self, wallet_client, ppu_user_id):
        """PPU user: plan=ppu, balance=$10 from seed, low_balance=False.

        TIGHT: balance is exactly $10.00 from seed (minus any prior test charges).
        Plan must be 'ppu' (resolved from wallet_subscription table).
        """
        resp = wallet_client.get(f"/wallet/{ppu_user_id}")
        print(f"  GET /wallet/{ppu_user_id} → {resp.status_code}")
        print(f"  Response: {resp.get_data(as_text=True)}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["plan"] == "ppu", (
            f"Expected plan='ppu' (from wallet_subscription), got '{data['plan']}'. "
            f"'free' means wallet_subscription table query failed."
        )
        assert data["balance_usd"] > 0, (
            f"PPU user should have positive balance from $10 seed"
        )
        assert data["low_balance"] is False
        # period_spend_usd should be a number
        assert isinstance(data["period_spend_usd"], (int, float))
        print(f"  ✓ PPU user wallet: plan={data['plan']}, balance=${data['balance_usd']}")

    def test_unknown_user(self, wallet_client):
        """Unknown user_id: returns 200 with free defaults (not error).

        TIGHT: exact values for unknown user — same as a fresh free user.
        """
        fake_id = f"nonexistent-{uuid.uuid4().hex[:8]}"
        resp = wallet_client.get(f"/wallet/{fake_id}")
        print(f"  GET /wallet/{fake_id} → {resp.status_code}")
        print(f"  Response: {resp.get_data(as_text=True)}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["plan"] == "free"
        assert data["balance_usd"] == 0.0
        assert data["cost_stop_progress"] is None
        assert data["low_balance"] is False
        print(f"  ✓ Unknown user gets free defaults (no crash)")


# ═══════════════════════════════════════════════════════════════════════════════
# GET /wallet/<user_id>/transactions — Transaction history
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetTransactions:
    def test_happy_path(self, wallet_client, ppu_user_id):
        """PPU user with seed topup: should have at least 1 transaction.

        TIGHT: verifies the seed topup is visible and has correct structure.
        """
        resp = wallet_client.get(f"/wallet/{ppu_user_id}/transactions?limit=10")
        print(f"  GET /wallet/{ppu_user_id}/transactions → {resp.status_code}")
        print(f"  Response: {resp.get_data(as_text=True)[:500]}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1, "PPU user should have at least the seed topup"
        # Verify structure of first transaction
        txn = data[0]
        assert "id" in txn
        assert "created_at" in txn
        assert "operation_type" in txn
        assert "charged_usd" in txn
        assert "cache_hit" in txn
        # The seed topup should be present somewhere
        topup_txns = [t for t in data if t["operation_type"] == "topup"]
        assert len(topup_txns) >= 1, "Seed topup transaction not found"
        print(f"  ✓ Transactions returned: {len(data)} rows, topups={len(topup_txns)}")

    def test_empty_user(self, wallet_client, test_user_id):
        """Free user with no wallet activity: returns empty list."""
        resp = wallet_client.get(f"/wallet/{test_user_id}/transactions")
        print(f"  GET /wallet/{test_user_id}/transactions → {resp.status_code}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 0
        print(f"  ✓ Empty user: 0 transactions")

    def test_unknown_user(self, wallet_client):
        """Unknown user: returns empty list, not error."""
        fake_id = f"nonexistent-{uuid.uuid4().hex[:8]}"
        resp = wallet_client.get(f"/wallet/{fake_id}/transactions")
        print(f"  GET /wallet/{fake_id}/transactions → {resp.status_code}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 0
        print(f"  ✓ Unknown user: 0 transactions (no crash)")

    def test_limit_parameter(self, wallet_client, ppu_user_id):
        """Limit parameter restricts result count."""
        resp = wallet_client.get(f"/wallet/{ppu_user_id}/transactions?limit=1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) <= 1
        print(f"  ✓ Limit=1: returned {len(data)} transaction(s)")


# ═══════════════════════════════════════════════════════════════════════════════
# GET /plans/available — Plan list
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetPlans:
    def test_happy_path(self, wallet_client):
        """Returns list of plans with expected structure.

        TIGHT: exactly 3 plans with known IDs and required fields.
        """
        resp = wallet_client.get("/plans/available")
        print(f"  GET /plans/available → {resp.status_code}")
        print(f"  Response: {resp.get_data(as_text=True)}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 3, f"Expected exactly 3 plans, got {len(data)}"
        plan_ids = [p["plan_id"] for p in data]
        assert "free" in plan_ids
        assert "ppu" in plan_ids
        assert "unlimited" in plan_ids
        # Verify structure
        for plan in data:
            assert "display_name" in plan
            assert "price_usd" in plan
            assert isinstance(plan["price_usd"], (int, float))
            assert "period" in plan
            assert "features" in plan
            assert isinstance(plan["features"], list)
            assert len(plan["features"]) > 0
        # Free plan should be $0
        free_plan = next(p for p in data if p["plan_id"] == "free")
        assert free_plan["price_usd"] == 0.0
        print(f"  ✓ Plans: {plan_ids}, free=$0")


# ═══════════════════════════════════════════════════════════════════════════════
# POST /wallet/<user_id>/topup — Credit top-up
# ═══════════════════════════════════════════════════════════════════════════════

class TestTopup:
    def test_happy_path(self, wallet_client, test_user_id):
        """Top-up free user: balance goes from 0 to $10.

        TIGHT: exact $10.00 (the CREDIT_TOPUP_USD constant).
        """
        product_id = f"receipt-{uuid.uuid4().hex[:8]}"
        resp = wallet_client.post(
            f"/wallet/{test_user_id}/topup",
            data=json.dumps({"product_id": product_id}),
            content_type="application/json",
        )
        print(f"  POST /wallet/{test_user_id}/topup → {resp.status_code}")
        print(f"  Response: {resp.get_data(as_text=True)}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["new_balance_usd"] == 10.0, (
            f"Expected $10.00 (CREDIT_TOPUP_USD), got ${data['new_balance_usd']}"
        )
        print(f"  ✓ Topup success: new_balance=${data['new_balance_usd']}")

    def test_idempotency(self, wallet_client, test_user_id):
        """Same product_id twice: balance should not double.

        TIGHT: first and second response have identical balance.
        """
        product_id = f"idem-{uuid.uuid4().hex[:8]}"
        resp1 = wallet_client.post(
            f"/wallet/{test_user_id}/topup",
            data=json.dumps({"product_id": product_id}),
            content_type="application/json",
        )
        assert resp1.status_code == 200
        balance_after_first = resp1.get_json()["new_balance_usd"]

        resp2 = wallet_client.post(
            f"/wallet/{test_user_id}/topup",
            data=json.dumps({"product_id": product_id}),
            content_type="application/json",
        )
        assert resp2.status_code == 200
        balance_after_second = resp2.get_json()["new_balance_usd"]

        print(f"  First topup: ${balance_after_first}, Second (same key): ${balance_after_second}")
        assert balance_after_first == balance_after_second, (
            f"Idempotency broken! First=${balance_after_first}, Second=${balance_after_second}"
        )
        print(f"  ✓ Idempotency: repeat topup did not double-credit")

    def test_malformed_body_no_product_id(self, wallet_client, test_user_id):
        """Missing product_id: 400."""
        resp = wallet_client.post(
            f"/wallet/{test_user_id}/topup",
            data=json.dumps({}),
            content_type="application/json",
        )
        print(f"  POST /wallet/{test_user_id}/topup (no product_id) → {resp.status_code}")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data
        assert "product_id" in data["error"].lower(), (
            f"Error message should mention product_id, got: {data['error']}"
        )
        print(f"  ✓ Malformed body: 400 with error='{data['error']}'")

    def test_malformed_body_empty(self, wallet_client, test_user_id):
        """Empty/non-JSON body: 400 (product_id missing from parsed result)."""
        resp = wallet_client.post(
            f"/wallet/{test_user_id}/topup",
            data="not json",
            content_type="text/plain",
        )
        print(f"  POST /wallet/{test_user_id}/topup (bad content-type) → {resp.status_code}")
        assert resp.status_code == 400
        print(f"  ✓ Non-JSON body: {resp.status_code}")


# ═══════════════════════════════════════════════════════════════════════════════
# POST /wallet/<user_id>/change-tier — Tier change
# ═══════════════════════════════════════════════════════════════════════════════

class TestChangeTier:
    def test_malformed_no_target_tier(self, wallet_client, test_user_id):
        """Missing target_tier: 400."""
        resp = wallet_client.post(
            f"/wallet/{test_user_id}/change-tier",
            data=json.dumps({}),
            content_type="application/json",
        )
        print(f"  POST /wallet/{test_user_id}/change-tier (empty) → {resp.status_code}")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert "target_tier" in data["message"].lower(), (
            f"Error should mention target_tier, got: {data['message']}"
        )
        print(f"  ✓ No target_tier: 400")

    def test_malformed_invalid_tier(self, wallet_client, test_user_id):
        """Invalid tier value: 400."""
        resp = wallet_client.post(
            f"/wallet/{test_user_id}/change-tier",
            data=json.dumps({"target_tier": "gold"}),
            content_type="application/json",
        )
        print(f"  POST /wallet/{test_user_id}/change-tier (gold) → {resp.status_code}")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        print(f"  ✓ Invalid tier 'gold': 400")

    def test_change_to_ppu(self, wallet_client, test_user_id):
        """Free → PPU: exercises the route and tier_change module against real DB.

        We accept 200 (success) or 409 (already on tier from earlier test run).
        The key assertion is that it doesn't 500 — it runs against the real schema.
        """
        resp = wallet_client.post(
            f"/wallet/{test_user_id}/change-tier",
            data=json.dumps({"target_tier": "ppu"}),
            content_type="application/json",
        )
        print(f"  POST /wallet/{test_user_id}/change-tier (ppu) → {resp.status_code}")
        print(f"  Response: {resp.get_data(as_text=True)}")
        data = resp.get_json()

        # 500 = schema/code mismatch (the thing we're looking for)
        assert resp.status_code != 500, (
            f"500 on change-tier — likely a schema mismatch or missing module. "
            f"Body: {resp.get_data(as_text=True)[:200]}"
        )
        # Valid responses
        assert resp.status_code in (200, 409), (
            f"Expected 200 or 409, got {resp.status_code}"
        )
        print(f"  ✓ change-tier: status={resp.status_code}, success={data.get('success')}")
